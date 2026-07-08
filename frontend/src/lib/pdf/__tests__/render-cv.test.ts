// @vitest-environment node
//
// Tests for `renderAdaptedCvAsPdf` — the pdf-lib renderer used by
// the cv/generate route to turn the LLM's `AdaptedCV` JSON into a
// downloadable PDF.
//
// Harvard CV template verification:
//   - Output is a valid PDF (`pdf-lib.PDFDocument.load` succeeds).
//   - At least one page is produced.
//   - The user's name is embedded in the PDF and can be extracted
//     back via `unpdf` (a real round-trip check, not a mock).
//   - Spanish section titles render under yellow highlight
//     rectangles (`PERFIL PROFESIONAL`, `EXPERIENCIA PROFESIONAL`,
//     `EDUCACIÓN`, `PROYECTOS`, `HABILIDADES`, `IDIOMAS`).
//   - Experience descriptions are split on sentence boundaries
//     into bullet points (capped per entry to avoid layout
//     breakage from runaway LLM output).
//   - The LLM's language is preserved verbatim — the renderer
//     emits only Spanish section titles; every other field
//     (`name`, `email`, `phone`, `location`, `summary`, etc.) is
//     rendered exactly as the LLM provided it.
//   - Empty / minimal `AdaptedCV`s still produce a valid PDF
//     (no crashes on missing fields).
//   - Long content triggers pagination across multiple pages
//     (multi-entry overflow, not single-bullet cap).

import { describe, it, expect, vi } from "vitest";
import { PDFDocument, PDFName } from "pdf-lib";
import { extractText, getDocumentProxy } from "unpdf";
import type { AdaptedCV } from "@/lib/llm/prompts";
import { renderAdaptedCvAsPdf, splitDescriptionIntoBullets } from "../render-cv";

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
  certifications: [],
  photo: null,
};

