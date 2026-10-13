#!/bin/bash
#
# lint.sh -- every offline lint rule of this repository, in one place.
#
#   scripts/lint.sh          CI (check-repo.yml): every tool must be installed;
#                            a missing one fails the run (not measured != clean)
#   scripts/lint.sh --hook   pre-commit (.githooks): a tool that is not installed
#                            here is named and skipped -- CI still runs it
#
# Every rule was measured before it was switched on and seen red on a planted
# defect (2026-10-13). A finding fails the run; nothing here only warns.
#
#   whitespace   text files: no trailing blanks, no CR, a final newline
#                (.editorconfig tells editors the same)
#   shell        shellcheck -S warning on every *.sh AND every shell-shebang file.
#                packaging.conf is data sourced by build-tool.sh; its content is
#                checked by scripts/test-copr-reconcile.py (routing vs .packit.yaml)
#   ruff         every *.py and python-shebang file: syntax, undefined names,
#                bug patterns (E9,F,B)
#   yamllint     workflows + .packit.yaml (rules: .yamllint)
#   actionlint   workflows: expressions, contexts, and shellcheck on every
#                `run:` block
#   packit       .packit.yaml against Packit's own schema
#   rpmlint      every spec; the expected findings are DECLARED below and
#                checked both ways
#   coverage     a tracked file type no rule here understands (XML, .desktop,
#                manpage) is red until a rule for it exists
set -uo pipefail

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
HOOK=0
[ "${1:-}" = --hook ] && HOOK=1

rc=0
skipped=""
bad() { echo "lint: $*" >&2; rc=1; }
ok() { echo "lint: ok   $*"; }
have() {
    command -v "$1" >/dev/null 2>&1 && return 0
    if [ "$HOOK" = 1 ]; then skipped="$skipped $1"; else bad "$1 is not installed -- not measured is not clean"; fi
    return 1
}

# git grep: 0 = found (a finding), 1 = nothing found (clean), else = it failed.
none() {
    local label=$1 out
    shift
    out=$(git grep "$@")
    case $? in
        0) bad "$label:"; printf '%s\n' "$out" >&2 ;;
        1) ok "$label" ;;
        *) bad "$label: git grep failed" ;;
    esac
}

# Tracked files whose first line is a shebang matching $1, minus those matching $2.
by_shebang() {
    git grep -I -n -E "^#!$1" -- "$2" | sed -n 's/:1:#!.*//p'
}

# --- whitespace -------------------------------------------------------------
# -I skips binaries, so the vendored release tarballs never reach these rules.
none "no trailing whitespace" -I -nE '[[:blank:]]+$'
none "no CR line endings" -I -l $'\r'
texts=$(git grep -I -l '') || { bad "could not list text files"; texts=""; }
[ -n "$texts" ] || bad "no text files found -- the check would pass on nothing"
missing=""
while IFS= read -r f; do
    [ -n "$f" ] && [ -n "$(tail -c1 "$f")" ] && missing="$missing $f"
done <<<"$texts"
if [ -n "$missing" ]; then bad "no newline at end of:$missing"; else ok "final newline ($(wc -l <<<"$texts") text files)"; fi

# --- shellcheck -------------------------------------------------------------
if have shellcheck; then
    shebang=$(by_shebang '(/usr)?/bin/(env +)?(ba|da|k)?sh\b' ':!*.sh')
    mapfile -t sh < <({ git ls-files '*.sh'; printf '%s\n' "$shebang"; } | sed '/^$/d' | sort -u)
    if [ "${#sh[@]}" -lt 3 ]; then
        bad "shellcheck: only ${#sh[@]} scripts found -- the layout moved"
    elif shellcheck -S warning -f gcc "${sh[@]}"; then
        ok "shellcheck (${#sh[@]} scripts, $(wc -w <<<"$shebang") of them by shebang)"
    else
        bad "shellcheck found the above"
    fi
fi

# --- ruff -------------------------------------------------------------------
if have ruff; then
    shebang=$(by_shebang '(/usr)?/bin/(env +)?python3?\b' ':!*.py')
    mapfile -t py < <({ git ls-files '*.py'; printf '%s\n' "$shebang"; } | sed '/^$/d' | sort -u)
    if [ "${#py[@]}" -lt 2 ]; then
        bad "ruff: only ${#py[@]} python files found -- the layout moved"
    elif ruff check --no-cache --quiet --select E9,F,B "${py[@]}"; then
        ok "ruff E9,F,B (${#py[@]} files)"
    else
        bad "ruff found the above"
    fi
