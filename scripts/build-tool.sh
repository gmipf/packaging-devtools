#!/usr/bin/env bash
#
# build-tool.sh — manually trigger a single tool's COPR build, safely (GENERIC).
#
# Generalized from the 3-day-proven media-preservation packaging script. The
# proven logic below is identical across packaging repos; the ONLY per-repo
# parts live in ./packaging.conf (COPR owner/project + the tool registry).
#
# Why this exists
# ---------------
# COPR builds use `update_release: false` (see .packit.yaml), so the published
# NEVRA is EXACTLY what the spec says — a clean bare-N Release, no build suffix
# (keeps the version convention intact, [[rpm-version-convention]]).
#
# The price of a clean NEVRA: a manual rebuild whose spec NEVRA hasn't changed
# would republish the SAME NEVRA with a fresh checksum and break `dnf` clients
# ([[dnf-cache-rebuild]]). GitHub watchers never hit this (they bump
# Version / reset Release on every real upstream change). MANUAL builds are the
# only gap — so this script is the one supported way to fire one by hand.
#
# Guarantees
# ----------
#  * Same-NEVRA impossible: before triggering it compares the spec NEVRA against
#    the latest already built in COPR and, if ours wouldn't be strictly newer,
#    AUTO-BUMPS the bare-N Release (e.g. -5 -> -6) and commits it.
#  * Only the requested tool rebuilds: routed through the per-tool trigger branch
#    build-<tool> (branch-scoping, [[packit-yaml-cross-trigger]]).
#
# Setup per packaging repo
# ------------------------
#   - copy this script to        <repo>/scripts/build-tool.sh   (chmod +x)
#   - create                     <repo>/packaging.conf          (see packaging.conf.example):
#       COPR_OWNER=<owner>
#       COPR_PROJECT=<default-project>
#       TOOLS[<short>]="<copr-package>|<spec-path>|<trigger-branch>[|<copr-project>]"
#
# The optional 4th field overrides COPR_PROJECT for that one tool — so a single
# repo can publish thematic apps to different COPR projects (gmipf/devtools,
# gmipf/<theme>, ...) WITHOUT moving any files. The directory tree only ever
# encodes <format>/<app>/ (which COPR it ships to is routing, not layout).
#
# Usage
# -----
#   scripts/build-tool.sh <tool>
#
# Run on a clean `main` (commit spec edits first). It will, if needed, add a
# Release-bump commit, push main (which builds nothing by design), then recreate
# build-<tool> and force-push it to fire exactly one build.

set -euo pipefail

API=https://copr.fedorainfracloud.org/api_3

# Vendored upstream binaries (Source0 committed flat) make pushes several MB. git's
# default http.postBuffer (~1MB) then switches to chunked transfer, which must rewind
# the body on a redirect and fails ("cannot rewind RPC post data"). Buffer the whole
# pack instead. Passed per-command (-c) so we never touch a sandbox-RO .git/config.
GIT="git -c http.postBuffer=524288000 -c http.version=HTTP/1.1"

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

# --- load per-repo config ----------------------------------------------------
CONF="$ROOT/packaging.conf"
[ -f "$CONF" ] || { echo "error: missing $CONF (copy templates/packaging.conf.example)" >&2; exit 2; }
declare -A TOOLS=()
# shellcheck disable=SC1090
. "$CONF"
: "${COPR_OWNER:?packaging.conf must set COPR_OWNER}"
: "${COPR_PROJECT:?packaging.conf must set COPR_PROJECT (default project)}"
OWNER=$COPR_OWNER

TOOL=${1:-}
ENTRY=${TOOLS[$TOOL]:-}
if [ -z "$ENTRY" ]; then
  echo "usage: $0 <tool>   (known: ${!TOOLS[*]})" >&2
  exit 2
