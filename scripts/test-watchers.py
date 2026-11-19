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

Each watcher first asks whether the upstream repository is archived
(scripts/upstream-archived.sh). The fake upstream answers as the real one does
today: archived exactly where the package carries .upstream-archived. An
archived upstream without that file, the file without an archived upstream,
and an answer that says neither must each stop the watcher; an archived
upstream with the file must not.

Anchore signs each release's checksums.txt with cosign
(scripts/verify-signed-checksums.sh), and the syft, grype and grant watchers
check that signature on every run: a new release before it is vendored, an
unchanged one against the tarball already vendored. A cosign stub stands in
for cosign; its fake bundle names the hash it signs, the signer and the OIDC
issuer. A checksums.txt changed after signing, a missing signature, another
signer or another issuer must each stop the watcher, and so must a vendored
tarball that no longer matches what was signed.

Gitea signs each tea and gitea-cli release's checksums.txt with its OpenPGP
release key (scripts/verify-pgp-checksums.sh), checked the same way on every
run. Stubs stand in for gpg and gpgv; a fake key names its fingerprint, a fake
signature the hash it signs and the key that made it, and gpgv answers with the
status lines the real one prints. A checksums.txt changed after signing, a
missing signature, a signature by another key or by a revoked key, another key
served under the release key's fingerprint, no answer from the key server and
a vendored binary that no longer matches must each stop the watcher.
"""
import hashlib
import io
import json
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
    "actionlint": ("github", "rhysd/actionlint"),
    "tea": ("gitea", "gitea/tea"),
    "gitea-cli": ("gitea", "gitea/cli"),
}
# Who signs each signed upstream's checksums.txt, as read from the certificates
# in the real bundles (2026-11-19), again independently of the watchers.
SIGNED = {"syft", "grype", "grant"}
SIGNER = "https://github.com/{project}/.github/workflows/release.yaml@refs/heads/main"
ISSUER = "https://token.actions.githubusercontent.com"
# Who signs each gitea upstream's checksums.txt: Gitea's release key "Teabot
# <teabot@gitea.io>", as read from the real signatures (2026-11-19).
PGP = {"tea", "gitea-cli"}
PGP_KEY = "7C9E68152594688862D62AF62D9AE806EC1592E2"
OTHER_KEY = "0123456789ABCDEF0123456789ABCDEF01234567"
LOCAL = object()  # tag=LOCAL: the release the package already ships

CURL = r"""#!/bin/bash
url= out=
while [ $# -gt 0 ]; do
    case $1 in -o) out=$2; shift 2 ;; http://*|https://*) url=$1; shift ;; *) shift ;; esac
done
echo "curl $url" >> "$STUB_ROOT/calls"
f=$STUB_ROOT/files/${url#*://}
[ -d "$f" ] && f=$f/.self
[ -f "$f" ] || { echo "curl: (22) The requested URL returned error: 404 ($url)" >&2; exit 22; }
if [ -n "$out" ]; then cp "$f" "$out"; else cat "$f"; fi
"""
GH = r"""#!/bin/bash
echo "gh $*" >> "$STUB_ROOT/calls"
if [ "$1" = api ]; then
    f=$STUB_ROOT/ghapi/$2
    [ -f "$f" ] || { echo '{"message":"Not Found","status":"404"}'; echo "gh: Not Found (HTTP 404)" >&2; exit 1; }
    cat "$f"
    exit 0
fi
repo=
while [ $# -gt 0 ]; do case $1 in --repo) repo=$2; shift 2 ;; *) shift ;; esac; done
f=$STUB_ROOT/gh/$repo
[ -f "$f" ] || { echo "release not found ($repo)" >&2; exit 1; }
cat "$f"
"""
# cosign verify-blob as far as the watchers use it. The fake bundle is one line:
# "<sha256 of the signed file> <signer identity> <OIDC issuer>". A flag it does
# not know is an error, so a watcher that loosens the check is not let through.
COSIGN = r"""#!/bin/bash
echo "cosign $*" >> "$STUB_ROOT/calls"
[ "$1" = verify-blob ] || { echo "cosign stub: only verify-blob" >&2; exit 1; }
shift
bundle= id= idre= iss= issre= file=
while [ $# -gt 0 ]; do
    case $1 in
        --bundle) bundle=$2; shift 2 ;;
        --certificate-identity) id=$2; shift 2 ;;
        --certificate-identity-regexp) idre=$2; shift 2 ;;
        --certificate-oidc-issuer) iss=$2; shift 2 ;;
        --certificate-oidc-issuer-regexp) issre=$2; shift 2 ;;
        -*) echo "cosign stub: flag $1 not known here" >&2; exit 1 ;;
        *) file=$1; shift ;;
    esac
