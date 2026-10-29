import random

from ccreader.app import ReaderApp
from ccreader.config import Config
from ccreader.state import Store
from ccreader.widgets import NovelBlock, StatusBar, WelcomeBox


def make_app(sample_txt, **cfg):
    store = Store()
    book = store.open_book(sample_txt)
    config = Config(**{"wpm": 2000, "stream_mode": "instant", **cfg}).normalized()
    return ReaderApp(book, store, config, start=(1, 0), rng=random.Random(5))


async def advance(pilot, n=20):
    for _ in range(n):
        await pilot.press("space")
        await pilot.pause(0.05)


async def test_main_screen_shows_novel_and_saves_bookmark(sample_txt):
    app = make_app(sample_txt)
    async with app.run_test(size=(100, 40)) as pilot:
        await advance(pilot)
        screen = app.main
        assert screen.query(WelcomeBox)
        blocks = list(screen.query(NovelBlock))
        assert blocks and blocks[0].text.startswith("Chương 1")
        assert "ch.2" in screen.query_one(StatusBar).metrics
        mark = Store().get_bookmark(app.book.book_id)
        assert mark is not None and mark[0] == 1 and mark[1] > 0


async def test_transcript_toggle(sample_txt):
    app = make_app(sample_txt)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("ctrl+o")
        await pilot.pause(0.1)
        assert type(app.screen).__name__ == "TranscriptScreen"
        await pilot.press("q")
        await pilot.pause(0.1)
        assert app.screen is app.main


async def test_stream_mode_reveals_progressively_and_space_finishes(sample_txt):
    app = make_app(sample_txt, stream_mode="stream", wpm=300)
    async with app.run_test(size=(100, 40)) as pilot:
        screen = app.main
        partial = None
        for _ in range(200):
            await pilot.pause(0.05)
            blocks = [b for b in screen.query(NovelBlock) if not b.title]
            if blocks and 0 < blocks[-1].revealed < len(blocks[-1].text):
                partial = blocks[-1]
                break
            if not screen.busy:
                break
            # skip thinking / tool waits, but not the stream itself
            if not blocks:
                screen._skip.set()
        assert partial is not None
        await pilot.press("space")
        await pilot.pause(0.1)
        assert partial.fully_revealed


async def test_wpm_keys(sample_txt):
    app = make_app(sample_txt, wpm=250)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("plus", "plus", "minus")
        assert app.wpm == 275


async def test_interactions_block_until_answered(sample_txt):
    from ccreader.widgets import InteractionPanel

    clock = [0.0]
    store = Store()
    book = store.open_book(sample_txt)
    app = ReaderApp(book, store, Config(wpm=2000, stream_mode="instant").normalized(),
                    start=(1, 0), rng=random.Random(2), clock=lambda: clock[0])
    async with app.run_test(size=(100, 40)) as pilot:
        clock[0] = 10**6
        panel = app.main.query_one(InteractionPanel)
        for _ in range(60):
            await pilot.pause(0.05)
            if panel.interaction or app.main.typeout:
                break
            await pilot.press("space")
        assert panel.interaction or app.main.typeout
        mark = app.position
        await pilot.pause(0.5)
        assert app.position == mark  # nothing advances while waiting
        if panel.interaction:
            await pilot.press("1")
        else:
            await pilot.press("x", "enter")
        await pilot.pause(0.1)
        assert panel.interaction is None and app.main.typeout is None


def visible_novel(screen):
    return [b for b in screen.query(NovelBlock) if not b.collapsed and b.display]


async def test_boss_key_collapses_pushes_and_resumes(sample_txt):
    from ccreader.widgets import InteractionPanel

    app = make_app(sample_txt)
    async with app.run_test(size=(100, 40)) as pilot:
        await advance(pilot, 10)
        screen = app.main
        assert visible_novel(screen)
        await pilot.press("escape", "escape")
        await pilot.pause(0.05)
        assert screen.bossed
        assert not visible_novel(screen)  # collapsed immediately
        panel = screen.query_one(InteractionPanel)
        for _ in range(60):
            await pilot.pause(0.05)
            if panel.interaction:
                break
        assert panel.interaction is not None  # ends on a permission prompt
        assert panel.interaction.kind == "permission"
        log = screen.log_view
        assert log.max_scroll_y > 0 and log.scroll_y == log.max_scroll_y
        # typing "continue" resumes
        await pilot.press("escape")
        await pilot.pause(0.6)  # single Esc answers "No"
        await pilot.press(*"continue", "enter")
        await pilot.pause(0.1)
        assert not screen.bossed
        await advance(pilot, 10)
        assert visible_novel(screen)
        # Esc Esc again from the transcript view
        await pilot.press("ctrl+o")
        await pilot.pause(0.1)
        await pilot.press("escape", "escape")
        await pilot.pause(0.1)
        assert app.screen is screen and screen.bossed
        await pilot.press("escape", "escape")
        await pilot.pause(0.1)
        assert not screen.bossed


async def test_ctrl_backslash_quits(sample_txt):
    app = make_app(sample_txt)
    calls = []
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("ctrl+o")
        original = app.exit
        app.exit = lambda *a, **k: (calls.append(1), original(*a, **k))
        await pilot.press("ctrl+backslash")
        await pilot.pause(0.1)
    assert calls


async def test_focus_loss_triggers_boss(sample_txt):
    from textual import events

    app = make_app(sample_txt)
    async with app.run_test(size=(100, 40)) as pilot:
        await advance(pilot, 3)
        app.post_message(events.AppBlur())
        await pilot.pause(0.1)
        assert app.main.bossed
