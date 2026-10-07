"""Find the corpus files and read each one into a document record.

Nothing here touches the database. Deciding whether a document has changed is the
pipeline's job; this module only reports what is on disk and a fingerprint of it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# Front matter is the block between two `---` lines at the very top of the file. \r? keeps
# files saved with Windows line endings readable without rewriting them, which would shift
# every character offset the chunker records.
_FRONT_MATTER = re.compile(r"\A---\r?\n(?P<block>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_FIELD = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*)[ \t]*:[ \t]*(?P<value>.*?)[ \t]*$")


class DocumentError(ValueError):
    """A corpus file that cannot be ingested, with the reason in the message."""


@dataclass(frozen=True)
class SourceDocument:
    """One markdown file, read and fingerprinted.

    `text` is the whole file, front matter included, so that offsets into it are offsets
    into the file itself. `body_start` is where the content after the front matter begins.
    """

    source_path: str
    title: str
    text: str
    body_start: int
    content_hash: str


def discover(root: Path) -> list[Path]:
    """Every markdown file under `root`, in a stable order.

    README.md files are skipped: content/README.md describes how to write the corpus and
    is not part of it.
    """
    return sorted(
        path for path in root.rglob("*.md") if path.is_file() and path.name.lower() != "readme.md"
    )


def read_document(root: Path, path: Path) -> SourceDocument:
    """Read one file and return its document record.

    The hash covers the raw bytes, front matter included, so a title change counts as a
    change. Bytes are decoded without newline translation for the same reason as the \\r?
    in the patterns above.
    """
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DocumentError(f"{path.name} is not valid UTF-8: {error}") from error

    source_path = path.relative_to(root).as_posix()
    title, body_start = parse_front_matter(source_path, text)
    return SourceDocument(
        source_path=source_path,
        title=title,
        text=text,
        body_start=body_start,
        content_hash=hashlib.sha256(raw).hexdigest(),
    )


def parse_front_matter(source_path: str, text: str) -> tuple[str, int]:
    """Return the document's title and the offset where its body begins.

    Only `key: value` lines are understood, which is all the corpus uses. A title is
    required, because it is what every chunk is labelled with for embedding and citation.
    Other keys are accepted and ignored.
    """
    match = _FRONT_MATTER.match(text)
    if match is None:
        raise DocumentError(
            f"{source_path} has no front matter. Start the file with a '---' block "
            "containing 'title: ...'."
        )

    fields: dict[str, str] = {}
    for line in match.group("block").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        field = _FIELD.match(line)
        if field is None:
            raise DocumentError(f"{source_path}: cannot read front matter line {line!r}")
        fields[field.group("key").lower()] = _unquote(field.group("value"))

    title = fields.get("title", "")
    if not title:
        raise DocumentError(f"{source_path}: front matter has no title")
    return title, match.end()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value
