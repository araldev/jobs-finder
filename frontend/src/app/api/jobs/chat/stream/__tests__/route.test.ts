import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock process.env before importing the handler
const originalEnv = process.env;

describe("POST /api/jobs/chat/stream", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv, BACKEND_URL: "http://test-backend:8000" };
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.unstubAllGlobals();
  });

  it("proxies POST request body to backend", async () => {
    const requestBody = { query: "remote react jobs" };
    const backendResponseBody = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data: test\n\n"));
        controller.close();
      },
    });

    const mockBackendResponse = new Response(backendResponseBody, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });

    const mockFetch = vi.fn().mockResolvedValue(mockBackendResponse);
    vi.stubGlobal("fetch", mockFetch);

    // Dynamic import so it uses the mocked process.env
    const { POST } = await import("../route");

    // Create a minimal mock for NextRequest
    const mockRequest = {
      text: () => Promise.resolve(JSON.stringify(requestBody)),
      headers: new Headers({ "Content-Type": "application/json" }),
    };

    const response = await POST(mockRequest as any);

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("text/event-stream");
    expect(response.headers.get("Cache-Control")).toBe("no-cache");
    expect(response.headers.get("Connection")).toBe("keep-alive");

    // Verify the proxy called the correct backend URL
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const fetchCall = mockFetch.mock.calls[0]!;
    expect(fetchCall[0]).toBe("http://test-backend:8000/jobs/chat/stream");
    expect(fetchCall[1]?.method).toBe("POST");
    expect(fetchCall[1]?.headers).toEqual({
      "Content-Type": "application/json",
    });
    expect(fetchCall[1]?.body).toBe(JSON.stringify(requestBody));
  });

  it("forwards backend error status to client", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: "LLM not available" }),
        { status: 503 },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const { POST } = await import("../route");

    const mockRequest = {
      text: () => Promise.resolve(JSON.stringify({ query: "test" })),
      headers: new Headers({ "Content-Type": "application/json" }),
    };

    const response = await POST(mockRequest as any);

    expect(response.status).toBe(503);
  });

  it("uses default BACKEND_URL when env var is not set", async () => {
    process.env = { ...originalEnv };
    delete process.env.BACKEND_URL;

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(null, { status: 200 }),
      ),
    );

    const { POST } = await import("../route");

    const mockRequest = {
      text: () => Promise.resolve("{}"),
      headers: new Headers(),
    };

    await POST(mockRequest as any);

    const fetchCall = (fetch as any).mock.calls[0]!;
    expect(fetchCall[0]).toBe("http://localhost:8000/jobs/chat/stream");
  });
});
