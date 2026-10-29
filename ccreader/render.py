"""Shared Rich styles and renderables that mimic Claude Code's output."""

from __future__ import annotations

from rich.cells import cell_len
from rich.style import Style
from rich.table import Table
from rich.text import Text

CLAUDE_ORANGE = "#d77757"
NOISE = Style(dim=True)
NOVEL = Style()
MARKER = "▏"
BULLET = "● "
ELBOW = "  ⎿  "


def hanging(prefix: Text | str, body: Text | str, *, style: Style | str = "") -> Table:
    """Render `prefix` followed by `body` wrapped with a hanging indent."""
    prefix = Text(prefix) if isinstance(prefix, str) else prefix
    body = Text(body) if isinstance(body, str) else body
    grid = Table.grid(padding=0, expand=True)
    grid.add_column(width=max(cell_len(prefix.plain), 1), no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")
    grid.add_row(prefix, body, style=style)
    return grid


def novel_paragraph(text: str, *, bullet: bool, current: bool) -> Table:
    """A novel paragraph shown as an assistant message: `▏● text`."""
    prefix = Text()
    prefix.append(MARKER if current else " ", style=NOISE)
    prefix.append(BULLET if bullet else "  ")
    return hanging(prefix, Text(text, style=NOVEL))


def wrapped_line_count(text: str, width: int) -> int:
    """Approximate number of terminal lines `text` occupies at `width` columns."""
    width = max(width, 10)
    lines = Text(text).wrap(_console(), width)
    return max(1, len(lines))


_CONSOLE = None


def _console():
    global _CONSOLE
    if _CONSOLE is None:
        import io

        from rich.console import Console

        _CONSOLE = Console(width=200, file=io.StringIO())
    return _CONSOLE
