"""The Textual application."""

from __future__ import annotations

from textual.app import App

from ccreader.book import Book
from ccreader.config import Config
from ccreader.state import Store
from ccreader.transcript import TranscriptScreen


class ReaderApp(App, inherit_bindings=False):
    ESCAPE_TO_MINIMIZE = False
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, book: Book, store: Store, config: Config,
                 start: tuple[int, int] | None = None) -> None:
        super().__init__(ansi_color=True)
        self.book = book
        self.store = store
        self.config = config
        mark = start or store.get_bookmark(book.book_id) or (0, 0)
        self.position = book.clamp(*mark)

    def on_mount(self) -> None:
        self.theme = "ansi-light" if self.config.theme == "light" else "ansi-dark"
        chapter, para = self.position
        self.push_screen(TranscriptScreen(self.book, chapter, para,
                                          self.config.max_width, standalone=True))

    def boss_key(self) -> None:
        self.exit()

    def panic_quit(self) -> None:
        self.exit()
