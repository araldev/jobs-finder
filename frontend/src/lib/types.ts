/**
 * Frontend types, mirror of the backend Pydantic schemas.
 *
 * These types are maintained by hand and are the contract between the
 * browser and the Next.js Route Handlers. If a backend field changes,
 * the diff must land here in the same commit so the compiler catches
 * downstream breakage.
 *
 * The authoritative shapes live in the backend:
 *   - src/jobs_finder/presentation/schemas/job.py (JobResponse)
 *   - src/jobs_finder/presentation/schemas/aggregator.py (AggregatedJobResponse)
 *   - src/jobs_finder/presentation/schemas/chat_stream.py (SSE event payloads)
 *
 * The wire shapes we expose to the browser are intentionally a
 * smaller subset — fields the UI does not render (e.g. internal
 * scraper metadata) are stripped by the Route Handlers.
 */

export type Source = "linkedin" | "indeed" | "infojobs";

export const SOURCES: readonly Source[] = ["linkedin", "indeed", "infojobs"] as const;

/** Brand colors per source, used by the JobCard badge. */
export const SOURCE_BADGE_COLORS: Record<Source, string> = {
  linkedin: "bg-[#0a66c2] text-white",
  indeed: "bg-[#6b46c1] text-white",
  infojobs: "bg-[#f97316] text-white",
};

/**
 * One job posting aggregated across one or more sources.
 *
 * `url` (not `link`) matches the backend canonical JobResponse field.
 * `sources` is an array because a job can be deduped across N sources.
 */
export interface Job {
  readonly id: string;
  readonly title: string;
  readonly company: string;
  readonly location: string;
  readonly url: string;
  readonly sources: readonly Source[];
  readonly posted_at: string | null;
  readonly description: string | null;
}

/** Body of a successful `GET /api/jobs` response. */
export interface JobsResponse {
  readonly jobs: readonly Job[];
}

/** Value of the `X-Cache` header on /api/jobs. */
export type CacheStatus = "HIT" | "MISS";

/**
 * Client-friendly shape returned by the `useDebouncedJobsSearch` hook.
 * Mirrors the JobsResponse body but adds the cache status from the
 * `X-Cache` response header.
 */
export interface SearchResult {
  readonly jobs: readonly Job[];
  readonly cacheStatus: CacheStatus;
}

/* -------------------------------------------------------------------------
 * SSE chat streaming — payload shapes per the canonical
 * openspec/specs/chat-streaming/spec.md (REQ-SSE-001).
 *
 * The wire order is: meta? → text* → done | error.
 *
 * `done` carries the FULL jobs array (the backend filters and returns
 * the matched subset), not matching_ids. The frontend replaces the
 * current results grid with done.jobs when this event arrives.
 * --------------------------------------------------------------------- */

/** Parsed intent from the LLM, surfaced via the `meta` event. */
export interface ChatStreamMetaEvent {
  readonly intent: Readonly<Record<string, unknown>>;
  readonly intent_text: string;
}

/** One chunk of the LLM's natural-language response. */
export interface ChatStreamTextEvent {
  readonly delta: string;
}

/** Terminal happy-path event. */
export interface ChatStreamDoneEvent {
  readonly jobs: readonly Job[];
  readonly explanation: string;
  readonly total_considered: number;
  readonly total_matched: number;
  readonly used_fallback: boolean;
  readonly request_id: string;
}

/** Terminal error event. */
export interface ChatStreamErrorEvent {
  readonly code: string;
  readonly message: string;
  readonly request_id?: string;
}

/**
 * The `done` event from the backend OR the `200 {available: false}`
 * fallback the Route Handler returns when the backend has
 * `LLM_FILTER_ENABLED=false`. The forwarder discriminates the two
 * by the `available` field; the Route Handler guarantees the
 * frontend never sees a 404 from the chat endpoint.
 */
export type ChatDonePayload =
  | { readonly available: true; readonly event: ChatStreamDoneEvent }
  | { readonly available: false; readonly reason: "llm_disabled" };
