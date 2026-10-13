import { existsSync } from "node:fs";
import path from "node:path";
import { IndexApp } from "@/components/IndexApp";
import { readWriteups } from "@/lib/content";
import { toProjectView } from "@/lib/projectView";
import { PROJECTS } from "@/lib/projects";
import { site } from "@/lib/site";

// Read once when the module loads, at build time: the write-ups and the résumé are files,
// the same for every request, so the page stays fully static.
const hasResume = existsSync(path.join(process.cwd(), "public", site.resumePath));
const writeups = readWriteups();
const projects = PROJECTS.map((project) => toProjectView(project, writeups));

export default function Home() {
  return <IndexApp hasResume={hasResume} projects={projects} />;
}
