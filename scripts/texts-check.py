#!/usr/bin/env python3
"""The texts a reader sees, against what this repository ships.

  texts-check.py offline
      Every package (each fedora/<pkg>/ and each tool in packaging.conf) is
      named in README.md, in docs/how-it-works.md and in the COPR texts; every
      workflow is named in docs/how-it-works.md. Runs in scripts/lint.sh, so in
      CI and in the pre-commit hook.

  texts-check.py live [--save DIR]
      The descriptions on GitHub (About) and COPR (Description, Installation
      Instructions) equal their copies in docs/descriptions/, and CHANGELOG.md
      names every Fedora release and architecture COPR builds for. Reads the
      public APIs without a login (GH_TOKEN, when set, only lifts GitHub's rate
      limit). Runs in check-repo.yml on every push and every day.
      --save DIR writes the live texts to DIR, to look at a drift.

Why: the recipes move and the texts stay behind. The live descriptions had no
copy in git at all, so nothing could compare them with anything; a new release
on COPR reached no text unless someone remembered. The per-commit half (does a
recipe change come with a text change?) is scripts/docs-gate.py.

Exit 0 ok, 1 with one line per finding, 2 when a text or a service could not
be read (not measured is not clean).
"""
import difflib
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DESCR = "docs/descriptions"
GITHUB_API = "https://api.github.com/repos/gmipf/packaging-devtools"
COPR_API = "https://copr.fedorainfracloud.org/api_3/project?ownername=gmipf&projectname=devtools"

# docs/descriptions/<file> -> the live text it is the copy of
LIVE = {
    "github-about.txt": "github",
    "copr-description.md": "copr_description",
    "copr-instructions.md": "copr_instructions",
}

# Texts that must name every package (texts joined with + are read as one).
NAME_RULES = (
    ("README.md",),
    ("docs/how-it-works.md",),
    (f"{DESCR}/copr-description.md", f"{DESCR}/copr-instructions.md"),
)
WORKFLOWS_TEXT = "docs/how-it-works.md"
TOOL_LINE = re.compile(r'^TOOLS\[([^\]]+)\]="([^|"]+)\|', re.M)


class Unmeasured(Exception):
    """A text or a service that could not be read."""


def git_files(root, *paths):
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *paths],
                       capture_output=True, text=True)
    if r.returncode:
        raise Unmeasured(f"git ls-files: {r.stderr.strip()}")
    return [f for f in r.stdout.split("\0") if f]


def read(root, rel):
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError as e:
        raise Unmeasured(f"{rel}: {e.strerror or e}") from e


def packages(root=ROOT):
    """Package name -> where it comes from: its recipe directory, or the packaging.conf line."""
    out = {}
    for f in git_files(root, "fedora"):
        parts = f.split("/")
        if len(parts) >= 3:
            out.setdefault(parts[1], f"fedora/{parts[1]}/ builds it")
    tools = TOOL_LINE.findall(read(root, "packaging.conf"))
    if not tools:
        raise Unmeasured("packaging.conf lists no TOOLS[...] line -- the format moved")
    for short, pkg in tools:
        for name in {short, pkg}:
            out.setdefault(name, f"packaging.conf routes {short}")
    return out


def names(text, name):
    """Is `name` in `text` as a name of its own? `tea` is not in `team` or `tea-cli`."""
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.I) is not None


COMMENT = re.compile(r"<!--.*?-->", re.S)
STARTS = re.compile(r"(?:[-*]|\d+\.)\s")


def units(text):
    """Paragraphs, bullets and headings, each joined into one line. HTML comments drop out."""
    text = COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out, cur = [], []
    for line in text.split("\n"):
        s = line.strip()
        if (not s or s.startswith("#") or STARTS.match(s)) and cur:
            out.append(" ".join(cur))
            cur = []
        if s:
            cur.append(s)
        if s.startswith("#"):
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def mentions(text, word, version):
    """Does one paragraph, bullet or heading carry the distribution's word and its version?"""
    ver = re.compile(rf"(?<![\d.]){re.escape(version)}(?!\d|\.\d)")
    return any(word in u and ver.search(u) for u in units(text))


# --- offline ---------------------------------------------------------------------

