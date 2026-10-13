import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

// jsdom does not lay pages out, so it has no scrollIntoView. Every browser does.
Element.prototype.scrollIntoView = function scrollIntoView() {};

// jsdom has no matchMedia either. Tests see a wide screen unless they replace this.
window.matchMedia = ((query: string) => ({
  matches: true,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;
