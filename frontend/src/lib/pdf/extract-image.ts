// Photo extractor for CV PDFs.
//
// THREE-PHASE STRATEGY:
//
//   Phase 1 — Full-resolution image extraction (unpdf `extractImages`)
//     Walks the page's operator list looking for `paintImageXObject`
//     ops and resolves each named image via `page.objs` / `page.commonObjs`.
//     Returns the RAW pixel data at FULL RESOLUTION (100-300+ DPI),
//     which gives much better quality than cropping from the rendered
//     page. This handles the common case where the CV embeds a regular
//     image XObject (no tiling pattern).
//
//   Phase 2 — CTM tracking via operator list + rendered-page crop
//     Walks the operator list tracking the CTM (current transformation
//     matrix) through save/restore/transform ops to find each image's
//     POSITION on the page. Renders the page at 2x scale and crops the
//     image at the position found. This is a fallback when Phase 1's
//     full-resolution data is unavailable (the image position is still
//     useful for cropping).
//
//   Phase 3 — Grid-based colorfulness scan (handles tiling patterns)
//     When the photo lives inside a TILING PATTERN that pdfjs does NOT
//     expand into the page's operator list, neither Phase 1 nor Phase 2
//     will find it. Phase 3 renders the page and scans overlapping
//     windows (multiple sizes) in the top portion, scoring each by
//     colorfulness. The most colorful region is returned as the photo.
//     This handles the user's CV (2x2 grid of headshots via pattern).
//
// The function never throws on bad input — it returns `null` on any
// failure (malformed PDF, no canvas, render error, empty page). This
// matches `extractPdfText`'s contract and AGENTS.md rule #24 (no
// leaking of internal exception details).

import "server-only";

import { getDocumentProxy, renderPageAsImage, extractImages } from "unpdf";
import { PNG } from "pngjs";

// ── Dynamic import for @napi-rs/canvas ──────────────────────────────────
//
// CRITICAL: the import MUST be lazy (dynamic) — a static
// `import * as canvas from "@napi-rs/canvas"` at module top-level
// forces Next.js webpack to bundle the canvas native binding
// (skia.linux-x64-gnu.node) into the CLIENT bundle, which throws
// "Module parse failed: Unexpected character" at build time.
// A dynamic `await import(...)` is only resolved at runtime, so
// webpack skips it. The `server-only` import above prevents the
// module from executing in the browser, so the dynamic import is
// only hit in the Node.js server runtime.

// ── Types ───────────────────────────────────────────────────────────────

interface CropCandidate {
  /** X offset (pixels) on the rendered page. */
  left: number;
  /** Y offset (pixels) — 0 = top of page. */
  top: number;
  /** Width in pixels. */
  width: number;
  /** Height in pixels. */
  height: number;
  /** Human-readable label for logging. */
  label: string;
}

// ── Raw-image encoder (Phase 1) ─────────────────────────────────────────

/**
 * Encode raw RGBA / RGB pixel data as a base64 PNG data URL.
 *
 * Accepts 3-channel (RGB) or 4-channel (RGBA) pixel data. 1-channel
 * (grayscale) data is also handled — the PNG is written as a full
 * RGB image.
 */
function rawToPngDataUrl(
  data: Uint8ClampedArray | Uint8Array,
  width: number,
  height: number,
): string {
  const png = new PNG({ width, height });
  const srcChannels = data.byteLength / (width * height);

  for (let i = 0; i < width * height; i++) {
    const si = i * srcChannels;
    const di = i * 4;
    if (srcChannels === 4) {
      png.data[di] = data[si]!;
      png.data[di + 1] = data[si + 1]!;
      png.data[di + 2] = data[si + 2]!;
      png.data[di + 3] = data[si + 3]!;
    } else if (srcChannels === 3) {
      png.data[di] = data[si]!;
      png.data[di + 1] = data[si + 1]!;
      png.data[di + 2] = data[si + 2]!;
      png.data[di + 3] = 0xff;
    } else {
      // 1-channel grayscale — repeat as RGB
      png.data[di] = data[si]!;
      png.data[di + 1] = data[si]!;
      png.data[di + 2] = data[si]!;
      png.data[di + 3] = 0xff;
    }
  }

  const pngBytes = PNG.sync.write(png);
  const b64 = Buffer.from(pngBytes).toString("base64");
  return `data:image/png;base64,${b64}`;
}

