"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import type { ChatMessage, ChatStatus, SSEParsedEvent } from "@/types/chat";
import type { SSEMessage } from "@/types/chat";
import type { Job } from "@/types/job";

// ── SSE Parser (pure, no React dependencies) ────────────────────────

export class SSEParser {
  private buffer = "";

  /**
   * Feed a chunk of SSE text. Returns zero or more complete messages.
   * Partial messages are buffered until the next \n\n boundary.
   */
  feed(chunk: string): SSEMessage[] {
    this.buffer += chunk;
    return this.extractMessages();
  }

  /**
   * Flush any remaining buffered data as a message.
   * Should be called when the stream ends.
   */
  flush(): SSEMessage[] {
    if (!this.buffer.trim()) return [];

    const raw = this.buffer;
    this.buffer = "";
    const msg = this.parseRaw(raw);
    return msg ? [msg] : [];
  }

  private extractMessages(): SSEMessage[] {
    const messages: SSEMessage[] = [];

    while (true) {
      const idx = this.buffer.indexOf("\n\n");
      if (idx === -1) break;

      const raw = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2);

      const msg = this.parseRaw(raw);
      if (msg) messages.push(msg);
    }

    return messages;
  }

  private parseRaw(raw: string): SSEMessage | null {
    const trimmed = raw.trim();
    if (!trimmed) return null;

    const lines = trimmed.split("\n");
    let event: string | undefined;
    let data: string | undefined;

    for (const line of lines) {
      if (line.startsWith(": ")) continue; // keepalive comment
      if (line.startsWith("event: ")) {
        event = line.slice(7);
      } else if (line.startsWith("data: ")) {
        data = line.slice(6);
      }
    }

    if (data === undefined) return null;
    return { event, data };
  }
}

// ── Parse an SSEMessage into a typed SSEParsedEvent ─────────────────

export function parseTypedEvent(msg: SSEMessage): SSEParsedEvent {
  const parsed = JSON.parse(msg.data);
  switch (msg.event) {
    case "meta":
      return { type: "meta", data: parsed };
    case "text":
      return { type: "text", data: parsed };
    case "done":
      return { type: "done", data: parsed };
    case "error":
      return { type: "error", data: parsed };
    default:
      throw new Error(`Unknown SSE event type: ${msg.event}`);
  }
}

// ── useChat hook ────────────────────────────────────────────────────

export interface UseChatReturn {
  messages: ChatMessage[];
  status: ChatStatus;
  sendMessage: (text: string) => void;
  reset: () => void;
  seenJobIds: Set<string>;
}

export interface UseChatOptions {
  /** localStorage key to persist/retrieve chat state across sessions. */
  storageKey?: string;
}

const decoder = new TextDecoder();

function loadFromStorage(key: string): { messages: ChatMessage[]; seenJobIds: string[] } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as { messages: ChatMessage[]; seenJobIds: string[] };
  } catch {
    return null;
  }
}

function saveToStorage(key: string, messages: ChatMessage[], seenJobIds: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, JSON.stringify({ messages, seenJobIds: Array.from(seenJobIds) }));
  } catch {
    // localStorage unavailable or quota exceeded — ignore
  }
}

