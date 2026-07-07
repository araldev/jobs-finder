import "server-only";

import { type NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;

/**
 * Build request headers for outbound calls to the Python backend.
 *
 * Inlined here (post-Phase-2) because the legacy `getUserHeaders`
 * helper in `api-client.ts` was removed when `api-client.ts` was
 * deleted. The Phase 3 migration (LLM in Next.js) will eliminate
 * the last `BACKEND_URL` consumer in this file and this helper
 * goes with it.
 */
function buildBackendHeaders(
  authHeader: string | null,
): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (BACKEND_API_KEY) h["X-API-Key"] = BACKEND_API_KEY;
  if (authHeader) h["Authorization"] = authHeader;
  return h;
}

/**
 * GET /api/cv/count
 *
 * Returns today's CV generation count for the authenticated user.
 * Proxies to the backend `GET /cv/count` endpoint, forwarding the
 * user's JWT from the incoming request's `Authorization` header.
 *
 * Response shape: `{ total_today: number }`
 *
 * Returns `{ total_today: 0 }` if the backend is unreachable
 * or returns a non-OK status — the frontend uses this as a best-
 * effort hint and the count is always 0 for anonymous users.
 */
export async function GET(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const headers = buildBackendHeaders(authHeader);

  try {
    const backendResponse = await fetch(`${BACKEND_URL}/cv/count`, {
      headers,
      next: { revalidate: 30, tags: ["cv-count"] },
    });

    if (!backendResponse.ok) {
      return NextResponse.json({ total_today: 0 });
    }

    const data = await backendResponse.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ total_today: 0 });
  }
}
