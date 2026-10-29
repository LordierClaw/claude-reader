"""The boss-key "push" sequence: a burst of real-looking work output."""

from __future__ import annotations

import random

from ccreader import fakes
from ccreader.fakes import ToolCall
from ccreader.noise import NoiseCorpus
from ccreader.scheduler import PERMISSION, Interaction, build_interaction
from ccreader.turns import AgentText

BOSS_PROMPTS = [
    "run the full test suite again",
    "ok, check the build and show me the recent commits",
    "let's make sure everything still passes",
]


def build_boss_sequence(c: NoiseCorpus, rng: random.Random,
                        min_lines: int = 60) -> tuple[list[AgentText | ToolCall], Interaction]:
    """Steps that stream at least `min_lines` lines, then a permission prompt."""
    steps: list[AgentText | ToolCall] = [
        AgentText("Let me run the test suite to make sure nothing else broke."),
    ]
    out = fakes.suite_output(c, rng, count=min(len(c.tests), rng.randint(10, 16)))
    steps.append(ToolCall("Bash", fakes.suite_command(c), out[0], out[1:], tokens=1800))
    steps.append(AgentText("All green. Checking what has landed recently."))
    steps.append(fakes.gitlog_call(c, rng, n=15))
    hunks = rng.sample(c.diffs, k=min(len(c.diffs), 3))
    for hunk in hunks:
        steps.append(fakes.update_call(c, rng, hunk))
    while line_count(steps) < min_lines:
        steps.append(fakes.update_call(c, rng))
    steps.append(AgentText(f"Now I'll update {rng.choice(c.classes)} to match."))
    return steps, build_interaction(PERMISSION, c, rng)


def line_count(steps: list[AgentText | ToolCall]) -> int:
    n = 0
    for step in steps:
        n += 2 if isinstance(step, AgentText) else 3 + len(step.body)
    return n
