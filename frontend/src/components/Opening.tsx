import { Chip } from "./Chip";

type OpeningProps = {
  onExplore: () => void;
  onAsk: (question: string) => void;
  hasResume: boolean;
  resumePath: string;
  /** After the first question the intro compacts upward and the conversation takes focus. */
  compact: boolean;
};

export const HOW_I_SOLVE_PROBLEMS = "How does Tae approach solving problems?";

export function Opening({ onExplore, onAsk, hasResume, resumePath, compact }: OpeningProps) {
  if (compact) {
    return (
      <p className="font-serif text-2xl text-ink sm:text-3xl">
        Explore the work. <em className="text-muted">Ask about the thinking.</em>
      </p>
    );
  }
  return (
    <section aria-labelledby="headline" className="animate-rise">
      <p className="label">Backend · AI</p>
      <h1 id="headline" className="mt-4 font-serif text-5xl leading-[1.05] text-ink sm:text-6xl">
        Explore the work.
        <br />
        <em className="text-muted">Ask about the thinking.</em>
      </h1>
      <p className="mt-6 max-w-xl text-lg text-ink">
        I&apos;m a recent Vanderbilt graduate building backend systems and AI applications.
      </p>
      <div className="mt-8 flex flex-wrap gap-2">
        <Chip onClick={onExplore}>Explore my projects</Chip>
        <Chip onClick={() => onAsk(HOW_I_SOLVE_PROBLEMS)}>How I solve problems</Chip>
        {hasResume ? (
          <Chip onClick={() => window.open(resumePath, "_blank", "noopener")}>
            View my résumé ↗
          </Chip>
        ) : (
          <Chip disabled title="Résumé coming soon">
            View my résumé <span className="label ml-1">soon</span>
          </Chip>
        )}
      </div>
    </section>
  );
}
