#!/usr/bin/env python3
"""selftest.py -- every check of this repository, seen red.

A check that cannot fail looks exactly like a check that passes. So each one
is run here against a defect planted for it, and must turn red for that
defect's own reason. A check that is edited, refactored or bypassed until it
no longer catches its defect turns this red instead of staying silently green.

    scripts/selftest.py             lint.sh, the test suites and the hook
                                    (CI: check-repo.yml, job lint)
    scripts/selftest.py --rpmbuild  every spec's %check (needs the build deps:
                                    check-repo.yml, job rpmbuild)

Works on a throwaway copy of the tracked files (staged and unstaged edits
included); the repository itself is never touched. The copy must be green
before any defect is planted, or nothing here is measured.
"""
import concurrent.futures
import os
import pathlib
import queue
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
# The hook tests below commit for real; inherited GIT_* would aim that at
# whatever repository called us.
for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
ROOT = pathlib.Path(__file__).resolve().parent.parent
BUMPED = "99.98.97"
JOBS = 4                      # copies linting in parallel; each run is ~20 s


class DoesNotApply(Exception):
    pass


def sh(*args, cwd, check=True, env=None):
    p = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode:
        sys.exit(f"selftest: {' '.join(args)} failed:\n{p.stdout}")
    return p


def git(w, *args, check=True):
    return sh("git", "-c", "user.name=selftest", "-c", "user.email=selftest@invalid", *args, cwd=w, check=check)


