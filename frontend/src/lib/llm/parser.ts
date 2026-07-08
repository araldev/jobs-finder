// Response parser for the CV-adaptation LLM call.
//
// Mirrors the defensive parsing strategy in
// `backend/src/jobs_finder/infrastructure/llm/_cv_prompt.parse_adapted_cv_response`:
// try 3 strategies in order — direct JSON parse, JSON in markdown code
// block, first-brace substring. Each strategy is tried before
// raising, so the caller gets a structured `AdaptedCV` whenever the
// LLM emits ANY JSON object matching the schema (even with markdown
// wrappers or trailing prose).
//
// Thinking-block stripping (the M2.x model family emits
// `<think>...</think>` tags) is also mirrored here.

import type { AdaptedCV, AdaptedCVProject, AdaptedCVProjectLink } from "./prompts";

export class AdaptedCVParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AdaptedCVParseError";
  }
}

/**
 * Maximum number of links accepted per project, per REQ-PJL-001
 * scenario "over-cap is capped". Real LLM output is usually 3-5
 * links per project; the cap protects the renderer layout from
 * pathological inputs.
 */
const MAX_LINKS_PER_PROJECT = 8;

const KNOWN_PLATFORMS: Record<string, string> = {
  "github.com": "GitHub",
  "gitlab.com": "GitLab",
  "bitbucket.org": "Bitbucket",
  "npmjs.com": "npm",
  "npmjs.org": "npm",
  "storybook.js.org": "Storybook",
  "youtube.com": "YouTube",
  "youtu.be": "YouTube",
  "linkedin.com": "LinkedIn",
  "medium.com": "Medium",
  "dev.to": "DEV",
};

/**
 * Derive a short, human-readable chip label from a URL.
 *
 * Mirrors the Python `derive_chip_label` helper in
 * `backend/.../cv/_template.py` byte-for-byte. Algorithm:
 *   1. Empty / unparseable URL → "" (never throw).
 *   2. Lowercase the hostname; strip a leading "www.".
 *   3. Look the hostname up in `KNOWN_PLATFORMS`.
 *   4. Fall back to the first label of the hostname, capitalized
 *      (e.g. "user.example.com" → "User").
 *
 * Used by the parser (legacy `url` → synthesized single-link) and
 * the renderer (chip fallback when the LLM emits an empty label).
 */
export function deriveChipLabel(url: string): string {
  if (!url) return "";
  let host: string;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
  if (host.startsWith("www.")) {
    host = host.slice(4);
  }
  if (!host) return "";
  if (host in KNOWN_PLATFORMS) {
    return KNOWN_PLATFORMS[host]!;
  }
  const firstLabel = host.split(".")[0];
  return firstLabel ? firstLabel.charAt(0).toUpperCase() + firstLabel.slice(1) : "";
}

const MARKDOWN_JSON_PATTERNS = [
  /```json\s*(\{[\s\S]*?\})\s*```/,
  /```\s*(\{[\s\S]*?\})\s*```/,
];

function stripThinkingBlocks(raw: string): string {
  // Strip ``...</think> and `<thinking>...</thinking>` blocks
  // ENTIRELY (content + tags). MiniMax-M3 emits a long
  // "Let me analyze..." preamble inside the think block before the
  // JSON, and the old "remove tags only" approach left the preamble
  // text mixed with the JSON, which broke the brace-substring
  // strategy (the first `{` it found was inside the think content,
  // not in the JSON).
  //
  // Falls back to "strip from `<think>` to end-of-string" when the
  // closing tag is missing (malformed response, max_tokens hit
  // mid-thinking). In that case the JSON never arrived, but at
  // least the parser can fail with a clean error instead of
  // trying to parse a half-thought preamble.
  let cleaned = raw;

  // Properly paired blocks: content + open + close tag.
  cleaned = cleaned.replace(/<think>[\s\S]*?<\/think>/g, "");
  cleaned = cleaned.replace(/<thinking>[\s\S]*?<\/thinking>/g, "");

  // Unpaired open tags (no closing tag in the response). Drop
  // everything from the open tag to end-of-string — there's no
  // useful content after an unclosed think block.
  cleaned = cleaned.replace(/<think>[\s\S]*$/g, "");
  cleaned = cleaned.replace(/<thinking>[\s\S]*$/g, "");

  return cleaned.trim();
}

