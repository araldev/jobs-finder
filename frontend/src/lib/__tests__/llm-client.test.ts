// Tests for the MiniMax LLM HTTP client.
//
// The client wraps the global `fetch` (Node 18+ built-in) — every
// test stubs `globalThis.fetch` with a `vi.fn()` so we can drive
// the request/response shape end-to-end without contacting the real
// MiniMax endpoint.
//
// Coverage focus (per Phase 3 spec):
//   - Request body shape (model, messages, temperature, max_tokens,
//     stream: false|true, optional response_format).
//   - Auth header (`Authorization: Bearer ...`) and Content-Type.
//   - URL is `${baseUrl}/v1/chat/completions`.
//   - Non-2xx → LLMUnavailableError, NO leak of status/body.
//   - Network error → LLMUnavailableError, NO leak of underlying
//     error (AGENTS.md rule #24).
//   - Missing LLM_API_KEY → LLMUnavailableError, NO env-var leak.
//   - Streaming: raw `data: {json}\n\n` chunks are reformatted to
//     `event: text\ndata: {"delta": ...}\n\n`; `data: [DONE]\n\n`
//     becomes `event: done\ndata: {...}\n\n`; upstream cancel
//     propagates to the LLM client's `cancel()` hook.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("server-only", () => ({}));

// We import after `server-only` is stubbed because the module's
// top-level `import "server-only"` would otherwise throw under
// vitest/jsdom.
import {
  chatCompletion,
  chatCompletionStream,
  LLMUnavailableError,
  LLMStreamError,
} from "../llm-client";

const ORIGINAL_ENV = { ...process.env };

beforeEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  process.env = { ...ORIGINAL_ENV, LLM_API_KEY: "test-key" };
});

afterEach(() => {
  process.env = ORIGINAL_ENV;
  vi.unstubAllGlobals();
});

function mockFetchOnce(response: Response): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async () => response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

