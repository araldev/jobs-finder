// Photo extractor for CV PDFs.
//
// Strategy: render the FIRST page of the PDF as a canvas image
// and crop the top portion. This is the most reliable approach
// for the user's specific case where the original PDF has the
// photo as a tiling pattern (the unpdf per-image route keeps
// returning the tile unit, which when drawn shows a "tiled
// headshot" pattern in the adapted CV).
//
// The page-render approach bypasses the per-image complexity:
// the first page already contains the photo in its correct
// position, and cropping the top-right region captures the
// photo as the user sees it in the original CV — without any
// tiling artifacts.
//
// We use `unpdf.renderPageAsImage` (which uses canvas under
// the hood) to render the first page at 2x scale. The cropped
// region is then re-encoded as a PNG data URL.
//
// The function never throws on bad input — it returns `null`
// on any failure (malformed PDF, no canvas, render error).
// This matches `extractPdfText`'s contract and AGENTS.md
// rule #24 (no leaking of internal exception details).

import "server-only";

import { getDocumentProxy, renderPageAsImage } from "unpdf";
import { PNG } from "pngjs";
// @napi-rs/canvas provides a real Canvas implementation for
// Node.js (the runtime we run in for the Next.js server).
// unpdf requires the caller to pass the canvas module as a
// `canvasImport` option in Node — it does NOT auto-resolve the
// optional `canvas` / `@napi-rs/canvas` peer dependency.
//
// CRITICAL: the import MUST be lazy (dynamic) — a static
// `import * as canvas from "@napi-rs/canvas"` at module
// top-level forces Next.js webpack to bundle the canvas
// native binding (skia.linux-x64-gnu.node) into the CLIENT
// bundle, which throws "Module parse failed: Unexpected
// character" at build time. A dynamic `await import(...)` is
// only resolved at runtime, so webpack skips it. The
// `server-only` import above prevents the module from
// executing in the browser, so the dynamic import is only
// hit in the Node.js server runtime.

const CROP_TOP_FRACTION = 0.18; // top 18% of the page (typical header area)
const CROP_WIDTH_FRACTION = 0.30; // right 30% of the page (typical photo width)
const MIN_HEADSHOT_SIDE = 100; // px — minimum cropped region dimension

export async function extractCvImage(
  bytes: ArrayBuffer,
): Promise<string | null> {
  // Lazy-load @napi-rs/canvas — see the top-of-file comment.
  // A static import would break the client bundle (webpack
  // would try to bundle the canvas native binding).
  const canvasPromise = (async () => {
    const mod = await import("@napi-rs/canvas");
    return mod;
  })();

  let doc: Awaited<ReturnType<typeof getDocumentProxy>>;
  try {
    doc = await getDocumentProxy(new Uint8Array(bytes));
  } catch (err) {
    console.error("pdf/extract-image: unpdf load failed", err);
    return null;
  }

  // Render the first page at 2x scale (so the headshot crop
  // is high-resolution). unpdf's renderPageAsImage returns an
  // ArrayBuffer of PNG bytes. The page is rendered as a
  // single image with the photo in its correct position —
  // we just crop the top-right region.
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

  // Decode the rendered page PNG so we can crop it.
  let decoded: ReturnType<typeof PNG.sync.read>;
  try {
    decoded = PNG.sync.read(Buffer.from(pagePngBytes));
  } catch (err) {
    console.error("pdf/extract-image: PNG decode of rendered page failed", err);
    return null;
  }

  const { width: pageW, height: pageH, data: pageData } = decoded;

  // Crop the top-right region of the page (where CV headshots
  // typically live). For a typical A4 portrait CV rendered at
  // 2x (~1190x1684 px), the crop is the top 18% × right 30%
  // of the page (~215 px tall, ~357 px wide). The crop
  // dimensions scale proportionally for non-A4 pages.
  const cropHeight = Math.max(
    MIN_HEADSHOT_SIDE,
    Math.floor(pageH * CROP_TOP_FRACTION),
  );
  // Use a portrait-ish aspect ratio for the cropped headshot
  // (4:5, similar to a typical CV headshot).
  const cropWidth = Math.max(
    MIN_HEADSHOT_SIDE,
    Math.floor(cropHeight * 0.8),
  );
  // Anchor the crop to the top-right corner with a small
  // margin from the right edge.
  const cropRightMargin = Math.floor(pageW * 0.02);
  const cropLeft = Math.max(0, pageW - cropWidth - cropRightMargin);
  const cropTop = 0;

  if (cropLeft + cropWidth > pageW || cropHeight > pageH) {
    console.error(
      `pdf/extract-image: crop bounds out of range (page ${pageW}x${pageH}, crop ${cropWidth}x${cropHeight} at (${cropLeft}, ${cropTop}))`,
    );
    return null;
  }

  // Extract the crop region from the page pixels.
  const cropped = new PNG({ width: cropWidth, height: cropHeight });
  for (let y = 0; y < cropHeight; y++) {
    for (let x = 0; x < cropWidth; x++) {
      const srcIdx = ((cropTop + y) * pageW + (cropLeft + x)) * 4;
      const dstIdx = (y * cropWidth + x) * 4;
      cropped.data[dstIdx] = pageData[srcIdx]!;
      cropped.data[dstIdx + 1] = pageData[srcIdx + 1]!;
      cropped.data[dstIdx + 2] = pageData[srcIdx + 2]!;
      cropped.data[dstIdx + 3] = 0xff; // force opaque
    }
  }

  const croppedPngBytes = PNG.sync.write(cropped);
  const b64 = Buffer.from(croppedPngBytes).toString("base64");
  console.log(
    `pdf/extract-image: rendered page 1 (${pageW}x${pageH}) and cropped headshot (${cropWidth}x${cropHeight}) at (${cropLeft}, ${cropTop}) — ${croppedPngBytes.byteLength} bytes`,
  );
  return `data:image/png;base64,${b64}`;
}
