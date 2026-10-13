import { describe, expect, it } from "vitest";
import { parseWriteup, readWriteups } from "../content";
import { CASE_STUDY_HEADINGS, PROJECTS, type CaseStudyKey } from "../projects";

describe("parseWriteup", () => {
  it("reads the title and each ## section", () => {
    const writeup = parseWriteup(
      "x.md",
      "---\ntitle: Abroadly\n---\n\n## The problem\n\nScattered info.\n\n## What I built\n\nMessaging.\nBookmarks.\n",
    );

    expect(writeup.title).toBe("Abroadly");
    expect(writeup.sections).toEqual([
      { heading: "The problem", body: "Scattered info." },
      { heading: "What I built", body: "Messaging.\nBookmarks." },
    ]);
  });

  it("refuses a file without front matter or a title", () => {
    expect(() => parseWriteup("x.md", "## Heading\n")).toThrow("front matter");
    expect(() => parseWriteup("x.md", "---\ntags: a\n---\n")).toThrow("title");
  });
});

// Against the real corpus: the case studies quote it, so a renamed heading must fail here.
describe("the projects and the write-ups agree", () => {
  const writeups = readWriteups();

  it.each(PROJECTS.map((p) => [p.name, p] as const))("%s", (_name, project) => {
    const writeup = writeups.get(project.file);
    expect(writeup, `${project.file} exists in content/`).toBeDefined();
    const headings = writeup!.sections.map((s) => s.heading);
    for (const key of Object.keys(CASE_STUDY_HEADINGS) as CaseStudyKey[]) {
      for (const heading of project.caseStudy[key]) {
        expect(headings, `${project.file} has "${heading}"`).toContain(heading);
      }
    }
  });

  it("uses each section at most once per project", () => {
    for (const project of PROJECTS) {
      const used = Object.values(project.caseStudy).flat();
      expect(new Set(used).size).toBe(used.length);
    }
  });

  // Each question is answered on its own, so a follow-up must say what it is about.
  it("gives every project follow-up questions that name Tae or the project", () => {
    for (const project of PROJECTS) {
      expect(project.followUps.length).toBeGreaterThanOrEqual(2);
      const subject = new RegExp(`Tae|${project.name.split(" ")[0]}|chatbot`);
      for (const question of project.followUps) expect(question).toMatch(subject);
    }
  });
});
