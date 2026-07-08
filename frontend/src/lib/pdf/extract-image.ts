// Photo extractor for CV PDFs.
//
// Mirrors `extract_cv_image` in
// `backend/src/jobs_finder/infrastructure/cv/_parser.py`. The
// Python port uses PyMuPDF; this TypeScript port uses
// `unpdf.extractImages` (which wraps pdfjs-dist) so we get
// PyMuPDF-quality image detection without the PyMuPDF native
// dependency. We then re-encode the raw pixel data to a PNG
// byte stream via `pngjs` (already a project dependency for
// the FlateDecode fallback in the old code path).
//
// Strategy:
//   1. Use `unpdf.getDocumentProxy` to get a pdfjs document.
//   2. For each page, call `unpdf.extractImages` — equivalent
//      to PyMuPDF's `page.get_images(full=True)`. Finds ALL
//      images on the page (in Resources / XObject, Form
//      XObjects, patterns, annotations, soft masks, etc.).
//   3. For each image: filter by:
//      - Must NOT be a Form XObject / pattern (key starts with
//        "g_" — pdfjs uses that prefix for patterns and form
//        XObjects, NOT for regular images; this is what was
//        causing the tiled-headshot rendering regression).
//      - Must be at least 100x100 pixels (a real CV headshot;
//        smaller images are icons, logos, or tiling pattern
//        units).
//      - Must be at most 2000x2000 pixels (a real CV headshot;
//        larger images are page backgrounds).
//      - Must be RGB or RGBA (3 or 4 channels; grayscale = SMask).
//      - Pixel data must be at least 4 KB (filter out tiny
//        compressed icons that pass the size check but are
//        actually pixel data, not real photos).
//   4. From all eligible candidates, pick the BEST one:
//      most channels first, then largest by raw data size,
//      then earliest page.
//   5. Re-encode the selected image as a valid PNG byte
//      stream via pngjs. FORCE the alpha channel to 255
//      (opaque) so any SMask-derived transparency doesn't
//      cause the renderer to composite the image weirdly.
//   6. Return as a `data:image/png;base64,<...>` URL.
//
// The function never throws on bad input — it returns `null`
// on any failure (malformed PDF, no images, oversized
// threshold). This matches `extractPdfText`'s contract and
// AGENTS.md rule #24 (no leaking of internal exception
// details).

import "server-only";

import { extractImages, getDocumentProxy } from "unpdf";
import { PNG } from "pngjs";

const MIN_IMAGE_BYTES = 4_000;
// Headshot dimensions. Below 100x100 the image is too small
// to be a real photo (likely a pattern tile unit, an icon, or
// a logo). Above 2000x2000 the image is too large to be a real
// photo (likely a page background or full-bleed decoration).
const MIN_WIDTH = 100;
const MIN_HEIGHT = 100;
const MAX_WIDTH = 2000;
const MAX_HEIGHT = 2000;

type Candidate = {
  pageNum: number;
  width: number;
  height: number;
  channels: 1 | 3 | 4;
  bytes: number;
  data: Uint8ClampedArray;
};

