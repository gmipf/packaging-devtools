# Creating the Copr project `gmipf/devtools`

One-time setup of the public Copr project this repo publishes to. Public tools only —
no private/closed-source artifacts ever land in a public Copr (see `CLAUDE.md`).

`copr-cli` is already installed and `~/.config/copr` exists locally, so the CLI path
below is the fast one. The web UI path is given as an equivalent fallback.

---

## 1. Verify the API token

The token in `~/.config/copr` expires periodically. Check it works (never `cat` the
file — it's a secret):

```sh
copr-cli whoami        # should print: gmipf
```

If it errors with an auth/expiry message, regenerate the token:

1. Open <https://copr.fedorainfracloud.org/api/> (logged in with your FAS account).
2. Copy the shown config block into `~/.config/copr`.
3. `chmod 600 ~/.config/copr`

---

## 2. Create the project

```sh
copr-cli create devtools \
  --chroot fedora-43-x86_64 \
  --chroot fedora-44-x86_64 \
  --chroot fedora-rawhide-x86_64 \
  --description "RPM builds of public CLI / infra tools, kept current via Packit. Enable with: dnf copr enable gmipf/devtools" \
  --instructions "sudo dnf copr enable gmipf/devtools && sudo dnf install <tool>" \
  --enable-net off \
  --appstream off \
  --follow-fedora-branching on
```

Settings rationale:

| Flag | Value | Why |
|------|-------|-----|
| `--chroot` | `fedora-43/44-x86_64`, `fedora-rawhide-x86_64` | Mirrors the sibling project `gmipf/media-preservation` (active Fedora releases + rawhide). Add arches/releases as needed (see §6). |
| `--enable-net` | `off` | Builds get **no** network — and neither does Copr's **source** build (where Packit runs `create-archive`). So we **vendor everything** flat in each tool's dir: dependency trees *and* prebuilt upstream binaries/`Source0` (committed, like `LICENSE`). Nothing is fetched at build time; the release watcher refreshes vendored sources where the network is reliable. `enable_net` only opens Fedora mirrors anyway, not arbitrary hosts — so turning it on wouldn't reliably fetch external sources and only hurts reproducibility. |
| `--appstream` | `off` | Skip AppStream metadata generation — faster builds; CLI tools don't ship it. |
| `--follow-fedora-branching` | `on` | When rawhide branches into a new Fedora release, the chroot is added automatically. |

> Pick chroots deliberately. List what's available with `copr-cli list-chroots`
> (or the copr MCP `copr_list_mock_chroots`). aarch64 can be added later per tool.

**Web UI equivalent:** <https://copr.fedorainfracloud.org/coprs/gmipf/> → **New Project** →
name `devtools`, tick the Fedora chroots, set Description/Instructions, leave "Enable
internet during build" **off**, tick "Follow Fedora branching".

---

## 3. Let Packit build here (two grants, BOTH critical)

Auto-builds come from the Packit service. Two **independent** Copr-side grants are
required — miss either and Packit-triggered builds end as `neutral`/failed before any
RPM is produced. Both are independent of the GitHub token used to push the repo.

**3a — builder permission.** Packit builds under its own Copr account (`packit`);
grant it the **builder** role on your project:

```sh
copr-cli edit-permissions --builder packit gmipf/devtools
```

(Web UI: project → **Permissions** → add user `packit` → Builder: *Approved*.)

**3b — allow the git-forge project (easy to miss).** Copr also gatekeeps *which*
git-forge repo may drive builds here. Without this, builds fail immediately with
*"Your git-forge project is not allowed to use the configured `gmipf/devtools` Copr
project"* — even though 3a is granted:

```sh
copr-cli modify gmipf/devtools --packit-forge-project-allowed github.com/gmipf/packaging-devtools
```

Wildcards work (e.g. `github.com/gmipf/*`). Verify:

```sh
curl -sg "https://copr.fedorainfracloud.org/api_3/project?ownername=gmipf&projectname=devtools" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('packit_forge_projects_allowed'))"
# -> ['github.com/gmipf/packaging-devtools']
```

(Web UI: project → **Settings → Packit** → *Packit allowed forge projects*.)

---

## 4. Verify

```sh
copr-cli get-package gmipf/devtools --name tea 2>/dev/null || echo "(no packages yet — expected)"
```

Project page (canonical, user-scoped URLs — `gmipf/devtools/...`, not the generic
`/coprs/add/`):

- Overview: <https://copr.fedorainfracloud.org/coprs/gmipf/devtools/>
- Builds:   <https://copr.fedorainfracloud.org/coprs/gmipf/devtools/builds/>
- Settings: <https://copr.fedorainfracloud.org/coprs/gmipf/devtools/edit/>
- Repo:     <https://copr.fedorainfracloud.org/coprs/gmipf/devtools/repo/fedora-43/>

---

## 5. How it connects (after the project exists)

- **`.packit.yaml`** points each `copr_build` job at `owner: gmipf`, `project: devtools`
  (or a per-tool override → a thematic Copr). On an upstream release, Packit builds
  the changed package straight into this project.
- **`scripts/build-tool.sh <tool>`** fires a single manual build safely (NEVRA
  auto-bump guard) into the same project — the only supported by-hand trigger.
- **End users** install with `sudo dnf copr enable gmipf/devtools && sudo dnf install <tool>`,
  and `dnf upgrade` then tracks new versions automatically.

---

## 6. Adding chroots later

```sh
copr-cli modify devtools --chroot fedora-44-x86_64        # add a release
copr-cli modify devtools --chroot fedora-43-aarch64       # add an arch
```

`modify` replaces the chroot set with the union you pass plus existing ones via the web
UI; to be safe, list current chroots first with
`copr-cli get gmipf/devtools` (web Settings shows the checkbox state).
