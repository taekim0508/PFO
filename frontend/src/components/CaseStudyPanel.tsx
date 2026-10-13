"use client";

import { useEffect, useRef } from "react";
import type { ProjectView } from "@/lib/projectView";
import { AnswerText } from "./AnswerText";

/**
 * The full case study: on wide screens a panel to the right of the conversation, so the
 * question stays visible; on phones a full-screen sheet. The text is Tae's own write-up,
 * arranged under the six headings; a heading his write-up does not cover says so.
 */
export function CaseStudyPanel({
  project,
  onClose,
}: {
  project: ProjectView;
  onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [project.slug, onClose]);

  return (
    <aside
      aria-labelledby="case-study-title"
      className="animate-rise fixed inset-0 z-50 overflow-y-auto bg-surface-strong backdrop-blur-xl lg:inset-auto lg:top-20 lg:right-4 lg:bottom-4 lg:z-30 lg:w-[30rem] lg:rounded-2xl lg:border lg:border-hairline"
    >
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-hairline bg-surface-strong px-6 py-3 backdrop-blur-xl">
        <span className="label">Case study</span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full px-3 py-1 text-sm text-ink hover:bg-peach-tint"
        >
          Close <span className="sr-only">case study</span>
          <span aria-hidden> ✕</span>
        </button>
      </div>

      <div className="px-6 pt-6 pb-10">
        <p className="label">{project.context}</p>
        <h2
          id="case-study-title"
          ref={heading}
          tabIndex={-1}
          className="mt-2 font-serif text-4xl leading-tight text-ink focus:outline-none"
        >
          {project.name}
        </h2>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {project.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-hairline-strong px-2.5 py-0.5 text-xs text-muted"
            >
              {tag}
            </span>
          ))}
        </div>

        {project.study.map(({ key, heading: title, parts }) => (
          <section key={key} aria-labelledby={`study-${key}`} className="mt-8">
            <h3 id={`study-${key}`} className="label text-accent-strong!">
              {title}
            </h3>
            {parts.length === 0 ? (
              <p className="mt-3 rounded-xl border border-dashed border-hairline-strong px-4 py-3 text-sm text-muted">
                <span className="label mr-2">Placeholder</span>
                Tae hasn&apos;t written this part up yet.
              </p>
            ) : (
              parts.map((part) => (
                <div key={part.heading} className="mt-3">
                  <h4 className="text-[15px] font-semibold text-ink">{part.heading}</h4>
                  <div className="mt-1 text-[15px] leading-7 text-ink">
                    <AnswerText text={part.body} labels={[]} />
                  </div>
                </div>
              ))
            )}
          </section>
        ))}

        <p className="mt-10 text-xs text-muted">
          From Tae&apos;s write-up, &ldquo;{project.title}&rdquo;, in his own words.
        </p>
      </div>
    </aside>
  );
}
