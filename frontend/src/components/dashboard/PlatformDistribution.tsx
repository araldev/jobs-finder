"use client";

import { getPlatformColorClass } from "@/lib/formatters";

interface PlatformDistributionProps {
  distribution: Record<string, number>;
}

export function PlatformDistribution({ distribution }: PlatformDistributionProps) {
  const entries = Object.entries(distribution);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);

  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No data</p>;
  }

  return (
    <div className="space-y-3">
      {entries.map(([platform, count]) => {
        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
        return (
          <div key={platform}>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="capitalize">{platform}</span>
              <span className="font-mono text-xs text-muted-foreground">
                {count} ({pct}%)
              </span>
            </div>
            <div className="h-2 rounded-full bg-muted">
              <div
                className={`h-full rounded-full transition-all ${getPlatformColorClass(platform)}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
