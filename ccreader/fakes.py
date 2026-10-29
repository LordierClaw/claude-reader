"""Generators for plausible tool calls, built from a noise corpus."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ccreader.noise import NoiseCorpus


@dataclass
class ToolCall:
    name: str
    arg: str
    summary: str = ""
    body: list[str] = field(default_factory=list)
    hidden: int = 0  # extra lines summarized as "… +N lines"
    tokens: int = 300


def short_path(path: str, keep: int = 3) -> str:
    parts = path.split("/")
    return "/".join(parts[-keep:]) if len(parts) > keep else path


def class_of(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _dir_of(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def pick_symbol(c: NoiseCorpus, rng: random.Random) -> str:
    pool = c.classes if rng.random() < 0.6 or not c.functions else c.functions
    return rng.choice(pool)


def read_call(c: NoiseCorpus, rng: random.Random) -> ToolCall:
    path = rng.choice(c.paths)
    n = rng.randint(24, 420)
    return ToolCall("Read", path, f"Read {n} lines", tokens=n * 11)


def search_call(c: NoiseCorpus, rng: random.Random) -> ToolCall:
    sym = pick_symbol(c, rng)
    where = _dir_of(rng.choice(c.paths))
    k = rng.randint(1, 9)
    return ToolCall("Search", f'pattern: "{sym}", path: "{where}"',
                    f"Found {k} file{'s' if k > 1 else ''}", tokens=120 + k * 40)


def list_call(c: NoiseCorpus, rng: random.Random) -> ToolCall:
    where = _dir_of(rng.choice(c.paths))
    return ToolCall("List", where, f"Listed {rng.randint(4, 40)} paths", tokens=200)


def bash_short_call(c: NoiseCorpus, rng: random.Random) -> ToolCall:
    choice = rng.randrange(3)
    if choice == 0:
        files = rng.sample(c.paths, k=min(len(c.paths), rng.randint(1, 3)))
        body = [f"{rng.choice(['M ', ' M', 'A '])} {p}" for p in files]
        return ToolCall("Bash", "git status --short", body[0], body[1:], tokens=150)
    if choice == 1:
        sym = pick_symbol(c, rng)
        files = rng.sample(c.paths, k=min(len(c.paths), 3))
        body = [f"{p}:{rng.randint(10, 300)}:    {sym}" for p in files]
        return ToolCall("Bash", f'rg -n "{sym}" | head -5', body[0], body[1:], tokens=260)
    line = rng.choice(c.commits)
    return ToolCall("Bash", "git log --oneline -3", line,
                    [rng.choice(c.commits) for _ in range(2)], tokens=140)


def light_call(c: NoiseCorpus, rng: random.Random) -> ToolCall:
    """A short tool call suitable between novel paragraphs."""
    return rng.choices([read_call, search_call, list_call, bash_short_call],
                       weights=[5, 4, 1, 2])[0](c, rng)


def diff_body(hunk: dict) -> tuple[list[str], int, int]:
    old = new = int(hunk.get("start", 1))
    out: list[str] = []
    added = removed = 0
    for line in hunk["lines"]:
        tag, text = line[:1], line[1:]
        if tag == "+":
            out.append(f"{new:>4} + {text}")
            new += 1
            added += 1
        elif tag == "-":
            out.append(f"{old:>4} - {text}")
            old += 1
            removed += 1
        else:
            out.append(f"{new:>4}   {text}")
            old += 1
            new += 1
    return out, added, removed


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def update_call(c: NoiseCorpus, rng: random.Random, hunk: dict | None = None) -> ToolCall:
    hunk = hunk or rng.choice(c.diffs)
    body, added, removed = diff_body(hunk)
    summary = (f"Updated {hunk['path']} with {_plural(added, 'addition')} "
               f"and {_plural(removed, 'removal')}")
    return ToolCall("Update", hunk["path"], summary, body, tokens=600 + 30 * len(body))


def _test_fqn(c: NoiseCorpus, name: str) -> str:
    for p in c.paths:
        if p.endswith(f"/{name}.java") or p.endswith(f"/{name}.kt"):
            for prefix in ("src/test/java/", "src/test/kotlin/"):
                if prefix in p:
                    return p.split(prefix, 1)[1].rsplit(".", 1)[0].replace("/", ".")
    return f"com.acme.{name}"


def suite_command(c: NoiseCorpus) -> str:
    return {
        "maven": "./mvnw -q test", "gradle": "./gradlew test", "npm": "npm test",
        "python": "pytest -q", "go": "go test ./...", "cargo": "cargo test",
    }.get(c.kind, "./mvnw -q test")


def suite_output(c: NoiseCorpus, rng: random.Random, count: int | None = None) -> list[str]:
    """Lines of a passing test run, in the style of the repo's build tool."""
    names = rng.sample(c.tests, k=min(len(c.tests), count or rng.randint(5, 12)))
    total = 0
    lines: list[str] = []
    if c.kind == "python":
        lines.append(f"platform linux -- Python 3.12.{rng.randint(1, 7)}, pytest-8.3.{rng.randint(1, 4)}")
        for i, n in enumerate(names):
            k = rng.randint(3, 18)
            total += k
            pct = int((i + 1) / len(names) * 100)
            lines.append(f"tests/{n}.py {'.' * k}{' ' * max(1, 30 - k)}[{pct:>3}%]")
        lines.append(f"{total} passed in {rng.uniform(2, 20):.2f}s")
        return lines
    if c.kind == "npm":
        for n in names:
            k = rng.randint(2, 15)
            total += k
            lines.append(f"PASS src/{n}.test.ts ({rng.uniform(0.2, 3):.3f} s)")
        lines += ["", f"Test Suites: {len(names)} passed, {len(names)} total",
                  f"Tests:       {total} passed, {total} total",
                  f"Time:        {rng.uniform(3, 25):.3f} s"]
        return lines
    if c.kind in ("go", "cargo"):
        for n in names:
            lines.append(f"ok  \t{n.lower()}\t{rng.uniform(0.01, 2):.3f}s")
        return lines
    module = c.root.rstrip("/").rsplit("/", 1)[-1] or "app"
    lines += ["[INFO] Scanning for projects...",
              f"[INFO] Building {module} 1.{rng.randint(2, 20)}.0-SNAPSHOT",
              f"[INFO] --- surefire:3.2.5:test (default-test) @ {module} ---"]
    for n in names:
        k = rng.randint(2, 24)
        total += k
        fqn = _test_fqn(c, n)
        lines.append(f"[INFO] Running {fqn}")
        lines.append(f"[INFO] Tests run: {k}, Failures: 0, Errors: 0, Skipped: 0, "
                     f"Time elapsed: {rng.uniform(0.05, 3):.3f} s -- in {fqn}")
    lines += ["[INFO] Results:", f"[INFO] Tests run: {total}, Failures: 0, Errors: 0, Skipped: 0",
              "[INFO] BUILD SUCCESS", f"[INFO] Total time:  {rng.uniform(8, 60):.3f} s"]
    return lines


