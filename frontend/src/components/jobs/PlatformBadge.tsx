"use client";

import { useTranslations } from "next-intl";
import type { Source } from "@/types/job";
import { cn } from "@/lib/utils";

interface PlatformBadgeProps {
  platform: Source;
}

export function PlatformBadge({ platform }: PlatformBadgeProps) {
  const t = useTranslations("Dashboard.platforms");
  const colors: Record<Source, string> = {
    linkedin: "bg-[hsl(var(--linkedin))] text-white",
    indeed: "bg-[hsl(var(--indeed))] text-white",
    infojobs: "bg-[hsl(var(--infojobs))] text-white",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        colors[platform],
      )}
    >
      {t(platform as "linkedin" | "indeed" | "infojobs")}
    </span>
  );
}