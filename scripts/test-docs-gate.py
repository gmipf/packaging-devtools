#!/usr/bin/env python3
"""Decision tests for docs-gate.py -- run by scripts/lint.sh (CI and pre-commit).

The rule is tested on paths and messages, the hook and the CI mode on a
throwaway git repository with real commits. Exit 1 if any case disagrees.
DOCSGATE=<path> runs the cases against another copy of the script.
"""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
# Run from a hook, git exports GIT_INDEX_FILE & co.; the throwaway repository
# below would otherwise stage into the commit being made.
for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("docsgate", os.environ.get("DOCSGATE", HERE / "docs-gate.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f": {got!r} (expected {want!r})"))


tmp = tempfile.TemporaryDirectory(prefix="docs-gate-test-")
REPO = pathlib.Path(tmp.name)


def sh(*args):
    return subprocess.run(["git", "-C", str(REPO), "-c", "user.name=t", "-c", "user.email=t@example.org",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True).stdout


def write(rel, text):
    p = REPO / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit(msg, *files):
    for rel, text in files:
        write(rel, text)
        sh("add", rel)
    sh("commit", "-q", "-m", msg)
    return sh("rev-parse", "HEAD").strip()


def ok_of(paths, msg):
    return g.judge(paths, msg, REPO)[0]


def why_of(paths, msg):
    return g.judge(paths, msg, REPO)[2]


sh("init", "-q", "-b", "main")
SPEC = "fedora/foo/foo.spec"
OK = "\n\nDocs-unchanged: only a build flag, nothing a reader sees\n"

# --- the rule ---------------------------------------------------------------------
check("a spec alone, no trailer", ok_of([SPEC], "foo: fix\n"), False)
check("... and why", why_of([SPEC], "foo: fix\n"), "no text changed and no `Docs-unchanged:` trailer")
check("a vendored source alone", ok_of(["fedora/foo/foo-1.0.tar.gz"], "x\n"), False)
check("a spec with the README", ok_of([SPEC, "README.md"], "foo: fix\n"), True)
check("a spec with CHANGELOG.md", ok_of([SPEC, "CHANGELOG.md"], "foo: fix\n"), True)
check("a spec with a docs/ page", ok_of([SPEC, "docs/how-it-works.md"], "foo: fix\n"), True)
check("a spec with a live description", ok_of([SPEC, "docs/descriptions/github-about.txt"], "x\n"), True)
check("a spec with a reason", ok_of([SPEC], "foo: fix" + OK), True)
check("a reason too short", ok_of([SPEC], "foo: fix\n\nDocs-unchanged: none\n"), False)
check("... and why", why_of([SPEC], "foo: fix\n\nDocs-unchanged: none\n"),
      "`Docs-unchanged: none` gives no reason (at least 3 words)")
check("the key in any case", ok_of([SPEC], "foo: fix\n\ndocs-unchanged: a b c\n"), True)
check("next to Co-Authored-By", ok_of([SPEC], "foo: fix\n\nDocs-unchanged: a b c\nCo-Authored-By: X <x@example.org>\n"),
      True)
check("not in the last paragraph = no trailer", ok_of([SPEC], "foo: fix\n\nDocs-unchanged: a b c\n\nmore text\n"), False)
check("a workflow alone", ok_of([".github/workflows/w.yml"], "x\n"), False)
check(".packit.yaml alone", ok_of([".packit.yaml"], "x\n"), False)
check("packaging.conf alone", ok_of(["packaging.conf"], "x\n"), False)
check("a script alone", ok_of(["scripts/lint.sh"], "x\n"), True)
check("a text alone", ok_of(["CHANGELOG.md"], "x\n"), True)
check("a README deeper in the tree is a recipe file, not a text",
      g.classify(["fedora/foo/README.md"]), (["fedora/foo/README.md"], []))
check("comment lines and the scissors drop out",
      g.cleaned("x\n\nDocs-unchanged: a b c\n# Please enter\n" + g.SCISSORS + "\ndiff --git\n"),
      "x\n\nDocs-unchanged: a b c\n")

# --- the hints ----------------------------------------------------------------------
commit("init", ("README.md", "Install `foo` with dnf.\n"), ("docs/how-it-works.md", "The workflows.\n"),
       (SPEC, "Name: foo\n"), ("CHANGELOG.md", "# Changelog\n"))
h = g.hints([SPEC, ".github/workflows/w.yml", "packaging.conf", ".packit.yaml"], REPO)
check("names the texts that mention the package", h[0], "  `foo` is named in: README.md")
check("points a workflow at how-it-works", any("docs/how-it-works.md" in x for x in h), True)
check("points packaging.conf at the README", any("packaging.conf" in x and "README.md" in x for x in h), True)
check("points .packit.yaml at the CHANGELOG", any(".packit.yaml" in x and "CHANGELOG.md" in x for x in h), True)
h = g.hints(["fedora/newpkg/newpkg.spec"], REPO)
check("a package no text names", h[0], "  `newpkg` is named in: no text at all -- a new package?")

# --- the hook: the staged change -------------------------------------------------------
msgfile = REPO / ".git" / "TEST_MSG"
write(SPEC, "Name: foo\nVersion: 2\n")
sh("add", SPEC)
msgfile.write_text("foo: bump\n", encoding="utf-8")
check("hook: a staged spec, no reason", g.staged(msgfile, REPO), 1)
msgfile.write_text("foo: bump" + OK, encoding="utf-8")
check("hook: a staged spec with a reason", g.staged(msgfile, REPO), 0)
msgfile.write_text("foo: bump\n\n# Docs-unchanged: a commented-out reason\n", encoding="utf-8")
check("hook: a reason in a comment line does not count", g.staged(msgfile, REPO), 1)
write("README.md", "Install `foo` 2 with dnf.\n")
sh("add", "README.md")
msgfile.write_text("foo: bump\n", encoding="utf-8")
check("hook: a staged spec with the README", g.staged(msgfile, REPO), 0)
sh("reset", "-q", "README.md")
(REPO / ".git" / "MERGE_HEAD").write_text("0" * 40 + "\n")
check("hook: a merge is left to CI", g.staged(msgfile, REPO), 0)
(REPO / ".git" / "MERGE_HEAD").unlink()
sh("reset", "-q", "--hard")

# --- CI: every pushed commit ---------------------------------------------------------------
c0 = sh("rev-parse", "HEAD").strip()
c1 = commit("foo: bump without a word", (SPEC, "Name: foo\nVersion: 3\n"))
commit("foo: bump with a reason" + OK, (SPEC, "Name: foo\nVersion: 4\n"))
c3 = commit("foo: bump with the README", (SPEC, "Name: foo\nVersion: 5\n"), ("README.md", "Install `foo` 5.\n"))
check("CI: a range with one commit lacking a reason", g.pushed(f"{c0}..{c3}", REPO), 1)
check("CI: a range of good commits", g.pushed(f"{c1}..{c3}", REPO), 0)
sh("checkout", "-q", "-b", "side", c0)
commit("side: a text", ("CHANGELOG.md", "# Changelog\n\nmore\n"))
sh("checkout", "-q", "main")
sh("merge", "-q", "--no-ff", "-m", "Merge side", "side")
m = sh("rev-parse", "HEAD").strip()
check("CI: a merge is skipped, the commits it brings are read", g.pushed(f"{c3}..{m}", REPO), 0)
check("CI: a new branch reads its tip", g.pushed(f"{'0' * 40}..{c1}", REPO), 1)
for label, rng in (("CI: a base not in the repository", f"{'1' * 40}..{c3}"), ("CI: not a range", "HEAD")):
    try:
        g.pushed(rng, REPO)
        check(label, "no exception", "Unmeasured")
    except g.Unmeasured:
        check(label, "Unmeasured", "Unmeasured")
check("usage: no mode is exit 2", g.main([]), 2)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
