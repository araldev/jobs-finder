import "server-only";

interface FetchResult {
  title: string | null;
  textContent: string;
  success: boolean;
}

const MAX_RESPONSE_SIZE = 5 * 1024 * 1024; // 5 MB
const MAX_TEXT_CONTENT_LENGTH = 10_000; // chars
const FETCH_TIMEOUT_MS = 15_000;

/**
 * Fetch a URL and extract its textual content.
 *
 * Designed for job-offer URLs. Returns `success: false` on any
 * failure (timeout, network error, non-HTML content-type, empty
 * response, too-large response) so callers can fall back to
 * manual description input without exposing internal errors.
 *
 * Imported with `"server-only"` — never call this from a client
 * component or Route Handler directly (browsers enforce CORS;
 * this runs server-side in a Route Handler or Server Action).
 */
export async function fetchUrlContent(url: string): Promise<FetchResult> {
  let response: Response;

  try {
    response = await fetch(url, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
  } catch {
    // Network error or timeout
    return { title: null, textContent: "", success: false };
  }

  if (!response.ok) {
    return { title: null, textContent: "", success: false };
  }

  // Check Content-Type starts with text/html
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.startsWith("text/html")) {
    return { title: null, textContent: "", success: false };
  }

  // Read the body as text (limited to MAX_RESPONSE_SIZE)
  let html: string;
  try {
    const textPromise = response.text();

    // Check content-length header first for a cheap rejection
    const contentLength = response.headers.get("content-length");
    if (contentLength !== null && Number.parseInt(contentLength, 10) > MAX_RESPONSE_SIZE) {
      return { title: null, textContent: "", success: false };
    }

    html = await textPromise;
  } catch {
    return { title: null, textContent: "", success: false };
  }

  if (html.length > MAX_RESPONSE_SIZE) {
    return { title: null, textContent: "", success: false };
  }

  if (html.length === 0) {
    return { title: null, textContent: "", success: false };
  }

  // Extract <title> via regex
  const titleMatch = html.match(/<title>(.*?)<\/title>/is);
  const title = titleMatch ? titleMatch[1]!.trim() : null;

  // Strip all HTML tags
  const textContent = html
    .replace(/<\/?[^>]*>/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_TEXT_CONTENT_LENGTH);

  if (textContent.length === 0) {
    return { title: null, textContent: "", success: false };
  }

  return { title, textContent, success: true };
}
