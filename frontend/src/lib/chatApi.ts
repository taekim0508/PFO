/**
 * The browser's side of POST /api/chat: send a question, receive the answer as events.
 *
 * `fetch` rather than `EventSource`, because EventSource can only make GET requests. The
 * response body is read as a stream and fed to the SSE parser as bytes arrive, so each
 * event reaches the page the moment the server writes it.
 *
 * The event payloads mirror backend/src/portfolio_bot/api/schemas.py.
 */

import { createSseParser } from "./sse";

export type Strategy = "dense" | "lexical" | "hybrid";

export type Passage = {
  label: number;
  title: string;
  heading_path: string[];
  source_path: string;
  location: string;
  text: string;
  score: number;
  provenance: { strategy: string; rank: number }[];
};

export type SourcesEvent = { strategy: string; passages: Passage[] };
export type DoneEvent = {
  no_context: boolean;
  model: string | null;
  finish_reason: string | null;
  prompt_version: string;
  cited: number[];
  invalid_citations: number[];
  retrieval_ms: number;
  first_text_ms: number | null;
  total_ms: number;
};
export type ErrorEvent = { code: string; message: string };

export type ChatEvent =
  | { type: "sources"; payload: SourcesEvent }
  | { type: "delta"; payload: { text: string } }
  | { type: "done"; payload: DoneEvent }
  | { type: "error"; payload: ErrorEvent };

/** Why a question could not even start streaming. `message` is safe to show. */
export class ChatRequestError extends Error {
  constructor(
    readonly kind: "rate_limited" | "invalid" | "network" | "server",
    message: string,
    readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ChatRequestError";
  }
}

type StreamChatOptions = {
  baseUrl: string;
  question: string;
  strategy?: Strategy;
  k?: number;
  signal?: AbortSignal;
  onEvent: (event: ChatEvent) => void;
  fetchImpl?: typeof fetch;
};

const KNOWN_EVENTS = new Set(["sources", "delta", "done", "error"]);

/**
 * Resolves when the stream ends. Throws `ChatRequestError` when the request is refused or
 * the network fails, and lets an `AbortError` through when `signal` stops it, so the caller
 * can tell "the visitor pressed Stop" from "something broke".
 */
export async function streamChat(options: StreamChatOptions): Promise<void> {
  const { baseUrl, question, strategy, k, signal, onEvent, fetchImpl = fetch } = options;

  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl.replace(/\/$/, "")}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, strategy, k }),
      signal,
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ChatRequestError("network", "Can't reach the chat right now. Check your connection.");
  }

  if (!response.ok) throw await refusal(response);
  if (!response.body) throw new ChatRequestError("server", "The chat sent an empty reply.");

  const parser = createSseParser(({ event, data }) => {
    if (!KNOWN_EVENTS.has(event)) return;
    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      return; // a malformed frame is skipped rather than ending the answer
    }
    onEvent({ type: event, payload } as ChatEvent);
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.end();
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ChatRequestError("network", "The connection dropped while the answer was coming in.");
  } finally {
    reader.releaseLock();
  }
}

async function refusal(response: Response): Promise<ChatRequestError> {
  let message: string | undefined;
  try {
    const body = (await response.json()) as { error?: { message?: string } };
    message = body.error?.message;
  } catch {
    // Not JSON; fall through to a generic message.
  }
  if (response.status === 429) {
    const retry = Number(response.headers.get("Retry-After"));
    return new ChatRequestError(
      "rate_limited",
      message ?? "You've asked a lot of questions quickly. Please wait.",
      Number.isFinite(retry) && retry > 0 ? retry : undefined,
    );
  }
  if (response.status === 422) {
    return new ChatRequestError("invalid", message ?? "That question couldn't be sent.");
  }
  return new ChatRequestError("server", "Something went wrong. Please try again.");
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
