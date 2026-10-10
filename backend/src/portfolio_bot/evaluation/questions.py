"""The evaluation set: questions paired with the sections that answer them.

An answer is named as a section, `education.md > Degrees and dates`, never as a chunk.
Chunk ids change on every re-ingest, and chunking settings are themselves something the
evaluation exists to compare; an answer pinned to a chunk would break the first time
either changed. A section survives both.

A section also matches everything beneath it, so `about.md > Background` covers the chunks
under its subheadings, and `about.md` alone covers the whole document.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SEPARATOR = " > "


class EvalSetError(ValueError):
    """The evaluation file is malformed, or names a section the corpus does not have."""


@dataclass(frozen=True, order=True)
class Section:
    """A file in content/, optionally narrowed to the heading path under it."""

    source_path: str
    heading_path: tuple[str, ...] = ()

    def __str__(self) -> str:
        return SEPARATOR.join([self.source_path, *self.heading_path])

    def covers(self, other: Section) -> bool:
        """Whether `other` is this section or lies somewhere beneath it."""
        return (
            self.source_path == other.source_path
            and other.heading_path[: len(self.heading_path)] == self.heading_path
        )


@dataclass(frozen=True)
class EvalQuestion:
    question: str
    expected: tuple[Section, ...]
    note: str | None = None


def parse_section(text: str) -> Section:
    """`file.md > Heading > Subheading` into a Section. Raises EvalSetError if malformed."""
    parts = [part.strip() for part in text.split(SEPARATOR.strip())]
    if not parts[0].endswith(".md") or any(not part for part in parts):
        raise EvalSetError(
            f"section {text!r} should look like 'file.md > Heading', with nothing empty"
        )
    return Section(parts[0], tuple(parts[1:]))


def load_questions(path: Path) -> list[EvalQuestion]:
    """Read and check the evaluation file.

    Every problem found is reported at once, each naming the entry it came from, so fixing
    a file with several mistakes takes one run rather than one run per mistake.
    """
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise EvalSetError(f"{path} is not valid YAML: {error}") from error

    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise EvalSetError(f"{path} should have a top-level 'questions:' list")

    questions: list[EvalQuestion] = []
    problems: list[str] = []
    seen: set[str] = set()
    for number, entry in enumerate(data["questions"], start=1):
        where = f"entry {number}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: should be a mapping with 'question' and 'expected'")
            continue
        question = entry.get("question")
        expected = entry.get("expected")
        note = entry.get("note")
        if not isinstance(question, str) or not question.strip():
            problems.append(f"{where}: 'question' is missing or empty")
            continue
        where = f"entry {number} ({question.strip()!r})"
        if question.strip() in seen:
            problems.append(f"{where}: duplicate question")
            continue
        seen.add(question.strip())
        if isinstance(expected, str):
            expected = [expected]
        if not isinstance(expected, list) or not expected:
            problems.append(f"{where}: 'expected' needs at least one section")
            continue
        try:
            sections = tuple(parse_section(str(item)) for item in expected)
        except EvalSetError as error:
            problems.append(f"{where}: {error}")
            continue
        if note is not None and not isinstance(note, str):
            problems.append(f"{where}: 'note' should be text")
            continue
        questions.append(EvalQuestion(question.strip(), sections, note))

    if problems:
        raise EvalSetError("\n".join(problems))
    return questions
