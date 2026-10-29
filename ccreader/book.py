"""Loading novels (.txt / .epub) and splitting them into chapters and paragraphs."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CHAPTER_RE = r"^\s*(Chương|CHƯƠNG|Chapter|CHAPTER|Hồi|HỒI)\s+(\d+|[IVXLCDM]+)\b.*$"

# Paragraphs longer than this are split at sentence boundaries.
MAX_PARAGRAPH_CHARS = 900
TARGET_CHUNK_CHARS = 600
# Without chapter headings, text is grouped into pseudo-chapters of this size.
PSEUDO_CHAPTER_PARAGRAPHS = 60

_SENTENCE_END_RE = re.compile(r"[.!?…。]+[\"'”’»)\]]*\s+")
_WS_RE = re.compile(r"[ \t ]+")


@dataclass
class Chapter:
    title: str
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class Book:
    book_id: str
    chapters: list[Chapter]
    kind: str = "txt"

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "kind": self.kind,
            "chapters": [{"title": c.title, "paragraphs": c.paragraphs} for c in self.chapters],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        return cls(
            book_id=data["book_id"],
            kind=data.get("kind", "txt"),
            chapters=[Chapter(c["title"], list(c["paragraphs"])) for c in data["chapters"]],
        )

    @property
    def total_paragraphs(self) -> int:
        return sum(len(c.paragraphs) for c in self.chapters)

    def clamp(self, chapter: int, para: int) -> tuple[int, int]:
        """Return a valid (chapter, paragraph) position closest to the given one."""
        if not self.chapters:
            return 0, 0
        chapter = max(0, min(chapter, len(self.chapters) - 1))
        n = len(self.chapters[chapter].paragraphs)
        para = max(0, min(para, max(n - 1, 0)))
        return chapter, para

    def next_pos(self, chapter: int, para: int) -> tuple[int, int] | None:
        """Position after (chapter, para), or None at the end of the book."""
        if para + 1 < len(self.chapters[chapter].paragraphs):
            return chapter, para + 1
        for c in range(chapter + 1, len(self.chapters)):
            if self.chapters[c].paragraphs:
                return c, 0
        return None

    def chapter_progress(self, chapter: int, para: int) -> float:
        n = len(self.chapters[chapter].paragraphs)
        return 0.0 if n == 0 else min(1.0, (para + 1) / n)

    def book_progress(self, chapter: int, para: int) -> float:
        total = self.total_paragraphs
        if total == 0:
            return 0.0
        done = sum(len(c.paragraphs) for c in self.chapters[:chapter]) + para + 1
        return min(1.0, done / total)


def book_id_for(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def normalize(text: str) -> str:
    """NFC-normalize (Vietnamese text is often decomposed) and tidy whitespace."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("﻿", "")
    return text


def clean_paragraph(text: str) -> str:
    return _WS_RE.sub(" ", text.replace("\n", " ")).strip()


def split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for m in _SENTENCE_END_RE.finditer(text):
        parts.append(text[start:m.end()].strip())
        start = m.end()
    parts.append(text[start:].strip())
    return [p for p in parts if p]


def split_long(paragraph: str, max_chars: int = MAX_PARAGRAPH_CHARS,
               target: int = TARGET_CHUNK_CHARS) -> list[str]:
    """Split an over-long paragraph into chunks, only at sentence boundaries."""
    if len(paragraph) <= max_chars:
        return [paragraph]
    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(paragraph):
        if current and len(current) + 1 + len(sentence) > target:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        chunks.append(current)
    return chunks


def split_paragraphs(text: str) -> list[str]:
    """Split a block of plain text into paragraphs.

    Text with blank lines between paragraphs (possibly hard-wrapped) is split on
    blank lines. Text where every line is a paragraph (common for web novels) is
    split on newlines.
    """
    lines = text.strip("\n").split("\n")
    non_blank = sum(1 for line in lines if line.strip())
    blank = len(lines) - non_blank
    if non_blank == 0:
        return []
    if blank < 0.2 * non_blank:
        raw = [line for line in lines if line.strip()]
    else:
        raw = [block for block in re.split(r"\n\s*\n", text) if block.strip()]
    out: list[str] = []
    for block in raw:
        para = clean_paragraph(block)
        if para:
            out.extend(split_long(para))
    return out


def parse_txt(text: str, chapter_regex: str | None = None) -> list[Chapter]:
    text = normalize(text)
    pattern = re.compile(chapter_regex or DEFAULT_CHAPTER_RE, re.MULTILINE)
    matches = list(pattern.finditer(text))
    chapters: list[Chapter] = []
    if not matches:
        paragraphs = split_paragraphs(text)
        for i in range(0, len(paragraphs), PSEUDO_CHAPTER_PARAGRAPHS):
            chapters.append(Chapter(f"Part {i // PSEUDO_CHAPTER_PARAGRAPHS + 1}",
                                    paragraphs[i:i + PSEUDO_CHAPTER_PARAGRAPHS]))
        return chapters
    preface = split_paragraphs(text[: matches[0].start()])
    if preface:
        chapters.append(Chapter("Preface", preface))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = split_paragraphs(text[m.end():end])
        chapters.append(Chapter(clean_paragraph(m.group(0)), body))
    return chapters


def _flatten_toc(toc) -> dict[str, str]:
    titles: dict[str, str] = {}
    for entry in toc:
        if isinstance(entry, (list, tuple)):
            section, children = entry[0], entry[1] if len(entry) > 1 else []
            href = getattr(section, "href", None)
            if href:
                titles.setdefault(href.split("#")[0], section.title)
            titles.update({k: v for k, v in _flatten_toc(children).items() if k not in titles})
        else:
            href = getattr(entry, "href", None)
            if href:
                titles.setdefault(href.split("#")[0], entry.title)
    return titles


def parse_epub(path: str | Path) -> list[Chapter]:
    import warnings

    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        book = epub.read_epub(str(path), options={"ignore_ncx": True})
    toc_titles = _flatten_toc(book.toc)
    chapters: list[Chapter] = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()
        heading = soup.find(["h1", "h2", "h3"])
        heading_text = clean_paragraph(normalize(heading.get_text(" "))) if heading else ""
        blocks = soup.find_all(["p", "blockquote", "li"])
        if blocks:
            texts = [b.get_text(" ") for b in blocks if not b.find_parent(["p", "blockquote", "li"])]
        else:
            body = soup.body or soup
            texts = body.get_text("\n").split("\n")
        paragraphs: list[str] = []
        for t in texts:
            para = clean_paragraph(normalize(t))
            if para and para != heading_text:
                paragraphs.extend(split_long(para))
        if not paragraphs:
            continue
        title = toc_titles.get(item.get_name()) or heading_text or f"Chapter {len(chapters) + 1}"
        chapters.append(Chapter(clean_paragraph(normalize(title)), paragraphs))
    return chapters


def load_book(path: str | Path, chapter_regex: str | None = None) -> Book:
    path = Path(path).expanduser()
    data = path.read_bytes()
    bid = book_id_for(data)
    if path.suffix.lower() == ".epub":
        chapters = parse_epub(path)
        kind = "epub"
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        chapters = parse_txt(text, chapter_regex)
        kind = "txt"
    chapters = [c for c in chapters if c.paragraphs]
    if not chapters:
        raise ValueError("no readable text found")
    return Book(book_id=bid, chapters=chapters, kind=kind)
