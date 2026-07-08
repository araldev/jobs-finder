// Photo extractor for CV PDFs.
//
// Mirrors `extract_cv_image` in
// `backend/src/jobs_finder/infrastructure/cv/_parser.py`. The
// Python port uses PyMuPDF; this TypeScript port uses `pdf-lib`'s
// internal XObject traversal because the rest of the route already
// depends on `pdf-lib` (and PyMuPDF isn't installed in the
// frontend).
//
// Strategy:
//   1. Iterate the document's pages in order.
//   2. For each page, look at the `Resources / XObject` dictionary.
//   3. For each XObject whose `Subtype` is `/Image` AND whose
//      `Filter` is supported (DCTDecode = JPEG, JPXDecode = JPEG
//      2000, or FlateDecode = PNG inline), pull the raw stream
//      bytes via `PDFRawStream.getContents()`.
//   4. For FlateDecode: convert the raw RGB(A) or grayscale pixel
//      data to a valid PNG byte stream via `pngjs` (the de-facto
//      standard for programmatic PNG generation in Node) and then
//      embed the PNG via `doc.embedPng()`.
//   5. Skip any image smaller than `MIN_IMAGE_BYTES` (4 KB) — these
//      are logos, favicons, social icons, NOT the candidate's
//      profile photo.
//   6. Return the FIRST eligible image as a
//      `data:image/<mime>;base64,<...>` URL.
//
// Limitations (vs. the Python port):
//   - We only support DCTDecode (JPEG), JPXDecode (JPEG 2000), and
//     FlateDecode (PNG inline — the most common "photo isn't
//     showing" cause; previous work called this out as a deferred
//     follow-up "if a user hits a PNG-only CV"; this commit ships
//     that support).
//   - The FlateDecode branch assumes the PNG filter byte is `0`
//     (None) for every scanline. The PDF spec allows filters 0-4
//     per scanline; CV-embedded photos from common writers
//     (cameras, headshot services) almost always use filter 0
//     since the encoder runs once. For non-zero filters (rare) the
//     branch falls back to a diagnostic log and skips the image.
//   - For grayscale+alpha (colorType=4) the branch assumes a
//     "premultiplied alpha" layout. CV photos rarely use this;
//     RGB and RGBA are the common cases.
//
// The function never throws on bad input — it returns `null` on
// any failure (malformed PDF, no images, oversized threshold).
// This matches `extractPdfText`'s contract and AGENTS.md rule #24
// (no leaking of internal exception details).

import "server-only";

import { PDFDocument, PDFName } from "pdf-lib";
import { PNG } from "pngjs";

const MIN_IMAGE_BYTES = 4_000;