export async function extractCvImage(
  bytes: ArrayBuffer,
): Promise<string | null> {
  let doc: Awaited<ReturnType<typeof getDocumentProxy>>;
  try {
    doc = await getDocumentProxy(new Uint8Array(bytes));
  } catch (err) {
    console.error("pdf/extract-image: unpdf load failed", err);
    return null;
  }

  // Walk each page in order. Collect ALL eligible candidates,
  // then pick the best one.
  const candidates: Candidate[] = [];
  const pageCount = doc.numPages;

  for (let pageNum = 1; pageNum <= pageCount; pageNum++) {
    let images: Awaited<ReturnType<typeof extractImages>>;
    try {
      images = await extractImages(doc, pageNum);
    } catch (err) {
      console.error(
        `pdf/extract-image: extractImages failed for page ${pageNum}`,
        err,
      );
      continue;
    }

    for (const img of images) {
      // The `key` property from unpdf comes from pdfjs's
      // operator list args. Image keys from the page's
      // resource table typically start with "img_"; Form
      // XObjects and patterns start with "g_". The "g_"
      // prefix was the root cause of the tiled-headshot
      // regression — unpdf was returning the tile unit of
      // a pattern, and the renderer drew it as a single
      // image at the photo position, showing the tile
      // pattern instead of the actual photo.
      if (img.key?.startsWith("g_")) {
        console.log(
          `pdf/extract-image: skipping ${img.width}x${img.height} (${img.channels}ch) key=${img.key} — Form XObject / pattern`,
        );
        continue;
      }

      // Filter by reasonable headshot dimensions. Below
      // 100x100 is almost certainly a tile unit, icon, or
      // logo (not a real photo). Above 2000x2000 is a page
      // background or full-bleed decoration.
      if (img.width < MIN_WIDTH || img.height < MIN_HEIGHT) {
        console.log(
          `pdf/extract-image: skipping ${img.width}x${img.height} (${img.channels}ch) — too small (< ${MIN_WIDTH}x${MIN_HEIGHT})`,
        );
        continue;
      }
      if (img.width > MAX_WIDTH || img.height > MAX_HEIGHT) {
        console.log(
          `pdf/extract-image: skipping ${img.width}x${img.height} (${img.channels}ch) — too large (> ${MAX_WIDTH}x${MAX_HEIGHT})`,
        );
        continue;
      }

      // Only accept RGB or RGBA. Grayscale = 1 channel is
      // the SMask (alpha channel) which pdfjs emits as a
      // separate image.
      if (img.channels < 3) {
        console.log(
          `pdf/extract-image: skipping ${img.width}x${img.height} (${img.channels}ch) — grayscale (likely SMask)`,
        );
        continue;
      }

      // Pixel data size threshold.
      const pixelBytes = img.width * img.height * img.channels;
      if (pixelBytes < MIN_IMAGE_BYTES) {
        console.log(
          `pdf/extract-image: skipping ${img.width}x${img.height} (${img.channels}ch) — ${pixelBytes} bytes (< ${MIN_IMAGE_BYTES} threshold)`,
        );
        continue;
      }

      candidates.push({
        pageNum,
        width: img.width,
        height: img.height,
        channels: img.channels,
        bytes: pixelBytes,
        data: img.data,
      });
    }
  }

  if (candidates.length === 0) {
    console.log("pdf/extract-image: no eligible images found");
    return null;
  }

  // Pick the BEST candidate: most channels (favors 4-channel
  // RGBA over 3-channel RGB), then largest by raw data size,
  // then earliest page.
  candidates.sort((a, b) => {
    if (b.channels !== a.channels) return b.channels - a.channels;
    if (b.bytes !== a.bytes) return b.bytes - a.bytes;
    return a.pageNum - b.pageNum;
  });

  const best = candidates[0]!;

  // Re-encode the raw pixel data to a valid PNG byte stream
  // via pngjs. FORCE the alpha channel to 255 (opaque) so
  // any residual transparency from the unpdf decode does
  // not cause the renderer to composite the image with the
  // page background in a way that looks "tiled" or "washed
  // out".
  try {
    const png = new PNG({
      width: best.width,
      height: best.height,
      channels: best.channels,
    });
    png.data = new Uint8Array(best.data);
    // Force alpha to 255 (only if RGBA, channels === 4).
    if (best.channels === 4) {
      for (let i = 3; i < png.data.length; i += 4) {
        png.data[i] = 0xff;
      }
    }
    const pngBytes = PNG.sync.write(png);
    const b64 = Buffer.from(pngBytes).toString("base64");
    console.log(
      `pdf/extract-image: extracted photo from page ${best.pageNum} — ${best.width}x${best.height} (${best.channels}ch) — ${pngBytes.byteLength} bytes (from ${candidates.length} candidate${candidates.length === 1 ? "" : "s"})`,
    );
    return `data:image/png;base64,${b64}`;
  } catch (err) {
    console.error("pdf/extract-image: pngjs re-encode failed", err);
    return null;
  }
}
