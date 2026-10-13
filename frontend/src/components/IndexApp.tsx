"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { ProjectView } from "@/lib/projectView";
import { apiBaseUrl, site } from "@/lib/site";
import { useConversation, type Turn } from "@/lib/useConversation";
import { CaseStudyPanel } from "./CaseStudyPanel";
import { ChatInput } from "./ChatInput";
import { Conversation } from "./Conversation";
import { Navbar } from "./Navbar";
import { Opening } from "./Opening";
import { ProjectCard } from "./ProjectCard";
import { SourcesPanel } from "./SourcesPanel";

export const MAX_QUESTION_CHARS = 500;
export const EXPLORE_LABEL = "Explore my projects";
export const OVERVIEW_TEXT =
  "Five projects, the deepest first. Open any card for the full case study, in Tae's own words.";

const GENERAL_FOLLOW_UPS = [
  "What projects has Tae done?",
  "What kind of role is Tae looking for?",
  "How does Tae approach solving problems?",
  "How can I contact Tae?",
];

type IndexAppProps = {
  hasResume: boolean;
  projects: ProjectView[];
  fetchImpl?: typeof fetch;
};

const WIDE = "(min-width: 1024px)";

function subscribeToWidth(onChange: () => void) {
  const query = window.matchMedia(WIDE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** The whole page: navbar, opening screen, the conversation, cards, sources, case study. */
export function IndexApp({ hasResume, projects, fetchImpl }: IndexAppProps) {
  const { turns, busy, ask, stop, addOverview } = useConversation({
    baseUrl: apiBaseUrl,
    fetchImpl,
  });
  const started = turns.length > 0;

  const [openProject, setOpenProject] = useState<ProjectView | null>(null);
  const wide = useSyncExternalStore(
    subscribeToWidth,
    () => window.matchMedia(WIDE).matches,
    () => true,
  );
  // On a phone the case study is a full-screen sheet, so everything behind it is taken out
  // of the tab order and the accessibility tree until it closes.
  const sheetOpen = openProject !== null && !wide;
  const returnFocus = useRef<HTMLElement | null>(null);
  const [openSources, setOpenSources] = useState<Set<string>>(new Set());
  const [highlight, setHighlight] = useState<{ turnId: string; label: number } | null>(null);

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

  // The overview opens at its own top, so the strongest project is the first thing seen.
  const lastTurn = turns.at(-1);
  useEffect(() => {
    if (lastTurn?.kind !== "overview") return;
    const element = document.getElementById(`${lastTurn.id}-q`);
    if (!element) return;
    window.scrollTo({ top: element.getBoundingClientRect().top + window.scrollY - 96 });
  }, [lastTurn]);

  const askQuestion = useCallback(
    (question: string) => {
      following.current = true;
      void ask(question);
    },
    [ask],
  );

  const showOverview = useCallback(() => {
    following.current = true;
    addOverview(EXPLORE_LABEL, OVERVIEW_TEXT);
  }, [addOverview]);

  const openCaseStudy = useCallback((project: ProjectView, trigger: HTMLElement) => {
    returnFocus.current = trigger;
    setOpenProject(project);
  }, []);

  const closeCaseStudy = useCallback(() => {
    setOpenProject(null);
    returnFocus.current?.focus();
  }, []);

  /** The projects an answer cited, at most two; with no citations, the top passage's. */
  const relatedProjects = useCallback(
    (turn: Turn): ProjectView[] => {
      if (turn.kind === "overview") return projects;
      if (turn.status !== "done" || turn.done?.no_context) return [];
      const cited = new Set(turn.done?.cited ?? []);
      const drawnOn =
        cited.size > 0
          ? turn.passages.filter((p) => cited.has(p.label))
          : turn.passages.slice(0, 1);
      const found: ProjectView[] = [];
      for (const passage of drawnOn) {
        const project = projects.find((p) => p.file === passage.source_path);
        if (project && !found.includes(project)) found.push(project);
      }
      return found.slice(0, 2);
    },
    [projects],
  );

  const followUps = useCallback(
    (turn: Turn) => {
      const lead = turn.kind === "overview" ? projects[0] : relatedProjects(turn)[0];
      const pool = lead ? lead.followUps : GENERAL_FOLLOW_UPS;
      return pool.filter((q) => q !== turn.question).slice(0, 3);
    },
    [projects, relatedProjects],
  );

  const toggleSources = useCallback((turnId: string) => {
    setOpenSources((open) => {
      const next = new Set(open);
      if (next.has(turnId)) next.delete(turnId);
      else next.add(turnId);
      return next;
    });
  }, []);

  const cite = useCallback((turn: Turn, label: number) => {
    setOpenSources((open) => new Set(open).add(turn.id));
    setHighlight({ turnId: turn.id, label });
  }, []);

  const extras = (turn: Turn) => {
    const cards = relatedProjects(turn);
    return (
      <>
        {cards.length > 0 && (
          <div
            className={`mt-6 grid gap-3 ${turn.kind === "overview" ? "" : "sm:grid-cols-2"}`}
            aria-label="Related projects"
          >
            {cards.map((project) => (
              <ProjectCard
                key={project.slug}
                project={project}
                onOpen={openCaseStudy}
                selected={openProject?.slug === project.slug}
              />
            ))}
          </div>
        )}
        {turn.kind === "answer" && turn.status !== "streaming" && (
          <SourcesPanel
            id={`${turn.id}-sources`}
            passages={turn.passages}
            strategy={turn.strategy}
            done={turn.done}
            open={openSources.has(turn.id)}
            onToggle={() => toggleSources(turn.id)}
            highlight={highlight?.turnId === turn.id ? highlight.label : undefined}
          />
        )}
      </>
    );
  };

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

  // With the case study open on a wide screen, the conversation makes room on the right.
  const roomForPanel = openProject ? "lg:pr-[32rem]" : "";

  return (
    <>
      <Navbar
        inert={sheetOpen}
        onWork={showOverview}
        onHome={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        hasResume={hasResume}
      />
      <div className={roomForPanel} inert={sheetOpen}>
        <main
          className={`mx-auto flex max-w-3xl flex-col px-5 ${
            started ? "min-h-dvh pt-28 pb-48" : "min-h-dvh justify-center pt-28 pb-16"
          }`}
        >
          <Opening
            onExplore={showOverview}
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
              onCite={cite}
              followUps={followUps}
              extras={extras}
            />
          ) : (
            <div className="mt-10">{input}</div>
          )}
        </main>
      </div>
      {started && (
        <div
          inert={sheetOpen}
          className={`fixed inset-x-0 bottom-0 z-20 px-5 pt-10 pb-4 [background:linear-gradient(to_top,var(--bg-edge)_55%,transparent)] ${roomForPanel}`}
        >
          <div className="mx-auto max-w-3xl">{input}</div>
        </div>
      )}
      {openProject && <CaseStudyPanel project={openProject} onClose={closeCaseStudy} />}
    </>
  );
}
