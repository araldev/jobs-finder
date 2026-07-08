// Tests for POST /api/cv/generate.
//
// The route now returns a real PDF (was JSON in Phase 3). The flow:
//   1. Auth check via Supabase session.
//   2. Multipart form validation (content-type whitelist + 10 MB cap).
//   3. PDF text extraction via `extractPdfText` (`unpdf`).
//   4. LLM call via `chatCompletion` from `@/lib/llm-client`.
//   5. Response parsing via `parseAdaptedCVResponse`.
//   6. PDF rendering via `renderAdaptedCvAsPdf` (`pdf-lib`).
//   7. Engagement event recording in `user_engagement`.
//
// Coverage focus:
//   - 401 when no session.
//   - 400 on missing fields, wrong content-type, oversized file.
//   - 502 when the LLM is unavailable (NO leak of the underlying
//     message per AGENTS.md rule #24).
//   - 422 when the LLM response can't be parsed.
//   - 200 returns a valid PDF (application/pdf, valid bytes,
//     attachment Content-Disposition).
//   - The `user_engagement` insert is called with `event_type =
//     'cv_adapted'` and the job_title / job_company metadata.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockLLMCompletion = vi.fn();

vi.mock("@/lib/llm-client", () => ({
  chatCompletion: (...args: unknown[]) => mockLLMCompletion(...args),
  LLMUnavailableError: class LLMUnavailableError extends Error {},
}));

// Mock the PDF modules so we exercise the route's plumbing rather
// than re-testing the PDF code (covered in `__tests__/extract-text.test.ts`,
// `__tests__/render-cv.test.ts`, and `__tests__/extract-image.test.ts`).
const mockExtractImage = vi.fn();
vi.mock("@/lib/pdf/extract-text", () => ({
  extractPdfText: vi.fn(async (_bytes: ArrayBuffer) => "stub extracted cv text"),
}));

vi.mock("@/lib/pdf/extract-image", () => ({
  extractCvImage: (...args: unknown[]) => mockExtractImage(...args),
}));

vi.mock("@/lib/pdf/render-cv", () => ({
  renderAdaptedCvAsPdf: vi.fn(
    async (_cv: unknown) =>
      new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34]), // "%PDF-1.4"
  ),
}));

// Mock the LLM prompts/parser so we exercise the route's plumbing
// rather than re-testing the prompt/parser (already covered in
// `prompts.test.ts` + `parser.test.ts`).
vi.mock("@/lib/llm/prompts", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/llm/prompts")>(
      "@/lib/llm/prompts",
    );
  return {
    ...actual,
    ADAPT_CV_SYSTEM_PROMPT: "stub-system-prompt",
    buildAdaptCVUserMessage: vi.fn(
      (_cv: string, title: string, company: string, desc: string) =>
        `STUB_USER(title=${title}, company=${company}, desc=${desc})`,
    ),
  };
});

vi.mock("@/lib/llm/parser", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/llm/parser")>(
      "@/lib/llm/parser",
    );
  return {
    ...actual,
    parseAdaptedCVResponse: vi.fn((raw: string) => {
      if (raw === "PARSE_FAIL") {
        throw new actual.AdaptedCVParseError("garbage");
      }
      return {
        name: "Ada Lovelace",
        email: "ada@example.com",
        phone: "+34 600 000 000",
        location: "Madrid",
        summary: "Senior engineer with 10 years experience.",
        experience: [
          {
            company: "Acme",
            title: "Senior Engineer",
            start_date: "2020-01",
            end_date: "2026-01",
            description: "Built systems",
            location: "Madrid",
          },
        ],
        education: [],
        projects: [
          {
            name: "V12-UI",
            description: "React-based component library.",
            technologies: ["React", "TypeScript"],
          },
        ],
        skills: ["TypeScript", "React"],
        languages: ["Spanish", "English"],
        photo: null,
      };
    }),
  };
});

// ── Supabase mock ──────────────────────────────────────────────────────────

interface InsertCall {
  table: string;
  payload: Record<string, unknown>;
}

const mockInsert = vi.fn();
const mockFrom = vi.fn();
const mockAuth = {
  getSession: vi.fn(),
};

const mockSupabase = {
  from: mockFrom,
  auth: mockAuth,
};

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockSupabase,
}));

// ── Helpers ──────────────────────────────────────────────────────────────

