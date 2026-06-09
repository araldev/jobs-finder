import { describe, expect, it, vi } from "vitest";
import { forwardChatStream, frameSseBlock } from "@/lib/chat-stream-forwarder";
import type {
  ChatStreamDoneEvent,
  ChatStreamMetaEvent,
  ChatStreamTextEvent,
} from "@/lib/types";

/**
 * Build a Response whose body is a `ReadableStream` pre-loaded
 * with the supplied SSE blocks (each block must end with the
 * `\n\n` separator the wire format uses).
 */
function sseResponse(
  blocks: readonly string[],
  init: { status?: number } = {},
): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const block of blocks) {
        controller.enqueue(encoder.encode(block));
      }
      controller.close();
    },
  });
  return new Response(body, { status: init.status ?? 200 });
}

/**
 * Build a `controller + enqueue` pair without using the
 * constructor directly (which is illegal in Node). The pair
 * captures all chunks the forwarder writes so tests can assert
 * on the wire bytes it produced.
 */
function captureSink(): {
  controller: ReadableStreamDefaultController<Uint8Array>;
  enqueue: (chunk: string) => void;
  chunks: string[];
} {
  const chunks: string[] = [];
  const captured: { controller: ReadableStreamDefaultController<Uint8Array> | null } = {
    controller: null,
  };
  // Build a real ReadableStream so we get a legal controller.
  // The stream never closes — the forwarder must finish writing
  // and the test ends.
  new ReadableStream<Uint8Array>({
    start(ctrl) {
      captured.controller = ctrl;
    },
  });
  if (captured.controller === null) {
    throw new Error("ReadableStream controller was not created");
  }
  const controller = captured.controller;
  return {
    controller,
    enqueue: (chunk: string) => {
      chunks.push(chunk);
      try {
        controller.enqueue(new TextEncoder().encode(chunk));
      } catch {
        // controller may be closed; ignore for the test sink.
      }
    },
    chunks,
  };
}

describe("forwardChatStream", () => {
  it("parses a meta event and calls onMeta with the payload", async () => {
    const events: ChatStreamMetaEvent[] = [];
    const sink = captureSink();

    await forwardChatStream({
      backendResponse: sseResponse([
        `event: meta\ndata: ${JSON.stringify({ intent: { city: "Madrid" }, intent_text: "Madrid" })}\n\n`,
      ]),
      controller: sink.controller,
      enqueue: sink.enqueue,
      callbacks: {
        onMeta: (e) => events.push(e),
        onText: () => {},
        onDone: () => {},
        onError: () => {},
      },
    });

    expect(events).toHaveLength(1);
    expect(events[0]?.intent_text).toBe("Madrid");
  });

  it("parses text events and concatenates the deltas", async () => {
    const textEvents: ChatStreamTextEvent[] = [];
    const donePayloads: unknown[] = [];
    const sink = captureSink();

    await forwardChatStream({
      backendResponse: sseResponse([
        `event: text\ndata: ${JSON.stringify({ delta: "hola " })}\n\n`,
        `event: text\ndata: ${JSON.stringify({ delta: "mundo" })}\n\n`,
        `event: done\ndata: ${JSON.stringify({
          jobs: [],
          explanation: "",
          total_considered: 0,
          total_matched: 0,
          used_fallback: false,
          request_id: "r1",
        })}\n\n`,
      ]),
      controller: sink.controller,
      enqueue: sink.enqueue,
      callbacks: {
        onText: (e) => textEvents.push(e),
        onDone: (p) => donePayloads.push(p),
        onError: () => {},
      },
    });

    expect(textEvents.map((e) => e.delta).join("")).toBe("hola mundo");
    expect(donePayloads).toHaveLength(1);
  });

  it("parses a done event and calls onDone with the canonical payload", async () => {
    const donePayloads: unknown[] = [];
    const sink = captureSink();
    const doneShape: ChatStreamDoneEvent = {
      jobs: [
        {
          id: "j1",
          title: "Junior",
          company: "Acme",
          location: "Madrid",
          url: "https://example.com",
          sources: ["linkedin"],
          posted_at: null,
          description: null,
        },
      ],
      explanation: "filtered by location",
      total_considered: 100,
      total_matched: 1,
      used_fallback: false,
      request_id: "r2",
    };

    await forwardChatStream({
      backendResponse: sseResponse([
        `event: done\ndata: ${JSON.stringify(doneShape)}\n\n`,
      ]),
      controller: sink.controller,
      enqueue: sink.enqueue,
      callbacks: {
        onText: () => {},
        onDone: (p) => donePayloads.push(p),
        onError: () => {},
      },
    });

    expect(donePayloads).toHaveLength(1);
    const payload = donePayloads[0] as { available: true; event: ChatStreamDoneEvent };
    expect(payload.available).toBe(true);
    expect(payload.event.request_id).toBe("r2");
    expect(payload.event.jobs[0]?.id).toBe("j1");
  });

  it("parses an error event and calls onError", async () => {
    const errorSpy = vi.fn();
    const sink = captureSink();

    await forwardChatStream({
      backendResponse: sseResponse([
        `event: error\ndata: ${JSON.stringify({ code: "llm_unavailable", message: "model down" })}\n\n`,
      ]),
      controller: sink.controller,
      enqueue: sink.enqueue,
      callbacks: {
        onText: () => {},
        onDone: () => {},
        onError: errorSpy,
      },
    });

    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy.mock.calls[0]?.[0]).toMatchObject({ code: "llm_unavailable" });
  });

  it("aborts cleanly when the signal fires", async () => {
    const errorSpy = vi.fn();
    const sink = captureSink();
    const controller = new AbortController();

    // The body emits once then never resolves; the abort
    // listener in the forwarder must break the in-flight read.
    const body = new ReadableStream<Uint8Array>({
      start(ctrl) {
        ctrl.enqueue(new TextEncoder().encode("event: text\ndata: {\"delta\":\"\"}\n\n"));
      },
    });
    const res = new Response(body);

    const promise = forwardChatStream({
      backendResponse: res,
      controller: sink.controller,
      enqueue: sink.enqueue,
      signal: controller.signal,
      callbacks: {
        onText: () => {},
        onDone: () => {},
        onError: errorSpy,
      },
    });

    // Give the forwarder a tick to enter reader.read(), then abort.
    await new Promise((r) => setTimeout(r, 5));
    controller.abort();
    await promise;
    expect(errorSpy).toHaveBeenCalled();
  });

  it("emits onDone({available: false}) defensively when status is 404", async () => {
    const donePayloads: unknown[] = [];
    const errorSpy = vi.fn();
    const sink = captureSink();

    await forwardChatStream({
      backendResponse: sseResponse([], { status: 404 }),
      controller: sink.controller,
      enqueue: sink.enqueue,
      callbacks: {
        onText: () => {},
        onDone: (p) => donePayloads.push(p),
        onError: errorSpy,
      },
    });

    expect(donePayloads).toHaveLength(1);
    expect(donePayloads[0]).toEqual({ available: false, reason: "llm_disabled" });
    expect(errorSpy).not.toHaveBeenCalled();
  });
});

describe("frameSseBlock", () => {
  it("emits a single SSE block", () => {
    const out = frameSseBlock("text", { delta: "hi" });
    expect(out).toBe(`event: text\ndata: ${JSON.stringify({ delta: "hi" })}\n\n`);
  });
});
