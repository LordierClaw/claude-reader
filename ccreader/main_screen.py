"""The main view: a fake agent session that streams the novel."""

from __future__ import annotations

import asyncio
import random
import re
from time import monotonic

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll

from ccreader.fakes import ToolCall
from ccreader.render import hanging
from ccreader.scheduler import (
    CHOICE,
    COMPACT,
    PERMISSION,
    TYPEOUT,
    Interaction,
    TypeOut,
    build_interaction,
)
from ccreader.screens import BaseScreen
from ccreader.turns import AgentText, Novel, Pause, Thinking
from ccreader.widgets import (
    InteractionPanel,
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
WPM_STEP = 25
_WORD_RE = re.compile(r"\S+\s*")


class MainScreen(BaseScreen):
    DEFAULT_CSS = """
    MainScreen { background: ansi_default; }
    #log { height: 1fr; scrollbar-size-vertical: 1; }
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
        self._answer: asyncio.Future[int] | None = None
        self.typeout: TypeOut | None = None
        self._ctrl_c = 0.0

    # -- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        log = VerticalScroll(id="log")
        log.can_focus = False
        yield log
        yield Spinner()
        yield InteractionPanel()
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
        if busy:
            self.turn_started = monotonic()
            self.turn_tokens = 0
            spinner.verb = self.rng.choice(VERBS)
        spinner.set_active(busy)

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
            if app.scheduler.due():
                await self.interact(TYPEOUT, CHOICE, COMPACT, PERMISSION)
            else:
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
            if app.scheduler.due():
                await self.interact(PERMISSION, CHOICE, COMPACT)
            app.set_position((event.chapter, event.para))
        block = NovelBlock(event.text, chapter=event.chapter, para=event.para,
                           turn=self.turn_no, bullet=event.bullet, title=event.title,
                           max_width=app.config.max_width)
        if self.current_block is not None:
            self.current_block.set_current(False)
        self.current_block = block
        block.set_current(not event.title)
        if not event.title and app.stream_mode == "stream":
            block.revealed = 0
        await self.append(block)
        await self.show_text(block)

    async def show_text(self, block: NovelBlock) -> None:
        if block.title:
            block.reveal(len(block.text))
            await self.wait(0.6)
            return
        if self.app.stream_mode == "instant":
            block.reveal(len(block.text))
            self.add_tokens(int(len(block.text) / 3.5))
            words = len(block.text.split())
            await self.wait(words / self.app.wpm * 60)
            return
        await self.stream(block)
        await self.wait(self.rng.uniform(0.4, 1.0))

    async def stream(self, block: NovelBlock) -> None:
        """Reveal the paragraph word by word at the reading speed (Space finishes it)."""
        words = list(_WORD_RE.finditer(block.text))
        block.reveal(0)
        self._skip.clear()
        shown = 0
        budget = 0.0
        last = monotonic()
        rate = 1.0
        while shown < len(words) and not self._skip.is_set():
            await asyncio.sleep(1 / 30)
            now = monotonic()
            budget += (now - last) * self.app.wpm / 60 * rate
            last = now
            n = int(budget)
            if not n:
                continue
            budget -= n
            start = words[shown].start()
            shown = min(len(words), shown + n)
            end = words[shown - 1].end()
            block.reveal(end)
            self.add_tokens(max(1, int((end - start) / 3.5)))
            rate = self.rng.uniform(0.75, 1.3)
            if block.text[:end].rstrip()[-1:] in ".!?…" and self.rng.random() < 0.25:
                await self.wait(self.rng.uniform(0.15, 0.5))
                last = monotonic()
        if block.revealed < len(block.text):
            self.add_tokens(int((len(block.text) - block.revealed) / 3.5))
        block.reveal(len(block.text))
        self._skip.clear()

    # -- interactions ------------------------------------------------------

    async def interact(self, *allowed: str) -> None:
        """Block on one interaction of an allowed kind, then reschedule."""
        app = self.app
        kind = app.scheduler.pick_kind(allowed)
        interaction = build_interaction(kind, app.corpus, self.rng)
        spinner = self.query_one(Spinner)
        was_active = spinner.active
        spinner.set_active(False)
        try:
            if kind == TYPEOUT:
                await self.run_typeout(interaction)
            elif kind == PERMISSION:
                await self.run_permission(interaction)
            elif kind == CHOICE:
                index = await self.ask(interaction)
                answer = f"· {interaction.question} → {interaction.options[index]}"
                await self.append(NoteLine(agent_text("User answered Claude's questions:")),
                                  NoteLine(hanging(Text("   ⎿  ", style="dim"),
                                                   Text(answer, style="dim")), margin=False))
            elif kind == COMPACT:
                if await self.ask(interaction) == 0:
                    await self.compact()
        finally:
            app.scheduler.reset()
            if self.is_attached:
                spinner.set_active(was_active)

    async def ask(self, interaction: Interaction) -> int:
        panel = self.query_one(InteractionPanel)
        prompt = self.query_one(PromptBar)
        self._answer = asyncio.get_running_loop().create_future()
        panel.show(interaction)
        prompt.display = False
        try:
            return await self._answer
        finally:
            self._answer = None
            if self.is_attached:
                panel.hide()
                prompt.display = True

    def answer(self, index: int) -> None:
        if self._answer is not None and not self._answer.done():
            self._answer.set_result(index)

    async def run_permission(self, interaction: Interaction) -> None:
        call = interaction.call
        block = ToolBlock(call, done=False)
        await self.append(block)
        if await self.ask(interaction) == interaction.cancel_index:
            what = "update to " + call.arg if call.name == "Update" else "bash command"
            block.reject(f"User rejected {what}")
            # "tell Claude what to do differently"
            await self.run_typeout(build_interaction(TYPEOUT, self.app.corpus, self.rng))
        else:
            block.finish()
            self.add_tokens(call.tokens)

    async def run_typeout(self, interaction: Interaction) -> None:
        self.typeout = TypeOut(interaction.canned)
        try:
            await self.wait_for_user()
        finally:
            self.typeout = None

    async def compact(self) -> None:
        spinner = self.query_one(Spinner)
        spinner.verb = "Compacting conversation"
        spinner.set_active(True)
        self.turn_started = monotonic()
        await asyncio.sleep(self.rng.uniform(1.5, 3.5))
        spinner.set_active(False)
        self.app.tokens = self.rng.randint(4_000, 9_000)
        self.update_status()
        await self.append(NoteLine(Text(" ✻ Conversation compacted (ctrl+o for history)",
                                        style="dim")))

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
        if self.typeout is not None:
            if not self.typeout.shown:
                return  # a typed-out prompt needs at least one keystroke
            text = self.typeout.finish()
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
        elif key == "ctrl+t":
            app = self.app
            app.stream_mode = "instant" if app.stream_mode == "stream" else "stream"
            self._skip.set()
            self.flash("output: " + app.stream_mode)
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
        elif self._answer is not None:
            self.interaction_key(key, char)
        elif self.typeout is not None and key == "backspace":
            prompt.set_buffer(self.typeout.backspace())
        elif self.typeout is not None and char and char.isprintable():
            if char == "/" and not self.typeout.shown:
                self.typeout = None  # typing a command: switch to literal input
                prompt.set_buffer("/")
            else:
                prompt.set_buffer(self.typeout.key())
        elif key == "enter":
            await self.submit()
        elif key == "backspace":
            prompt.set_buffer(prompt.buffer[:-1])
        elif char and char.isprintable():
            if not prompt.buffer and self.on_control_char(char):
                return
            prompt.set_buffer(prompt.buffer + char)

    def interaction_key(self, key: str, char: str | None) -> None:
        panel = self.query_one(InteractionPanel)
        if panel.interaction is None:
            return
        if key in ("up", "k"):
            panel.move(-1)
        elif key in ("down", "j", "tab"):
            panel.move(1)
        elif key == "enter":
            self.answer(panel.selected)
        elif char and char.isdigit() and 1 <= int(char) <= len(panel.interaction.options):
            self.answer(int(char) - 1)

    def on_single_escape(self) -> None:
        panel = self.query_one(InteractionPanel)
        if self._answer is not None and panel.interaction is not None:
            if panel.interaction.cancel_index is not None:
                self.answer(panel.interaction.cancel_index)
        else:
            self.query_one(PromptBar).set_buffer("")

    def on_control_char(self, char: str) -> bool:
        """Single-key controls, active while the prompt is empty."""
        if char == " ":
            if self.busy:
                self._skip.set()
                return True
            if self._submit is not None:
                self.run_worker(self.submit())
                return True
        if char in "+=-_":
            step = WPM_STEP if char in "+=" else -WPM_STEP
            self.app.wpm = max(60, min(2000, self.app.wpm + step))
            self.flash(f"{self.app.wpm}/min")
            return True
        return False

    def flash(self, text: str) -> None:
        """Briefly show a value in the status bar."""
        status = self.query_one(StatusBar)
        status.flash = text
        status.refresh()

        def clear() -> None:
            if status.flash == text:
                status.flash = ""
                status.refresh()

        self.set_timer(2.0, clear)
