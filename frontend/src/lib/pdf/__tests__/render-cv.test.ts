// Tests for `renderAdaptedCvAsPdf` — the pdf-lib renderer used by
// the cv/generate route to turn the LLM's `AdaptedCV` JSON into a
// downloadable PDF.
//
// Verifies:
//   - The output is a valid PDF (`pdf-lib.PDFDocument.load` succeeds).
//   - At least one page is produced.
//   - The user's name is embedded in the PDF and can be extracted
//     back via `unpdf` (a real round-trip check, not a mock).
//   - Empty / minimal `AdaptedCV`s still produce a valid PDF
//     (no crashes on missing fields).
//   - Very long descriptions get wrapped and paginated correctly
//     (multiple pages, all content extracted).

import { describe, it, expect, vi } from "vitest";
import { PDFDocument, PDFName } from "pdf-lib";
import { extractText, getDocumentProxy } from "unpdf";
import type { AdaptedCV } from "@/lib/llm/prompts";
import { renderAdaptedCvAsPdf } from "../render-cv";

// Build a synthetic JPEG byte array that satisfies pdf-lib's
// `embedJpg` header check (FF D8 + valid SOF0 marker). Mirrors the
// fixture in `extract-image.test.ts` — kept local to this file so
// the two tests stay independently readable.
function buildSyntheticJpeg(targetSize: number): Uint8Array {
  const bytes = new Uint8Array(targetSize);
  bytes[0] = 0xff;
  bytes[1] = 0xd8;
  bytes[2] = 0xff;
  bytes[3] = 0xe0;
  const app0Len = 16;
  bytes[4] = (app0Len >> 8) & 0xff;
  bytes[5] = app0Len & 0xff;
  bytes[6] = 0x4a;
  bytes[7] = 0x46;
  bytes[8] = 0x49;
  bytes[9] = 0x46;
  bytes[10] = 0x00;
  bytes[11] = 0x01;
  bytes[12] = 0x01;
  bytes[13] = 0x00;
  bytes[14] = 0x00;
  bytes[15] = 0x01;
  bytes[16] = 0x00;
  bytes[17] = 0x01;
  bytes[18] = 0x00;
  bytes[19] = 0x00;
  bytes[20] = 0xff;
  bytes[21] = 0xc0;
  const sofLen = 11;
  bytes[22] = (sofLen >> 8) & 0xff;
  bytes[23] = sofLen & 0xff;
  bytes[24] = 0x08;
  bytes[25] = 0x00;
  bytes[26] = 0x40;
  bytes[27] = 0x00;
  bytes[28] = 0x40;
  bytes[29] = 0x03;
  for (let i = 30; i < targetSize - 2; i += 2) {
    bytes[i] = 0xff;
    bytes[i + 1] = 0xfe;
  }
  bytes[targetSize - 2] = 0xff;
  bytes[targetSize - 1] = 0xd9;
  return bytes;
}

function bytesToBase64(bytes: Uint8Array): string {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(bytes).toString("base64");
  }
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.byteLength; i += chunk) {
    binary += String.fromCharCode(
      ...bytes.subarray(i, Math.min(i + chunk, bytes.byteLength)),
    );
  }
  return btoa(binary);
}

// `server-only` is an empty module that throws if imported from a
// Client Component. The renderer's `import "server-only"` would
// otherwise block vitest's jsdom environment. The function itself
// has no side effects — no need to actually run it on the server in
// the test process.
vi.mock("server-only", () => ({}));

const SAMPLE_CV: AdaptedCV = {
  name: "Ada Lovelace",
  email: "ada@example.com",
  phone: "+34 600 000 000",
  location: "Madrid, Spain",
  summary:
    "Senior engineer with 10 years of experience building distributed systems.",
  experience: [
    {
      company: "Acme",
      title: "Senior Engineer",
      start_date: "2020-01",
      end_date: "Presente",
      description:
        "Led the platform team. Built the realtime pipeline. Mentored 4 juniors.",
      location: "Madrid",
    },
    {
      company: "Globex",
      title: "Backend Developer",
      start_date: "2017-06",
      end_date: "2019-12",
      description:
        "Migrated the monolith to microservices on Kubernetes.",
      location: "Barcelona",
    },
  ],
  education: [
    {
      degree: "MSc Computer Science",
      institution: "Universidad Politécnica de Madrid",
      year: "2016",
      grade: "9.0",
    },
  ],
  projects: [
    {
      name: "V12-UI",
      description:
        "React-based component library used in side projects.",
      technologies: ["React", "TypeScript"],
    },
    {
      name: "PORTFOLIO",
      description: "Personal website with blog and project showcase.",
      technologies: ["Next.js"],
    },
  ],
  skills: ["TypeScript", "React", "Node.js", "PostgreSQL", "Kubernetes"],
  languages: ["Spanish", "English"],
  photo: null,
};

