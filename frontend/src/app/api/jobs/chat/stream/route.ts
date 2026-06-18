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

  // Handle cases where the backend returns no body (e.g., certain error responses)
  // In Next.js 15, passing null to new Response() causes
  // "Attempted to access streaming response content" error
  if (!backendResponse.body) {
    return new Response(
      JSON.stringify({ error: "Backend returned empty response" }),
      {
        status: backendResponse.status || 502,
        headers: { "Content-Type": "application/json" },
      },
    );
  }

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
