"use client";

import { useCallback, useRef, useState } from "react";
import {
  ChatRequestError,
  streamChat,
  type DoneEvent,
  type Passage,
  type Strategy,
} from "./chatApi";

export type TurnStatus = "streaming" | "done" | "error" | "stopped";

export type Turn = {
  id: string;
  question: string;
  /** "answer" comes from the API; "overview" is the project list the page shows itself. */
  kind: "answer" | "overview";
  status: TurnStatus;
  text: string;
  passages: Passage[];
  strategy?: string;
  done?: DoneEvent;
  error?: string;
};

type Options = { baseUrl: string; strategy?: Strategy; fetchImpl?: typeof fetch };

/**
 * The conversation: one turn per question, the newest streaming in, and Stop.
 *
 * Each question is answered on its own; the API keeps no memory of earlier turns (the
 * roadmap defers conversation history). Only one answer streams at a time.
 */
export function useConversation({ baseUrl, strategy, fetchImpl }: Options) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const controller = useRef<AbortController | null>(null);
  const counter = useRef(0);

  const update = useCallback((id: string, change: (turn: Turn) => Partial<Turn>) => {
    setTurns((all) => all.map((turn) => (turn.id === id ? { ...turn, ...change(turn) } : turn)));
  }, []);

  const busy = turns.some((turn) => turn.status === "streaming");

  const ask = useCallback(
    async (question: string) => {
      if (controller.current) return; // one answer at a time
      const id = `turn-${++counter.current}`;
      const abort = new AbortController();
      controller.current = abort;
      setTurns((all) => [
        ...all,
        { id, question, kind: "answer", status: "streaming", text: "", passages: [] },
      ]);

      try {
        await streamChat({
          baseUrl,
          question,
          strategy,
          signal: abort.signal,
          fetchImpl,
          onEvent: (event) => {
            switch (event.type) {
              case "sources":
                update(id, () => ({
                  passages: event.payload.passages,
                  strategy: event.payload.strategy,
                }));
                break;
              case "delta":
                update(id, (turn) => ({ text: turn.text + event.payload.text }));
                break;
              case "done":
                update(id, () => ({ status: "done", done: event.payload }));
                break;
              case "error":
                update(id, () => ({ status: "error", error: event.payload.message }));
                break;
            }
          },
        });
        // A stream that closed without done or error was cut off in transit.
        update(id, (turn) =>
          turn.status === "streaming"
            ? { status: "error", error: "The answer was cut off. Please try again." }
            : {},
        );
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          update(id, () => ({ status: "stopped" }));
        } else {
          const message =
            error instanceof ChatRequestError
              ? error.message
              : "Something went wrong. Please try again.";
          update(id, () => ({ status: "error", error: message }));
        }
      } finally {
        controller.current = null;
      }
    },
    [baseUrl, strategy, fetchImpl, update],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  /** A turn the page fills itself, with no model call: the project overview. */
  const addOverview = useCallback((question: string, text: string) => {
    const id = `turn-${++counter.current}`;
    setTurns((all) => [
      ...all,
      { id, question, kind: "overview", status: "done", text, passages: [] },
    ]);
  }, []);

  const reset = useCallback(() => {
    controller.current?.abort();
    setTurns([]);
  }, []);

  return { turns, busy, ask, stop, addOverview, reset };
}