/**
 * Minimum image dimension (in pixels) to consider as a potential
 * photo. Images smaller than this are likely icons, logos, or
 * decorative elements. At 72 DPI, 50 px ≈ 0.7 inches.
 *
 * Note: this is in image-pixel space (the natural resolution of
 * the embedded image), not PDF user-space units.
 */
const MIN_PHOTO_PX = 50;

// ── Grid fallback (Phase 3) ────────────────────────────────────────────

/**
 * Generate candidate crop regions covering the top 75 % of the page
 * using MULTIPLE window sizes (small, medium, large) in a sliding-
 * window pattern with heavy overlap.
 *
 * Window sizes:
 *   - Small: 20 %W × 15 %H — for small passport-style photos
 *   - Medium: 35 %W × 20 %H — for typical CV photo regions
 *   - Large: 50 %W × 30 %H — for header-wide photo backgrounds
 *
 * The multiple sizes ensure that at least one window captures the
 * photo regardless of its size on the page.
 *
 * Covers the top 75 % of the page (extended from previous 65 %).
 */
function generateGridCandidates(pageW: number, pageH: number): CropCandidate[] {
  const candidates: CropCandidate[] = [];
  let idx = 0;
  const maxY = Math.floor(pageH * 0.75);

  // Multi-size configuration: [winW_ratio, winH_ratio, strideX_ratio, strideY_ratio]
  const sizes: Array<[number, number, number, number]> = [
    [0.20, 0.15, 0.10, 0.08],  // small
    [0.35, 0.20, 0.15, 0.10],  // medium
    [0.50, 0.30, 0.25, 0.15],  // large
  ];

  for (const [wRatio, hRatio, sXRatio, sYRatio] of sizes) {
    const winW = Math.max(40, Math.floor(pageW * wRatio));
    const winH = Math.max(40, Math.floor(pageH * hRatio));
    const strideX = Math.max(1, Math.floor(pageW * sXRatio));
    const strideY = Math.max(1, Math.floor(pageH * sYRatio));

    for (let top = 0; top + winH <= maxY; top += strideY) {
      for (let left = 0; left + winW <= pageW; left += strideX) {
        candidates.push({
          left,
          top,
          width: winW,
          height: winH,
          label: `gs-${idx++}`,
        });
      }
    }
  }
  return candidates;
}

// ── Colorfulness scoring ────────────────────────────────────────────────

/**
 * Score a crop region by its "colorfulness" — the sum of absolute
 * differences between RGB channels per pixel, averaged over the
 * region.
 *
 * Why this works:
 *   - A photo (skin, hair, clothing, background) has significant
 *     differences between R, G, and B channels at most pixels →
 *     high score (typically 30–100+).
 *   - Text on white is mostly gray/black/white pixels where
 *     R ≈ G ≈ B → low score (typically 3–8).
 *   - Blank / white areas have R≈G≈B≈255 → score ≈ 0.
 *
 * The scoring is O(n) in the number of pixels in the region and
 * uses only integer arithmetic — fast enough to run on 50–80
 * candidate regions per request.
 */
function scoreColorfulness(
  pageData: Buffer,
  pageW: number,
  region: CropCandidate,
): number {
  let totalDiff = 0;
  let count = 0;

  for (let y = region.top; y < region.top + region.height; y++) {
    const rowOffset = y * pageW;
    for (let x = region.left; x < region.left + region.width; x++) {
      const idx = (rowOffset + x) * 4;
      const r = pageData[idx]!;
      const g = pageData[idx + 1]!;
      const b = pageData[idx + 2]!;
      totalDiff += Math.abs(r - g) + Math.abs(g - b) + Math.abs(b - r);
      count++;
    }
  }

  return count > 0 ? totalDiff / count : 0;
}

