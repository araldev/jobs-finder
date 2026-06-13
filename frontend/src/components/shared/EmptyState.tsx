"use client";

import { motion } from "framer-motion";
import { SearchX, Briefcase, AlertCircle, Inbox } from "lucide-react";
import type { ReactNode } from "react";

type EmptyVariant = "no-results" | "no-jobs" | "error" | "empty";

interface EmptyStateProps {
  variant?: EmptyVariant;
  title?: string;
  description?: string;
  action?: ReactNode;
}

const defaults: Record<EmptyVariant, { title: string; description: string; icon: typeof SearchX }> = {
  "no-results": {
    title: "No results found",
    description: "Try adjusting your search or filters",
    icon: SearchX,
  },
  "no-jobs": {
    title: "No jobs yet",
    description: "Jobs will appear here once they are scraped by the backend",
    icon: Briefcase,
  },
  error: {
    title: "Something went wrong",
    description: "Could not load data. Please try again.",
    icon: AlertCircle,
  },
  empty: {
    title: "Nothing here",
    description: "This section is empty",
    icon: Inbox,
  },
};

export function EmptyState({
  variant = "empty",
  title,
  description,
  action,
}: EmptyStateProps) {
  const config = defaults[variant];
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", bounce: 0.15, duration: 0.5 }}
      className="flex flex-col items-center justify-center py-16 text-center"
    >
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted/50">
        <Icon className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="font-display text-lg font-semibold">{title ?? config.title}</h3>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">
        {description ?? config.description}
      </p>
      {action && <div className="mt-4">{action}</div>}
    </motion.div>
  );
}
