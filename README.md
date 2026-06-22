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
2. A `packages:` block in `.packit.yaml` (`paths: fedora/<app>/`, `specfile_path: <app>.spec`).
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

## Tools

| Tool | Description | Status |
|------|-------------|--------|
| [tea](fedora/tea/) | Gitea / Forgejo CLI | in progress (first package) |
