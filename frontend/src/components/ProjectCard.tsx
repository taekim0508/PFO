import type { ProjectView } from "@/lib/projectView";

/** Name, the problem in one line, Tae's role, and the stack. Opens the case study. */
export function ProjectCard({
  project,
  onOpen,
  selected = false,
}: {
  project: ProjectView;
  onOpen: (project: ProjectView, trigger: HTMLElement) => void;
  selected?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={(event) => onOpen(project, event.currentTarget)}
      aria-pressed={selected}
      className={`glass group w-full rounded-2xl p-5 text-left transition-colors hover:bg-peach-tint ${
        selected ? "border-accent-strong!" : ""
      }`}
    >
      <span className="label">{project.context}</span>
      <span className="mt-2 flex items-baseline justify-between gap-3">
        <span className="font-serif text-2xl leading-tight text-ink">{project.name}</span>
        <span
          aria-hidden
          className="text-sm text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-accent-strong"
        >
          →
        </span>
      </span>
      <span className="mt-2 block text-[15px] leading-6 text-ink">{project.problem}</span>
      <span className="mt-2 block text-sm leading-6 text-muted">
        <span className="font-medium text-ink">Tae: </span>
        {project.role}
      </span>
      <span className="mt-4 flex flex-wrap gap-1.5">
        {project.tags.map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-hairline-strong px-2.5 py-0.5 text-xs text-muted"
          >
            {tag}
          </span>
        ))}
      </span>
      <span className="sr-only">Open the case study</span>
    </button>
  );
}
