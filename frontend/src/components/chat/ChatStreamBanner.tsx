"use client";

import { motion } from "motion/react";
import { Sparkles } from "lucide-react";

interface ChatStreamBannerProps {
  readonly intentText: string;
}

/**
 * Animated banner above the message list. Shows the LLM's parsed
 * intent (e.g. "Buscando: Madrid, junior, …") so the user
 * understands what the model understood from their prompt.
 */
export function ChatStreamBanner({ intentText }: ChatStreamBannerProps): React.ReactElement {
  return (
    <motion.div
      role="status"
      aria-live="polite"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.15, ease: "easeOut" }}
      className="flex items-center gap-2 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-xs text-accent"
    >
      <motion.span
        aria-hidden
        animate={{ scale: [1, 1.18, 1] }}
        transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
        className="grid size-5 place-items-center rounded-full bg-accent/20"
      >
        <Sparkles className="size-3" />
      </motion.span>
      <span>Buscando: {intentText}</span>
    </motion.div>
  );
}
