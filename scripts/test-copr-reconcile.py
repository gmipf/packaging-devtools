#!/usr/bin/env python3
"""Decision tests for copr-reconcile.py -- run before every reconcile in CI.

Every state judge() can return, with COPR and git replaced by fixtures (judge()
itself is the code under test, unmodified), the .packit.yaml parsing in jobs(),
the real .packit.yaml against packaging.conf, plus heal() for real against a
throwaway bare repository. copr-reconcile.yml runs this first: a reconciler
whose own decisions are broken must not push anything.

Set REC=<path> to run the same tests against another copy of the script (that
is how each case was seen to go red against a deliberately broken copy).
"""
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

# No scripts/__pycache__: copr-reconcile.yml runs this right before --heal, and
# a stray file there would make the working tree look dirty to it.
sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rec", os.environ.get("REC", HERE / "copr-reconcile.py"))
rec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)

NOW = 2_000_000_000
H = 3600
WANT = "1.2-3"


def build(i, state, version, submitted):
    return {"id": i, "state": state, "submitted_on": submitted, "source_package": {"version": version}}


def judge(*, have=None, builds=(), changed=NOW - 5 * H, tip_age=10 * H,
          tip_subject="trigger: pkg", same_tree=False, project="devtools", asked=None):
    def fake_copr(path):
        if asked is not None:
            asked.append(path)
        if path.startswith("package?"):
            last = {"id": 99, "source_package": {"version": have}} if have else None
            return {"builds": {"latest_succeeded": last}}
        if path.startswith("build/list?"):
            return {"items": list(builds)}
        raise AssertionError(path)

    def fake_git(*a):
        if a[:3] == ("log", "-1", "--format=%ct"):
            return str(changed)
        if a[:3] == ("log", "-1", "--format=%ct%n%s"):
            return f"{NOW - tip_age}\n{tip_subject}"
        if a[0] == "rev-parse":
            return "TREE-MAIN" if a[1].startswith(rec.REF) or same_tree else "TREE-OLD"
        raise AssertionError(a)

    saved = rec.copr, rec.git, rec.spec_nevra
    rec.copr, rec.git, rec.spec_nevra = fake_copr, fake_git, lambda s, t: ("pkg", WANT)
    try:
        return rec.judge("pkg", "build-pkg", "fedora/pkg", "fedora/pkg/pkg.spec",
                         "gmipf", project, "/nonexistent", NOW)
    finally:
        rec.copr, rec.git, rec.spec_nevra = saved


CASES = [
    ("copr has main's NEVRA", dict(have=WANT), "ok"),
    ("copr ahead of main (release)", dict(have="1.2-4"), "ERROR"),
    ("copr ahead of main (version)", dict(have="1.3-1"), "ERROR"),
    ("a build is running", dict(have="1.2-2", builds=[build(5, "running", None, NOW - 60)]), "running"),
    ("a build is pending", dict(have="1.2-2", builds=[build(5, "pending", None, NOW - 60)]), "running"),
    ("a build of main's NEVRA failed", dict(have="1.2-2", builds=[build(5, "failed", WANT, NOW - 2 * H)]), "ERROR"),
    ("a build of main's NEVRA was cancelled",
     dict(have="1.2-2", builds=[build(5, "canceled", WANT, NOW - 2 * H)]), "ERROR"),
    ("SRPM-less failure after the change", dict(have="1.2-2", builds=[build(5, "failed", None, NOW - 2 * H)]), "ERROR"),
    ("SRPM-less failure before the change is not ours",
     dict(have="1.2-2", builds=[build(5, "failed", None, NOW - 9 * H)]), "heal"),
    ("failure of an older NEVRA is not ours",
     dict(have="1.2-2", builds=[build(5, "failed", "1.2-1", NOW - 2 * H)]), "heal"),
    ("main changed 10 min ago", dict(have="1.2-2", changed=NOW - 600), "fresh"),
    ("lost trigger", dict(have="1.2-2"), "heal"),
    ("lost trigger of a package with no success yet", dict(have=None), "heal"),
    ("trigger got this tree 10 min ago", dict(have="1.2-2", same_tree=True, tip_age=600), "fresh"),
    ("our own re-push 10 min ago", dict(have="1.2-2", same_tree=True, tip_age=600, tip_subject="reconcile: pkg"), "fresh"),
    ("our own re-push long ago, still no build", dict(have="1.2-2", same_tree=True, tip_subject="reconcile: pkg"), "ERROR"),
    ("watcher push long ago, Packit dropped it", dict(have="1.2-2", same_tree=True), "heal"),
    ("our re-push was of an older tree", dict(have="1.2-2", tip_subject="reconcile: pkg"), "heal"),
]


def routing_checks():
    """judge() asks the job's own COPR project, never a fixed one."""
    asked = []
    judge(have=WANT, project="other-proj", asked=asked)
    return {"every COPR query names the job's owner/project":
            bool(asked) and all("ownername=gmipf&projectname=other-proj&" in p for p in asked)}


