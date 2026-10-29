import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SAMPLES = ROOT / "samples"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("CCREADER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("CCREADER_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path


@pytest.fixture
def sample_txt() -> Path:
    return SAMPLES / "ngon-hai-dang.txt"