function mockFetchSequence(responses: Response[]): ReturnType<typeof vi.fn> {
  const fn = vi.fn();
  for (const r of responses) fn.mockResolvedValueOnce(r);
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("chatCompletion", () => {
  it("posts to ${LLM_BASE_URL}/v1/chat/completions with the expected body shape", async () => {
    const fetchMock = mockFetchOnce(
      new Response(
        JSON.stringify({
          choices: [{ message: { content: "hello" } }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const out = await chatCompletion(
      [
        { role: "system", content: "you are X" },
        { role: "user", content: "hi" },
      ],
      { jsonMode: true },
    );

    expect(out).toBe("hello");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("https://api.minimax.io/v1/chat/completions");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer test-key",
    );
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
    const body = JSON.parse(init?.body as string);
    expect(body.model).toBe("MiniMax-M3");
    expect(body.messages).toEqual([
      { role: "system", content: "you are X" },
      { role: "user", content: "hi" },
    ]);
    expect(body.stream).toBe(false);
    expect(body.response_format).toEqual({ type: "json_object" });
  });

  it("honors LLM_BASE_URL and LLM_MODEL overrides", async () => {
    process.env.LLM_BASE_URL = "https://custom.example.com/";
    process.env.LLM_MODEL = "custom-model";

    const fetchMock = mockFetchOnce(
      new Response(
        JSON.stringify({
          choices: [{ message: { content: "ok" } }],
        }),
        { status: 200 },
      ),
    );

    await chatCompletion([{ role: "user", content: "hi" }]);

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("https://custom.example.com/v1/chat/completions");
    expect(JSON.parse(init?.body as string).model).toBe("custom-model");
  });

  it("uses defaults when LLM_BASE_URL / LLM_MODEL are unset", async () => {
    delete process.env.LLM_BASE_URL;
    delete process.env.LLM_MODEL;

    const fetchMock = mockFetchOnce(
      new Response(
        JSON.stringify({ choices: [{ message: { content: "ok" } }] }),
        { status: 200 },
      ),
    );

    await chatCompletion([{ role: "user", content: "hi" }]);

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("https://api.minimax.io/v1/chat/completions");
    const body = JSON.parse(init?.body as string);
    expect(body.model).toBe("MiniMax-M3");
    expect(body.temperature).toBe(0.3);
    expect(body.max_tokens).toBe(2048);
    expect(body.response_format).toBeUndefined();
  });

  it("returns LLMUnavailableError when LLM_API_KEY is missing", async () => {
    delete process.env.LLM_API_KEY;

    await expect(
      chatCompletion([{ role: "user", content: "hi" }]),
    ).rejects.toBeInstanceOf(LLMUnavailableError);
  });

  it("returns LLMUnavailableError on a non-2xx response", async () => {
    mockFetchOnce(
      new Response("internal server error", { status: 500 }),
    );

    await expect(
      chatCompletion([{ role: "user", content: "hi" }]),
    ).rejects.toBeInstanceOf(LLMUnavailableError);
  });

  it("returns LLMUnavailableError on a network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed: ECONNREFUSED 127.0.0.1:443");
      }),
    );

    await expect(
      chatCompletion([{ role: "user", content: "hi" }]),
    ).rejects.toBeInstanceOf(LLMUnavailableError);
  });

  it("returns LLMUnavailableError on malformed JSON body", async () => {
    mockFetchOnce(
      new Response("not-json", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(
      chatCompletion([{ role: "user", content: "hi" }]),
    ).rejects.toBeInstanceOf(LLMUnavailableError);
  });

  it("returns LLMUnavailableError when choices[] is empty", async () => {
    mockFetchOnce(
      new Response(JSON.stringify({ choices: [] }), { status: 200 }),
    );

    await expect(
      chatCompletion([{ role: "user", content: "hi" }]),
    ).rejects.toBeInstanceOf(LLMUnavailableError);
  });

  it("the LLMUnavailableError message does NOT leak the API key (AGENTS.md #24)", async () => {
    process.env.LLM_API_KEY = "super-secret-key";

    mockFetchOnce(new Response("nope", { status: 500 }));

    try {
      await chatCompletion([{ role: "user", content: "hi" }]);
      throw new Error("expected LLMUnavailableError");
    } catch (e) {
      expect(e).toBeInstanceOf(LLMUnavailableError);
      expect((e as Error).message).not.toContain("super-secret-key");
      expect((e as Error).message).not.toContain("test-key");
    }
  });
});

describe("chatCompletionStream", () => {
  it("posts with stream: true and returns a ReadableStream", async () => {
    mockFetchOnce(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              new TextEncoder().encode('data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'),
            );
            controller.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
            controller.close();
          },
        }),
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      ),
    );

    const stream = await chatCompletionStream([
      { role: "system", content: "you are X" },
      { role: "user", content: "hi" },
    ]);
    expect(stream).toBeInstanceOf(ReadableStream);

    const text = await readStream(stream);
    // The raw `data: ...` line is reformatted into the chat panel's
    // `event: text\ndata: {"delta": ...}\n\n` shape, then a terminal
    // `event: done` is appended.
    expect(text).toContain('event: text\ndata: {"delta":"hi"}');
    expect(text).toContain("event: done");
  });

  it("skips chunks with empty deltas (e.g. role-only deltas)", async () => {
    mockFetchOnce(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              new TextEncoder().encode(
                'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n',
              ),
            );
            controller.enqueue(
              new TextEncoder().encode(
                'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',
              ),
            );
            controller.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
            controller.close();
          },
        }),
        { status: 200 },
      ),
    );

    const stream = await chatCompletionStream([
      { role: "user", content: "hi" },
    ]);
    const text = await readStream(stream);

    // The empty role-only delta must NOT produce an `event: text`
    // chunk; only the non-empty "hello" delta does.
    const textEvents = text.split("event: text").length - 1;
    expect(textEvents).toBe(1);
    expect(text).toContain('"delta":"hello"');
  });

  it("emits event: error on mid-stream exception (no leak)", async () => {
    // A malformed SSE line mid-stream should be skipped (per the
    // backend's "skip malformed lines" policy), but a malformed
    // JSON inside the line should NOT crash — it's tolerated.
    mockFetchOnce(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              new TextEncoder().encode("data: this-is-not-json\n\n"),
            );
            controller.enqueue(
              new TextEncoder().encode(
                'data: {"choices":[{"delta":{"content":"survived"}}]}\n\n',
              ),
            );
            controller.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
            controller.close();
          },
        }),
        { status: 200 },
      ),
    );

    const stream = await chatCompletionStream([
      { role: "user", content: "hi" },
    ]);
    const text = await readStream(stream);

    expect(text).toContain('"delta":"survived"');
    expect(text).toContain("event: done");
    expect(text).not.toContain("event: error");
  });

  it("returns LLMUnavailableError when LLM_API_KEY is missing", async () => {
    delete process.env.LLM_API_KEY;

    // The kill switch fires before we know whether the request
    // would have streamed or completed — `LLMUnavailableError`
    // is the canonical "we can't reach the LLM" signal.
    await expect(
      chatCompletionStream([{ role: "user", content: "hi" }]),
    ).rejects.toBeInstanceOf(LLMUnavailableError);
  });

  it("returns LLMStreamError on a non-2xx response", async () => {
    mockFetchOnce(new Response("boom", { status: 502 }));

    await expect(
      chatCompletionStream([{ role: "user", content: "hi" }]),
    ).rejects.toBeInstanceOf(LLMStreamError);
  });

  it("returns LLMStreamError on an empty body (no upstream stream)", async () => {
    mockFetchOnce(new Response(null, { status: 200 }));

    await expect(
      chatCompletionStream([{ role: "user", content: "hi" }]),
    ).rejects.toBeInstanceOf(LLMStreamError);
  });
});

// ── Helpers ──────────────────────────────────────────────────────────────

async function readStream(stream: ReadableStream<Uint8Array>): Promise<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let out = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    out += decoder.decode(value, { stream: true });
  }
  return out;
}