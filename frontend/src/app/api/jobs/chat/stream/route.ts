import { NextRequest } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL ?? "http://localhost:8000";

/**
 * SSE proxy route handler.
 * Forwards POST body and Content-Type to the backend's /jobs/chat/stream
 * endpoint and streams the SSE response back to the client transparently.
 */
export async function POST(request: NextRequest) {
  const body = await request.text();

  const backendResponse = await fetch(
    `${BACKEND_URL}/jobs/chat/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body,
    },
  );

  return new Response(backendResponse.body, {
    status: backendResponse.status,
    statusText: backendResponse.statusText,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
