"use client";

import { Heart } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { useFavorites } from "@/hooks/useFavorites";
import type { Job } from "@/types/job";

interface FavoriteButtonProps {
  job: Job;
  size?: "sm" | "md";
  className?: string;
}

export function FavoriteButton({ job, size = "md", className }: FavoriteButtonProps) {
  const { isFavorite, toggleFavorite } = useFavorites();
  const t = useTranslations("Jobs.favorite");
  const favorited = isFavorite(job.id);

  const sizeClasses = size === "sm" ? "h-4 w-4" : "h-5 w-5";
  const buttonSize = size === "sm" ? "h-8 w-8" : "h-9 w-9";

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    toggleFavorite(job);
    toast.success(favorited ? t("remove") : t("add"));
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={favorited ? t("remove") : t("add")}
      title={favorited ? t("remove") : t("add")}
      className={cn(
        "inline-flex items-center justify-center rounded-lg transition-colors hover:bg-muted",
        buttonSize,
        className,
      )}
    >
      <Heart
        className={cn(
          sizeClasses,
          "transition-colors",
          favorited
            ? "fill-destructive text-destructive"
            : "text-muted-foreground hover:text-destructive",
        )}
      />
    </button>
  );
}