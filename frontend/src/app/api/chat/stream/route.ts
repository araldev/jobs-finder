/**
 * POST /api/chat/stream — server-side SSE forwarder.
 *
 * Responsibilities:
 *   1. Validate the incoming JSON body ({message: string}).
 *   2. POST to the backend's POST /jobs/chat/stream.
 *   3. Forward the SSE stream byte-by-byte to the browser.
 *   4. Translate the backend's 404 (LLM_FILTER_ENABLED=false) into
 *      a 200 JSON response with {available: false, reason: "llm_disabled"}
 *      so the browser UI never sees a 404 here.
 */
import { NextResponse, type NextRequest } from "next/server";
import { backendFetch, BackendError } from "@/lib/backend";
import {
  encode,
  forwardChatStream,
  frameSseBlock,
} from "@/lib/chat-stream-forwarder";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface ChatRequestBody {
  readonly message?: unknown;
}

function parseBody(raw: string): { ok: true; message: string } | { ok: false; code: string } {
  let parsed: ChatRequestBody;
  try {
    parsed = JSON.parse(raw) as ChatRequestBody;
  } catch {
    return { ok: false, code: "invalid_json" };
  }
  if (typeof parsed.message !== "string") {
    return { ok: false, code: "missing_message" };
  }
  const trimmed = parsed.message.trim();
  if (trimmed.length === 0) {
    return { ok: false, code: "empty_message" };
  }
  if (trimmed.length > 1_000) {
    return { ok: false, code: "message_too_long" };
  }
  return { ok: true, message: trimmed };
}

export async function POST(request: NextRequest): Promise<NextResponse | Response> {
  const raw = await request.text();
  const body = parseBody(raw);
  if (!body.ok) {
    return NextResponse.json(
      { error: { code: body.code, message: "Invalid request body" } },
      { status: 400 },
    );
  }

  // 1) Probe the backend for the 404-short-circuit case.
  // We issue the real POST once and inspect the status; if it is
  // 404 (LLM disabled), we never start an SSE response.
  const incomingRequestId = request.headers.get("X-Request-Id");
  let backendRes: Response;
  try {
    backendRes = await backendFetch("/jobs/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ message: body.message }),
      forwardRequestId: incomingRequestId,
      // SSE responses are not bounded by the standard 30s — the
      // LLM stream can run for 30s+ on slow models. We let the
      // request.signal carry the abort and disable the timeout.
      timeoutMs: 120_000,
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

  if (backendRes.status === 404) {
    return NextResponse.json(
      { available: false, reason: "llm_disabled" },
      { status: 200 },
    );
  }

  if (!backendRes.ok) {
    const text = await backendRes.text();
    return new NextResponse(text, {
      status: backendRes.status,
      headers: { "Content-Type": backendRes.headers.get("Content-Type") ?? "application/json" },
    });
  }

  if (backendRes.body === null) {
    return NextResponse.json(
      { error: { code: "empty_body", message: "Backend returned an empty body" } },
      { status: 502 },
    );
  }

  // 2) Stream the SSE response back to the browser.
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const enqueue = (chunk: string) => {
        try {
          controller.enqueue(encode(chunk));
        } catch {
          // controller already closed; ignore
        }
      };
      const requestSignal = request.signal;
      try {
        await forwardChatStream({
          backendResponse: backendRes,
          controller,
          enqueue,
          ...(requestSignal ? { signal: requestSignal } : {}),
          callbacks: {
            onMeta: (event) => {
              enqueue(frameSseBlock("meta", event));
            },
            onText: (event) => {
              enqueue(frameSseBlock("text", event));
            },
            onDone: (payload) => {
              enqueue(frameSseBlock("done", payload));
            },
            onError: async (event) => {
              enqueue(frameSseBlock("error", event));
            },
          },
        });
      } finally {
        try {
          controller.close();
        } catch {
          // already closed
        }
        // Touch the encoder so the bundler keeps it (unused otherwise).
        void encoder;
      }
    },
    cancel() {
      // The browser went away; nothing extra to do — the request
      // signal will abort the backend reader.
    },
  });

  return new NextResponse(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
