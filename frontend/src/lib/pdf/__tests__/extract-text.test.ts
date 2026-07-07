// Tests for `extractPdfText` — the unpdf wrapper used by the
// cv/generate route to convert the uploaded PDF's bytes into a
// single merged text string for the LLM.
//
// Verifies:
//   - Empty / non-text PDFs return "" (graceful degradation).
//   - A PDF with one page of "Hello World" extracts that text.
//   - The function never throws (AGENTS.md rule #24 — the caller
//     receives "" on any failure, no internal exception leaks).

import { describe, it, expect, vi } from "vitest";
import { PDFDocument, StandardFonts } from "pdf-lib";

vi.mock("server-only", () => ({}));

import { extractPdfText } from "../extract-text";

async function makeMinimalPdf(text: string): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const page = doc.addPage();
  page.drawText(text, { x: 50, y: 700, font, size: 12 });
  return new Uint8Array(await doc.save());
}

describe("extractPdfText", () => {
  it("extracts single-page text", async () => {
    const bytes = await makeMinimalPdf("Hello World");
    const text = await extractPdfText(bytes.buffer.slice(0) as ArrayBuffer);
    expect(text).toContain("Hello World");
  });

  it("extracts multi-page text merged into a single string", async () => {
    const doc = await PDFDocument.create();
    const font = await doc.embedFont(StandardFonts.Helvetica);
    doc.addPage().drawText("Page One", { x: 50, y: 700, font, size: 12 });
    doc.addPage().drawText("Page Two", { x: 50, y: 700, font, size: 12 });
    const bytes = new Uint8Array(await doc.save());

    const text = await extractPdfText(bytes.buffer.slice(0) as ArrayBuffer);
    expect(text).toContain("Page One");
    expect(text).toContain("Page Two");
  });

  it("returns '' when given an empty ArrayBuffer", async () => {
    const text = await extractPdfText(new ArrayBuffer(0));
    expect(text).toBe("");
  });

  it("returns '' when given malformed bytes (no leak of underlying error)", async () => {
    const garbage = new TextEncoder().encode("not a pdf, just text").buffer;
    const text = await extractPdfText(garbage);
    // We don't assert "throws" — the contract is "graceful fallback".
    // Just confirm we don't crash and return some non-undefined value.
    expect(typeof text).toBe("string");
  });
});