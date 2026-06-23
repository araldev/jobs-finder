/** User-related types for the user-storage change. */

export interface UserFavorite {
  readonly id: number;
  readonly user_id: string;
  readonly job_id: number;
  readonly created_at: string;
}

export interface UserSettings {
  readonly enabled_platforms: readonly string[];
  readonly notifications_enabled: boolean;
}

export interface UserStats {
  readonly favorites_count: number;
  readonly job_views: number;
  readonly job_clicks: number;
  readonly searches: number;
  readonly cv_adapted: number;
  readonly top_favorite_sources: ReadonlyArray<{ source: string; count: number }>;
}

export type EngagementEventType = "job_view" | "job_click" | "search" | "cv_adapted";

export interface EngagementEvent {
  readonly id: number;
  readonly user_id: string;
  readonly event_type: EngagementEventType;
  readonly job_id: number | null;
  readonly metadata: Record<string, unknown>;
  readonly created_at: string;
}

export interface FavoritesListResponse {
  readonly data: readonly import("@/types/job").Job[];
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
}
