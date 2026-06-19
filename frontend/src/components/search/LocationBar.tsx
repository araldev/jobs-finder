"use client";

import { MapPin, X } from "lucide-react";
import { Input } from "@/components/ui/input";

interface LocationBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

/**
 * Dashboard location filter. Sits next to the main `SearchBar`
 * and is intentionally case- AND accent-insensitive on the
 * backend ("malaga" matches "Málaga, Andalusia, Spain").
 */
export function LocationBar({
  value,
  onChange,
  placeholder = "Filter by location...",
}: LocationBarProps) {
  return (
    <div className="relative">
      <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="pl-9 pr-8"
        aria-label="Filter jobs by location"
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          aria-label="Clear location filter"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
