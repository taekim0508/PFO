"use client";

import { useEffect, useRef, useState } from "react";

/** Copies the address and says so for about a second and a half. */
export function CopyEmail({ email, className = "" }: { email: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  async function copy() {
    try {
      await navigator.clipboard.writeText(email);
    } catch {
      // Clipboard access can be refused (insecure context, permissions). Fall back to mail.
      window.location.href = `mailto:${email}`;
      return;
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1500);
  }

  return (
    <button
      type="button"
      onClick={copy}
      className={`rounded-full px-3 py-1.5 text-sm text-ink transition-colors hover:bg-peach-tint ${className}`}
      aria-label={copied ? "Email copied" : `Copy email address ${email}`}
    >
      <span aria-live="polite">{copied ? "Copied!" : "Copy Email"}</span>
    </button>
  );
}
