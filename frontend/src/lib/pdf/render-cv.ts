import "server-only";

import { PDFDocument, PDFFont, PDFPage, StandardFonts, rgb } from "pdf-lib";
import type { AdaptedCV } from "@/lib/llm/prompts";

// ── Page geometry ───────────────────────────────────────────────────────
//
// A4 (210 × 297 mm) ≈ 595 × 842 points (1 point = 1/72 inch).
// Conservative margins — Harvard/ATS templates use ~15–20 mm.
const PAGE_WIDTH = 595;
const PAGE_HEIGHT = 842;
const MARGIN = 50;
const CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN;

// Photo size matches the Python CSS template (28mm × 32mm ≈ 80pt × 91pt).
// pdf-lib's `drawImage` doesn't crop, so we draw at the natural aspect
// ratio and accept slightly non-square photos.
const PHOTO_WIDTH = 80;
const PHOTO_HEIGHT = 90;

// ── Font selection ──────────────────────────────────────────────────────
//
// The Python template (`_template.py`) uses Arial — an ATS-friendly
// sans-serif. The user's CV reference image targets a SERIF layout
// (classic Harvard look), so the TS renderer uses Times Roman instead.
// All four variants are available in pdf-lib's `StandardFonts`.
const FONT_REG = StandardFonts.TimesRoman;
const FONT_BOLD = StandardFonts.TimesRomanBold;
const FONT_ITALIC = StandardFonts.TimesRomanItalic;
const FONT_BOLD_ITALIC = StandardFonts.TimesRomanBoldItalic;

// ── Font sizes ──────────────────────────────────────────────────────────
//
// Each constant is named for the visual role it plays (NAME, CONTACT,
// BODY, SECTION_TITLE, etc.) so the layout stays readable.
const SIZE_NAME = 18;
const SIZE_CONTACT = 10;
const SIZE_BODY = 10;
const SIZE_BODY_ITALIC = 10;
const SIZE_SECTION_TITLE = 11;
const SIZE_EXP_COMPANY = 10;
const SIZE_EXP_TITLE = 10;
const SIZE_EXP_LOCATION = 9;
const SIZE_EXP_DATE = 9;
const SIZE_EXP_BULLET = 10;
const SIZE_PROJECT_NAME = 10;
const SIZE_PROJECT_DESC = 10;
const SIZE_PROJECT_TECH = 9;
const SIZE_EDU_DEGREE = 10;
const SIZE_EDU_YEAR = 9;
const SIZE_EDU_INSTITUTION = 9;
const SIZE_SKILLS = 10;
const SIZE_LANGUAGES = 10;

const LINE_HEIGHT_RATIO = 1.4;

// Section title block (rectangle + border + text). Slightly larger
// than the text itself so the highlight feels like a "compartment"
// rather than a colored text run.
const SECTION_TITLE_HEIGHT = 16;
const SECTION_TITLE_TEXT_PADDING = 6;
const SECTION_TITLE_BORDER_THICKNESS = 0.4;

// Inter-section vertical gap.
const SECTION_GAP = 4;

// Yellow highlight color (pastel — matches the Harvard reference image,
// approximated as #fff3cd / rgb(255, 242, 205)).
const HIGHLIGHT_COLOR = rgb(1, 0.949, 0.804);

const DIVIDER_COLOR = rgb(0.55, 0.55, 0.55);
const DIVIDER_THICKNESS = 0.4;

// Section titles — Spanish to match the user's CV reference image AND
// the backend Python template (`backend/.../cv/_template.py`), which
// uses the same Spanish titles. The renderer does NOT pick these from
// the LLM (the `AdaptedCV` schema doesn't include section titles);
// they're hardcoded to match the user's language.
const SECTION_TITLES = {
  summary: "Perfil Profesional",
  education: "Educación",
  experience: "Experiencia Profesional",
  projects: "Proyectos",
  certifications: "Certificaciones",
  skills: "Habilidades",
  languages: "Idiomas",
} as const;

// Maximum bullets per experience entry. Caps pathological LLM outputs
// (e.g. a runaway list of 200 short sentences) from blowing out the
// layout — real LLM descriptions are usually 3–7 sentences.
const MAX_BULLETS_PER_ENTRY = 8;