// Spanish CV — exercises the user's typical input shape (the LLM is
// instructed to return Spanish when the original CV was in Spanish).
const SPANISH_CV: AdaptedCV = {
  name: "María García",
  email: "maria@example.es",
  phone: "+34 600 111 222",
  location: "Madrid, España",
  summary:
    "Ingeniera senior con 10 años de experiencia construyendo sistemas distribuidos.",
  experience: [
    {
      company: "NTT DATA",
      title: "Desarrolladora Backend",
      start_date: "2020-01",
      end_date: "Presente",
      description:
        "Lideré la plataforma de pagos. Diseñé la API REST. Mentoré a 4 juniors.",
      location: "Madrid",
    },
  ],
  education: [
    {
      degree: "Ingeniería Informática",
      institution: "Universidad Politécnica de Madrid",
      year: "2016",
      grade: "8.5",
    },
  ],
  projects: [
    {
      name: "V12-UI",
      description: "Librería de componentes React usada en proyectos personales.",
      technologies: ["React", "TypeScript"],
    },
  ],
  skills: ["TypeScript", "React", "Node.js", "PostgreSQL"],
  languages: ["Español", "Inglés"],
  certifications: [],
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

  it("joins email, phone, and location on a single contact line", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("ada@example.com");
    expect(text).toContain("+34 600 000 000");
    expect(text).toContain("Madrid");
  });

  it("renders Spanish section titles (uppercase, matches user reference + Python template)", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    // Harvard layout uses uppercase Spanish section titles. The
    // `drawSectionTitle` helper upcases before drawing, so the PDF
    // text extraction should match the UPPERCASE form.
    expect(text).toContain("PERFIL PROFESIONAL");
    expect(text).toContain("EXPERIENCIA PROFESIONAL");
    expect(text).toContain("EDUCACIÓN");
    expect(text).toContain("PROYECTOS");
    expect(text).toContain("HABILIDADES");
    expect(text).toContain("IDIOMAS");
  });

  it("renders experience content as bullets (split on sentence boundaries)", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    // The description "Led the platform team. Built the realtime
    // pipeline. Mentored 4 juniors." is split on sentence boundaries
    // into three bullets, each preceded by `•`.
    expect(text).toContain("\u2022 Led the platform team.");
    expect(text).toContain("\u2022 Built the realtime pipeline.");
    expect(text).toContain("\u2022 Mentored 4 juniors.");
    // The second experience's description (single sentence) becomes
    // one bullet.
    expect(text).toContain(
      "\u2022 Migrated the monolith to microservices on Kubernetes.",
    );
  });

  it("caps bullet count per entry (defensive against runaway LLM output)", async () => {
    // 200 short sentences → at most MAX_BULLETS_PER_ENTRY (8) bullets.
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
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    // First 8 are rendered.
    expect(text).toContain("Responsibility 1");
    expect(text).toContain("Responsibility 8");
    // Anything past the cap is dropped — the renderer bounds the
    // bullet list to MAX_BULLETS_PER_ENTRY (8) per experience entry.
    expect(text).not.toContain("Responsibility 9");
    expect(text).not.toContain("Responsibility 200");
  });

  it("preserves the LLM's language verbatim (Spanish input stays Spanish)", async () => {
    const bytes = await renderAdaptedCvAsPdf(SPANISH_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    // The renderer must output the LLM-emitted strings unchanged —
    // no translation, no language detection, no hardcoded English.
    expect(text).toContain("María García");
    expect(text).toContain("Ingeniera senior con 10 años");
    expect(text).toContain("NTT DATA");
    expect(text).toContain("Desarrolladora Backend");
    expect(text).toContain("Lideré la plataforma de pagos.");
    expect(text).toContain("Mentoré a 4 juniors.");
    expect(text).toContain("Universidad Politécnica de Madrid");
    expect(text).toContain("Ingeniería Informática");
    expect(text).toContain("Librería de componentes React");
    expect(text).toContain("Español");
    // The skills array is preserved verbatim — the renderer does not
    // reformat, translate, or sort it.
    expect(text).toContain("TypeScript");
    expect(text).toContain("PostgreSQL");
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
      certifications: [],
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

  it("renders sections in Harvard order: Educación before Experiencia before Proyectos", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    const eduIdx = text.indexOf("EDUCACIÓN");
    const expIdx = text.indexOf("EXPERIENCIA PROFESIONAL");
    const projIdx = text.indexOf("PROYECTOS");
    const skillsIdx = text.indexOf("HABILIDADES");
    expect(eduIdx).toBeGreaterThan(-1);
    expect(expIdx).toBeGreaterThan(eduIdx);
    expect(projIdx).toBeGreaterThan(expIdx);
    expect(skillsIdx).toBeGreaterThan(projIdx);
  });

  it("renders a Certificaciones section between Proyectos and Habilidades when certifications are present", async () => {
    // The user's original CV has a 'CERTIFICACIONES Y COMPETENCIAS'
    // section in INFORMACIÓN ADICIONAL. The LLM surfaces those
    // items in the 'certifications' array and the renderer draws
    // a 'Certificaciones' section between 'Proyectos' and
    // 'Habilidades', with each cert as a bullet so the issuer /
    // date suffix is preserved.
    const bytes = await renderAdaptedCvAsPdf({
      ...SPANISH_CV,
      certifications: [
        "Carné de conducir B y vehículo propio.",
        "Ultimate JavaScript - Arturo Alba - 2025-02-09",
        "Java SE Programmer Certification Preparation | NTT DATA / Oracle Training",
      ],
    });
    const pdf = await getDocumentProxy(new Uint8Array(bytes));
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("CERTIFICACIONES");
    expect(text).toContain("Carné de conducir B y vehículo propio.");
    expect(text).toContain("Ultimate JavaScript - Arturo Alba - 2025-02-09");
    expect(text).toContain(
      "Java SE Programmer Certification Preparation | NTT DATA / Oracle Training",
    );
    const projIdx = text.indexOf("PROYECTOS");
    const certIdx = text.indexOf("CERTIFICACIONES");
    const skillsIdx = text.indexOf("HABILIDADES");
    expect(certIdx).toBeGreaterThan(projIdx);
    expect(skillsIdx).toBeGreaterThan(certIdx);
  });

  it("skips the Certifications section entirely when no certifications are present", async () => {
    const bytes = await renderAdaptedCvAsPdf(SPANISH_CV);
    const pdf = await getDocumentProxy(new Uint8Array(bytes));
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).not.toContain("CERTIFICACIONES");
  });

  it("skips the Projects section entirely when no projects are present", async () => {
    const bytes = await renderAdaptedCvAsPdf({
      ...SAMPLE_CV,
      projects: [],
    });
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).not.toContain("PROYECTOS");
    // V12-UI is also a project, so it shouldn't appear.
    expect(text).not.toContain("V12-UI");
  });

  it("renders a project with no technologies without a Tecnologías: line", async () => {
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
    expect(text).not.toContain("Tecnologías:");
  });

  it("does not emit em dashes in section dividers (replaced by commas / en dashes)", async () => {
    const bytes = await renderAdaptedCvAsPdf(SAMPLE_CV);
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    // The renderer uses commas for company/location headers and the
    // en dash (U+2013) for date ranges. Em dashes (U+2014) are
    // forbidden anywhere in the rendered output — both as separators
    // the renderer introduces and as content from the LLM we don't
    // want to echo back unchanged.
    expect(text).not.toMatch(/Globex\s+\u2014/);
    expect(text).not.toMatch(/Globex\s+\u2014\s*Backend/);
    expect(text).not.toContain("\u2014");
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

  it("paginates long content across multiple pages", async () => {
    // The bullet cap (8 per entry) means a single 200-sentence
    // description no longer overflows the first page on its own.
    // To exercise pagination we use 12 experience entries — each
    // with a long description split into a few sentences. Combined,
    // the entries overflow the first page and force a new page.
    const longEntryDescription =
      "Led a cross-functional team through a complex migration. " +
      "Designed and shipped a new realtime pipeline. " +
      "Mentored 4 junior engineers across two quarters.";
    const cv: AdaptedCV = {
      ...SAMPLE_CV,
      summary: "",
      education: [],
      projects: [],
      skills: [],
      languages: [],
      experience: Array.from({ length: 12 }).map((_, i) => ({
        company: `Company ${i + 1}`,
        title: `Title ${i + 1}`,
        start_date: "2020",
        end_date: "Presente",
        description: longEntryDescription,
        location: `City ${i + 1}`,
      })),
    };
    const bytes = await renderAdaptedCvAsPdf(cv);
    const loaded = await PDFDocument.load(bytes);
    expect(loaded.getPageCount()).toBeGreaterThan(1);

    // All the content should still be extractable after pagination —
    // the renderer doesn't truncate, it wraps + overflows.
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("Company 1");
    expect(text).toContain("Company 12");
  });

  it("sanitizes non-WinAnsi characters from the cv object (the '⟶' regression)", async () => {
    // Regression: the LLM was copying special characters verbatim
    // from the original CV (e.g. "⟶" in "Ultimate JavaScript
    // - Arturo Alba - 2025-02-09 ⟶ Más información"). The built-in
    // PDF fonts (Times Roman) use WinAnsi encoding which can't
    // represent those characters — pdf-lib threw WinAnsiError
    // on drawText. The renderer now sanitizes every string field
    // of the cv object before drawing.
    const cv: AdaptedCV = {
      name: "Arturo Alba",
      email: "arturo@example.com",
      phone: "+34 600 000 000",
      location: "Málaga",
      summary: "Desarrollador web \u2014 experiencia en React", // em dash
      experience: [
        {
          company: "NTT DATA \u2013 España", // en dash
          title: "Prácticas",
          start_date: "2026-04",
          end_date: "2026-05",
          description: "Prácticas en NTT DATA. \u201CJava SE\u201D preparación.",
          location: null,
        },
      ],
      education: [],
      projects: [],
      certifications: [
        "Ultimate JavaScript \u27F6 Arturo Alba \u2014 2025-02-09", // ⟶ arrow + em dash
      ],
      skills: ["TypeScript", "React"],
      languages: ["Español"],
      photo: null,
    };

    // The renderer should NOT throw. If the sanitizer isn't
    // applied, pdf-lib would throw a WinAnsiError on the
    // certification bullet containing "⟶" or on the em dash.
    const bytes = await renderAdaptedCvAsPdf(cv);
    expect(bytes.byteLength).toBeGreaterThan(0);

    // Verify the PDF was generated and the sanitized content
    // round-trips. The em dash should be replaced with "-"
    // and the ⟶ should be replaced with "->" (the long arrow
    // is not in WinAnsi and gets replaced with ASCII).
    const pdf = await getDocumentProxy(new Uint8Array(bytes));
    const { text } = await extractText(pdf, { mergePages: true });
    expect(text).toContain("Ultimate JavaScript");
    expect(text).toContain("->"); // ⟶ → ->
    expect(text).toContain("Arturo Alba");
  });

  it("strips leading markdown bullet markers from description bullets", async () => {
    // Regression: the LLM copies the original CV's markdown-like
    // structure verbatim — topic lines prefixed with "* ", and
    // sub-bullets like "Habilidades ganadas: ..." with no
    // marker. When the renderer adds its own "• " bullet
    // character, the topic lines end up as "• * Desarrollo
    // Backend con Java y Spring Boot: ..." and the sub-bullets
    // end up as "• Habilidades ganadas: ...". The asterisk is
    // the only difference between the two — the LLM is using it
    // as a markdown-style bullet marker.
    const cv: AdaptedCV = {
      name: "Arturo",
      email: "a@b.com",
      phone: "+34 600",
      location: "M",
      summary: "",
      experience: [
        {
          company: "NTT DATA",
          title: "Prácticas",
          start_date: "2026-04",
          end_date: "2026-05",
          description:
            "* Desarrollo Backend con Java y Spring Boot: Implementación de servicios RESTful robustos.\n" +
            "Habilidades ganadas: Dominio profundo del ecosistema Spring.\n" +
            "* Calidad de Software (Testing): Creación de suites de pruebas unitarias.\n" +
            "Habilidades ganadas: Mentalidad Testing-First y depuración eficiente.\n" +
            "- Gestión de Datos: Modelado y administración de esquemas en PostgreSQL.\n" +
            "Habilidades ganadas: Optimización de bases de datos relacionales.",
          location: null,
        },
      ],
      education: [],
      projects: [],
      certifications: [],
      skills: [],
      languages: [],
      photo: null,
    };

    const bytes = await renderAdaptedCvAsPdf(cv);
    expect(bytes.byteLength).toBeGreaterThan(0);

    const pdf = await getDocumentProxy(new Uint8Array(bytes));
    const { text } = await extractText(pdf, { mergePages: true });
    // The bullets should NOT have leading "* " or "- " in the
    // rendered text (the renderer adds its own "• ").
    expect(text).not.toMatch(/•\s*\*\s+Desarrollo/);
    expect(text).not.toMatch(/•\s*\*\s+Calidad/);
    expect(text).not.toMatch(/•\s*-\s+Gestión/);
    // But the actual content should still be there.
    expect(text).toContain("Desarrollo Backend con Java y Spring Boot");
    expect(text).toContain("Calidad de Software (Testing)");
    expect(text).toContain("Gestión de Datos");
    expect(text).toContain("Habilidades ganadas");
  });
});

