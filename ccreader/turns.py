"""Building "agent turns": novel paragraphs interleaved with light noise."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ccreader import fakes
from ccreader.book import Book
from ccreader.fakes import ToolCall
from ccreader.noise import NoiseCorpus


@dataclass
class Thinking:
    seconds: float


@dataclass
class AgentText:
    """A short (dim) assistant remark, e.g. "Let me check ..."."""
    text: str


@dataclass
class Novel:
    chapter: int
    para: int
    text: str
    title: bool = False  # a chapter heading
    bullet: bool = True  # first paragraph after noise starts with "●"


@dataclass
class Pause:
    seconds: float


Event = Thinking | AgentText | ToolCall | Novel | Pause


@dataclass
class Turn:
    events: list[Event] = field(default_factory=list)
    start: tuple[int, int] = (0, 0)
    end: tuple[int, int] | None = None  # position after the turn, None at end of book

    @property
    def novel(self) -> list[Novel]:
        return [e for e in self.events if isinstance(e, Novel) and not e.title]


class TurnBuilder:
    def __init__(self, book: Book, corpus: NoiseCorpus, rng: random.Random | None = None,
                 paragraphs_per_turn: tuple[int, int] = (3, 6)) -> None:
        self.book = book
        self.corpus = corpus
        self.rng = rng or random.Random()
        self.ppt = paragraphs_per_turn

    def build(self, pos: tuple[int, int], *, resumed: bool = False) -> Turn:
        rng, c = self.rng, self.corpus
        turn = Turn(start=pos)
        ev = turn.events
        ev.append(Thinking(round(rng.uniform(1.0, 6.0), 1)))
        if resumed:
            ev.append(AgentText("Picking up where I left off."))
        elif rng.random() < 0.6:
            ev.append(AgentText(fakes.agent_line(c, rng)))
        for _ in range(rng.randint(1, 2)):
            ev.append(fakes.light_call(c, rng))

        count = rng.randint(*self.ppt)
        chapter, para = pos
        bullet = True
        cur: tuple[int, int] | None = pos
        for i in range(count):
            if cur is None:
                break
            chapter, para = cur
            if para == 0:
                ev.append(Novel(chapter, para, self.book.chapters[chapter].title,
                                title=True, bullet=bullet))
                bullet = False
            ev.append(Novel(chapter, para, self.book.chapters[chapter].paragraphs[para],
                            bullet=bullet))
            bullet = False
            cur = self.book.next_pos(chapter, para)
            if cur is None or i == count - 1:
                break
            if cur[0] != chapter:
                # a new chapter starts: end the turn here, it reads more naturally
                break
            r = rng.random()
            if r < 0.30:
                ev.append(fakes.light_call(c, rng))
                bullet = True
            elif r < 0.40:
                ev.append(fakes.light_call(c, rng))
                ev.append(fakes.light_call(c, rng))
                bullet = True
            else:
                ev.append(Pause(round(rng.uniform(0.2, 0.8), 2)))
        turn.end = cur

        r = rng.random()
        if r < 0.45:
            ev.append(fakes.update_call(c, rng))
        elif r < 0.60:
            ev.append(fakes.suite_call(c, rng))
        return turn
