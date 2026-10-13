#!/bin/bash
#
# rpmbuild-check.sh [--install-deps] -- build every spec the way COPR would,
# %check included, and fail if any build, any %check, or any expected binary
# RPM is missing.
#
# Why: a push to main builds nothing on COPR (only build-<tool> does), so a spec
# edited by hand on main is first built when the next upstream release bumps it
# -- possibly weeks later, and then that release is stuck. This builds it now.
#
#   CI:      check-repo.yml, job rpmbuild (Fedora container, --install-deps)
#   locally: docker run --rm --security-opt label=disable \
#              -v "$PWD:/src:ro" -w /src registry.fedoraproject.org/fedora:latest \
#              bash scripts/rpmbuild-check.sh --install-deps
#
# --install-deps runs `dnf builddep` for every spec: only for a throwaway
# container, never on a workstation. Builds go to a temporary _topdir; the
# vendored sources are read in place (flat, next to each spec).
set -uo pipefail

DEPS=0
[ "${1:-}" = --install-deps ] && DEPS=1
cd "$(dirname "$0")/.." || exit 2
TOP=$(mktemp -d)
trap 'rm -rf "$TOP"' EXIT

if [ "$DEPS" = 1 ] && ! dnf -y -q install rpm-build >"$TOP/deps.log" 2>&1; then
    tail -20 "$TOP/deps.log" >&2
    echo "rpmbuild-check: could not install rpm-build" >&2
    exit 2
fi
for tool in rpmbuild rpmspec; do
    command -v "$tool" >/dev/null || { echo "rpmbuild-check: $tool is not installed (rpm-build)" >&2; exit 2; }
done

mapfile -t specs < <(find fedora -mindepth 2 -maxdepth 2 -name '*.spec' | sort)
if [ "${#specs[@]}" -eq 0 ]; then
    echo "rpmbuild-check: no spec found under fedora/ -- the layout moved" >&2
    exit 2
fi

rc=0
for spec in "${specs[@]}"; do
    dir=$(dirname "$spec")
    nvr=$(rpmspec -q --srpm --qf '%{name}-%{version}-%{release}\n' "$spec" 2>/dev/null | head -1)
    log="$TOP/$(basename "$spec" .spec).log"
    if [ "$DEPS" = 1 ] && ! dnf -y -q builddep "$spec" >"$log" 2>&1; then
        echo "FAIL  $spec: dnf builddep failed" >&2; tail -20 "$log" >&2; rc=1; continue
    fi
    if ! rpmbuild -bb --define "_topdir $TOP" --define "_sourcedir $PWD/$dir" "$spec" >"$log" 2>&1; then
        echo "FAIL  $spec ($nvr): rpmbuild failed" >&2; tail -30 "$log" >&2; rc=1; continue
    fi
    # Ask the artifact, not the exit code: %check must really have run (a
    # --nocheck or a lost section would still exit 0), and the RPM must exist.
    if ! grep -q 'Executing(%check)' "$log"; then
        echo "FAIL  $spec ($nvr): %check did not run" >&2; rc=1; continue
    fi
    if ! compgen -G "$TOP/RPMS/*/$nvr.*.rpm" >/dev/null; then
        echo "FAIL  $spec: no binary RPM $nvr.*.rpm was written" >&2; rc=1; continue
    fi
    echo "ok    $spec ($nvr, %check passed)"
done
exit $rc
