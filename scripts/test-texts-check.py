#!/usr/bin/env python3
"""Decision tests for texts-check.py -- run by scripts/lint.sh (CI and pre-commit).

The functions under test are the script's own, unmodified, on the real texts
and the real tree of this repository, edited in memory; the live services are
replaced by their answers as of 2026-10-14, so these cases need no network.
Exit 1 if any case disagrees. TEXTSCHECK=<path> runs them against another copy.
"""
import importlib.util
import json
import os
import pathlib
import sys

sys.dont_write_bytecode = True
for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("textscheck", os.environ.get("TEXTSCHECK", HERE / "texts-check.py"))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
ROOT, DESCR = t.ROOT, t.DESCR
COPR_TEXTS = f"{DESCR}/copr-description.md + {DESCR}/copr-instructions.md"

results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f": {got!r} (expected {want!r})"))


def has(findings, *words):
    return any(all(w in f for w in words) for f in findings)


REAL_READ, REAL_GET, REAL_FETCH = t.read, t.get, t.fetch


def with_texts(edits):
    """read() with texts edited in memory: {rel: (old, new)}, every occurrence."""
    edited = {}
    for rel, (old, new) in edits.items():
        body = REAL_READ(ROOT, rel)
        edited[rel] = body.replace(old, new)
        assert edited[rel] != body, f"test setup: {old!r} not found in {rel}"
    t.read = lambda root, r: edited[r] if r in edited else REAL_READ(root, r)


def restore():
    t.read, t.get, t.fetch = REAL_READ, REAL_GET, REAL_FETCH


# --- the readers ---------------------------------------------------------------------
check("a name of its own", t.names("install tea here", "tea"), True)
check("not inside a longer package name", t.names("install tea-cli here", "tea"), False)
check("not inside a word", t.names("the team", "tea"), False)
check("any case", t.names("**Syft** scans", "syft"), True)
check("after a slash", t.names("[anchore/grant](x)", "grant"), True)
check("units: bullets, headings and paragraphs",
      t.units("# Head\ntext one\ncontinued\n\n- a\n  b\n- c\n<!--\n- hidden 12\n-->\nlast\n"),
      ["# Head", "text one continued", "- a b", "- c", "last"])
check("a version needs its word in the same unit", t.mentions("- Fedora 43.\n- rawhide, 44.\n", "Fedora", "44"), False)
check("... and is found there", t.mentions("- Fedora 43, 44 and\n  rawhide.\n", "Fedora", "44"), True)
check("a version at a sentence end", t.mentions("First builds: Fedora 45.", "Fedora", "45"), True)
check("a version is not a longer number", t.mentions("Fedora 450", "Fedora", "45"), False)
check("a version is not part of another", t.mentions("Fedora 44.1", "Fedora", "44"), False)
check("line ends and trailing blanks are no drift", t.norm("a  \r\nb\n\n"), t.norm("a\nb"))

# --- the targets -------------------------------------------------------------------------
CHROOTS = ["fedora-43-x86_64", "fedora-44-x86_64", "fedora-45-x86_64", "fedora-rawhide-x86_64"]
check("today: three releases, one architecture, nothing unknown", t.targets(CHROOTS),
      ({"43", "44", "45"}, {"x86_64"}, []))
check("aarch64 is an architecture", t.targets(["fedora-44-aarch64"])[1], {"aarch64"})
check("rawhide is no release of its own", t.targets(["fedora-rawhide-x86_64"])[0], set())
check("forms not understood", t.targets(["epel-10-x86_64", "opensuse-leap-16.0-x86_64", "fedora-44-ppc64le"])[2],
      ["epel-10-x86_64", "opensuse-leap-16.0-x86_64", "fedora-44-ppc64le"])

# --- offline: the real tree --------------------------------------------------------------
f, _ = t.offline()
check("the real tree: every package and workflow named", f, [])
check("packages come from fedora/ and packaging.conf", sorted(t.packages()), ["grant", "grype", "syft", "tea"])
with_texts({"docs/how-it-works.md": ("grant", "gr_ant")})
f, _ = t.offline()
restore()
check("grant gone from how-it-works (every mention, the watcher's name too)", f,
      ["docs/how-it-works.md: does not name `grant` (fedora/grant/ builds it)",
       "docs/how-it-works.md: does not name watch-grant-releases.yml"])
with_texts({"packaging.conf": ("TOOLS[grant]=", 'TOOLS[newtool]="newtool|fedora/newtool/newtool.spec|build-newtool"\n'
                                                 "TOOLS[grant]=")})
