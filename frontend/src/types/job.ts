export type Source = "linkedin" | "indeed" | "infojobs";

export const SOURCES: readonly Source[] = ["linkedin", "indeed", "infojobs"] as const;

export const SOURCE_BADGE_COLORS: Record<Source, string> = {
  linkedin: "bg-[hsl(var(--linkedin))] text-white",
  indeed: "bg-[hsl(var(--indeed))] text-white",
  infojobs: "bg-[hsl(var(--infojobs))] text-white",
};

export interface Job {
  readonly id: string;
  readonly source: Source;
  readonly title: string;
  readonly company: string;
  readonly location: string;
  readonly url: string;
  readonly posted_at: string | null;
  readonly description: string | null;
}

export interface HistoryResponse {
  readonly items: readonly Job[];
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
}

export interface SchedulerStatus {
  readonly enabled: boolean;
  readonly running: boolean;
  readonly total_in_db: number;
  readonly last_run_start: string | null;
  readonly last_run_end: string | null;
}
