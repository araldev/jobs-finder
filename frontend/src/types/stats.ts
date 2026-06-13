export interface DashboardStats {
  readonly total_jobs: number;
  readonly jobs_today: number;
  readonly active_platforms: number;
  readonly last_sync: string | null;
  readonly platform_distribution: Record<string, number>;
}
