"""The loader finds the corpus files and reads their titles and fingerprints."""

import hashlib

import pytest

from portfolio_bot.ingest.loader import DocumentError, discover, parse_front_matter, read_document


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def test_reads_title_and_where_the_body_starts(tmp_path):
    text = "---\ntitle: About Tae\n---\n\n## Background\n\nBody.\n"
    path = write(tmp_path / "about.md", text)

    document = read_document(tmp_path, path)

    assert document.title == "About Tae"
    assert document.source_path == "about.md"
    assert document.text == text
    assert text[document.body_start :] == "\n## Background\n\nBody.\n"


def test_hash_is_of_the_raw_file_and_changes_with_any_edit(tmp_path):
    path = write(tmp_path / "a.md", "---\ntitle: A\n---\nOne.\n")
    first = read_document(tmp_path, path).content_hash
    assert first == hashlib.sha256(path.read_bytes()).hexdigest()

    write(path, "---\ntitle: A2\n---\nOne.\n")
    assert read_document(tmp_path, path).content_hash != first


def test_source_path_is_relative_to_the_root_with_forward_slashes(tmp_path):
    path = write(tmp_path / "projects" / "abroadly.md", "---\ntitle: Abroadly\n---\nText.\n")
    assert read_document(tmp_path, path).source_path == "projects/abroadly.md"


def test_discover_finds_markdown_recursively_and_skips_readme(tmp_path):
    write(tmp_path / "b.md", "")
    write(tmp_path / "a.md", "")
    write(tmp_path / "nested" / "c.md", "")
    write(tmp_path / "README.md", "")
    write(tmp_path / "notes.txt", "")

    found = [path.relative_to(tmp_path).as_posix() for path in discover(tmp_path)]

    assert found == ["a.md", "b.md", "nested/c.md"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("## No front matter\n", "no front matter"),
        ("---\ntags: x\n---\nBody\n", "no title"),
        ("---\ntitle:\n---\nBody\n", "no title"),
        ("---\njust words\n---\nBody\n", "cannot read"),
    ],
)
def test_rejects_unusable_front_matter(text, message):
    with pytest.raises(DocumentError, match=message):
        parse_front_matter("x.md", text)


def test_quoted_title_and_other_keys(tmp_path):
    title, _ = parse_front_matter("x.md", '---\ntitle: "Quoted: yes"\ntags: a, b\n---\nBody\n')
    assert title == "Quoted: yes"


def test_windows_line_endings_keep_offsets_true_to_the_file():
    text = "---\r\ntitle: A\r\n---\r\nBody\r\n"
    title, body_start = parse_front_matter("x.md", text)
    assert title == "A"
    assert text[body_start:] == "Body\r\n"


def test_invalid_utf8_is_a_document_error(tmp_path):
    path = tmp_path / "bad.md"
    path.write_bytes(b"---\ntitle: A\n---\n\xff\n")
    with pytest.raises(DocumentError, match="UTF-8"):
        read_document(tmp_path, path)