fi

# --- yamllint ---------------------------------------------------------------
if have yamllint; then
    mapfile -t yml < <(git ls-files '*.yml' '*.yaml' .yamllint)
    if [ "${#yml[@]}" -lt 3 ]; then bad "yamllint: only ${#yml[@]} files found -- the layout moved"
    elif yamllint -s -f parsable "${yml[@]}"; then ok "yamllint (${#yml[@]} files)"
    else bad "yamllint found the above"; fi
fi

# --- actionlint -------------------------------------------------------------
if have actionlint; then
    if actionlint -oneline; then ok "actionlint ($(git ls-files '.github/workflows/*.yml' | wc -l) workflows)"
    else bad "actionlint found the above"; fi
fi

# --- packit -----------------------------------------------------------------
if have packit; then
    # Its log is long and full of harmless dist-git warnings; shown only on failure.
    if out=$(packit validate . 2>&1); then ok "packit validate (.packit.yaml)"
    else bad "packit validate:"; printf '%s\n' "$out" | tail -20 >&2; fi
fi

# --- rpmlint ----------------------------------------------------------------
# 2026-10-13: 10 warnings, 0 errors. 3 were macros in comments -- rpm expands
# those too, and grant.spec really did render wrong (%license became the
# License tag). Escaped as %%. 4 were no-%check-section, gone since every spec
# got a selftest %check (also 2026-10-13; scripts/rpmbuild-check.sh runs it).
# The rest are expected and DECLARED here as "<spec> <severity> <check>",
# checked both ways: a finding not on the list is red, and so is a listed one
# that no longer occurs (take it off the list).
#   invalid-url        Source0 is the vendored upstream tarball, committed next
#                      to the spec, not a URL: COPR builds offline
EXPECTED="
grant.spec W invalid-url
grype.spec W invalid-url
syft.spec W invalid-url
"
if have rpmlint; then
    mapfile -t specs < <(git ls-files 'fedora/*.spec')
    out=$(rpmlint "${specs[@]}" 2>&1)
    got=$(grep -E ': [EW]: ' <<<"$out" | sed -E 's/^([^: ]+)(:[0-9]+)?: ([EW]): ([^ ]+).*/\1 \3 \4/' | sort -u)
    want=$(sed '/^$/d' <<<"$EXPECTED" | sort -u)
    unexpected=$(comm -23 <(printf '%s\n' "$got") <(printf '%s\n' "$want") | sed '/^$/d')
    gone=$(comm -13 <(printf '%s\n' "$got") <(printf '%s\n' "$want") | sed '/^$/d')
    if [ "${#specs[@]}" -eq 0 ]; then bad "rpmlint: no spec found -- the layout moved"
    elif ! grep -qE "${#specs[@]} specfiles checked" <<<"$out"; then
        bad "rpmlint did not report checking ${#specs[@]} specs:"; tail -5 <<<"$out" >&2
    else
        if [ -n "$unexpected" ]; then
            bad "rpmlint findings not on the EXPECTED list:"; grep -E ': [EW]: ' <<<"$out" >&2
        fi
        if [ -n "$gone" ]; then
            bad "rpmlint no longer reports these -- take them off EXPECTED in scripts/lint.sh:"; printf '%s\n' "$gone" >&2
        fi
        [ -n "$unexpected$gone" ] || ok "rpmlint (${#specs[@]} specs, $(wc -l <<<"$want") declared findings)"
    fi
fi

# --- coverage ---------------------------------------------------------------
# Nothing in this repo is XML, a desktop file or a manpage today (the manpages
# are generated at build time). The day one is committed, it must get a rule
# (xmllint / desktop-file-validate / groff -ww) instead of passing unread.
unlinted=$(git ls-files '*.xml' '*_service' '*.desktop' '*.[1-8]' '*.[1-8].in')
if [ -n "$unlinted" ]; then bad "no lint rule for these yet -- add one to scripts/lint.sh:"; printf '%s\n' "$unlinted" >&2
else ok "coverage (no XML, desktop file or manpage left unread)"; fi

if [ -n "$skipped" ]; then
    echo "lint: NOT RUN here (not installed):$skipped -- CI runs them" >&2
fi
exit $rc
