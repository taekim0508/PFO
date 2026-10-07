"""Split a document into chunks small enough to embed, each tied to where it came from.

The document is first cut at its headings, so no chunk straddles two sections. A section
that fits is one chunk. A section that does not is split recursively: at blank lines
first, then at sentence ends, then by a hard cut, going a level deeper only for a piece
that is still over the limit. Adjacent small pieces are then packed back together up to
the limit, and each chunk after the first in a section starts a little before the previous
one ended, so a sentence cut at a boundary still appears whole in one of the two.

Every chunk is a span of the original file. Its text is exactly `text[char_start:char_end]`,
which is what lets a citation point at a real place in a real file. Nothing is rewritten:
no whitespace collapsed, no markdown stripped.

Code fences are never split at a blank line or a sentence end inside them. Only a fence
longer than the whole limit gets a hard cut, because there is no other way to make it fit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(?P<marks>#{1,6})[ \t]+(?P<title>.+?)[ \t]*#*[ \t]*\r?$", re.MULTILINE)
_FENCE_LINE = re.compile(r"^ {0,3}(?:```|~~~)", re.MULTILINE)
# A split point after a blank line: the next piece begins at the first non-blank character.
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\r?\n\s*")
# A split point after a sentence: terminal punctuation, optional closing quote or bracket,
# then whitespace. The next piece begins after the whitespace.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"')\]]*\s+")

Span = tuple[int, int]


@dataclass(frozen=True)
class Chunk:
    """One slice of a document, with the headings above it and its place in the file."""

    ordinal: int
    text: str
    heading_path: tuple[str, ...]
    char_start: int
    char_end: int


def chunk_document(text: str, body_start: int, size: int, overlap: int) -> list[Chunk]:
    """Split `text[body_start:]` into chunks of at most `size` characters.

    `overlap` is how many characters of the previous chunk a following chunk in the same
    section may repeat. It is a ceiling, not an exact amount: the start is moved forward to
    a word boundary, and dropped entirely when it would push the chunk over `size`.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be at least 0 and less than size")

    fences = _fence_spans(text, body_start)
    chunks: list[Chunk] = []
    for start, end, path in _sections(text, body_start, fences):
        pieces = _split(text, start, end, size, 0, fences)
        for chunk_start, chunk_end in _pack(text, pieces, start, size, overlap, fences):
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    text=text[chunk_start:chunk_end],
                    heading_path=path,
                    char_start=chunk_start,
                    char_end=chunk_end,
                )
            )
    return chunks


def _fence_spans(text: str, start: int) -> list[Span]:
    """Spans of fenced code blocks, from the opening fence line to the end of the closing one.

    An unclosed fence runs to the end of the file, which is how markdown renders it.
    """
    spans: list[Span] = []
    opened: int | None = None
    for match in _FENCE_LINE.finditer(text, start):
        if opened is None:
            opened = match.start()
        else:
            line_end = text.find("\n", match.end())
            spans.append((opened, len(text) if line_end == -1 else line_end + 1))
            opened = None
    if opened is not None:
        spans.append((opened, len(text)))
    return spans


def _inside(position: int, fences: list[Span]) -> int | None:
    """The end of the fence strictly containing `position`, or None if it is outside all."""
    for fence_start, fence_end in fences:
        if fence_start < position < fence_end:
            return fence_end
    return None


def _sections(
    text: str, body_start: int, fences: list[Span]
) -> list[tuple[int, int, tuple[str, ...]]]:
    """Cut the body at headings, returning each section's span and the headings above it.

    A section runs from its heading line to the next heading of any level. Its path is the
    chain of enclosing headings, outermost first, including its own. A section with no
    content beyond its heading line is dropped; its title still appears in the paths of the
    sections nested under it. Whitespace at either end of a section is trimmed off its span.
    """
    headings = [
        match
        for match in _HEADING.finditer(text, body_start)
        if _inside(match.start(), fences) is None
    ]

    sections: list[tuple[int, int, tuple[str, ...]]] = []
    stack: list[tuple[int, str]] = []
    boundaries = [body_start, *(match.start() for match in headings), len(text)]
    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        heading_end = start
        if index > 0:
            heading = headings[index - 1]
            level = len(heading.group("marks"))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading.group("title")))
            heading_end = heading.end()

        if not text[heading_end:end].strip():
            continue
        start, end = _trim(text, start, end)
        sections.append((start, end, tuple(title for _, title in stack)))
    return sections


