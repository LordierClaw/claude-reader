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