// Minimum bullet length (after trimming). Drops empty strings and
// residual fragments like "." or "ok." that survive the sentence split.
const MIN_BULLET_LENGTH = 5;

// Sanitize text for the built-in PDF fonts (Times Roman family
// uses WinAnsi encoding). The LLM often copies special chars
// verbatim from the original CV — e.g. "⟶" (U+27F6 long arrow)
// in "Ultimate JavaScript — Arturo Alba — 2025-02-09 ⟶ Más
// información." WinAnsi can't encode that char and pdf-lib
// throws WinAnsiError on the drawText call. We map common
// Unicode chars to their WinAnsi-safe equivalents (or strip
// if no equivalent exists). Mappings are exhaustive for the
// chars we see in real CVs; anything outside WinAnsi not in
// the map is dropped silently.
const WIN_ANSI_MAP: Record<string, string> = {
  // Long arrows (U+27F6 etc.) → ASCII equivalents directly
  // (not to the intermediate U+2192, which is also NOT in
  // WinAnsi and would be dropped on the second pass).
  "⟶": "->", // U+27F6 long rightwards arrow
  "⟵": "<-", // U+27F5 long leftwards arrow
  "↔": "<->", // U+2194 left right arrow
  "⇒": "=>", // U+21D2 rightwards double arrow
  "⇐": "<=", // U+21D0 leftwards double arrow
  "→": "->", // U+2192 rightwards arrow (NOT in WinAnsi)
  "←": "<-", // U+2190 leftwards arrow (NOT in WinAnsi)
  "↑": "^", // U+2191 upwards arrow (NOT in WinAnsi)
  "↓": "v", // U+2193 downwards arrow (NOT in WinAnsi)
  // Em dash and en dash
  "—": "-", // U+2014 em dash → hyphen
  "–": "-", // U+2013 en dash → hyphen
  // Curly quotes
  "\u201C": '"', // U+201C left double quotation mark
  "\u201D": '"', // U+201D right double quotation mark
  "\u2018": "'", // U+2018 left single quotation mark
  "\u2019": "'", // U+2019 right single quotation mark
  // Ellipsis, bullet, daggers
  "…": "...", // U+2026 horizontal ellipsis
  "•": "*", // U+2022 bullet → asterisk
  "†": "+", // U+2020 dagger
  "‡": "++", // U+2021 double dagger
  // Common math / misc
  "×": "x", // U+00D7 multiplication sign (in WinAnsi actually)
  "÷": "/", // U+00F7 division sign (in WinAnsi actually)
  "°": "°", // U+00B0 degree sign (in WinAnsi)
  "©": "(c)", // U+00A9 copyright sign
  "®": "(R)", // U+00AE registered sign
  "™": "TM", // U+2122 trademark
  "€": "EUR", // U+20AC euro sign (in WinAnsi actually)
  // Spanish / Catalan letters that are NOT in basic Latin
  "·": ".", // U+00B7 middle dot (in WinAnsi)
  "ª": "a.", // U+00AA feminine ordinal
  "º": "o.", // U+00BA masculine ordinal
  "¡": "!", // U+00A1 inverted exclamation
  "¿": "?", // U+00BF inverted question
};

function sanitizeForWinAnsi(text: string): string {
  // First, map known chars. Then strip anything that's still
  // outside the WinAnsi codepoints (basic Latin + Latin-1
  // supplement + the small set of PDF WinAnsi extensions
  // listed in the PDF spec table D.2).
  let result = "";
  for (const ch of text) {
    const mapped = WIN_ANSI_MAP[ch] ?? ch;
    if (isWinAnsiSafe(mapped)) {
      result += mapped;
    }
    // else: drop the char silently (it would crash pdf-lib).
  }
  return result;
}

function isWinAnsiSafe(ch: string): boolean {
  // Basic Latin (U+0000..U+007F) is always safe.
  // Latin-1 supplement (U+00A0..U+00FF) minus U+00AD is safe.
  // The PDF WinAnsi extension set (per spec table D.2):
  //   U+0152, U+0153, U+2013, U+2014, U+2018, U+2019,
  //   U+201C, U+201D, U+2022, U+2026, U+2030, U+2039,
  //   U+203A, U+20AC.
  const code = ch.codePointAt(0)!;
  if (code <= 0x7f) return true;
  if (code >= 0xa0 && code <= 0xff && code !== 0xad) return true;
  return (
    code === 0x152 || // Œ
    code === 0x153 || // œ
    code === 0x2013 || // – en dash
    code === 0x2014 || // — em dash
    code === 0x2018 || // ' left single quote
    code === 0x2019 || // ' right single quote
    code === 0x201c || // " left double quote
    code === 0x201d || // " right double quote
    code === 0x2022 || // • bullet
    code === 0x2026 || // … ellipsis
    code === 0x2030 || // ‰ per mille
    code === 0x2039 || // ‹ single guillemet
    code === 0x203a || // › single guillemet
    code === 0x20ac    // € euro
  );
}

