"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Filter, MapPin, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import type { Source } from "@/types/job";
import { SOURCES } from "@/types/job";

export interface FilterValues {
  sources: Source[];
  location?: string;
}

interface FilterPanelProps {
  values: FilterValues;
  onChange: (values: FilterValues) => void;
}

const defaultValues: FilterValues = {
  sources: [],
  location: "",
};

export function FilterPanel({ values, onChange }: FilterPanelProps) {
  const t = useTranslations("Search");
  const tPlatform = useTranslations("Dashboard.platforms");
  const [open, setOpen] = useState(false);
  const hasFilters = values.sources.length > 0 || !!values.location;

  const toggleSource = (source: Source) => {
    const next = values.sources.includes(source)
      ? values.sources.filter((s) => s !== source)
      : [...values.sources, source];
    onChange({ ...values, sources: next });
  };

  const clearAll = () => {
    onChange(defaultValues);
  };

  const setLocation = (location: string) => {
    onChange({ ...values, location });
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Filter className="h-4 w-4" />
          {t("filters.platform")}
          {hasFilters && (
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
              {(values.sources.length > 0 ? values.sources.length : 0) + (values.location ? 1 : 0)}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72" align="start">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="font-display text-sm font-semibold">{t("filters.platform")}</h4>
            {hasFilters && (
              <Button variant="ghost" size="sm" className="h-auto px-2 py-1 text-xs" onClick={clearAll}>
                <X className="mr-1 h-3 w-3" />
                {t("clear")}
              </Button>
            )}
          </div>

          {/* Platforms */}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {t("filters.platform")}
            </p>
            <div className="space-y-1">
              {SOURCES.map((source) => (
                <label key={source} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={values.sources.includes(source)}
                    onChange={() => toggleSource(source)}
                    className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
                  />
                  {tPlatform(source as "linkedin" | "indeed" | "infojobs")}
                </label>
              ))}
            </div>
          </div>

          {/* Location */}
          <div>
            <p className="mb-2 flex items-center gap-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              <MapPin className="h-3 w-3" />
              {t("filters.salary")}
            </p>
            <Input
              placeholder={t("locationPlaceholder")}
              value={values.location ?? ""}
              onChange={(e) => setLocation(e.target.value)}
              className="h-9 text-sm"
            />
          </div>

          <Separator />
        </div>
      </PopoverContent>
    </Popover>
  );
}