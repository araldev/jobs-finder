import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("server-only", () => ({}));

// Mock the LLM client BEFORE importing the route. The route now
// uses `chatCompletionStream` from `@/lib/llm-client` directly —
// the previous Python backend proxy is gone.
const mockStream = vi.fn();

vi.mock("@/lib/llm-client", () => ({
  chatCompletionStream: (...args: unknown[]) => mockStream(...args),
  // The route catches errors via the `LLMStreamError` and
  // `LLMUnavailableError` instanceof checks, so we also need the
  // class identities to match. The real classes extend `Error`.
  LLMStreamError: class LLMStreamError extends Error {},
  LLMUnavailableError: class LLMUnavailableError extends Error {},
}));

describe("POST /api/jobs/chat/stream", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    process.env = { ...process.env, LLM_API_KEY: "test-key" };
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds the messages array with the chat system prompt and pipes the LLM stream through", async () => {
    const upstreamStream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode('event: text\ndata: {"delta":"hi"}\n\n'),
        );
        controller.enqueue(
          new TextEncoder().encode(
            'event: done\ndata: {"jobs":[],"explanation":""}\n\n',
          ),
        );
        controller.close();
      },
    });
    mockStream.mockResolvedValueOnce(upstreamStream);

    const { POST } = await import("../route");

    const request = new Request("http://localhost:3000/api/jobs/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "react madrid" }),
    });

    const response = await POST(request as never);

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("text/event-stream");
    expect(response.headers.get("Cache-Control")).toBe("no-cache");
    expect(response.headers.get("Connection")).toBe("keep-alive");
    expect(response.headers.get("X-Accel-Buffering")).toBe("no");

    // The LLM client was called with the chat system prompt and
    // the user's message (built via `buildChatFilterUserMessage`).
    expect(mockStream).toHaveBeenCalledTimes(1);
    const messages = mockStream.mock.calls[0]![0] as Array<{
      role: string;
      content: string;
    }>;
    expect(messages[0]?.role).toBe("system");
    expect(messages[1]?.role).toBe("user");
    // The user message is JSON-serialized `{intent, jobs}` per
    // `buildChatFilterUserMessage`. We assert the round-trip:
    const parsed = JSON.parse(messages[1]!.content) as {
      intent: string;
      jobs: unknown[];
    };
    expect(parsed.intent).toBe("react madrid");
    expect(parsed.jobs).toEqual([]);

    // The upstream stream flows through unchanged.
    const reader = response.body?.getReader();
    expect(reader).toBeDefined();
    const decoder = new TextDecoder();
    let body = "";
    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      body += decoder.decode(value, { stream: true });
    }
    expect(body).toContain('event: text\ndata: {"delta":"hi"}');
    expect(body).toContain("event: done");
  });

  it("returns an SSE error chunk when chatCompletionStream throws LLMStreamError", async () => {
    // Use the real class via dynamic import so `instanceof` matches.
    const { LLMStreamError } = await import("@/lib/llm-client");
    mockStream.mockRejectedValueOnce(
      new LLMStreamError("HTTP 502 from upstream: <internal trace abc123>"),
    );

    const { POST } = await import("../route");

    const request = new Request("http://localhost:3000/api/jobs/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "test" }),
    });

    const response = await POST(request as never);
    expect(response.status).toBe(200); // SSE: errors are in-band
    expect(response.headers.get("Content-Type")).toBe("text/event-stream");

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let body = "";
    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      body += decoder.decode(value, { stream: true });
    }

    expect(body).toContain("event: error");
    expect(body).toContain('"code":"llm_stream"');
    // The raw exception message MUST NOT leak (AGENTS.md #24) —
    // pin a substring that ONLY appears in the original exception
    // text, not in the static user-facing SSE message.
    expect(body).not.toContain("HTTP 502 from upstream");
    expect(body).not.toContain("internal trace abc123");
  });

  it("returns an SSE error chunk with code llm_unavailable when LLMUnavailableError is thrown", async () => {
    const { LLMUnavailableError } = await import("@/lib/llm-client");
    mockStream.mockRejectedValueOnce(
      new LLMUnavailableError(
        "DNS resolution failed: getaddrinfo ENOTFOUND api.minimax.io",
      ),
    );

    const { POST } = await import("../route");

    const request = new Request("http://localhost:3000/api/jobs/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "test" }),
    });

    const response = await POST(request as never);
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let body = "";
    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      body += decoder.decode(value, { stream: true });
    }

    expect(body).toContain("event: error");
    expect(body).toContain('"code":"llm_unavailable"');
    // No DNS / hostname / network internals in the SSE payload.
    expect(body).not.toContain("getaddrinfo");
    expect(body).not.toContain("ENOTFOUND");
    expect(body).not.toContain("api.minimax.io");
  });

  it("returns 400 with a JSON body when the request body is malformed", async () => {
    const { POST } = await import("../route");

    const request = new Request("http://localhost:3000/api/jobs/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "not-json",
    });

    const response = await POST(request as never);
    expect(response.status).toBe(400);
    const body = (await response.json()) as { code: string };
    expect(body.code).toBe("internal");
    // LLM client must NOT have been called for a malformed body.
    expect(mockStream).not.toHaveBeenCalled();
  });

  it("returns 400 when the 'message' field is missing", async () => {
    const { POST } = await import("../route");

    const request = new Request("http://localhost:3000/api/jobs/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    const response = await POST(request as never);
    expect(response.status).toBe(400);
    expect(mockStream).not.toHaveBeenCalled();
  });
});