// ── Drawing state ───────────────────────────────────────────────────────

interface DrawState {
  doc: PDFDocument;
  page: PDFPage;
  font: PDFFont;
  bold: PDFFont;
  italic: PDFFont;
  boldItalic: PDFFont;
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

// ── Section title (yellow highlight + uppercase bold text) ─────────────

function drawSectionTitle(state: DrawState, text: string): void {
  const size = SIZE_SECTION_TITLE;
  ensureSpace(state, SECTION_TITLE_HEIGHT + SECTION_GAP);

  // Background rectangle (full content width).
  const rectBottom = state.y - SECTION_TITLE_HEIGHT;
  state.page.drawRectangle({
    x: MARGIN,
    y: rectBottom,
    width: CONTENT_WIDTH,
    height: SECTION_TITLE_HEIGHT,
    color: HIGHLIGHT_COLOR,
  });

  // Subtle border-bottom line UNDER the highlight.
  state.page.drawLine({
    start: { x: MARGIN, y: rectBottom },
    end: { x: MARGIN + CONTENT_WIDTH, y: rectBottom },
    thickness: SECTION_TITLE_BORDER_THICKNESS,
    color: DIVIDER_COLOR,
  });

  // Title text (uppercase bold) on top of the rectangle.
  // Baseline is positioned at ~ the visual mid-height of the box
  // minus a small offset for optical centering of the cap-height.
  const titleText = text.toUpperCase();
  const baseline = rectBottom + SECTION_TITLE_HEIGHT / 2 - size * 0.23;
  state.page.drawText(titleText, {
    x: MARGIN + SECTION_TITLE_TEXT_PADDING,
    y: baseline,
    font: state.bold,
    size,
    color: rgb(0, 0, 0),
  });

  // Advance past the title block + small gap.
  state.y = rectBottom - SECTION_GAP;
}

// ── Wrapped text (left-aligned or centered) ────────────────────────────

interface DrawTextOptions {
  size?: number;
  font?: PDFFont;
  indent?: number;
  center?: boolean;
}

function drawWrappedText(
  state: DrawState,
  text: string,
  opts: DrawTextOptions = {},
): void {
  const size = opts.size ?? SIZE_BODY;
  const font = opts.font ?? state.font;
  const indent = opts.indent ?? 0;
  const center = opts.center ?? false;

  const trimmed = text.trim();
  if (trimmed.length === 0) return;

  const lines = wrapLine(trimmed, font, size, CONTENT_WIDTH - indent);
  const height = lineHeight(size);
  for (const line of lines) {
    ensureSpace(state, height);
    const x = center
      ? MARGIN + (CONTENT_WIDTH - font.widthOfTextAtSize(line, size)) / 2
      : MARGIN + indent;
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

// ── Bullet line (• character + wrapped, indented text) ────────────────

function drawBullet(
  state: DrawState,
  text: string,
  size: number = SIZE_EXP_BULLET,
): void {
  const font = state.font;
  const bulletChar = "\u2022";
  const indent = 14;
  const bulletX = MARGIN + 2;
  const textX = MARGIN + indent;
  const maxTextWidth = CONTENT_WIDTH - indent;

  const trimmed = text.trim();
  if (trimmed.length === 0) return;

  const lines = wrapLine(trimmed, font, size, maxTextWidth);
  if (lines.length === 0) return;

  const height = lineHeight(size);
  for (let i = 0; i < lines.length; i++) {
    ensureSpace(state, height);
    // The bullet character only appears on the first wrapped line —
    // continuation lines are indented at the text column, not the
    // bullet column.
    if (i === 0) {
      state.page.drawText(bulletChar, {
        x: bulletX,
        y: state.y - size,
        font,
        size,
        color: rgb(0, 0, 0),
      });
    }
    const line = lines[i]!;
    state.page.drawText(line, {
      x: textX,
      y: state.y - size,
      font,
      size,
      color: rgb(0, 0, 0),
    });
    state.y -= height;
  }
}

// ── Two-column row (left text + right text on the same line) ──────────

interface RowSideOpts {
  font?: PDFFont;
  size?: number;
}

function drawRow(
  state: DrawState,
  leftText: string | null,
  rightText: string | null,
  leftOpts: RowSideOpts = {},
  rightOpts: RowSideOpts = {},
): void {
  const leftSize = leftOpts.size ?? SIZE_BODY;
  const rightSize = rightOpts.size ?? SIZE_BODY;
  const leftFont = leftOpts.font ?? state.font;
  const rightFont = rightOpts.font ?? state.font;
  const height = lineHeight(Math.max(leftSize, rightSize));

  ensureSpace(state, height);

  if (leftText && leftText.length > 0) {
    state.page.drawText(leftText, {
      x: MARGIN,
      y: state.y - leftSize,
      font: leftFont,
      size: leftSize,
      color: rgb(0, 0, 0),
    });
  }

  if (rightText && rightText.length > 0) {
    const w = rightFont.widthOfTextAtSize(rightText, rightSize);
    state.page.drawText(rightText, {
      x: MARGIN + CONTENT_WIDTH - w,
      y: state.y - rightSize,
      font: rightFont,
      size: rightSize,
      color: rgb(0, 0, 0),
    });
  }

  state.y -= height;
}

// ── Header horizontal rule (full content width) ───────────────────────

function drawHeaderRule(state: DrawState): void {
  ensureSpace(state, 1);
  state.page.drawLine({
    start: { x: MARGIN, y: state.y },
    end: { x: MARGIN + CONTENT_WIDTH, y: state.y },
    thickness: 0.5,
    color: rgb(0.2, 0.2, 0.2),
  });
}

// ── Per-section content helpers ────────────────────────────────────────

function drawEducationEntry(
  state: DrawState,
  ed: AdaptedCV["education"][number],
): void {
  const degreeText = ed.grade ? `${ed.degree}, ${ed.grade}` : ed.degree;
  drawRow(
    state,
    degreeText || null,
    ed.year || null,
    { font: state.bold, size: SIZE_EDU_DEGREE },
    { font: state.font, size: SIZE_EDU_YEAR },
  );
  if (ed.institution) {
    drawWrappedText(state, ed.institution, {
      size: SIZE_EDU_INSTITUTION,
      font: state.italic,
    });
  }
}

function formatDateRange(start: string, end: string): string {
  const s = (start ?? "").trim();
  const e = (end ?? "").trim();
  if (!s && !e) return "";
  if (!e) return s;
  if (!s) return e;
  // En dash (U+2013) — typographically correct for date ranges.
  // Em dashes are forbidden anywhere in the rendered output (the
  // "no AI writing tells" rule from `ADAPT_CV_SYSTEM_PROMPT`).
  return `${s} \u2013 ${e}`;
}

function drawExperienceEntry(
  state: DrawState,
  exp: AdaptedCV["experience"][number],
): void {
  // Row 1: company (bold, left) + location (italic, smaller, right).
  drawRow(
    state,
    exp.company || null,
    exp.location || null,
    { font: state.bold, size: SIZE_EXP_COMPANY },
    { font: state.italic, size: SIZE_EXP_LOCATION },
  );
  // Row 2: title (italic, left) + date range (smaller, right).
  const dateRange = formatDateRange(exp.start_date, exp.end_date);
  drawRow(
    state,
    exp.title || null,
    dateRange || null,
    { font: state.italic, size: SIZE_EXP_TITLE },
    { font: state.font, size: SIZE_EXP_DATE },
  );
  // Bullets — split the description on sentence boundaries and
  // newlines, drop fragments too short to be a real bullet.
  if (exp.description) {
    const bullets = splitDescriptionIntoBullets(exp.description);
    for (const bullet of bullets) {
      drawBullet(state, bullet, SIZE_EXP_BULLET);
    }
  }
  // Subtle divider line below the entry.
  drawSpacer(state, 2);
  state.page.drawLine({
    start: { x: MARGIN, y: state.y },
    end: { x: MARGIN + CONTENT_WIDTH, y: state.y },
    thickness: DIVIDER_THICKNESS,
    color: DIVIDER_COLOR,
  });
  drawSpacer(state, 4);
}

function splitDescriptionIntoBullets(
  description: string,
  cap: number = MAX_BULLETS_PER_ENTRY,
): string[] {
  // Normalize line endings so \r\n / \r behave the same as \n.
  const normalized = description.replace(/\r\n?/g, "\n").trim();
  if (!normalized) return [];

  const lines = normalized.split(/\n+/);
  const bullets: string[] = [];
  for (const line of lines) {
    // Sentence boundary: period followed by whitespace. The lookbehind
    // keeps the period attached to the previous sentence so it renders
    // with the bullet text instead of starting the next bullet.
    const sentences = line.split(/(?<=\.)\s+/);
    for (const sentence of sentences) {
      // Strip leading markdown bullet markers the LLM copied
      // verbatim from the original CV ("* ", "- ", "• ", "· ").
      // The renderer adds its own bullet character; the LLM
      // shouldn't include one in the text.
      const t = sentence.trim().replace(/^[*\-•·]\s+/, "").trim();
      if (t.length >= MIN_BULLET_LENGTH) bullets.push(t);
    }
  }
  return bullets.slice(0, cap);
}

function drawProjectEntry(
  state: DrawState,
  proj: AdaptedCV["projects"][number],
): void {
  if (proj.name) {
    drawWrappedText(state, proj.name, {
      size: SIZE_PROJECT_NAME,
      font: state.bold,
    });
  }
  if (proj.description) {
    drawWrappedText(state, proj.description, {
      size: SIZE_PROJECT_DESC,
      font: state.font,
    });
  }
  if (proj.technologies && proj.technologies.length > 0) {
    drawWrappedText(
      state,
      `Tecnologías: ${proj.technologies.join(", ")}`,
      { size: SIZE_PROJECT_TECH, font: state.italic },
    );
  }
  drawSpacer(state, 3);
}

// ── Photo decoder (mirrors the route's data-URL contract) ──────────────

async function decodePhotoDataUrl(
  photo: string,
): Promise<{ bytes: Uint8Array; isJpeg: boolean } | null> {
  const match = photo.match(/^data:image\/(png|jpeg|jpg);base64,(.+)$/i);
  if (!match) return null;
  const mime = match[1]!.toLowerCase();
  const b64 = match[2]!;
  const bytes = Uint8Array.from(
    typeof Buffer !== "undefined"
      ? Buffer.from(b64, "base64")
      : Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)),
  );
  return { bytes, isJpeg: mime === "jpeg" || mime === "jpg" };
}

// ── Public entry point ─────────────────────────────────────────────────

/**
 * Render the LLM's `AdaptedCV` as a downloadable PDF (Uint8Array).
 *
 * Layout — Harvard CV template:
 *   - Header: photo (top-right) || centered name (18pt bold) +
 *     contact line (10pt) + horizontal rule.
 *   - Resumen / Perfil Profesional (italic body under a yellow
 *     highlighted uppercase section title).
 *   - One section per content group: Educación, Experiencia
 *     Profesional, Proyectos, Habilidades, Idiomas. Each section
 *     starts with a yellow-highlighted uppercase title bar.
 *   - Experience: company (bold) + location (italic right) →
 *     title (italic) + date range (smaller right) → bullet list
 *     split on sentence boundaries, capped per entry.
 *   - Education: degree (bold) + year (right) → institution (italic).
 *   - Projects: name (bold) → optional description → "Tecnologías:"
 *     line (italic).
 *   - Skills / Languages: comma-separated list.
 *
 * Typography: serif (Times Roman). The Python backend uses Arial for
 * ATS friendliness; this TS renderer targets the user's reference
 * image instead — a classic serif Harvard look.
 *
 * Constraints honored:
 *   - No em dashes emitted anywhere (the "no AI writing tells" rule
 *     from `ADAPT_CV_SYSTEM_PROMPT`).
 *   - No translation: the renderer outputs whatever the LLM emits
 *     for `name`, `email`, `phone`, `location`, `summary`, etc. The
 *     section titles ARE the renderer's choice (the schema doesn't
 *     carry them), and they're hardcoded to Spanish to match the
 *     user's reference + the Python template.
 *   - Photo flow unchanged: `cv.photo` (data URL or null) →
 *     embedded image XObject or no photo.
 */
export async function renderAdaptedCvAsPdf(
  cv: AdaptedCV,
): Promise<Uint8Array<ArrayBuffer>> {
  // Sanitize the cv object for WinAnsi-safe encoding. The LLM
  // often copies special characters verbatim from the original
  // CV (e.g. "⟶" in "Ultimate JavaScript ⟶ Más información",
  // em dashes, curly quotes, ellipsis, etc.) and the built-in
  // PDF fonts (Times Roman family) use WinAnsi encoding which
  // can't represent those chars — pdf-lib throws WinAnsiError
  // on drawText. We walk the cv object and sanitize every
  // string field once, before any drawing happens.
  const sanitized: AdaptedCV = {
    name: sanitizeForWinAnsi(cv.name),
    email: sanitizeForWinAnsi(cv.email),
    phone: sanitizeForWinAnsi(cv.phone),
    location: sanitizeForWinAnsi(cv.location),
    summary: sanitizeForWinAnsi(cv.summary),
    experience: cv.experience.map((e) => ({
      company: sanitizeForWinAnsi(e.company),
      title: sanitizeForWinAnsi(e.title),
      start_date: sanitizeForWinAnsi(e.start_date),
      end_date: sanitizeForWinAnsi(e.end_date),
      description: sanitizeForWinAnsi(e.description),
      location: e.location ? sanitizeForWinAnsi(e.location) : null,
    })),
    education: cv.education.map((e) => ({
      degree: sanitizeForWinAnsi(e.degree),
      institution: sanitizeForWinAnsi(e.institution),
      year: sanitizeForWinAnsi(e.year),
      grade: e.grade ? sanitizeForWinAnsi(e.grade) : null,
    })),
    projects: cv.projects.map((p) => ({
      name: sanitizeForWinAnsi(p.name),
      description: sanitizeForWinAnsi(p.description),
      technologies: p.technologies.map(sanitizeForWinAnsi),
    })),
    certifications: cv.certifications.map(sanitizeForWinAnsi),
    skills: cv.skills.map(sanitizeForWinAnsi),
    languages: cv.languages.map(sanitizeForWinAnsi),
    photo: cv.photo, // base64 data URL — no sanitization needed
  };

  const doc = await PDFDocument.create();
  const font = await doc.embedFont(FONT_REG);
  const bold = await doc.embedFont(FONT_BOLD);
  const italic = await doc.embedFont(FONT_ITALIC);
  const boldItalic = await doc.embedFont(FONT_BOLD_ITALIC);

  const state: DrawState = {
    doc,
    page: doc.addPage([PAGE_WIDTH, PAGE_HEIGHT]),
    font,
    bold,
    italic,
    boldItalic,
    y: PAGE_HEIGHT - MARGIN,
  };

  // Photo header — drawn FIRST so the text doesn't overlap it.
  // We size the photo by its natural aspect ratio (clamped to the
  // PHOTO_WIDTH × PHOTO_HEIGHT bounding box) so a portrait photo
  // doesn't get stretched horizontally. The previous code used
  // fixed PHOTO_WIDTH × PHOTO_HEIGHT which stretched any photo
  // whose aspect ratio didn't match 80:90 (e.g. the user's
  // 577×845 portrait photo).
  let hasPhoto = false;
  let photoWidth = PHOTO_WIDTH;
  let photoHeight = PHOTO_HEIGHT;
  if (sanitized.photo) {
    const decoded = await decodePhotoDataUrl(sanitized.photo).catch(() => null);
    if (decoded) {
      try {
        const embedded = decoded.isJpeg
          ? await doc.embedJpg(decoded.bytes)
          : await doc.embedPng(decoded.bytes);
        // Fit the embedded image's natural dimensions into the
        // PHOTO_WIDTH × PHOTO_HEIGHT box while preserving the
        // aspect ratio. The intrinsic dimensions come from
        // pdf-lib after decoding the PNG/JPEG.
        const intr = embedded.size();
        if (intr.width > 0 && intr.height > 0) {
          const scale = Math.min(
            PHOTO_WIDTH / intr.width,
            PHOTO_HEIGHT / intr.height,
          );
          photoWidth = Math.round(intr.width * scale);
          photoHeight = Math.round(intr.height * scale);
        }
        const photoX = PAGE_WIDTH - MARGIN - photoWidth;
        const photoY = PAGE_HEIGHT - MARGIN - photoHeight;
        state.page.drawImage(embedded, {
          x: photoX,
          y: photoY,
          width: photoWidth,
          height: photoHeight,
        });
        hasPhoto = true;
      } catch (err) {
        // Embedder can throw on invalid image bytes — log + skip
        // (better than crashing the whole render).
        console.error("pdf/render-cv: photo embed failed", err);
      }
    }
  }

  // Header text — centered when no photo, else left-aligned (the
  // photo occupies the right ~80pt of the page).
  if (sanitized.name) {
    drawWrappedText(state, sanitized.name, {
      size: SIZE_NAME,
      font: state.bold,
      center: !hasPhoto,
    });
  }
  const contactParts: string[] = [];
  if (sanitized.location) contactParts.push(sanitized.location);
  if (sanitized.email) contactParts.push(sanitized.email);
  if (sanitized.phone) contactParts.push(sanitized.phone);
  if (contactParts.length > 0) {
    drawWrappedText(state, contactParts.join(" | "), {
      size: SIZE_CONTACT,
      center: !hasPhoto,
    });
  }

  // Horizontal rule under the header (separates header from body).
  drawSpacer(state, 5);
  drawHeaderRule(state);
  drawSpacer(state, 6);

  // Resumen / Perfil Profesional — italic body under yellow section title.
  if (sanitized.summary) {
    drawSectionTitle(state, SECTION_TITLES.summary);
    drawWrappedText(state, sanitized.summary, {
      size: SIZE_BODY_ITALIC,
      font: state.italic,
    });
    drawSpacer(state, SECTION_GAP);
  }

  // Educación (Harvard order: before Experience).
  if (sanitized.education && sanitized.education.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.education);
    for (const ed of sanitized.education) {
      drawEducationEntry(state, ed);
      drawSpacer(state, 2);
    }
    drawSpacer(state, SECTION_GAP);
  }

