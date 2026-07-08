// Photo extractor for CV PDFs.
//
// Mirrors `extract_cv_image` in
// `backend/src/jobs_finder/infrastructure/cv/_parser.py`. The
// Python port uses PyMuPDF; this TypeScript port uses
// `unpdf.extractImages` (which wraps pdfjs-dist) so we get
// PyMuPDF-quality image detection without the PyMuPDF native
// dependency. We then re-encode the raw pixel data to a PNG
// byte stream via `pngjs`.
//
// Strategy:
//   1. Use `unpdf.getDocumentProxy` to get a pdfjs document.
//   2. For each page, call `unpdf.extractImages` — equivalent
//      to PyMuPDF's `page.get_images(full=True)`.
//   3. For each image: apply a stack of filters:
//      - Must NOT be a Form XObject / pattern (key starts
//        with "g_").
//      - Must be at least 200x200 pixels (a real CV headshot;
//        smaller images are tile units, icons, or logos).
//      - Must be at most 2000x2000 pixels (a real CV headshot;
//        larger images are page backgrounds).
//      - Must be RGB or RGBA (3 or 4 channels; grayscale = SMask).
//      - Pixel data must be at least 4 KB.
//   4. Pick the BEST candidate: most channels, then largest
//      by raw data size, then earliest page.
//   5. Re-encode the selected image as a valid PNG byte stream
//      via pngjs. Force the alpha channel to 255 (opaque) so
//      any residual transparency doesn't cause the renderer
//      to composite the image weirdly.
//
// The function never throws on bad input — it returns `null`
// on any failure. This matches `extractPdfText`'s contract
// and AGENTS.md rule #24 (no leaking of internal exception
// details).

import "server-only";

import { extractImages, getDocumentProxy } from "unpdf";
import { PNG } from "pngjs";

const MIN_IMAGE_BYTES = 4_000;
// Real CV headshots are typically at least 200x200. Anything
// smaller is likely a tile unit, an icon, a logo, or a
// thumbnail.
const MIN_WIDTH = 200;
const MIN_HEIGHT = 200;
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
      // resource table start with "img_"; Form XObjects and
      // patterns start with "g_". The "g_" prefix was the root
      // cause of the "tiled headshot" regression — unpdf was
      // returning the tile unit of a pattern.
      if (img.key?.startsWith("g_")) {
        console.log(
          `pdf/extract-image: skipping ${img.width}x${img.height} (${img.channels}ch) key=${img.key} — Form XObject / pattern`,
        );
        continue;
      }

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

      if (img.channels < 3) {
        console.log(
          `pdf/extract-image: skipping ${img.width}x${img.height} (${img.channels}ch) — grayscale (likely SMask)`,
        );
        continue;
      }

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

  // Most channels first, then largest size, then earliest page.
  candidates.sort((a, b) => {
    if (b.channels !== a.channels) return b.channels - a.channels;
    if (b.bytes !== a.bytes) return b.bytes - a.bytes;
    return a.pageNum - b.pageNum;
  });

  const best = candidates[0]!;

  try {
    const png = new PNG({
      width: best.width,
      height: best.height,
      channels: best.channels,
    });
    png.data = new Uint8Array(best.data);
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