def copy_tree(dst):
    """The tracked files as they are on disk, in a fresh repository of their own."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    for rel in filter(None, out.split("\0")):
        src = ROOT / rel
        if src.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / rel)          # keeps the mode: +x matters here
    git(dst, "init", "-q", "-b", "main")
    git(dst, "add", "-A")
    git(dst, "commit", "-q", "-m", "selftest base")


def reset(w):
    git(w, "reset", "-q", "--hard")
    git(w, "clean", "-fdqx")


# --- ways to plant a defect; each refuses to report success without effect ----
def replace(path, old, new):
    def plant(w):
        f = w / path
        s = f.read_text()
        if old not in s:
            raise DoesNotApply(f"{path}: {old!r} not found")
        f.write_text(s.replace(old, new, 1))
    return plant


def append(path, text):
    def plant(w):
        with open(w / path, "a", newline="") as f:
            f.write(text)
    return plant


def drop_final_newline(path):
    def plant(w):
        f = w / path
        b = f.read_bytes()
        if not b.endswith(b"\n"):
            raise DoesNotApply(f"{path} has no final newline to drop")
        f.write_bytes(b[:-1])
    return plant


def add_tracked(path, text):
    def plant(w):
        (w / path).write_text(text)
        git(w, "add", path)
    return plant


def spec_version(w, tool):
    return re.search(r"^Version:\s*(\S+)", (w / f"fedora/{tool}/{tool}.spec").read_text(), re.M).group(1)


def gcv(tool):
    return f"rpmspec -q --queryformat '%{{version}}\\n' {tool}.spec | head -1"


def pin_create_archive(w):
    v = spec_version(w, "syft")
    replace(".packit.yaml", "ls -1 syft_*_linux_amd64.tar.gz", f"ls -1 syft_{v}_linux_amd64.tar.gz")(w)


def hardcode_version(w):
    replace(".packit.yaml", gcv("tea"), f"echo {spec_version(w, 'tea')}")(w)


REC = "scripts/copr-reconcile.py"
LINT = [
    # lint.sh's own rules
    ("whitespace: trailing blank", append("README.md", "x  \n"), r"trailing whitespace:"),
    ("whitespace: CR line ending", append("README.md", "y\r\n"), r"CR line endings:"),
    ("whitespace: no final newline", drop_final_newline("LICENSE"), r"no newline at end of: ?LICENSE"),
    ("shellcheck: a *.sh file", replace("scripts/push-retry.sh", "\nset ", "\ncd /nonexistent\nset "),
     r"shellcheck found"),
    ("shellcheck: a file found by its shebang only",
     replace(".githooks/pre-commit", "\nroot=", "\ncd /nonexistent\nroot="), r"shellcheck found"),
    ("ruff: undefined name", append(REC, "\nundefined_name_x()\n"), r"ruff found"),
    ("yamllint: duplicate key", replace(".packit.yaml", "\nsrpm_build_deps:",
                                        "\nissue_repository: https://example.invalid\nsrpm_build_deps:"),
     r"yamllint found"),
    ("actionlint: unknown context", replace(".github/workflows/copr-reconcile.yml",
                                            "github.event_name", "github.evnt_name"), r"actionlint found"),
    ("packit validate: invalid trigger", replace(".packit.yaml", "trigger: commit", "trigger: comit"),
     r"packit validate:"),
    ("rpmlint: a finding not declared", replace("fedora/tea/tea.spec", "\nName:", "\n# see %doc\nName:"),
     r"not on the EXPECTED list"),
    ("rpmlint: a declared finding that no longer occurs",
     replace("scripts/lint.sh", 'EXPECTED="\n', 'EXPECTED="\ntea.spec W invalid-url\n'), r"no longer reports"),
    ("coverage: a manpage no rule reads", add_tracked("fedora/tea/tea.1", ".TH X 1\n"),
     r"no lint rule for these yet"),
    # .packit.yaml: Packit must leave the NEVRA alone, and survive a bump
    ("NEVRA: update_release true", replace(".packit.yaml", "packages: [syft]\n    update_release: false",
                                           "packages: [syft]\n    update_release: true"),
     r"update_release is not false"),
    ("NEVRA: update_release missing (Packit's default is true)",
     replace(".packit.yaml", "packages: [grype]\n    update_release: false\n", "packages: [grype]\n"),
     r"update_release is not false"),
    ("NEVRA: version_suffix", replace(".packit.yaml", "\nsrpm_build_deps:",
                                      '\nversion_suffix: "^{PACKIT_PROJECT_SNAPSHOTID}"\nsrpm_build_deps:'),
     r"version_suffix is set"),
    ("NEVRA: no get-current-version (the version would come from a git tag)",
     replace(".packit.yaml", f'      get-current-version:\n        - bash -c "{gcv("grant")}"\n', ""),
     r"has no get-current-version"),
    ("bump: get-current-version hard-codes today's version", hardcode_version,
     rf"FAIL  tea: after a bump to {BUMPED}: get-current-version follows"),
    ("bump: create-archive pins today's version", pin_create_archive,
     rf"FAIL  syft: after a bump to {BUMPED}: create-archive finds the new Source0"),
    ("bump: create-archive matches the wrong file", replace(".packit.yaml", "ls -1 tea-*-linux-amd64.xz", "ls -1 *"),
     r"FAIL  tea: create-archive names Source0"),
    ("routing: unanchored branch", replace(".packit.yaml", "branch: ^build-grype$", "branch: build-grype"),
     r"unexpected branch pattern"),
    ("routing: a tool only in packaging.conf", append("packaging.conf", 'TOOLS[foo]="foo|fedora/foo/foo.spec|build-foo"\n'),
     r"FAIL  repo: packaging.conf and .packit.yaml route the same"),
    # the watchers, weakened one at a time (test-watchers.py runs them for real)
    ("watcher: checksum read but not enforced",
     replace(".github/workflows/watch-syft-releases.yml", 'if [ "$EXPECT" != "$ACTUAL" ]; then', "if false; then"),
     r"FAIL  syft: refuses a checksum mismatch"),
    ("watcher: per-asset checksum not enforced",
     replace(".github/workflows/watch-tea-releases.yml", 'if [ -z "$EXPECT" ] || [ "$EXPECT" != "$ACTUAL" ]; then',
             "if false; then"), r"FAIL  tea: refuses a checksum mismatch"),
    ("watcher: payload not checked for an ELF",
     replace(".github/workflows/watch-grant-releases.yml", 'if [ "$MAGIC" != "7f454c46" ]; then', "if false; then"),
     r"FAIL  grant: refuses a payload that is not an ELF"),
    ("watcher: asks the wrong upstream project",
     replace(".github/workflows/watch-grype-releases.yml", "--repo anchore/grype", "--repo anchore/syft"),
     r"FAIL  grype: a new release runs through"),
    ("watcher: Release not reset on a new version",
     replace(".github/workflows/watch-tea-releases.yml",
             '          sed -i "s/^Release:.*/Release:        1%{?dist}/" "$SPEC"\n', ""),
     r"FAIL  tea: main: spec at the new version, Release reset to 1"),
    ("watcher: trigger branch not pushed",
     replace(".github/workflows/watch-syft-releases.yml",
             "          bash scripts/push-retry.sh -f origin trigger-tmp:build-syft\n", ""),
     r"FAIL  syft: trigger: build branch is main plus its landing page"),
    # the reconciler's decisions, broken one at a time
    ("reconcile: no grace period", replace(REC, "GRACE = 3600", "GRACE = 0"), r"FAIL  fresh"),
    ("reconcile: a failed build of main's NEVRA ignored", replace(REC, "    if tried:\n", "    if False and tried:\n"),
     r"FAIL  ERROR .*failed"),
    ("reconcile: COPR project hard-coded",
     replace(REC, 'where = f"ownername={owner}&projectname={project}&', 'where = f"ownername={owner}&projectname=devtools&'),
     r"FAIL  routing: every COPR query names"),
    ("reconcile: unanchored branch accepted",
     replace(REC, 'branch = pattern[1:-1] if pattern.startswith("^") and pattern.endswith("$") else ""',
             'branch = pattern.strip("^$")'), r"FAIL  jobs\(\): unanchored branch refused"),
    ("reconcile: its own fruitless re-push repeated",
     replace(REC, "        if tip_subject.startswith(HEAL_SUBJECT):\n", "        if False:\n"),
     r"FAIL  ERROR .*our own re-push long ago"),
    ("reconcile: job without owner accepted", replace(REC, "        if not owner or not project:\n", "        if False:\n"),
     r"FAIL  jobs\(\): job without owner refused"),
    ("reconcile: update_release not checked",
     replace(REC, 'in layers if "update_release" in d), True) is not False:', 'in layers if "update_release" in d), True) is None:'),
     r"FAIL  jobs\(\): update_release missing"),
    ("reconcile: suffixes not checked", replace(REC, "            if any(d.get(key) is not None for d in layers):\n",
                                                "            if False:\n"),
     r"FAIL  jobs\(\): version_suffix at the top level refused"),
    ("reconcile: get-current-version not checked",
     replace(REC, '        if not (p.get("actions") or {}).get("get-current-version"):\n', "        if False:\n"),
     r"FAIL  jobs\(\): package without get-current-version refused"),
]


def lint(w, path=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return sh("bash", "scripts/lint.sh", cwd=w, check=False, env=env)


def one_lint_mutant(w, label, plant, expect):
    try:
        plant(w)
    except DoesNotApply as e:
        return False, label, f"the defect does not apply any more ({e}) -- update this selftest"
    if not git(w, "status", "--porcelain").stdout.strip():
        return False, label, "planting the defect changed nothing"
    p = lint(w)
    return (p.returncode != 0 and re.search(expect, p.stdout) is not None, label,
            f"exit {p.returncode}, wanted /{expect}/:\n" + tail(p.stdout))


def run_lint_mutants(copies, verdict):
    """Each defect in a copy of its own at a time; the copies work in parallel."""
    free = queue.Queue()
    for w in copies:
        free.put(w)

    def task(mutant):
        w = free.get()
        try:
            return one_lint_mutant(w, *mutant)
        finally:
            reset(w)
            free.put(w)

    with concurrent.futures.ThreadPoolExecutor(len(copies)) as ex:
        for result in ex.map(task, LINT):
            verdict(*result)


def tail(out, n=15):
    return "\n".join("      " + line for line in out.strip().splitlines()[-n:])


def run_special(w, verdict):
    # CI mode: a tool that is not installed is red, never skipped.
    tool = shutil.which("actionlint")
    if not tool:
        verdict(False, "CI mode: a missing linter fails the run", "actionlint is not installed, cannot measure")
    else:
        d = os.path.dirname(tool)
        path = os.pathsep.join(x for x in os.environ["PATH"].split(os.pathsep) if os.path.realpath(x) != os.path.realpath(d))
        if shutil.which("actionlint", path=path):
            verdict(False, "CI mode: a missing linter fails the run", "could not take actionlint off PATH")
        else:
            p = lint(w, path)
            verdict(p.returncode != 0 and "actionlint is not installed -- not measured is not clean" in p.stdout,
                    "CI mode: a missing linter fails the run", tail(p.stdout))

    git(w, "config", "core.hooksPath", ".githooks")
    # The hook refuses a commit that lint.sh finds fault with.
    before = git(w, "rev-parse", "HEAD").stdout
    append("README.md", "z \n")(w)
    git(w, "add", "README.md")
    p = git(w, "commit", "-q", "-m", "red", check=False)
    verdict(p.returncode != 0 and git(w, "rev-parse", "HEAD").stdout == before,
            "hook: a commit with a lint finding is refused", tail(p.stdout))
    reset(w)

    # `git commit -a` hands the hook an absolute GIT_INDEX_FILE. The suites run
    # git in throwaway repositories; if they inherited it, their files would be
    # staged into this commit. Green as committed, red without their GIT_* reset.
    for label, plant, want_clean in (
        ("hook: commit -a carries only its own change", None, True),
        ("hook: ... and without the suites' GIT_* reset it does not",
         replace("scripts/test-copr-reconcile.py",
                 'for k in [k for k in os.environ if k.startswith("GIT_")]:\n    del os.environ[k]\n', ""), False),
    ):
        expected = ["README.md"]
        if plant:
            try:
                plant(w)
            except DoesNotApply as e:
                verdict(False, label, f"the defect does not apply any more ({e})")
                reset(w)
                continue
            expected.append("scripts/test-copr-reconcile.py")
        append("README.md", "one more line\n")(w)
        before = git(w, "rev-parse", "HEAD").stdout.strip()
        p = git(w, "commit", "-q", "-a", "-m", "clean change", check=False)
        if p.returncode:
            clean, how = False, "the commit was refused:\n" + tail(p.stdout)
        else:
            changed = sorted(git(w, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").stdout.split())
            clean, how = changed == sorted(expected), f"the commit changed {changed}"
        # Either way of not being clean (stray files committed, or the suite
        # breaking and the hook refusing) is the red this case asks for.
        verdict(clean == want_clean, label, how)
        if not want_clean:
            print("      (how: " + how.splitlines()[0] + ")")
        git(w, "reset", "-q", "--hard", before)
        reset(w)
    git(w, "config", "--unset", "core.hooksPath")


def run_rpmbuild(w, verdict):
    """One typical packaging fault per spec; each must fail its own build."""
    v = spec_version(w, "tea")
    plants = {
        # a watcher bump that did not re-vendor: the spec moved, the binary did not
        "tea": (lambda w: (replace("fedora/tea/tea.spec", f"Version:        {v}\n", f"Version:        {BUMPED}\n")(w),
                           (w / f"fedora/tea/tea-{v}-linux-amd64.xz").rename(w / f"fedora/tea/tea-{BUMPED}-linux-amd64.xz")),
                rf"does not report {BUMPED}"),
        # a man page generator that silently writes nothing
        "syft": (replace("fedora/syft/syft.spec", "\n  ./%{name} > %{name}.1\n", "\n  ./%{name} > /dev/null; : > %{name}.1\n"),
                 r"Bad exit status from .*\(%check\)"),
        # an empty completion
        "grype": (replace("fedora/grype/grype.spec", "./%{name} completion fish > %{name}.fish", ": > %{name}.fish"),
                  r"Bad exit status from .*\(%check\)"),
        # the %check section lost
        "grant": (lambda w: (w / "fedora/grant/grant.spec").write_text(
            re.sub(r"\n%check\n.*?(?=\n%files\n)", "", (w / "fedora/grant/grant.spec").read_text(), count=1, flags=re.S)),
                  r"%check did not run"),
    }
    for tool, (plant, _) in plants.items():
        before = (w / f"fedora/{tool}/{tool}.spec").read_text()
        try:
            plant(w)
        except DoesNotApply as e:
            verdict(False, f"%check: {tool}", f"the defect does not apply any more ({e})")
            return
        if (w / f"fedora/{tool}/{tool}.spec").read_text() == before:
            verdict(False, f"%check: {tool}", "planting the defect changed nothing")
            return
    p = sh("bash", "scripts/rpmbuild-check.sh", cwd=w, check=False)
    # Cut the log into one piece per spec: "FAIL  <spec>" / "ok    <spec>" start one.
    pieces, cur = {}, None
    for line in p.stdout.splitlines():
        m = re.match(r"(?:FAIL|ok)  +fedora/([^/]+)/", line)
        if m:
            cur = m.group(1)
        if cur:
            pieces.setdefault(cur, []).append(line)
    for tool, (_, expect) in plants.items():
        piece = "\n".join(pieces.get(tool, []))
        verdict(piece.startswith("FAIL") and re.search(expect, piece) is not None,
                f"%check: {tool} fails its build", f"wanted FAIL and /{expect}/:\n" + tail(piece or p.stdout))


def main():
    rpmbuild = sys.argv[1:] == ["--rpmbuild"]
    if sys.argv[1:] not in ([], ["--rpmbuild"]):
        sys.exit(__doc__)
    gaps = total = 0

    def verdict(red, label, detail):
        nonlocal gaps, total
        total += 1
        gaps += not red
        print(f"{'RED ok' if red else 'GAP   '}  {label}" + ("" if red else f"\n{detail}"), flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        w = pathlib.Path(tmp) / "w"
        w.mkdir()
        copy_tree(w)
        base = sh("bash", "scripts/rpmbuild-check.sh", cwd=w, check=False) if rpmbuild else lint(w)
        if base.returncode:
            print("selftest: the unmodified copy is already red -- nothing can be measured\n" + tail(base.stdout, 40))
            sys.exit(2)
        if rpmbuild:
            run_rpmbuild(w, verdict)
        else:
            # More copies by cloning the first: git shares only its immutable
            # objects, every working file is a file of its own.
            copies = [w]
            for i in range(1, JOBS):
                c = pathlib.Path(tmp) / f"w{i}"
                git(tmp, "clone", "-q", str(w), str(c))
                copies.append(c)
            run_lint_mutants(copies, verdict)
            run_special(w, verdict)
    print(f"\n{total - gaps}/{total} defects caught")
    sys.exit(1 if gaps else 0)


if __name__ == "__main__":
    main()
