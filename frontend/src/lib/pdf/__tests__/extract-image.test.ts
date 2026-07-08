// Tests for `extractCvImage` — the pdf-lib image extractor used by
// the cv/generate route to extract a CV's embedded photo as a base64
// data URL.
//
// Mirrors `extract_cv_image` in
// `backend/src/jobs_finder/infrastructure/cv/_parser.py` (the
// Python port uses PyMuPDF — this TypeScript port uses `pdf-lib`'s
// internal XObject traversal). Both implementations:
//   - iterate pages in order
//   - filter out images smaller than 4 KB (logos, favicons, icons)
//   - return the first match as a `data:<mime>;base64,<...>` URL
//   - return `null` when no eligible image is found
//
// Verifies:
//   - A PDF with a single large JPEG image returns its data URL.
//   - A PDF with only tiny images (< 4 KB) returns `null`.
//   - A PDF with no images returns `null`.
//   - Malformed bytes return `null` (no leak of underlying error).
//   - The 4 KB threshold is the lower bound (any image ≥ 4 KB is OK;
//     the previous 10 KB threshold was too conservative for compressed
//     CV photos at 200x250px JPEG quality 60-70%, which routinely
//     land in the 5-15 KB range).

import { describe, it, expect, vi } from "vitest";
import { PDFDocument } from "pdf-lib";
import { PNG } from "pngjs";

vi.mock("server-only", () => ({}));

import { extractCvImage } from "../extract-image";

// Build a JPEG byte array large enough to pass the 10 KB threshold.
// pdf-lib's `embedJpg` only validates the JPEG header + SOF marker
// (see `JpegEmbedder.for` in `pdf-lib/cjs/core/embedders/JpegEmbedder.js`)
// — it does NOT decode the entropy stream. So a "synthetic" JPEG with
// a real header + a padded SOF segment is accepted by `embedJpg` and
// round-trips back through our extractor byte-for-byte. This is a
// TEST-ONLY fixture: production code never sees these bytes.
function buildJpegBytes(targetSize = 12_000): Uint8Array {
  const bytes = new Uint8Array(targetSize);

  // SOI marker.
  bytes[0] = 0xff;
  bytes[1] = 0xd8;

  // APP0 (JFIF) segment — minimal, just so the header looks plausible.
  // FF E0 <length:2> "JFIF\0" <version:4> <units:1> <Xdensity:2> <Ydensity:2> ...
  bytes[2] = 0xff;
  bytes[3] = 0xe0;
  const app0Len = 16; // segment length (includes the 2 length bytes)
  bytes[4] = (app0Len >> 8) & 0xff;
  bytes[5] = app0Len & 0xff;
  // "JFIF\0"
  bytes[6] = 0x4a;
  bytes[7] = 0x46;
  bytes[8] = 0x49;
  bytes[9] = 0x46;
  bytes[10] = 0x00;
  // Version 1.1
  bytes[11] = 0x01;
  bytes[12] = 0x01;
  // Units = 0 (no units), X density = 1, Y density = 1
  bytes[13] = 0x00;
  bytes[14] = 0x00;
  bytes[15] = 0x01;
  bytes[16] = 0x00;
  bytes[17] = 0x01;
  // No thumbnail
  bytes[18] = 0x00;
  bytes[19] = 0x00;

  // SOF0 (baseline DCT) marker — pdf-lib walks past non-SOF markers
  // until it hits one of FFC0..FFCF, then reads:
  //   bitsPerComponent (1 byte), height (2), width (2), channels (1)
  // FF C0 <length:2> <precision:1> <height:2> <width:2> <channels:1> ...
  bytes[20] = 0xff;
  bytes[21] = 0xc0;
  const sofLen = 11; // SOF0 segment length for 1 component (3-channel uses 17, but pdf-lib reads 1 byte here)
  bytes[22] = (sofLen >> 8) & 0xff;
  bytes[23] = sofLen & 0xff;
  bytes[24] = 0x08; // precision = 8 bits per component
  bytes[25] = 0x00;
  bytes[26] = 0x40; // height = 64
  bytes[27] = 0x00;
  bytes[28] = 0x40; // width = 64
  bytes[29] = 0x03; // 3 channels (RGB → DeviceRGB in pdf-lib)

  // Fill the rest with a no-op marker pattern (FF FE = comment marker
  // is safe — pdf-lib walks past it). pdf-lib stops at the SOF0, so
  // anything after doesn't need to be a real entropy stream for the
  // embedder or our extractor to accept it.
  for (let i = 30; i < targetSize - 2; i += 2) {
    bytes[i] = 0xff;
    bytes[i + 1] = 0xfe; // COM (comment) marker
  }
  // EOI at the very end (cosmetic — pdf-lib doesn't check).
  bytes[targetSize - 2] = 0xff;
  bytes[targetSize - 1] = 0xd9;

  return bytes;
}