def offline(root=ROOT):
    pkgs = packages(root)
    findings = []
    for texts in NAME_RULES:
        body = "\n".join(read(root, t) for t in texts)
        findings += [f"{' + '.join(texts)}: does not name `{p}` ({pkgs[p]})" for p in sorted(pkgs) if not names(body, p)]
    flows = [f for f in git_files(root, ".github/workflows") if f.endswith((".yml", ".yaml"))]
    if not flows:
        raise Unmeasured("no workflow found in .github/workflows -- the layout moved")
    doc = read(root, WORKFLOWS_TEXT)
    findings += [f"{WORKFLOWS_TEXT}: does not name {pathlib.Path(f).name}"
                 for f in sorted(flows) if pathlib.Path(f).name not in doc]
    return findings, f"texts name every package ({len(pkgs)}) and workflow ({len(flows)})"


# --- live ------------------------------------------------------------------------

def get(url, token=None):
    req = urllib.request.Request(url, headers={"User-Agent": "packaging-devtools texts-check"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8")
    except OSError as e:
        raise Unmeasured(f"{url}: {e}") from e


def fetch():
    """Every live text and build target this check compares."""
    got = {}
    try:
        gh = json.loads(get(GITHUB_API, os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")))
        got["github"] = gh.get("description") or ""
        copr = json.loads(get(COPR_API))
        got["copr_description"] = copr["description"] or ""
        got["copr_instructions"] = copr["instructions"] or ""
        got["copr_chroots"] = sorted(copr["chroot_repos"])
    except (ValueError, KeyError, TypeError) as e:
        raise Unmeasured(f"unexpected answer: {e!r}") from e
    if not got["copr_chroots"]:
        raise Unmeasured("COPR listed no chroot")
    return got


def norm(text):
    """Line ends and trailing blanks are not content; the services do not keep them alike."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip("\n").split("\n"))


def targets(chroots):
    """The Fedora releases, the architectures, and every chroot whose form is not understood."""
    rel, arches, unknown = set(), set(), []
    for c in chroots:
        if m := re.fullmatch(r"fedora-(\d+)-(x86_64|aarch64)", c):
            rel.add(m[1])
            arches.add(m[2])
        elif m := re.fullmatch(r"fedora-rawhide-(x86_64|aarch64)", c):
            arches.add(m[1])        # rawhide has no number; it becomes one when it branches
        else:
            unknown.append(c)
    return rel, arches, unknown


def live(got, root=ROOT):
    findings = []
    for fname, key in LIVE.items():
        rel = f"{DESCR}/{fname}"
        want, have = norm(read(root, rel)), norm(got[key])
        if want != have:
            diff = list(difflib.unified_diff(want.split("\n"), have.split("\n"), f"{rel} (git)", f"{key} (live)",
                                             n=1, lineterm=""))
            more = f"\n    ... {len(diff) - 30} more diff lines" if len(diff) > 30 else ""
            findings.append(f"{rel}: the live text differs; publish the git copy, or take a deliberate "
                            f"live edit into git:\n    " + "\n    ".join(diff[:30]) + more)
    rel, arches, unknown = targets(got["copr_chroots"])
    findings += [f"COPR chroot {u}: form not understood -- teach scripts/texts-check.py (targets) what it is"
                 for u in unknown]
    log = read(root, "CHANGELOG.md")
    findings += [f"CHANGELOG.md: does not name Fedora {v} (COPR builds it)"
                 for v in sorted(rel, key=int) if not mentions(log, "Fedora", v)]
    findings += [f"CHANGELOG.md: does not name {a} ({'/'.join(sorted(arches))} are built)"
                 for a in sorted(arches) if a not in log]
    return findings, (f"live descriptions equal {DESCR}/ ({len(LIVE)} texts); every Fedora release COPR "
                      f"builds ({len(rel)}) and architecture ({len(arches)}) is in CHANGELOG.md")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    mode = argv[0] if argv else ""
    try:
        if mode == "offline" and len(argv) == 1:
            findings, ok = offline()
        elif mode == "live" and (len(argv) == 1 or (len(argv) == 3 and argv[1] == "--save")):
            got = fetch()
            if len(argv) == 3:
                out = pathlib.Path(argv[2])
                out.mkdir(parents=True, exist_ok=True)
                for fname, key in LIVE.items():
                    (out / fname).write_text(got[key].rstrip("\n") + "\n", encoding="utf-8")
                print(f"live texts saved to {out}")
            findings, ok = live(got)
        else:
            print("\n\n".join(__doc__.split("\n\n")[1:3]), file=sys.stderr)
            return 2
    except Unmeasured as e:
        print(f"texts-check: NOT MEASURED -- {e}", file=sys.stderr)
        return 2
    for f in findings:
        print(f"texts-check: {f}")
    if findings:
        return 1
    print(f"texts-check: ok -- {ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
