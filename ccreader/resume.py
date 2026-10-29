"""The `/resume` picker: chapters shown as past sessions."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.widgets import Static

from ccreader.render import CLAUDE_ORANGE, NOISE
from ccreader.screens import BaseScreen
from ccreader.sessions import Session


class SessionList(Static):
    def __init__(self, sessions: list[Session], selected: int) -> None:
        super().__init__()
        self.sessions = sessions
        self.selected = selected

    def move(self, delta: int) -> None:
        self.selected = max(0, min(len(self.sessions) - 1, self.selected + delta))
        self.refresh()

    def render(self) -> RenderableType:
        rows = max(3, self.size.height - 1)
        top = max(0, min(self.selected - rows // 2, len(self.sessions) - rows))
        header = Text(f"     {'Modified':<10}{'# Messages':<12}{'Git Branch':<28}Summary",
                      style="bold")
        lines = [header]
        for i, s in enumerate(self.sessions[top:top + rows], start=top):
            chosen = i == self.selected
            line = Text("❯ " if chosen else "  ", style=CLAUDE_ORANGE)
            body = f"{i + 1:>2}. {s.modified:<10}{s.messages:<12}{s.branch[:26]:<28}{s.summary}"
            line.append(body, style=CLAUDE_ORANGE if chosen else "")
            line.no_wrap, line.overflow = True, "ellipsis"
            lines.append(line)
        return Group(*lines)


class ResumeScreen(BaseScreen):
    DEFAULT_CSS = """
    ResumeScreen { background: ansi_default; }
    #resume-title { padding: 1 1 1 1; }
    SessionList { height: 1fr; padding: 0 1; }
    #resume-hint { height: 1; padding: 0 1; }
    """

    def __init__(self, sessions: list[Session], current: int) -> None:
        super().__init__()
        self.sessions = sessions
        self.current = current

    def compose(self) -> ComposeResult:
        yield Static(Text("Resume a previous conversation", style="bold"), id="resume-title")
        yield SessionList(self.sessions, self.current)
        yield Static(Text("↑/↓ to select · Enter to resume · Esc to cancel", style=NOISE),
                     id="resume-hint")

    async def handle_key(self, event: events.Key) -> None:
        lst = self.query_one(SessionList)
        key = event.key
        if key in ("up", "k"):
            lst.move(-1)
        elif key in ("down", "j"):
            lst.move(1)
        elif key == "pageup":
            lst.move(-10)
        elif key == "pagedown":
            lst.move(10)
        elif key in ("home", "g"):
            lst.move(-len(self.sessions))
        elif key in ("end", "G"):
            lst.move(len(self.sessions))
        elif key == "enter":
            self.dismiss(self.sessions[lst.selected].chapter)
        elif key == "ctrl+o":
            self.dismiss(None)

    def on_single_escape(self) -> None:
        self.dismiss(None)
