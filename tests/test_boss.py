import random

from ccreader.boss import build_boss_sequence, line_count
from ccreader.fakes import ToolCall
from ccreader.noise import builtin_corpus
from ccreader.scheduler import PERMISSION


def test_boss_sequence_is_long_and_ends_on_permission():
    for seed in range(20):
        steps, prompt = build_boss_sequence(builtin_corpus(), random.Random(seed), min_lines=60)
        assert line_count(steps) >= 60
        names = [s.name for s in steps if isinstance(s, ToolCall)]
        assert names[0] == "Bash" and "Update" in names
        assert prompt.kind == PERMISSION
        tests = steps[1]
        assert tests.body[-2] == "[INFO] BUILD SUCCESS"
