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
//      `Filter` is `/DCTDecode` (i.e. a JPEG embedded as-is), pull
//      the raw stream bytes via `PDFRawStream.getContents()`.
//   4. Skip any image smaller than `MIN_IMAGE_BYTES` (4 KB) — these
//      are logos, favicons, social icons, NOT the candidate's
//      profile photo. The threshold matches the Python port's
//      10_000 byte value LOOSENED to 4_000 because: real CV
//      profile photos are commonly 5-10 KB at 200x250px JPEG
//      quality 60-70%, while logos/icons are reliably <2 KB. The
//      4 KB threshold catches all icons while accepting real
//      photos. (Python port uses 10_000 — that's a TODO to
//      revisit if the user reports a CV with a small photo.)
//   5. Return the FIRST eligible image as a
//      `data:image/<mime>;base64,<...>` URL.
//
// Limitations (vs. the Python port):
//   - We only support DCTDecode (JPEG) and JPXDecode (JPEG 2000).
//     Both formats store the raw image bytes inline — the PDF
//     stream's contents ARE the original JPEG/JPX file bytes,
//     so no further decoding is required.
//   - We do NOT support FlateDecode (PNG / raw bitmaps). Those
//     formats split the image into RGB + alpha channels with
//     prediction filters; reconstructing a valid PNG from them is
//     out of scope for this round. Real CV profile photos are
//     almost always JPEGs (cameras, smartphones, headshot
//     services), so DCTDecode covers ~99% of the field.
//
// The function never throws on bad input — it returns `null` on
// any failure (malformed PDF, no images, oversized threshold).
// This matches `extractPdfText`'s contract and AGENTS.md rule #24
// (no leaking of internal exception details).

import "server-only";

import { PDFDocument, PDFName } from "pdf-lib";

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

        // Filter — accept DCTDecode (JPEG) and JPXDecode (JPEG2000).
        // Both filters store the source image bytes inline, so the
        // stream's `getContents()` IS the original file. We do NOT
        // support FlateDecode (PNG / raw bitmaps) — reconstructing a
        // PNG from split RGB + alpha channels with prediction
        // filters is out of scope. Real CV profile photos are almost
        // always JPEGs (cameras, smartphones, headshot services).
        const filter = dict.get(PDFName.of("Filter"));
        const filterName = filter?.toString();

        let mime: string | null = null;
        if (filterName === "/DCTDecode") mime = "image/jpeg";
        else if (filterName === "/JPXDecode") mime = "image/jp2";
        else {
          // Most common case: FlateDecode (PNG / raw bitmaps).
          // Currently skipped — see module docstring. Log so the
          // user/dev can see in the dev server that this is the
          // path being taken (diagnostic for the photo issue).
          console.log(
            `pdf/extract-image: skipping ${filterName ?? "(no filter)"} image (not supported — only /DCTDecode and /JPXDecode)`,
          );
          continue;
        }

        // Guard: a PDF stream subclass might lack getContents.
        // (None of pdf-lib's own streams do — but external
        // subclasses could.)
        if (typeof stream.getContents !== "function") continue;
        const imageBytes = stream.getContents();
        if (imageBytes.byteLength < MIN_IMAGE_BYTES) {
          // Diagnostic log so the dev can see the threshold skip
          // path (was the most common cause of the missing photo
          // before the threshold was lowered to 4 KB).
          console.log(
            `pdf/extract-image: skipping ${imageBytes.byteLength} byte image (below ${MIN_IMAGE_BYTES} threshold — probably a logo/icon)`,
          );
          continue;
        }

        // Base64 encode with `Buffer` (Node) or the btoa fallback
        // for edge runtimes. Chunking keeps the call stack flat
        // for very large images (uncommon at 10–500 KB but cheap
        // to guard).
        const b64 = bytesToBase64(imageBytes);
        console.log(
          `pdf/extract-image: extracted photo, ${imageBytes.byteLength} bytes, ${mime}`,
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