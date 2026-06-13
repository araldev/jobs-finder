"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  trend?: { value: number; isUp: boolean };
  iconClassName?: string;
  delay?: number;
}

export function StatCard({
  icon: Icon,
  label,
  value,
  trend,
  iconClassName,
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
      className="rounded-xl border bg-card p-4 shadow-sm"
    >
      <div
        className={cn(
          "mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-muted/50",
          iconClassName,
        )}
      >
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <p className="font-display text-2xl font-bold tracking-tight">{value}</p>
      <p className="mt-1 text-sm text-muted-foreground">{label}</p>
      {trend && (
        <p
          className={cn(
            "mt-1 text-xs font-medium",
            trend.isUp ? "text-secondary" : "text-destructive",
          )}
        >
          {trend.isUp ? "▲" : "▼"} {Math.abs(trend.value)}%
        </p>
      )}
    </motion.div>
  );
}
