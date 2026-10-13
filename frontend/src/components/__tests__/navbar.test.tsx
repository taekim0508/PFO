import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { formatClock } from "../Clock";
import { CopyEmail } from "../CopyEmail";
import { Navbar } from "../Navbar";
import { ThemeToggle } from "../ThemeToggle";

describe("formatClock", () => {
  it("shows hours and minutes in the given time zone", () => {
    const noonUtc = new Date("2026-10-13T19:05:00Z");
    expect(formatClock(noonUtc, "America/Los_Angeles")).toBe("12:05 PM");
  });
});

describe("CopyEmail", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });
  afterEach(() => vi.useRealTimers());

  it("copies the address and says Copied! for about a second and a half", async () => {
    render(<CopyEmail email="tae@example.com" />);

    await act(async () => fireEvent.click(screen.getByRole("button")));

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("tae@example.com");
    expect(screen.getByRole("button")).toHaveTextContent("Copied!");
    act(() => vi.advanceTimersByTime(1500));
    expect(screen.getByRole("button")).toHaveTextContent("Copy Email");
  });
});

describe("ThemeToggle", () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = "light";
    localStorage.clear();
  });

  it("switches the page theme and remembers it", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeInTheDocument();
  });
});

describe("Navbar", () => {
  it("shows the résumé as a placeholder until the file exists", () => {
    render(<Navbar onWork={() => {}} onHome={() => {}} hasResume={false} />);

    expect(screen.queryByRole("link", { name: /Résumé/ })).toBeNull();
    expect(screen.getAllByText("soon")[0]).toBeInTheDocument();
  });

  it("links the résumé once it exists, and GitHub always", () => {
    render(<Navbar onWork={() => {}} onHome={() => {}} hasResume />);

    expect(screen.getByRole("link", { name: /Résumé/ })).toHaveAttribute("href", "/resume.pdf");
    expect(screen.getByRole("link", { name: /GitHub/ })).toHaveAttribute(
      "href",
      "https://github.com/taekim0508",
    );
  });

  it("calls onWork from the Work link", () => {
    const onWork = vi.fn();
    render(<Navbar onWork={onWork} onHome={() => {}} hasResume={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Work" }));

    expect(onWork).toHaveBeenCalledOnce();
  });

  it("opens and closes the phone menu", () => {
    render(<Navbar onWork={() => {}} onHome={() => {}} hasResume={false} />);
    const toggle = screen.getByRole("button", { name: "Open menu" });

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});
