#!/usr/bin/env python3
"""Every upstream-release watcher, run as written against a fake upstream.

The watchers download a release binary and commit it into packages that other
people install. What they refuse matters as much as what they do, and neither
can be seen from a green daily run that found no new release. So this takes
the `run:` block of each watch-*.yml exactly as written and runs it the way
GitHub does (bash -eo pipefail), in a small copy of the package whose origin
is a local bare repository, with curl and gh replaced by stubs that serve a
fake release -- only at the real upstream's URLs, so a watcher asking the
wrong project gets a 404.

A good release must land on main (spec bumped, Release reset, changelog,
binary swapped, marker moved) and on the trigger branch. A wrong checksum, a
missing checksum, a payload that is not an ELF, a missing download and an
unexpected tag must each stop the watcher before anything is pushed.
"""
import hashlib
import io
import lzma
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

import yaml

sys.dont_write_bytecode = True
# See test-copr-reconcile.py: from the pre-commit hook, GIT_* would point the
# git commands here at the repository being committed.
for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
ROOT = pathlib.Path(__file__).resolve().parent.parent
TAG, V = "v99.98.97", "99.98.97"
ELF = b"\x7fELF" + b"\0" * 60

# Where each tool really comes from -- written down here independently of the
# watchers, so that a watcher pointing at the wrong project fails.
UPSTREAM = {
    "syft": ("github", "anchore/syft"),
    "grype": ("github", "anchore/grype"),
    "grant": ("github", "anchore/grant"),
    "tea": ("gitea", "gitea/tea"),
}

CURL = r"""#!/bin/bash
url= out=
while [ $# -gt 0 ]; do
    case $1 in -o) out=$2; shift 2 ;; http://*|https://*) url=$1; shift ;; *) shift ;; esac
done
echo "curl $url" >> "$STUB_ROOT/calls"
f=$STUB_ROOT/files/${url#*://}
[ -f "$f" ] || { echo "curl: (22) The requested URL returned error: 404 ($url)" >&2; exit 22; }
if [ -n "$out" ]; then cp "$f" "$out"; else cat "$f"; fi
"""
GH = r"""#!/bin/bash
echo "gh $*" >> "$STUB_ROOT/calls"
repo=
while [ $# -gt 0 ]; do case $1 in --repo) repo=$2; shift 2 ;; *) shift ;; esac; done
f=$STUB_ROOT/gh/$repo
[ -f "$f" ] || { echo "release not found ($repo)" >&2; exit 1; }
cat "$f"
"""


def sh(*args, cwd, env=None, check=True):
    p = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode:
        sys.exit(f"test-watchers: {' '.join(map(str, args))} failed:\n{p.stdout}")
    return p.stdout.strip()


def git(cwd, *args):
    return sh("git", "-c", "user.name=t", "-c", "user.email=t@t", *args, cwd=cwd)


def run_block(tool):
    wf = yaml.safe_load((ROOT / f".github/workflows/watch-{tool}-releases.yml").read_text())
    runs = [s["run"] for s in wf["jobs"]["watch"]["steps"] if "run" in s]
    if len(runs) != 1 or "${{" in runs[0]:
        sys.exit(f"watch-{tool}-releases.yml: want one run: block without ${{{{ }}}}, the layout moved")
    return runs[0]


def source0(spec):
    out = sh("rpmspec", "-P", str(spec), cwd=spec.parent)
    return os.path.basename(re.search(r"^Source0:\s*(\S+)", out, re.M).group(1))


def nevr(spec):
    return sh("rpmspec", "-q", "--srpm", "--undefine", "dist", "--qf", "%{version}-%{release}\n", str(spec),
              cwd=spec.parent).splitlines()[0]


