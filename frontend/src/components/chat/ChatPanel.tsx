"use client";

import { useCallback, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Sparkles } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { ChatInput } from "./ChatInput";
import { ChatMessage, type ChatRole } from "./ChatMessage";
import { ChatStreamBanner } from "./ChatStreamBanner";
import { NoChatAvailable } from "./NoChatAvailable";
import { useChatStream } from "@/hooks/useChatStream";
import { useJobsOverride } from "@/components/layout/JobsOverrideContext";
import type {
  ChatStreamErrorEvent,
  ChatStreamMetaEvent,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface ChatTurn {
  readonly id: string;
  readonly role: ChatRole;
  readonly text: string;
}

interface ChatPanelProps {
  readonly className?: string;
}

const PROMPT_CHIPS: readonly string[] = [
  "busco junior en Madrid",
  "remoto y en español",
  "menos de 30 días",
];

/**
 * Right-side chat panel. Holds the message list, the stream
 * banner, the chat input, and the SSE consumer hook. Glass
 * surface via the `.glass` utility.
 */
export function ChatPanel({ className }: ChatPanelProps): React.ReactElement {
  const [turns, setTurns] = useState<readonly ChatTurn[]>([]);
  const [metaText, setMetaText] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState<"llm_disabled" | null>(null);
  const { setOverride, clearOverride } = useJobsOverride();

  const handleMeta = useCallback((event: ChatStreamMetaEvent) => {
    setMetaText(event.intent_text || "interpretando la consulta…");
  }, []);

  const handleText = useCallback((event: { delta: string }) => {
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      if (last !== undefined && last.role === "assistant") {
        const updated: ChatTurn = { id: last.id, role: "assistant", text: last.text + event.delta };
        return prev.slice(0, -1).concat(updated);
      }
      return prev.concat({
        id: cryptoRandomId(),
        role: "assistant",
        text: event.delta,
      });
    });
  }, []);

  const handleDone = useCallback(
    (payload: { available: boolean; reason?: "llm_disabled" } | { available: true; event: import("@/lib/types").ChatStreamDoneEvent }) => {
      if ("reason" in payload && payload.reason === "llm_disabled") {
        setUnavailable("llm_disabled");
        setMetaText(null);
        return;
      }
      if ("event" in payload) {
        setOverride(payload.event.jobs);
        setMetaText(null);
        // Append the LLM's final explanation as a new assistant turn
        // so the user sees what the model said about the filter.
        if (payload.event.explanation.length > 0) {
          setTurns((prev) =>
            prev.concat({
              id: cryptoRandomId(),
              role: "assistant",
              text: payload.event.explanation,
            }),
          );
        }
      }
    },
    [setOverride],
  );

  const handleError = useCallback(async (event: ChatStreamErrorEvent) => {
    setErrorCode(event.code);
    setMetaText(null);
  }, []);

  const { isStreaming, send } = useChatStream({
    onMeta: handleMeta,
    onText: handleText,
    onDone: handleDone as Parameters<typeof useChatStream>[0]["onDone"],
    onError: handleError,
  });

  const handleSend = useCallback(
    (message: string) => {
      setErrorCode(null);
      setUnavailable(null);
      setMetaText(null);
      setTurns((prev) =>
        prev.concat({ id: cryptoRandomId(), role: "user", text: message }),
      );
      void send(message);
    },
    [send],
  );

  const handleReset = useCallback(() => {
    clearOverride();
  }, [clearOverride]);

  const showUnavailable = unavailable !== null;
  const showEmpty = turns.length === 0 && !isStreaming && !showUnavailable && errorCode === null;

  return (
    <aside
      className={cn(
        "glass flex h-[70vh] min-h-120 flex-col overflow-hidden rounded-2xl border-border/60",
        className,
      )}
      aria-label="Panel de chat"
    >
      <header className="flex items-center gap-2 border-b border-border/60 px-4 py-3 text-sm font-medium">
        <Sparkles aria-hidden className="size-4 text-accent" />
        Refinar resultados
      </header>
      <div className="flex flex-1 flex-col">
        <ScrollArea className="flex-1 px-4 py-3">
          <div className="flex flex-col gap-3">
            <AnimatePresence>{metaText !== null ? <ChatStreamBanner key="meta" intentText={metaText} /> : null}</AnimatePresence>
            {turns.map((turn) => (
              <ChatMessage
                key={turn.id}
                role={turn.role}
                text={turn.text}
                isStreaming={isStreaming && turn.role === "assistant" && turn === turns[turns.length - 1]}
              />
            ))}
            {showUnavailable ? <NoChatAvailable reason="llm_disabled" /> : null}
            {errorCode !== null && !showUnavailable ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                <p className="font-medium">No pudimos procesar la consulta</p>
                <p className="opacity-80">Código: {errorCode}</p>
              </div>
            ) : null}
            {showEmpty ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 py-8 text-center text-sm text-muted-foreground">
                <Sparkles aria-hidden className="size-5 text-accent" />
                <p className="max-w-xs">
                  Refina tus resultados en lenguaje natural. Algunos ejemplos para empezar:
                </p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {PROMPT_CHIPS.map((chip) => (
                    <Button
                      key={chip}
                      variant="outline"
                      size="sm"
                      className="rounded-full"
                      onClick={() => handleSend(chip)}
                    >
                      {chip}
                    </Button>
                  ))}
                </div>
              </div>
            ) : null}
            {isStreaming && turns.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-xs text-muted-foreground"
              >
                Esperando respuesta…
              </motion.div>
            ) : null}
          </div>
        </ScrollArea>
        {errorCode !== null || showUnavailable ? (
          <div className="flex items-center justify-end border-t border-border/60 bg-card/40 px-3 py-2 text-xs">
            <Button variant="ghost" size="sm" onClick={handleReset}>
              Limpiar filtro
            </Button>
          </div>
        ) : null}
        <ChatInput
          isStreaming={isStreaming}
          disabled={showUnavailable}
          onSend={handleSend}
        />
      </div>
    </aside>
  );
}

function cryptoRandomId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}
