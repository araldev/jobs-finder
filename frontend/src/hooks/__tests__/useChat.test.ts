import { describe, it, expect } from "vitest";
import { formatErrorMessage, ERROR_CODE_MAP } from "@/types/chat";
import { SSEParser } from "../useChat";

// ── Error mapping tests (task 4.3) ─────────────────────────────────

describe("formatErrorMessage", () => {
  it("returns message for llm_unavailable", () => {
    expect(formatErrorMessage("llm_unavailable")).toBe(
      "The AI assistant is currently unavailable. Please try again later.",
    );
  });

  it("returns message for llm_stream", () => {
    expect(formatErrorMessage("llm_stream")).toBe(
      "Connection interrupted while processing your request.",
    );
  });

  it("returns message for llm_parse", () => {
    expect(formatErrorMessage("llm_parse")).toBe(
      "The AI response couldn't be interpreted. Please rephrase.",
    );
  });

  it("returns message for llm_timeout", () => {
    expect(formatErrorMessage("llm_timeout")).toBe(
      "The request timed out. Try a simpler query.",
    );
  });

  it("returns message for stage1_parse", () => {
    expect(formatErrorMessage("stage1_parse")).toBe(
      "Couldn't understand that. Try being more specific.",
    );
  });

  it("returns message for internal", () => {
    expect(formatErrorMessage("internal")).toBe(
      "Something went wrong. Please try again.",
    );
  });

  it("returns default message for unknown code", () => {
    expect(formatErrorMessage("unknown_code")).toBe("Something went wrong. Please try again.");
  });
});

// ── SSE Parser tests (task 4.1) ────────────────────────────────────

describe("SSEParser", () => {
  describe("feed", () => {
    it("extracts a single complete SSE message", () => {
      const parser = new SSEParser();
      const raw = 'event: text\ndata: {"delta":"Hello"}\n\n';
      const messages = parser.feed(raw);

      expect(messages).toHaveLength(1);
      expect(messages[0]!.event).toBe("text");
      expect(messages[0]!.data).toBe('{"delta":"Hello"}');
    });

    it("extracts multiple messages from a single chunk", () => {
      const parser = new SSEParser();
      const raw = [
        'event: text\ndata: {"delta":"Hello"}\n\n',
        'event: done\ndata: {"jobs":[],"explanation":"Done"}\n\n',
      ].join("");

      const messages = parser.feed(raw);

      expect(messages).toHaveLength(2);
      expect(messages[0]!.event).toBe("text");
      expect(messages[1]!.event).toBe("done");
    });

    it("skips keepalive comment lines", () => {
      const parser = new SSEParser();
      const raw = ': keepalive\n\n';
      const messages = parser.feed(raw);

      expect(messages).toHaveLength(0);
    });

    it("skips keepalive comments mixed with real events", () => {
      const parser = new SSEParser();
      const raw = [
        ': keepalive\n\n',
        'event: text\ndata: {"delta":"A"}\n\n',
        ': another keepalive\n\n',
      ].join("");

      const messages = parser.feed(raw);

      expect(messages).toHaveLength(1);
      expect(messages[0]!.event).toBe("text");
      expect(messages[0]!.data).toBe('{"delta":"A"}');
    });

    it("ignores extra newlines between messages", () => {
      const parser = new SSEParser();
      const raw = 'event: text\ndata: {"delta":"A"}\n\n\n\n';
      const messages = parser.feed(raw);

      expect(messages).toHaveLength(1);
    });

    it("handles messages with no event field (default to undefined)", () => {
      const parser = new SSEParser();
      const raw = 'data: {"key":"value"}\n\n';
      const messages = parser.feed(raw);

      expect(messages).toHaveLength(1);
      expect(messages[0]!.event).toBeUndefined();
      expect(messages[0]!.data).toBe('{"key":"value"}');
    });
  });

  describe("streaming (chunked feed)", () => {
    it("buffers partial messages across multiple feed calls", () => {
      const parser = new SSEParser();

      // First chunk: partial data line only
      const first = parser.feed('event: text\ndata: {"del');
      expect(first).toHaveLength(0); // no complete message yet

      // Second chunk: completes the message
      const second = parser.feed('ta":"World"}\n\n');
      expect(second).toHaveLength(1);
      expect(second[0]!.event).toBe("text");
      expect(second[0]!.data).toBe('{"delta":"World"}');
    });

    it("handles three-part split across messages", () => {
      const parser = new SSEParser();

      parser.feed('event: text\ndata: {"del');
      const mid = parser.feed('ta":"Hel');
      expect(mid).toHaveLength(0);

      const last = parser.feed('lo"}\n\n');
      expect(last).toHaveLength(1);
    });
  });

  describe("flush", () => {
    it("returns remaining buffered data", () => {
      const parser = new SSEParser();
      parser.feed('event: text\ndata: {"delta":"A"}\n\n');
      const remaining = parser.feed('data: partial');
      expect(remaining).toHaveLength(0);

      const flushed = parser.flush();
      expect(flushed).toHaveLength(1);
      expect(flushed[0]!.data).toBe("partial");
    });

    it("returns empty when no buffered data", () => {
      const parser = new SSEParser();
      parser.feed('event: text\ndata: {"delta":"A"}\n\n');
      const flushed = parser.flush();

      expect(flushed).toHaveLength(0);
    });
  });
});
