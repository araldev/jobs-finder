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
import { PDFDocument } from "pdf-lib";
import { extractText, getDocumentProxy } from "unpdf";
import type { AdaptedCV } from "@/lib/llm/prompts";
import { renderAdaptedCvAsPdf } from "../render-cv";

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
  skills: ["TypeScript", "React", "Node.js", "PostgreSQL", "Kubernetes"],
  languages: ["Spanish", "English"],
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
      skills: [],
      languages: [],
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
      skills: [],
      languages: [],
    });
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