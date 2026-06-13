"use client";

import Link from "next/link";
import type { ChatMessage } from "@/types/chat";

interface AssistantMessageProps {
  message: ChatMessage;
  isStreaming: boolean;
  statusLabel?: string;
}

export function AssistantMessage({
  message,
  isStreaming,
  statusLabel,
}: AssistantMessageProps) {
  // Show the status indicator while connecting / before first token
  const showStatus = isStreaming && !message.content && !message.extractedQuery;

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
          {isStreaming && (
            <span className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
              Searching...
            </span>
          )}
        </div>
      )}

      {/* Connecting / waiting for first token */}
      {showStatus && (
        <div className="flex items-center gap-2 rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
          {statusLabel ?? "Analyzing your request..."}
        </div>
      )}

      {/* Streaming content or final explanation */}
      {(message.content || (!showStatus && !message.error)) && (
        <div className="rounded-lg bg-muted px-4 py-3 text-sm text-foreground">
          {message.content || ""}
          {isStreaming && (
            <span
              data-testid="typing-indicator"
              className="ml-1 inline-block animate-pulse"
            >
              ▌
            </span>
          )}
        </div>
      )}

      {/* Job results */}
      {message.jobs && message.jobs.length > 0 && !isStreaming && (
        <div className="space-y-1.5 pt-1">
          <p className="text-xs font-semibold text-foreground">
            Matching jobs ({message.jobs.length})
          </p>
          <ul className="space-y-1">
            {message.jobs.map((job, idx) => (
              <li key={`${job.id}-${idx}`}>
                <Link
                  href={`/jobs/${job.id}`}
                  className="block rounded-md border border-border bg-card px-3 py-2.5 text-sm transition-colors hover:bg-accent"
                >
                  <span className="font-medium text-foreground">
                    {job.title}
                  </span>
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
            ))}
          </ul>
        </div>
      )}

      {/* No results message */}
      {message.jobs &&
        message.jobs.length === 0 &&
        !isStreaming &&
        !message.error &&
        message.content && (
          <p className="rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
            No matching jobs found. Try a different description.
          </p>
        )}

      {/* Error state */}
      {message.error && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {message.error.message}
        </div>
      )}
    </div>
  );
}
