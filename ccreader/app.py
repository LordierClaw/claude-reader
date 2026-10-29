"""The Textual application."""

from __future__ import annotations

import random

from textual.app import App

from ccreader.book import Book
from ccreader.config import Config
from ccreader.noise import NoiseCorpus, builtin_corpus
from ccreader.scheduler import InteractionScheduler
from ccreader.state import Store
from ccreader.transcript import TranscriptScreen
from ccreader.turns import TurnBuilder


class ReaderApp(App, inherit_bindings=False):
    ESCAPE_TO_MINIMIZE = False
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, book: Book, store: Store, config: Config,
                 corpus: NoiseCorpus | None = None, start: tuple[int, int] | None = None,
                 transcript_only: bool = False, rng: random.Random | None = None,
                 clock=None) -> None:
        super().__init__(ansi_color=True)
        self.book = book
        self.store = store
        self.config = config
        self.corpus = corpus or builtin_corpus()
        self.rng = rng or random.Random()
        self.transcript_only = transcript_only
        mark = start or store.get_bookmark(book.book_id) or (0, 0)
        self.position = book.clamp(*mark)
        self.wpm = config.wpm
        self.stream_mode = config.stream_mode
        self.tokens = self.rng.randint(9_000, 22_000)
        self.builder = TurnBuilder(book, self.corpus, self.rng, config.paragraphs_per_turn)
        sched_args = {"clock": clock} if clock else {}
        self.scheduler = InteractionScheduler(config.interaction_min_minutes,
                                              config.interaction_max_minutes, self.rng,
                                              **sched_args)

    def on_mount(self) -> None:
        self.theme = "ansi-light" if self.config.theme == "light" else "ansi-dark"
        if self.transcript_only:
            chapter, para = self.position
            self.push_screen(TranscriptScreen(self.book, chapter, para,
                                              self.config.max_width, standalone=True))
        else:
            from ccreader.main_screen import MainScreen

            self.push_screen(MainScreen())

    @property
    def main(self):
        from ccreader.main_screen import MainScreen

        for screen in self.screen_stack:
            if isinstance(screen, MainScreen):
                return screen
        return None

    def set_position(self, pos: tuple[int, int]) -> None:
        self.position = pos
        self.store.set_bookmark(self.book.book_id, *pos)
        if self.main is not None:
            self.main.update_status()

    def open_transcript(self) -> None:
        if isinstance(self.screen, TranscriptScreen):
            return
        chapter, para = self.position
        self.push_screen(TranscriptScreen(self.book, chapter, para, self.config.max_width))

    def open_resume(self) -> None:
        from ccreader.resume import ResumeScreen
        from ccreader.sessions import build_sessions

        if isinstance(self.screen, ResumeScreen):
            return
        current = self.position[0]
        sessions = build_sessions(self.book, self.corpus, current)
        self.push_screen(ResumeScreen(sessions, current), callback=self._resume_chosen)

    def _resume_chosen(self, chapter: int | None) -> None:
        if chapter is None or self.main is None:
            return
        pos = self.position if chapter == self.position[0] else (chapter, 0)
        self.main.jump_to(self.book.clamp(*pos))

    def boss_key(self) -> None:
        """Esc Esc: hide the novel (from any view), or resume when already hidden."""
        if self.transcript_only:
            self.exit()
            return
        main = self.main
        if main is None:
            return
        if self.screen is not main:
            while self.screen is not main:
                self.pop_screen()
            main.boss()
        elif main.bossed:
            main.resume()
        else:
            main.boss()

    def on_app_blur(self) -> None:
        main = self.main
        if self.config.boss_on_blur and main is not None and not main.bossed:
            while self.screen is not main:
                self.pop_screen()
            main.boss()

    def panic_quit(self) -> None:
        self.exit()