done
read -r signed signer issuer < "$bundle" || { echo "Error: cannot read bundle $bundle" >&2; exit 1; }
[ "$(sha256sum < "$file" | cut -d' ' -f1)" = "$signed" ] ||
    { echo "Error: failed to verify signature: invalid signature" >&2; exit 1; }
if [ -n "$id" ]; then [ "$signer" = "$id" ]; elif [ -n "$idre" ]; then [[ $signer =~ $idre ]]; else false; fi ||
    { echo "Error: failed to verify certificate identity: got SAN \"$signer\"" >&2; exit 1; }
if [ -n "$iss" ]; then [ "$issuer" = "$iss" ]; elif [ -n "$issre" ]; then [[ $issuer =~ $issre ]]; else false; fi ||
    { echo "Error: failed to verify certificate identity: got issuer \"$issuer\"" >&2; exit 1; }
echo "Verified OK" >&2
"""
# gpg and gpgv as far as scripts/verify-pgp-checksums.sh uses them. The fake key
# is one line, "<primary fingerprint> [revoked]"; the fake signature is
# "<sha256 of the signed file> <primary fingerprint of the key that made it>".
# gpgv answers with the status lines and exit codes the real one gives
# (measured with gpgv 2.4.9): GOODSIG + VALIDSIG ending in the primary
# fingerprint, BADSIG and 1, ERRSIG + NO_PUBKEY and 2. For a revoked key the
# stub prints REVKEYSIG and exits 0, the worst case (not measured), so that
# only a check of the status lines refuses it.
GPG = r"""#!/bin/bash
echo "gpg $*" >> "$STUB_ROOT/calls"
for a; do [ "$a" = --dearmor ] && exec cat; done
echo "gpg stub: only --dearmor" >&2
exit 2
"""
GPGV = r"""#!/bin/bash
echo "gpgv $*" >> "$STUB_ROOT/calls"
fd= keyring=
while [ $# -gt 2 ]; do
    case $1 in
        --status-fd) fd=$2; shift 2 ;;
        --keyring) keyring=$2; shift 2 ;;
        *) echo "gpgv stub: flag $1 not known here" >&2; exit 2 ;;
    esac