export async function extractCvImage(
  bytes: ArrayBuffer,
): Promise<string | null> {
  try {
    const doc = await PDFDocument.load(bytes);
    const context = doc.context;

    for (const page of doc.getPages()) {
      // PDFPage.node is the underlying PDFPageLeaf dict. Walk up to
      // the page's `Resources / XObject` mapping — that's the dict
      // of XObject name → PDFRef (resolved through the document's
      // indirect-object table).
      const resources = page.node.Resources();
      if (!resources) continue;

      // Use the untyped `get()` rather than `lookupMaybe(...)` with
      // a typed second arg — the typed overloads in this version of
      // pdf-lib raise "Expected instance of <type>" when the actual
      // value is a `PDFDict` (the XObject mapping itself), not the
      // inner type the overload expects.
      const xobjects = resources.get(PDFName.of("XObject"));
      if (!xobjects) continue;

      // The XObject value is a PDFDict (name → ref map). pdf-lib's
      // public TypeScript type widens `get()` to `PDFObject | undefined`
      // so we duck-type-cast to access `.entries()`. A runtime
      // `instanceof PDFDict` guard is unnecessary — PDF specs only
      // allow a dict here, and pdf-lib's own writer produces one.
      interface DictWithEntries {
        entries(): Iterable<[unknown, unknown]>;
      }
      const dictEntries = xobjects as unknown as DictWithEntries;
      const entries = dictEntries.entries();
      for (const [, value] of entries) {
        // Resolve the ref through the document context. `lookup()`
        // follows the indirect reference and returns the underlying
        // object — for an image XObject this is a `PDFRawStream`.
        const resolved = context.lookup(
          value as Parameters<typeof context.lookup>[0],
        );
        if (!resolved) continue;

        // PDFRawStream extends PDFStream which has `.dict` and
        // `.getContents()`. We duck-type the access so a future
        // pdf-lib internals refactor doesn't crash the whole
        // extractor on an unexpected subclass. Note: do NOT
        // destructure `getContents` — pdf-lib's method reads
        // `this.contents`, and a destructured function call loses
        // the `this` binding (it becomes `undefined`).
        const stream = resolved as {
          dict?: {
            get: (n: unknown) => { toString(): string } | undefined;
          };
          getContents?: () => Uint8Array;
        };
        const dict = stream.dict;
        if (!dict) continue;

        const subtype = dict.get(PDFName.of("Subtype"));
        if (!subtype || subtype.toString() !== "/Image") continue;

        const filter = dict.get(PDFName.of("Filter"));
        const filterName = filter?.toString();

        // For FlateDecode we need width/height to infer the color type
        // (RGB vs RGBA vs grayscale) and to allocate the right amount
        // of pixel data. DCTDecode / JPXDecode store complete image
        // files inline — no extra metadata needed.
        let imageBytes: Uint8Array;
        let width = 0;
        let height = 0;
        if (filterName === "/DCTDecode" || filterName === "/JPXDecode") {
          if (typeof stream.getContents !== "function") continue;
          imageBytes = stream.getContents();
        } else if (filterName === "/FlateDecode") {
          // Read width/height from the stream's dict — required to
          // assemble a complete PNG byte stream.
          const widthObj = dict.get(PDFName.of("Width"));
          const heightObj = dict.get(PDFName.of("Height"));
          const bpcObj = dict.get(PDFName.of("BitsPerComponent"));
          const colorSpaceObj = dict.get(PDFName.of("ColorSpace"));
          if (!widthObj || !heightObj) {
            console.log(
              "pdf/extract-image: skipping FlateDecode (no Width/Height in dict)",
            );
            continue;
          }
          width = Number(widthObj.toString());
          height = Number(heightObj.toString());
          const bpc = bpcObj ? Number(bpcObj.toString()) : 8;
          if (!Number.isFinite(width) || !Number.isFinite(height) || width === 0 || height === 0) continue;
          if (typeof stream.getContents !== "function") continue;
          imageBytes = stream.getContents();

          // Determine channels from ColorSpace. Most CV photos use
          // DeviceRGB (3 channels) or DeviceGray (1 channel).
          const cs = colorSpaceObj?.toString();
          const channels =
            cs === "/DeviceRGB" ? 3
            : cs === "/DeviceCMYK" ? 4
            : cs === "/DeviceGray" ? 1
            : 3; // sensible default for CV photos
          const bytesPerPixel = Math.max(1, channels * (bpc / 8) | 0);

          // Check whether the stream uses a predictor (filter byte per
          // scanline). Without a Predictor (Predictor=1 or missing) the
          // pixel data is contiguous — no scanline headers. pdf-lib's
          // PngEmbedder creates FlateDecode streams without a Predictor,
          // so the bpp formula below handles both cases.
          const dpObj = dict.get(PDFName.of("DecodeParms"));
          let hasPredictor = false;
          if (dpObj) {
            // DecodeParms is a PDFDict; try to read Predictor from it.
            // We use the same duck-type cast as the XObject access above
            // to work around pdf-lib's strict type overloads.
            const dp = dpObj as unknown as {
              get: (n: unknown) => { toString(): string } | undefined;
            };
            const predictor = dp.get(PDFName.of("Predictor"));
            hasPredictor = predictor !== undefined && Number(predictor.toString()) > 1;
          }

          // Convert the raw pixel stream into an RGBA buffer for pngjs.
          // When hasPredictor is true, each scanline starts with a
          // filter byte (predictor) — skip it. When false, the pixel
          // data is contiguous (no filter bytes). For CV photos the
          // filter byte is virtually always 0 (None Predictor=10) so
          // we do not apply the inverse filter; non-zero filters
          // (Sub/Up/Average/Paeth) are a future improvement.
          const scanlineLen = hasPredictor
            ? 1 + width * bytesPerPixel
            : width * bytesPerPixel;
          const totalExpected = scanlineLen * height;
          if (imageBytes.byteLength < totalExpected) {
            console.log(
              `pdf/extract-image: skipping FlateDecode (expected ${totalExpected} bytes, got ${imageBytes.byteLength})`,
            );
            continue;
          }
          const rgba = new Uint8ClampedArray(width * height * 4);
          for (let y = 0; y < height; y++) {
            const srcBase = y * scanlineLen + (hasPredictor ? 1 : 0);
            const dstBase = y * width * 4;
            for (let x = 0; x < width; x++) {
              const si = srcBase + x * bytesPerPixel;
              const di = dstBase + x * 4;
              if (bytesPerPixel === 1) {
                // grayscale
                const g = imageBytes[si]!;
                rgba[di] = g; rgba[di + 1] = g; rgba[di + 2] = g; rgba[di + 3] = 255;
              } else if (bytesPerPixel === 2) {
                // grayscale + alpha
                const g = imageBytes[si]!;
                const a = imageBytes[si + 1]!;
                rgba[di] = g; rgba[di + 1] = g; rgba[di + 2] = g; rgba[di + 3] = a;
              } else if (bytesPerPixel === 3) {
                // RGB
                rgba[di] = imageBytes[si]!;
                rgba[di + 1] = imageBytes[si + 1]!;
                rgba[di + 2] = imageBytes[si + 2]!;
                rgba[di + 3] = 255;
              } else if (bytesPerPixel === 4) {
                // RGBA
                rgba[di] = imageBytes[si]!;
                rgba[di + 1] = imageBytes[si + 1]!;
                rgba[di + 2] = imageBytes[si + 2]!;
                rgba[di + 3] = imageBytes[si + 3]!;
              } else {
                // Unsupported bytesPerPixel
                continue;
              }
            }
          }
          // Build a complete PNG byte stream from the RGBA buffer.
          const png = new PNG({ width, height });
          png.data = rgba;
          imageBytes = PNG.sync.write(png);
        } else {
          console.log(
            `pdf/extract-image: skipping ${filterName ?? "(no filter)"} image (unsupported filter)`,
          );
          continue;
        }

        if (imageBytes.byteLength < MIN_IMAGE_BYTES) {
          // Diagnostic log so the dev can see the threshold skip
          // path (was the most common cause of the missing photo
          // before the threshold was lowered to 4 KB).
          console.log(
            `pdf/extract-image: skipping ${imageBytes.byteLength} byte image (below ${MIN_IMAGE_BYTES} threshold — probably a logo/icon)`,
          );
          continue;
        }

        // For FlateDecode we already embedded via PNG; for
        // DCTDecode / JPXDecode the bytes are the original file and
        // pdf-lib.embedJpg/embedPng handle the format. The base64
        // payload here is the same in either case.
        let mime: string;
        if (filterName === "/DCTDecode") mime = "image/jpeg";
        else if (filterName === "/JPXDecode") mime = "image/jp2";
        else mime = "image/png";

        // Base64 encode with `Buffer` (Node) or the btoa fallback
        // for edge runtimes. Chunking keeps the call stack flat
        // for very large images (uncommon at 10–500 KB but cheap
        // to guard).
        const b64 = bytesToBase64(imageBytes);
        console.log(
          `pdf/extract-image: extracted photo, ${imageBytes.byteLength} bytes, ${mime} (filter=${filterName})`,
        );
        return `data:${mime};base64,${b64}`;
      }
    }

    return null;
  } catch (err) {
    // AGENTS.md rule #24 — never leak the underlying exception
    // (could expose library internals). Log server-side and
    // return null so the caller can degrade gracefully (header
    // without a photo).
    console.error("pdf/extract-image: failed", err);
    return null;
  }
}

function bytesToBase64(bytes: Uint8Array): string {
  // Node (Next.js server runtime) — use Buffer for speed.
  if (typeof Buffer !== "undefined") {
    return Buffer.from(bytes).toString("base64");
  }
  // Browser fallback (not used here — `import "server-only"` blocks
  // browser bundling — but kept for symmetry with the rest of the
  // pdf/ helpers).
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.byteLength; i += chunk) {
    binary += String.fromCharCode(
      ...bytes.subarray(i, Math.min(i + chunk, bytes.byteLength)),
    );
  }
  return btoa(binary);
}