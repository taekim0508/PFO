"use client";

import type { ReactNode } from "react";
import type { Turn } from "@/lib/useConversation";
import { AnswerText } from "./AnswerText";
import { Chip } from "./Chip";

type ConversationProps = {
  turns: Turn[];
  busy: boolean;
  onAsk: (question: string) => void;
  onCite: (turn: Turn, label: number) => void;
  /** Suggested next questions for a finished turn. */
  followUps: (turn: Turn) => string[];
  /** Anything shown beneath a turn's answer: project cards, the sources panel. */
  extras?: (turn: Turn) => ReactNode;
};

/** Questions as small gray labels, answers as editorial text, hairlines between. No bubbles. */
export function Conversation({ turns, busy, onAsk, onCite, followUps, extras }: ConversationProps) {
  return (
    <ol className="mt-8" aria-label="Conversation">
      {turns.map((turn, index) => {
        const last = index === turns.length - 1;
        const streaming = turn.status === "streaming";
        const suggestions = last && turn.status === "done" ? followUps(turn) : [];
        return (
          <li
            key={turn.id}
            className="animate-rise border-t border-hairline py-8 first:border-t-0 first:pt-2"
            aria-labelledby={`${turn.id}-q`}
          >
            <p id={`${turn.id}-q`} className="text-sm text-muted">
              {turn.question}
            </p>

            <div
              className="mt-3 text-[17px] leading-[1.7] text-ink"
              aria-live={last ? "polite" : undefined}
              aria-busy={streaming}
            >
              {turn.text ? (
                <AnswerText
                  text={turn.text}
                  labels={turn.passages.map((p) => p.label)}
                  onCite={(label) => onCite(turn, label)}
                />
              ) : streaming ? (
                <Thinking />
              ) : null}
              {streaming && turn.text && (
                <span
                  aria-hidden
                  className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-accent align-[-0.15em]"
                />
              )}
            </div>

            {turn.status === "error" && (
              <p role="alert" className="mt-4 flex flex-wrap items-center gap-3 text-sm text-ink">
                <span>{turn.error}</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onAsk(turn.question)}
                  className="rounded-full border border-hairline-strong px-3 py-1 text-sm hover:bg-peach-tint disabled:opacity-50"
                >
                  Try again
                </button>
              </p>
            )}
            {turn.status === "stopped" && <p className="mt-3 text-sm text-muted">Stopped.</p>}

            {extras?.(turn)}

            {suggestions.length > 0 && (
              <div className="mt-6 flex flex-wrap gap-2" aria-label="Suggested questions">
                {suggestions.map((question) => (
                  <Chip key={question} disabled={busy} onClick={() => onAsk(question)}>
                    {question}
                  </Chip>
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Thinking() {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted">
      <span className="flex gap-1" aria-hidden>
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-1.5 animate-pulse rounded-full bg-faint"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
      Looking through Tae&apos;s writing…
    </span>
  );
}
