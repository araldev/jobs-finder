"use client";

import { useCallback, type FormEvent } from "react";
import { Search, MapPin } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SearchBarProps {
  readonly keywords: string;
  readonly location: string;
  readonly onKeywordsChange: (value: string) => void;
  readonly onLocationChange: (value: string) => void;
  readonly isLoading: boolean;
  readonly onSubmit?: () => void;
}

/**
 * Two-input search form (keywords + location) + a Search button.
 * The form is controlled; the parent owns the values so the
 * debounce and the React Query subscription can react to them.
 * The submit handler is a no-op (the inputs already debounce) but
 * it lets users press Enter to feel productive and stops the
 * default form submit reload.
 */
export function SearchBar({
  keywords,
  location,
  onKeywordsChange,
  onLocationChange,
  isLoading,
  onSubmit,
}: SearchBarProps): React.ReactElement {
  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      onSubmit?.();
    },
    [onSubmit],
  );

  return (
    <form
      onSubmit={handleSubmit}
      className="grid w-full gap-3 sm:grid-cols-[1fr_18rem_auto] sm:items-end"
      role="search"
      aria-label="Buscar empleo"
    >
      <label className="flex flex-col gap-1.5 text-left">
        <span className="text-xs font-medium text-muted-foreground">
          Palabras clave
        </span>
        <span className="relative">
          <Search
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            value={keywords}
            onChange={(e) => onKeywordsChange(e.target.value)}
            placeholder="Backend, Junior, Remoto…"
            className={cn("pl-9")}
            aria-label="Palabras clave"
            maxLength={200}
            autoComplete="off"
            enterKeyHint="search"
          />
        </span>
      </label>
      <label className="flex flex-col gap-1.5 text-left">
        <span className="text-xs font-medium text-muted-foreground">
          Ubicación
        </span>
        <span className="relative">
          <MapPin
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            value={location}
            onChange={(e) => onLocationChange(e.target.value)}
            placeholder="Madrid, España"
            className={cn("pl-9")}
            aria-label="Ubicación"
            maxLength={200}
            autoComplete="off"
            enterKeyHint="search"
          />
        </span>
      </label>
      <Button
        type="submit"
        disabled={isLoading}
        className="h-10 sm:self-end"
      >
        Buscar
      </Button>
    </form>
  );
}
