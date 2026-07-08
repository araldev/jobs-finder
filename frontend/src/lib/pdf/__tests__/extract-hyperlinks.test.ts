/** @vitest-environment node */
import { describe, expect, it } from "vitest";
import {
  PDFArray,
  PDFDocument,
  PDFName,
  PDFNumber,
  PDFString,
} from "pdf-lib";

import { extractPdfHyperlinks } from "@/lib/pdf/extract-hyperlinks";

/**
 * Build a minimal PDF with text + URI link annotations.
 *
 * Mimics the Canva-style tight-rect PDF: the link annotation rect
 * covers only the baseline area of the text, NOT the full glyph
 * bbox. The frontend's `extractPdfHyperlinks` MUST use soft bbox
 * overlap (not center-point intersection) so it catches these
 * tight rects.
 *
 * Uses pdf-lib (already a dep) for both creation and link annotation
 * injection — `extractPdfHyperlinks` reads via `pdfjs-dist` (via
 * `unpdf`), so this is a true cross-library test.
 *
 * Note: pdf-lib's `context.obj({...})` does NOT auto-convert string
 * values to `PDFName` / `PDFString` / `PDFNumber` — the PDF spec
 * requires those, and pdfjs-dist (the reader) won't expose the URL
 * if the action dict has the wrong types. Wrap explicitly.
 */
async function makePdfWithLinks(
  textsAndLinks: Array<{
    text: string;
    x: number;
    y: number; // baseline
    rect: [number, number, number, number]; // [x1, y1, x2, y2] in PDF user space
    url: string;
  }>,
): Promise<ArrayBuffer> {
  const doc = await PDFDocument.create();
  const page = doc.addPage([612, 792]);

  for (const { text, x, y } of textsAndLinks) {
    page.drawText(text, { x, y, size: 11 });
  }

  // Add link annotations to the page. The action dict MUST be a real
  // `PDFDict` (not a JS object) with `Type: /Action`, `S: /URI`,
  // `URI: (string)` — otherwise pdfjs won't expose `url` on the
  // annotation.
  const annots: PDFArray = doc.context.obj([]);
  for (const { rect, url } of textsAndLinks) {
    const actionDict = doc.context.obj({
      Type: PDFName.of("Action"),
      S: PDFName.of("URI"),
      URI: PDFString.of(url),
    });
    const linkAnnot = doc.context.obj({
      Type: PDFName.of("Annot"),
      Subtype: PDFName.of("Link"),
      Rect: [
        PDFNumber.of(rect[0]),
        PDFNumber.of(rect[1]),
        PDFNumber.of(rect[2]),
        PDFNumber.of(rect[3]),
      ],
      Border: [PDFNumber.of(0), PDFNumber.of(0), PDFNumber.of(0)],
      A: actionDict,
    });
    annots.push(linkAnnot);
  }
  page.node.set(PDFName.of("Annots"), annots);

  const bytes = await doc.save();
  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
}

describe("extractPdfHyperlinks", () => {
  it("returns empty for a PDF with no link annotations", async () => {
    const doc = await PDFDocument.create();
    doc.addPage([612, 792]);
    const bytes = await doc.save();
    const ab = bytes.buffer.slice(
      bytes.byteOffset,
      bytes.byteOffset + bytes.byteLength,
    ) as ArrayBuffer;

    const result = await extractPdfHyperlinks(ab);
    expect(result).toEqual([]);
  });

  it("extracts a single http hyperlink with its visible label", async () => {
    // Tight-baseline rect (Canva-style): the link rect's bottom
    // touches the text baseline; the text glyphs extend ABOVE the
    // rect. Soft bbox overlap (not center-point) is required.
    const ab = await makePdfWithLinks([
      {
        text: "Github link",
        x: 100,
        y: 700,
        rect: [100, 700, 200, 712],
        url: "https://github.com/user/v12-ui",
      },
    ]);
    const result = await extractPdfHyperlinks(ab);
    expect(result).toHaveLength(1);
    expect(result[0]?.url).toBe("https://github.com/user/v12-ui");
    expect(result[0]?.page).toBe(1);
    expect(result[0]?.label.toLowerCase()).toContain("github");
  });

  it("extracts multiple hyperlinks (the user's V12-UI case)", async () => {
    // 3 adjacent labels with tight baseline rects (Canva-style).
    const ab = await makePdfWithLinks([
      {
        text: "Github link",
        x: 100,
        y: 700,
        rect: [100, 700, 200, 712],
        url: "https://github.com/user/v12-ui",
      },
      {
        text: "Storybook link",
        x: 100,
        y: 720,
        rect: [100, 720, 220, 732],
        url: "https://user.github.io/v12-ui",
      },
      {
        text: "npm link",
        x: 100,
        y: 740,
        rect: [100, 740, 170, 752],
        url: "https://www.npmjs.com/package/v12-ui",
      },
    ]);
    const result = await extractPdfHyperlinks(ab);
    expect(result).toHaveLength(3);
    const urls = result.map((r) => r.url).sort();
    expect(urls).toEqual([
      "https://github.com/user/v12-ui",
      "https://user.github.io/v12-ui",
      "https://www.npmjs.com/package/v12-ui",
    ]);
    // Every label should mention its corresponding text.
    const labels = result.map((r) => r.label).join(" | ");
    expect(labels.toLowerCase()).toContain("github");
    expect(labels.toLowerCase()).toContain("storybook");
    expect(labels.toLowerCase()).toContain("npm");
  });

  it("drops non-http(s) URI links (mailto, javascript, etc.)", async () => {
    const ab = await makePdfWithLinks([
      {
        text: "email",
        x: 100,
        y: 700,
        rect: [100, 700, 150, 712],
        url: "mailto:test@example.com",
      },
      {
        text: "Github",
        x: 100,
        y: 720,
        rect: [100, 720, 170, 732],
        url: "https://github.com/u/v",
      },
    ]);
    const result = await extractPdfHyperlinks(ab);
    expect(result).toHaveLength(1);
    expect(result[0]?.url).toBe("https://github.com/u/v");
  });

  it("returns empty on malformed PDF bytes (does not throw)", async () => {
    const garbage = new TextEncoder().encode("not a pdf at all").buffer;
    const result = await extractPdfHyperlinks(garbage as ArrayBuffer);
    expect(result).toEqual([]);
  });
});
