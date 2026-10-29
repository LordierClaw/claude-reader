"""Command line entry point: `python -m ccreader`."""

from __future__ import annotations

import argparse
import sys

from ccreader import __version__
from ccreader.config import load_config
from ccreader.state import Store


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ccreader", description="Terminal novel reader.")
    p.add_argument("book", nargs="?", help=".txt or .epub file (default: last opened book)")
    p.add_argument("--chapter", type=int, help="start at chapter N (1-based)")
    p.add_argument("--list-chapters", action="store_true", help="print chapters and exit")
    p.add_argument("--version", action="version", version=f"ccreader {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    store = Store()
    try:
        book = store.open_book(args.book, config.chapter_regex)
    except (OSError, ValueError) as exc:
        print(f"ccreader: {exc}", file=sys.stderr)
        return 1

    if args.list_chapters:
        mark = store.get_bookmark(book.book_id)
        for i, ch in enumerate(book.chapters):
            here = " <" if mark and mark[0] == i else ""
            print(f"{i + 1:4d}  {ch.title}  ({len(ch.paragraphs)} paragraphs){here}")
        return 0

    start = None
    if args.chapter is not None:
        start = book.clamp(args.chapter - 1, 0)

    from ccreader.app import ReaderApp

    ReaderApp(book, store, config, start=start).run()
    return 0
