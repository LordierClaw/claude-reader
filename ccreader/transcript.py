"""Ctrl+O transcript view: the novel only, without noise, for re-reading."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ccreader.book import Book
from ccreader.render import NOISE, novel_paragraph
from ccreader.screens import BaseScreen


class TranscriptScreen(BaseScreen):
    DEFAULT_CSS = """
    TranscriptScreen { background: ansi_default; }
    #tx-body { height: 1fr; scrollbar-size-vertical: 1; }
    #tx-body > Static { padding: 0 1 0 1; margin-bottom: 1; }
    #tx-body > .title { text-style: bold; margin-top: 1; }
    #tx-footer { height: 1; padding: 0 1; }
    """

    def __init__(self, book: Book, chapter: int, para: int, max_width: int = 78,
                 standalone: bool = False) -> None:
        super().__init__()
        self.book = book
        self.chapter = chapter
        self.mark = (chapter, para)
        self.max_width = max_width
        self.standalone = standalone

    def compose(self) -> ComposeResult:
        body = VerticalScroll(id="tx-body")
        body.can_focus = False
        yield body
        hint = Text("Showing detailed transcript · ctrl+o to toggle", style=NOISE)
        yield Static(hint, id="tx-footer")

    async def on_mount(self) -> None:
        await self.show_chapter(self.chapter)

    async def show_chapter(self, chapter: int) -> None:
        self.chapter = chapter
        body = self.query_one("#tx-body", VerticalScroll)
        await body.remove_children()
        ch = self.book.chapters[chapter]
        widgets = [Static(Text(ch.title), classes="title")]
        target = None
        for i, para in enumerate(ch.paragraphs):
            current = (chapter, i) == self.mark
            w = Static(novel_paragraph(para, bullet=True, current=current))
            if current:
                target = w
            widgets.append(w)
        for w in widgets:
            w.styles.max_width = self.max_width + 4
        await body.mount_all(widgets)
        if target is not None:
            self.call_after_refresh(body.scroll_to_widget, target, animate=False, top=True)
        else:
            body.scroll_home(animate=False)

    async def handle_key(self, event: events.Key) -> None:
        body = self.query_one("#tx-body", VerticalScroll)
        key = event.key
        if key in ("j", "down", "enter"):
            body.scroll_relative(y=1, animate=False)
        elif key in ("k", "up"):
            body.scroll_relative(y=-1, animate=False)
        elif key in ("pagedown", "space", "f", "ctrl+d"):
            body.scroll_page_down(animate=False)
        elif key in ("pageup", "b", "ctrl+u"):
            body.scroll_page_up(animate=False)
        elif key in ("g", "home"):
            body.scroll_home(animate=False)
        elif key in ("G", "end", "shift+g"):
            body.scroll_end(animate=False)
        elif key in ("right_square_bracket", "n", "l"):
            if self.chapter + 1 < len(self.book.chapters):
                await self.show_chapter(self.chapter + 1)
        elif key in ("left_square_bracket", "p", "h"):
            if self.chapter > 0:
                await self.show_chapter(self.chapter - 1)
        elif key in ("q", "ctrl+o"):
            self.close()

    def on_single_escape(self) -> None:
        self.close()

    def close(self) -> None:
        if self.standalone:
            self.app.exit()
        else:
            self.dismiss()