function tryParseJson(text: string): unknown | undefined {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function extractFirstBraced(text: string): unknown | undefined {
  const first = text.indexOf("{");
  const last = text.lastIndexOf("}");
  if (first === -1 || last === -1 || last <= first) return undefined;
  return tryParseJson(text.slice(first, last + 1));
}

function extractMarkdownJson(text: string): unknown | undefined {
  for (const pattern of MARKDOWN_JSON_PATTERNS) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const result = tryParseJson(match[1]);
      if (result !== undefined) return result;
    }
  }
  return undefined;
}

function strOr(value: unknown, fallback = ""): string {
  return value === null || value === undefined ? fallback : String(value);
}

function photoOr(value: unknown): string | null {
  // The LLM is supposed to emit `photo: null` (the route handler
  // overlays the extracted image). If the model emits a non-string
  // value (an object, array, number), we coerce to `null` rather
  // than to a string — preserves the "no photo" signal and avoids
  // surfacing malformed values to the renderer.
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  return null;
}

function listOr(value: unknown): string[] {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((v) => String(v));
  }
  return [];
}

function linksOr(value: unknown): AdaptedCVProjectLink[] {
  // Parse a `links` array from the LLM JSON, dropping invalid
  // entries (empty URL, non-http(s) scheme) and capping at
  // MAX_LINKS_PER_PROJECT per REQ-PJL-001.
  //
  // Returns an empty list for missing or non-array input — the
  // caller decides whether to synthesize from the legacy `url`.
  if (!value || !Array.isArray(value)) return [];
  const out: AdaptedCVProjectLink[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object") continue;
    const e = entry as Record<string, unknown>;
    const url = e.url;
    if (typeof url !== "string" || !url) continue;
    // Only http:// and https:// survive WinAnsi + the browser's
    // "open this link" behavior. Drop ftp://, javascript:,
    // file://, etc. — they'd either crash the renderer or open
    // the wrong thing in the browser.
    if (!url.startsWith("http://") && !url.startsWith("https://")) continue;
    const label = e.label;
    const labelStr = typeof label === "string" ? label : "";
    out.push({ label: labelStr, url });
    if (out.length >= MAX_LINKS_PER_PROJECT) break;
  }
  return out;
}

function projectsOr(value: unknown): AdaptedCVProject[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((p) => {
      const proj = (p ?? {}) as Record<string, unknown>;
      // Per REQ-PJL-001 + REQ-PJL-002: prefer the new `links[]`
      // shape when present; fall back to synthesizing a one-entry
      // list from the legacy `url` field (backward compat — any
      // cached LLM output that still uses the singular URL shape
      // keeps working).
      const links = linksOr(proj.links);
      const legacyUrl =
        typeof proj.url === "string" && proj.url.length > 0 ? proj.url : null;
      const effectiveLinks =
        links.length > 0
          ? links
          : legacyUrl
            ? [{ label: deriveChipLabel(legacyUrl), url: legacyUrl }]
            : [];
      return {
        name: strOr(proj.name),
        description: strOr(proj.description, ""),
        technologies: listOr(proj.technologies),
        links: effectiveLinks,
      };
    })
    .filter((p) => p.name.length > 0);
}

