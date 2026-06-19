import { NextRequest } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL ?? "http://localhost:8000";

/**
 * SSE proxy route handler.
 * Forwards POST body and Content-Type to the backend's /jobs/chat/stream
 * endpoint and streams the SSE response back to the client.
 *
 * Uses Web API fetch streaming: we create a new Response with the
 * ReadableStream from the backend response body. The stream is consumed
 * once by the client, so this works reliably in Next.js 15 / Node.js 18+.
 */
export async function POST(request: NextRequest) {
  const body = await request.text();

  const response = await fetch(`${BACKEND_URL}/jobs/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });

  if (!response.body) {
    return Response.json(
      { error: "Backend returned empty response" },
      { status: response.status || 502 },
    );
  }

  // Stream the SSE response back to the client.
  // In Next.js 15 / React 19, ReadableStream from fetch can be
  // passed directly to Response constructor.
  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
