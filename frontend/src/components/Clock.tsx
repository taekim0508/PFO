"use client";

import { useSyncExternalStore } from "react";

/** "4:00 PM" in `timeZone`. Exported for tests. */
export function formatClock(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(date);
}

function subscribe(onChange: () => void) {
  const id = setInterval(onChange, 15_000);
  return () => clearInterval(id);
}

/**
 * The time where Tae is. Empty on the server, which cannot know the visitor's clock, then
 * filled in the browser; the snapshot is the formatted minute, so it only re-renders when
 * the minute changes.
 */
export function Clock({ timeZone, location }: { timeZone: string; location: string }) {
  const time = useSyncExternalStore(
    subscribe,
    () => formatClock(new Date(), timeZone),
    () => "",
  );
  return (
    <span className="label whitespace-nowrap tabular-nums" aria-label={`Local time in ${location}`}>
      {time || " "} · {location}
    </span>
  );
}
