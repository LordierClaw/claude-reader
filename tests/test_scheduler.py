import random
from collections import Counter

from ccreader.noise import builtin_corpus
from ccreader.scheduler import (
    CHOICE,
    COMPACT,
    KINDS,
    PERMISSION,
    TYPEOUT,
    InteractionScheduler,
    TypeOut,
    build_interaction,
)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_due_within_configured_window():
    for seed in range(50):
        clock = Clock()
        s = InteractionScheduler(5, 10, random.Random(seed), clock=clock)
        assert 300 <= s.seconds_left() <= 600
        clock.t += 299
        assert not s.due()
        clock.t += 301
        assert s.due()
        s.reset()
        assert not s.due()
        assert 300 <= s.seconds_left() <= 600


def test_postpone():
    clock = Clock()
    s = InteractionScheduler(1, 1, random.Random(0), clock=clock)
    clock.t += 61
    assert s.due()
    s.postpone(30)
    assert not s.due() and s.seconds_left() == 30


def test_pick_kind_variety_and_compact_is_rare():
    s = InteractionScheduler(5, 10, random.Random(3), clock=Clock())
    kinds = [s.pick_kind() for _ in range(400)]
    assert set(kinds) == set(KINDS)
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    counts = Counter(kinds)
    assert counts[COMPACT] < counts[PERMISSION]
    # compact never comes within 3 picks of the previous compact
    idx = [i for i, k in enumerate(kinds) if k == COMPACT]
    assert all(b - a > 3 for a, b in zip(idx, idx[1:]))


def test_pick_kind_respects_allowed():
    s = InteractionScheduler(5, 10, random.Random(1), clock=Clock())
    for _ in range(50):
        assert s.pick_kind((PERMISSION, CHOICE)) in (PERMISSION, CHOICE)


def test_build_interactions_use_corpus_names():
    c = builtin_corpus()
    rng = random.Random(7)
    names = set(c.classes) | set(c.functions) | set(c.tests)
    for _ in range(30):
        perm = build_interaction(PERMISSION, c, rng)
        assert perm.call is not None and perm.cancel_index == 2 and len(perm.options) == 3
        choice = build_interaction(CHOICE, c, rng)
        assert len(choice.options) == len(choice.descriptions) >= 2
        assert any(n in choice.question or any(n in o for o in choice.options) for n in names)
        typeout = build_interaction(TYPEOUT, c, rng)
        assert typeout.canned and "{" not in typeout.canned
    compact = build_interaction(COMPACT, c, rng)
    assert compact.options[0].startswith("Yes") and compact.cancel_index == 1


def test_typeout_one_char_per_key():
    t = TypeOut("hello world")
    assert t.key() == "h"
    assert t.key() == "he"
    assert t.backspace() == "h"
    for _ in range(50):
        t.key()
    assert t.complete and t.text == "hello world"
    assert TypeOut("abc").finish() == "abc"
