import "server-only";

import { getDocumentProxy } from "unpdf";

/**
 * A single hyperlink extracted from the original CV PDF.
 *
 * Pairs the visible text at a link's rect with the URL it points to.
 * Used to build the HYPERLINKS — ORIGINAL URL MAP in the LLM prompt
 * so the LLM doesn't invent URLs from labels.
 *
 * Mirrors `HyperlinkEntry` in
 * `backend/src/jobs_finder/infrastructure/cv/_parser.py`.
 */
export interface HyperlinkEntry {
  label: string;
  url: string;
  page: number;
}

/**
 * Extract external http(s) hyperlinks from a CV PDF.
 *
 * The frontend uses `unpdf` (which wraps `pdfjs-dist` from Mozilla) for
 * PDF parsing, so we call `page.getAnnotations()` directly on the
 * pdfjs document. The function returns the (label, url, page) triples
 * in reading order (page 1 first).
 *
 * Robustness against design-tool exports (Canva, Figma, etc.): the
 * previous `cv-link-preservation` change shipped a Python extractor
 * using PyMuPDF's `page.get_textbox(rect)` for label lookup. The TS
 * equivalent doesn't have a single-call helper, so we use a soft
 * bbox-overlap check (text bbox must overlap the annotation's rect
 * in BOTH x and y) — which works for both tight-baseline rects
 * (Canva-style) and oversized rects that wrap a whole text box.
 *
 * Returns `[]` on any failure (malformed PDF, image-only PDF,
 * library error). The route caller treats an empty result the same
 * as a PDF without hyperlinks — no MAP section, no post-processor
 * substitution.
 */
export async function extractPdfHyperlinks(
  bytes: ArrayBuffer,
): Promise<HyperlinkEntry[]> {
  let pdf: Awaited<ReturnType<typeof getDocumentProxy>>;
  try {
    pdf = await getDocumentProxy(new Uint8Array(bytes));
  } catch (err) {
    console.error("pdf/extract-hyperlinks: document open failed", err);
    return [];
  }

  const result: HyperlinkEntry[] = [];
  for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
    let page: PdfjsPage;
    try {
      // pdfjs-dist's `getPage` returns a `PDFPageProxy`. We use a
      // structural type (`PdfjsPage`) so the extractor doesn't
      // depend on pdfjs-dist's exported types — and so we can
      // mock it in unit tests.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      page = (await pdf.getPage(pageNum)) as any;
    } catch (err) {
      console.error(
        `pdf/extract-hyperlinks: page ${pageNum} load failed`,
        err,
      );
      continue;
    }
    const pageEntries = await extractPageHyperlinks(page, pageNum);
    result.push(...pageEntries);
  }

  // Destroy the document so pdfjs can release its worker.
  try {
    await pdf.destroy();
  } catch {
    // best-effort
  }

  return result;
}

interface PdfjsPage {
  getAnnotations: () => Promise<PdfjsAnnotation[]>;
  getTextContent: () => Promise<PdfjsTextContent>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  cleanup?: () => void;
}

interface PdfjsAnnotation {
  subtype: string;
  url?: string | unknown;
  rect?: number[] | unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

interface PdfjsTextContent {
  items: Array<{
    str?: string;
    transform?: number[];
    width?: number;
    height?: number;
  }>;
}

async function extractPageHyperlinks(
  page: PdfjsPage,
  pageNum: number,
): Promise<HyperlinkEntry[]> {
  let annotations: PdfjsAnnotation[];
  let textContent: PdfjsTextContent;
  try {
    [annotations, textContent] = await Promise.all([
      page.getAnnotations(),
      page.getTextContent(),
    ]);
  } catch (err) {
    console.error(
      `pdf/extract-hyperlinks: page ${pageNum} annotations/text failed`,
      err,
    );
    return [];
  }

  const entries: HyperlinkEntry[] = [];
  for (const annot of annotations) {
    if (annot.subtype !== "Link") continue;

    const url = annot.url;
    if (typeof url !== "string" || !url) continue;
    if (!url.startsWith("http://") && !url.startsWith("https://")) continue;

    const rect = annot.rect;
    if (!Array.isArray(rect) || rect.length !== 4) continue;
    const [x1, y1, x2, y2] = rect as number[];
    // PDF.js uses standard PDF user space — annotation rect is
    // [xMin, yMin, xMax, yMax] where yMin < yMax (origin at
    // bottom-left, Y-up). Skip degenerate rects.
    if (x1 === x2 && y1 === y2) continue;

    const label = deriveLinkLabel(rect as [number, number, number, number], textContent);
    if (!label) continue;

    entries.push({ label, url, page: pageNum });
  }
  return entries;
}

/**
 * Find the visible text inside the annotation's rect via soft bbox
 * overlap (works for tight-baseline Canva rects AND oversized rects).
 *
 * When multiple text items fall inside a tall rect, the FIRST one in
 * pdfjs reading order wins (mirrors the Python `get_textbox` first-
 * line heuristic — PyMuPDF returns in reading order, pdfjs does too).
 */
function deriveLinkLabel(
  rect: [number, number, number, number],
  textContent: PdfjsTextContent,
): string {
  const [ax1, ay1, ax2, ay2] = rect;
  // Normalize rect (pdfjs can return either y1<y2 or y1>y2 for
  // some annotation types — be defensive).
  const rMinX = Math.min(ax1, ax2);
  const rMaxX = Math.max(ax1, ax2);
  const rMinY = Math.min(ay1, ay2);
  const rMaxY = Math.max(ay1, ay2);

  const matched: string[] = [];
  for (const item of textContent.items) {
    if (typeof item.str !== "string") continue;
    const text = item.str.trim();
    if (!text) continue;
    const transform = item.transform;
    if (!Array.isArray(transform) || transform.length < 6) continue;
    // PDF.js text position: transform[4]=x, transform[5]=y (baseline).
    // Bbox: (x, y) to (x+width, y+height). Y goes UP in PDF user space,
    // so the text top is at y+height and the baseline is at y.
    const tx = transform[4]!;
    const ty = transform[5]!;
    const w = item.width ?? 0;
    const h = item.height ?? 0;
    const tMinX = tx;
    const tMaxX = tx + w;
    const tMinY = ty;
    const tMaxY = ty + h;
    // Soft overlap: text bbox intersects the annotation rect in
    // BOTH x and y. Stricter than center-point intersection (which
    // fails for Canva's tight-baseline rects where the text center
    // is ABOVE the link rect's bottom).
    if (tMaxX < rMinX || tMinX > rMaxX) continue;
    if (tMaxY < rMinY || tMinY > rMaxY) continue;
    matched.push(text);
  }

  return matched.join(" ").trim();
}
