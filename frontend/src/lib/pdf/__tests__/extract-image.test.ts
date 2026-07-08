// @vitest-environment node
// (The default vitest environment is jsdom, which does NOT
// implement the HTMLCanvasElement APIs that unpdf's
// renderPageAsImage needs. This file declares node so the
// @napi-rs/canvas dependency provides the real canvas impl.)

// Tests for `extractCvImage` — the photo extractor for CV PDFs.
//
// The current implementation renders the FIRST page of the PDF
// as a canvas image via `unpdf.renderPageAsImage` and crops
// the top-right region (where CV headshots typically live).
// This bypasses the per-image complexity of unpdf.extractImages
// (Form XObjects, patterns, SMasks, tile units) that caused
// a "tiled headshot" regression with the user's CV — the photo
// in the original PDF is a tiling pattern that the per-image
// route kept returning as a tile unit.
//
// Tests cover the contract: returns a valid PNG data URL for a
// well-formed PDF, returns null for bad input.

import { describe, it, expect, vi } from "vitest";
import { PDFDocument } from "pdf-lib";
import { PNG } from "pngjs";

vi.mock("server-only", () => ({}));

import { extractCvImage } from "../extract-image";

describe("extractCvImage", () => {
  it("renders the first page of a valid PDF and crops the top-right region for the headshot", async () => {
    const doc = await PDFDocument.create();
    // Add a text element in the top portion of the page so the
    // cropped region has SOMETHING to capture (not just white).
    doc.addPage().drawText("Hello CV", { x: 50, y: 700, size: 12 });
    const bytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);

    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/png;base64,/);
    // Verify it's a valid PNG (89 50 4E 47 0D 0A 1A 0A).
    const b64 = dataUrl!.replace(/^data:image\/png;base64,/, "");
    const decoded = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    expect(Array.from(decoded.slice(0, 8))).toEqual([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    ]);
    // The cropped region is at least MIN_HEADSHOT_SIDE in
    // each dimension (so a real headshot is always big enough
    // to be visible).
    const png = PNG.sync.read(Buffer.from(decoded));
    expect(png.width).toBeGreaterThanOrEqual(100);
    expect(png.height).toBeGreaterThanOrEqual(100);
  });

  it("returns a PNG data URL for a PDF with a blank page (no images / no text)", async () => {
    // The page-render approach doesn't fail for empty / blank
    // pages — it just returns a white PNG. The contract is
    // "returns a valid PNG for any well-formed PDF".
    const doc = await PDFDocument.create();
    doc.addPage();
    const bytes = new Uint8Array(await doc.save());

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);
    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/png;base64,/);
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
});
