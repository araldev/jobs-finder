/**
 * GET /api/jobs — server-side proxy to the FastAPI backend.
 *
 * The browser calls this Route Handler (not the backend directly)
 * so the backend URL is server-only and so we can fan out a
 * uniform error contract. We forward the request, then forward
 * the response shape, copying the cache and rate-limit headers
 * the backend sets.
 */
import { NextResponse, type NextRequest } from "next/server";
import { backendFetch, BackendError } from "@/lib/backend";

const FORWARDED_HEADERS = [
  "X-Cache",
  "X-Request-Id",
  "X-RateLimit-Limit",
  "X-RateLimit-Remaining",
  "X-RateLimit-Reset",
] as const;

function buildPath(request: NextRequest): string {
  const params = request.nextUrl.searchParams;
  const qs = params.toString();
  return `/jobs${qs.length > 0 ? `?${qs}` : ""}`;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const incomingRequestId = request.headers.get("X-Request-Id");
  try {
    const backendRes = await backendFetch(buildPath(request), {
      method: "GET",
      forwardRequestId: incomingRequestId,
    });
    const body = await backendRes.text();
    const headers = new Headers();
    headers.set("Content-Type", backendRes.headers.get("Content-Type") ?? "application/json");
    for (const name of FORWARDED_HEADERS) {
      const value = backendRes.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    return new NextResponse(body, {
      status: backendRes.status,
      headers,
    });
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json(
        { error: { code: "upstream_error", message: error.message } },
        { status: error.status },
      );
    }
    return NextResponse.json(
      { error: { code: "internal_error", message: "Unexpected error" } },
      { status: 500 },
    );
  }
}
