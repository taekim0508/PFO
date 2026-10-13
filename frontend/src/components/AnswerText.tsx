import { Fragment, type ReactNode } from "react";

type AnswerTextProps = {
  text: string;
  /** Passage numbers that exist; a citation to any other number renders as plain text. */
  labels: number[];
  onCite?: (label: number) => void;
};

/**
 * The model's answer as editorial text: paragraphs, short lists, **bold**, and citation
 * markers like [1] turned into small buttons that open the source. Everything else is
 * plain text; nothing from the model is ever inserted as HTML.
 */
export function AnswerText({ text, labels, onCite }: AnswerTextProps) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n").filter((line) => line.trim() !== "");
        const isList =
          lines.length > 0 && lines.every((line) => /^\s*([-*•]|\d+[.)])\s+/.test(line));
        if (isList) {
          const ordered = /^\s*\d/.test(lines[0]);
          const items = lines.map((line) => line.replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
          const List = ordered ? "ol" : "ul";
          return (
            <List
              key={i}
              className={`my-3 space-y-1.5 pl-5 ${ordered ? "list-decimal" : "list-disc"} marker:text-faint`}
            >
              {items.map((item, j) => (
                <li key={j}>{inline(item, labels, onCite)}</li>
              ))}
            </List>
          );
        }
        return (
          <p key={i} className="my-3 first:mt-0 last:mb-0">
            {inline(lines.join(" ").replace(/^#+\s+/, ""), labels, onCite)}
          </p>
        );
      })}
    </>
  );
}

const TOKEN = /(\*\*[^*]+\*\*|\[\d+\])/g;

function inline(text: string, labels: number[], onCite?: (label: number) => void): ReactNode {
  return text.split(TOKEN).map((part, i) => {
    const citation = /^\[(\d+)\]$/.exec(part);
    if (citation) {
      const label = Number(citation[1]);
      if (!labels.includes(label)) return <Fragment key={i}>{part}</Fragment>;
      return (
        <button
          key={i}
          type="button"
          onClick={() => onCite?.(label)}
          className="mx-0.5 inline-grid min-w-[1.35rem] place-items-center rounded-md border border-hairline-strong px-1 align-[0.15em] text-[0.68rem] leading-[1.1rem] font-medium text-accent-strong transition-colors hover:bg-peach-tint"
          aria-label={`Source ${label}`}
        >
          {label}
        </button>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={i} className="font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
