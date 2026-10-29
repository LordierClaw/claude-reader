"""`/resume`: the chapter list, disguised as a list of past sessions."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from ccreader.book import Book
from ccreader.noise import NoiseCorpus

VERBS = ["refactor", "fix", "add tests for", "clean up", "investigate", "migrate",
         "speed up", "harden", "document", "simplify", "review", "debug"]
_CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


@dataclass
class Session:
    chapter: int
    summary: str
    modified: str
    messages: int
    branch: str


def humanize(words: str) -> str:
    return " ".join(w.lower() for w in _CAMEL_RE.findall(words)) or words.lower()


def ago(minutes: int) -> str:
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    if minutes < 60 * 24:
        return f"{minutes // 60}h ago"
    return f"{minutes // (60 * 24)}d ago"


def build_sessions(book: Book, corpus: NoiseCorpus, current: int) -> list[Session]:
    """One "session" per chapter. The summary is stable for a given chapter."""
    sessions = []
    for i, ch in enumerate(book.chapters):
        rng = random.Random(f"{book.book_id}:{i}")
        subject = humanize(rng.choice(corpus.classes))
        summary = f"{rng.choice(VERBS)} {subject} – ch.{i + 1}"
        distance = abs(current - i)
        minutes = 2 if i == current else distance * rng.randint(90, 600)
        branch = corpus.branch if i == current else rng.choice(
            [corpus.branch, "main", f"feature/{subject.replace(' ', '-')}"])
        sessions.append(Session(i, summary, ago(minutes), len(ch.paragraphs) * 2 + 3, branch))
    return sessions
