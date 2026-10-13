import { CASE_STUDY_HEADINGS, type CaseStudyKey, type Project } from "./projects";
import type { Section, Writeup } from "./content";

/** A project with its case-study text resolved from the write-up, ready to render. */
export type ProjectView = Omit<Project, "caseStudy"> & {
  title: string;
  study: { key: CaseStudyKey; heading: string; parts: Section[] }[];
};

/** Fails loudly when a project names a file or heading the corpus does not have. */
export function toProjectView(project: Project, writeups: Map<string, Writeup>): ProjectView {
  const writeup = writeups.get(project.file);
  if (!writeup) throw new Error(`projects.ts names ${project.file}, which is not in content/`);
  const study = (Object.keys(CASE_STUDY_HEADINGS) as CaseStudyKey[]).map((key) => ({
    key,
    heading: CASE_STUDY_HEADINGS[key],
    parts: project.caseStudy[key].map((heading) => {
      const section = writeup.sections.find((s) => s.heading === heading);
      if (!section) throw new Error(`${project.file} has no section "${heading}"`);
      return section;
    }),
  }));
  const { caseStudy: _unused, ...rest } = project;
  void _unused;
  return { ...rest, title: writeup.title, study };
}
