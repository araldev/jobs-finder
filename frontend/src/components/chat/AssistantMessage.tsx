"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ChatMessage } from "@/types/chat";

interface AssistantMessageProps {
  message: ChatMessage;
  isStreaming: boolean;
  statusLabel?: string;
  openedJobIds: Set<string>;
}

/**
 * Three-pulse thinking indicator. Each dot fades in/out in sequence,
 * OpenCode-style. Pure CSS, no JS animation library needed.
 */
function ThinkingDots() {
  return (
    <span
      className="ml-auto inline-flex items-center gap-1"
      data-testid="thinking-dots"
      aria-label="Thinking"
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary [animation-delay:-0.32s]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary [animation-delay:-0.16s]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
    </span>
  );
}

export function AssistantMessage({
  message,
  isStreaming,
  statusLabel,
  openedJobIds,
}: AssistantMessageProps) {
  // Show the status indicator as long as we're streaming AND
  // we don't yet have the final explanation in `message.content`.
  // The LLM emits thinking tokens as text deltas which we
  // intentionally ignore (see useChat.ts) — the user-facing
  // response arrives only in the `done` event.
  const showThinking =
    isStreaming && (!message.content || message.content.length === 0);

  // Translate chat error codes via the Chat.errors.* keys. Fall back
  // to the server-provided `message` (which may already be localized)
  // when the code has no translation key — this preserves the previous
  // behavior for legacy localStorage payloads and any unknown codes the
  // backend might emit. next-intl's "missing key" convention is to
  // return the namespace-prefixed path (e.g. "Chat.errors.llm_unavailable"),
  // which is how we detect a missing translation without try/catch.
  const tErrors = useTranslations("Chat.errors");
  const localizedError = message.error
    ? (() => {
        const code = message.error.code;
        try {
          const translated = tErrors(
            code as Parameters<typeof tErrors>[0],
          );
          // next-intl returns the namespace-prefixed path when the
          // key is missing — that is our "fall back to message" signal.
          if (translated.startsWith("Chat.errors.")) {
            return message.error.message;
          }
          return translated;
        } catch {
          return message.error.message;
        }
      })()
    : null;

  return (
    <div className="flex flex-col gap-2">
      {/* Extracted query hint — shown early so user knows it understood */}
      {message.extractedQuery && !message.error && (
        <div className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-2">
          <span className="text-xs font-medium text-muted-foreground">
            Looking for:
          </span>
          <span className="text-sm font-medium text-foreground">
            {message.extractedQuery}
          </span>
          {isStreaming && <ThinkingDots />}
        </div>
      )}

      {/* Thinking / connecting / streaming indicator */}
      {showThinking && (
        <div className="flex items-center gap-2 rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
          {statusLabel ?? "Analyzing your request..."}
        </div>
      )}

      {/* Final explanation (only shown after done event arrives) */}
      {!isStreaming && message.content && (
        <div className="rounded-lg bg-muted px-4 py-3 text-sm text-foreground">
          {message.content}
        </div>
      )}

      {/* Job results */}
      {message.jobs && message.jobs.length > 0 && !isStreaming && (
        <div className="space-y-1.5 pt-1">
          <p className="text-xs font-semibold text-foreground">
            Matching jobs ({message.jobs.length})
          </p>
          <ul className="space-y-1">
            {message.jobs.map((job, idx) => {
              const isOpened = openedJobIds.has(job.id);
              return (
                <li key={`${job.id}-${idx}`}>
                  <Link
                    href={`/jobs/${job.id}`}
                    className="block rounded-md border border-border bg-card px-3 py-2.5 text-sm transition-colors hover:bg-accent"
                  >
                    <span className="mr-2 font-medium text-foreground">
                      {job.title}
                    </span>
                    {isOpened && (
                      <span className="inline-flex items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-700">
                        <Check className="h-3 w-3" />
                        Abierta
                      </span>
                    )}
                    <span className="ml-2 text-muted-foreground">
                      @ {job.company}
                    </span>
                    {job.location && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {job.location}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* No results message */}
      {message.jobs &&
        message.jobs.length === 0 &&
        !isStreaming &&
        !message.error && (
          <p className="rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
            No matching jobs found. Try a different description.
          </p>
        )}

      {/* Error state */}
      {message.error && localizedError && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {localizedError}
        </div>
      )}
    </div>
  );
}
