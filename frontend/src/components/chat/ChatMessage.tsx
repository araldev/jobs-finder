"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

export type ChatRole = "user" | "assistant";

interface ChatMessageProps {
  readonly role: ChatRole;
  readonly text: string;
  readonly isStreaming?: boolean;
}

/**
 * A chat bubble. The user bubble is right-aligned and uses the
 * accent palette; the assistant bubble is left-aligned and uses
 * the card surface. The assistant bubble shows a soft pulsing
 * caret while the stream is still in flight so the user can see
 * the LLM is still typing.
 */
export function ChatMessage({
  role,
  text,
  isStreaming,
}: ChatMessageProps): React.ReactElement {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div
          className={cn(
            "max-w-[85%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-sm text-accent-foreground shadow-sm",
          )}
        >
          {text}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div
        className={cn(
          "max-w-[85%] rounded-2xl rounded-bl-md border border-border/60 bg-card px-3.5 py-2 text-sm shadow-sm",
        )}
      >
        <span className="whitespace-pre-wrap">{text}</span>
        {isStreaming ? (
          <motion.span
            aria-hidden
            animate={{ opacity: [0.2, 1, 0.2] }}
            transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
            className="ml-0.5 inline-block size-1.5 translate-y-[1px] rounded-full bg-accent"
          />
        ) : null}
      </div>
    </div>
  );
}
