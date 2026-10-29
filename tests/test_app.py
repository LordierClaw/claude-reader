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
