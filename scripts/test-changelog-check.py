#!/usr/bin/env python3
"""Decision tests for changelog-check.py -- run by scripts/lint.sh (CI and pre-commit).

The functions under test are the script's own, unmodified, on the real
CHANGELOG.md and the real tree of this repository, edited in memory. Exit 1 if
any case disagrees. CHANGELOGCHECK=<path> runs the cases against another copy of
the script.
"""
import importlib.util
import os
import pathlib
import sys

sys.dont_write_bytecode = True
for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("changelogcheck",
                                              os.environ.get("CHANGELOGCHECK", HERE / "changelog-check.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f": {got!r} (expected {want!r})"))


def edited(old, new):
    s = LOG.replace(old, new, 1)
    assert s != LOG, f"test setup: {old!r} not found in CHANGELOG.md"
    return s


def has(findings, *words):
    return any(all(w in f for w in words) for f in findings)


LOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
TREE = c.tree()
SYFT = "- Added `syft` on Fedora. Anchore's SBOM generator."

# --- the tree as the check sees it ---------------------------------------------
check("tree: 4 packages on Fedora", TREE, {(p, "Fedora") for p in ("tea", "syft", "grype", "grant")})

# --- green ---------------------------------------------------------------------
check("the real log against the real tree", c.check(LOG, TREE), [])

# --- red: log and tree disagree --------------------------------------------------
f = c.check(edited(SYFT, "- Something about syft."), TREE)
check("a recipe with no Added line is named", has(f, "`syft`", "Fedora", "fedora/syft/", "no line adds it"), True)
f = c.check(LOG, TREE | {("newtool", "Fedora")})
check("a new recipe in the tree is named", has(f, "`newtool`", "fedora/newtool/", "no line adds it"), True)
f = c.check(LOG, TREE - {("grant", "Fedora")})
check("a recipe that is gone while the log ships it", has(f, "`grant`", "fedora/grant/", "Removed or Renamed"), True)

# --- red: the log contradicts itself ----------------------------------------------
f = c.check(edited("## 2026-06-24", "## 2026-07-20"), TREE)
check("dates out of order", has(f, "2026-07-20 after 2026-07-01", "newest first"), True)
f = c.check(edited("## 2026-06-24", "## 2026-07-01"), TREE)
check("the same day twice", has(f, "2026-07-01 after 2026-07-01"), True)
f = c.check(edited("## 2026-06-24", "## June 24th"), TREE)
check("a heading that is no date", has(f, "'## June 24th'", "YYYY-MM-DD"), True)
f = c.check(edited("## 2026-08-27\n", "## 2026-08-27\n\n- Removed `ghost` on Fedora.\n"), TREE)
check("removing what was never added", has(f, "removed `ghost` on Fedora", "no older line added"), True)
f = c.check(edited("## 2026-08-27\n", "## 2026-08-27\n\n- Added `tea` on Fedora.\n"), TREE)
check("adding what is already there", has(f, "adds `tea` on Fedora", "already added"), True)
f = c.check(edited("## 2026-08-27\n", "## 2026-08-27\n\n- Renamed `ghost` to `spook` on Fedora.\n"), TREE)
check("renaming what was never added", has(f, "renamed `ghost` on Fedora", "no older line added"), True)
check("... and the new name is then shipped without a recipe", has(f, "`spook`", "fedora/spook/ is gone"), True)
f = c.check(edited("## 2026-08-27\n", "## 2026-08-27\n\n- Renamed `grant` to `grant2` on Fedora.\n"),
            TREE - {("grant", "Fedora")} | {("grant2", "Fedora")})
check("a rename that matches the tree", f, [])

# --- red: a line the check cannot read is a finding, never skipped ------------------
f = c.check(edited(SYFT, "- Added syft on Fedora. Anchore's SBOM generator."), TREE)
check("a package without backticks", has(f, "cannot read this line"), True)
check("... and the package then counts as missing", has(f, "`syft`", "no line adds it"), True)
f = c.check(edited(SYFT, "- Added `syft` on Fedora 44.1 and later."), TREE)
check("a version number in the distribution list", has(f, "cannot read this line"), True)
f = c.check(edited(SYFT, "- Added `syft` on Fedora and EPEL. Anchore's SBOM generator."), TREE)
check("a distribution this repository does not build for", has(f, "unknown distribution 'EPEL'"), True)
f = c.check("- Added `tea` on Fedora.\n\n" + LOG, TREE)
check("an entry before the first date", has(f, "entry before the first dated section"), True)

# --- the reader ---------------------------------------------------------------------
s, f = c.parse("## 2026-01-02\n\n- Added `a` and\n  `b` on\n  Fedora. Text.\n")
check("a wrapped line reads as one", (s, f), ([("2026-01-02", [(3, "Added", ["a", "b"], ["Fedora"])])], []))
s, f = c.parse("## 2026-01-02\n\n- Added `a`, `b`, and `c` on Fedora. Text.\n")
check("an Oxford comma", s[0][1][0][2], ["a", "b", "c"])
s, f = c.parse("## 2026-01-02\n\n- Renamed `a` to `b` and `c` to `d` on Fedora. Text.\n")
check("two renames in one line", s[0][1][0][2], [("a", "b"), ("c", "d")])
s, f = c.parse("<!--\n- Added `x` on Fedora.\n-->\n## 2026-01-02\n\n- Added `y` on Fedora.\n")
check("lines inside a comment are not entries, line numbers stay true", (s, f),
      ([("2026-01-02", [(6, "Added", ["y"], ["Fedora"])])], []))
s, f = c.parse("## 2026-01-02\n\n- The COPR repository starts. Added `x` on Fedora.\n")
check("free text is not an entry", (s, f), ([("2026-01-02", [])], []))

# --- main: not measured is not clean --------------------------------------------------
saved_root, saved_tree = c.ROOT, c.tree
c.ROOT = pathlib.Path("/nonexistent-changelog-check")
check("no CHANGELOG.md: exit 2", c.main(), 2)
c.ROOT, c.tree = saved_root, (lambda: set())
check("no recipe found: exit 2", c.main(), 2)
c.tree = saved_tree
check("the real repository: exit 0", c.main(), 0)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