function clearStorage(key: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { storageKey } = options;

  // Load persisted state from localStorage on init
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (storageKey) {
      const saved = loadFromStorage(storageKey);
      return saved?.messages ?? [];
    }
    return [];
  });

  const [status, setStatus] = useState<ChatStatus>("idle");

  const [seenJobIds, setSeenJobIds] = useState<Set<string>>(() => {
    if (storageKey) {
      const saved = loadFromStorage(storageKey);
      return new Set(saved?.seenJobIds ?? []);
    }
    return new Set();
  });

  const abortRef = useRef<AbortController | null>(null);

  // Persist state to localStorage on every change
  useEffect(() => {
    if (storageKey) {
      saveToStorage(storageKey, messages, seenJobIds);
    }
  }, [storageKey, messages, seenJobIds]);

  const sendMessage = useCallback((text: string) => {
    if (!text.trim()) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };

    setMessages((prev) => [...prev, userMsg]);
    setStatus("connecting");

    const controller = new AbortController();
    abortRef.current = controller;

    const assistantId = crypto.randomUUID();
    let accumulatedContent = "";

    fetch("/api/jobs/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        exclude_ids: Array.from(seenJobIds),
      }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const bodyText = await response.text();
          let errCode = "internal";
          let errMsg = "Something went wrong. Please try again.";
          try {
            const err = JSON.parse(bodyText);
            if (err.code) errCode = err.code;
            if (err.detail) errMsg = err.detail;
            if (err.message) errMsg = err.message;
          } catch {
            // ignore parse failures on error body
          }

          setStatus("error");
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: "",
              error: { code: errCode, message: errMsg },
            },
          ]);
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          setStatus("error");
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: "",
              error: {
                code: "internal",
                message: "Connection failed — no response body.",
              },
            },
          ]);
          return;
        }

        setStatus("streaming");

        // Insert the initial (empty) assistant message
        setMessages((prev) => [
          ...prev,
          { id: assistantId, role: "assistant", content: "" },
        ]);

        const parser = new SSEParser();

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const messages = parser.feed(chunk);

            for (const msg of messages) {
              const typed = parseTypedEvent(msg);

              switch (typed.type) {
                case "text":
                  accumulatedContent += typed.data.delta;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? { ...m, content: accumulatedContent }
                        : m,
                    ),
                  );
                  break;

                case "done":
                  accumulatedContent = typed.data.explanation;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? {
                            ...m,
                            content: typed.data.explanation,
                            jobs: typed.data.jobs,
                            explanation: typed.data.explanation,
                          }
                        : m,
                    ),
                  );
                  // Track seen job IDs for "visto" filtering
                  if (typed.data.jobs && Array.isArray(typed.data.jobs)) {
                    setSeenJobIds((prev) => {
                      const next = new Set(prev);
                      for (const job of typed.data.jobs) {
                        if (job && job.id) next.add(job.id);
                      }
                      return next;
                    });
                  }
                  break;

                case "error":
                  setStatus("error");
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? {
                            ...m,
                            error: {
                              code: typed.data.code,
                              message: typed.data.message,
                            },
                          }
                        : m,
                    ),
                  );
                  return;

                case "meta": {
                  // Show what the system understood
                  const intent = typed.data.intent as Record<string, unknown> | undefined;
                  const q = typeof intent?.q === "string" ? intent.q : undefined;
                  if (q) {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? { ...m, extractedQuery: q }
                          : m,
                      ),
                    );
                  }
                  break;
                }
              }
            }
          }

          // Flush any remaining data
          const remaining = parser.flush();
          for (const msg of remaining) {
            const typed = parseTypedEvent(msg);
            if (typed.type === "text") {
              accumulatedContent += typed.data.delta;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: accumulatedContent }
                    : m,
                ),
              );
            }
          }

          setStatus("done");
        } catch (err) {
          if (
            err instanceof DOMException &&
            err.name === "AbortError"
          ) {
            // User triggered reset/abort — clean exit
            setStatus("idle");
            return;
          }
          throw err;
        }
      })
      .catch((err) => {
        // Network error or unhandled stream error
        if (
          err instanceof DOMException &&
          err.name === "AbortError"
        ) {
          setStatus("idle");
          return;
        }

        setStatus("error");
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: accumulatedContent
              ? accumulatedContent
              : "",
            error: {
              code: "internal",
              message:
                err instanceof Error
                  ? err.message
                  : "Something went wrong. Please try again.",
            },
          },
        ]);
      });
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setStatus("idle");
    setSeenJobIds(new Set());
    if (storageKey) {
      clearStorage(storageKey);
    }
  }, [storageKey]);

  return { messages, status, sendMessage, reset, seenJobIds };
}
