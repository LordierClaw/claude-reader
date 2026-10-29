"""Configuration loaded from ~/.config/ccreader/config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from ccreader.state import config_dir

DEFAULT_CONFIG = """\
# ccreader configuration
wpm = 250                      # reading speed in stream mode (+/- to adjust)
stream_mode = "stream"         # "stream" or "instant"
interaction_min_minutes = 5.0  # interaction prompts every min..max minutes
interaction_max_minutes = 10.0
paragraphs_per_turn = [3, 6]   # novel paragraphs per agent turn (int or [min, max])
max_width = 78                 # novel text column width
# repo = "~/code/payment-core"  # work repo used for the noise corpus
proc_title = "node"
theme = "dark"                 # "dark" or "light" (colors follow the terminal)
boss_on_blur = true            # run the boss sequence when the terminal loses focus
collapse_previous_turns = true # older novel blocks are shown collapsed
# chapter_regex = "^(Chương|Chapter)\\\\s+\\\\d+"
"""


@dataclass
class Config:
    wpm: int = 250
    stream_mode: str = "stream"
    interaction_min_minutes: float = 5.0
    interaction_max_minutes: float = 10.0
    paragraphs_per_turn: tuple[int, int] = (3, 6)
    max_width: int = 78
    repo: str | None = None
    proc_title: str = "node"
    theme: str = "dark"
    boss_on_blur: bool = True
    collapse_previous_turns: bool = True
    chapter_regex: str | None = None

    def normalized(self) -> "Config":
        """Clamp values into sane ranges."""
        self.wpm = max(60, min(int(self.wpm), 2000))
        if self.stream_mode not in ("stream", "instant"):
            self.stream_mode = "stream"
        ppt = self.paragraphs_per_turn
        if isinstance(ppt, int):
            ppt = (ppt, ppt)
        lo, hi = int(ppt[0]), int(ppt[-1])
        lo = max(1, lo)
        self.paragraphs_per_turn = (lo, max(lo, hi))
        self.interaction_min_minutes = max(0.1, float(self.interaction_min_minutes))
        self.interaction_max_minutes = max(self.interaction_min_minutes,
                                           float(self.interaction_max_minutes))
        self.max_width = max(40, min(int(self.max_width), 120))
        if self.theme not in ("dark", "light"):
            self.theme = "dark"
        return self


def config_path() -> Path:
    return config_dir() / "config.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    data: dict = {}
    if path.exists():
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    known = {f.name for f in fields(Config)}
    cfg = Config(**{k: v for k, v in data.items() if k in known})
    return cfg.normalized()


def write_default_config(path: Path | None = None) -> Path:
    path = path or config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return path
