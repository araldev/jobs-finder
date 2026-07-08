// Tests for POST /api/cv/generate-custom.
//
// The route extends the `/api/cv/generate` flow by accepting a
// job URL or free-text description instead of requiring a database
// job record. The tests cover:
//   1. Auth check (401).
//   2. Missing file (400).
//   3. Missing URL AND description (400).
//   4. URL fetch failure (422).
//   5. Description overrides URL when both are provided.
//   6. Successful end-to-end flow (200 + valid PDF + engagement).
//   7. LLM / parse / render errors (502, 422, 500).

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockLLMCompletion = vi.fn();

vi.mock("@/lib/llm-client", () => ({
  chatCompletion: (...args: unknown[]) => mockLLMCompletion(...args),
  LLMUnavailableError: class LLMUnavailableError extends Error {},
}));

// Mock the PDF modules
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
      new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34]),
  ),
}));

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

// Mock url-fetch
const mockFetchUrlContent = vi.fn();
vi.mock("@/lib/url-fetch", () => ({
  fetchUrlContent: (...args: unknown[]) => mockFetchUrlContent(...args),
}));

// ── Supabase mock ──────────────────────────────────────────────────────────

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

function makeFormRequest(fields: Record<string, FormDataEntryValue>): Request {
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    form.append(key, value);
  }
  const req = new Request("http://localhost/api/cv/generate-custom", {
    method: "POST",
    body: new Uint8Array(),
    headers: { "Content-Type": "multipart/form-data; boundary=stub" },
  });
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
  const insertBuilder = { insert: mockInsert };
  mockFrom.mockReturnValue(insertBuilder);
  // Default: no photo extracted.
  mockExtractImage.mockResolvedValue(null);
  // Default: URL fetch succeeds (unused in most tests).
  mockFetchUrlContent.mockResolvedValue({
    title: "Senior Engineer at Acme",
    textContent: "We are looking for a senior engineer with TypeScript experience.",
    success: true,
  });
});

import { POST } from "../route";

describe("POST /api/cv/generate-custom — auth + validation", () => {
  it("returns 401 when the user is not authenticated", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_description: "Senior engineer needed",
      }) as never,
    );

    expect(res.status).toBe(401);
    expect(mockLLMCompletion).not.toHaveBeenCalled();
  });

  it("returns 400 when the file field is missing", async () => {
    const res = await POST(
      makeFormRequest({
        job_description: "Senior engineer needed",
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/CV/);
  });

  it("returns 400 when neither URL nor description is provided", async () => {
    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/URL|descripción/i);
  });

  it("returns 400 when both URL and description are empty strings", async () => {
    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_url: "",
        job_description: "",
      }) as never,
    );

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/URL|descripción/i);
  });

  it("returns 422 when URL fetch fails", async () => {
    mockFetchUrlContent.mockResolvedValueOnce({
      title: null,
      textContent: "",
      success: false,
    });

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_url: "https://example.com/broken-offer",
      }) as never,
    );

    expect(res.status).toBe(422);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/URL/);
    // The internal fetch error must not leak (AGENTS.md rule #24).
    expect(body.error).not.toContain("broken-offer");
    expect(mockLLMCompletion).not.toHaveBeenCalled();
  });
});

describe("POST /api/cv/generate-custom — URL vs description resolution", () => {
  it("fetches URL content when only job_url is provided", async () => {
    mockLLMCompletion.mockResolvedValueOnce(
      JSON.stringify({
        name: "Ada Lovelace",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }),
    );

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_url: "https://linkedin.com/jobs/123",
      }) as never,
    );

    expect(res.status).toBe(200);
    // Verify the URL was fetched
    expect(mockFetchUrlContent).toHaveBeenCalledWith("https://linkedin.com/jobs/123");
    // Verify the LLM received the fetched content as the description
    const { buildAdaptCVUserMessage } = await import("@/lib/llm/prompts");
    expect(buildAdaptCVUserMessage).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      "We are looking for a senior engineer with TypeScript experience.",
    );
  });

  it("uses job_description over URL content when both are provided", async () => {
    mockLLMCompletion.mockResolvedValueOnce(
      JSON.stringify({
        name: "Ada Lovelace",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }),
    );

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_url: "https://linkedin.com/jobs/123",
        job_description: "Custom user-written description",
      }) as never,
    );

    expect(res.status).toBe(200);
    // URL should NOT have been fetched
    expect(mockFetchUrlContent).not.toHaveBeenCalled();
    // The LLM received the user's description
    const { buildAdaptCVUserMessage } = await import("@/lib/llm/prompts");
    expect(buildAdaptCVUserMessage).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      "Custom user-written description",
    );
  });

  it("uses job_description directly when no URL is provided", async () => {
    mockLLMCompletion.mockResolvedValueOnce(
      JSON.stringify({
        name: "Ada Lovelace",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }),
    );

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_description: "Direct description text",
      }) as never,
    );

    expect(res.status).toBe(200);
    expect(mockFetchUrlContent).not.toHaveBeenCalled();
    const { buildAdaptCVUserMessage } = await import("@/lib/llm/prompts");
    expect(buildAdaptCVUserMessage).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      "Direct description text",
    );
  });
});

