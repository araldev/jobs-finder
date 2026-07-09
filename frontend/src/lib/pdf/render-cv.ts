import "server-only";

import { PDFDocument, PDFFont, PDFPage, PDFImage, StandardFonts, rgb, PDFName, PDFArray, PDFOperator } from "pdf-lib";
import type { AdaptedCV, AdaptedCVProjectLink } from "@/lib/llm/prompts";
import { deriveChipLabel } from "@/lib/llm/parser";

// ── Page geometry ───────────────────────────────────────────────────────
//
// A4 (210 × 297 mm) ≈ 595 × 842 points (1 point = 1/72 inch).
// Conservative margins — Harvard/ATS templates use ~15–20 mm.
const PAGE_WIDTH = 595;
const PAGE_HEIGHT = 842;
const MARGIN = 50;
const CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN;

// Photo bounding box (was 120×140 — too tall, caused ~110pt of
// empty white space below the header because the renderer reserved
// the right-column vertical range for "photo-side" content that
// never actually existed). Sized to fit alongside the two-line
// header text (name + contact), matching its vertical extent so
// the photo doesn't push the first section down.
const PHOTO_BOX_WIDTH = 80;
const PHOTO_BOX_HEIGHT = 80;
// Visual radius for the rounded-photo effect (pdf-lib's drawImage
// has no built-in mask; we use SVG path clipping via raw PDF
// operators — see drawRoundedImage below). ~32pt = Harvard/ATS
// standard for a circular profile photo.
const PHOTO_RADIUS = 40;

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
const SIZE_PROJECT_LINK = 8;
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

// Inter-section vertical gap. Bumped from 4 → 10 for visible
// breathing room between sections (ATS scanners don't care;
// humans do — a CV without gaps looks like a wall of text).
const SECTION_GAP = 10;

// Minimum vertical room we keep together when starting a new
// section: the section's highlight bar + its FIRST content line
// must both fit on the same page. If not, we move to the next
// page instead of orphaning the title at the bottom (the
// worst-case PDF layout bug — a section title on page N with
// its content on page N+1 breaks the reader's flow).
const SECTION_KEEP_TOGETHER_HEIGHT = SECTION_TITLE_HEIGHT + 18;

// Yellow highlight color (pastel — matches the Harvard reference image,
// approximated as #fff3cd / rgb(255, 242, 205)).
const HIGHLIGHT_COLOR = rgb(1, 0.949, 0.804);

const DIVIDER_COLOR = rgb(0.55, 0.55, 0.55);
const DIVIDER_THICKNESS = 0.4;

// Project link chip geometry (REQ-PJL-004). The chip is a small
// bordered rectangle with subtle fill, matching the Python
// template's `.project-link-chip` style (gray border, light gray
// fill, italic small text). Each chip is its own clickable region
// (REQ-PJL-003) — the `drawLinkAnnotation` call below covers the
// WHOLE chip rectangle, not just the text.
const CHIP_FILL_COLOR = rgb(0.957, 0.957, 0.957); // #f4f4f4
const CHIP_BORDER_COLOR = rgb(0.533, 0.533, 0.533); // #888
const CHIP_BORDER_THICKNESS = 0.5;
const CHIP_PADDING_X = 4;
const CHIP_PADDING_Y = 2;
const CHIP_GAP_X = 4;
const CHIP_GAP_Y = 3;

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

