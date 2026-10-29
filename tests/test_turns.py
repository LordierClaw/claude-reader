import random

from ccreader.book import load_book
from ccreader.fakes import ToolCall, suite_output, update_call
from ccreader.noise import builtin_corpus
from ccreader.turns import AgentText, Novel, Pause, Thinking, TurnBuilder


def _builder(sample_txt, seed=0, ppt=(3, 6)):
    book = load_book(sample_txt)
    return book, TurnBuilder(book, builtin_corpus(), random.Random(seed), ppt)


def test_turn_structure(sample_txt):
    book, builder = _builder(sample_txt)
    for seed in range(40):
        builder.rng.seed(seed)
        turn = builder.build((1, 0))
        ev = turn.events
        assert isinstance(ev[0], Thinking)
        first_novel = next(i for i, e in enumerate(ev) if isinstance(e, Novel))
        tools_before = [e for e in ev[:first_novel] if isinstance(e, ToolCall)]
        assert 1 <= len(tools_before) <= 2
        assert all(isinstance(e, (Thinking, AgentText, ToolCall)) for e in ev[:first_novel])
        assert 1 <= len(turn.novel) <= 6
        # between novel paragraphs: at most 2 short tool calls, never long blocks
        last_novel = max(i for i, e in enumerate(ev) if isinstance(e, Novel))
        run = 0
        for e in ev[first_novel:last_novel]:
            if isinstance(e, ToolCall):
                run += 1
                assert e.name in ("Read", "Search", "List", "Bash")
                assert len(e.body) <= 3 and not e.hidden
                assert run <= 2
            else:
                run = 0
                assert isinstance(e, (Novel, Pause))
        # trailing long noise only after the last paragraph
        assert all(isinstance(e, ToolCall) for e in ev[last_novel + 1:])


def test_turn_positions_are_consecutive(sample_txt):
    book, builder = _builder(sample_txt, ppt=(3, 3))
    pos = (1, 0)
    seen = []
    while pos is not None:
        turn = builder.build(pos)
        seen += [(n.chapter, n.para) for n in turn.novel]
        pos = turn.end
    expected = [(c, p) for c in range(1, len(book.chapters))
                for p in range(len(book.chapters[c].paragraphs))]
    assert seen == expected


def test_chapter_title_starts_chapter(sample_txt):
    book, builder = _builder(sample_txt)
    turn = builder.build((2, 0))
    titles = [e for e in turn.events if isinstance(e, Novel) and e.title]
    assert titles and titles[0].text == book.chapters[2].title


def test_update_call_counts():
    hunk = {"path": "a.py", "start": 5, "lines": [" x", "-y", "+z", "+w"]}
    call = update_call(builtin_corpus(), random.Random(0), hunk)
    assert call.summary == "Updated a.py with 2 additions and 1 removal"
    assert call.body[1].strip().startswith("6 -")


def test_test_output_kinds():
    c = builtin_corpus()
    out = suite_output(c, random.Random(1))
    assert out[-2] == "[INFO] BUILD SUCCESS"
    c.kind = "python"
    assert "passed" in suite_output(c, random.Random(1))[-1]
