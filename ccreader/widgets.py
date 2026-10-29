"""Widgets that draw a Claude-Code-like session."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static

from ccreader.fakes import ToolCall
from ccreader.scheduler import CHOICE, COMPACT, PERMISSION, Interaction
from ccreader.render import (
    BULLET,
    CLAUDE_ORANGE,
    ELBOW,
    MARKER,
    NOISE,
    NOVEL,
    hanging,
    wrapped_line_count,
)

SPINNER_FRAMES = "·✢✳✶✻✽✻✶✳✢"


def _line(text: Text) -> Text:
    text.no_wrap = True
    text.overflow = "ellipsis"
    return text


class WelcomeBox(Static):
    DEFAULT_CSS = "WelcomeBox { width: auto; max-width: 72; margin: 1 0 1 0; }"

    def __init__(self, cwd: str) -> None:
        super().__init__()
        self.cwd = cwd

    def render(self) -> RenderableType:
        body = Text()
        body.append("✻", style=CLAUDE_ORANGE)
        body.append(" Welcome to ", style="bold")
        body.append("Claude Code", style="bold")
        body.append("!\n\n")
        body.append("  /help for help, /status for your current setup\n\n", style=NOISE)
        body.append(f"  cwd: {self.cwd}", style=NOISE)
        return Panel(body, border_style=CLAUDE_ORANGE, padding=(0, 1), expand=False)


class NovelBlock(Static):
    """One novel paragraph. Can be partially revealed, marked current, or collapsed."""

    DEFAULT_CSS = "NovelBlock { margin-top: 1; }"

    def __init__(self, text: str, *, chapter: int, para: int, turn: int, bullet: bool,
                 title: bool = False, max_width: int = 78) -> None:
        super().__init__()
        self.text = text
        self.chapter = chapter
        self.para = para
        self.turn = turn
        self.bullet = bullet
        self.title = title
        self.max_width = max_width
        self.revealed = len(text)
        self.current = False
        self.collapsed = False
        # consecutive blocks collapse together into the first one of the group
        self.group: list[NovelBlock] = [self]
        self.styles.max_width = max_width + 3

    @property
    def fully_revealed(self) -> bool:
        return self.revealed >= len(self.text)

    def reveal(self, n: int) -> None:
        self.revealed = min(len(self.text), n)
        self.refresh(layout=True)

    def set_current(self, current: bool) -> None:
        if current != self.current:
            self.current = current
            self.refresh()

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed != self.collapsed:
            self.collapsed = collapsed
            if collapsed:
                self.current = False
            self.refresh(layout=True)

    def line_count(self) -> int:
        return wrapped_line_count(self.text, self.max_width)

    def render(self) -> RenderableType:
        if self.collapsed:
            n = sum(b.line_count() for b in self.group)
            return _line(Text(f"{ELBOW}… +{n} line{'s' if n != 1 else ''} (ctrl+o to expand)",
                              style=NOISE))
        prefix = Text()
        prefix.append(MARKER if self.current else " ", style=NOISE)
        prefix.append(BULLET if self.bullet else "  ")
        body = Text(self.text[: self.revealed], style="bold" if self.title else NOVEL)
        return hanging(prefix, body)

    def on_click(self) -> None:
        if self.collapsed:
            expand_group(self.group)
        elif self.fully_revealed and not self.current:
            collapse_group(self.group)


def collapse_group(group: list[NovelBlock]) -> None:
    head, *rest = group
    for block in group:
        block.group = group
    head.set_collapsed(True)
    for block in rest:
        block.set_collapsed(True)
        block.display = False


def expand_group(group: list[NovelBlock]) -> None:
    for block in group:
        block.display = True
        block.set_collapsed(False)


class ToolBlock(Static):
    """`● Name(arg)` with a dim `⎿ summary` and optional body lines."""

    DEFAULT_CSS = "ToolBlock { margin-top: 1; }"

    def __init__(self, call: ToolCall, *, done: bool = True) -> None:
        super().__init__()
        self.call = call
        self.done = done
        self.shown = len(call.body) if done else 0
        self.interrupted = False
        self.rejected = ""

    def finish(self) -> None:
        self.done = True
        self.shown = len(self.call.body)
        self.refresh(layout=True)

    def reject(self, message: str) -> None:
        self.done = True
        self.shown = 0
        self.rejected = message
        self.refresh(layout=True)

    def show_lines(self, n: int) -> None:
        self.done = True
        self.shown = min(n, len(self.call.body))
        self.refresh(layout=True)

    def render(self) -> RenderableType:
        c = self.call
        head = Text(" ")
        head.append("●", style="dim green" if self.done else "dim")
        head.append(" ")
        head.append(c.name, style="dim bold")
        head.append(f"({c.arg})", style=NOISE)
        lines: list[Text] = [_line(head)]
        if self.rejected:
            lines.append(_line(Text(f" {ELBOW}{self.rejected}", style=NOISE)))
            return Group(*lines)
        if self.done and c.summary:
            lines.append(_line(Text(f" {ELBOW}{c.summary}", style=NOISE)))
        for raw in c.body[: self.shown]:
            style = NOISE
            if c.name == "Update":
                if raw[5:6] == "+":
                    style = "dim green"
                elif raw[5:6] == "-":
                    style = "dim red"
            lines.append(_line(Text(f"      {raw}", style=style)))
        if self.done and self.shown >= len(c.body) and c.hidden:
            lines.append(_line(Text(f"      … +{c.hidden} lines (ctrl+r to expand)", style=NOISE)))
        if self.interrupted:
            lines.append(_line(Text(f" {ELBOW}Interrupted by user", style=NOISE)))
        return Group(*lines)


class NoteLine(Static):
    DEFAULT_CSS = "NoteLine { margin-top: 1; }"

    def __init__(self, text: RenderableType, *, margin: bool = True) -> None:
        super().__init__(Text(text, style=NOISE) if isinstance(text, str) else text)
        if not margin:
            self.styles.margin = (0, 0, 0, 0)


def agent_text(text: str) -> Text:
    t = Text(" ")
    t.append(BULLET, style=NOISE)
    t.append(text, style=NOISE)
    return t


def user_text(text: str) -> Text:
    return Text(f" > {text}", style=NOISE)


class Spinner(Static):
    DEFAULT_CSS = "Spinner { height: 1; margin-top: 1; }"

    def __init__(self, accent: str = CLAUDE_ORANGE) -> None:
        super().__init__()
        self.accent = accent
        self.verb = "Thinking"
        self.seconds = 0.0
        self.tokens = 0
        self.frame = 0
        self.active = False
        self.display = False

    def set_active(self, active: bool) -> None:
        self.active = active
        self.display = active
        self.refresh()

    def render(self) -> RenderableType:
        if not self.active:
            return Text("")
        t = Text(" ")
        t.append(SPINNER_FRAMES[self.frame % len(SPINNER_FRAMES)], style=self.accent)
        t.append(f" {self.verb}… ", style=self.accent)
        tok = f"{self.tokens / 1000:.1f}k" if self.tokens >= 1000 else str(self.tokens)
        t.append(f"({int(self.seconds)}s · ↑ {tok} tokens · esc to interrupt)", style=NOISE)
        return _line(t)


class PromptBar(Static):
    """The `>` input between two horizontal rules."""

    DEFAULT_CSS = "PromptBar { height: 3; }"

    def __init__(self) -> None:
        super().__init__()
        self.buffer = ""
        self.placeholder = ""

    def set_buffer(self, text: str) -> None:
        self.buffer = text
        self.refresh()

    def render(self) -> RenderableType:
        width = max(self.size.width, 10)
        rule = Text("─" * width, style=NOISE)
        line = Text(" > ", style="bold")
        if self.buffer:
            line.append(self.buffer)
            line.append(" ", style="reverse")
        else:
            line.append(" ", style="reverse")
            if self.placeholder:
                line.append(self.placeholder, style=NOISE)
        return Group(rule, _line(line), rule)


class StatusBar(Static):
    DEFAULT_CSS = "StatusBar { height: 1; padding: 0 1; }"

    MODES = [
        ("⏵⏵ accept edits on", " (shift+tab to cycle)"),
        ("⏸ plan mode on", " (shift+tab to cycle)"),
        ("? for shortcuts", ""),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.mode = 0
        self.metrics = ""
        self.flash = ""

    def cycle(self) -> None:
        self.mode = (self.mode + 1) % len(self.MODES)
        self.refresh()

    def set_metrics(self, text: str) -> None:
        self.metrics = text
        self.refresh()

    def render(self) -> RenderableType:
        label, hint = self.MODES[self.mode]
        left = Text()
        left.append(label, style="dim" if self.mode == 2 else f"dim {CLAUDE_ORANGE}")
        left.append(hint, style=NOISE)
        if self.metrics:
            left.append(f" · {self.metrics}", style=NOISE)
        if self.flash:
            left.append(f" · {self.flash}", style=NOISE)
        return _line(left)


class InteractionPanel(Static):
    """Permission prompt / multiple-choice question / compact confirmation."""

    DEFAULT_CSS = "InteractionPanel { height: auto; margin-top: 1; padding: 0 1 0 1; }"

    def __init__(self, accent: str = CLAUDE_ORANGE) -> None:
        super().__init__()
        self.accent = accent
        self.interaction: Interaction | None = None
        self.selected = 0
        self.display = False

    def show(self, interaction: Interaction) -> None:
        self.interaction = interaction
        self.selected = 0
        self.display = True
        self.refresh(layout=True)

    def hide(self) -> None:
        self.interaction = None
        self.display = False

    def move(self, delta: int) -> None:
        if self.interaction:
            self.selected = (self.selected + delta) % len(self.interaction.options)
            self.refresh()

    def _options(self) -> list[Text]:
        it = self.interaction
        out: list[Text] = []
        for i, option in enumerate(it.options):
            chosen = i == self.selected
            line = Text()
            line.append("❯ " if chosen else "  ", style=self.accent)
            line.append(f"{i + 1}. {option}", style=self.accent if chosen else "")
            out.append(line)
            if it.descriptions and i < len(it.descriptions):
                out.append(Text(f"     {it.descriptions[i]}", style=NOISE))
        return out

    def render(self) -> RenderableType:
        it = self.interaction
        if it is None:
            return Text("")
        if it.kind == PERMISSION:
            preview: list[Text] = []
            call = it.call
            if call is not None and call.name == "Update":
                preview.append(Text(call.arg, style="bold"))
                for raw in call.body[:14]:
                    style = "green" if raw[5:6] == "+" else "red" if raw[5:6] == "-" else NOISE
                    preview.append(_line(Text(raw, style=style)))
            elif call is not None:
                preview.append(Text(f"  {call.arg}"))
                preview.append(Text("  Run the test suite", style=NOISE))
            inner = Panel(Group(*preview), border_style="dim", padding=(0, 1))
            body = Group(Text(it.title, style=f"bold {self.accent}"), inner,
                         Text(it.question), *self._options())
            return Panel(body, border_style=self.accent, padding=(0, 1))
        if it.kind == CHOICE:
            head = Text()
            head.append("☐ ", style=NOISE)
            head.append(it.title, style="bold")
            hint = Text("Enter to select · ↑/↓ to navigate · Esc to cancel", style=NOISE)
            return Group(head, Text(""), Text(it.question, style="bold"), *self._options(),
                         Text(""), hint)
        if it.kind == COMPACT:
            head = Text(f"⚠ {it.title}", style="yellow")
            return Panel(Group(head, Text(it.question), *self._options()),
                         border_style="dim", padding=(0, 1))
        return Text("")