function makePdfFile(name = "cv.pdf", content: string | Uint8Array = "fake-pdf-bytes"): File {
  const blobPart: BlobPart[] =
    typeof content === "string" ? [content] : [content as BlobPart];
  const file = new File(blobPart, name, { type: "application/pdf" });
  // jsdom's `File` polyfill does NOT expose `arrayBuffer()` /
  // `text()` — only `name`, `lastModified`, and `constructor`.
  // Real Next.js runs under Node 18+'s native Blob/File, where
  // these methods exist. We polyfill them so the route's
  // `await file.arrayBuffer()` works under vitest/jsdom.
  const bytes: Uint8Array =
    typeof content === "string"
      ? new TextEncoder().encode(content)
      : content;
  (file as unknown as { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer =
    async () =>
      bytes.byteLength === 0
        ? new ArrayBuffer(0)
        : bytes.buffer.slice(
            bytes.byteOffset,
            bytes.byteOffset + bytes.byteLength,
          ) as ArrayBuffer;
  return file;
}

/**
 * Build a Request whose `formData()` works under vitest/jsdom.
 *
 * jsdom's `Request` polyfill does NOT round-trip multipart bodies
 * correctly: `new Request(url, { body: formData })` constructs a
 * Request whose `formData()` throws on read. Real Next.js runs
 * under Node 18+'s native `Request`, where this round-trip works.
 *
 * To exercise the route under vitest without depending on the
 * polyfill behavior, we build a plain Request with a stubbed
 * `formData()` method that returns our FormData verbatim. The
 * content-type header is set to `multipart/form-data` so the
 * route's parser path runs exactly as in production.
 */
function makeFormRequest(fields: Record<string, FormDataEntryValue>): Request {
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    form.append(key, value);
  }
  const req = new Request("http://localhost/api/cv/generate", {
    method: "POST",
    body: new Uint8Array(),
    headers: { "Content-Type": "multipart/form-data; boundary=stub" },
  });
  // Override the broken polyfill `formData()` with a pass-through.
  (req as unknown as { formData: () => Promise<FormData> }).formData =
    async () => form;
  return req;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAuth.getSession.mockResolvedValue({
    data: { session: { user: { id: "user-1" } } },
    error: null,
  });
  // Default: engagement insert succeeds.
  mockInsert.mockResolvedValue({ error: null });
  const insertBuilder = {
    insert: mockInsert,
  };
  mockFrom.mockReturnValue(insertBuilder);
  // Default: no photo extracted from the PDF.
  mockExtractImage.mockResolvedValue(null);
});

// ── Tests ─────────────────────────────────────────────────────────────────

import { POST } from "../route";

