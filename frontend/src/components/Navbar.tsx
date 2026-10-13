"use client";

import { useEffect, useRef, useState } from "react";
import { site } from "@/lib/site";
import { Clock } from "./Clock";
import { CopyEmail } from "./CopyEmail";
import { ThemeToggle } from "./ThemeToggle";

type NavbarProps = {
  /** Shows the project overview in the conversation. */
  onWork: () => void;
  /** Scrolls back to the top and the opening screen. */
  onHome: () => void;
  /** False until frontend/public/resume.pdf exists; the link then shows as a placeholder. */
  hasResume: boolean;
};

const linkClass =
  "rounded-full px-3 py-1.5 text-sm text-ink transition-colors hover:bg-peach-tint hover:text-accent-strong";

/** A floating translucent pill that stays put on scroll. Collapses to a menu on phones. */
export function Navbar({ onWork, onHome, hasResume }: NavbarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const links = (
    <>
      <button
        type="button"
        className={linkClass}
        onClick={() => {
          setMenuOpen(false);
          onWork();
        }}
      >
        Work
      </button>
      <ResumeLink hasResume={hasResume} />
      <a className={linkClass} href={site.github} target="_blank" rel="noreferrer">
        GitHub <span aria-hidden>↗</span>
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    </>
  );

  return (
    <header className="fixed inset-x-0 top-3 z-40 px-4 sm:top-4">
      <nav
        aria-label="Main"
        className="glass mx-auto flex max-w-5xl items-center justify-between gap-2 rounded-full py-1.5 pr-1.5 pl-4"
      >
        <button
          type="button"
          onClick={onHome}
          className="label rounded-full px-1 py-1 text-ink! tracking-[0.2em]"
        >
          Tae Kim
        </button>

        <div className="hidden items-center gap-0.5 md:flex">{links}</div>

        <div className="flex items-center gap-1">
          <span className="hidden lg:inline">
            <Clock timeZone={site.timeZone} location={site.location} />
          </span>
          <CopyEmail email={site.email} />
          <span className="hidden md:inline">
            <ThemeToggle />
          </span>
          <button
            ref={menuButton}
            type="button"
            className="grid size-8 place-items-center rounded-full text-ink hover:bg-peach-tint md:hidden"
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <svg
              aria-hidden
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
            >
              {menuOpen ? (
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
              ) : (
                <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
              )}
            </svg>
          </button>
        </div>
      </nav>

      {menuOpen && (
        <div
          id="mobile-menu"
          className="glass animate-rise mx-auto mt-2 flex max-w-5xl flex-col items-start gap-1 rounded-2xl bg-surface-strong p-3 md:hidden"
        >
          {links}
          <div className="flex w-full items-center justify-between px-3 pt-2">
            <Clock timeZone={site.timeZone} location={site.location} />
            <ThemeToggle />
          </div>
        </div>
      )}
    </header>
  );
}

function ResumeLink({ hasResume }: { hasResume: boolean }) {
  if (!hasResume) {
    // A clearly marked placeholder until the PDF is added, never a dead link.
    return (
      <span
        className={`${linkClass} cursor-not-allowed text-muted! hover:bg-transparent`}
        aria-disabled
        title="Résumé coming soon"
      >
        Résumé <span className="label">soon</span>
      </span>
    );
  }
  return (
    <a className={linkClass} href={site.resumePath} target="_blank" rel="noreferrer">
      Résumé <span aria-hidden>↗</span>
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}
