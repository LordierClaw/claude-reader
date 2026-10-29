"""When to block for user interaction, and what the interaction looks like."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable

from ccreader import fakes
from ccreader.noise import NoiseCorpus

PERMISSION, CHOICE, TYPEOUT, COMPACT = "permission", "choice", "typeout", "compact"
KINDS = (PERMISSION, CHOICE, TYPEOUT, COMPACT)
WEIGHTS = {PERMISSION: 0.35, CHOICE: 0.25, TYPEOUT: 0.30, COMPACT: 0.10}


class InteractionScheduler:
    """Fires every `min..max` minutes (random jitter), using an injectable clock."""

    def __init__(self, min_minutes: float, max_minutes: float,
                 rng: random.Random | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.min_s = min_minutes * 60
        self.max_s = max(max_minutes * 60, self.min_s)
        self.rng = rng or random.Random()
        self.clock = clock
        self.last_kind: str | None = None
        self.since_compact = 0
        self.next_due = self.clock() + self.interval()

    def interval(self) -> float:
        return self.rng.uniform(self.min_s, self.max_s)

    def due(self) -> bool:
        return self.clock() >= self.next_due

    def seconds_left(self) -> float:
        return max(0.0, self.next_due - self.clock())

    def reset(self) -> None:
        self.next_due = self.clock() + self.interval()

    def postpone(self, seconds: float) -> None:
        self.next_due = max(self.next_due, self.clock() + seconds)

    def pick_kind(self, allowed: tuple[str, ...] = KINDS) -> str:
        kinds = [k for k in allowed if k != self.last_kind] or list(allowed)
        if self.since_compact < 3:
            kinds = [k for k in kinds if k != COMPACT] or kinds
        kind = self.rng.choices(kinds, weights=[WEIGHTS[k] for k in kinds])[0]
        self.last_kind = kind
        self.since_compact = 0 if kind == COMPACT else self.since_compact + 1
        return kind


@dataclass
class Interaction:
    kind: str
    title: str = ""
    question: str = ""
    options: list[str] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    cancel_index: int | None = None  # chosen by a single Esc
    call: fakes.ToolCall | None = None  # the tool call a permission prompt is about
    canned: str = ""  # text "typed" by a type-out prompt


_QUESTIONS = [
    ("Retry strategy", "How should {cls} handle a gateway timeout?",
     [("Exponential backoff with jitter", "Retry up to the configured limit, spreading load."),
      ("Fixed delay, capped attempts", "Simpler, predictable timing."),
      ("Fail fast and enqueue", "Hand off to the outbox and let the worker retry.")]),
    ("Placement", "Where should the validation for {fn} live?",
     [("Inside {cls}", "Keeps the logic next to its only caller."),
      ("A new validator class", "Reusable and easier to test in isolation."),
      ("At the API boundary", "Reject bad input before it reaches the service.")]),
    ("Compatibility", "Should I keep the old signature of {fn} for existing callers?",
     [("Yes, add a deprecated overload", "No call sites need to change now."),
      ("No, update all call sites", "Cleaner, touches more files."),
      ("Keep it for one release", "Deprecate now, remove in the next version.")]),
    ("Slow test", "{test} takes 8.4s. How do you want to proceed?",
     [("Mock the clock", "Removes the real sleeps."),
      ("Split the test", "Smaller tests, same coverage."),
      ("Leave it for now", "Note it as a follow-up.")]),
    ("Error handling", "What should {cls} do when the response can't be parsed?",
     [("Throw a typed exception", "Callers decide how to recover."),
      ("Return an empty result and log", "Keeps the batch going."),
      ("Retry once, then throw", "Covers transient truncation.")]),
]

_PROMPTS = [
    "can you also add a test in {test} for the empty batch case?",
    "looks good. one thing: {fn} should log at debug, not info",
    "wait, does this change how {cls} behaves when the config is missing?",
    "ok, now run the full test suite and fix anything that breaks",
    "let's rename {fn} to something clearer",
    "can you double check {path} for the same issue?",
    "make sure {cls} is still thread safe after this change",
    "nice. can you also update the javadoc on {fn}?",
    "hmm, I'd rather not touch {cls} in this PR, can you revert that part?",
]


def _names(c: NoiseCorpus, rng: random.Random) -> dict[str, str]:
    return {
        "cls": rng.choice(c.classes),
        "fn": rng.choice(c.functions or c.classes),
        "test": rng.choice(c.tests or c.classes),
        "path": fakes.short_path(rng.choice(c.paths)),
    }


def build_interaction(kind: str, c: NoiseCorpus, rng: random.Random) -> Interaction:
    names = _names(c, rng)
    if kind == PERMISSION:
        if rng.random() < 0.7:
            call = fakes.update_call(c, rng)
            return Interaction(
                kind, title="Edit file",
                question=f"Do you want to make this edit to {fakes.short_path(call.arg, 1)}?",
                options=["Yes", "Yes, allow all edits during this session (shift+tab)",
                         "No, and tell Claude what to do differently (esc)"],
                cancel_index=2, call=call)
        cmd = fakes.suite_command(c)
        call = fakes.suite_call(c, rng)
        return Interaction(
            kind, title="Bash command", question="Do you want to proceed?",
            options=["Yes", f"Yes, and don't ask again for {cmd.split()[0]} commands",
                     "No, and tell Claude what to do differently (esc)"],
            cancel_index=2, call=call)
    if kind == CHOICE:
        title, q, opts = rng.choice(_QUESTIONS)
        return Interaction(
            kind, title=title, question=q.format(**names),
            options=[o.format(**names) for o, _ in opts],
            descriptions=[d.format(**names) for _, d in opts], cancel_index=None)
    if kind == COMPACT:
        left = rng.randint(3, 12)
        return Interaction(
            kind, title=f"Context left until auto-compact: {left}%",
            question="Compact the conversation now?",
            options=["Yes, run /compact", "Not now"], cancel_index=1)
    return Interaction(TYPEOUT, canned=rng.choice(_PROMPTS).format(**names))


class TypeOut:
    """Maps the user's keystrokes onto a canned prompt, one character per key."""

    def __init__(self, canned: str) -> None:
        self.canned = canned
        self.shown = 0

    @property
    def text(self) -> str:
        return self.canned[: self.shown]

    @property
    def complete(self) -> bool:
        return self.shown >= len(self.canned)

    def key(self) -> str:
        if not self.complete:
            self.shown += 1
        return self.text

    def backspace(self) -> str:
        self.shown = max(0, self.shown - 1)
        return self.text

    def finish(self) -> str:
        self.shown = len(self.canned)
        return self.canned
