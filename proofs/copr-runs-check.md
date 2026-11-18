# copr-runs-check

Claim, one ledger entry per package (`copr-runs-check-syft`, `-grype`,
`-grant`, `-actionlint`, `-tea`, `-gitea-cli`): Copr runs the `%check`
section of that package's spec, and its builds pass with it.

The red half was measured in CI, not at Copr: `scripts/selftest.py --rpmbuild`
(check-repo.yml, job `rpmbuild`) plants one packaging fault per spec -- a
watcher bump that did not re-vendor, a man page generator that writes nothing,
an empty completion, a lost `%check` section -- and each must fail its own
build. Producing it at Copr would mean shipping a broken build to the people
who install the package.

OBSERVED (read on 2026-11-18 from `builder-live.log` of every chroot of every
Copr build of these packages since `%check` came in with 456ed51 on
2026-10-13). In each chroot (Fedora 43, 44, 45 and rawhide, x86_64) the log
has `Executing(%check)`, the binary prints the packaged version, the man page
and completion steps run, and the section ends in `+ exit 0` before
`Processing files:`. Copr build, package, version-release, state, ended (UTC):

    11176904  syft  1.55.0-1    succeeded 2026-10-20
    11250178  syft  1.56.0-1    succeeded 2026-11-03
    11271263  syft  1.57.0-1    succeeded 2026-11-06
    11292906  syft  1.57.1-1    succeeded 2026-11-09
    11341982  syft  1.57.2-1    succeeded 2026-11-17
    11177243  grype 0.121.0-1   succeeded 2026-10-20
    11245949  grype 0.121.1-1   succeeded 2026-11-02
    11271489  grype 0.121.2-1   succeeded 2026-11-06
    11299762  grype 0.121.3-1   succeeded 2026-11-10
    11342097  grype 0.122.0-1   succeeded 2026-11-17
    11350662  grype 0.122.1-1   succeeded 2026-11-18
    11246234  grant 0.7.0-1     succeeded 2026-11-02
    11293464  grant 0.7.1-1     succeeded 2026-11-09
    11342387  grant 0.8.0-1     succeeded 2026-11-17

Copr does not keep build logs for ever: those of 11089765 and 11089897
(2026-10-07) and of 10969768 (2026-09-10) already answer 404. So here is one
`%check` section as it stood, from 11341982, fedora-rawhide-x86_64; the
bracketed lines stand for what was left out:

    Executing(%check): /bin/sh -e /var/tmp/rpm-tmp.WjuTWV
    + umask 022
    + cd /builddir/build/BUILD/syft-1.57.2-build
    [the compiler flag exports]
    + cd packaging-devtools-1.57.2
    ++ /builddir/build/BUILD/syft-1.57.2-build/BUILDROOT/usr/bin/syft --version
    + v='syft 1.57.2'
    + echo 'syft 1.57.2'
    syft 1.57.2
    + case " $v " in
    + zcat -f /builddir/build/BUILD/syft-1.57.2-build/BUILDROOT/usr/share/man/man1/syft.1.gz
    + grep -q '^\.TH .*1.57.2' syft.1.check
    ++ wc -l
    + test 175 -gt 20
    + for f in [the bash, zsh and fish completion files]
    + grep -q syft /builddir/build/BUILD/syft-1.57.2-build/BUILDROOT/usr/share/bash-completion/completions/syft
    [the same for zsh/site-functions/_syft and fish/vendor_completions.d/syft.fish]
    + RPM_EC=0
    ++ jobs -p
    + exit 0
    Processing files: syft-1.57.2-1.fc46.x86_64

Each package's entry rests on that package's own job and packages block in
`.packit.yaml` (`jobs[branch=^build-<p>$]` and `packages.<p>`), not on the
whole list of jobs. For syft, grype and grant both are the same at 6587f8e
(2026-10-03, before every build above), at 82ffd71, where this observation
was first written down, and at 8da19d8, the last commit before the entry was
split per package. Only the list around them changed: 0d1f305 appended
actionlint's job. The `%check` sections of the syft, grype and grant specs
are the same at 8da19d8 as in 456ed51.

Until that split the observation was one entry over all jobs, and adding
actionlint's job set it back to not-yet, although no job it was observed for
had changed. Now a new package's job reopens only `packit-routing`, the claim
about all jobs together.

VERDICT: holds for syft, grype and grant. Copr ran their `%check` in every
chroot, and it passed in all 14 builds (56 chroot logs).

actionlint came in with 0d1f305 (2026-11-18), with `%check` from its first
build on.

