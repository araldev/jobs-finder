"use client";

import { motion } from "motion/react";
import { type ReactNode } from "react";

interface PageEntryProps {
  readonly children: ReactNode;
}

/**
 * Page-level entry animation. Staggers its direct children top-to-
 * bottom with a 50ms delay so the topbar → search → results → chat
 * reveal feels intentional rather than synchronized. Respects
 * prefers-reduced-motion via the MotionConfig provider.
 */
export function PageEntry({ children }: PageEntryProps): React.ReactElement {
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: {
          transition: { staggerChildren: 0.05, delayChildren: 0.04 },
        },
      }}
      className="flex min-h-[calc(100vh-3.5rem)] flex-col"
    >
      {children}
    </motion.div>
  );
}

/**
 * Stagger item used by PageEntry's children. Wraps a child with a
 * vertical fade-in that respects the parent's stagger timing.
 */
export function PageEntryItem({
  children,
  className,
}: {
  readonly children: ReactNode;
  readonly className?: string;
}): React.ReactElement {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 6 },
        show: {
          opacity: 1,
          y: 0,
          transition: { duration: 0.25, ease: "easeOut" },
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
