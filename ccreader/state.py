"""Local state: bookmarks and caches, stored gzip+base64 under hashed file names.

Nothing written here contains the book title or file name in clear text.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ccreader.book import Book, book_id_for, load_book


def config_dir() -> Path:
    if env := os.environ.get("CCREADER_CONFIG_DIR"):
        return Path(env)
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "ccreader"


def cache_dir() -> Path:
    if env := os.environ.get("CCREADER_CACHE_DIR"):
        return Path(env)
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "ccreader"


def encode(obj: Any) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, mtime=0))


def decode(data: bytes) -> Any:
    return json.loads(gzip.decompress(base64.b64decode(data)).decode("utf-8"))


class Store:
    """Key/value store of encoded blobs under the cache directory."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else cache_dir()

    def path_for(self, *key: str) -> Path:
        digest = hashlib.sha256("\0".join(("ccreader",) + key).encode()).hexdigest()[:24]
        return self.root / f"{digest}.dat"

    def get(self, *key: str, default: Any = None) -> Any:
        path = self.path_for(*key)
        try:
            return decode(path.read_bytes())
        except (OSError, ValueError):
            return default

    def put(self, value: Any, *key: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(*key)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(encode(value))
        os.replace(tmp, path)

    # -- state (bookmarks, last opened book) -------------------------------

    def _state(self) -> dict:
        state = self.get("state", default=None)
        return state if isinstance(state, dict) else {"bookmarks": {}, "last": None}

    def get_bookmark(self, book_id: str) -> tuple[int, int] | None:
        mark = self._state()["bookmarks"].get(book_id)
        return (int(mark[0]), int(mark[1])) if mark else None

    def set_bookmark(self, book_id: str, chapter: int, para: int) -> None:
        state = self._state()
        state["bookmarks"][book_id] = [chapter, para]
        state["last"] = book_id
        self.put(state, "state")

    def last_book_id(self) -> str | None:
        return self._state().get("last")

    def set_last(self, book_id: str) -> None:
        state = self._state()
        state["last"] = book_id
        self.put(state, "state")

    # -- book cache --------------------------------------------------------

    def cached_book(self, book_id: str) -> Book | None:
        data = self.get("book", book_id)
        return Book.from_dict(data) if data else None

    def cache_book(self, book: Book) -> None:
        self.put(book.to_dict(), "book", book.book_id)

    def open_book(self, path: str | Path | None, chapter_regex: str | None = None) -> Book:
        """Load a book from path (via cache), or the last opened book if path is None."""
        if path is None:
            last = self.last_book_id()
            book = self.cached_book(last) if last else None
            if book is None:
                raise FileNotFoundError("no book given and no previous book in cache")
            return book
        path = Path(path).expanduser()
        bid = book_id_for(path.read_bytes())
        book = None if chapter_regex else self.cached_book(bid)
        if book is None:
            book = load_book(path, chapter_regex)
            self.cache_book(book)
        self.set_last(book.book_id)
        return book