def fake_release(tool, root, *, tag=TAG, payload=ELF, member=None, sums="good", asset=True):
    """Lay out what the upstream would serve. sums: good | wrong | missing."""
    kind, project = UPSTREAM[tool]
    files = root / "files"
    if kind == "github":
        (root / "gh" / project).parent.mkdir(parents=True, exist_ok=True)
        (root / "gh" / project).write_text(tag + "\n")
        name = f"{tool}_{V}_linux_amd64.tar.gz"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for n, data in ((member or tool, payload), ("LICENSE", b"license\n")):
                info = tarfile.TarInfo(n)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        blob = buf.getvalue()
        base = files / f"github.com/{project}/releases/download/{tag}"
        sumfile, sumline = base / f"{tool}_{V}_checksums.txt", f"  {name}\n"
    else:
        api = files / f"gitea.com/api/v1/repos/{project}/releases"
        api.mkdir(parents=True)
        (api / "latest").write_text(f'{{"tag_name": "{tag}"}}\n')
        name = f"{tool}-{V}-linux-amd64.xz"
        blob = lzma.compress(payload, format=lzma.FORMAT_XZ)
        base = files / f"gitea.com/{project}/releases/download/{tag}"
        sumfile, sumline = base / f"{name}.sha256", f"  {name}\n"
    base.mkdir(parents=True, exist_ok=True)
    if asset:
        (base / name).write_bytes(blob)
    digest = hashlib.sha256(blob if sums == "good" else blob + b"tampered").hexdigest()
    if sums != "missing":
        other = "0" * 64 + f"  {tool}_{V}_darwin_amd64.tar.gz\n"
        sumfile.write_text((other if kind == "github" else "") + digest + sumline)
    return name, blob


def setup(tool, w):
    """A repository holding just this tool's package dir and push-retry.sh,
    with the vendored binary swapped for a small stand-in of the same name."""
    src = ROOT / f"fedora/{tool}"
    spec = src / f"{tool}.spec"
    old = source0(spec)
    work, remote = w / "work", w / "remote.git"
    (work / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/push-retry.sh", work / "scripts/push-retry.sh")
    shutil.copytree(src, work / f"fedora/{tool}", ignore=shutil.ignore_patterns(old))
    (work / f"fedora/{tool}" / old).write_bytes(b"the old vendored binary\n")
    # Every spec sits at Release 1 today, where a watcher that forgot to reset
    # it would look exactly like one that did. Start from a later iteration.
    s = work / f"fedora/{tool}/{tool}.spec"
    text = s.read_text()
    later = re.sub(r"^Release:.*$", "Release:        7%{?dist}", text, count=1, flags=re.M)
    if later == text:
        sys.exit(f"{s.name}: no Release: line, the layout moved")
    s.write_text(later)
    git(w, "init", "-q", "--bare", "-b", "main", str(remote))
    git(work, "init", "-q", "-b", "main")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "main")
    git(work, "branch", "-q", "--set-upstream-to=origin/main")
    stubs = w / "bin"
    stubs.mkdir()
    for n, text in (("curl", CURL), ("gh", GH)):
        (stubs / n).write_text(text)
        (stubs / n).chmod(0o755)
    return work, remote, old


def refs(remote):
    return git(remote, "for-each-ref", "--format=%(refname) %(objectname)")


def run_watcher(tool, w, work):
    script = w / "run.sh"
    script.write_text(run_block(tool))
    env = dict(os.environ, PATH=f"{w / 'bin'}{os.pathsep}{os.environ['PATH']}", STUB_ROOT=str(w / "up"),
               GH_TOKEN="stub", HOME=str(w))
    p = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)], cwd=work, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout


