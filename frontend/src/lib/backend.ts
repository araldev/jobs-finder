/**
 * Server-only fetch wrapper around the FastAPI backend.
 *
 * `import "server-only"` is the Next.js guard that turns this module
 * into a build error if any client component ever imports it. The
 * browser must never bundle `process.env.BACKEND_URL` — it leaks the
 * server's view of the topology and the value can include a private
 * hostname in production.
 */
import "server-only";

/** The URL of the FastAPI backend. Configurable per environment. */
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Per-request timeout for backend calls. 30s is the upper bound the
 *  chat stream is allowed to take end-to-end (LLM + scrape + parse). */
const DEFAULT_TIMEOUT_MS = 30_000;

export interface BackendFetchInit {
  readonly method?: string;
  readonly headers?: Readonly<Record<string, string>>;
  readonly body?: BodyInit | null;
  readonly signal?: AbortSignal;
  readonly timeoutMs?: number;
  readonly forwardRequestId?: string | null;
}

export class BackendError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "BackendError";
    this.status = status;
  }
}

/**
 * Build a fetch() to the FastAPI backend with the project's
 * standard headers (X-Forwarded-By, optional X-Request-Id passthrough)
 * and a deadline.
 *
 * Throws BackendError on non-2xx. Returns the raw Response on success
 * so the caller can stream the body (used by the chat SSE route).
 */
export async function backendFetch(
  path: string,
  init: BackendFetchInit = {},
): Promise<Response> {
  const url = new URL(path, BACKEND_URL).toString();
  const headers = new Headers(init.headers);
  headers.set("X-Forwarded-By", "jobs-finder-frontend");
  if (init.forwardRequestId) {
    headers.set("X-Request-Id", init.forwardRequestId);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), init.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  // Chain the caller's signal into our internal one.
  if (init.signal) {
    if (init.signal.aborted) {
      clearTimeout(timer);
      controller.abort();
    } else {
      init.signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method: init.method ?? "GET",
      headers,
      body: init.body ?? null,
      signal: controller.signal,
      // Required because the backend may set cookies and we want
      // streaming responses to flow through.
      cache: "no-store",
    });
  } catch (cause) {
    if (cause instanceof Error && cause.name === "AbortError") {
      throw new BackendError(504, `Backend request to ${path} timed out`);
    }
    throw new BackendError(
      502,
      `Backend request to ${path} failed: ${cause instanceof Error ? cause.message : String(cause)}`,
    );
  } finally {
    clearTimeout(timer);
  }
  return res;
}
