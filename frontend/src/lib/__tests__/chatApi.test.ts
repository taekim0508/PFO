import { describe, expect, it, vi } from "vitest";
import { ChatRequestError, streamChat, type ChatEvent } from "../chatApi";

/** A Response whose body arrives in the given chunks, as a slow network would deliver it. */
function streamed(chunks: string[], init: ResponseInit = {}) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    ...init,
  });
}

async function collect(fetchImpl: typeof fetch, signal?: AbortSignal) {
  const events: ChatEvent[] = [];
  await streamChat({
    baseUrl: "http://api.test/",
    question: "Where did Tae go to school?",
    strategy: "dense",
    signal,
    fetchImpl,
    onEvent: (event) => events.push(event),
  });
  return events;
}

describe("streamChat", () => {
  it("posts the question as JSON to /api/chat", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(streamed([]));

    await collect(fetchImpl);

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://api.test/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      question: "Where did Tae go to school?",
      strategy: "dense",
    });
  });

  it("delivers typed events in order, across chunk boundaries", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        streamed([
          'event: sources\ndata: {"strategy":"dense","pass',
          'ages":[]}\n\nevent: delta\ndata: {"text":"Hi"}\n',
          '\nevent: done\ndata: {"cited":[]}\n\n',
        ]),
      );

    const events = await collect(fetchImpl);

    expect(events.map((e) => e.type)).toEqual(["sources", "delta", "done"]);
    expect(events[1]).toEqual({ type: "delta", payload: { text: "Hi" } });
  });

  it("decodes characters split across chunks", async () => {
    const bytes = new TextEncoder().encode('event: delta\ndata: {"text":"Résumé"}\n\n');
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    });
    const fetchImpl = vi.fn().mockResolvedValue(new Response(body));

    const events = await collect(fetchImpl);

    expect(events).toEqual([{ type: "delta", payload: { text: "Résumé" } }]);
  });

  it("skips unknown events and malformed JSON instead of failing the answer", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        streamed([
          "event: ping\ndata: {}\n\n",
          "event: delta\ndata: {not json\n\n",
          'event: delta\ndata: {"text":"ok"}\n\n',
        ]),
      );

    expect(await collect(fetchImpl)).toEqual([{ type: "delta", payload: { text: "ok" } }]);
  });

  it("reports a rate limit with its message and wait", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "rate_limited", message: "Please wait." } }), {
        status: 429,
        headers: { "Retry-After": "42" },
      }),
    );

    const error = await collect(fetchImpl).catch((e) => e);

    expect(error).toBeInstanceOf(ChatRequestError);
    expect(error.kind).toBe("rate_limited");
    expect(error.message).toBe("Please wait.");
    expect(error.retryAfterSeconds).toBe(42);
  });

  it("reports refused input with the server's message", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ error: { code: "invalid_request", message: "the question is empty" } }),
          { status: 422 },
        ),
      );

    const error = await collect(fetchImpl).catch((e) => e);

    expect(error.kind).toBe("invalid");
    expect(error.message).toBe("the question is empty");
  });

  it("turns a network failure into a readable error", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    const error = await collect(fetchImpl).catch((e) => e);

    expect(error.kind).toBe("network");
    expect(error.message).not.toContain("Failed to fetch");
  });

  it("turns a connection dropped mid-answer into a readable error", async () => {
    let sent = false;
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (!sent) {
          sent = true;
          controller.enqueue(new TextEncoder().encode('event: delta\ndata: {"text":"Tae "}\n\n'));
        } else {
          controller.error(new TypeError("network error"));
        }
      },
    });
    const events: ChatEvent[] = [];
    const error = await streamChat({
      baseUrl: "http://api.test",
      question: "q",
      fetchImpl: vi.fn().mockResolvedValue(new Response(body)),
      onEvent: (e) => events.push(e),
    }).catch((e) => e);

    expect(events).toEqual([{ type: "delta", payload: { text: "Tae " } }]);
    expect(error.kind).toBe("network");
  });

  it("lets an abort through untouched, so Stop is not reported as a failure", async () => {
    const controller = new AbortController();
    const fetchImpl = vi.fn().mockImplementation(async () => {
      controller.abort();
      throw new DOMException("aborted", "AbortError");
    });

    const error = await collect(fetchImpl, controller.signal).catch((e) => e);

    expect(error).toBeInstanceOf(DOMException);
    expect(error.name).toBe("AbortError");
  });
});
