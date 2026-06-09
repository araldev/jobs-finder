"use client";

import { Info } from "lucide-react";

interface NoChatAvailableProps {
  readonly reason: "llm_disabled";
}

/**
 * Friendly fallback when the backend reports the LLM filter is
 * disabled. Replaces the message list so the user knows why the
 * chat input is disabled; the search panel keeps working.
 */
export function NoChatAvailable({ reason }: NoChatAvailableProps): React.ReactElement {
  return (
    <div className="m-3 flex items-start gap-2 rounded-xl border border-border/60 bg-card/40 p-3 text-xs text-muted-foreground">
      <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-accent" />
      <div className="flex flex-col gap-1">
        <p className="font-medium text-foreground">El chat no está disponible ahora mismo</p>
        <p>
          {reason === "llm_disabled"
            ? "Activa el chat en el backend con LLM_FILTER_ENABLED=true y LLM_API_KEY=<tu-clave>."
            : "El servicio de chat no responde. Inténtalo de nuevo en unos minutos."}
        </p>
      </div>
    </div>
  );
}