def suite_call(c: NoiseCorpus, rng: random.Random, visible: int = 4) -> ToolCall:
    """A test run collapsed to its first few lines, for the start/end of a turn."""
    out = suite_output(c, rng)
    return ToolCall("Bash", suite_command(c), out[0], out[1:visible],
                    hidden=max(0, len(out) - visible), tokens=900)


def gitlog_call(c: NoiseCorpus, rng: random.Random, n: int = 12) -> ToolCall:
    lines = c.commits[:n] or ["(no commits)"]
    return ToolCall("Bash", f"git log --oneline -{n}", lines[0], lines[1:], tokens=300)


_AGENT_LINES = [
    "I'll look at how {cls} handles this before changing anything.",
    "Let me check where {fn} is called from.",
    "Now I'll trace the flow through {cls} and its tests.",
    "Good, {test} covers most of this. Let me read the remaining cases.",
    "I need to see how {cls} is wired up first.",
    "Let me verify the current behaviour of {fn}.",
    "That looks right. Next I'll check {cls}.",
]


def agent_line(c: NoiseCorpus, rng: random.Random) -> str:
    return rng.choice(_AGENT_LINES).format(
        cls=rng.choice(c.classes), fn=rng.choice(c.functions or c.classes),
        test=rng.choice(c.tests or c.classes))
