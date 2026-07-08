import "server-only";

import type { AdaptedCV, AdaptedCVProjectLink } from "@/lib/llm/prompts";

/**
 * TS port of `substitute_hyperlinks_in_cv` from the Python backend.
 *
 * Replaces LLM-invented URLs in `cv.projects[].links[]` with the
 * real URLs from the PDF hyperlink map (by label match).
 *
 * When `hyperlinks` is empty → returns `cv` unchanged (no-op,
 * backward compat — REQ-CLP-006). Otherwise: builds
 * `url_map = {normalized_label: url}` and walks each
 * `project.links[*]` entry. For each entry, looks up the real URL
 * via 4-strategy cascade: exact → substring either way → token
 * Jaccard > 0.5. On a match, substitutes the URL; on no match,
 * keeps the LLM's URL.
 *
 * Returns a NEW `AdaptedCV` (does not mutate the input).
 *
 * Mirrors `substitute_hyperlinks_in_cv` in
 * `backend/src/jobs_finder/application/usecases/generate_adapted_cv.py`
 * + `_link_matcher.py`.
 */

export interface HyperlinkLike {
  label: string;
  url: string;
  // Page number is accepted (and ignored) for parity with the full
  // HyperlinkEntry shape produced by the extractor; the post-
  // processor only needs (label, url) for matching.
  page?: number;
}

export function substituteHyperlinksInCv(
  cv: AdaptedCV,
  hyperlinks: readonly HyperlinkLike[],
): AdaptedCV {
  if (!hyperlinks || hyperlinks.length === 0) {
    return cv;
  }

  const urlMap = buildUrlMap(hyperlinks);

  const newProjects = cv.projects.map((project) => {
    const newLinks: AdaptedCVProjectLink[] = project.links.map((link) => {
      const realUrl = findUrlForLabel(link.label, urlMap);
      if (realUrl && realUrl !== link.url) {
        return { label: link.label, url: realUrl };
      }
      // No match — keep the original link (don't lose data the LLM
      // already had).
      return link;
    });
    return { ...project, links: newLinks };
  });

  return { ...cv, projects: newProjects };
}

/**
 * Normalize a hyperlink label for matching: lowercase, strip common
 * suffixes ("link", "url", "enlace"), strip common prefixes, collapse
 * whitespace. Mirrors `normalize_label` in `_link_matcher.py`.
 */
export function normalizeLabel(s: string): string {
  if (!s) return "";
  let out = s.toLowerCase().trim();
  const suffixes = [" link", " enlace", " url", " href", " aqui", " here", " ver"];
  const prefixes = ["go to ", "visit ", "see ", "ver ", "abre ", "open "];
  for (const suf of suffixes) {
    if (out.endsWith(suf)) {
      out = out.slice(0, -suf.length).trimEnd();
    }
  }
  for (const pre of prefixes) {
    if (out.startsWith(pre)) {
      out = out.slice(pre.length).trimStart();
    }
  }
  // Collapse internal whitespace.
  return out.split(/\s+/).filter(Boolean).join(" ");
}

/**
 * Build a normalized_label -> url map. Last-write-wins on collision
 * (a PDF with two "Github link" labels pointing to different URLs is
 * pathological — the last one parsed wins).
 */
export function buildUrlMap(
  hyperlinks: readonly HyperlinkLike[],
): Map<string, string> {
  const map = new Map<string, string>();
  for (const h of hyperlinks) {
    const key = normalizeLabel(h.label);
    if (!key) continue;
    map.set(key, h.url);
  }
  return map;
}

/**
 * Find URL by label using the 4-strategy cascade. First hit wins.
 *
 * Strategies (mirrors `find_url_for_label` in `_link_matcher.py`):
 *   1. Exact normalized match.
 *   2. Substring both directions (`norm` ⊂ `pdfLabel` OR `pdfLabel` ⊂ `norm`).
 *   3. Token Jaccard overlap > 0.5.
 *
 * Returns `null` when no strategy hits.
 */
export function findUrlForLabel(
  label: string,
  urlMap: ReadonlyMap<string, string>,
): string | null {
  if (!label || urlMap.size === 0) return null;
  const norm = normalizeLabel(label);
  if (!norm) return null;

  // Strategy 1: exact normalized.
  const exact = urlMap.get(norm);
  if (exact) return exact;

  // Strategy 2: substring either direction.
  for (const [pdfLabel, url] of urlMap) {
    if (pdfLabel && (norm.includes(pdfLabel) || pdfLabel.includes(norm))) {
      return url;
    }
  }

  // Strategy 3: token Jaccard > 0.5.
  const normTokens = new Set(norm.split(/\s+/).filter(Boolean));
  if (normTokens.size === 0) return null;
  let bestUrl: string | null = null;
  let bestScore = 0.5;
  for (const [pdfLabel, url] of urlMap) {
    const pdfTokens = new Set(pdfLabel.split(/\s+/).filter(Boolean));
    if (pdfTokens.size === 0) continue;
    const intersection = [...normTokens].filter((t) => pdfTokens.has(t)).length;
    const union = new Set([...normTokens, ...pdfTokens]).size;
    if (union === 0) continue;
    const jaccard = intersection / union;
    if (jaccard > bestScore) {
      bestScore = jaccard;
      bestUrl = url;
    }
  }
  return bestUrl;
}