fi
# 4th field (PROJ) is optional: per-tool COPR-project override, else the default.
IFS='|' read -r PKG SPEC BR PROJ <<<"$ENTRY"
PROJECT=${PROJ:-$COPR_PROJECT}

if [ -n "$(git status --porcelain)" ]; then
  echo "error: working tree is dirty — commit or stash your changes first." >&2
  exit 1
fi

START_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# --- spec NEVRA (clean, as it will be published) -----------------------------
SPEC_V=$(rpmspec -q --srpm --qf '%{version}\n' "$SPEC" | head -1)
SPEC_R_FULL=$(rpmspec -q --srpm --qf '%{release}\n' "$SPEC" | head -1)
SPEC_RBASE=${SPEC_R_FULL%%.*}   # bare-N, drop %{?dist} (.fcNN)

# --- latest succeeded NEVRA already in COPR ----------------------------------
COPR_VR=$(curl -sg "$API/package?ownername=$OWNER&projectname=$PROJECT&packagename=$PKG&with_latest_succeeded_build=True" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);b=(d.get('builds') or {}).get('latest_succeeded') or {};print(((b.get('source_package') or {}).get('version')) or '')")

echo "spec : $SPEC_V-$SPEC_RBASE"
echo "copr : ${COPR_VR:-<none>}"

# --- decide: ok / bump:<N> / abort -------------------------------------------
if [ -z "$COPR_VR" ]; then
  ACTION=ok   # no prior build, nothing to collide with
else
  COPR_V=${COPR_VR%-*}
  COPR_R=${COPR_VR##*-}
  ACTION=$(python3 - "$SPEC_V" "$SPEC_RBASE" "$COPR_V" "$COPR_R" <<'PY'
import sys, rpm
_, sv, sr, cv, cr = sys.argv
cmp = rpm.labelCompare(("0", sv, sr), ("0", cv, cr))
if cmp > 0:
    print("ok")                                      # spec already strictly newer
elif sv == cv:
    print("bump:%d" % (int(cr.split(".")[0]) + 1))   # same version, lift Release
else:
    print("abort")                                   # spec version older — needs a human
PY
)
fi

case "$ACTION" in
  ok)
    echo "-> spec NEVRA is already newer than COPR; building as-is." ;;
  bump:*)
    N=${ACTION#bump:}
    echo "-> would collide with COPR; auto-bumping Release to $N."
    sed -i "s/^Release:.*/Release:        ${N}%{?dist}/" "$SPEC"
    git add "$SPEC"
    git commit -q -m "chore: bump $PKG Release to $N (keep clean NEVRA, supersede prior build)"
    SPEC_RBASE=$N ;;
  abort)
    echo "error: spec version ($SPEC_V) is older than COPR's ($COPR_V) — refusing." >&2
    echo "       bump the Version in $SPEC and re-run." >&2
    exit 1 ;;
esac

# --- canonical push (main builds nothing) ------------------------------------
$GIT push origin "HEAD:main"

# --- trigger branch = main's tree + a generic landing README (cosmetic), -----
#     force-pushed so ONLY this tool's COPR job fires.
git checkout -q -B trigger-build "$START_BRANCH"
SPECDIR=$(dirname "$SPEC")
printf '# %s — %s (Fedora/COPR trigger branch)\n\nAuto-managed **trigger branch** for the `%s` package: a push here fires\nthe %s COPR build via Packit, nothing else rebuilds. Canonical source is\n`main` (do not edit here). Packaging: `%s/`.\n' \
  "$BR" "$PKG" "$PKG" "$PKG" "$SPECDIR" > README.md
git add README.md
git commit -q -m "trigger: $PKG build ($SPEC_V-$SPEC_RBASE)"
$GIT push -f origin "trigger-build:$BR"

git checkout -q "$START_BRANCH"
git branch -D trigger-build >/dev/null 2>&1 || true

echo "done: $PKG $SPEC_V-$SPEC_RBASE -> $BR (COPR build triggered)."
