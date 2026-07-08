import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Import AFTER mocking fetch
import { fetchUrlContent } from "../url-fetch";

function makeResponse({
  body = "<html><title>Test Title</title><body>Hello world</body></html>",
  contentType = "text/html",
  status = 200,
  contentLength,
}: {
  body?: string;
  contentType?: string;
  status?: number;
  contentLength?: string;
} = {}): Response {
  const headers = new Headers({ "content-type": contentType });
  if (contentLength !== undefined) {
    headers.set("content-length", contentLength);
  }
  return new Response(body, { status, headers });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("fetchUrlContent — HTML stripping + title extraction", () => {
  it("extracts title and stripped text content from HTML", async () => {
    mockFetch.mockResolvedValueOnce(
      makeResponse({
        body: `<html>
          <head><title>Software Engineer at Acme</title></head>
          <body><p>We are looking for a senior engineer.</p></body>
        </html>`,
      }),
    );

    const result = await fetchUrlContent("https://example.com/job/123");
    expect(result.success).toBe(true);
    expect(result.title).toBe("Software Engineer at Acme");
    expect(result.textContent).toContain("senior engineer");
    expect(result.textContent).not.toContain("<title>");
    expect(result.textContent).not.toContain("</p>");
  });

  it("returns title: null when HTML has no <title> tag", async () => {
    mockFetch.mockResolvedValueOnce(
      makeResponse({
        body: "<html><body>No title here</body></html>",
      }),
    );

    const result = await fetchUrlContent("https://example.com");
    expect(result.success).toBe(true);
    expect(result.title).toBeNull();
    expect(result.textContent).toBe("No title here");
  });

  it("strips all HTML tags and collapses whitespace", async () => {
    mockFetch.mockResolvedValueOnce(
      makeResponse({
        body: "<div>Hello</div><div>  World  </div><style>.hidden{display:none}</style>",
      }),
    );

    const result = await fetchUrlContent("https://example.com");
    expect(result.success).toBe(true);
    expect(result.textContent).toContain("Hello");
    expect(result.textContent).toContain("World");
    expect(result.textContent).not.toContain("<div>");
    expect(result.textContent).not.toContain("<style>");
    // Whitespace is collapsed
    expect(result.textContent).not.toMatch(/  /);
  });

  it("caps textContent at 10_000 characters", async () => {
    const longText = "A".repeat(15_000);
    const html = `<html><body>${longText}</body></html>`;
    mockFetch.mockResolvedValueOnce(makeResponse({ body: html }));

    const result = await fetchUrlContent("https://example.com");
    expect(result.success).toBe(true);
    expect(result.textContent.length).toBeLessThanOrEqual(10_000);
  });
});

describe("fetchUrlContent — error handling", () => {
  it("returns success: false on network error", async () => {
    mockFetch.mockRejectedValueOnce(new TypeError("fetch failed"));

    const result = await fetchUrlContent("https://example.com");
    expect(result.success).toBe(false);
    expect(result.title).toBeNull();
    expect(result.textContent).toBe("");
  });

  it("returns success: false on timeout", async () => {
    mockFetch.mockRejectedValueOnce(new DOMException("The operation was aborted", "AbortError"));

    const result = await fetchUrlContent("https://example.com");
    expect(result.success).toBe(false);
  });

  it("returns success: false on non-HTML content-type", async () => {
    mockFetch.mockResolvedValueOnce(makeResponse({ contentType: "application/json" }));

    const result = await fetchUrlContent("https://example.com/data.json");
    expect(result.success).toBe(false);
  });

  it("returns success: false on HTTP error status", async () => {
    mockFetch.mockResolvedValueOnce(makeResponse({ status: 404 }));

    const result = await fetchUrlContent("https://example.com/missing");
    expect(result.success).toBe(false);
  });

  it("returns success: false on empty response body", async () => {
    mockFetch.mockResolvedValueOnce(makeResponse({ body: "" }));

    const result = await fetchUrlContent("https://example.com/empty");
    expect(result.success).toBe(false);
  });

  it("returns success: false when body consists only of whitespace after tag stripping", async () => {
    mockFetch.mockResolvedValueOnce(
      makeResponse({ body: "<html><body>   </body></html>" }),
    );

    const result = await fetchUrlContent("https://example.com");
    expect(result.success).toBe(false);
  });

  it("returns success: false on response larger than 5MB", async () => {
    // Simulate a 6MB body
    const largeBody = "x".repeat(6 * 1024 * 1024);
    mockFetch.mockResolvedValueOnce(makeResponse({ body: largeBody }));

    const result = await fetchUrlContent("https://example.com/large");
    expect(result.success).toBe(false);
  });

  it("returns success: false when content-length header indicates > 5MB", async () => {
    mockFetch.mockResolvedValueOnce(
      makeResponse({
        body: "small body",
        contentLength: String(6 * 1024 * 1024),
      }),
    );

    const result = await fetchUrlContent("https://example.com/claimed-large");
    expect(result.success).toBe(false);
  });
});
