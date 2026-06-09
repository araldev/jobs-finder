"use client";

import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  readonly isStreaming: boolean;
  readonly disabled?: boolean;
  readonly onSend: (message: string) => void;
}

const MAX_LENGTH = 1_000;

/**
 * Auto-sizing textarea + Send button. Enter sends, Shift+Enter
 * inserts a newline. The button is disabled and shows a spinner
 * while a stream is in flight.
 */
export function ChatInput({
  isStreaming,
  disabled,
  onSend,
}: ChatInputProps): React.ReactElement {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const submit = useCallback(() => {
    const trimmed = value.trim();
    if (trimmed.length === 0 || isStreaming) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, isStreaming, onSend]);

  const handleKey = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submit();
      }
    },
    [submit],
  );

  const handleChange = useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      const next = event.target.value.slice(0, MAX_LENGTH);
      setValue(next);
      // Auto-grow: reset then expand to scrollHeight.
      const el = event.target;
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
    },
    [],
  );

  return (
    <div className="flex items-end gap-2 border-t border-border/60 bg-card/40 p-3">
      <label className="sr-only" htmlFor="chat-input">
        Mensaje para el chat
      </label>
      <textarea
        id="chat-input"
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKey}
        placeholder="Refina los resultados: «junior en Madrid», «remoto», «menos de 30 días»…"
        rows={1}
        disabled={disabled === true}
        maxLength={MAX_LENGTH}
        className="min-h-9 flex-1 resize-none rounded-xl border border-border/60 bg-background px-3 py-2 text-sm shadow-sm outline-none focus:border-accent focus:ring-2 focus:ring-ring/40 disabled:opacity-60"
      />
      <Button
        type="button"
        size="icon"
        onClick={submit}
        disabled={value.trim().length === 0 || isStreaming || disabled === true}
        aria-label="Enviar mensaje"
      >
        {isStreaming ? (
          <span
            aria-hidden
            className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
        ) : (
          <Send aria-hidden className="size-4" />
        )}
      </Button>
    </div>
  );
}