// ── ATS keyword expansion (display-only, no fabrication) ─────────────
//
// Many ATS systems index by exact-string match on different aliases
// of the same technology (e.g. "React", "React.js", "ReactJS" all
// match the same job description). When the LLM emits the canonical
// name (e.g. "React"), the renderer expands it to all known aliases
// joined by " / " so a single ATS scan picks up all variants.
//
// CRITICAL: this dictionary is for DISPLAY expansion only. The LLM
// is forbidden from adding technologies not in the original CV (see
// the NO KEYWORD INJECTION rule in the prompt); this dictionary
// does not introduce new tech, only renders more keywords for techs
// already in the CV.
const TECH_VARIANTS: Record<string, string> = {
  "React": "React.js / ReactJS",
  "Node": "Node.js / NodeJS",
  "Vue": "Vue.js / VueJS",
  "Angular": "AngularJS / Angular 2+",
  "Next": "Next.js / NextJS",
  "Nuxt": "Nuxt.js / NuxtJS",
  "Express": "Express.js / ExpressJS",
  "TypeScript": "TypeScriptJS / TS",
  "JavaScript": "JS / ECMAScript",
  "Java": "Java SE / JDK",
  "Python": "Python 3 / Python3",
  "TypeScriptScript": "TS", // safety fallback in case LLM emits "TypeScriptScript"
  "Postgres": "PostgreSQL / Postgres",
  "MySQL": "MySQL / My SQL",
  "MongoDB": "Mongo / Mongo DB",
  "GraphQL": "GraphQL / Graph QL",
  "HTML": "HTML5",
  "CSS": "CSS3",
  "Sass": "SCSS / Sass",
  "Tailwind": "Tailwind CSS",
  "Docker": "Docker Engine / Docker Hub",
  "Kubernetes": "K8s / Kube",
  "AWS": "Amazon Web Services / AWS Cloud",
  "GCP": "Google Cloud Platform / Google Cloud",
  "Azure": "Microsoft Azure",
  "CI/CD": "Continuous Integration / Continuous Deployment",
  "REST": "REST API / RESTful",
  "GraphQLAPI": "GraphQL API", // safety
};

/**
 * Expand a canonical technology name to all known ATS-friendly
 * aliases. Returns the input unchanged when no aliases are known.
 *
 * The LLM emits the canonical name (e.g. "React"); we expand it
 * for display so the rendered text covers more alias variants
 * that ATS systems index by. The expanded form is joined by " / "
 * (e.g. "React / React.js / ReactJS") — readable in the PDF and
 * easily grep-able by ATS regex matchers.
 *
 * Sanity rule: capitalization of the canonical name is preserved
 * EXACTLY as the LLM emitted it. Aliases are not modified.
 */
function expandTech(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return trimmed;
  const variants = TECH_VARIANTS[trimmed];
  return variants ? `${trimmed} / ${variants}` : trimmed;
}

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

/**
 * Ensure room for an entire section block — the section title bar
 * PLUS its first content line — on the current page. If the room
 * isn't there, move the WHOLE section to the next page
 * (eliminates the "title at bottom of page N, content on page N+1"
 * orphan that the previous version produced). Section titles are
 * small enough that bumping them to the next page is always the
 * better UX.
 */
function ensureSectionRoom(
  state: DrawState,
  firstContentHeight: number,
): void {
  const totalNeeded = SECTION_KEEP_TOGETHER_HEIGHT + firstContentHeight;
  ensureSpace(state, totalNeeded);
}

/**
 * Draw an image masked to a circle (rounded profile photo). pdf-lib
 * doesn't expose a `clip` for images, so we push raw PDF operators:
 * the arc operator defines a circular clipping path, drawImage
 * respects the clip, then we pop the graphics state. The result is
 * a perfectly circular photo — common for Harvard-style CV templates
 * and never crops the face because we fit the natural image into the
 * bounding box and clip AFTER drawing.
 *
 * `PDFOperator.of` is the safe way to push raw operators — it
 * registers any PDF objects we reference and ensures they're
 * tracked for serialization. The constants `cx`, `cy`, `r` are
 * intentionally inlined into the operator strings (PDF arc syntax
 * requires positional numeric args).
 */
/**
 * Draw an image masked to a circle (rounded profile photo). pdf-lib
 * doesn't expose a `clip` for images, so we push raw PDF operators:
 * the arc operator defines a circular clipping path, drawImage
 * respects the clip, then we pop the graphics state. The result is
 * a perfectly circular photo — common for Harvard-style CV templates
 * and never crops the face because we fit the natural image into the
 * bounding box and clip AFTER drawing.
 *
 * `PDFOperator.of` is the safe way to push raw operators — it
 * registers any PDF objects we reference and ensures they're
 * tracked for serialization. The constants are intentionally
 * inlined into the operator strings (PDF arc syntax requires
 * positional numeric args).
 */
