#!/bin/bash
#
# push-retry.sh <git push arguments...>
#
# `git push`, retried. Used by every watcher for the push to main and for the
# COPR trigger-branch push.
#
# The trigger push is the one step nothing repeats: the watcher has already put
# the new .upstream-tag on main, so if this push fails, the next run finds the
# marker current and has nothing left to do -- the build is LOST rather than
# late. GitHub does answer pushes with transient 500s (seen 2026-10-12 in
# gmipf/packaging-media-preservation, three in a row). A failure BEHIND the
# state write is not healed by the next run; only a retry here is, and
# scripts/copr-reconcile.py behind it.
#
# The push to main is a fast-forward and every trigger push is a -f to a branch
# the caller owns, so repeating either cannot do harm.
set -u
attempts=4
for attempt in $(seq 1 "$attempts"); do
    git push "$@" && exit 0
    [ "$attempt" -lt "$attempts" ] || break
    echo "::warning::git push $* failed (attempt $attempt/$attempts), retrying in $((attempt * 15))s"
    sleep $((attempt * 15))
done
echo "::error::git push $* failed $attempts times"
exit 1
