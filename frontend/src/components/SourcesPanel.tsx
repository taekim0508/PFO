"use client";

import { useEffect, useRef } from "react";
import type { DoneEvent, Passage } from "@/lib/chatApi";

type SourcesPanelProps = {
  id: string;
  passages: Passage[];
  strategy?: string;
  done?: DoneEvent;
  open: boolean;
  onToggle: () => void;
  /** The passage a citation was clicked for; scrolled to and highlighted. */
  highlight?: number;
};

/**
 * What the answer was built from: every retrieved passage, its score, which search found
 * it and at what rank, and whether the answer cited it. Collapsed under each answer.
 */
export function SourcesPanel({
  id,
  passages,
  strategy,
  done,
  open,
  onToggle,
  highlight,
}: SourcesPanelProps) {
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (!open || highlight === undefined) return;
    const item = list.current?.querySelector<HTMLElement>(`[data-label="${highlight}"]`);
    // Centred, so it clears the pinned question box at the bottom of the screen.
    item?.scrollIntoView({ block: "center", behavior: "smooth" });
    item?.focus({ preventScroll: true });
  }, [open, highlight]);

  if (passages.length === 0) return null;
  const cited = new Set(done?.cited ?? []);

  return (
    <div className="mt-5">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={id}
        className="label inline-flex items-center gap-2 rounded-full px-1 py-1 hover:text-ink!"
      >
        <span aria-hidden className={`transition-transform ${open ? "rotate-90" : ""}`}>
          ›
        </span>
        Sources · {passages.length} {passages.length === 1 ? "passage" : "passages"}
        {strategy ? ` · ${strategy} search` : ""}
      </button>

      {open && (
        <div id={id} className="glass animate-rise mt-2 rounded-2xl p-4">
          <ol ref={list} className="space-y-3">
            {passages.map((passage) => (
              <li
                key={passage.label}
                data-label={passage.label}
                tabIndex={-1}
                className={`rounded-xl px-3 py-2 transition-colors focus:outline-none ${
                  highlight === passage.label ? "bg-peach-tint" : ""
                }`}
              >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-xs font-semibold text-accent-strong">
                    [{passage.label}]
                  </span>
                  <span className="text-sm font-medium text-ink">{passage.location}</span>
                  {cited.has(passage.label) && <span className="label">cited</span>}
                </div>
                <p className="mt-1 text-xs text-muted tabular-nums">
                  score {passage.score.toFixed(3)} ·{" "}
                  {passage.provenance.map((p) => `${p.strategy} #${p.rank}`).join(", ")} ·{" "}
                  {passage.source_path}
                </p>
                <p className="mt-1 line-clamp-3 text-sm leading-6 text-ink">
                  {excerpt(passage.text)}
                </p>
              </li>
            ))}
          </ol>
          {done && (
            <p className="mt-4 border-t border-hairline pt-3 text-xs text-muted tabular-nums">
              {done.no_context
                ? "Nothing was close enough to answer from, so the model was not asked."
                : `Found in ${seconds(done.retrieval_ms)}, first words at ${
                    done.first_text_ms === null ? "n/a" : seconds(done.first_text_ms)
                  }, done in ${seconds(done.total_ms)} · ${done.model ?? "model"} · prompt ${
                    done.prompt_version
                  }`}
              {done.invalid_citations.length > 0 &&
                ` · cited passages that were not given: ${done.invalid_citations.join(", ")}`}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** The passage without its leading markdown heading line, which the location already names. */
function excerpt(text: string): string {
  return text.replace(/^#+ .*\n+/, "").trim();
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}
