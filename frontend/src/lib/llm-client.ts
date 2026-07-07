import "server-only";

import { cache } from "react";

// ── Configuration ────────────────────────────────────────────────────────────
//
// MiniMax exposes an OpenAI-compatible chat-completions endpoint at
// `${baseUrl}/v1/chat/completions`. The defaults match the Python
// backend's `Settings.llm_*` defaults so a frontend deployment can
// use the same MiniMax credentials the backend did.
//
// `LLM_API_KEY` is the only REQUIRED var — it is the kill switch that
// disables the chat and CV routes when unset. We never log it, never
// interpolate it into error messages, and never include it in SSE
// error payloads (AGENTS.md rule #24 — don't leak exception details).

const DEFAULT_BASE_URL = "https://api.minimax.io";
const DEFAULT_MODEL = "MiniMax-M3";
// JSON-mode calls (e.g. cv/generate) need temperature 0 — MiniMax-M3
// drifts away from the strict-JSON output at higher temperatures and
// the `response_format: { type: "json_object" }` flag is best-effort
// (not enforced server-side for every model). Creative calls
// (chat) keep the higher temperature.
const DEFAULT_TEMPERATURE = 0.0;
const DEFAULT_MAX_TOKENS = 4096;
// cv/generate emits a 5-7KB JSON blob with 5+ experience entries,
// education, skills, languages, and now projects. MiniMax-M3 has
// been observed taking 25-40s for this prompt size. 30s was too
// tight. 90s leaves headroom while still failing fast enough to
// surface a real outage (vs. a 5-minute timeout that hangs the
// route handler). The chat endpoint stays on the original 30s
// since its prompts are smaller and MiniMax returns streaming
// chunks quickly.
const DEFAULT_TIMEOUT_MS = 90_000;

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatCompletionOptions {
  temperature?: number;
  maxTokens?: number;
  jsonMode?: boolean;
}

/**
 * Raised when the LLM provider is unavailable (network error, non-2xx,
 * malformed response). Maps to HTTP 502 from the calling route handler.
 *
 * The message is a STATIC user-facing string — the underlying cause
 * is logged server-side but NEVER included in `message` (AGENTS.md #24).
 */
export class LLMUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LLMUnavailableError";
  }
}

/**
 * Raised when the LLM streaming response cannot be consumed (non-200
 * status, empty body, network error during streaming). Maps to the
 * SSE `event: error` `code: llm_stream` machine code in the chat
 * route handler.
 */
export class LLMStreamError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LLMStreamError";
  }
}

interface LLMConfig {
  apiKey: string;
  baseUrl: string;
  model: string;
}

function readConfig(): LLMConfig {
  const apiKey = process.env.LLM_API_KEY;
  if (!apiKey) {
    throw new LLMUnavailableError("LLM provider unavailable");
  }
  const baseUrl = (process.env.LLM_BASE_URL ?? DEFAULT_BASE_URL).replace(
    /\/+$/,
    "",
  );
  const model = process.env.LLM_MODEL ?? DEFAULT_MODEL;
  return { apiKey, baseUrl, model };
}

function buildRequestBody(
  model: string,
  messages: ChatMessage[],
  options: ChatCompletionOptions,
  stream: boolean,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model,
    messages,
    temperature: options.temperature ?? DEFAULT_TEMPERATURE,
    max_tokens: options.maxTokens ?? DEFAULT_MAX_TOKENS,
    stream,
  };
  if (options.jsonMode) {
    body.response_format = { type: "json_object" };
  }
  return body;
}

function buildHeaders(apiKey: string): Record<string, string> {
  return {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  };
}

/**
 * Extract the assistant's text content from a non-streaming
 * chat-completions response payload.
 *
 * Mirrors the Python client's `payload["choices"][0]["message"]["content"]`
 * extraction. Returns `null` if the payload shape is unexpected
 * (caller raises `LLMUnavailableError`).
 */
function extractContent(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const choices = (payload as { choices?: unknown }).choices;
  if (!Array.isArray(choices) || choices.length === 0) return null;
  const first = choices[0] as { message?: { content?: unknown } };
  const content = first?.message?.content;
  return typeof content === "string" ? content : null;
}