done
[ "$fd" = 1 ] && [ -n "$keyring" ] && [ $# -eq 2 ] || { echo "gpgv stub: want --status-fd 1 --keyring K SIG FILE" >&2; exit 2; }
read -r key state < "$keyring" || { echo "gpgv: keydb_search failed" >&2; exit 2; }
read -r signed signer < "$1" || { echo "gpgv: no signature found" >&2; exit 2; }
echo "[GNUPG:] NEWSIG"
if [ "$signer" != "$key" ]; then
    echo "[GNUPG:] ERRSIG ${signer: -16} 1 10 00 1795034985 9 -"
    echo "[GNUPG:] NO_PUBKEY ${signer: -16}"
    exit 2
fi
if [ "$(sha256sum < "$2" | cut -d' ' -f1)" != "$signed" ]; then
    echo "[GNUPG:] BADSIG ${key: -16} Teabot <teabot@gitea.io>"
    exit 1
fi
if [ "$state" = revoked ]; then
    echo "[GNUPG:] REVKEYSIG ${key: -16} Teabot <teabot@gitea.io>"
else
    echo "[GNUPG:] GOODSIG ${key: -16} Teabot <teabot@gitea.io>"
fi
echo "[GNUPG:] VALIDSIG CC64B1DB67ABBEECAB24B6455FC346329753F4B0 2026-11-18 1795034985 0 4 0 1 10 00 $key"
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


def fake_release(tool, root, *, tag=TAG, payload=ELF, member=None, sums="good", asset=True, repo=None,
                 sig="good", vendored=None):
    """Lay out what the upstream would serve. sums: good | wrong | missing.
    repo, the repository's own answer: active | archived | no-field | missing;
    by default archived exactly where the real package has .upstream-archived.
    sig, the bundle next to checksums.txt (Sigstore upstreams): good |
    tampered (checksums.txt changed after signing) | missing | other-signer |
    other-issuer; or its checksums.txt.sig (OpenPGP upstreams): good |
    tampered | missing | other-key | revoked | swapped-key (the key server
    serves another key, which made the signature) | no-key (the key server
    has none). vendored: the bytes the package already ships for this
    release; checksums.txt lists them instead of the asset."""
    kind, project = UPSTREAM[tool]
    ver = tag[1:] if re.fullmatch(r"v\d+\.\d+\.\d+", tag) else V
    files = root / "files"
    if repo is None:
        repo = "archived" if (ROOT / f"fedora/{tool}/.upstream-archived").exists() else "active"
    if repo != "missing":
        meta = {"full_name": project}
        if repo != "no-field":
            meta["archived"] = repo == "archived"
        where = (root / "ghapi/repos" / project if kind == "github"
                 else files / f"gitea.com/api/v1/repos/{project}/.self")
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(json.dumps(meta) + "\n")
    if kind == "github":
        (root / "gh" / project).parent.mkdir(parents=True, exist_ok=True)
        (root / "gh" / project).write_text(tag + "\n")
        name = f"{tool}_{ver}_linux_amd64.tar.gz"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for n, data in ((member or tool, payload), ("LICENSE", b"license\n")):
                info = tarfile.TarInfo(n)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        blob = buf.getvalue()
        base = files / f"github.com/{project}/releases/download/{tag}"
        sumfile, sumline = base / f"{tool}_{ver}_checksums.txt", f"  {name}\n"
    else:
        api = files / f"gitea.com/api/v1/repos/{project}/releases"
        api.mkdir(parents=True)
        (api / "latest").write_text(f'{{"tag_name": "{tag}"}}\n')
        name = f"{tool}-{ver}-linux-amd64.xz"
        blob = lzma.compress(payload, format=lzma.FORMAT_XZ)
        base = files / f"gitea.com/{project}/releases/download/{tag}"
        sumfile, sumline = base / "checksums.txt", f"  {name}\n"
    base.mkdir(parents=True, exist_ok=True)
    if asset:
        (base / name).write_bytes(blob)
    listed = blob if vendored is None else vendored
    digest = hashlib.sha256(listed if sums == "good" else listed + b"tampered").hexdigest()
    if sums != "missing":
        other = "0" * 64 + (f"  {tool}_{ver}_darwin_amd64.tar.gz\n" if kind == "github"
                            else f"  {tool}-{ver}-darwin-amd64.xz\n")
        sumfile.write_text(other + digest + sumline)
    if tool in PGP:
        signed = sumfile.read_bytes() if sumfile.exists() else b""
        if sig == "tampered":
            signed += b"0" * 64 + b"  an asset signed before checksums.txt was changed\n"
        signer = OTHER_KEY if sig in ("other-key", "swapped-key") else PGP_KEY
        if sig != "missing":
            (base / "checksums.txt.sig").write_text(f"{hashlib.sha256(signed).hexdigest()} {signer}\n")
        if sig != "no-key":
            served = files / f"keys.openpgp.org/vks/v1/by-fingerprint/{PGP_KEY}"
            served.parent.mkdir(parents=True, exist_ok=True)
            served.write_text((OTHER_KEY if sig == "swapped-key" else PGP_KEY)
                              + (" revoked" if sig == "revoked" else "") + "\n")
    if tool in SIGNED and sig != "missing":
        signed = sumfile.read_bytes() if sumfile.exists() else b""
        signer = SIGNER.format(project=f"someone-else/{tool}" if sig == "other-signer" else project)
        issuer = "https://accounts.google.com" if sig == "other-issuer" else ISSUER
        if sig == "tampered":
            signed += b"0" * 64 + b"  an asset signed before checksums.txt was changed\n"
        (base / f"{sumfile.name}.sigstore.json").write_text(
            f"{hashlib.sha256(signed).hexdigest()} {signer} {issuer}\n")
    return name, blob


def setup(tool, w, marker=None):
    """A repository holding just this tool's package dir and the scripts its
    watcher calls, with the vendored binary swapped for a small stand-in of the
    same name. marker: True or False puts or takes away .upstream-archived,
    None leaves it as the package has it."""
    src = ROOT / f"fedora/{tool}"
    spec = src / f"{tool}.spec"
    old = source0(spec)
    work, remote = w / "work", w / "remote.git"
    (work / "scripts").mkdir(parents=True)
    for script in ("push-retry.sh", "upstream-archived.sh", "verify-signed-checksums.sh", "verify-pgp-checksums.sh"):
        shutil.copy2(ROOT / "scripts" / script, work / "scripts" / script)
    shutil.copytree(src, work / f"fedora/{tool}", ignore=shutil.ignore_patterns(old))
    note = work / f"fedora/{tool}/.upstream-archived"
    if marker:
        note.write_text("archived upstream, kept on purpose\n")
    elif marker is False:
        note.unlink(missing_ok=True)
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
    for n, text in (("curl", CURL), ("gh", GH), ("cosign", COSIGN), ("gpg", GPG), ("gpgv", GPGV)):
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


def shipped(tool, work, old):
    """What fake_release needs to stand for the release the package ships."""
    return {"tag": (work / f"fedora/{tool}/.upstream-tag").read_text().strip(),
            "vendored": (work / f"fedora/{tool}" / old).read_bytes()}


def refusal(tool, w, label, expect, marker=None, **release):
    work, remote, old = setup(tool, w, marker)
    if release.get("tag") is LOCAL:
        release.update(shipped(tool, work, old))
    fake_release(tool, w / "up", **release)
    before = refs(remote)
    rc, out = run_watcher(tool, w, work)
    ok = rc != 0 and refs(remote) == before and (expect is None or re.search(expect, out) is not None)
    return {f"refuses {label}, pushes nothing": (ok, f"exit {rc}, wanted /{expect}/:\n{out[-1200:]}")}


def unchanged(tool, w, label="same tag again: nothing to do, nothing pushed", marker=None, repo=None):
    work, remote, old = setup(tool, w, marker)
    fake_release(tool, w / "up", repo=repo, **shipped(tool, work, old))
    before = refs(remote)
    rc, out = run_watcher(tool, w, work)
    return {label: (rc == 0 and refs(remote) == before, out[-800:])}


def cases(tool):
    yield good_release
    yield unchanged
    yield lambda t, w: refusal(t, w, "a checksum mismatch", r"SHA256 mismatch", sums="wrong")
    yield lambda t, w: refusal(t, w, "a release without a checksum", None, sums="missing")
    yield lambda t, w: refusal(t, w, "a payload that is not an ELF", r"not an ELF", payload=b"#!/bin/sh\necho hi\n")
    yield lambda t, w: refusal(t, w, "a missing download", r"404", asset=False)
    yield lambda t, w: refusal(t, w, "an unexpected tag", r"Unexpected .*tag", tag="nightly-2026")
    yield lambda t, w: refusal(t, w, "an archived upstream without .upstream-archived", r"is archived: no new release",
                               marker=False, repo="archived")
    yield lambda t, w: unchanged(t, w, "an archived upstream with .upstream-archived carries on, pushes nothing",
                                 marker=True, repo="archived")
    yield lambda t, w: refusal(t, w, "an .upstream-archived that upstream contradicts", r"upstream is active again",
                               marker=True, repo="active")
    yield lambda t, w: refusal(t, w, "an answer without the archived field", r"is archived \(answer: null\)",
                               repo="no-field")
    yield lambda t, w: refusal(t, w, "no answer whether upstream is archived", r"is archived \(answer: unreadable\)",
                               repo="missing")
    if UPSTREAM[tool][0] == "github":
        yield lambda t, w: refusal(t, w, "an archive without the binary", r"not a valid gzip tarball containing",
                                   member="README")
    if tool in SIGNED:
        yield cosign_installed
        not_signed = r"cosign could not verify \S+_checksums\.txt of anchore/\S+ \S+ as signed by"
        yield lambda t, w: refusal(t, w, "a checksums.txt changed after it was signed", not_signed, sig="tampered")
        yield lambda t, w: refusal(t, w, "a release without a signature", r"Could not download \S+\.sigstore\.json",
                                   sig="missing")
        yield lambda t, w: refusal(t, w, "a signature by another workflow", not_signed, sig="other-signer")
        yield lambda t, w: refusal(t, w, "a signature from another OIDC issuer", not_signed, sig="other-issuer")
        yield lambda t, w: refusal(t, w, "a vendored tarball that no longer matches the signed checksums",
                                   r"SHA256 mismatch", tag=LOCAL, sums="wrong")
        yield lambda t, w: refusal(t, w, "an unchanged release whose signature is gone",
                                   r"Could not download \S+\.sigstore\.json", tag=LOCAL, sig="missing")
    if tool in PGP:
        not_signed = rf"checksums\.txt of {re.escape(UPSTREAM[tool][1])} \S+ is not signed by Gitea's release key"
        no_sig = r"Could not download checksums\.txt\.sig"
        yield lambda t, w: refusal(t, w, "a checksums.txt changed after it was signed", not_signed, sig="tampered")
        yield lambda t, w: refusal(t, w, "a release without a signature", no_sig, sig="missing")
        yield lambda t, w: refusal(t, w, "a signature by another key", not_signed, sig="other-key")
        yield lambda t, w: refusal(t, w, "a signature by a revoked key", not_signed, sig="revoked")
        yield lambda t, w: refusal(t, w, "another key served under the release key's fingerprint", not_signed,
                                   sig="swapped-key")
        yield lambda t, w: refusal(t, w, "no answer from the key server", r"Could not download Gitea's release key",
                                   sig="no-key")
        yield lambda t, w: refusal(t, w, "a vendored binary that no longer matches the signed checksums",
                                   r"SHA256 mismatch", tag=LOCAL, sums="wrong")
        yield lambda t, w: refusal(t, w, "an unchanged release whose signature is gone", no_sig, tag=LOCAL,
                                   sig="missing")


def cosign_installed(tool, w):
    steps = yaml.safe_load((ROOT / f".github/workflows/watch-{tool}-releases.yml").read_text())["jobs"]["watch"]["steps"]
    kinds = [s.get("uses", "run" if "run" in s else "?") for s in steps]
    cosign = [i for i, k in enumerate(kinds) if k.startswith("sigstore/cosign-installer@")]
    run = kinds.index("run") if "run" in kinds else -1
    ok = (len(cosign) == 1 and cosign[0] < run
          and re.fullmatch(r"sigstore/cosign-installer@[0-9a-f]{40}", kinds[cosign[0]]) is not None)
    return {"installs cosign, pinned to a commit, before its run step": (ok, str(kinds))}


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
