import "server-only";

import { type NextRequest } from "next/server";
import {
  chatCompletionStream,
  LLMStreamError,
  LLMUnavailableError,
} from "@/lib/llm-client";
import {
  CHAT_FILTER_SYSTEM_PROMPT,
  buildChatFilterUserMessage,
} from "@/lib/llm/prompts";

/**
 * POST /api/jobs/chat/stream
 *
 * Phase 3 LLM migration: replaces the previous Python backend
 * proxy (`POST /jobs/chat/stream`) with a direct MiniMax call.
 *
 * The chat panel's SSE parser (`useChat.SSEParser` +
 * `parseTypedEvent`) consumes `event: text`, `event: done`, and
 * `event: error` chunks. The LLM client
 * (`@/lib/llm-client.chatCompletionStream`) already reformats
 * MiniMax's raw `data: {json}\n\n` stream into that exact
 * contract, so we just pipe its `ReadableStream<Uint8Array>`
 * straight into the response body — no buffering, no
 * transformation.
 *
 * Phase 3 limitation: the previous Python backend ran a
 * 3-stage flow (aggregator → intent extractor → LLM) and
 * emitted a `done` event with the matched `jobs[]` and the
 * LLM's `explanation`. Without the aggregator in Next.js,
 * the `done` event is intentionally minimal
 * (`jobs: []`, `explanation: ""`) — the chat panel will show
 * the LLM's streamed reasoning but no job cards. Rebuilding
 * the aggregator + intent extractor as Next.js code is a
 * separate follow-up task.
 *
 * Error handling: any LLM failure (no API key, network error,
 * non-2xx) becomes a single SSE `event: error` chunk with
 * the `code: llm_stream` machine code. The raw exception is
 * NEVER included in the error payload (AGENTS.md rule #24).
 */
export async function POST(request: NextRequest) {
  // 1. Parse the request body. The consumer (`useChat.ts`) sends
  //    `{ message: string }`. A malformed body returns 400
  //    synchronously (NOT an SSE error event) so the client can
  //    distinguish between "bad request" and "LLM failure".
  let body: { message?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { code: "internal", message: "Invalid request body" },
      { status: 400 },
    );
  }

  const message = typeof body.message === "string" ? body.message : "";
  if (message.length === 0) {
    return Response.json(
      { code: "internal", message: "Missing 'message' field" },
      { status: 400 },
    );
  }

  // 2. Build the messages array. The chat filter prompt expects
  //    `{intent, jobs[]}`; with no aggregator in Next.js, `jobs`
  //    is empty — the LLM will respond with `matching_ids: []`
  //    and the chat panel will see no job cards. The intent
  //    message is the user-provided query.
  const userMessage = buildChatFilterUserMessage(message, []);

  let stream: ReadableStream<Uint8Array>;
  try {
    stream = await chatCompletionStream(
      [
        { role: "system", content: CHAT_FILTER_SYSTEM_PROMPT },
        { role: "user", content: userMessage },
      ],
    );
  } catch (err) {
    // Map domain errors to the SSE error chunk contract. Both
    // error classes collapse to `code: llm_stream` for the chat
    // panel — the panel only differentiates `llm_unavailable`
    // from `llm_stream` for UX messages, and the user-facing
    // copy is generic ("Please try again.").
    const code =
      err instanceof LLMUnavailableError
        ? "llm_unavailable"
        : err instanceof LLMStreamError
          ? "llm_stream"
          : "internal";
    const message =
      code === "llm_unavailable"
        ? "LLM provider unavailable. Please try again later."
        : code === "llm_stream"
          ? "LLM stream failed. Please try again."
          : "Internal error. Please try again.";

    // Log the underlying exception server-side for debugging.
    console.error("jobs/chat/stream: LLM error", err);

    const encoder = new TextEncoder();
    const errorStream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            `event: error\ndata: ${JSON.stringify({ code, message })}\n\n`,
          ),
        );
        controller.close();
      },
    });

    return new Response(errorStream, {
      status: 200, // SSE: errors are in-band, not in HTTP status
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  }

  // 3. Pipe the LLM client's pre-formatted SSE stream into the
  //    response body. Next.js 15 / React 19 / Node 18+ supports
  //    returning a `ReadableStream<Uint8Array>` directly from a
  //    Route Handler — the bytes flow through without buffering.
  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}