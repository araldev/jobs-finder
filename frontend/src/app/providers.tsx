"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState, type ReactNode } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Client-only providers wrapping the app:
 *   - QueryClient (TanStack Query) with a 60s staleTime so users
 *     do not re-fetch on every focus change.
 *   - MotionConfig to centralise reduced-motion handling — all
 *     `motion.*` components respect it automatically.
 *   - Toaster from sonner for transient errors and notifications.
 *   - TooltipProvider from shadcn, required by the Tooltip primitive.
 *
 * Kept as a client component because QueryClient, Toaster, and
 * MotionConfig all need a browser context. The root layout stays
 * a server component.
 */
export function Providers({ children }: { children: ReactNode }): ReactNode {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <TooltipProvider delay={200}>
          {children}
          <Toaster position="top-right" richColors closeButton />
        </TooltipProvider>
      </MotionConfig>
    </QueryClientProvider>
  );
}