def good_release(tool, w):
    work, remote, old = setup(tool, w)
    name, blob = fake_release(tool, w / "up")
    rc, out = run_watcher(tool, w, work)
    if rc:
        return {"a new release runs through": (False, out[-1500:])}
    git(work, "fetch", "-q", "origin")
    check = w / "check"
    git(w, "clone", "-q", str(remote), str(check))
    d = check / f"fedora/{tool}"
    spec = d / f"{tool}.spec"
    text = spec.read_text()
    trigger = f"origin/build-{tool}"
    main = git(check, "rev-parse", "origin/main")
    pushed = subprocess.run(["git", "rev-parse", "--verify", "-q", trigger], cwd=check,
                            capture_output=True).returncode == 0
    return {
        "a new release runs through": (True, ""),
        "main: spec at the new version, Release reset to 1": (nevr(spec) == f"{V}-1", nevr(spec)),
        "main: changelog entry for it on top": (
            re.search(rf"%changelog\n\* \w{{3}} \w{{3}} \d{{2}} \d{{4}} .+ - {re.escape(V)}-1\n", text) is not None,
            text[text.find("%changelog"):][:200]),
        "main: the downloaded binary is vendored, byte for byte": (
            (d / name).is_file() and (d / name).read_bytes() == blob, str(sorted(p.name for p in d.iterdir()))),
        "main: the old binary is gone": (not (d / old).exists(), old),
        "main: the spec's Source0 is the vendored file": (source0(spec) == name, source0(spec)),
        "main: .upstream-tag moved": ((d / ".upstream-tag").read_text().strip() == TAG,
                                      (d / ".upstream-tag").read_text()),
        "trigger: build branch is main plus its landing page": (
            pushed
            and git(check, "rev-parse", f"{trigger}~1") == main
            and git(check, "diff", "--name-only", main, trigger) == "README.md"
            and f"build-{tool}" in git(check, "show", f"{trigger}:README.md"),
            git(check, "log", "--oneline", "-3", trigger) if pushed else f"{trigger} was never pushed"),
    }


def refusal(tool, w, label, expect, **release):
    work, remote, _ = setup(tool, w)
    fake_release(tool, w / "up", **release)
    before = refs(remote)
    rc, out = run_watcher(tool, w, work)
    ok = rc != 0 and refs(remote) == before and (expect is None or re.search(expect, out) is not None)
    return {f"refuses {label}, pushes nothing": (ok, f"exit {rc}, wanted /{expect}/:\n{out[-1200:]}")}


def unchanged(tool, w):
    work, remote, _ = setup(tool, w)
    fake_release(tool, w / "up", tag=(work / f"fedora/{tool}/.upstream-tag").read_text().strip())
    before = refs(remote)
    rc, out = run_watcher(tool, w, work)
    return {"same tag again: nothing to do, nothing pushed": (rc == 0 and refs(remote) == before, out[-800:])}


def cases(tool):
    yield good_release
    yield unchanged
    yield lambda t, w: refusal(t, w, "a checksum mismatch", r"SHA256 mismatch", sums="wrong")
    yield lambda t, w: refusal(t, w, "a release without a checksum", None, sums="missing")
    yield lambda t, w: refusal(t, w, "a payload that is not an ELF", r"not an ELF", payload=b"#!/bin/sh\necho hi\n")
    yield lambda t, w: refusal(t, w, "a missing download", r"404", asset=False)
    yield lambda t, w: refusal(t, w, "an unexpected tag", r"Unexpected .*tag", tag="nightly-2026")
    if UPSTREAM[tool][0] == "github":
        yield lambda t, w: refusal(t, w, "an archive without the binary", r"not a valid gzip tarball containing",
                                   member="README")


def main():
    found = sorted(p.name[len("watch-"):-len("-releases.yml")] for p in (ROOT / ".github/workflows").glob("watch-*-releases.yml"))
    fails = total = 0

    def report(ok, label, detail=""):
        nonlocal fails, total
        total += 1
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else "\n" + "\n".join(
            "      " + line for line in detail.splitlines())))

    report(found == sorted(UPSTREAM), f"a known upstream for every watcher ({', '.join(found)})",
           f"watchers {found}, upstreams known here {sorted(UPSTREAM)}")
    for tool in found:
        if tool not in UPSTREAM:
            continue
        for case in cases(tool):
            with tempfile.TemporaryDirectory() as w:
                for label, (ok, detail) in case(tool, pathlib.Path(w)).items():
                    report(ok, f"{tool}: {label}", detail)
    print(f"\n{total - fails}/{total} passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