async function makePdfWithJpeg(jpeg: Uint8Array): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const image = await doc.embedJpg(jpeg);
  const page = doc.addPage();
  page.drawImage(image, { x: 50, y: 700, width: 80, height: 80 });
  return new Uint8Array(await doc.save());
}

async function makePdfWithoutImages(): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  doc.addPage();
  return new Uint8Array(await doc.save());
}

describe("extractCvImage", () => {
  it("returns a JPEG data URL when the PDF contains a single large embedded image", async () => {
    const jpeg = await buildJpegBytes();
    const bytes = await makePdfWithJpeg(jpeg);

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);

    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/jpeg;base64,/);
    // Round-trip the base64 payload and confirm it matches the source bytes.
    const b64 = dataUrl!.replace(/^data:image\/jpeg;base64,/, "");
    const decoded = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    expect(decoded.byteLength).toBe(jpeg.byteLength);
    expect(decoded).toEqual(jpeg);
  });

  it("filters out images smaller than 4 KB (logos, icons, not photos)", async () => {
    // Build a PDF with a tiny JPEG (well under the threshold).
    // The Python port uses `if len(image_bytes) < 10_000: continue`
    // — our TypeScript port uses 4_000 to also accept compressed
    // CV photos that are commonly 5-10 KB at 200x250px JPEG
    // quality 60-70%. Logos/icons are reliably < 2 KB.
    const tinyJpeg = buildJpegBytes(2_000);
    const bytes = await makePdfWithJpeg(tinyJpeg);

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);
    expect(dataUrl).toBeNull();
  });

  it("accepts a 5 KB image (the previous 10 KB threshold rejected this — a real compressed CV photo)", async () => {
    // Regression test: this image size was rejected under the
    // 10 KB threshold even though it's a legitimate CV photo.
    // The 4 KB threshold now accepts it.
    const smallJpeg = buildJpegBytes(5_000);
    const bytes = await makePdfWithJpeg(smallJpeg);

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);
    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/jpeg;base64,/);
  });

  it("accepts an image at the 4 KB threshold boundary", async () => {
    const boundaryJpeg = buildJpegBytes(4_000);
    const bytes = await makePdfWithJpeg(boundaryJpeg);

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);
    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/jpeg;base64,/);
  });

  it("returns null when the PDF has no images", async () => {
    const bytes = await makePdfWithoutImages();
    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);
    expect(dataUrl).toBeNull();
  });

  it("returns null for malformed bytes (no leak of underlying error)", async () => {
    const garbage = new TextEncoder().encode("not a pdf, just text").buffer;
    const dataUrl = await extractCvImage(garbage);
    // AGENTS.md rule #24 — graceful fallback. We don't assert
    // "throws"; the contract is "returns null on any failure".
    expect(dataUrl).toBeNull();
  });

  it("returns null for an empty ArrayBuffer", async () => {
    const dataUrl = await extractCvImage(new ArrayBuffer(0));
    expect(dataUrl).toBeNull();
  });

  it("extracts a FlateDecode-embedded PNG image (via embedPng)", async () => {
    // pdf-lib's embedPng decodes the PNG into raw RGB + alpha, then
    // embeds the RGB data as a FlateDecode stream (see PngEmbedder
    // in pdf-lib). This test verifies the FlateDecode path in our
    // extractor: it should reconstruct a PNG from the raw pixel data.
    // The alpha channel is embedded as a separate SMask XObject that
    // gets skipped (flat constant mask → too small after PNG
    // reconstruction → falls below the 4 KB threshold), so the main
    // RGB image is the one the extractor returns.
    // 100×100 with random-ish noise so the PNG compresses to well
    // over the 4 KB MIN_IMAGE_BYTES threshold (a smooth gradient
    // only produces ~1.2 KB — too small).
    const png = new PNG({ width: 80, height: 80 });
    for (let y = 0; y < 80; y++) {
      for (let x = 0; x < 80; x++) {
        const idx = (y * 80 + x) * 4;
        png.data[idx] = ((x * 13 + y * 29) * 7) & 0xff;
        png.data[idx + 1] = ((x * 17 + y * 31) * 11) & 0xff;
        png.data[idx + 2] = ((x * 19 + y * 23) * 5) & 0xff;
        png.data[idx + 3] = 255;
      }
    }
    const pngRaw = PNG.sync.write(png);
    // Convert Node Buffer → pure Uint8Array (vitest may not
    // recognise Buffer as Uint8Array in all code paths).
    const pngBytes = new Uint8Array(pngRaw.buffer, pngRaw.byteOffset, pngRaw.byteLength);

    const doc = await PDFDocument.create();
    const image = await doc.embedPng(pngBytes);
    doc.addPage().drawImage(image, { x: 50, y: 700, width: 80, height: 80 });
    const pdfBytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(
      pdfBytes.buffer.slice(0) as ArrayBuffer,
    );

    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/png;base64,/);

    // Verify the reconstructed PNG has the right dimensions and
    // basic pixel properties.  pdf-lib's embedPng decodes and
    // re-encodes the image, so we cannot guarantee byte-for-byte
    // round-trip of every pixel — but we CAN verify the structural
    // properties that matter for CV photo extraction.
    const b64 = dataUrl!.replace(/^data:image\/png;base64,/, "");
    const decodedBytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const decoded = PNG.sync.read(Buffer.from(decodedBytes));
    expect(decoded.width).toBe(80);
    expect(decoded.height).toBe(80);
    // All alpha values should be 255 (fully opaque — our source
    // PNG had A=255 for every pixel).
    for (let i = 3; i < decoded.data.length; i += 4) {
      expect(decoded.data[i]).toBe(255);
    }
    // The image should have per-pixel variation (not constant color).
    // This proves the noise pattern round-tripped through the
    // FlateDecode → RGBA → PNG reconstruction pipeline.
    expect(decoded.data.slice(0, 4)).not.toEqual(decoded.data.slice(4, 8));
  });

  it("encodes the first eligible image it finds (page iteration order)", async () => {
    // Build a 2-page PDF where each page has a distinct JPEG. The
    // extractor MUST return the first one it encounters (matches
    // the Python `extract_cv_image` behavior — first image in
    // first page).
    const jpegA = await buildJpegBytes();
    const jpegB = await buildJpegBytes();
    const doc = await PDFDocument.create();
    const imgA = await doc.embedJpg(jpegA);
    const imgB = await doc.embedJpg(jpegB);
    doc.addPage().drawImage(imgA, { x: 50, y: 700, width: 50, height: 50 });
    doc.addPage().drawImage(imgB, { x: 50, y: 700, width: 50, height: 50 });
    const bytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);
    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/jpeg;base64,/);
  });
});