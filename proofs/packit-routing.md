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

OBSERVED again (2026-11-18 at Packit and Copr `gmipf/devtools`, read back
from the Copr API build list the same evening), after 0d1f305 added the fifth
job, actionlint's, to `.packit.yaml#jobs`:

    0d1f305  Add actionlint        pushed to main                     -> no build
    d690954  trigger: actionlint   build-tool.sh pushed build-actionlint -> 11351527  actionlint 1.7.12-1 succeeded

The list went from 41 builds to 42. grant stayed at 11342387, grype at
11350662, syft at 11341982 and tea at 10969768. Packit submitted 11351527 at
19:58:53 UTC, seconds after the trigger push; the push to main, eight minutes
earlier (its CI run started at 19:50:03 UTC), built nothing.

OBSERVED a third time (2026-11-18 at Packit and Copr `gmipf/devtools`, read
back from the Copr API build list and from the commits' GitHub check runs the
same night), after b272966 added the sixth job, gitea-cli's:

    b272966  Add gitea-cli         pushed to main                       -> no build
    9c08832  trigger: gitea-cli    build-tool.sh pushed build-gitea-cli -> 11357213  gitea-cli 2.0.0-1 succeeded

build-tool.sh pushed main and then the trigger branch seconds apart, and
Packit submitted 11357213 at 23:25:18 UTC, so the time alone does not tell
which push it answered. Its check runs do: the four
`rpm-build:build-gitea-cli:<chroot>:gitea-cli` runs of packit-as-a-service
are on 9c08832, and b272966 carries only the four GitHub Actions jobs of
check-repo. The list went from 43 builds to 44. The 43rd, 11357085, is tea's
rebuild from its own trigger push, c45d71f on build-tea; the pushes to main
around it, 8eaf437 and 8ae8f21, built nothing and carry no Packit run either.
actionlint stayed at 11351527, grant at 11342387, grype at 11350662, syft at
11341982 and tea at 11357085.

The fingerprint in the ledger is taken at b272966: the six jobs observed in
the third run. The one before was taken on 2026-11-18 at 0d1f305, over the
five jobs of the second run; the first on 2026-10-13, over four jobs,
identical at 97b78e1, 186369f and 01a6423.

VERDICT: holds, with four jobs, with five and with six. One push of a trigger
branch, one build, of its own package; main builds nothing.
