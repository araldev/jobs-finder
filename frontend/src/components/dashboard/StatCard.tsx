"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  trend?: { value: number; isUp: boolean };
  /** Optional gradient class for the icon bubble + top accent bar. */
  accent?: "primary" | "secondary" | "muted" | "success" | "warning";
  delay?: number;
}

const ACCENT: Record<NonNullable<StatCardProps["accent"]>, string> = {
  primary: "from-primary/15 to-transparent bg-primary",
  secondary: "from-secondary/15 to-transparent bg-secondary",
  muted: "from-muted/30 to-transparent bg-muted-foreground",
  success: "from-emerald-500/15 to-transparent bg-emerald-500",
  warning: "from-amber-500/15 to-transparent bg-amber-500",
};

/**
 * A "metric tile" — visually distinct from job cards. No
 * border or shadow, just a subtle gradient + a thin top
 * accent bar that signals "this is a number, not a job".
 */
export function StatCard({
  icon: Icon,
  label,
  value,
  trend,
  accent = "primary",
  delay = 0,
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        stiffness: 300,
        damping: 25,
        delay,
      }}
      className="relative overflow-hidden rounded-xl bg-gradient-to-br from-card to-card/50 p-4 ring-1 ring-border/50"
    >
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-1",
          ACCENT[accent].split(" ").pop(),
        )}
        aria-hidden
      />

      <div
        className={cn(
          "mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br",
          ACCENT[accent],
        )}
      >
        <Icon className="h-5 w-5 text-foreground/80" />
      </div>
      <p className="font-display text-2xl font-bold tracking-tight text-foreground">
        {value}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">{label}</p>
      {trend && (
        <p
          className={cn(
            "mt-1 text-xs font-medium",
            trend.isUp ? "text-emerald-600" : "text-destructive",
          )}
        >
          {trend.isUp ? "▲" : "▼"} {Math.abs(trend.value)}%
        </p>
      )}
    </motion.div>
  );
}