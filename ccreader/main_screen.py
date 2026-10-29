"""The main view: a fake agent session that streams the novel."""

from __future__ import annotations

import asyncio
import random
from time import monotonic

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ccreader.fakes import ToolCall
from ccreader.screens import BaseScreen
from ccreader.turns import AgentText, Novel, Pause, Thinking
from ccreader.widgets import (
    NoteLine,
    NovelBlock,
    PromptBar,
    Spinner,
    StatusBar,
    ToolBlock,
    WelcomeBox,
    agent_text,
    collapse_group,
    user_text,
)

VERBS = ["Thinking", "Pondering", "Cogitating", "Brewing", "Percolating", "Mulling",
         "Noodling", "Crafting", "Reticulating", "Synthesizing", "Considering"]
CONTINUE_MESSAGES = ["continue", "ok, go on", "looks good, continue", "yes, keep going",
                     "go ahead", "sounds right, continue", "next"]
MAX_LOG_WIDGETS = 500


class MainScreen(BaseScreen):
    DEFAULT_CSS = """
    MainScreen { background: ansi_default; }
    #log { height: 1fr; scrollbar-size-vertical: 1; }
    #interaction { height: auto; display: none; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.rng = random.Random()
        self.turn_no = 0
        self.busy = False
        self.turn_started = 0.0
        self.turn_tokens = 0
        self.current_block: NovelBlock | None = None
        self._skip = asyncio.Event()
        self._submit: asyncio.Future[str] | None = None
        self._ctrl_c = 0.0

    # -- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        log = VerticalScroll(id="log")
        log.can_focus = False
        yield log
        yield Spinner()
        yield Static(id="interaction")
        yield PromptBar()
        yield StatusBar()

    @property
    def log_view(self) -> VerticalScroll:
        return self.query_one("#log", VerticalScroll)

    async def on_mount(self) -> None:
        await self.log_view.mount(WelcomeBox(self.app.corpus.root))
        self.log_view.anchor()
        self.set_interval(1 / 8, self._tick)
        self.update_status()
        self.start_player()

    def start_player(self, resumed: bool = False) -> None:
        self.run_worker(self.player(resumed), group="player", exclusive=True)

    def _tick(self) -> None:
        spinner = self.query_one(Spinner)
        if spinner.active:
            spinner.frame += 1
            spinner.seconds = monotonic() - self.turn_started
            spinner.tokens = self.turn_tokens
            spinner.refresh()

    def update_status(self) -> None:
        app = self.app
        chapter, para = app.position
        pct = int(app.book.chapter_progress(chapter, para) * 100)
        tokens = app.tokens
        tok = f"{tokens / 1000:.0f}k" if tokens >= 1000 else str(tokens)
        self.query_one(StatusBar).set_metrics(f"ch.{chapter + 1} {pct}% · {tok} tokens")

    def add_tokens(self, n: int) -> None:
        self.turn_tokens += n
        self.app.tokens += n
        self.update_status()

    async def append(self, *widgets) -> None:
        log = self.log_view
        await log.mount_all(widgets)
        children = list(log.children)
        if len(children) > MAX_LOG_WIDGETS:
            await log.remove_children(children[1: len(children) - MAX_LOG_WIDGETS + 100])

    def collapse_novel(self, before_turn: int | None = None) -> None:
        """Collapse novel blocks (runs of consecutive blocks become one line)."""
        runs: list[list[NovelBlock]] = []
        run: list[NovelBlock] = []
        for child in self.log_view.children:
            if (isinstance(child, NovelBlock) and not child.collapsed
                    and (before_turn is None or child.turn < before_turn)):
                run.append(child)
            elif not (isinstance(child, NovelBlock) and child.collapsed and not child.display):
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)
        for run in runs:
            collapse_group(run)
        if self.current_block is not None and self.current_block.collapsed:
            self.current_block = None

    # -- the agent ---------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        spinner = self.query_one(Spinner)
        spinner.active = busy
        if busy:
            self.turn_started = monotonic()
            self.turn_tokens = 0
            spinner.verb = self.rng.choice(VERBS)
        spinner.refresh()

    async def wait(self, seconds: float) -> None:
        """Sleep, unless Space cuts it short."""
        self._skip.clear()
        try:
            await asyncio.wait_for(self._skip.wait(), timeout=max(0.0, seconds))
        except asyncio.TimeoutError:
            pass

    async def player(self, resumed: bool = False) -> None:
        app = self.app
        while True:
            turn = app.builder.build(app.position, resumed=resumed)
            resumed = False
            self.turn_no += 1
            if app.config.collapse_previous_turns:
                self.collapse_novel(before_turn=self.turn_no)
            self.set_busy(True)
            try:
                for event in turn.events:
                    await self.play(event)
            finally:
                if self.is_attached:
                    self.set_busy(False)
            if turn.end is None:
                await self.append(NoteLine(agent_text("All tasks are complete.")))
                await asyncio.Event().wait()
            app.set_position(turn.end)
            await self.wait_for_user()

    async def play(self, event) -> None:
        app = self.app
        if isinstance(event, Thinking):
            self.query_one(Spinner).verb = "Thinking"
            await self.wait(event.seconds)
            self.query_one(Spinner).verb = self.rng.choice(VERBS)
        elif isinstance(event, AgentText):
            await self.append(NoteLine(agent_text(event.text)))
            self.add_tokens(len(event.text) // 3 + 20)
            await self.wait(self.rng.uniform(0.3, 0.9))
        elif isinstance(event, ToolCall):
            block = ToolBlock(event, done=False)
            await self.append(block)
            await self.wait(self.rng.uniform(0.3, 1.3))
            block.finish()
            self.add_tokens(event.tokens)
        elif isinstance(event, Novel):
            await self.play_novel(event)
        elif isinstance(event, Pause):
            await self.wait(event.seconds)

    async def play_novel(self, event: Novel) -> None:
        app = self.app
        if not event.title:
            app.set_position((event.chapter, event.para))
        block = NovelBlock(event.text, chapter=event.chapter, para=event.para,
                           turn=self.turn_no, bullet=event.bullet, title=event.title,
                           max_width=app.config.max_width)
        if self.current_block is not None:
            self.current_block.set_current(False)
        self.current_block = block
        block.set_current(not event.title)
        await self.append(block)
        await self.show_text(block)
        self.add_tokens(int(len(event.text) / 3.5))

    async def show_text(self, block: NovelBlock) -> None:
        block.reveal(len(block.text))
        words = len(block.text.split())
        await self.wait(words / self.app.wpm * 60 if not block.title else 0.6)

    # -- user input --------------------------------------------------------

    async def wait_for_user(self) -> str:
        loop = asyncio.get_running_loop()
        self._submit = loop.create_future()
        try:
            return await self._submit
        finally:
            self._submit = None

    async def submit(self) -> None:
        prompt = self.query_one(PromptBar)
        text = prompt.buffer.strip()
        prompt.set_buffer("")
        if text.startswith("/"):
            await self.slash_command(text)
            return
        if self._submit is not None and not self._submit.done():
            await self.append(NoteLine(user_text(text or self.rng.choice(CONTINUE_MESSAGES))))
            self._submit.set_result(text)
        elif text:
            await self.append(NoteLine(user_text(text)))

    async def slash_command(self, text: str) -> None:
        cmd = text.split()[0].lower()
        await self.append(NoteLine(user_text(text)))
        if cmd in ("/exit", "/quit"):
            self.app.exit()
        elif cmd == "/clear":
            log = self.log_view
            await log.remove_children(list(log.children)[1:])
        else:
            await self.append(NoteLine(Text(f"  ⎿  Unknown command: {cmd}", style="dim")))

    async def handle_key(self, event: events.Key) -> None:
        key, char = event.key, event.character
        prompt = self.query_one(PromptBar)
        if key == "ctrl+o":
            self.app.open_transcript()
        elif key == "shift+tab":
            self.query_one(StatusBar).cycle()
        elif key == "ctrl+c":
            now = monotonic()
            if not prompt.buffer and now - self._ctrl_c < 1.0:
                self.app.exit()
            self._ctrl_c = now
            prompt.set_buffer("")
        elif key == "pageup":
            self.log_view.scroll_page_up(animate=False)
        elif key == "pagedown":
            self.log_view.scroll_page_down(animate=False)
        elif key == "enter":
            await self.submit()
        elif key == "backspace":
            prompt.set_buffer(prompt.buffer[:-1])
        elif char and char.isprintable():
            if not prompt.buffer and self.on_control_char(char):
                return
            prompt.set_buffer(prompt.buffer + char)

    def on_control_char(self, char: str) -> bool:
        """Single-key controls, active while the prompt is empty."""
        if char == " ":
            if self.busy:
                self._skip.set()
                return True
            if self._submit is not None:
                self.run_worker(self.submit())
                return True
        return False