/**
 * Minimum colorfulness score to consider a region as containing a
 * photo. Below this threshold the region is mostly blank or just
 * text — we return null instead of a useless crop.
 *
 * Lowered from 8 to 5 to handle grayscale / low-contrast photos
 * (passport photos with white backgrounds).
 */
const MIN_COLORFULNESS_SCORE = 5;

// ── Crop + encode helper ────────────────────────────────────────────────

/**
 * Extract a rectangular region from the rendered page and encode it
 * as a base64 PNG data URL.
 */
function cropAndEncode(
  pageData: Buffer,
  pageW: number,
  region: CropCandidate,
): string {
  const cropped = new PNG({ width: region.width, height: region.height });

  for (let y = 0; y < region.height; y++) {
    const srcRow = (region.top + y) * pageW;
    for (let x = 0; x < region.width; x++) {
      const srcIdx = (srcRow + region.left + x) * 4;
      const dstIdx = (y * region.width + x) * 4;
      cropped.data[dstIdx] = pageData[srcIdx]!;
      cropped.data[dstIdx + 1] = pageData[srcIdx + 1]!;
      cropped.data[dstIdx + 2] = pageData[srcIdx + 2]!;
      cropped.data[dstIdx + 3] = 0xff; // force opaque
    }
  }

  const pngBytes = PNG.sync.write(cropped);
  const b64 = Buffer.from(pngBytes).toString("base64");
  console.log(
    `pdf/extract-image: cropped ${region.label} (${region.width}x${region.height}) ` +
      `at (${region.left}, ${region.top}) — ${pngBytes.byteLength} bytes`,
  );
  return `data:image/png;base64,${b64}`;
}

// ── Public entry point ──────────────────────────────────────────────────