describe("renderAdaptedCvAsPdf", () => {
  it("produces a valid PDF with at least one page", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    expect(bytes.byteLength).toBeGreaterThan(0);

    // %PDF- header magic confirms it's a real PDF, not JSON-wrapped.
    expect(String.fromCharCode(bytes[0]!, bytes[1]!, bytes[2]!, bytes[3]!))
      .toBe("%PDF");

    const loaded = await PDFDocument.load(bytes);
    expect(loaded.getPageCount()).toBeGreaterThanOrEqual(1);
  });

  it("embeds the user's name in the PDF (extractable round-trip)", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("Ada Lovelace");
  });

  it("includes email, phone, and location in the header", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("ada@example.com");
    expect(text).toContain("+34 600 000 000");
    expect(text).toContain("Madrid");
  });

  it("includes section headings and content for experience, education, skills, languages", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });

    expect(text).toContain("Summary");
    expect(text).toContain("Experience");
    expect(text).toContain("Acme");
    expect(text).toContain("Senior Engineer");
    expect(text).toContain("Education");
    expect(text).toContain("Universidad Politécnica de Madrid");
    expect(text).toContain("Skills");
    expect(text).toContain("TypeScript");
    expect(text).toContain("Languages");
    expect(text).toContain("Spanish");
  });

  it("renders an empty CV without crashing (no fields = no content lines)", async () => {
    const empty: AdaptedCV = {
      name: "",
      email: "",
      phone: "",
      location: "",
      summary: "",
      experience: [],
      education: [],
      projects: [],
      skills: [],
      languages: [],
      photo: null,
    };
    const bytes = await renderAdaptedCvAsPdf(empty);
    const loaded = await PDFDocument.load(bytes);
    expect(loaded.getPageCount()).toBeGreaterThanOrEqual(1);
  });

  it("renders a minimal CV with just a name", async () => {
    const bytes = await renderAdaptedCvAsPdf({
      ...SAMPLE_CV,
      email: "",
      phone: "",
      location: "",
      summary: "",
      experience: [],
      education: [],
      projects: [],
      skills: [],
      languages: [],
    });
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("Ada Lovelace");
  });

  it("renders a Projects section between Experience and Skills (Harvard order)", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });

    expect(text).toContain("Projects");
    expect(text).toContain("V12-UI");
    expect(text).toContain("PORTFOLIO");
    expect(text).toContain("Technologies:");
    expect(text).toContain("React");
    expect(text).toContain("Next.js");
    // Harvard ordering: Education appears before Experience in the PDF.
    const eduIdx = text.indexOf("Education");
    const expIdx = text.indexOf("Experience");
    const projIdx = text.indexOf("Projects");
    expect(eduIdx).toBeGreaterThan(-1);
    expect(expIdx).toBeGreaterThan(eduIdx);
    expect(projIdx).toBeGreaterThan(expIdx);
  });

  it("skips the Projects section entirely when no projects are present", async () => {
    const bytes = await renderAdaptedCvAsPdf({
      ...SAMPLE_CV,
      projects: [],
    });
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).not.toContain("Projects");
    // V12-UI is also a project, so it shouldn't appear.
    expect(text).not.toContain("V12-UI");
  });

  it("renders a project with no technologies without a Technologies: line", async () => {
    const bytes = await renderAdaptedCvAsPdf({
      ...SAMPLE_CV,
      projects: [
        {
          name: "MyNakedProject",
          description: "Description only.",
          technologies: [],
        },
      ],
    });
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("MyNakedProject");
    expect(text).toContain("Description only.");
    expect(text).not.toContain("Technologies:");
  });

  it("does not emit em dashes in section dividers (replaced by commas)", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    // The renderer uses commas for company/title/education headers;
    // em dashes only appear inside the user's text content (e.g. the
    // SAMPLE_CV description doesn't have any, but a future LLM might
    // — what we GUARANTEE here is that the renderer never introduces
    // em dashes itself).
    expect(text).not.toContain("Globex \u2014");
    expect(text).not.toContain("Globex —");
  });

  it("embeds the photo as an image XObject when provided (Harvard header layout)", async () => {
    // Build a JPEG that satisfies the 10 KB threshold we use
    // elsewhere (pdf-lib's `embedJpg` only inspects the header +
    // SOF marker — see extract-image.test.ts for the format).
    const jpeg = buildSyntheticJpeg(12_000);
    const photoDataUrl =
      "data:image/jpeg;base64," + bytesToBase64(jpeg);

    const cv: AdaptedCV = { ...SAMPLE_CV, photo: photoDataUrl };
    const bytes = await renderAdaptedCvAsPdf(cv);

    const loaded = await PDFDocument.load(bytes);
    const firstPage = loaded.getPages()[0]!;
    const xobjects = firstPage.node
      .Resources()
      ?.get(PDFName.of("XObject"));
    // The header photo is rendered via `page.drawImage`, which
    // pdf-lib stores as an XObject on the page's Resources. We
    // assert at least one image XObject is present (the photo).
    expect(xobjects).toBeDefined();
    const entries = (
      xobjects as unknown as { entries(): Iterable<[unknown, unknown]> }
    ).entries();
    const xObjectEntries = Array.from(entries);
    expect(xObjectEntries.length).toBeGreaterThan(0);

    // Confirm the name appears in the body text (header text
    // flows on the left of the photo).
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("Ada Lovelace");
  });

  it("does NOT embed a photo when photo is null (no XObjects in Resources)", async () => {
    const bytes = await renderAdaptedCvAsPdf({ ...SAMPLE_CV, photo: null });
    const loaded = await PDFDocument.load(bytes);
    const firstPage = loaded.getPages()[0]!;
    const xobjects = firstPage.node
      .Resources()
      ?.get(PDFName.of("XObject"));
    // No photo → no image XObjects on the first page. (Font +
    // graphics state are still there but no XObject entry.)
    if (xobjects) {
      const entries = Array.from(
        (
          xobjects as unknown as { entries(): Iterable<[unknown, unknown]> }
        ).entries(),
      );
      expect(entries).toHaveLength(0);
    }
  });

  it("treats a malformed photo string as no photo (does not throw)", async () => {
    // Defensive: the route handler always passes a real data URL,
    // but a future caller could pass garbage. The renderer must
    // skip the image gracefully (no crash, no garbage bytes in
    // the PDF).
    const cv: AdaptedCV = {
      ...SAMPLE_CV,
      photo: "data:image/jpeg;base64,!!!not-base64!!!",
    };
    const bytes = await renderAdaptedCvAsPdf(cv);
    const loaded = await PDFDocument.load(bytes);
    expect(loaded.getPageCount()).toBeGreaterThanOrEqual(1);

    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("Ada Lovelace");
  });

  it("paginates long descriptions across multiple pages", async () => {
    // Build a CV with one very long experience description so the
    // renderer is forced to overflow the first page.
    const longDescription = Array.from({ length: 200 })
      .map((_, i) => `Responsibility ${i + 1}`)
      .join(". ");
    const cv: AdaptedCV = {
      ...SAMPLE_CV,
      experience: [
        {
          company: "Verbose Co",
          title: "Overloaded Engineer",
          start_date: "2020",
          end_date: "Presente",
          description: longDescription,
          location: null,
        },
      ],
    };
    const bytes = await renderAdaptedCvAsPdf(cv);
    const loaded = await PDFDocument.load(bytes);
    expect(loaded.getPageCount()).toBeGreaterThan(1);

    // All the responsibilities should still be extractable after
    // pagination — the renderer doesn't truncate, it wraps + overflows.
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("Responsibility 1");
    expect(text).toContain("Responsibility 200");
  });
});