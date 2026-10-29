import random

from ccreader.book import load_book
from ccreader.cli import main
from ccreader.config import Config, load_config, write_default_config
from ccreader.noise import builtin_corpus
from ccreader.sessions import build_sessions, humanize


def test_default_config_file_roundtrip(tmp_path):
    path = write_default_config(tmp_path / "config.toml")
    cfg = load_config(path)
    assert cfg == Config().normalized()


def test_config_values_and_clamping(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('wpm = 10\nstream_mode = "bogus"\nparagraphs_per_turn = 4\n'
                    'interaction_min_minutes = 9\ninteraction_max_minutes = 2\n'
                    'theme = "light"\nrepo = "~/x"\nunknown = 1\n')
    cfg = load_config(path)
    assert cfg.wpm == 60
    assert cfg.stream_mode == "stream"
    assert cfg.paragraphs_per_turn == (4, 4)
    assert cfg.interaction_max_minutes == 9
    assert cfg.theme == "light" and cfg.repo == "~/x"


def test_cli_list_chapters(sample_txt, capsys):
    assert main([str(sample_txt), "--list-chapters"]) == 0
    out = capsys.readouterr().out
    assert "Chương 4" in out
    # without a book argument the last book is reopened from the cache
    assert main(["--list-chapters"]) == 0
    assert "Chương 1" in capsys.readouterr().out


def test_cli_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.txt")]) == 1
    assert main([]) == 1
    assert "ccreader:" in capsys.readouterr().err


def test_cli_init_config(tmp_path, capsys):
    target = tmp_path / "cfg" / "config.toml"
    assert main(["--init-config", "--config", str(target)]) == 0
    assert target.exists()


def test_sessions_disguise_chapters(sample_txt):
    book = load_book(sample_txt)
    sessions = build_sessions(book, builtin_corpus(), current=2)
    assert len(sessions) == len(book.chapters)
    assert sessions[2].modified == "2m ago"
    assert sessions[3].summary.endswith("– ch.4")
    assert all(book.chapters[s.chapter].title not in s.summary for s in sessions)
    # stable across calls
    assert build_sessions(book, builtin_corpus(), current=2) == sessions
    assert humanize("PaymentRetryScheduler") == "payment retry scheduler"
