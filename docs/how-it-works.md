# How it works

Back to the [README](../README.md).

## What each package tracks

| Package | Upstream | Watcher | What is vendored |
|---|---|---|---|
| tea | [gitea/tea](https://gitea.com/gitea/tea) releases | `watch-tea-releases.yml` | the static `linux-amd64` binary, checked against its `.sha256` |
| syft | [anchore/syft](https://github.com/anchore/syft) releases | `watch-syft-releases.yml` | the `linux_amd64` tarball, checked against the release's `checksums.txt` |
| grype | [anchore/grype](https://github.com/anchore/grype) releases | `watch-grype-releases.yml` | the same way as syft |
| grant | [anchore/grant](https://github.com/anchore/grant) releases | `watch-grant-releases.yml` | the same way as syft |

Every package is the upstream binary, repackaged: COPR builds offline, so the
release asset is committed next to the spec (`fedora/<app>/`) and nothing is
fetched at build time. The man page (and for syft, grype and grant the shell
completions) is rendered from the binary during the build. Each spec's `%check`
runs the binary it ships: it must report exactly the packaged version, and what
was rendered from it must not be empty.

## Automation

- **Watchers** (`watch-<app>-releases.yml`, once a day): on a new upstream
  release they download the asset, verify its checksum and that it is an ELF
  binary, set the spec to the new version with `Release: 1`, push that to
  `main`, and then force-push the trigger branch `build-<app>`.
- **Packit** builds one package per trigger branch: every `copr_build` job in
  `.packit.yaml` listens on exactly one `build-<app>` branch, so a push to `main`
  builds nothing and a release of one tool rebuilds no other. All jobs set
  `update_release: false`, so the published NEVRA is exactly the spec's.
- **Safety net** (`copr-reconcile.yml`, every six hours): if a watcher pushed
  `main` but its trigger push was lost, the next watcher run sees nothing to do.
  Every push is therefore retried (`scripts/push-retry.sh`), and the reconciler
  compares each spec on `main` with COPR: a version COPR never received gets its
  trigger re-pushed. It never re-pushes a version COPR has seen in any state, so
  the same NEVRA is never built twice; a failed build, COPR ahead of `main`, or
  an unanswered API turns the run red instead. `scripts/copr-reconcile.py` gives
  the same report locally (`--heal` only in CI).
- **Checks** (`check-repo.yml`, on push, on pull requests and every day): the
  jobs `lint` and `rpmbuild` (see [Checks](#checks)), `docs-gate` and
  `live-texts` (see [The texts](#the-texts)). The daily run matters: the
  watchers push with the built-in `GITHUB_TOKEN`, which starts no other
  workflow, so their spec edits are checked by the next scheduled run.

### The texts

Recipes move and texts stay behind, so both directions are checked:

- `scripts/docs-gate.py`: a commit that changes a recipe (`fedora/`),
  `packaging.conf`, `.packit.yaml` or a workflow also changes a text (README,
  `CHANGELOG.md`, `docs/`), or says why not in a trailer in the last paragraph
  of its message: `Docs-unchanged: <why, in a few words>`. It runs as the
  `commit-msg` hook and in `check-repo.yml` (job `docs-gate`) over every pushed
  commit; `scripts/build-tool.sh` gives its auto-bump commit the trailer.
- `scripts/texts-check.py offline` (in `scripts/lint.sh`): every package is
  named in the README, on this page and in the COPR texts, and every workflow on
  this page.
- `scripts/texts-check.py live` (job `live-texts`): the GitHub About and the
  COPR Description and Installation Instructions equal their copies in
  [docs/descriptions/](descriptions/README.md), and `CHANGELOG.md` names every
  Fedora release and architecture COPR builds for.
- `scripts/changelog-check.py` (in `scripts/lint.sh`): the `Added`, `Removed`
  and `Renamed` lines of `CHANGELOG.md`, replayed, end in exactly the packages
  `fedora/` builds. The log lists milestones only (a package, a release, an
  architecture); version updates stay in each spec's `%changelog`.

## Layout

The directory tree encodes only what produces *files*: **format → app**.
Everything volatile (which COPR project, trigger branch, watcher schedule) lives
in config, never in the path.

```
.
├── .packit.yaml            # one packages: block per app (paths: + specfile_path)
├── packaging.conf          # tool registry consumed by scripts/build-tool.sh
├── scripts/build-tool.sh   # safe manual COPR build (NEVRA auto-bump + branch-scoped trigger)
├── scripts/copr-reconcile.py  # safety net: re-pushes a trigger whose build never reached COPR
└── fedora/                 # format level (sibling debian/, arch/ … added on demand)
    └── <app>/              # self-contained: <app>.spec + flat sources + watcher state
```

| Axis | Lives in | Example |
|------|----------|---------|
| Distro / format | path top level | `fedora/` · later `debian/` |
| App | path under format | `fedora/tea/` |
| **COPR project (routing)** | `packaging.conf` 4th field | default `gmipf/devtools`, overridable per app |

A second distro for the same app is a sibling recipe dir (`debian/<app>/`), not
a move. Re-homing an app to a thematic COPR (`gmipf/<theme>`) is a one-line
config change; no files move.

## Adding a tool

Only public upstream tools belong here. The additions, nothing else changes:

1. `fedora/<app>/<app>.spec` (+ flat sources and the watcher state file
   `.upstream-tag`).
2. A `packages:` block in `.packit.yaml` (`paths: fedora/<app>/`,
   `specfile_path: <app>.spec`, a `get-current-version` action that reads the
   spec and a `create-archive` action that matches the vendored Source0 by its
   form, never by its version) and a `copr_build` job with
   `branch: ^build-<app>$`, `update_release: false` and `owner`/`project`.
   `scripts/test-copr-reconcile.py` checks that it routes exactly like
   `packaging.conf` and that Packit leaves the NEVRA alone;
   `scripts/test-packit-config.py` runs both actions through a simulated
   upstream bump.
3. One line in `packaging.conf`:
   `TOOLS[<app>]="<copr-package>|fedora/<app>/<app>.spec|build-<app>[|<copr-project>]"`.
4. An upstream-release watcher workflow, added to the `UPSTREAM` table of
   `scripts/test-watchers.py`.
5. The texts: an `Added` line in `CHANGELOG.md` (dated by the first successful
   COPR build), the README table and install line, this page, and the COPR
   texts in `docs/descriptions/`, which are then published (see its README).
   The lint and the live check name whatever is missing.

The one-time COPR project setup (Packit's builder permission, the allowed
forge project): [copr-setup.md](copr-setup.md).

## Building

Upstream releases trigger COPR builds automatically. To fire a build by hand:

```sh
scripts/build-tool.sh <app>
```

It refuses to republish an identical NEVRA (which would break `dnf` clients),
auto-bumping the bare-`N` Release if needed, and routes through the per-tool
`build-<app>` branch so only that one package rebuilds.

## Checks

`scripts/lint.sh` holds every lint rule (whitespace, shellcheck, ruff, yamllint,
actionlint, `packit validate`, rpmlint with a declared list of expected
findings, the offline text checks) and runs the offline test suites
(`scripts/test-*.py`). CI runs it with every tool installed (`check-repo.yml`,
job `lint`); locally it runs as a pre-commit hook, skipping tools that are not
installed, next to the `commit-msg` hook:

```sh
git config core.hooksPath .githooks
```

`scripts/rpmbuild-check.sh` builds every spec with its `%check` in CI (job
`rpmbuild`), since a push to `main` builds nothing on COPR; the script's header
shows the `docker run` line for a local run.

A check that cannot fail looks exactly like one that passes.
`scripts/selftest.py` plants a defect for every check above (every lint rule,
every test-suite decision, both hooks, each spec's `%check` with `--rpmbuild`)
in a throwaway copy and requires each to turn red for its own reason; CI runs it
in both jobs.

What only the real services can show (how Packit routes a push, what COPR runs,
what the reconciler does on GitHub) is in `proofs/ledger.tsv`: observed once,
with the evidence in `proofs/` and a fingerprint of the files it rests on.
`scripts/test-proofs.py` (run by `lint.sh`) turns red when such a file changes
while the entry still claims the old observation.
