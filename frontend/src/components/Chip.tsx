import type { ButtonHTMLAttributes } from "react";

/** A suggestion: a short question or action, one click away. */
export function Chip({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`glass rounded-full px-4 py-2 text-sm text-ink transition-colors hover:bg-peach-tint hover:text-accent-strong disabled:cursor-not-allowed disabled:text-muted disabled:hover:bg-transparent ${className}`}
      {...props}
    />
  );
}
