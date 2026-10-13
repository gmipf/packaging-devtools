#!/usr/bin/env python3
"""Every package in .packit.yaml, run through a simulated upstream bump.

Packit takes two things from the actions, not from the spec: the version
(get-current-version) and the archive that becomes Source0 (create-archive).
Both fail silently and late. Without get-current-version, Packit uses the
newest git tag of this repository as the version -- the build is green, the
NEVRA is wrong. A create-archive pattern with a version in it keeps working
until the next bump, and that bump then dies in the SRPM step.

So this runs both actions the way Packit does (a plain subprocess, no shell,
in the package directory) twice: on the package as committed, and on a copy
bumped the way the watchers bump it (the Version: line rewritten, the vendored
Source0 replaced by one of the new version). Each answer must follow the spec.
"""
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.dont_write_bytecode = True
# See test-copr-reconcile.py: from the pre-commit hook, GIT_* would point git at
# the repository being committed. rpmspec does not use git, but nothing may.
for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
ROOT = pathlib.Path(__file__).resolve().parent.parent
BUMPED = "99.98.97"


def run_action(cfg, name, cwd):
    """Packit's own way: each command split into argv, run without a shell."""
    cmds = (cfg.get("actions") or {}).get(name) or []
    if len(cmds) != 1:
        return None, f"{name}: want exactly one command, have {len(cmds)}"
    p = subprocess.run(shlex.split(cmds[0]), cwd=cwd, capture_output=True, text=True)
    if p.returncode:
        return None, f"{name}: exit {p.returncode}: {p.stderr.strip()}"
    return p.stdout.strip(), None


def spec_facts(spec):
    """(Version, [Source basenames]) as rpm reads the spec."""
    out = subprocess.run(["rpmspec", "-P", str(spec)], check=True, capture_output=True, text=True).stdout
    version = re.search(r"^Version:\s*(\S+)", out, re.M).group(1)
    sources = [os.path.basename(s) for s in re.findall(r"^Source\d*:\s*(\S+)", out, re.M)]
    return version, sources


def package_checks(name, p, tmp):
    d = ROOT / p["paths"][0]
    spec = d / p["specfile_path"]
    version, sources = spec_facts(spec)
    checks = {}

    got, err = run_action(p, "get-current-version", d)
    checks["get-current-version reads the spec"] = (got == version, err or f"{got!r}, spec says {version!r}")
    got, err = run_action(p, "create-archive", d)
    checks["create-archive names Source0, which is here"] = (
        got == sources[0] and (d / got).is_file(), err or f"{got!r}, Source0 is {sources[0]!r}")

    # The tree a watcher leaves: the same files, minus the old Source0, plus a
    # new one, and the Version: line rewritten with the watcher's own pattern.
    b = tmp / name
    b.mkdir()
    for f in d.iterdir():
        if f.is_file() and f.name != sources[0]:
            shutil.copy(f, b / f.name)
    text = spec.read_text()
    bumped = re.sub(r"^Version:.*$", f"Version:        {BUMPED}", text, count=1, flags=re.M)
    if bumped == text:
        return {"the bump applies": (False, "no Version: line to rewrite")}
    (b / spec.name).write_text(bumped)
    bversion, bsources = spec_facts(b / spec.name)
    if bversion != BUMPED or bsources[0] == sources[0]:
        return {"the bump applies": (False, f"Version {bversion!r}, Source0 {bsources[0]!r}")}
    (b / bsources[0]).write_bytes(b"")

    got, err = run_action(p, "get-current-version", b)
    checks[f"after a bump to {BUMPED}: get-current-version follows"] = (
        got == BUMPED, err or f"{got!r}")
    got, err = run_action(p, "create-archive", b)
    checks[f"after a bump to {BUMPED}: create-archive finds the new Source0"] = (
        got == bsources[0], err or f"{got!r}, Source0 is {bsources[0]!r}")
    return checks


def main():
    cfg = yaml.safe_load((ROOT / ".packit.yaml").read_text())
    packages = cfg.get("packages") or {}
    fails = total = 0
    if not packages:
        print("FAIL  no packages in .packit.yaml -- this would pass on nothing")
        sys.exit(1)
    with tempfile.TemporaryDirectory() as tmp:
        for name, p in sorted(packages.items()):
            for label, (ok, detail) in package_checks(name, p, pathlib.Path(tmp)).items():
                total += 1
                fails += not ok
                print(f"{'PASS' if ok else 'FAIL'}  {name}: {label}" + ("" if ok else f"  [{detail}]"))
    print(f"\n{total - fails}/{total} passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