describe("POST /api/cv/generate-custom — LLM + engagement flow", () => {
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
        job_url: "https://linkedin.com/jobs/123",
        job_title: "Senior Engineer",
        job_company: "Acme",
      }) as never,
    );

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toMatch(/^application\/pdf/);
    expect(res.headers.get("content-disposition")).toBe(
      'attachment; filename="CV-adaptado.pdf"',
    );

    const bytes = new Uint8Array(await res.arrayBuffer());
    expect(bytes.byteLength).toBeGreaterThan(0);
    expect(String.fromCharCode(bytes[0]!, bytes[1]!, bytes[2]!, bytes[3]!))
      .toBe("%PDF");

    // LLM was called with the system prompt + a user message that
    // includes the job fields.
    expect(mockLLMCompletion).toHaveBeenCalledTimes(1);
    const messages = mockLLMCompletion.mock.calls[0]![0] as Array<{
      role: string;
      content: string;
    }>;
    expect(messages[0]?.role).toBe("system");
    expect(messages[0]?.content).toBe("stub-system-prompt");

    const opts = mockLLMCompletion.mock.calls[0]![1] as { jsonMode: boolean };
    expect(opts.jsonMode).toBe(true);

    // Engagement event was recorded with metadata including job_url.
    expect(mockFrom).toHaveBeenCalledWith("user_engagement");
    expect(mockInsert).toHaveBeenCalledTimes(1);
    const payload = mockInsert.mock.calls[0]![0] as Record<string, unknown>;
    expect(payload.event_type).toBe("cv_adapted");
    expect(payload.job_id).toBeNull();
    expect(payload.metadata).toEqual({
      job_title: "Senior Engineer",
      job_company: "Acme",
      job_url: "https://linkedin.com/jobs/123",
    });
  });

  it("returns 502 when the LLM is unavailable (no leak of underlying message)", async () => {
    const { LLMUnavailableError } = await import("@/lib/llm-client");
    mockLLMCompletion.mockRejectedValueOnce(
      new LLMUnavailableError("fetch failed: ENOTFOUND api.minimax.io secret-key"),
    );

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_description: "Senior engineer needed",
      }) as never,
    );

    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("LLM provider unavailable");
    expect(body.error).not.toContain("api.minimax.io");
    expect(body.error).not.toContain("secret-key");
    expect(mockInsert).not.toHaveBeenCalled();
  });

  it("returns 422 when the LLM response can't be parsed", async () => {
    mockLLMCompletion.mockResolvedValueOnce("PARSE_FAIL");

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_description: "Senior engineer needed",
      }) as never,
    );

    expect(res.status).toBe(422);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/adaptar/i);
    expect(body.error).not.toContain("PARSE_FAIL");
    expect(mockInsert).not.toHaveBeenCalled();
  });

  it("returns 500 when PDF rendering fails", async () => {
    mockLLMCompletion.mockResolvedValueOnce(
      JSON.stringify({
        name: "Ada",
        experience: [],
        education: [],
        skills: [],
        languages: [],
      }),
    );
    const { renderAdaptedCvAsPdf } = await import("@/lib/pdf/render-cv");
    (renderAdaptedCvAsPdf as unknown as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error("pdf-lib internal error"));

    const res = await POST(
      makeFormRequest({
        file: makePdfFile(),
        job_description: "Senior engineer needed",
      }) as never,
    );

    expect(res.status).toBe(500);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/PDF/);
    // Internal details must not leak
    expect(body.error).not.toContain("pdf-lib");
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
        job_url: "https://linkedin.com/jobs/123",
      }) as never,
    );

    expect(res.status).toBe(200);
    expect(mockInsert).toHaveBeenCalledTimes(1);
  });

  it("forwards photo from extractCvImage to the renderer", async () => {
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
        job_description: "Senior engineer needed",
      }) as never,
    );

    expect(res.status).toBe(200);
    expect(renderMock).toHaveBeenCalledTimes(1);
    const cvArg = renderMock.mock.calls[0]![0] as { photo: string | null };
    expect(cvArg.photo).toBe(dataUrl);
  });
});
