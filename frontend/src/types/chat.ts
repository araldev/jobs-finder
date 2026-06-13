import type { Job } from "./job";

// ── Chat message types ──────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  jobs?: Job[];
  explanation?: string;
  error?: { code: string; message: string };
  /** Extracted query from the meta event, shown as a hint */
  extractedQuery?: string;
}

// ── SSE event payloads (raw from backend/stream) ────────────────────

export interface SSEEventMeta {
  stage: number;
  intent?: Record<string, unknown>;
}

export interface SSEEventText {
  delta: string;
}

export interface SSEEventDone {
  jobs: Job[];
  explanation: string;
  total_considered: number;
  total_matched: number;
  used_fallback: boolean;
}

export interface SSEEventError {
  code: string;
  message: string;
}

// ── Parsed SSE event union ──────────────────────────────────────────

export type SSEParsedEvent =
  | { type: "meta"; data: SSEEventMeta }
  | { type: "text"; data: SSEEventText }
  | { type: "done"; data: SSEEventDone }
  | { type: "error"; data: SSEEventError };

// ── Chat hook status ────────────────────────────────────────────────

export type ChatStatus = "idle" | "connecting" | "streaming" | "done" | "error";

// ── Error code → user-facing message ────────────────────────────────

export const ERROR_CODE_MAP: Record<string, string> = {
  llm_unavailable: "The AI assistant is currently unavailable. Please try again later.",
  llm_stream: "Connection interrupted while processing your request.",
  llm_parse: "The AI response couldn't be interpreted. Please rephrase.",
  llm_timeout: "The request timed out. Try a simpler query.",
  stage1_parse: "Couldn't understand that. Try being more specific.",
  internal: "Something went wrong. Please try again.",
};

/**
 * Maps a backend error code to a user-facing message.
 * Returns the default message for unknown codes.
 */
export function formatErrorMessage(code: string): string {
  return ERROR_CODE_MAP[code] ?? "Something went wrong. Please try again.";
}

// ── Raw SSE message (before JSON parsing) ───────────────────────────

export interface SSEMessage {
  event?: string;
  data: string;
}