def _trim(text: str, start: int, end: int) -> Span:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _split(
    text: str, start: int, end: int, size: int, level: int, fences: list[Span]
) -> list[Span]:
    """Cover [start, end) with contiguous pieces, each at most `size` characters.

    Level 0 splits at blank lines, level 1 at sentence ends, level 2 by a hard cut. A piece
    that fits is kept whole; one that does not is split again one level down.
    """
    if end - start <= size:
        return [(start, end)]
    if level >= 2:
        return _hard_cut(text, start, end, size)

    pattern = _PARAGRAPH_BREAK if level == 0 else _SENTENCE_BREAK
    points = [
        match.end()
        for match in pattern.finditer(text, start, end)
        if start < match.end() < end and _inside(match.end(), fences) is None
    ]
    if not points:
        return _split(text, start, end, size, level + 1, fences)

    pieces: list[Span] = []
    for piece_start, piece_end in zip([start, *points], [*points, end], strict=True):
        pieces.extend(_split(text, piece_start, piece_end, size, level + 1, fences))
    return pieces


def _hard_cut(text: str, start: int, end: int, size: int) -> list[Span]:
    """Cut into pieces of at most `size`, at the last whitespace before the limit if any."""
    pieces: list[Span] = []
    while end - start > size:
        limit = start + size
        cut = max(text.rfind(" ", start + 1, limit + 1), text.rfind("\n", start + 1, limit + 1))
        if cut <= start:
            cut = limit
        pieces.append((start, cut))
        start = cut
    pieces.append((start, end))
    return pieces


def _pack(
    text: str, pieces: list[Span], section_start: int, size: int, overlap: int, fences: list[Span]
) -> list[Span]:
    """Join adjacent pieces into chunks of at most `size`, with overlap, trimmed of whitespace."""
    chunks: list[Span] = []
    current: Span | None = None
    for piece_start, piece_end in pieces:
        if current is None:
            current = (piece_start, piece_end)
        elif _trimmed_length(text, current[0], piece_end) <= size:
            current = (current[0], piece_end)
        else:
            chunks.append(_trim(text, *current))
            start = _overlap_start(text, current[1], section_start, overlap, fences)
            if start is None or _trimmed_length(text, start, piece_end) > size:
                start = piece_start
            current = (start, piece_end)
    if current is not None:
        chunks.append(_trim(text, *current))
    return [chunk for chunk in chunks if chunk[0] < chunk[1]]


def _trimmed_length(text: str, start: int, end: int) -> int:
    trimmed_start, trimmed_end = _trim(text, start, end)
    return trimmed_end - trimmed_start


def _overlap_start(
    text: str, previous_end: int, section_start: int, overlap: int, fences: list[Span]
) -> int | None:
    """Where a chunk starting right after `previous_end` should begin to repeat its tail.

    Steps back `overlap` characters, then forward to the start of the next word so the
    chunk does not open mid-word. A start that lands inside a code fence moves to the end
    of the fence, so no chunk begins halfway through one. None means no overlap.
    """
    if overlap == 0:
        return None
    position = max(previous_end - overlap, section_start)
    if position > section_start and not text[position - 1].isspace():
        while position < previous_end and not text[position].isspace():
            position += 1
    while position < previous_end and text[position].isspace():
        position += 1
    fence_end = _inside(position, fences)
    if fence_end is not None:
        position = fence_end
    return position if position < previous_end else None
