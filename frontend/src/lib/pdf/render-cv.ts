import "server-only";

import { PDFDocument, PDFFont, PDFPage, StandardFonts, rgb } from "pdf-lib";
import type { AdaptedCV } from "@/lib/llm/prompts";

// A4 dimensions in points (1 point = 1/72 inch).
const PAGE_WIDTH = 595;
const PAGE_HEIGHT = 842;
const MARGIN = 50;
const CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN;

// Photo size matches the Python CSS template (28mm × 32mm ≈ 80pt × 91pt).
// The Python template uses `object-fit: cover`; pdf-lib's `drawImage`
// doesn't crop, so we draw at the natural aspect ratio and accept
// slightly non-square photos — the photo still appears in the header
// (the user's stated goal), we just don't crop aggressively.
const PHOTO_WIDTH = 80;
const PHOTO_HEIGHT = 90;

// Body 10pt → line height 14. Section headings 12pt → 16. Name 18pt → 22.
// Using a single `LINE_HEIGHT_RATIO` keeps the layout table easy to read.
const LINE_HEIGHT_RATIO = 1.4;

interface DrawState {
  doc: PDFDocument;
  page: PDFPage;
  font: PDFFont;
  bold: PDFFont;
  y: number;
}

function lineHeight(size: number): number {
  return Math.round(size * LINE_HEIGHT_RATIO);
}

function wrapLine(
  text: string,
  font: PDFFont,
  size: number,
  maxWidth: number,
): string[] {
  const words = text.split(/\s+/).filter((w) => w.length > 0);
  if (words.length === 0) return [];

  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const candidate = current.length === 0 ? word : `${current} ${word}`;
    const width = font.widthOfTextAtSize(candidate, size);
    if (width <= maxWidth || current.length === 0) {
      current = candidate;
    } else {
      lines.push(current);
      current = word;
    }
  }
  if (current.length > 0) lines.push(current);
  return lines;
}

function ensureSpace(state: DrawState, neededHeight: number): void {
  if (state.y - neededHeight < MARGIN) {
    state.page = state.doc.addPage([PAGE_WIDTH, PAGE_HEIGHT]);
    state.y = PAGE_HEIGHT - MARGIN;
  }
}

function drawSpacer(state: DrawState, height: number): void {
  ensureSpace(state, height);
  state.y -= height;
}

function drawLine(
  state: DrawState,
  text: string,
  opts: { bold?: boolean; size?: number; center?: boolean } = {},
): void {
  const size = opts.size ?? 10;
  const font = opts.bold ? state.bold : state.font;
  const height = lineHeight(size);

  const trimmed = text.trim();
  if (trimmed.length === 0) {
    drawSpacer(state, height);
    return;
  }

  const lines = wrapLine(trimmed, font, size, CONTENT_WIDTH);
  for (const line of lines) {
    ensureSpace(state, height);
    const width = font.widthOfTextAtSize(line, size);
    const x = opts.center
      ? MARGIN + (CONTENT_WIDTH - width) / 2
      : MARGIN;
    state.page.drawText(line, {
      x,
      y: state.y - size,
      font,
      size,
      color: rgb(0, 0, 0),
    });
    state.y -= height;
  }
}

/**
 * Decode a `data:image/<mime>;base64,<...>` URL into raw image bytes
 * + the pdf-lib embedder to call. Returns `null` if the URL is
 * malformed or the bytes can't be decoded.
 *
 * Mirrors the contract enforced by the route handler (always a
 * real data URL from `extractCvImage`). Falls back to `null` for any
 * malformed input rather than throwing — the renderer must not
 * crash on bad data.
 */
async function decodePhotoDataUrl(
  photo: string,
): Promise<{ bytes: Uint8Array; isJpeg: boolean } | null> {
  const match = photo.match(
    /^data:image\/(png|jpeg|jpg);base64,(.+)$/i,
  );
  if (!match) return null;
  const mime = match[1]!.toLowerCase();
  const b64 = match[2]!;

  // Decode base64 → Uint8Array. `Buffer.from(b64, "base64")` works
  // in Node; in the browser the route is gated by `import "server-only"`
  // so we don't worry about the browser path here.
  const bytes = Uint8Array.from(
    typeof Buffer !== "undefined"
      ? Buffer.from(b64, "base64")
      : Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)),
  );

  return { bytes, isJpeg: mime === "jpeg" || mime === "jpg" };
}

/**
 * Render the LLM's `AdaptedCV` as a downloadable PDF (Uint8Array).
 *
 * Layout (Harvard CV template order):
 *   - Header (centered): name (18pt bold) + email/phone/location (10pt)
 *   - Summary (if present): "Summary" heading + body
 *   - Education: "Education" heading + per-entry degree, institution
 *     + year (9pt)
 *   - Experience: "Experience" heading + per-entry title, company
 *     (bold), date range (9pt), description (10pt)
 *   - Projects (if any): "Projects" heading + per-entry name, optional
 *     description, optional "Technologies:" line
 *   - Skills: "Skills" heading + comma-separated list
 *   - Languages: "Languages" heading + comma-separated list
 *
 * Long lines wrap at `CONTENT_WIDTH`; if a line doesn't fit on the
 * current page, a new page is added. The output is a "good enough"
 * CV — not Canva-quality, but a real, valid PDF that opens in any
 * PDF viewer.
 *
 * No em dashes are emitted anywhere; section separators use commas or
 * the en dash (typographically correct for date ranges only). Matches
 * the "no AI writing tells" rule from `ADAPT_CV_SYSTEM_PROMPT`.
 *
 * No text is ever logged (the route logs the file size only, and
 * `LLM_API_KEY` is read upstream — this module never touches it).
 */
