// Tests for `extractCvImage` — the photo extractor for CV PDFs.
//
// The current implementation uses `unpdf.extractImages` (pdfjs
// under the hood) to get all painted images, then filters out
// Form XObjects / patterns (key starts with "g_"), grayscale
// SMasks, and images outside the 200x200..2000x2000 size
// range. The best candidate (most channels, largest size,
// earliest page) is re-encoded as a PNG data URL via pngjs.
//
// Tests cover the contract: returns a valid PNG data URL for a
// well-formed PDF, returns null for bad input (no leak of
// internal exception details, AGENTS.md rule #24).

import { describe, it, expect, vi } from "vitest";
import { PDFDocument } from "pdf-lib";
import { PNG } from "pngjs";

vi.mock("server-only", () => ({}));

import { extractCvImage } from "../extract-image";

// Build a real PNG byte array. The minimum acceptable size
// for the new extractor is 200x200 (a real CV headshot). Smaller
// images are filtered out (tile units, icons, logos).
function buildPngBytes(width: number, height: number): Uint8Array {
  const png = new PNG({ width, height });
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      png.data[idx] = (x * 7) & 0xff;
      png.data[idx + 1] = (y * 11) & 0xff;
      png.data[idx + 2] = ((x + y) * 13) & 0xff;
      png.data[idx + 3] = 0xff;
    }
  }
  return new Uint8Array(PNG.sync.write(png));
}

async function makePdfWithPng(png: Uint8Array): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const image = await doc.embedPng(png);
  doc.addPage().drawImage(image, { x: 50, y: 600, width: 200, height: 200 });
  return new Uint8Array(await doc.save());
}

async function makePdfWithoutImages(): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  doc.addPage();
  return new Uint8Array(await doc.save());
}

describe("extractCvImage", () => {
  it("returns a PNG data URL when the PDF contains a large embedded image (>= 200x200)", async () => {
    // 250x250 = 62_500 pixels, 4-channel RGBA = 250_000 bytes.
    // Well above the 4 KB threshold and the 200x200 minimum.
    const png = buildPngBytes(250, 250);
    const bytes = await makePdfWithPng(png);

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);

    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toMatch(/^data:image\/png;base64,/);
    // Verify it's a valid PNG.
    const b64 = dataUrl!.replace(/^data:image\/png;base64,/, "");
    const decoded = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    expect(Array.from(decoded.slice(0, 8))).toEqual([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    ]);
  });

  it("filters out images smaller than 200x200 (tile units, icons, logos)", async () => {
    // 50x50 = 2_500 pixels — well above the 4 KB threshold
    // but well below the 200x200 minimum. This is the "tile
    // unit" / "icon" / "logo" size that the user's CV was
    // returning (causing the tiled-headshot regression).
    const smallPng = buildPngBytes(50, 50);
    const bytes = await makePdfWithPng(smallPng);

    const dataUrl = await extractCvImage(bytes.buffer.slice(0) as ArrayBuffer);
    expect(dataUrl).toBeNull();
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
});