describe("splitDescriptionIntoBullets", () => {
  it("keeps short single-paragraph text as-is (fallback NOT triggered)", () => {
    // GIVEN a short 80-char description with no newlines and no
    // period-space boundaries
    const desc = "Developed features using React and TypeScript";

    // WHEN splitDescriptionIntoBullets processes it
    const bullets = splitDescriptionIntoBullets(desc);

    // THEN the result contains exactly 1 bullet (the original text)
    expect(bullets).toHaveLength(1);
    expect(bullets[0]).toBe(desc);
  });

  it("re-splits long single paragraph with period-space separators into multiple bullets (fallback triggered)", () => {
    // GIVEN a long single-paragraph description (>200 chars) with
    // no \n but with period-space boundaries
    const desc =
      "Led a cross-functional team of 8 engineers through a complex migration from a monolith to microservices architecture using Kubernetes and Docker. " +
      "Designed and shipped a new realtime notification pipeline handling 50k events per second with sub-100ms latency and full fault tolerance. " +
      "Mentored 4 junior engineers across two quarters through structured pair programming sessions, code reviews, and weekly 1-on-1 coaching.";

    expect(desc.length).toBeGreaterThanOrEqual(200);
    expect(desc).not.toContain("\n");

    // WHEN splitDescriptionIntoBullets processes it
    const bullets = splitDescriptionIntoBullets(desc);

    // THEN the result contains ≥2 bullets
    expect(bullets.length).toBeGreaterThanOrEqual(2);
    // AND every bullet is ≥5 characters
    for (const bullet of bullets) {
      expect(bullet.length).toBeGreaterThanOrEqual(5);
    }
  });

  it("leaves text already split by newlines unchanged (no regression)", () => {
    // GIVEN a description already split by \n
    const desc = "• Led the platform team\n• Built the realtime pipeline\n• Mentored 4 juniors";
    const expected = [
      "Led the platform team",
      "Built the realtime pipeline",
      "Mentored 4 juniors",
    ];

    // WHEN splitDescriptionIntoBullets processes it
    const bullets = splitDescriptionIntoBullets(desc);

    // THEN the result matches the expected bullets
    expect(bullets).toEqual(expected);
  });

  it("handles empty description gracefully", () => {
    expect(splitDescriptionIntoBullets("")).toEqual([]);
    expect(splitDescriptionIntoBullets("   ")).toEqual([]);
  });
});