JOB = """
packages:
  pkg: {paths: [fedora/pkg/], specfile_path: pkg.spec}
  two: {paths: [fedora/two/], specfile_path: two.spec}
jobs:
  - {job: copr_build, trigger: commit, branch: %s, packages: %s, owner: %s, project: devtools}
  - {job: copr_build, trigger: pull_request, packages: [pkg]}
"""


def raises(text):
    try:
        rec.jobs(text)
    except (SystemExit, ValueError):
        return True
    return False


def jobs_checks():
    good = rec.jobs(JOB % ("^build-pkg$", "[pkg]", "gmipf"))
    return {
        "anchored job parsed, non-commit job skipped":
            good == [("pkg", "build-pkg", "fedora/pkg", "fedora/pkg/pkg.spec", "gmipf", "devtools")],
        "unanchored branch refused": raises(JOB % ("build-pkg", "[pkg]", "gmipf")),
        "half-anchored branch refused": raises(JOB % ("^build-pkg", "[pkg]", "gmipf")),
        "regex in branch refused": raises(JOB % ("^build-.*$", "[pkg]", "gmipf")),
        "job without owner refused": raises(JOB % ("^build-pkg$", "[pkg]", "''")),
        "two packages on one trigger refused": raises(JOB % ("^build-pkg$", "[pkg, two]", "gmipf")),
        "no commit job at all refused": raises("packages: {}\njobs: []\n"),
    }


def repo_checks():
    """The real .packit.yaml routes exactly like packaging.conf (what build-tool.sh pushes)."""
    root = HERE.parent
    conf = (root / "packaging.conf").read_text()
    owner = re.search(r"^COPR_OWNER=(\S+)", conf, re.M).group(1)
    default = re.search(r"^COPR_PROJECT=(\S+)", conf, re.M).group(1)
    tools = {}
    for entry in re.findall(r'^TOOLS\[[^]]+\]="([^"]+)"', conf, re.M):
        f = entry.split("|")
        tools[f[0]] = (f[2], f[1], owner, f[3] if len(f) > 3 and f[3] else default)
    got = {pkg: (branch, spec, o, p)
           for pkg, branch, _, spec, o, p in rec.jobs((root / ".packit.yaml").read_text())}
    return {
        f"packaging.conf and .packit.yaml route the same {len(tools)} tools": bool(tools) and got == tools,
    }


def heal_checks(w):
    """heal() against a local bare remote: what lands on the trigger branch."""
    def sh(*a, cwd=None):
        return subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

    work = w / "work"
    sh("git", "init", "-q", "--bare", "-b", "main", str(w / "remote.git"))
    sh("git", "clone", "-q", str(w / "remote.git"), str(work))

    def g(*a):
        return sh("git", "-c", "user.name=t", "-c", "user.email=t@t", *a, cwd=work)

    (work / "scripts").mkdir()
    shutil.copy(HERE / "push-retry.sh", work / "scripts/push-retry.sh")
    (work / "fedora/pkg").mkdir(parents=True)
    (work / "fedora/pkg/pkg.spec").write_text("v1\n")
    (work / "README.md").write_text("main readme\n")
    g("add", "-A")
    g("commit", "-q", "-m", "v1")
    g("push", "-q", "origin", "main")
    (work / "README.md").write_text("# build-pkg landing page\n")
    g("commit", "-q", "-am", "trigger: pkg")
    g("push", "-q", "origin", "HEAD:build-pkg")
    g("reset", "-q", "--hard", "origin/main")
    (work / "fedora/pkg/pkg.spec").write_text("v2\n")
    g("commit", "-q", "-am", "bump to v2")
    g("push", "-q", "origin", "main")
    g("fetch", "-q", "origin")
    before = g("rev-parse", "HEAD")
    cwd = os.getcwd()
    os.chdir(work)
    try:
        pushed = rec.heal("pkg", "build-pkg", WANT)
    finally:
        os.chdir(cwd)
    g("fetch", "-q", "origin")
    return {
        "push succeeded": pushed,
        "back on the starting commit": g("rev-parse", "HEAD") == before,
        "temporary branch removed": "reconcile-tmp" not in g("branch", "--list"),
        "trigger carries main's spec": g("show", "origin/build-pkg:fedora/pkg/pkg.spec") == "v2",
        "trigger kept its own README": g("show", "origin/build-pkg:README.md") == "# build-pkg landing page",
        "subject marks our re-push": g("log", "-1", "--format=%s", "origin/build-pkg").startswith(rec.HEAL_SUBJECT),
        "main untouched": g("rev-parse", "origin/main") == before,
    }


def main():
    fails = total = 0

    def report(ok, label):
        nonlocal fails, total
        total += 1
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}")

    for name, kw, expected in CASES:
        state, detail, _ = judge(**kw)
        report(state == expected, f"{expected:<7} got {state:<7} {name}  [{detail}]")
    for group, checks in (("routing", routing_checks()), ("jobs()", jobs_checks()), ("repo", repo_checks())):
        for name, ok in checks.items():
            report(ok, f"{group}: {name}")
    with tempfile.TemporaryDirectory() as w:
        for name, ok in heal_checks(pathlib.Path(w)).items():
            report(ok, f"heal(): {name}")
    print(f"\n{total - fails}/{total} passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