f, _ = t.offline()
restore()
check("a tool only packaging.conf knows, which no text describes", f,
      ["README.md: does not name `newtool` (packaging.conf routes newtool)",
       "docs/how-it-works.md: does not name `newtool` (packaging.conf routes newtool)",
       f"{COPR_TEXTS}: does not name `newtool` (packaging.conf routes newtool)"])
with_texts({"docs/descriptions/copr-instructions.md": ("grype", "gr_ype")})
f, _ = t.offline()
restore()
check("the COPR texts are read as one: the description still names grype", f, [])
with_texts({"docs/descriptions/copr-instructions.md": ("grype", "gr_ype"),
           "docs/descriptions/copr-description.md": ("grype", "gr_ype")})
f, _ = t.offline()
restore()
check("... and neither does", f, [f"{COPR_TEXTS}: does not name `grype` (fedora/grype/ builds it)"])
with_texts({"docs/how-it-works.md": ("copr-reconcile.yml", "copr-reconcile")})
f, _ = t.offline()
restore()
check("a workflow missing from how-it-works", f, ["docs/how-it-works.md: does not name copr-reconcile.yml"])
with_texts({"packaging.conf": ("TOOLS[", "#TOOLS[")})
check("packaging.conf without a TOOLS line: exit 2", t.main(["offline"]), 2)
restore()


def missing(root, rel):
    raise t.Unmeasured(f"{rel}: gone")


t.read = missing
check("offline: an unreadable text is exit 2", t.main(["offline"]), 2)
restore()

# --- live: the answers of 2026-10-14, with the git copies as the live texts ---------------------
GOT = {key: REAL_READ(ROOT, f"{DESCR}/{fname}") for fname, key in t.LIVE.items()}
GOT.update(copr_chroots=CHROOTS)


def live_with(**changes):
    return t.live({**GOT, **changes})[0]


check("live: the git copies against themselves", live_with(), [])
f = live_with(copr_description=GOT["copr_description"].replace("Fedora 43+", "Fedora 44+"))
check("live: a description edited on COPR", has(f, f"{DESCR}/copr-description.md: the live text differs",
                                                "-Public", "+Public"), True)
f = live_with(github=GOT["github"] + "\n")
check("live: a trailing newline is no drift", f, [])
f = live_with(copr_chroots=CHROOTS + ["fedora-46-x86_64"])
check("live: a new Fedora release the CHANGELOG does not name", f,
      ["CHANGELOG.md: does not name Fedora 46 (COPR builds it)"])
f = live_with(copr_chroots=CHROOTS + ["fedora-45-aarch64"])
check("live: a new architecture", f, ["CHANGELOG.md: does not name aarch64 (aarch64/x86_64 are built)"])
f = live_with(copr_chroots=CHROOTS + ["epel-10-x86_64"])
check("live: an unknown chroot is a finding", has(f, "COPR chroot epel-10-x86_64", "form not understood"), True)
with_texts({"CHANGELOG.md": ("First Fedora 45 builds", "First builds of the next Fedora")})
f = live_with()
restore()
check("live: a release the CHANGELOG never names", f, ["CHANGELOG.md: does not name Fedora 45 (COPR builds it)"])

# --- live: reading the services ------------------------------------------------------------
ANSWERS = {t.GITHUB_API: json.dumps({"description": "About"}),
           t.COPR_API: json.dumps({"description": "D", "instructions": "I", "chroot_repos": {c: "url" for c in CHROOTS}})}
t.get = lambda url, token=None: ANSWERS[url]
check("fetch: what the check compares", t.fetch(),
      {"github": "About", "copr_description": "D", "copr_instructions": "I", "copr_chroots": CHROOTS})
ANSWERS[t.COPR_API] = json.dumps({"description": "D", "instructions": "I"})
try:
    t.fetch()
    check("fetch: an answer without chroots", "no exception", "Unmeasured")
except t.Unmeasured:
    check("fetch: an answer without chroots", "Unmeasured", "Unmeasured")
ANSWERS[t.COPR_API] = json.dumps({"description": "D", "instructions": "I", "chroot_repos": {}})
check("live: COPR listing no chroot is exit 2", t.main(["live"]), 2)
restore()
t.fetch = lambda: (_ for _ in ()).throw(t.Unmeasured("COPR: timed out"))
check("live: a service that does not answer is exit 2", t.main(["live"]), 2)
restore()
check("usage: an unknown mode is exit 2", t.main(["bogus"]), 2)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
