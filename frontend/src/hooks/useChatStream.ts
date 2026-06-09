"use client";

import { useCallback, useRef, useState } from "react";
import { postChatMessageStream } from "@/lib/api";
import type {
  ChatDonePayload,
  ChatStreamErrorEvent,
  ChatStreamMetaEvent,
  ChatStreamTextEvent,
} from "@/lib/types";

export interface UseChatStreamCallbacks {
  readonly onMeta?: (event: ChatStreamMetaEvent) => void;
  readonly onText: (event: ChatStreamTextEvent) => void;
  readonly onDone: (payload: ChatDonePayload) => void;
  readonly onError: (event: ChatStreamErrorEvent) => Promise<void> | void;
}

/**
 * SSE consumer hook for the chat panel. Uses fetch + ReadableStream
 * because the endpoint requires a POST with a JSON body, which
 * EventSource does not support.
 *
 * The hook exposes:
 *   - isStreaming: true between send() and the terminal event
 *   - send(message): kicks off a request
 *   - cancel(): aborts the in-flight request
 */
export function useChatStream(callbacks: UseChatStreamCallbacks): {
  isStreaming: boolean;
  send: (message: string) => Promise<void>;
  cancel: () => void;
} {
  const [isStreaming, setIsStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setIsStreaming(false);
  }, []);

  const send = useCallback(
    async (message: string) => {
      cancel();
      const controller = new AbortController();
      controllerRef.current = controller;
      setIsStreaming(true);

      let res: Response;
      try {
        res = await postChatMessageStream({ message, signal: controller.signal });
      } catch (error) {
        if (controller.signal.aborted) {
          setIsStreaming(false);
          return;
        }
        await callbacks.onError({
          code: "network_error",
          message: error instanceof Error ? error.message : "Network error",
        });
        setIsStreaming(false);
        return;
      }

      // Special case: the Route Handler returned 200 with
      // {available: false, reason: "llm_disabled"} (a JSON body,
      // not SSE). Surface that to the consumer as the synthetic
      // unavailable done payload.
      const contentType = res.headers.get("Content-Type") ?? "";
      if (contentType.includes("application/json")) {
        try {
          const body = (await res.json()) as { available?: boolean; reason?: string };
          if (body.available === false) {
            callbacks.onDone({ available: false, reason: "llm_disabled" });
          } else {
            await callbacks.onError({
              code: "unexpected_response",
              message: "Unexpected JSON response from chat endpoint",
            });
          }
        } catch {
          await callbacks.onError({
            code: "unexpected_response",
            message: "Failed to parse chat endpoint response",
          });
        }
        setIsStreaming(false);
        return;
      }

      if (!res.ok || res.body === null) {
        await callbacks.onError({
          code: `http_${res.status}`,
          message: `Chat endpoint returned ${res.status}`,
        });
        setIsStreaming(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let terminalReached = false;

      try {
        while (!terminalReached) {
          if (controller.signal.aborted) {
            await callbacks.onError({ code: "aborted", message: "Stream aborted" });
            return;
          }
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const sep = "\n\n";
          let idx = buffer.indexOf(sep);
          while (idx !== -1) {
            const block = buffer.slice(0, idx);
            buffer = buffer.slice(idx + sep.length);
            const parsed = parseSseBlock(block);
            if (parsed !== null) {
              if (parsed.event === "meta") {
                callbacks.onMeta?.(parsed.payload as ChatStreamMetaEvent);
              } else if (parsed.event === "text") {
                callbacks.onText(parsed.payload as ChatStreamTextEvent);
              } else if (parsed.event === "done") {
                callbacks.onDone({
                  available: true,
                  event: parsed.payload as ChatStreamDonePayloadAvailable,
                });
                terminalReached = true;
                break;
              } else if (parsed.event === "error") {
                await callbacks.onError(parsed.payload as ChatStreamErrorEvent);
                terminalReached = true;
                break;
              }
            }
            idx = buffer.indexOf(sep);
          }
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          await callbacks.onError({
            code: "stream_interrupted",
            message: cause instanceof Error ? cause.message : String(cause),
          });
        }
      } finally {
        try {
          reader.releaseLock();
        } catch {
          // already released
        }
        setIsStreaming(false);
      }
    },
    [callbacks, cancel],
  );

  return { isStreaming, send, cancel };
}

type ChatStreamDonePayloadAvailable = Extract<ChatDonePayload, { available: true }>["event"];

interface ParsedSseBlock {
  readonly event: string;
  readonly payload: unknown;
}

function parseSseBlock(block: string): ParsedSseBlock | null {
  const lines = block.split("\n");
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  try {
    return { event: eventName, payload: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}