export function parseAdaptedCVResponse(raw: string): AdaptedCV {
  const cleaned = stripThinkingBlocks(raw);
  const errors: string[] = [];

  // Strategy 1: direct parse
  let data: unknown;
  try {
    data = JSON.parse(cleaned);
  } catch (e) {
    errors.push(`direct: ${(e as Error).message}`);
  }

  // Strategy 2: extract from markdown code block
  if (data === undefined || data === null) {
    const fromMd = extractMarkdownJson(cleaned);
    if (fromMd !== undefined) {
      data = fromMd;
    } else {
      errors.push("markdown: no match");
    }
  }

  // Strategy 3: find first { and last } and try that substring
  if (data === undefined || data === null) {
    const fromBrace = extractFirstBraced(cleaned);
    if (fromBrace !== undefined) {
      data = fromBrace;
    } else {
      errors.push("brace: no match");
    }
  }

  if (data === undefined || data === null || typeof data !== "object" || Array.isArray(data)) {
    // Server-side debug log: a truncated preview of the raw LLM
    // response so we can see what the model is actually emitting
    // (the user-facing error message below intentionally does NOT
    // echo this — AGENTS.md rule #24). Help debug future MiniMax
    // JSON-formatting quirks without leaking the payload to the
    // client.
    console.error(
      "parser: LLM returned non-JSON. Tried strategies:",
      errors.join("; "),
      "Raw preview:",
      raw.slice(0, 500),
    );
    // AGENTS.md rule #24 — the error message MUST NOT echo the raw
    // LLM response. The "Tried: ..." line names the strategies that
    // failed (helps debugging) but does NOT include the response
    // payload. The caller maps this to a 422 with a static message.
    throw new AdaptedCVParseError(
      `LLM response is not a JSON object (tried: ${errors.join("; ")}).`,
    );
  }

  const obj = data as Record<string, unknown>;

  const experience = Array.isArray(obj.experience)
    ? obj.experience.map((e) => {
        const exp = (e ?? {}) as Record<string, unknown>;
        return {
          company: strOr(exp.company),
          title: strOr(exp.title),
          start_date: strOr(exp.start_date, ""),
          end_date: strOr(exp.end_date, "Presente"),
          description: strOr(exp.description, ""),
          location: exp.location ? strOr(exp.location) : null,
        };
      })
    : [];

  const education = Array.isArray(obj.education)
    ? obj.education.map((e) => {
        const edu = (e ?? {}) as Record<string, unknown>;
        return {
          degree: strOr(edu.degree),
          institution: strOr(edu.institution),
          year: strOr(edu.year, ""),
          grade: edu.grade ? strOr(edu.grade) : null,
        };
      })
    : [];

  const projects = projectsOr(obj.projects);

  return {
    name: strOr(obj.name, "Sin nombre"),
    email: strOr(obj.email, ""),
    phone: strOr(obj.phone, ""),
    location: strOr(obj.location, ""),
    summary: strOr(obj.summary, ""),
    experience,
    education,
    projects,
    certifications: listOr(obj.certifications),
    skills: listOr(obj.skills),
    languages: listOr(obj.languages),
    photo: photoOr(obj.photo),
  };
}

// ── Chat-filter response parser ──────────────────────────────────
//
// Mirrors `_prompt.parse_user_message` validation: the LLM returns a
// JSON object with `matching_ids: string[]` and `explanation: string`.
// Any deviation throws — the caller maps the error to an SSE `error`
// event with code `llm_parse`.

export interface ChatFilterResult {
  matching_ids: string[];
  explanation: string;
}

export class ChatFilterParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatFilterParseError";
  }
}

export function parseChatFilterResponse(raw: string): ChatFilterResult {
  const cleaned = raw.trim();
  let data: unknown;

  // Try direct JSON parse first.
  try {
    data = JSON.parse(cleaned);
  } catch {
    // Fallback: find first { and last }.
    const first = cleaned.indexOf("{");
    const last = cleaned.lastIndexOf("}");
    if (first === -1 || last === -1 || last <= first) {
      // AGENTS.md rule #24 — error message MUST NOT echo the raw
      // LLM response payload. Caller maps this to a 502 with a
      // static "LLM response could not be parsed" detail.
      throw new ChatFilterParseError("LLM response is not a JSON object");
    }
    try {
      data = JSON.parse(cleaned.slice(first, last + 1));
    } catch {
      throw new ChatFilterParseError("LLM response is not a JSON object");
    }
  }

  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new ChatFilterParseError("LLM response is not a JSON object");
  }

  const obj = data as Record<string, unknown>;
  const matching_ids = Array.isArray(obj.matching_ids)
    ? obj.matching_ids.map((id) => String(id))
    : [];
  const explanation = typeof obj.explanation === "string" ? obj.explanation : "";

  return { matching_ids, explanation };
}