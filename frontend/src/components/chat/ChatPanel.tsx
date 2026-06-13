"use client";

import { useEffect, useRef } from "react";
import { useChat } from "@/hooks/useChat";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessages } from "./ChatMessages";
import { ChatInput } from "./ChatInput";

export function ChatPanel() {
  const { messages, status, sendMessage, reset } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change or streaming
  useEffect(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector("[data-radix-scroll-area-viewport]");
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight;
      }
    }
  }, [messages, status]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">
            Job Assistant
          </h2>
          {status === "connecting" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
              Connecting
            </span>
          )}
          {status === "streaming" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
              Searching
            </span>
          )}
          {status === "done" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
              Done
            </span>
          )}
          {status === "error" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2.5 py-0.5 text-xs font-medium text-destructive">
              Error
            </span>
          )}
        </div>
        <button
          onClick={reset}
          className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          aria-label="Reset chat"
        >
          Reset
        </button>
      </div>

      <ScrollArea className="flex-1" ref={scrollRef}>
        <ChatMessages messages={messages} status={status} />
      </ScrollArea>

      <ChatInput
        onSend={sendMessage}
        disabled={status === "connecting" || status === "streaming"}
      />
    </div>
  );
}
