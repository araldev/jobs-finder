"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import type { ChatMessage, ChatStatus, SSEParsedEvent } from "@/types/chat";
import type { SSEMessage } from "@/types/chat";
import type { Job } from "@/types/job";
import {
  CHAT_STORAGE_KEY,
  loadChatStorage,
  saveChatStorage,
  clearChatStorage,
} from "@/lib/chat-storage";

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
  openedJobIds: Set<string>;
  markJobAsOpened: (jobId: string) => void;
}

export interface UseChatOptions {
  /** localStorage key to persist/retrieve chat state across sessions. */
  storageKey?: string;
}

const decoder = new TextDecoder();

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { storageKey } = options;
  const effectiveKey = storageKey ?? CHAT_STORAGE_KEY;

  // Load persisted state from localStorage on init
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (effectiveKey) {
      const saved = loadChatStorage();
      return (saved?.messages as ChatMessage[]) ?? [];
    }
    return [];
  });

  const [status, setStatus] = useState<ChatStatus>("idle");

  const [openedJobIds, setOpenedJobIds] = useState<Set<string>>(() => {
    if (effectiveKey) {
      const saved = loadChatStorage();
      return new Set(saved?.openedJobIds ?? []);
    }
    return new Set();
  });

  const abortRef = useRef<AbortController | null>(null);

  // Persist state to localStorage on every change
  useEffect(() => {
    if (effectiveKey) {
      saveChatStorage({ messages, openedJobIds: Array.from(openedJobIds) });
    }
  }, [effectiveKey, messages, openedJobIds]);

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

    fetch("/api/jobs/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
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
                  // Text deltas are the LLM's reasoning/thinking content
                  // (MiniMax emits  lexicographic tokens despite
                  // `thinking: disabled`). We DON'T accumulate them into
                  // `message.content` because the user-facing response
                  // comes in the `done` event's `explanation` field.
                  // The thinking animation handles the in-flight state.
                  break;

                case "done":
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
          parser.flush();

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
            content: "",
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
    setOpenedJobIds(new Set());
    if (effectiveKey) {
      clearChatStorage();
    }
  }, [effectiveKey]);

  const markJobAsOpened = useCallback((jobId: string) => {
    setOpenedJobIds((prev) => {
      const next = new Set(prev);
      next.add(jobId);
      return next;
    });
  }, []);

  return { messages, status, sendMessage, reset, openedJobIds, markJobAsOpened };
}
