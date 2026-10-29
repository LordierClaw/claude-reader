import subprocess

import pytest

from ccreader.noise import builtin_corpus, load_corpus, parse_diffs, scan_repo
from ccreader.state import Store

LOG = """commit abc
Author: x

    msg

diff --git a/src/Foo.java b/src/Foo.java
index 1..2 100644
--- a/src/Foo.java
+++ b/src/Foo.java
@@ -10,4 +10,5 @@ class Foo {
     int a;
-    int b;
+    int b = 1;
+    int c;
     int d;
diff --git a/img.png b/img.png
Binary files a/img.png and b/img.png differ
"""


def test_parse_diffs():
    hunks = parse_diffs(LOG)
    assert len(hunks) == 1
    assert hunks[0]["path"] == "src/Foo.java"
    assert hunks[0]["start"] == 10
    assert hunks[0]["lines"][1] == "-    int b;"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "payment-core"
    src = root / "src/main/java/com/acme"
    test = root / "src/test/java/com/acme"
    src.mkdir(parents=True)
    test.mkdir(parents=True)
    (root / "pom.xml").write_text("<project/>")
    (src / "LedgerService.java").write_text(
        "public class LedgerService {\n    public void postEntry(int a) {\n        a++;\n    }\n}\n")
    (test / "LedgerServiceTest.java").write_text("class LedgerServiceTest {}\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "junk.js").write_text("class Junk {}")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=a@b", "-c", "user.name=a", "add", ".")
    _git(root, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "first")
    (src / "LedgerService.java").write_text(
        "public class LedgerService {\n    public void postEntry(int a) {\n        a += 2;\n"
        "        log(a);\n    }\n}\n")
    _git(root, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qam", "second")
    return root


def test_scan_repo(repo):
    c = scan_repo(repo)
    assert c.kind == "maven"
    assert "src/main/java/com/acme/LedgerService.java" in c.paths
    assert not any("node_modules" in p for p in c.paths)
    assert "LedgerService" in c.classes and "Junk" not in c.classes
    assert "postEntry" in c.functions
    assert c.tests == ["LedgerServiceTest"]
    assert any(d["path"].endswith("LedgerService.java") for d in c.diffs)
    assert c.commits[0].endswith("second")


def test_load_corpus_is_cached(repo):
    store = Store()
    first = load_corpus(str(repo), store)
    (repo / "New.java").write_text("class Brand {}")
    assert load_corpus(str(repo), store) == first
    assert "New.java" in load_corpus(str(repo), store, rescan=True).paths


def test_builtin_corpus_is_complete():
    c = builtin_corpus()
    for name in ("paths", "classes", "functions", "tests", "diffs", "commits"):
        assert getattr(c, name)
