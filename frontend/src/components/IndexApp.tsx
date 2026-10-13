"use client";

import { useCallback, useEffect, useRef } from "react";
import { apiBaseUrl, site } from "@/lib/site";
import { useConversation, type Turn } from "@/lib/useConversation";
import { ChatInput } from "./ChatInput";
import { Conversation } from "./Conversation";
import { Navbar } from "./Navbar";
import { Opening } from "./Opening";

export const MAX_QUESTION_CHARS = 500;
export const PROJECTS_QUESTION = "What projects has Tae done?";

const GENERAL_FOLLOW_UPS = [
  "What projects has Tae done?",
  "What kind of role is Tae looking for?",
  "How does Tae approach solving problems?",
  "How can I contact Tae?",
];

/** The whole page: navbar, opening screen, the conversation, and the question box. */
export function IndexApp({
  hasResume,
  fetchImpl,
}: {
  hasResume: boolean;
  fetchImpl?: typeof fetch;
}) {
  const { turns, busy, ask, stop } = useConversation({ baseUrl: apiBaseUrl, fetchImpl });
  const started = turns.length > 0;

  // Follow the answer as it streams, unless the reader has scrolled up to read something.
  const following = useRef(true);
  useEffect(() => {
    function onScroll() {
      const fromBottom =
        document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
      following.current = fromBottom < 160;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    if (busy && following.current) {
      window.scrollTo({ top: document.documentElement.scrollHeight });
    }
  }, [turns, busy]);

  const askQuestion = useCallback(
    (question: string) => {
      following.current = true;
      void ask(question);
    },
    [ask],
  );

  const followUps = useCallback(
    (turn: Turn) => GENERAL_FOLLOW_UPS.filter((q) => q !== turn.question).slice(0, 3),
    [],
  );

  const input = (
    <>
      <ChatInput
        onSubmit={askQuestion}
        busy={busy}
        onStop={stop}
        maxLength={MAX_QUESTION_CHARS}
        autoFocus={!started}
      />
      <p className="mt-2 text-center text-xs text-muted">
        Answers come from a friend who knows Tae&apos;s work, drawn only from what he&apos;s
        written.
      </p>
    </>
  );

  return (
    <>
      <Navbar
        onWork={() => askQuestion(PROJECTS_QUESTION)}
        onHome={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        hasResume={hasResume}
      />
      <main
        className={`mx-auto flex max-w-3xl flex-col px-5 ${
          started ? "min-h-dvh pt-28 pb-48" : "min-h-dvh justify-center pt-28 pb-16"
        }`}
      >
        <Opening
          onExplore={() => askQuestion(PROJECTS_QUESTION)}
          onAsk={askQuestion}
          hasResume={hasResume}
          resumePath={site.resumePath}
          compact={started}
        />
        {started ? (
          <Conversation
            turns={turns}
            busy={busy}
            onAsk={askQuestion}
            onCite={() => {}}
            followUps={followUps}
          />
        ) : (
          <div className="mt-10">{input}</div>
        )}
      </main>
      {started && (
        <div className="fixed inset-x-0 bottom-0 z-30 px-5 pt-10 pb-4 [background:linear-gradient(to_top,var(--bg-edge)_55%,transparent)]">
          <div className="mx-auto max-w-3xl">{input}</div>
        </div>
      )}
    </>
  );
}
