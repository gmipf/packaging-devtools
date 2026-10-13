# packit-routing

Claim: a push of the trigger branch `build-<tool>` makes Packit build exactly
that package on Copr, and a push to `main` builds nothing.

RED (2026-10-03, locally, with Packit's own matching): Packit matches a job's
`branch:` with `re.match`, which anchors at the start only. The filters in use
then were unanchored, and `re.match("build-grype", "build-grype-db")` matched:
a later tool whose name starts with `grype` would have rebuilt grype as well.
`re.match("^build-grype$", "build-grype-db")` does not match. Anchored in
6587f8e; since then `scripts/test-copr-reconcile.py` refuses any filter that
is not `^build-<tool>$`. The red half was not produced at the service: that
would have meant a foreign rebuild of a package people install.

OBSERVED (2026-10-07 at Packit and Copr `gmipf/devtools`, read back from the
Copr API build list on 2026-10-13):

    97b78e1  chore: syft v1.54.1    watcher pushed main + build-syft   -> 11089765  syft 1.54.1-1   succeeded
    186369f  chore: grype v0.120.1  watcher pushed main + build-grype  -> 11089897  grype 0.120.1-1 succeeded

No other build since 6587f8e (2026-10-03): tea stayed at 10969768 and grant
at 10702123, and the pushes to main 6587f8e, b424177, 3ec969f and 456ed51
built nothing.

The fingerprint in the ledger was taken on 2026-10-13. It is the state that
was observed: the `jobs` of `.packit.yaml` are identical at 97b78e1, 186369f
and 01a6423, and no commit in between touched the file.

VERDICT: holds. One push of a trigger branch, one build, of its own package;
main builds nothing.