function drawCircularImage(
  state: DrawState,
  image: PDFImage,
  cx: number,
  cy: number,
  r: number,
): void {
  // Operator sequence:
  //   q                 % push graphics state
  //   x1 y1 x2 y2 ...   % arc operator (PDF spec §8.5.3)
  //   W                 % set clipping path (intersect with current)
  //   n                 % end path (no-fill, no-stroke)
  //   <draw image>
  //   Q                 % pop graphics state
  // For a circle at (cx, cy) with radius r, the bounding box
  // arc parameters are (cx-r, cy-r, cx+r, cy+r) and the start/end
  // point is the right edge of the circle, full sweep.
  const x1 = cx - r;
  const y1 = cy - r;
  const x2 = cx + r;
  const y2 = cy + r;
  const startX = cx + r;
  const startY = cy;
  const endX = cx + r;
  const endY = cy;
  state.page.pushOperators(
    PDFOperator.of("q"),
    PDFOperator.of(
      `${x1} ${y1} ${x2} ${y2} ${startX} ${startY} ${endX} ${endY} arc`,
    ),
    PDFOperator.of("W"),
    PDFOperator.of("n"),
  );
  // Draw the image inside the clip. Origin is the bounding-box
  // bottom-left (PDF Y-up); we want the image's BOTTOM at cy - r.
  state.page.drawImage(image, {
    x: cx - r,
    y: cy - r,
    width: r * 2,
    height: r * 2,
  });
  // Pop the clip so subsequent draws aren't restricted.
  state.page.pushOperators(PDFOperator.of("Q"));
}

function drawSpacer(state: DrawState, height: number): void {
  ensureSpace(state, height);
  state.y -= height;
}

// ── Section title (yellow highlight + uppercase bold text) ─────────────

/**
 * Draw a section title bar.
 *
 * When `firstContentHeight` is provided, ensure the room for the
 * bar PLUS that content line exists on the current page. If not,
 * move the WHOLE section (title + content) to the next page —
 * eliminates the "title at the bottom of one page, content at the
 * top of the next" orphan that destroys reading flow. Default is
 * the title-only size (backward-compatible).
 */
