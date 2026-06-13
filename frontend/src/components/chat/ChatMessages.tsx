"use client";

import type { ChatMessage, ChatStatus } from "@/types/chat";
import { AssistantMessage } from "./AssistantMessage";

interface ChatMessagesProps {
  messages: ChatMessage[];
  status: ChatStatus;
  openedJobIds: Set<string>;
}

export function ChatMessages({ messages, status, openedJobIds }: ChatMessagesProps) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <p className="text-center text-sm text-muted-foreground">
          Describe the job you are looking for in natural language.
        </p>
      </div>
    );
  }

  const isStreaming = status === "streaming" || status === "connecting";

  const statusLabel =
    status === "connecting"
      ? "Analyzing your request..."
      : status === "streaming"
        ? "Searching for matching jobs..."
        : undefined;

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      {messages.map((msg, i) => {
        const isLastAssistant =
          i === messages.length - 1 && msg.role === "assistant";

        if (msg.role === "user") {
          return (
            <div
              key={msg.id}
              className="flex justify-end"
            >
              <div className="max-w-[80%] rounded-lg bg-primary px-4 py-3 text-sm text-primary-foreground">
                {msg.content}
              </div>
            </div>
          );
        }

        return (
          <div key={msg.id} className="flex justify-start">
            <div className="max-w-[85%]">
              <AssistantMessage
                message={msg}
                isStreaming={isLastAssistant && isStreaming}
                statusLabel={isLastAssistant ? statusLabel : undefined}
                openedJobIds={openedJobIds}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