export async function extractCvImage(
  bytes: ArrayBuffer,
): Promise<string | null> {
  // Lazy-load @napi-rs/canvas — see the top-level comment.
  const canvasPromise = (async () => {
    const mod = await import("@napi-rs/canvas");
    return mod;
  })();

  // ── 1. Load the PDF via unpdf ─────────────────────────────────
  let doc: Awaited<ReturnType<typeof getDocumentProxy>>;
  try {
    doc = await getDocumentProxy(new Uint8Array(bytes));
  } catch (err) {
    console.error("pdf/extract-image: unpdf load failed", err);
    return null;
  }

  // ═══════════════════════════════════════════════════════════════
  // Phase 1 — Full-resolution image extraction via `extractImages`
  // ═══════════════════════════════════════════════════════════════
  //
  // unpdf's `extractImages` walks the operator list, resolves each
  // `paintImageXObject` via `page.objs` / `page.commonObjs`, and
  // returns the RAW pixel data at the image's natural resolution.
  // This gives the BEST quality — we pick the largest image and
  // encode it directly as a PNG data URL.
  //
  // This phase does NOT handle tiling patterns (page 2), but it is
  // the preferred path for normal embedded images.
  try {
    const images = await extractImages(doc, 1);
    let bestImg: (typeof images)[number] | null = null;
    for (const img of images) {
      if (img.width >= MIN_PHOTO_PX && img.height >= MIN_PHOTO_PX) {
        if (!bestImg || img.width * img.height > bestImg.width * bestImg.height) {
          bestImg = img;
        }
      }
    }
    if (bestImg) {
      const dataUrl = rawToPngDataUrl(bestImg.data, bestImg.width, bestImg.height);
      console.log(
        `pdf/extract-image: Phase-1 full-res image "${bestImg.key}" ` +
          `${bestImg.width}×${bestImg.height} (${bestImg.data.byteLength} bytes)`,
      );
      return dataUrl;
    }
  } catch (err) {
    // extractImages can throw on some PDFs (e.g. structuredClone
    // issues with pdfjs worker). Log and fall through.
    console.error("pdf/extract-image: Phase-1 extractImages failed", err);
  }

  // ═══════════════════════════════════════════════════════════════
  // Phase 2 — Rendered page crop at operator-list image position
  // ═══════════════════════════════════════════════════════════════
  //
  // When Phase 1 fails (no images found or extraction error), we
  // render the page and crop at the position where the operator list
  // paints an image XObject. The operator list tracks the CTM to
  // position each image on the page.
  //
  // This phase also does NOT handle tiling patterns (the operator
  // list does not expand them), but it handles the common case
  // where Phase 1 succeeded in finding an image but we need the
  // position to crop from the rendered page.

  // ── 2a. Get page 1 and its viewport ──────────────────────
  let page: Awaited<ReturnType<typeof doc.getPage>>;
  try {
    page = await doc.getPage(1);
  } catch (err) {
    console.error("pdf/extract-image: getPage(1) failed", err);
    return null;
  }

  const pdfViewport = page.getViewport({ scale: 1 });
  const pdfW = pdfViewport.width;
  const pdfH = pdfViewport.height;

  // ── 2b. Walk operator list for largest image position ─────
  let imageBox: { x: number; y: number; w: number; h: number } | null = null;
  try {
    const { getResolvedPDFJS } = await import("unpdf");
    const pdfjs = await getResolvedPDFJS();
    const OPS: Record<string, number> = pdfjs.OPS;
    const opList = await page.getOperatorList();

    let ctm = [1, 0, 0, 1, 0, 0];
    const stack: number[][] = [];

    for (let i = 0; i < opList.fnArray.length; i++) {
      const op = opList.fnArray[i]!;
      const args: number[] = opList.argsArray[i] ?? [];

      if (op === OPS.save) {
        stack.push([...ctm]);
      } else if (op === OPS.restore) {
        const saved = stack.pop();
        if (saved) ctm = saved;
      } else if (op === OPS.transform) {
        ctm = mulCTM(ctm, [
          args[0]!, args[1]!, args[2]!, args[3]!, args[4]!, args[5]!,
        ]);
      } else if (op === OPS.paintImageXObject) {
        const box = ctmToBox(ctm);
        if (box.w >= MIN_PHOTO_PX && box.h >= MIN_PHOTO_PX) {
          if (!imageBox || box.w * box.h > imageBox.w * imageBox.h) {
            imageBox = box;
          }
        }
      }
    }
  } catch (err) {
    console.error("pdf/extract-image: Phase-2 operator-list walk failed", err);
    // Fall through to Phase 3
  }

  // ── 2c. Render the first page at 2x scale ────────────────
  let pagePngBytes: ArrayBuffer;
  try {
    pagePngBytes = await renderPageAsImage(doc, 1, {
      scale: 2,
      canvasImport: async () => {
        const canvas = await canvasPromise;
        return canvas;
      },
    });
  } catch (err) {
    console.error("pdf/extract-image: renderPageAsImage failed", err);
    return null;
  }

  // ── 2d. Decode the rendered page PNG ─────────────────────
  let decoded: ReturnType<typeof PNG.sync.read>;
  try {
    decoded = PNG.sync.read(Buffer.from(pagePngBytes));
  } catch (err) {
    console.error("pdf/extract-image: PNG decode of rendered page failed", err);
    return null;
  }

  const { width: pngW, height: pngH, data: pageData } = decoded;
  const renderScale = pngW / pdfW; // Should be ~2

  // ── 2e. If we found an image position, crop at that position ─
  if (imageBox) {
    const region: CropCandidate = {
      left: Math.floor(imageBox.x * renderScale),
      top: Math.floor((pdfH - imageBox.y - imageBox.h) * renderScale),
      width: Math.max(50, Math.ceil(imageBox.w * renderScale)),
      height: Math.max(50, Math.ceil(imageBox.h * renderScale)),
      label: "image-xobject",
    };

    if (
      region.left >= 0 &&
      region.top >= 0 &&
      region.left + region.width <= pngW &&
      region.top + region.height <= pngH
    ) {
      console.log(
        `pdf/extract-image: Phase-2 cropping at ` +
          `(${region.left}, ${region.top}) ${region.width}×${region.height}`,
      );
      return cropAndEncode(pageData, pngW, region);
    }

    console.warn(
      `pdf/extract-image: Phase-2 image box out of bounds ` +
        `(${region.left}, ${region.top}, ${region.width}×${region.height} ` +
        `in ${pngW}×${pngH}), falling to grid`,
    );
  }

  // ═══════════════════════════════════════════════════════════════
  // Phase 3 — Grid-based colorfulness scan (handles tiling patterns)
  // ═══════════════════════════════════════════════════════════════
  //
  // When the photo lives inside a tiling pattern (2×2 grid of
  // headshots), neither Phase 1 nor Phase 2 will detect it because
  // pdfjs does NOT expand patterns into the page's operator list.
  //
  // Phase 3 scans the rendered page with overlapping windows at
  // MULTIPLE sizes (small, medium, large) across the top 75 % of
  // the page, scoring each window by colorfulness. The most
  // colorful region is cropped and returned.

  console.log("pdf/extract-image: Phase-3 grid fallback started");
  const candidates = generateGridCandidates(pngW, pngH);

  let bestRegion: CropCandidate | null = null;
  let bestScore = -1;

  for (const candidate of candidates) {
    if (
      candidate.left + candidate.width > pngW ||
      candidate.top + candidate.height > pngH
    ) {
      continue;
    }
    const score = scoreColorfulness(pageData, pngW, candidate);
    if (score > bestScore) {
      bestScore = score;
      bestRegion = candidate;
    }
  }

  if (bestRegion && bestScore >= MIN_COLORFULNESS_SCORE) {
    console.log(
      `pdf/extract-image: Phase-3 selected "${bestRegion.label}" ` +
        `(score ${bestScore.toFixed(1)}, ${bestRegion.width}×${bestRegion.height} @ ` +
        `${bestRegion.left},${bestRegion.top}) — page ${pngW}×${pngH}`,
    );
    return cropAndEncode(pageData, pngW, bestRegion);
  }

  console.log(
    `pdf/extract-image: no photo detected (best score ${bestScore.toFixed(1)}, ` +
      `threshold ${MIN_COLORFULNESS_SCORE})`,
  );
  return null;
}

