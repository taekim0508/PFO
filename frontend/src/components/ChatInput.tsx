"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";

type ChatInputProps = {
  onSubmit: (question: string) => void;
  /** While an answer streams, Enter does nothing and the button stops the answer instead. */
  busy?: boolean;
  onStop?: () => void;
  maxLength: number;
  autoFocus?: boolean;
};

/** The pill-shaped question box. Enter sends; Shift+Enter starts a new line. */
export function ChatInput({
  onSubmit,
  busy = false,
  onStop,
  maxLength,
  autoFocus,
}: ChatInputProps) {
  const [value, setValue] = useState("");

  function send(event?: FormEvent) {
    event?.preventDefault();
    const question = value.trim();
    if (!question || busy) return;
    onSubmit(question);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  }

  return (
    <form
      onSubmit={send}
      className="glass flex items-end gap-2 rounded-[1.75rem] bg-surface-strong py-2 pr-2 pl-5 transition-shadow focus-within:shadow-[0_0_0_2px_var(--accent-strong)]"
    >
      <label htmlFor="question" className="sr-only">
        Ask about Tae&apos;s work
      </label>
      <textarea
        id="question"
        rows={1}
        value={value}
        maxLength={maxLength}
        autoFocus={autoFocus}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask about my work… ↵"
        className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent py-2 text-[15px] leading-6 text-ink placeholder:text-muted focus:outline-none [field-sizing:content]"
      />
      {busy ? (
        <button
          type="button"
          onClick={onStop}
          className="h-10 shrink-0 rounded-full border border-hairline-strong px-4 text-sm text-ink transition-colors hover:bg-peach-tint"
        >
          Stop
        </button>
      ) : (
        <button
          type="submit"
          disabled={!value.trim()}
          aria-label="Send question"
          className="grid size-10 shrink-0 place-items-center rounded-full bg-accent text-[#1a1a1a] transition-opacity disabled:opacity-40"
        >
          <svg
            aria-hidden
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
          >
            <path d="M12 19V5M5 12l7-7 7 7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
    </form>
  );
}