describe("POST /api/cv/generate — auth + form validation", () => {
  it("returns 401 when the user is not authenticated", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(401);
    expect(mockLLMCompletion).not.toHaveBeenCalled();
    expect(mockInsert).not.toHaveBeenCalled();
  });

  it("returns 400 when the form body is malformed", async () => {
    const request = new Request("http://localhost/api/cv/generate", {
      method: "POST",
      body: "not-a-multipart-body",
    });
    const res = await POST(request as never);

    expect(res.status).toBe(400);
  });

  it("returns 400 when the file field is missing", async () => {
    const res = await POST(
      makeFormRequest({
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/file/i);
  });

  it("returns 400 when the file content-type is not application/pdf", async () => {
    const txt = new File(["x"], "cv.txt", { type: "text/plain" });
    (txt as unknown as { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer =
      async () => new TextEncoder().encode("x").buffer;
    const res = await POST(
      makeFormRequest({
        file: txt,
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/PDF/i);
  });

  it("returns 400 when job_title is missing", async () => {
    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/job_title/);
  });

  it("returns 400 when job_company is missing", async () => {
    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_title: "Senior Engineer",
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/job_company/);
  });

  it("returns 400 when the file exceeds 10 MB", async () => {
    const oversized = new Uint8Array(11 * 1024 * 1024); // 11 MB
    const file = makePdfFile("big.pdf", oversized);
    const res = await POST(
      makeFormRequest({
        file,
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/10 MB/);
  });

  it("returns 400 when the file is empty", async () => {
    const res = await POST(
      makeFormRequest({
        file: makePdfFile("empty.pdf", ""),
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/vacío/i);
  });
});

describe("POST /api/cv/generate — LLM + engagement flow", () => {
  it("returns 200 with a valid PDF and records the cv_adapted event", async () => {
    mockLLMCompletion.mockResolvedValueOnce(
      JSON.stringify({
        name: "Ada Lovelace",
        experience: [],
        education: [],
        skills: ["TypeScript"],
        languages: ["Spanish"],
      }),
    );

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_title: "Senior Engineer",
        job_company: "Acme",
        job_description: "We need someone who loves TypeScript.",
      }) as never,
    );

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toMatch(/^application\/pdf/);
    expect(res.headers.get("content-disposition")).toBe(
      'attachment; filename="CV-adaptado.pdf"',
    );

    const bytes = new Uint8Array(await res.arrayBuffer());
    expect(bytes.byteLength).toBeGreaterThan(0);
    // The mocked renderer returns "%PDF-1.4" — confirm the body
    // round-trips as binary (no JSON wrapper, no double-encoding).
    expect(String.fromCharCode(bytes[0]!, bytes[1]!, bytes[2]!, bytes[3]!))
      .toBe("%PDF");

    // LLM was called with the system prompt + a user message that
    // includes the job fields (the CV text is what the mocked
    // extractPdfText returned: "stub extracted cv text").
    expect(mockLLMCompletion).toHaveBeenCalledTimes(1);
    const messages = mockLLMCompletion.mock.calls[0]![0] as Array<{
      role: string;
      content: string;
    }>;
    expect(messages[0]?.role).toBe("system");
    expect(messages[0]?.content).toBe("stub-system-prompt");
    expect(messages[1]?.content).toContain("Senior Engineer");
    expect(messages[1]?.content).toContain("Acme");
    // jsonMode was passed so the LLM client requested JSON output.
    // thinking is also disabled so the model emits a direct (non-
    // thinking) response — otherwise MiniMax-M3 burns the entire
    // max_tokens budget on a 'Let me analyze...' preamble and the
    // JSON never lands.
    const opts = mockLLMCompletion.mock.calls[0]![1] as {
      jsonMode: boolean;
      thinking: { type: string };
    };
    expect(opts.jsonMode).toBe(true);
    expect(opts.thinking).toEqual({ type: "disabled" });

    // Engagement event was recorded with the right event_type and metadata.
    expect(mockFrom).toHaveBeenCalledWith("user_engagement");
    expect(mockInsert).toHaveBeenCalledTimes(1);
    const payload = mockInsert.mock.calls[0]![0] as Record<string, unknown>;
    expect(payload.event_type).toBe("cv_adapted");
    expect(payload.job_id).toBeNull();
    expect(payload.metadata).toEqual({
      job_title: "Senior Engineer",
      job_company: "Acme",
    });
  });

  it("returns 502 when the LLM is unavailable (no leak of underlying message)", async () => {
    const { LLMUnavailableError } = await import("@/lib/llm-client");
    mockLLMCompletion.mockRejectedValueOnce(
      new LLMUnavailableError(
        "fetch failed: getaddrinfo ENOTFOUND api.minimax.io super-secret-key",
      ),
    );

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("LLM provider unavailable");
    // No hostnames / DNS errors / API keys may leak to the client.
    expect(body.error).not.toContain("api.minimax.io");
    expect(body.error).not.toContain("super-secret-key");
    expect(body.error).not.toContain("getaddrinfo");

    // The engagement event MUST NOT be recorded when the LLM call
    // failed (no CV was generated).
    expect(mockInsert).not.toHaveBeenCalled();
  });

  it("returns 422 when the LLM response can't be parsed", async () => {
    mockLLMCompletion.mockResolvedValueOnce("PARSE_FAIL");

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(422);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/adaptar/i);
    // The raw LLM response / parse error must not leak.
    expect(body.error).not.toContain("PARSE_FAIL");
    expect(body.error).not.toContain("garbage");

    // The engagement event MUST NOT be recorded when parsing failed.
    expect(mockInsert).not.toHaveBeenCalled();
  });

  it("returns 200 even when engagement-event recording fails (best-effort)", async () => {
    mockLLMCompletion.mockResolvedValueOnce(
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }),
    );
    mockInsert.mockResolvedValueOnce({
      error: { message: "RLS violation" },
    });

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    // The CV was generated — don't fail the user because the
    // engagement event couldn't be recorded.
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toMatch(/^application\/pdf/);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });

  it("calls extractCvImage and forwards the photo data URL to the renderer", async () => {
    mockLLMCompletion.mockResolvedValueOnce(
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }),
    );

    const dataUrl = "data:image/jpeg;base64,/9j/4AAQ-test-photo";
    mockExtractImage.mockResolvedValueOnce(dataUrl);

    const { renderAdaptedCvAsPdf } = await import("@/lib/pdf/render-cv");
    const renderMock = renderAdaptedCvAsPdf as unknown as ReturnType<
      typeof vi.fn
    >;

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(200);
    // extractCvImage was called once with the PDF bytes.
    expect(mockExtractImage).toHaveBeenCalledTimes(1);
    // The renderer received the data URL as `cv.photo` (overlaid
    // by the route after parsing the LLM response).
    expect(renderMock).toHaveBeenCalledTimes(1);
    const cvArg = renderMock.mock.calls[0]![0] as { photo: string | null };
    expect(cvArg.photo).toBe(dataUrl);
  });

  it("forwards photo: null to the renderer when no image is found in the PDF", async () => {
    mockLLMCompletion.mockResolvedValueOnce(
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }),
    );
    // mockExtractImage returns null by default (beforeEach).
    const { renderAdaptedCvAsPdf } = await import("@/lib/pdf/render-cv");
    const renderMock = renderAdaptedCvAsPdf as unknown as ReturnType<
      typeof vi.fn
    >;

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(200);
    const cvArg = renderMock.mock.calls[0]![0] as { photo: string | null };
    expect(cvArg.photo).toBeNull();
  });
});