OBSERVED for actionlint (read on 2026-11-18 from `builder-live.log` of all
four chroots of its first Copr build): 11351527, actionlint 1.7.12-1,
succeeded 2026-11-18. In each chroot the binary prints 1.7.12, the clean
workflow passes, the broken one is reported for its undefined context, the
man page has 284 lines and the section ends in `+ exit 0`. From
fedora-rawhide-x86_64:

    Executing(%check): /bin/sh -e /var/tmp/rpm-tmp.QJphYW
    + umask 022
    + cd /builddir/build/BUILD/actionlint-1.7.12-build
    [the compiler flag exports]
    + cd packaging-devtools-1.7.12
    ++ /builddir/build/BUILD/actionlint-1.7.12-build/BUILDROOT/usr/bin/actionlint -version
    ++ head -1
    + v=1.7.12
    1.7.12
    + echo 1.7.12
    + '[' 1.7.12 '!=' 1.7.12 ']'
    [the two printf lines writing good.yml and bad.yml]
    + /builddir/build/BUILD/actionlint-1.7.12-build/BUILDROOT/usr/bin/actionlint -shellcheck= -pyflakes= good.yml
    + /builddir/build/BUILD/actionlint-1.7.12-build/BUILDROOT/usr/bin/actionlint -shellcheck= -pyflakes= -oneline bad.yml
    + cat bad.out
    bad.yml:6:23: undefined variable "nosuch". available variables are "env", "github", "inputs", "job", "matrix", "needs", "runner", "secrets", "steps", "strategy", "vars" [expression]
    + grep -q 'undefined variable "nosuch"' bad.out
    + zcat -f /builddir/build/BUILD/actionlint-1.7.12-build/BUILDROOT/usr/share/man/man1/actionlint.1.gz
    + grep -q '^\.TH "ACTIONLINT"' actionlint.1.check
    ++ wc -l
    + test 284 -gt 20
    ++ jobs -p
    + exit 0
    Processing files: actionlint-1.7.12-1.fc46.x86_64

VERDICT: holds for actionlint. Copr ran its `%check` in all four chroots of
its first build, and it passed.

tea will see no new release to run its `%check`: upstream archived the
repository on 2026-10-29 and names gt (gitea.com/gitea/cli) as its successor.
Its last Copr build, 0.16.0-1 on 2026-09-10, predates `%check`, so 8eaf437
builds the same binary once more as 0.16.0-2, only for that.

OBSERVED for tea (read on 2026-11-18 from `builder-live.log` of all four
chroots): 11357085, tea 0.16.0-2, succeeded 2026-11-18. In each chroot the
binary prints 0.16.0, the man page has 3995 lines and the section ends in
`+ exit 0`. From fedora-rawhide-x86_64:

    Executing(%check): /bin/sh -e /var/tmp/rpm-tmp.cYa69G
    + umask 022
    + cd /builddir/build/BUILD/tea-0.16.0-build
    [the compiler flag exports]
    + cd packaging-devtools-0.16.0
    ++ /builddir/build/BUILD/tea-0.16.0-build/BUILDROOT/usr/bin/tea --version
    + v=$'Version: \E[1m0.16.0\E[0m\tgolang: 1.26.6\tgo-sdk: v1.2.0'
    + echo $'Version: \E[1m0.16.0\E[0m\tgolang: 1.26.6\tgo-sdk: v1.2.0'
    + case " $v " in
    Version: 0.16.0	golang: 1.26.6	go-sdk: v1.2.0
    + zcat -f /builddir/build/BUILD/tea-0.16.0-build/BUILDROOT/usr/share/man/man1/tea.1.gz
    + grep -q '^\.TH ' tea.1.check
    ++ wc -l
    + test 3995 -gt 20
    ++ jobs -p
    + exit 0
    Processing files: tea-0.16.0-2.fc46.x86_64

VERDICT: holds for tea. Copr ran its `%check` in all four chroots of
11357085, and it passed.

gitea-cli came in with b272966 (2026-11-18), with `%check` from its first
build on.

OBSERVED for gitea-cli (read on 2026-11-18 from `builder-live.log` of all
four chroots of its first Copr build): 11357213, gitea-cli 2.0.0-1,
succeeded 2026-11-18. In each chroot the binary, gt, prints 2.0.0, the man
page has 35334 lines, the bash, zsh and fish completions each register
themselves for gt, and the section ends in `+ exit 0`. From
fedora-rawhide-x86_64:

    Executing(%check): /bin/sh -e /var/tmp/rpm-tmp.3niYNe
    + umask 022
    + cd /builddir/build/BUILD/gitea-cli-2.0.0-build
    [the compiler flag exports]
    + cd packaging-devtools-2.0.0
    ++ /builddir/build/BUILD/gitea-cli-2.0.0-build/BUILDROOT/usr/bin/gt --version
    + v=$'gt version 2.0.0 (2026-11-18)\nhttps://gitea.com/gitea/cli/releases/tag/v2.0.0\nbuilt with go1.27.4'
    gt version 2.0.0 (2026-11-18)
    https://gitea.com/gitea/cli/releases/tag/v2.0.0
    built with go1.27.4
    + echo $'gt version 2.0.0 (2026-11-18)\nhttps://gitea.com/gitea/cli/releases/tag/v2.0.0\nbuilt with go1.27.4'
    + case " $v " in
    + zcat -f /builddir/build/BUILD/gitea-cli-2.0.0-build/BUILDROOT/usr/share/man/man1/gt.1.gz
    + grep -q '^\.TH ' gt.1.check
    ++ wc -l
    + test 35334 -gt 20
    + grep -q -- '-F __start_gt gt$' /builddir/build/BUILD/gitea-cli-2.0.0-build/BUILDROOT/usr/share/bash-completion/completions/gt
    + grep -qx '#compdef gt' /builddir/build/BUILD/gitea-cli-2.0.0-build/BUILDROOT/usr/share/zsh/site-functions/_gt
    + grep -q '^complete -c gt ' /builddir/build/BUILD/gitea-cli-2.0.0-build/BUILDROOT/usr/share/fish/vendor_completions.d/gt.fish
    + RPM_EC=0
    ++ jobs -p
    + exit 0
    Processing files: gitea-cli-2.0.0-1.fc46.x86_64

VERDICT: holds for gitea-cli. Copr ran its `%check` in all four chroots of
its first build, and it passed.
