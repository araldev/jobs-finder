// @vitest-environment node
// (The default vitest environment is jsdom, which does NOT
// implement the HTMLCanvasElement APIs that unpdf's
// renderPageAsImage needs. This file declares node so the
// @napi-rs/canvas dependency provides the real canvas impl.)

// Tests for `extractCvImage` — the photo extractor for CV PDFs.
//
// The implementation:
//   1. Walks the pdfjs OPERATOR LIST tracking the CTM (current
//      transformation matrix) through save/restore/transform ops.
//   2. For each `paintImageXObject` op, computes its bounding box
//      from the CTM at that point.
//   3. Picks the largest image and crops from the rendered page.
//   4. If no image was found (e.g. photo in a tiling pattern, or
//      a synthetic test PDF with rectangles instead of image
//      XObjects), falls back to a GRID-BASED colorfulness scan
//      over the top 65 % of the page.
//
// These tests create synthetic PDFs with colored rectangles
// (simulating a photo via pdf-lib). Since a rectangle is NOT an
// image XObject, all tests exercise the GRID FALLBACK path.
// The operator-list path is tested implicitly: when a real PDF
// with embedded images is processed, the operator list finds them
// first.
//
// Tests cover: detection in multiple positions, rejection of
// text-only/blank pages, and graceful error handling.

import { describe, it, expect, vi } from "vitest";
import { PDFDocument, rgb } from "pdf-lib";
import { PNG } from "pngjs";

vi.mock("server-only", () => ({}));

import { extractCvImage } from "../extract-image";

/** Page dimensions for an A4 page in pdf-lib units. */
const PAGE_W = 595;
const PAGE_H = 842;

/**
 * Draw a colorful rectangle that simulates a photo in a given region.
 * The rectangle uses a non-gray color (red) so it scores high on
 * the colorfulness metric.
 */
function drawPhotoRegion(
  doc: PDFDocument,
  x: number,
  y: number,
  w: number,
  h: number,
): void {
  const page = doc.getPages()[0]!;
  page.drawRectangle({
    x,
    y,
    width: w,
    height: h,
    color: rgb(0.9, 0.1, 0.1), // bright red — colorful
  });
  // Add a second color rectangle to increase colorfulness
  page.drawRectangle({
    x: x + 10,
    y: y + 10,
    width: w * 0.4,
    height: h * 0.4,
    color: rgb(0.1, 0.1, 0.9), // blue — different channel
  });
}

describe("extractCvImage", () => {
  it("detects and crops a photo in the TOP-RIGHT region", async () => {
    // A4 page with a colorful "photo" in the top-right corner.
    const doc = await PDFDocument.create();
    doc.addPage([PAGE_W, PAGE_H]);
    drawPhotoRegion(doc, 420, 680, 150, 160);
    const bytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);

    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/png;base64,/);
    // Verify valid PNG header
    const b64 = dataUrl!.replace(/^data:image\/png;base64,/, "");
    const decoded = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    expect(Array.from(decoded.slice(0, 8))).toEqual([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    ]);
    // Cropped region should be at least 100px in each dimension
    const png = PNG.sync.read(Buffer.from(decoded));
    expect(png.width).toBeGreaterThanOrEqual(100);
    expect(png.height).toBeGreaterThanOrEqual(100);
  });

  it("detects and crops a photo in the TOP-LEFT region", async () => {
    // A4 page with a colorful "photo" in the top-left corner.
    const doc = await PDFDocument.create();
    doc.addPage([PAGE_W, PAGE_H]);
    drawPhotoRegion(doc, 20, 680, 150, 160);
    const bytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);

    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/png;base64,/);
  });

  it("detects and crops a photo in the CENTER-TOP region", async () => {
    // A4 page with a colorful "photo" centered in the header.
    const doc = await PDFDocument.create();
    doc.addPage([PAGE_W, PAGE_H]);
    drawPhotoRegion(doc, 200, 680, 200, 150);
    const bytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);

    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/png;base64,/);
  });

  it("returns null for a page with only black text (no photo)", async () => {
    // Black text on white has very low colorfulness (R≈G≈B per pixel)
    // → should score below threshold and return null.
    const doc = await PDFDocument.create();
    const page = doc.addPage([PAGE_W, PAGE_H]);
    page.drawText("Hello CV — purely text, no photo", {
      x: 50,
      y: 700,
      size: 12,
    });
    page.drawText("More text content in the header area", {
      x: 50,
      y: 680,
      size: 10,
    });
    const bytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);

    // Text-only pages should not be detected as containing a photo.
    expect(dataUrl).toBeNull();
  });

  it("returns null for a blank page (no content at all)", async () => {
    const doc = await PDFDocument.create();
    doc.addPage([PAGE_W, PAGE_H]);
    const bytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);

    expect(dataUrl).toBeNull();
  });

  it("returns null for malformed bytes (no leak of underlying error)", async () => {
    const garbage = new TextEncoder().encode("not a pdf, just text").buffer;
    const dataUrl = await extractCvImage(garbage);
    // AGENTS.md rule #24 — graceful fallback.
    expect(dataUrl).toBeNull();
  });

  it("returns null for an empty ArrayBuffer", async () => {
    const dataUrl = await extractCvImage(new ArrayBuffer(0));
    expect(dataUrl).toBeNull();
  });
});
