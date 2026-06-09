/**
 * Pure SSE forwarder.
 *
 * Lives in src/lib/ (NOT src/app/api/) so it can be unit-tested
 * without booting the Next.js server runtime. The Route Handler
 * `src/app/api/chat/stream/route.ts` calls this with the raw
 * `fetch()` response from the backend and a `ReadableStreamDefaultController`
 * wired to the outbound NextResponse.
 *
 * Wire contract (matches openspec/specs/chat-streaming/spec.md
 * REQ-SSE-001):
 *   meta?  → onMeta({ intent, intent_text })
 *   text*  → onText({ delta })
 *   done   → onDone({ available: true, event: {...} })
 *   error  → onError({ code, message })
 *
 * Plus a defensive `available: false` payload for the case where the
 * Route Handler decided to short-circuit because `LLM_FILTER_ENABLED`
 * is off — see REQ-FALLBACK-001.
 */
import type {
  ChatStreamDoneEvent,
  ChatStreamErrorEvent,
  ChatStreamMetaEvent,
  ChatStreamTextEvent,
  ChatDonePayload,
} from "./types";

/** JSON payload of a `data: ...` line after stripping the prefix. */
type SseDataPayload = unknown;

export interface ForwardChatStreamCallbacks {
  readonly onMeta?: (event: ChatStreamMetaEvent) => void;
  readonly onText: (event: ChatStreamTextEvent) => void;
  readonly onDone: (payload: ChatDonePayload) => void;
  readonly onError: (event: ChatStreamErrorEvent) => Promise<void> | void;
}

export interface ForwardChatStreamArgs {
  /** The raw fetch() response from the backend. */
  readonly backendResponse: Response;
  /**
   * The ReadableStream controller wired to the outbound Next.js
   * Response. We use it only for cancellation; the actual bytes
   * are written via the `enqueue` callback that the caller
   * provides (it may need to encode SSE framing itself).
   */
  readonly controller: ReadableStreamDefaultController<Uint8Array>;
  /** Optional helper to push framed bytes to the browser. */
  readonly enqueue: (chunk: string) => void;
  /** Optional AbortSignal that stops the forwarder on cancel. */
  readonly signal?: AbortSignal;
  readonly callbacks: ForwardChatStreamCallbacks;
}

const SSE_SEP = "\n\n";
const textEncoder = new TextEncoder();

/**
 * Parse a single SSE block. A block is the text between two `\n\n`
 * separators. It may contain `event:`, `data:`, `id:`, and `retry:`
 * lines. We only care about `event` and `data`.
 */
function parseSseBlock(block: string): { event: string; data: SseDataPayload } | null {
  const lines = block.split("\n");
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith(":")) continue; // comment
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  const dataText = dataLines.join("\n");
  let data: SseDataPayload;
  try {
    data = JSON.parse(dataText);
  } catch {
    data = dataText;
  }
  return { event: eventName, data };
}

/**
 * Read a stream chunk-by-chunk, splitting on SSE_SEP, and dispatch
 * events to the callbacks. Defensive against malformed blocks.
 */
export async function forwardChatStream(args: ForwardChatStreamArgs): Promise<void> {
  const { backendResponse, callbacks, enqueue, signal } = args;

  // Defensive: if the backend already told us the chat is unavailable
  // (e.g. LLM_FILTER_ENABLED=false), emit the synthetic done and
  // bail. The Route Handler is expected to short-circuit to a
  // 200 JSON response in this case, so this branch only fires if
  // the contract is violated.
  if (backendResponse.status === 404) {
    callbacks.onDone({ available: false, reason: "llm_disabled" });
    enqueue(
      `event: done\ndata: ${JSON.stringify({ available: false, reason: "llm_disabled" })}\n\n`,
    );
    return;
  }

  if (!backendResponse.ok) {
    const requestId = backendResponse.headers.get("X-Request-Id");
    await callbacks.onError({
      code: `http_${backendResponse.status}`,
      message: `Backend returned ${backendResponse.status}`,
      ...(requestId !== null ? { request_id: requestId } : {}),
    });
    return;
  }

  if (backendResponse.body === null) {
    await callbacks.onError({
      code: "empty_body",
      message: "Backend returned an empty body",
    });
    return;
  }

  const reader = backendResponse.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let doneEmitted = false;
  let errorEmitted = false;

  try {
    while (!doneEmitted && !errorEmitted) {
      if (signal?.aborted) {
        await callbacks.onError({ code: "aborted", message: "Stream aborted" });
        return;
      }
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIndex = buffer.indexOf(SSE_SEP);
      while (sepIndex !== -1) {
        const block = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + SSE_SEP.length);
        await dispatchBlock(block, callbacks, () => {
          doneEmitted = true;
        }, () => {
          errorEmitted = true;
        });
        if (doneEmitted || errorEmitted) break;
        sepIndex = buffer.indexOf(SSE_SEP);
      }
    }
  } catch (cause) {
    await callbacks.onError({
      code: "stream_interrupted",
      message: cause instanceof Error ? cause.message : String(cause),
    });
    return;
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // already released
    }
  }

  // If the stream closed without a terminal event, surface a synthetic
  // error so the UI does not stay in the "streaming" state forever.
  if (!doneEmitted && !errorEmitted) {
    await callbacks.onError({
      code: "stream_interrupted",
      message: "Backend closed the stream without a done/error event",
    });
  }
}

async function dispatchBlock(
  block: string,
  callbacks: ForwardChatStreamCallbacks,
  markDone: () => void,
  markError: () => void,
): Promise<void> {
  const trimmed = block.trim();
  if (trimmed.length === 0) return;
  const parsed = parseSseBlock(trimmed);
  if (parsed === null) return;

  switch (parsed.event) {
    case "meta": {
      if (callbacks.onMeta) {
        const data = asRecord(parsed.data);
        const intent = data && isObject(data.intent) ? data.intent : {};
        const intentText =
          data && typeof data.intent_text === "string" ? data.intent_text : "";
        callbacks.onMeta({ intent, intent_text: intentText });
      }
      return;
    }
    case "text": {
      const data = asRecord(parsed.data);
      if (data !== null && typeof data.delta === "string") {
        callbacks.onText({ delta: data.delta });
      }
      return;
    }
    case "done": {
      const data = asRecord(parsed.data);
      if (data !== null) {
        // We trust the backend wire shape (validated by the canonical
        // chat-streaming spec) but keep the cast explicit so future
        // reviewers see the contract.
        callbacks.onDone({
          available: true,
          event: data as unknown as ChatStreamDoneEvent,
        });
        markDone();
      }
      return;
    }
    case "error": {
      const data = asRecord(parsed.data);
      if (data !== null) {
        const code = typeof data.code === "string" ? data.code : "unknown";
        const message = typeof data.message === "string" ? data.message : "Unknown error";
        await callbacks.onError({
          code,
          message,
          ...(typeof data.request_id === "string" ? { request_id: data.request_id } : {}),
        });
        markError();
      }
      return;
    }
    default:
      // Unknown event names are ignored so the forwarder is forward
      // compatible with future backend events.
      return;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Convenience helper to re-frame an SSE block before sending it on. */
export function frameSseBlock(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Used by the Route Handler to size the controller's high-water mark. */
export function encode(chunk: string): Uint8Array {
  return textEncoder.encode(chunk);
}
