/**
 * GET /api/health — pass-through to the backend's /health.
 *
 * The topbar polls this every 30s to render the green/gray/red
 * status dot. We forward the response verbatim (status + body)
 * so any 503 / degraded information the backend includes is
 * preserved for the UI to render.
 */
import { NextResponse, type NextRequest } from "next/server";
import { backendFetch, BackendError } from "@/lib/backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest): Promise<NextResponse> {
  try {
    const backendRes = await backendFetch("/health", {
      method: "GET",
      forwardRequestId: request.headers.get("X-Request-Id"),
      timeoutMs: 5_000,
    });
    const body = await backendRes.text();
    return new NextResponse(body, {
      status: backendRes.status,
      headers: {
        "Content-Type":
          backendRes.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json(
        { status: "unhealthy", error: error.message },
        { status: error.status },
      );
    }
    return NextResponse.json(
      { status: "unhealthy", error: "Unexpected error" },
      { status: 500 },
    );
  }
}
