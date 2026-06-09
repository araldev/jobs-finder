/**
 * Client-side API layer.
 *
 * The browser NEVER talks to the FastAPI backend directly. Every
 * call routes through a Next.js Route Handler, which:
 *   - hides the backend URL from the client bundle
 *   - avoids CORS preflights for non-GET verbs (the backend
 *     only allows `GET` cross-origin by default — see
 *     `backend/src/jobs_finder/presentation/middleware/cors.py`)
 *   - lets us translate backend 4xx/5xx shapes into the
 *     `ApiError` class below, so every component consumes a
 *     single, predictable error contract.
 */

import type { CacheStatus, Job, JobsResponse, SearchResult, Source } from "./types";
import { SOURCES } from "./types";

/** Error class thrown by the API layer on any non-2xx response. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly retryAfter: number | null;

  constructor(args: {
    status: number;
    code: string;
    message: string;
    requestId?: string | null;
    retryAfter?: number | null;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.code = args.code;
    this.requestId = args.requestId ?? null;
    this.retryAfter = args.retryAfter ?? null;
  }
}

/**
 * Map a backend response status + body into a friendly ApiError.
 * Centralised so every component shows the same Spanish-language
 * message and so the test suite has a single seam to cover.
 */
export function mapBackendError(
  status: number,
  body: unknown,
  requestId: string | null,
  retryAfter: number | null = null,
): ApiError {
  if (status === 401 || status === 403) {
    return new ApiError({
      status,
      code: status === 401 ? "unauthorized" : "forbidden",
      message: "Autenticación requerida",
      requestId,
    });
  }
  if (status === 404) {
    return new ApiError({
      status,
      code: "not_found",
      message: "Recurso no encontrado",
      requestId,
    });
  }
  if (status === 429) {
    const seconds =
      retryAfter !== null && Number.isFinite(retryAfter)
        ? Math.max(1, Math.round(retryAfter))
        : null;
    return new ApiError({
      status,
      code: "rate_limited",
      message:
        seconds !== null
          ? `Demasiadas solicitudes, espera ${seconds} segundos`
          : "Demasiadas solicitudes, intenta más tarde",
      requestId,
      retryAfter: seconds,
    });
  }
  if (status >= 500) {
    return new ApiError({
      status,
      code: "internal_error",
      message: "Error del servidor, intenta de nuevo",
      requestId,
    });
  }
  // 4xx other than the above — preserve the body as the code if it has one.
  const bodyCode =
    typeof body === "object" && body !== null && "code" in body
      ? String((body as { code: unknown }).code)
      : "bad_request";
  return new ApiError({
    status,
    code: bodyCode,
    message: readErrorMessage(body) ?? "Solicitud inválida",
    requestId,
  });
}

function readErrorMessage(body: unknown): string | null {
  if (typeof body === "object" && body !== null) {
    const record = body as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (typeof record.error === "string") return record.error;
  }
  return null;
}

/** Args for `fetchJobs` — all optional; defaults mirror the backend Pydantic schema. */
export interface FetchJobsArgs {
  readonly keywords?: string;
  readonly location?: string;
  readonly limit?: number;
  readonly sources?: readonly Source[];
}

function buildJobsQuery(args: FetchJobsArgs): string {
  const params = new URLSearchParams();
  if (args.keywords !== undefined && args.keywords.length > 0) {
    params.set("keywords", args.keywords);
  }
  if (args.location !== undefined && args.location.length > 0) {
    params.set("location", args.location);
  }
  if (args.limit !== undefined) {
    params.set("limit", String(args.limit));
  }
  if (args.sources !== undefined && args.sources.length > 0) {
    for (const source of args.sources) {
      if (SOURCES.includes(source)) {
        params.append("source", source);
      }
    }
  }
  const qs = params.toString();
  return qs.length > 0 ? `?${qs}` : "";
}

/**
 * GET /api/jobs. Returns the client-friendly SearchResult so the
 * caller can read the X-Cache header without a second pass.
 */
export async function fetchJobs(args: FetchJobsArgs = {}): Promise<SearchResult> {
  let res: Response;
  try {
    res = await fetch(`/api/jobs${buildJobsQuery(args)}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError({
      status: 0,
      code: "network_error",
      message: cause instanceof Error ? cause.message : "Network error",
    });
  }
  return parseJobsResponse(res);
}

/** Shared parse helper, also used by the tests. */
export async function parseJobsResponse(res: Response): Promise<SearchResult> {
  const requestId = res.headers.get("X-Request-Id");
  const cacheHeader = res.headers.get("X-Cache");
  const cacheStatus: CacheStatus = cacheHeader === "HIT" ? "HIT" : "MISS";

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    throw mapBackendError(res.status, body, requestId);
  }
  const body = (await res.json()) as JobsResponse;
  return { jobs: body.jobs, cacheStatus };
}

/** Args for `postChatMessageStream`. */
export interface PostChatMessageStreamArgs {
  readonly message: string;
  readonly signal?: AbortSignal;
}

/**
 * POST /api/chat/stream. Returns the raw Response so the caller
 * (the useChatStream hook) can drive the SSE forwarder over the
 * body stream. Throws ApiError on synchronous failure (network
 * down, abort, etc.) but propagates backend 4xx/5xx as a normal
 * Response so the stream can be parsed.
 */
export async function postChatMessageStream(
  args: PostChatMessageStreamArgs,
): Promise<Response> {
  try {
    return await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ message: args.message }),
      signal: args.signal,
    });
  } catch (cause) {
    throw new ApiError({
      status: 0,
      code: "network_error",
      message: cause instanceof Error ? cause.message : "Network error",
    });
  }
}

/** Re-export Job for callers that want to import from one place. */
export type { Job, SearchResult, JobsResponse, Source };
