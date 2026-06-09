"use client";

import { Search } from "lucide-react";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  readonly keywords: string;
  readonly onPickPrompt: (keywords: string, location: string) => void;
}

interface PromptChip {
  readonly label: string;
  readonly keywords: string;
  readonly location: string;
}

const PROMPT_CHIPS: readonly PromptChip[] = [
  { label: "Senior Python en Madrid", keywords: "Senior Python Developer", location: "Madrid" },
  { label: "Junior Frontend en Barcelona", keywords: "Junior Frontend Developer", location: "Barcelona" },
  { label: "Data Engineer, remoto", keywords: "Data Engineer", location: "Remote" },
];

export function EmptyState({ keywords, onPickPrompt }: EmptyStateProps): React.ReactElement {
  const hasQuery = keywords.trim().length > 0;
  return (
    <Empty className="rounded-2xl border border-dashed border-border/60 bg-card/40 py-12">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Search className="size-5" aria-hidden />
        </EmptyMedia>
        <EmptyTitle>
          {hasQuery ? `Sin resultados para "${keywords}"` : "Encuentra tu próximo puesto"}
        </EmptyTitle>
        <EmptyDescription>
          {hasQuery
            ? "Prueba con una búsqueda más amplia u otra ubicación."
            : "Busca en LinkedIn, Indeed e InfoJobs a la vez. Escribe palabras clave y una ubicación para empezar."}
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {PROMPT_CHIPS.map((chip) => (
            <Button
              key={chip.label}
              variant="outline"
              size="sm"
              className="rounded-full"
              onClick={() => onPickPrompt(chip.keywords, chip.location)}
            >
              {chip.label}
            </Button>
          ))}
        </div>
      </EmptyContent>
    </Empty>
  );
}
