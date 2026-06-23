import "server-only";

import { type NextRequest, NextResponse } from "next/server";
import { getUserHeaders } from "@/lib/api-client";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

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
  const headers = getUserHeaders(authHeader);

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
