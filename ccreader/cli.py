"""Command line entry point: `python -m ccreader`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ccreader import __version__
from ccreader.config import config_path, load_config, write_default_config
from ccreader.state import Store


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ccreader", description="Terminal novel reader.")
    p.add_argument("book", nargs="?", help=".txt or .epub file (default: last opened book)")
    p.add_argument("--repo", help="work repo used to build the noise corpus")
    p.add_argument("--rescan", action="store_true", help="rescan the repo for the noise corpus")
    p.add_argument("--chapter", type=int, help="start at chapter N (1-based)")
    p.add_argument("--wpm", type=int, help="reading speed (words per minute)")
    p.add_argument("--instant", action="store_true", help="show paragraphs instantly")
    p.add_argument("--config", type=Path, help=f"config file (default: {config_path()})")
    p.add_argument("--init-config", action="store_true",
                   help="write a default config file and exit")
    p.add_argument("--transcript", action="store_true", help="open the plain transcript view only")
    p.add_argument("--list-chapters", action="store_true", help="print chapters and exit")
    p.add_argument("--version", action="version", version=f"ccreader {__version__}")
    return p


def set_process_title(title: str) -> None:
    if not title:
        return
    try:
        import setproctitle
    except ImportError:
        return
    setproctitle.setproctitle(title)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.init_config:
        print(write_default_config(args.config))
        return 0
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        print(f"ccreader: bad config: {exc}", file=sys.stderr)
        return 1
    if args.wpm:
        config.wpm = args.wpm
    if args.instant:
        config.stream_mode = "instant"
    config.normalized()
    set_process_title(config.proc_title)

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
    from ccreader.noise import load_corpus

    repo = args.repo or config.repo
    if repo and not Path(repo).expanduser().is_dir():
        print(f"ccreader: repo not found: {repo}", file=sys.stderr)
        return 1
    corpus = load_corpus(repo, store, rescan=args.rescan)
    ReaderApp(book, store, config, corpus=corpus, start=start,
              transcript_only=args.transcript).run()
    return 0
