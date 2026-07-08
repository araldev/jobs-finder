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
//   3. For each image: filter by size (skip logos / icons
//      that are too small to be a headshot) and collect it
//      as a candidate.
//   4. From all candidates, pick the BEST one — most
//      channels first (favors 3- or 4-channel color images
//      over 1-channel grayscale SMasks), then largest by raw
//      data size. This filter is what fixes the "photo
//      appears as a grayscale tile" regression: pdfjs emits
//      the SMask (alpha channel) as a separate 1-channel
//      grayscale image with the SAME dimensions as the main
//      image. Taking the first image returned gave us the
//      SMask (grayscale, smaller byte count) instead of the
//      main color image.
//   5. Re-encode the selected image as a valid PNG byte
//      stream via pngjs and return as a
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
  // then pick the best one. Going best-of-all (not first-of-all)
  // is what filters out the SMask (alpha channel) which pdfjs
  // emits as a separate 1-channel grayscale image with the
  // same dimensions as the main image — the SMask has fewer
  // channels and a smaller byte count than the main image.
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

  // Pick the BEST candidate: most channels (favors 3-/4-channel
  // color over 1-channel grayscale SMask), then largest by raw
  // data size, then earliest page (first page wins when there
  // are multiple same-size main images).
  candidates.sort((a, b) => {
    if (b.channels !== a.channels) return b.channels - a.channels;
    if (b.bytes !== a.bytes) return b.bytes - a.bytes;
    return a.pageNum - b.pageNum;
  });

  const best = candidates[0]!;

  // Re-encode the raw pixel data to a valid PNG byte stream
  // via pngjs. The renderer embeds this PNG via
  // `doc.embedPng(...)` (see `render-cv.ts`), so the photo
  // data URL must be `data:image/png;base64,...`.
  try {
    const png = new PNG({
      width: best.width,
      height: best.height,
      channels: best.channels,
    });
    // `img.data` is a Uint8ClampedArray; pngjs' data field
    // is a Uint8Array (alias for Buffer in Node). We copy
    // into a plain Uint8Array so the TS type aligns.
    png.data = new Uint8Array(best.data);
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