// ── Standalone CTM helpers (no longer exported, kept for the
//    operator-list walk in Phase 2) ──────────────────────────────

/**
 * Multiply two PDF CTM matrices: result = m1 × m2.
 */
function mulCTM(m1: number[], m2: number[]): number[] {
  return [
    m1[0] * m2[0] + m1[1] * m2[2],
    m1[0] * m2[1] + m1[1] * m2[3],
    m1[2] * m2[0] + m1[3] * m2[2],
    m1[2] * m2[1] + m1[3] * m2[3],
    m1[4] * m2[0] + m1[5] * m2[2] + m2[4],
    m1[4] * m2[1] + m1[5] * m2[3] + m2[5],
  ];
}

/**
 * Compute the axis-aligned bounding box of a unit square [0,0]…[1,1]
 * transformed through a PDF CTM.
 */
function ctmToBox(ctm: number[]): { x: number; y: number; w: number; h: number } {
  const [a, b, c, d, e, f] = ctm;
  const xs = [e, e + a, e + c, e + a + c];
  const ys = [f, f + b, f + d, f + b + d];
  return {
    x: Math.min(...xs),
    y: Math.min(...ys),
    w: Math.max(...xs) - Math.min(...xs),
    h: Math.max(...ys) - Math.min(...ys),
  };
}
