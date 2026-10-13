# packaging-tools

RPM packaging recipes for **public** CLI / infra tools, published to Copr and kept
current automatically via [Packit](https://packit.dev/) + per-tool upstream watchers.
Install a tool with `dnf copr enable gmipf/devtools` then `dnf install <tool>`.

> Only **public** upstream tools live here. Nothing private or closed-source.

## Layout

The directory tree encodes only what produces *files* — **format → app**. Everything
volatile (which Copr project, trigger branch, watcher schedule) lives in config, never
in the path. That's what keeps the repo sane once it holds many apps.

```
.
├── .packit.yaml            # one packages: block per app (paths: + specfile_path)
├── packaging.conf          # tool registry consumed by scripts/build-tool.sh
├── scripts/build-tool.sh   # safe manual Copr build (NEVRA auto-bump + branch-scoped trigger)
├── scripts/copr-reconcile.py  # safety net: re-pushes a trigger whose build never reached Copr
└── fedora/                 # format level (sibling debian/, arch/ … added on demand)
    └── <app>/              # self-contained: <app>.spec + flat sources + manpage/icon/state
```

| Axis | Lives in | Example |
|------|----------|---------|
| Distro / format | path top level | `fedora/` · later `debian/` |
| App | path under format | `fedora/tea/` |
| **Copr project (routing)** | `packaging.conf` 4th field | default `gmipf/devtools`, overridable per app |

A second distro for the same app is a sibling recipe dir (`debian/<app>/`), not a move.
Re-homing an app to a thematic Copr (`gmipf/<theme>`) is a one-line config change — no
files move.

## Adding a tool

Four additions, nothing else changes:

1. `fedora/<app>/<app>.spec` (+ flat sources, manpage, watcher state file).
2. A `packages:` block in `.packit.yaml` (`paths: fedora/<app>/`, `specfile_path: <app>.spec`,
   a `get-current-version` action that reads the spec and a `create-archive` action that
   matches the vendored Source0 by its form, never by its version) and a `copr_build` job
   with `branch: ^build-<app>$`, `update_release: false` and `owner`/`project`.
   `scripts/test-copr-reconcile.py` checks that it routes exactly like `packaging.conf` and
   that Packit leaves the NEVRA alone; `scripts/test-packit-config.py` runs both actions
   through a simulated upstream bump.
3. One line in `packaging.conf`:
   `TOOLS[<app>]="<copr-package>|fedora/<app>/<app>.spec|build-<app>[|<copr-project>]"`.
4. An upstream-release watcher workflow.

## Building

Upstream releases trigger Copr builds automatically. To fire a build by hand:

```sh
scripts/build-tool.sh <app>
```

It refuses to republish an identical NEVRA (which would break `dnf` clients), auto-bumping
the bare-`N` Release if needed, and routes through the per-tool `build-<app>` branch so
only that one package rebuilds.

A watcher pushes the bumped spec to `main` first and the trigger branch second. If only the
second push fails, the next watcher run sees nothing to do, so every push is retried
(`scripts/push-retry.sh`), and every six hours `copr-reconcile.yml` compares each spec on
`main` with Copr: a version Copr never received gets its trigger re-pushed. It never
re-pushes a version Copr has seen in any state, so the same NEVRA is never built twice. A
failed build, Copr ahead of `main`, or an unanswered API turns the run red instead.
Run `scripts/copr-reconcile.py` for the same report locally (`--heal` only in CI).

## Checks

`scripts/lint.sh` holds every lint rule (whitespace, shellcheck, ruff, yamllint, actionlint,
`packit validate`, rpmlint with a declared list of expected findings) and runs the offline
test suites (`scripts/test-*.py`). CI runs it with every tool installed (`check-repo.yml`,
on push, on pull requests and daily); locally it runs as a pre-commit hook, skipping tools
that are not installed:

```sh
git config core.hooksPath .githooks
```

Every spec has a `%check` that runs the binary it ships: it must report exactly the packaged
version, and the man page and completions rendered from it must not be empty.
`scripts/rpmbuild-check.sh` builds every spec that way in CI (`check-repo.yml`, job
`rpmbuild`), since a push to `main` builds nothing on Copr; the script's header shows the
`docker run` line for a local run.

A check that cannot fail looks exactly like one that passes. `scripts/selftest.py` plants a
defect for every check above (every lint rule, every test-suite decision, the hook, each
spec's `%check` with `--rpmbuild`) in a throwaway copy and requires each to turn red for
its own reason; CI runs it in both jobs.

## Tools

| Tool | Description | Status |
|------|-------------|--------|
| [tea](fedora/tea/) | Gitea / Forgejo CLI | live |
| [syft](fedora/syft/) | Anchore SBOM generator (SPDX / CycloneDX) | live |
| [grype](fedora/grype/) | Anchore vulnerability scanner (images / filesystems / SBOMs) | live |
| [grant](fedora/grant/) | Anchore license checker (images / SBOMs / filesystems) | live |
