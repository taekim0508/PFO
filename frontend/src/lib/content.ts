import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

/**
 * Tae's write-ups in content/, the same markdown the chatbot answers from, read at build
 * time. One source of truth: the case studies quote these files, so they cannot drift from
 * what the bot says.
 *
 * Server-only (it reads the filesystem). Pages read it once at module scope, as the
 * Next.js caching guide recommends for files that are the same on every request.
 */

export type Section = { heading: string; body: string };
export type Writeup = { file: string; title: string; sections: Section[] };

export const CONTENT_DIR = path.join(process.cwd(), "..", "content");

export function parseWriteup(file: string, raw: string): Writeup {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(raw);
  if (!match) throw new Error(`${file}: missing front matter`);
  const title = /^title:\s*(.+)$/m.exec(match[1])?.[1].trim();
  if (!title) throw new Error(`${file}: front matter has no title`);

  const sections: Section[] = [];
  let current: Section | null = null;
  for (const line of raw.slice(match[0].length).split(/\r?\n/)) {
    const heading = /^##\s+(.+)$/.exec(line);
    if (heading) {
      current = { heading: heading[1].trim(), body: "" };
      sections.push(current);
    } else if (current) {
      current.body += `${line}\n`;
    }
  }
  for (const section of sections) section.body = section.body.trim();
  return { file, title, sections };
}

export function readWriteups(dir: string = CONTENT_DIR): Map<string, Writeup> {
  const writeups = new Map<string, Writeup>();
  for (const file of readdirSync(dir).sort()) {
    if (!file.endsWith(".md") || file === "README.md") continue;
    writeups.set(file, parseWriteup(file, readFileSync(path.join(dir, file), "utf8")));
  }
  return writeups;
}