/**
 * Non-streaming chat completion.
 *
 * POSTs to `${LLM_BASE_URL}/v1/chat/completions` with
 * `stream: false` and returns the assistant's text content.
 *
 * Wrapped in `React.cache()` for per-request memoization — within a
 * single render pass the same `(messages, options)` pair hits the
 * upstream API only once. Mirrors the pattern in
 * `frontend/src/lib/supabase-queries.ts`.
 *
 * Throws:
 *   - `LLMUnavailableError` on any failure mode (no API key,
 *     network error, non-2xx, malformed payload). The `message`
 *     is a static user-facing string.
 */
export const chatCompletion = cache(
  async (
    messages: ChatMessage[],
    options: ChatCompletionOptions = {},
  ): Promise<string> => {
    const { apiKey, baseUrl, model } = readConfig();
    const url = `${baseUrl}/v1/chat/completions`;
    const body = buildRequestBody(model, messages, options, false);
    const headers = buildHeaders(apiKey);

    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      });
    } catch (err) {
      // Never leak the underlying cause to the client (could expose
      // internal API structure, DNS names, or library internals).
      console.error("LLM network error", err);
      throw new LLMUnavailableError("LLM provider unavailable");
    }

    if (!response.ok) {
      console.error("LLM non-OK response", response.status);
      throw new LLMUnavailableError("LLM provider unavailable");
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch (err) {
      console.error("LLM JSON parse error", err);
      throw new LLMUnavailableError("LLM provider unavailable");
    }

    const content = extractContent(payload);
    if (content === null) {
      console.error("LLM unexpected response shape", payload);
      throw new LLMUnavailableError("LLM provider unavailable");
    }
    return content;
  },
);

// ── SSE chunk format expected by the chat panel ─────────────────────────────
//
// The frontend SSE parser (`useChat.SSEParser`) splits on `\n\n`,
// then extracts `event:` and `data:` lines. `parseTypedEvent` switches
// on the event name:
//   - `event: meta`   → {type: "meta",   data: {intent: ...}}
//   - `event: text`   → {type: "text",   data: {delta: string}}
//   - `event: done`   → {type: "done",   data: {jobs, explanation, ...}}
//   - `event: error`  → {type: "error",  data: {code, message}}
//
// The Python backend's `chat_stream` route produced exactly this
// shape. The MiniMax raw stream is different — `data: {json}\n\n` per
// token, `data: [DONE]\n\n` at end. We reformat each chunk on the
// fly inside the transformed ReadableStream below.

interface DonePayload {
  jobs: unknown[];
  explanation: string;
  total_considered: number;
  total_matched: number;
  used_fallback: boolean;
  request_id: string;
}