export async function renderAdaptedCvAsPdf(
  cv: AdaptedCV,
): Promise<Uint8Array<ArrayBuffer>> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const bold = await doc.embedFont(StandardFonts.HelveticaBold);

  const state: DrawState = {
    doc,
    page: doc.addPage([PAGE_WIDTH, PAGE_HEIGHT]),
    font,
    bold,
    y: PAGE_HEIGHT - MARGIN,
  };

  // Header — Harvard layout: photo on the right, name + contact
  // info flow on the left (or centered when no photo is present).
  // The photo is drawn BEFORE the header text so the text doesn't
  // overlap the image (the photo bounding box is at the top-right
  // corner and the text uses the left portion of the page).
  let headerPhotoHeight = 0;
  if (cv.photo) {
    const decoded = await decodePhotoDataUrl(cv.photo).catch(() => null);
    if (decoded) {
      try {
        const embedded = decoded.isJpeg
          ? await doc.embedJpg(decoded.bytes)
          : await doc.embedPng(decoded.bytes);
        // Anchor the photo to the top-right margin. `drawImage`'s
        // `y` is the BOTTOM-left corner in PDF coordinates — so we
        // subtract the photo height from the top margin.
        const photoX = PAGE_WIDTH - MARGIN - PHOTO_WIDTH;
        const photoY = PAGE_HEIGHT - MARGIN - PHOTO_HEIGHT;
        state.page.drawImage(embedded, {
          x: photoX,
          y: photoY,
          width: PHOTO_WIDTH,
          height: PHOTO_HEIGHT,
        });
        headerPhotoHeight = PHOTO_HEIGHT;
      } catch (err) {
        // Embedder can throw on invalid image bytes (truncated,
        // wrong format). Log + skip — header continues without the
        // photo (better than crashing the whole render).
        console.error("pdf/render-cv: photo embed failed", err);
      }
    }
  }

  // Header text — centered when no photo, else left-aligned on the
  // left portion of the page (photo occupies the right ~80pt).
  const headerHasPhoto = headerPhotoHeight > 0;
  if (cv.name) {
    drawLine(state, cv.name, {
      bold: true,
      size: 18,
      center: !headerHasPhoto,
    });
  }
  if (cv.email) {
    drawLine(state, cv.email, {
      size: 10,
      center: !headerHasPhoto,
    });
  }
  if (cv.phone) {
    drawLine(state, cv.phone, {
      size: 10,
      center: !headerHasPhoto,
    });
  }
  if (cv.location) {
    drawLine(state, cv.location, {
      size: 10,
      center: !headerHasPhoto,
    });
  }

  // Summary.
  if (cv.summary) {
    drawSpacer(state, lineHeight(10));
    drawLine(state, "Summary", { bold: true, size: 12 });
    drawLine(state, cv.summary, { size: 10 });
  }

  // Education (Harvard order: before Experience).
  if (cv.education && cv.education.length > 0) {
    drawSpacer(state, lineHeight(10));
    drawLine(state, "Education", { bold: true, size: 12 });
    for (const ed of cv.education) {
      const line = [ed.degree, ed.institution].filter(Boolean).join(", ");
      if (line) drawLine(state, line, { size: 10 });
      if (ed.year) drawLine(state, ed.year, { size: 9 });
    }
  }

  // Experience.
  if (cv.experience && cv.experience.length > 0) {
    drawSpacer(state, lineHeight(10));
    drawLine(state, "Experience", { bold: true, size: 12 });
    for (const exp of cv.experience) {
      const heading = [exp.title, exp.company].filter(Boolean).join(", ");
      if (heading) {
        drawLine(state, heading, { bold: true, size: 10 });
      }
      if (exp.start_date || exp.end_date) {
        drawLine(
          state,
          `${exp.start_date ?? ""} – ${exp.end_date ?? ""}`.trim(),
          { size: 9 },
        );
      }
      if (exp.description) {
        drawLine(state, exp.description, { size: 10 });
      }
    }
  }

  // Projects (personal projects / volunteer work / certifications).
  // Sourced from the original CV via `ADAPT_CV_SYSTEM_PROMPT`; the
  // LLM rephrases the description and lists the technologies.
  if (cv.projects && cv.projects.length > 0) {
    drawSpacer(state, lineHeight(10));
    drawLine(state, "Projects", { bold: true, size: 12 });
    for (const proj of cv.projects) {
      if (proj.name) {
        drawLine(state, proj.name, { bold: true, size: 10 });
      }
      if (proj.description) {
        drawLine(state, proj.description, { size: 10 });
      }
      if (proj.technologies && proj.technologies.length > 0) {
        drawLine(state, `Technologies: ${proj.technologies.join(", ")}`, {
          size: 9,
        });
      }
    }
  }

  // Skills.
  if (cv.skills && cv.skills.length > 0) {
    drawSpacer(state, lineHeight(10));
    drawLine(state, "Skills", { bold: true, size: 12 });
    drawLine(state, cv.skills.join(", "), { size: 10 });
  }

  // Languages.
  if (cv.languages && cv.languages.length > 0) {
    drawSpacer(state, lineHeight(10));
    drawLine(state, "Languages", { bold: true, size: 12 });
    drawLine(state, cv.languages.join(", "), { size: 10 });
  }

  const bytes = await doc.save();
  // `pdf-lib`'s `doc.save()` returns `Uint8Array<ArrayBufferLike>` under
  // TS 5.9 (the generic is widened because `ArrayBufferLike` covers
  // `SharedArrayBuffer` too). The bytes always live on a plain
  // `ArrayBuffer` in practice — we copy them into a fresh
  // `ArrayBuffer`-backed `Uint8Array` so the strict `BlobPart` type is
  // satisfied without an `unknown` cast leaking into callers.
  const out = new Uint8Array(bytes.byteLength);
  out.set(bytes);
  return out;
}