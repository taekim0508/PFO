"use client";

import { site } from "@/lib/site";
import { ChatInput } from "./ChatInput";
import { Navbar } from "./Navbar";
import { Opening } from "./Opening";

/** The whole page: navbar, opening screen, and the question box. */
export function IndexApp({ hasResume }: { hasResume: boolean }) {
  const noop = () => {};
  return (
    <>
      <Navbar onWork={noop} onHome={() => window.scrollTo({ top: 0 })} hasResume={hasResume} />
      <main className="mx-auto flex min-h-dvh max-w-3xl flex-col justify-center px-5 pt-28 pb-16">
        <Opening
          onExplore={noop}
          onAsk={noop}
          hasResume={hasResume}
          resumePath={site.resumePath}
          compact={false}
        />
        <div className="mt-10">
          <ChatInput onSubmit={noop} maxLength={500} autoFocus />
          <p className="mt-3 text-center text-xs text-muted">
            Answers come from a friend who knows Tae&apos;s work, drawn only from what he&apos;s
            written.
          </p>
        </div>
      </main>
    </>
  );
}