function serializeEvent(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

const FALLBACK_DONE_PAYLOAD: DonePayload = {
  jobs: [],
  explanation: "",
  total_considered: 0,
  total_matched: 0,
  used_fallback: true,
  request_id: "",
};

/**
 * Streaming chat completion.
 *
 * Returns a `ReadableStream<Uint8Array>` of SSE-formatted chunks
 * the chat panel can consume directly. Each MiniMax `data: {json}\n\n`
 * chunk is reformatted into an `event: text\ndata: {"delta": ...}\n\n`
 * chunk; the terminal `data: [DONE]\n\n` becomes an
 * `event: done\ndata: {...}\n\n` chunk.
 *
 * The stream is intentionally source-agnostic — the chat panel never
 * sees a MiniMax-specific chunk shape, just the contract it already
 * speaks (event: text / event: done / event: error).
 *
 * The `done` event payload is intentionally minimal (`jobs: []`,
 * `explanation: ""`): rebuilding the 3-stage aggregator → intent
 * extractor → LLM flow that produces the real `jobs[]` + `explanation`
 * is a separate follow-up task (the 3-stage orchestrator currently
 * lives only in the Python backend).
 *
 * Wrapped in `React.cache()` — the upstream `fetch` is memoized per
 * request, but the resulting `ReadableStream` is consumed once by
 * the caller (Next.js pipes it into the response body).
 *
 * Throws:
 *   - `LLMStreamError` on non-2xx / empty body / network error during
 *     the initial POST. Mid-stream errors are mapped to SSE
 *     `event: error` `code: llm_stream` chunks (per the backend
 *     REQ-ERROR-MAPPING-001 contract).
 */
export const chatCompletionStream = cache(
  async (
    messages: ChatMessage[],
    options: ChatCompletionOptions = {},
  ): Promise<ReadableStream<Uint8Array>> => {
    const { apiKey, baseUrl, model } = readConfig();
    const url = `${baseUrl}/v1/chat/completions`;
    const body = buildRequestBody(model, messages, options, true);
    const headers = buildHeaders(apiKey);

    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      });
    } catch (err) {
      console.error("LLM stream network error", err);
      throw new LLMStreamError("LLM stream failed");
    }

    if (!response.ok || !response.body) {
      console.error("LLM stream non-OK response", response.status);
      throw new LLMStreamError("LLM stream failed");
    }

    const upstream = response.body.getReader();
    const decoder = new TextDecoder();
    const encoder = new TextEncoder();
    // `done` is mutated from inside the closure — TypeScript's
    // `let` narrows it correctly across the await boundaries.
    let finished = false;

    function emitDone(controller: ReadableStreamDefaultController<Uint8Array>): void {
      if (finished) return;
      finished = true;
      controller.enqueue(
        encoder.encode(serializeEvent("done", FALLBACK_DONE_PAYLOAD)),
      );
      controller.close();
    }

    function emitError(
      controller: ReadableStreamDefaultController<Uint8Array>,
      code: string,
      message: string,
    ): void {
      if (finished) return;
      finished = true;
      controller.enqueue(
        encoder.encode(serializeEvent("error", { code, message })),
      );
      controller.close();
    }

    /**
     * Stateful SSE-framing buffer. The upstream reader may split a
     * single `data: {json}\n\n` frame across multiple `read()` calls,
     * so we accumulate bytes until we see a `\n\n` boundary, then
     * drain complete frames. `buffer` MUST persist across `pull()`
     * invocations — we hoist it into a closure-bound variable above.
     */
    let buffer = "";

    return new ReadableStream<Uint8Array>({
      async pull(controller) {
        try {
          while (true) {
            if (finished) {
              controller.close();
              return;
            }

            const { done, value } = await upstream.read();
            if (done) {
              emitDone(controller);
              return;
            }

            buffer += decoder.decode(value, { stream: true });

            // Drain complete SSE frames from the buffer.
            let idx: number;
            let emittedSomething = false;
            while ((idx = buffer.indexOf("\n\n")) !== -1) {
              const raw = buffer.slice(0, idx);
              buffer = buffer.slice(idx + 2);

              const line = raw.trim();
              if (!line.startsWith("data: ")) continue;
              const payload = line.slice(6).trim();
              if (payload === "[DONE]") {
                emitDone(controller);
                return;
              }

              let chunk: unknown;
              try {
                chunk = JSON.parse(payload);
              } catch {
                // Malformed SSE line — skip (matches the backend's
                // skip-malformed-lines policy; aborting would kill
                // the stream over transient protocol noise).
                continue;
              }

              const delta = extractStreamDelta(chunk);
              if (delta !== null && delta.length > 0) {
                controller.enqueue(
                  encoder.encode(serializeEvent("text", { delta })),
                );
                emittedSomething = true;
              }
            }
            // Yield back to the event loop only when we drained
            // the buffer OR emitted at least one frame — otherwise
            // we keep reading to back-pressure properly.
            if (emittedSomething || buffer.length > 0) return;
          }
        } catch (err) {
          console.error("LLM stream transform error", err);
          emitError(controller, "llm_stream", "LLM stream failed. Please try again.");
        }
      },
      cancel() {
        // Client disconnected — cancel the upstream so we don't keep
        // billing tokens on a request nobody's listening to.
        upstream.cancel().catch(() => {
          /* ignore — stream may already be closed */
        });
      },
    });
  },
);

/**
 * Pull the assistant's text delta from a MiniMax streaming chunk.
 *
 * MiniMax emits either `choices[0].delta.content` (per-token) or
 * `choices[0].message.content` (per-non-streaming-call-shape, rare).
 * Returns `null` for empty deltas (e.g. role-only chunks, function-
 * call deltas) so the caller can skip them silently.
 */
function extractStreamDelta(chunk: unknown): string | null {
  if (!chunk || typeof chunk !== "object") return null;
  const choices = (chunk as { choices?: unknown }).choices;
  if (!Array.isArray(choices) || choices.length === 0) return null;
  const first = choices[0] as {
    delta?: { content?: unknown };
    message?: { content?: unknown };
  };
  const delta = first?.delta?.content ?? first?.message?.content;
  return typeof delta === "string" ? delta : null;
}