  // Experiencia Profesional.
  if (sanitized.experience && sanitized.experience.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.experience);
    for (const exp of sanitized.experience) {
      drawExperienceEntry(state, exp);
    }
    drawSpacer(state, SECTION_GAP);
  }

  // Proyectos (personal projects, volunteer work, standalone
  // experience items from the original CV that look like projects).
  if (sanitized.projects && sanitized.projects.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.projects);
    for (const proj of sanitized.projects) {
      drawProjectEntry(state, proj);
    }
    drawSpacer(state, SECTION_GAP);
  }

  // Certificaciones (items from a 'Certificaciones' / 'Licencias'
  // / 'Certifications' section in the original CV — licenses,
  // courses, and training programs).
  if (sanitized.certifications && sanitized.certifications.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.certifications);
    // Bullet list — each cert gets its own line. Splitting a
    // comma-joined string would lose the issuer / date suffix
    // that lives in the verbatim name (e.g. '... | NTT DATA /
    // Oracle Training', '... - 2025-02-09').
    for (const cert of sanitized.certifications) {
      drawBullet(state, cert);
    }
    drawSpacer(state, SECTION_GAP);
  }

  // Habilidades.
  if (sanitized.skills && sanitized.skills.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.skills);
    drawWrappedText(state, sanitized.skills.join(", "), { size: SIZE_SKILLS });
    drawSpacer(state, SECTION_GAP);
  }

  // Idiomas.
  if (sanitized.languages && sanitized.languages.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.languages);
    drawWrappedText(state, sanitized.languages.join(", "), { size: SIZE_LANGUAGES });
  }

  const bytes = await doc.save();
  // `pdf-lib`'s `doc.save()` returns `Uint8Array<ArrayBufferLike>` under
  // TS 5.9 (the generic is widened because `ArrayBufferLike` covers
  // `SharedArrayBuffer` too). The bytes always live on a plain
  // `ArrayBuffer` in practice — copy them into a fresh `ArrayBuffer`-
  // backed `Uint8Array` so the strict `BlobPart` type is satisfied.
  const out = new Uint8Array(bytes.byteLength);
  out.set(bytes);
  return out;
}
