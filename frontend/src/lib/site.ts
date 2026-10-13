/**
 * Facts about Tae the site shows outside the chat. Each one is public in content/: the
 * email, LinkedIn, and GitHub in skills.md, the location in job-search.md. Change them
 * there first, then here.
 */
export const site = {
  name: "Tae Kim",
  title: "Index",
  email: "taekim0508@gmail.com",
  github: "https://github.com/taekim0508",
  linkedin: "https://www.linkedin.com/in/kimtae03",
  location: "Seattle, WA",
  timeZone: "America/Los_Angeles",
  /** Where the résumé lives once it exists: frontend/public/resume.pdf. */
  resumePath: "/resume.pdf",
} as const;

/** The chat API. Inlined at build time; set NEXT_PUBLIC_API_BASE_URL per environment. */
export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
