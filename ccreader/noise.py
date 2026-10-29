"""The "noise corpus": real names and diffs from a work repo, used as disguise.

The repo is scanned once; the result is cached (encoded) in the store.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "target", "build", "dist", "out", ".venv",
    "venv", "env", "__pycache__", ".idea", ".vscode", ".gradle", "vendor", ".tox",
    ".mypy_cache", ".pytest_cache", ".next", "coverage", "bin", "obj",
}
CODE_EXT = {
    ".java", ".kt", ".scala", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".cs",
    ".rb", ".php", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".m",
}
OTHER_EXT = {".sql", ".yml", ".yaml", ".xml", ".json", ".md", ".toml", ".gradle",
             ".properties", ".sh", ".proto", ".graphql"}

_CLASS_RE = re.compile(r"\b(?:class|interface|enum|record|struct|trait|object|type)\s+([A-Z][A-Za-z0-9_]{2,})")
_FUNC_RE = re.compile(
    r"(?:\bdef\s+([a-z_][a-z0-9_]{3,})\s*\("
    r"|\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w{3,})\s*\("
    r"|\bfn\s+([a-z_]\w{3,})\s*\("
    r"|(?:public|private|protected|internal)\s+(?:static\s+|final\s+|async\s+|override\s+)*[\w<>\[\],? ]+\s+([a-z]\w{3,})\s*\()"
)
_TEST_FILE_RE = re.compile(r"(Test|Tests|Spec|IT)\.\w+$|^test_.*\.py$|_test\.(go|py)$|\.(spec|test)\.[jt]sx?$")


@dataclass
class NoiseCorpus:
    root: str
    kind: str = "maven"
    branch: str = "main"
    paths: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    diffs: list[dict] = field(default_factory=list)  # {"path": str, "start": int, "lines": [str]}
    commits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NoiseCorpus":
        names = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in names})

    def filled(self) -> "NoiseCorpus":
        """Fill any empty list from the built-in corpus so generators never starve."""
        base = builtin_corpus(self.root)
        for name in ("paths", "classes", "functions", "tests", "diffs", "commits"):
            if not getattr(self, name):
                setattr(self, name, getattr(base, name))
        return self


def detect_kind(root: Path) -> str:
    if (root / "pom.xml").exists():
        return "maven"
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return "gradle"
    if (root / "package.json").exists():
        return "npm"
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "python"
    if (root / "go.mod").exists():
        return "go"
    if (root / "Cargo.toml").exists():
        return "cargo"
    return "maven"


def _git(root: Path, *args: str, limit: int = 400_000) -> str:
    try:
        proc = subprocess.Popen(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return ""
    try:
        data = proc.stdout.read(limit) if proc.stdout else b""
    finally:
        proc.kill()
        proc.wait()
    return data.decode("utf-8", errors="replace")


def parse_diffs(log: str, max_hunks: int = 200, min_lines: int = 3,
                max_lines: int = 24) -> list[dict]:
    """Extract short hunks from `git log -p` output."""
    hunks: list[dict] = []
    path = None
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current and min_lines <= len(current["lines"]) <= max_lines:
            if any(l[:1] in "+-" for l in current["lines"]):
                hunks.append(current)
        current = None

    for line in log.split("\n"):
        if line.startswith("diff --git "):
            flush()
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            path = m.group(2) if m else None
        elif line.startswith("@@"):
            flush()
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if path and m:
                current = {"path": path, "start": int(m.group(1)), "lines": []}
        elif line.startswith(("commit ", "Binary files", "index ", "--- ", "+++ ")):
            flush()
        elif current is not None:
            if line[:1] in (" ", "+", "-") and len(line) < 160:
                current["lines"].append(line)
            elif line == "":
                current["lines"].append(" ")
            else:
                current = None
        if len(hunks) >= max_hunks:
            break
    flush()
    return hunks[:max_hunks]


def scan_repo(root: str | Path, max_files: int = 4000, max_read: int = 600,
              log_bytes: int = 1_500_000) -> NoiseCorpus:
    root = Path(root).expanduser().resolve()
    paths: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    tests: list[str] = []
    read = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            if ext not in CODE_EXT and ext not in OTHER_EXT:
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            paths.append(rel)
            is_test = bool(_TEST_FILE_RE.search(name)) or "/test" in f"/{rel}"
            if is_test and ext in CODE_EXT:
                tests.append(os.path.splitext(name)[0])
            if ext in CODE_EXT and read < max_read:
                try:
                    if full.stat().st_size > 200_000:
                        continue
                    text = full.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                read += 1
                classes.extend(_CLASS_RE.findall(text))
                for groups in _FUNC_RE.findall(text):
                    functions.extend(g for g in groups if g and not g.startswith("_"))
            if len(paths) >= max_files:
                break
        if len(paths) >= max_files:
            break

    log = _git(root, "log", "-p", "--no-color", "--no-ext-diff", "-n", "300", limit=log_bytes)
    oneline = _git(root, "log", "--oneline", "--no-color", "-n", "200")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() or "main"

    def uniq(items: list[str], cap: int) -> list[str]:
        return list(dict.fromkeys(items))[:cap]

    return NoiseCorpus(
        root=str(root),
        kind=detect_kind(root),
        branch=branch,
        paths=paths,
        classes=uniq(classes, 800),
        functions=uniq(functions, 800),
        tests=uniq(tests, 400),
        diffs=parse_diffs(log),
        commits=[l for l in oneline.split("\n") if l.strip()],
    ).filled()


def load_corpus(repo: str | None, store=None, rescan: bool = False) -> NoiseCorpus:
    """Return the cached corpus for `repo` (scanning it once), or the built-in one."""
    if not repo:
        return builtin_corpus()
    root = str(Path(repo).expanduser().resolve())
    if store is not None and not rescan:
        cached = store.get("corpus", root)
        if cached:
            return NoiseCorpus.from_dict(cached)
    corpus = scan_repo(root)
    if store is not None:
        store.put(corpus.to_dict(), "corpus", root)
    return corpus


# -- built-in corpus (used without --repo, and to fill gaps) -----------------

_PKG = "src/main/java/com/acme/payment"
_TPKG = "src/test/java/com/acme/payment"
_BUILTIN_CLASSES = [
    "PaymentRetryScheduler", "RetryPolicy", "BackoffCalculator", "IdempotencyKeyStore",
    "LedgerEntryMapper", "SettlementBatchJob", "PaymentGatewayClient", "WebhookDispatcher",
    "RefundService", "CurrencyConverter", "FraudScoreEvaluator", "PaymentStateMachine",
    "OutboxPublisher", "ReconciliationReport", "CardTokenVault", "ChargebackHandler",
]
_BUILTIN_DIRS = ["retry", "retry", "retry", "idempotency", "ledger", "settlement", "gateway",
                 "webhook", "refund", "fx", "fraud", "core", "outbox", "recon", "vault", "dispute"]


def builtin_corpus(root: str | None = None) -> NoiseCorpus:
    paths = [f"{_PKG}/{d}/{c}.java" for d, c in zip(_BUILTIN_DIRS, _BUILTIN_CLASSES)]
    tests = [f"{c}Test" for c in _BUILTIN_CLASSES[:12]]
    paths += [f"{_TPKG}/{d}/{c}Test.java" for d, c in zip(_BUILTIN_DIRS, _BUILTIN_CLASSES[:12])]
    paths += ["pom.xml", "src/main/resources/application.yml",
              "src/main/resources/db/migration/V42__add_retry_attempts.sql", "README.md"]
    functions = [
        "scheduleRetry", "nextBackoff", "isRetryable", "markSettled", "reserveKey",
        "publishPending", "toLedgerEntry", "evaluateScore", "handleWebhook", "convertAmount",
        "transitionTo", "refundPartial", "loadPendingBatch", "verifySignature",
    ]
    diffs = [
        {"path": f"{_PKG}/retry/BackoffCalculator.java", "start": 41, "lines": [
            "     public Duration nextBackoff(int attempt) {",
            "-        long delay = baseDelayMs * (1L << attempt);",
            "-        return Duration.ofMillis(Math.min(delay, maxDelayMs));",
            "+        long exp = baseDelayMs * (1L << Math.min(attempt, 16));",
            "+        long capped = Math.min(exp, maxDelayMs);",
            "+        long jitter = ThreadLocalRandom.current().nextLong(capped / 4 + 1);",
            "+        return Duration.ofMillis(capped - jitter);",
            "     }"]},
        {"path": f"{_PKG}/retry/PaymentRetryScheduler.java", "start": 88, "lines": [
            "         if (!policy.isRetryable(result.code())) {",
            "-            log.warn(\"giving up on {}\", payment.id());",
            "+            log.warn(\"giving up on {} after {} attempts\", payment.id(), attempt);",
            "+            metrics.counter(\"payment.retry.exhausted\").increment();",
            "             return RetryDecision.abort();",
            "         }"]},
        {"path": f"{_PKG}/idempotency/IdempotencyKeyStore.java", "start": 27, "lines": [
            "-    private final Map<String, Instant> keys = new HashMap<>();",
            "+    private final Map<String, Instant> keys = new ConcurrentHashMap<>();",
            " ",
            "     public boolean reserveKey(String key) {",
            "-        if (keys.containsKey(key)) return false;",
            "-        keys.put(key, clock.instant());",
            "-        return true;",
            "+        return keys.putIfAbsent(key, clock.instant()) == null;",
            "     }"]},
        {"path": f"{_PKG}/outbox/OutboxPublisher.java", "start": 63, "lines": [
            "     @Scheduled(fixedDelayString = \"${outbox.poll-interval:500}\")",
            "     public void publishPending() {",
            "-        List<OutboxEvent> batch = repository.findPending(100);",
            "+        List<OutboxEvent> batch = repository.findPendingForUpdate(batchSize);",
            "+        if (batch.isEmpty()) {",
            "+            return;",
            "+        }",
            "         batch.forEach(this::publish);"]},
        {"path": f"{_TPKG}/retry/BackoffCalculatorTest.java", "start": 19, "lines": [
            "     @Test",
            "-    void backoffDoublesEachAttempt() {",
            "-        assertThat(calc.nextBackoff(3)).isEqualTo(Duration.ofMillis(800));",
            "+    void backoffIsCappedAndJittered() {",
            "+        Duration d = calc.nextBackoff(30);",
            "+        assertThat(d).isLessThanOrEqualTo(Duration.ofMillis(MAX_DELAY));",
            "+        assertThat(d).isGreaterThan(Duration.ofMillis(MAX_DELAY * 3 / 4));",
            "     }"]},
        {"path": "src/main/resources/application.yml", "start": 12, "lines": [
            " payment:",
            "   retry:",
            "-    max-attempts: 5",
            "+    max-attempts: 7",
            "+    max-delay: 30s",
            "     base-delay: 200ms"]},
        {"path": f"{_PKG}/core/PaymentStateMachine.java", "start": 112, "lines": [
            "         case AUTHORIZED -> switch (event) {",
            "             case CAPTURE -> State.CAPTURED;",
            "-            case VOID -> State.VOIDED;",
            "+            case VOID, EXPIRE -> State.VOIDED;",
            "             default -> throw illegal(state, event);",
            "         };"]},
    ]
    commits = [
        "a91f3c2 retry: cap exponential backoff and add jitter",
        "7d04e18 idempotency: use putIfAbsent to close race",
        "c3b5a90 outbox: lock pending rows before publishing",
        "52e7d1f ledger: map partial refunds to separate entries",
        "e18aa4b settlement: skip empty batches",
        "0f9c6d3 test: cover webhook signature rotation",
        "9be2047 fx: round half-even when converting amounts",
        "41d8f75 fraud: lower threshold for new cards",
        "d6a0c11 build: bump spring-boot to 3.3.4",
        "8e31b9a core: allow EXPIRE from AUTHORIZED",
        "2c47f0e gateway: propagate request id header",
        "f5d9e62 recon: include currency in report key",
    ]
    return NoiseCorpus(
        root=root or "~/code/payment-core", kind="maven", branch="feature/retry-backoff",
        paths=paths, classes=list(_BUILTIN_CLASSES), functions=functions, tests=tests,
        diffs=diffs, commits=commits,
    )
