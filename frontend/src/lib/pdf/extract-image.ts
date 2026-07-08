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
//   2. For each page (in order), call `unpdf.extractImages` —
//      this is equivalent to PyMuPDF's `page.get_images(full=True)`
//      and finds ALL images on the page (in Resources / XObject,
//      Form XObjects, patterns, annotations, soft masks, etc.),
//      not just the direct page XObjects the previous pdf-lib
//      walk could see.
//   3. For each image: filter by size (skip logos / icons that
//      are too small to be a headshot), then re-encode the
//      raw pixel data (Uint8ClampedArray) to a valid PNG byte
//      stream via pngjs.
//   4. Return the FIRST eligible image as a
//      `data:image/png;base64,<...>` URL.
//
// Why this is more robust than the previous pdf-lib walk:
//   - The old code only looked at `Resources / XObject` on each
//     page. If the CV's photo was placed in a Form XObject, a
//     pattern, or referenced indirectly from the content
//     stream, the old code missed it entirely. unpdf walks the
//     same way PyMuPDF does and finds the photo wherever it lives.
//   - The old code only handled 3 filters (DCTDecode, JPXDecode,
//     FlateDecode). unpdf returns RGBA pixel data regardless of
//     the original filter, so we get a uniform path with no
//     per-filter manual decode.
//   - Same `4 KB` size threshold as the Python backend so a
//     small headshot (5–10 KB) is NOT silently dropped.
//
// The function never throws on bad input — it returns `null` on
// any failure (malformed PDF, no images, oversized threshold).
// This matches `extractPdfText`'s contract and AGENTS.md rule #24
// (no leaking of internal exception details).

import "server-only";

import { extractImages, getDocumentProxy } from "unpdf";
import { PNG } from "pngjs";

const MIN_IMAGE_BYTES = 4_000;

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

  // Walk each page in order. Stop at the first eligible image
  // (matches PyMuPDF's `for page_num in range(len(doc))`).
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
      // Filter out tiny images (likely icons/logos, not a
      // photo). The previous code filtered on byte count; here
      // we have raw pixel data so we compute the equivalent
      // size — `width * height * channels` bytes — and compare
      // against the same 4 KB threshold.
      const pixelBytes = img.width * img.height * img.channels;
      if (pixelBytes < MIN_IMAGE_BYTES) {
        console.log(
          `pdf/extract-image: skipping ${img.width}x${img.height} (${img.channels}ch) — ${pixelBytes} bytes (< ${MIN_IMAGE_BYTES} threshold, probably a logo/icon)`,
        );
        continue;
      }

      // Re-encode the raw pixel data to a valid PNG byte stream
      // via pngjs. The renderer embeds this PNG via
      // `doc.embedPng(...)` (see `render-cv.ts`), so the photo
      // data URL must be `data:image/png;base64,<...>`.
      //
      // unpdf returns `data: Uint8ClampedArray` with the
      // channel count (1, 3, or 4) — pngjs' PNG supports all
      // three (grayscale, RGB, RGBA) so we just copy the buffer.
      try {
        const png = new PNG({
          width: img.width,
          height: img.height,
          channels: img.channels,
        });
        // `img.data` is a Uint8ClampedArray; pngjs' data field
        // is a Uint8Array (alias for Buffer in Node). We copy
        // into a plain Uint8Array so the TS type aligns.
        const data = new Uint8Array(img.data);
        png.data = data;
        const pngBytes = PNG.sync.write(png);
        const b64 = Buffer.from(pngBytes).toString("base64");
        console.log(
          `pdf/extract-image: extracted photo from page ${pageNum} — ${img.width}x${img.height} (${img.channels}ch) — ${pngBytes.byteLength} bytes`,
        );
        return `data:image/png;base64,${b64}`;
      } catch (err) {
        console.error(
          `pdf/extract-image: pngjs re-encode failed for page ${pageNum}`,
          err,
        );
        continue;
      }
    }
  }

  return null;
}
