import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChat } from "../useChat";

// Helper: create a mock ReadableStream from chunks
function createMockStream(
  chunks: string[],
): ReadableStream<Uint8Array> {
  return new ReadableStream({
    async start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(new TextEncoder().encode(chunk));
      }
      controller.close();
    },
  });
}

// Helper: create a mock Response
function mockSSEResponse(
  chunks: string[],
  status = 200,
): Response {
  return new Response(createMockStream(chunks), {
    status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });
}

describe("useChat", () => {
  beforeEach(() => {
    // Mock crypto.randomUUID
    let idCounter = 0;
    vi.spyOn(crypto, "randomUUID").mockImplementation(
      () => `mock-id-${++idCounter}`,
    );

    // Mock global fetch
    vi.stubGlobal("fetch", vi.fn());

    // Mock localStorage for chat persistence
    const store: Record<string, string> = {};
    vi.spyOn(Storage.prototype, "getItem").mockImplementation((key) => {
      return store[key] ?? null;
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation((key, value) => {
      store[key] = value as string;
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation((key) => {
      delete store[key];
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("starts with empty messages and idle status", () => {
    const { result } = renderHook(() => useChat());

    expect(result.current.messages).toEqual([]);
    expect(result.current.status).toBe("idle");
  });

  it("adds user message when sendMessage is called", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockSSEResponse(
        ['event: done\ndata: {"jobs":[],"explanation":"Done","total_considered":0,"total_matched":0,"used_fallback":false}\n\n'],
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.sendMessage("remote react jobs");
    });

    // Should have added user message
    expect(result.current.messages).toHaveLength(2); // user + assistant
    expect(result.current.messages[0]!.role).toBe("user");
    expect(result.current.messages[0]!.content).toBe("remote react jobs");
    expect(result.current.messages[1]!.role).toBe("assistant");
  });

  it("transitions through statuses during a successful stream", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockSSEResponse(
        ['event: done\ndata: {"jobs":[],"explanation":"Done","total_considered":0,"total_matched":0,"used_fallback":false}\n\n'],
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    expect(result.current.status).toBe("idle");

    await act(async () => {
      result.current.sendMessage("test query");
    });

    expect(result.current.status).toBe("done");
  });

  it("handles text events and accumulates content", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockSSEResponse([
        'event: text\ndata: {"delta":"Hello"}\n\n',
        'event: text\ndata: {"delta":" "}\n\n',
        'event: text\ndata: {"delta":"World"}\n\n',
        'event: done\ndata: {"jobs":[],"explanation":"Hello World","total_considered":0,"total_matched":0,"used_fallback":false}\n\n',
      ]),
    );
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.sendMessage("test");
    });

    const assistantMsg = result.current.messages[1]!;
    expect(assistantMsg.content).toBe("Hello World");
    expect(assistantMsg.role).toBe("assistant");
  });

  it("handles done event with job results", async () => {
    const mockJobs = [
      {
        id: "123",
        source: "linkedin",
        title: "Software Engineer",
        company: "Acme",
        location: "Madrid",
        url: "https://example.com/job/123",
        posted_at: "2026-06-01T00:00:00Z",
        description: null,
      },
    ];

    const mockFetch = vi.fn().mockResolvedValue(
      mockSSEResponse([
        `event: done\ndata: ${JSON.stringify({ jobs: mockJobs, explanation: "Found 1 match", total_considered: 5, total_matched: 1, used_fallback: false })}\n\n`,
      ]),
    );
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.sendMessage("engineer");
    });

    const assistantMsg = result.current.messages[1]!;
    expect(assistantMsg.jobs).toHaveLength(1);
    expect(assistantMsg.jobs![0]!.title).toBe("Software Engineer");
    expect(assistantMsg.jobs![0]!.company).toBe("Acme");
  });

  it("handles HTTP error response", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "llm_unavailable",
          message: "LLM not available",
        }),
        { status: 503, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.sendMessage("test");
    });

    expect(result.current.status).toBe("error");
    const lastMsg =
      result.current.messages[result.current.messages.length - 1]!;
    expect(lastMsg.role).toBe("assistant");
    expect(lastMsg.error?.code).toBe("llm_unavailable");
  });

  it("handles network errors", async () => {
    const mockFetch = vi
      .fn()
      .mockRejectedValue(new Error("Network failure"));
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.sendMessage("test");
    });

    expect(result.current.status).toBe("error");
    const lastMsg =
      result.current.messages[result.current.messages.length - 1]!;
    expect(lastMsg.error?.message).toContain("Network failure");
  });

  it("reset clears messages and status", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockSSEResponse(
        ['event: done\ndata: {"jobs":[],"explanation":"Done","total_considered":0,"total_matched":0,"used_fallback":false}\n\n'],
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.sendMessage("test");
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.messages).toEqual([]);
    expect(result.current.status).toBe("idle");
  });

  it("handles SSE error event mid-stream", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      mockSSEResponse([
        'event: text\ndata: {"delta":"Partial"}\n\n',
        'event: error\ndata: {"code":"llm_stream","message":"Stream interrupted"}\n\n',
      ]),
    );
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.sendMessage("test");
    });

    expect(result.current.status).toBe("error");
    const assistantMsg = result.current.messages[1]!;
    expect(assistantMsg.error?.code).toBe("llm_stream");
    // Text deltas are intentionally ignored (they're LLM thinking
    // content, not the user-facing response). The user sees the
    // thinking animation until the error event arrives.
    expect(assistantMsg.content).toBe("");
  });

  it("does not send empty messages", () => {
    const mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);

    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.sendMessage("");
    });
    act(() => {
      result.current.sendMessage("   ");
    });

    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.messages).toEqual([]);
  });
});