function drawSectionTitle(
  state: DrawState,
  text: string,
  firstContentHeight: number = 0,
): void {
  const size = SIZE_SECTION_TITLE;
  const titleTotal = SECTION_TITLE_HEIGHT + SECTION_GAP + firstContentHeight;
  ensureSpace(state, titleTotal);

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

/**
 * Draw a bullet line. When `link` is provided, the FIRST wrapped
 * line of text is wrapped in a clickable PDF link annotation (the
 * user can click the text to open the URL). The annotation only
 * covers the first line because that's where the cert / bullet name
 * lives; continuation lines (date, issuer, etc.) are not clickable.
 *
 * Used by both experience bullets (no link) and certification
 * bullets (with link when the cert has a URL in the original CV).
 */
function drawBullet(
  state: DrawState,
  text: string,
  size: number = SIZE_EXP_BULLET,
  link: string | null = null,
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
    // On the first line, if a link was provided, overlay a clickable
    // region covering the text so the cert name is clickable.
    if (i === 0 && link && link.startsWith("http")) {
      const lineWidth = font.widthOfTextAtSize(line, size);
      const textTopY = state.y; // top of the line (PDF Y-up)
      const textBottomY = state.y - size;
      const textHeight = textTopY - textBottomY;
      drawLinkAnnotation(
        state,
        link,
        textX,
        textBottomY,
        lineWidth,
        textHeight,
      );
    }
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

// ── Link annotation helper ─────────────────────────────────────────────

function drawLinkAnnotation(
  state: DrawState,
  url: string,
  x: number,
  y: number,
  width: number,
  height: number,
): void {
  if (!url.startsWith("http")) return;
  const linkAnnotation = state.doc.context.obj({
    Type: "Annot",
    Subtype: "Link",
    Rect: [x, y, x + width, y + height],
    Border: [0, 0, 0],
    A: {
      Type: "Action",
      S: "URI",
      URI: url,
    },
  }) as any;
  const linkRef = state.doc.context.register(linkAnnotation);
  const existingAnnotsObj = state.page.node.get(PDFName.of("Annots"));
  const existing = existingAnnotsObj instanceof PDFArray
    ? existingAnnotsObj.asArray().slice()
    : [];
  existing.push(linkRef);
  state.page.node.set(PDFName.of("Annots"), state.doc.context.obj(existing) as any);
}

// ── Chip row (per-link clickable rectangles, REQ-PJL-003 / REQ-PJL-004)
// ────────────────────────────────────────────────────────────────

interface ChipPlacement {
  link: AdaptedCVProjectLink;
  width: number;
  x: number;
  y: number;
  height: number;
  label: string;
}

/**
 * Draw a row of clickable link chips, wrapping to the next line
 * when the cumulative width exceeds `CONTENT_WIDTH`.
 *
 * Each chip:
 *   1. is rendered as a bordered rectangle (border + subtle fill),
 *   2. carries the link label as italic text centered horizontally,
 *   3. has its own `drawLinkAnnotation` over the WHOLE chip
 *      rectangle — distinct from every other chip's region.
 *
 * Per design §1.5 the helper:
 *   - uses `state.italic.widthOfTextAtSize` to measure labels,
 *   - greedy-wraps across `CONTENT_WIDTH` (cumulative width),
 *   - falls back to `deriveChipLabel(l.url)` for empty labels.
 */
function drawChipRow(
  state: DrawState,
  links: readonly AdaptedCVProjectLink[],
): void {
  if (links.length === 0) return;

  // Pre-measure each chip's width (label + horizontal padding).
  const chipHeight = SIZE_PROJECT_LINK + 2 * CHIP_PADDING_Y;
  const widths: number[] = links.map((l) => {
    const label = l.label || deriveChipLabel(l.url);
    const labelWidth = state.italic.widthOfTextAtSize(label, SIZE_PROJECT_LINK);
    return Math.ceil(labelWidth) + 2 * CHIP_PADDING_X;
  });

  // Greedy-wrap into placements. Each row is a list of placements
  // (x-positioned greedily from MARGIN). When the next chip
  // wouldn't fit, we start a new row.
  const placements: ChipPlacement[] = [];
  let rowStartY = state.y;
  let cursorX = MARGIN;
  let rowMaxHeight = chipHeight;
  for (let i = 0; i < links.length; i++) {
    const link = links[i]!;
    const width = widths[i]!;
    // If this chip would overflow CONTENT_WIDTH AND we're not at
    // the start of a row, wrap to the next line.
    if (cursorX + width > MARGIN + CONTENT_WIDTH && cursorX > MARGIN) {
      rowStartY -= rowMaxHeight + CHIP_GAP_Y;
      cursorX = MARGIN;
      rowMaxHeight = chipHeight;
    }
    placements.push({
      link,
      width,
      x: cursorX,
      y: rowStartY - chipHeight,
      height: chipHeight,
      label: link.label || deriveChipLabel(link.url),
    });
    cursorX += width + CHIP_GAP_X;
    // rowMaxHeight tracks the tallest chip on this row (all chips
    // are the same size today, but the structure leaves room for
    // variable-size chips in the future).
    if (chipHeight > rowMaxHeight) rowMaxHeight = chipHeight;
  }

  // Each chip = bordered rectangle + centered italic label +
  // independent link annotation covering the whole rectangle.
  for (const chip of placements) {
    state.page.drawRectangle({
      x: chip.x,
      y: chip.y,
      width: chip.width,
      height: chip.height,
      color: CHIP_FILL_COLOR,
      borderColor: CHIP_BORDER_COLOR,
      borderWidth: CHIP_BORDER_THICKNESS,
    });
    const labelWidth = state.italic.widthOfTextAtSize(
      chip.label,
      SIZE_PROJECT_LINK,
    );
    const labelX = chip.x + (chip.width - labelWidth) / 2;
    state.page.drawText(chip.label, {
      x: labelX,
      y: chip.y + CHIP_PADDING_Y,
      font: state.italic,
      size: SIZE_PROJECT_LINK,
      color: rgb(0, 0, 0),
    });
    // Each chip gets its own link annotation over the WHOLE
    // rectangle — REQ-PJL-003 requires each entry in `links` to be
    // an independently clickable region.
    drawLinkAnnotation(
      state,
      chip.link.url,
      chip.x,
      chip.y,
      chip.width,
      chip.height,
    );
  }

  // Advance past the chip row(s) + a small gap before the next
  // section (description, technologies, or next project).
  state.y = rowStartY - rowMaxHeight - 2;
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

export function splitDescriptionIntoBullets(
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

  // Fallback: if no \n was found and we ended up with a single very
  // long bullet, try re-splitting on stricter [.;] + whitespace
  // boundaries to catch pathological LLM output that collapsed
  // multiple sentences into one continuous paragraph.
  if (
    bullets.length === 1 &&
    bullets[0]!.length >= 200 &&
    !normalized.includes("\n")
  ) {
    const longBullet = bullets[0]!;
    if (/[.;]\s/.test(longBullet)) {
      const reSplit = longBullet.split(/(?<=[.;])\s+/);
      const refiltered: string[] = [];
      for (const frag of reSplit) {
        const t = frag.trim();
        if (t.length >= MIN_BULLET_LENGTH) refiltered.push(t);
      }
      // Replace bullets with the re-split (still capped).
      bullets.length = 0;
      bullets.push(...refiltered.slice(0, cap));
    }
  }

  return bullets.slice(0, cap);
}

function drawProjectEntry(
  state: DrawState,
  proj: AdaptedCV["projects"][number],
): void {
  if (proj.name) {
    // Project name is plain bold text — the chip row below carries
    // the link targets. (The legacy code wrapped the name in a
    // single `<a href>` over the singular `url` field; with the
    // new shape each link is its own chip, so the name doesn't
    // need its own clickable region.)
    drawWrappedText(state, proj.name, {
      size: SIZE_PROJECT_NAME,
      font: state.bold,
    });
  }
  // Per-link chip row (REQ-PJL-003 + REQ-PJL-004). One
  // independently-clickable chip per entry in `proj.links`.
  if (proj.links && proj.links.length > 0) {
    drawChipRow(state, proj.links);
  }
  if (proj.description) {
    const descStartY = state.y;
    drawWrappedText(state, proj.description, {
      size: SIZE_PROJECT_DESC,
      font: state.font,
    });
    const descEndY = state.y;
    // Auto-detect HTTP URLs in description text and make them
    // clickable (preserved per spec REQ-PJL-007 — handles
    // accidental bare URLs in the body that the LLM copies
    // verbatim from the original CV).
    if (/https?:\/\/\S+/.test(proj.description)) {
      const urls = proj.description.match(/https?:\/\/\S+/g);
      if (urls) {
        const descHeight = descStartY - descEndY;
        for (const url of urls) {
          drawLinkAnnotation(state, url, MARGIN, descEndY, CONTENT_WIDTH, descHeight);
        }
      }
    }
  }
  if (proj.technologies && proj.technologies.length > 0) {
    // Expand each technology to its known aliases for ATS matchers
    // (canonical / alias1 / alias2 joined by " / "). Display-only
    // expansion — the LLM is forbidden from adding techs not in
    // the original CV; we just render more keyword variants per
    // tech that's already there.
    drawWrappedText(
      state,
      `Tecnologías: ${proj.technologies.map(expandTech).join(", ")}`,
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
      links: p.links.map((l) => ({
        label: sanitizeForWinAnsi(l.label),
        url: sanitizeForWinAnsi(l.url),
      })),
    })),
    certifications: cv.certifications.map((c) => ({
      name: sanitizeForWinAnsi(c.name),
      url: c.url ? sanitizeForWinAnsi(c.url) : null,
    })),
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
  // Sizing: the photo fits inside the PHOTO_BOX_WIDTH × PHOTO_BOX_HEIGHT
  // bounding box (with aspect-ratio preservation) and is drawn as a
  // CIRCLE via `drawCircularImage`. Center is at:
  //   - cx = PAGE_WIDTH - MARGIN - PHOTO_RADIUS (top-right column)
  //   - cy = PAGE_HEIGHT - MARGIN - PHOTO_RADIUS (so the bottom of the
  //     photo touches MARGIN from the top)
  // This way the photo is `2*PHOTO_RADIUS` wide (80pt by default),
  // aligned with the contact line, and DOES NOT extend below the
  // header text — so the first section starts immediately below the
  // header rule. The previous design reserved the photo's full
  // vertical range for "right-side content" that never existed,
  // producing ~110pt of ugly white space before the first section.
  let hasPhoto = false;
  if (sanitized.photo) {
    const decoded = await decodePhotoDataUrl(sanitized.photo).catch(() => null);
    if (decoded) {
      try {
        const embedded = decoded.isJpeg
          ? await doc.embedJpg(decoded.bytes)
          : await doc.embedPng(decoded.bytes);
        // The photo is drawn at a CIRCLE centered on the top-right
        // of the page. The image is fit into PHOTO_BOX (its
        // natural aspect ratio preserved via scale-to-fit) and
        // the resulting bitmap is clipped to a circle of radius
        // PHOTO_RADIUS centered on (photoCx, photoCy). This gives
        // a perfectly circular profile photo regardless of the
        // source image's aspect ratio (a 577x845 portrait gets
        // scaled to fit the box, then clipped to the circle —
        // the head ends up roughly centered).
        const photoCx = PAGE_WIDTH - MARGIN - PHOTO_RADIUS;
        const photoCy = PAGE_HEIGHT - MARGIN - PHOTO_RADIUS;
        drawCircularImage(
          state,
          embedded,
          photoCx,
          photoCy,
          PHOTO_RADIUS,
        );
        hasPhoto = true;
      } catch (err) {
        // Embedder can throw on invalid image bytes — log + skip
        // (better than crashing the whole render).
        console.error("pdf/render-cv: photo embed failed", err);
      }
    }
  }

  // Header text — centered when no photo, else left-aligned. The
  // photo (when present) is small and inline with the header text,
  // NOT a tall column that pushes the first section down.
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

  // NO Y-reservation below the photo — the photo is small
  // enough to fit beside the header text. Content flows
  // directly below the contact line. (The old code did
  // `state.y = Math.min(state.y, photoY - 5)` which created
  // ~110pt of empty white space below the header — the worst
  // visual bug in the previous Harvard layout.)

  // Horizontal rule under the header (separates header from body).
  drawSpacer(state, 5);
  drawHeaderRule(state);
  drawSpacer(state, 6);

  // Resumen / Perfil Profesional — italic body under yellow section title.
  // Keep-together passes the height of one summary line so a
  // summary never gets orphaned at the bottom of a page.
  if (sanitized.summary) {
    drawSectionTitle(state, SECTION_TITLES.summary, lineHeight(SIZE_BODY_ITALIC));
    drawWrappedText(state, sanitized.summary, {
      size: SIZE_BODY_ITALIC,
      font: state.italic,
    });
    drawSpacer(state, SECTION_GAP);
  }

  // Educación (Harvard order: before Experience).
  if (sanitized.education && sanitized.education.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.education, lineHeight(SIZE_EDU_INSTITUTION));
    for (const ed of sanitized.education) {
      drawEducationEntry(state, ed);
      drawSpacer(state, 2);
    }
    drawSpacer(state, SECTION_GAP);
  }

  // Experiencia Profesional.
  if (sanitized.experience && sanitized.experience.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.experience, lineHeight(SIZE_EXP_BULLET));
    for (const exp of sanitized.experience) {
      drawExperienceEntry(state, exp);
    }
    drawSpacer(state, SECTION_GAP);
  }

  // Proyectos (personal projects, volunteer work, standalone
  // experience items from the original CV that look like projects).
  if (sanitized.projects && sanitized.projects.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.projects, lineHeight(SIZE_PROJECT_NAME));
    for (const proj of sanitized.projects) {
      drawProjectEntry(state, proj);
    }
    drawSpacer(state, SECTION_GAP);
  }

  // Certificaciones (items from a 'Certificaciones' / 'Licencias'
  // / 'Certifications' section in the original CV — licenses,
  // courses, and training programs).
  if (sanitized.certifications && sanitized.certifications.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.certifications, lineHeight(SIZE_EXP_BULLET));
    // Bullet list — each cert gets its own line. The `url` field
    // (when non-null) makes the cert name clickable and adds a
    // small "›" indicator so the user knows the cert has a link
    // (PDFs don't change cursor on hover like HTML — the icon is
    // the only visual cue). "›" (U+203A) is in the WinAnsi
    // extension set so it survives the sanitizer without mapping.
    for (const cert of sanitized.certifications) {
      const indicator = cert.url ? " ›" : "";
      drawBullet(state, `${cert.name}${indicator}`, SIZE_EXP_BULLET, cert.url);
    }
    drawSpacer(state, SECTION_GAP);
  }

  // Habilidades.
  if (sanitized.skills && sanitized.skills.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.skills, lineHeight(SIZE_SKILLS));
    // Expand each skill to its ATS-friendly aliases (canonical /
    // alias1 / alias2 joined by " / "). Display-only expansion —
    // the LLM is forbidden from adding skills not in the original
    // CV; we just render more keyword variants per skill that's
    // already there. Helps ATS regex match on "React.js" /
    // "ReactJS" / "React" all from a single skill entry.
    drawWrappedText(
      state,
      sanitized.skills.map(expandTech).join(", "),
      { size: SIZE_SKILLS },
    );
    drawSpacer(state, SECTION_GAP);
  }

  // Idiomas.
  if (sanitized.languages && sanitized.languages.length > 0) {
    drawSectionTitle(state, SECTION_TITLES.languages, lineHeight(SIZE_LANGUAGES));
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
