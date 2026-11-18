# copr-runs-check

Claim: Copr runs the `%check` section of the syft, grype and grant specs, and
their builds pass with it. tea is the separate entry `copr-runs-check-tea`,
still open: its last Copr build, 0.16.0-1 on 2026-09-10, predates `%check`.

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

The fingerprint in the ledger was taken on 2026-11-18 over `.packit.yaml`'s
`jobs`. The file has not changed since 6587f8e (2026-10-03), before every
build above, and the `%check` sections of all four specs are the same as in
456ed51.

VERDICT: holds for syft, grype and grant. Copr ran their `%check` in every
chroot, and it passed in all 14 builds (56 chroot logs).
