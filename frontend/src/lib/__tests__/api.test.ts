import { describe, expect, it } from "vitest";
import { ApiError, mapBackendError, parseJobsResponse } from "@/lib/api";

describe("ApiError", () => {
  it("stores status, code, requestId and retryAfter", () => {
    const err = new ApiError({
      status: 429,
      code: "rate_limited",
      message: "Demasiadas solicitudes",
      requestId: "req-1",
      retryAfter: 30,
    });
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("ApiError");
    expect(err.status).toBe(429);
    expect(err.code).toBe("rate_limited");
    expect(err.requestId).toBe("req-1");
    expect(err.retryAfter).toBe(30);
  });

  it("defaults requestId and retryAfter to null", () => {
    const err = new ApiError({ status: 500, code: "internal_error", message: "boom" });
    expect(err.requestId).toBeNull();
    expect(err.retryAfter).toBeNull();
  });
});

describe("mapBackendError", () => {
  it("maps 500 to an internal_error ApiError", () => {
    const err = mapBackendError(500, { message: "boom" }, "req-1");
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(500);
    expect(err.code).toBe("internal_error");
    expect(err.message).toMatch(/servidor/i);
  });

  it("maps 429 with Retry-After to a rate_limited ApiError", () => {
    const err = mapBackendError(429, {}, "req-1", 30);
    expect(err.status).toBe(429);
    expect(err.code).toBe("rate_limited");
    expect(err.retryAfter).toBe(30);
    expect(err.message).toMatch(/30/);
  });

  it("maps 404 to a not_found ApiError", () => {
    const err = mapBackendError(404, {}, "req-1");
    expect(err.status).toBe(404);
    expect(err.code).toBe("not_found");
    expect(err.message).toMatch(/no encontrado/i);
  });

  it("maps 401 to unauthorized and 403 to forbidden", () => {
    const a = mapBackendError(401, {}, "req-1");
    const b = mapBackendError(403, {}, "req-1");
    expect(a.code).toBe("unauthorized");
    expect(b.code).toBe("forbidden");
    expect(a.message).toMatch(/autenticaci[oó]n/i);
  });
});

describe("parseJobsResponse", () => {
  function makeResponse(body: unknown, init: { status?: number; cache?: string | null; requestId?: string | null } = {}): Response {
    const headers = new Headers();
    if (init.cache !== undefined && init.cache !== null) headers.set("X-Cache", init.cache);
    if (init.requestId !== undefined && init.requestId !== null) headers.set("X-Request-Id", init.requestId);
    return new Response(JSON.stringify(body), {
      status: init.status ?? 200,
      headers,
    });
  }

  it("returns the SearchResult with cacheStatus HIT when X-Cache is HIT", async () => {
    const body = {
      jobs: [
        {
          id: "j1",
          title: "Senior Python",
          company: "Acme",
          location: "Madrid",
          url: "https://example.com/j1",
          sources: ["linkedin"],
          posted_at: "2026-06-01T00:00:00Z",
          description: null,
        },
      ],
    };
    const res = makeResponse(body, { cache: "HIT", requestId: "req-1" });
    const result = await parseJobsResponse(res);
    expect(result.cacheStatus).toBe("HIT");
    expect(result.jobs).toHaveLength(1);
    expect(result.jobs[0]?.id).toBe("j1");
  });

  it("defaults cacheStatus to MISS when the header is absent", async () => {
    const res = makeResponse({ jobs: [] });
    const result = await parseJobsResponse(res);
    expect(result.cacheStatus).toBe("MISS");
    expect(result.jobs).toEqual([]);
  });

  it("throws an ApiError on non-2xx responses", async () => {
    const res = makeResponse({ message: "internal" }, { status: 500 });
    await expect(parseJobsResponse(res)).rejects.toBeInstanceOf(ApiError);
  });
});
