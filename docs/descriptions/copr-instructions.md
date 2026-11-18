## Install

```sh
sudo dnf copr enable gmipf/devtools
sudo dnf install gitea-cli tea syft grype grant actionlint
```

## Tools

- **gitea-cli** — the official command-line client for [Gitea](https://gitea.com);
  its command is `gt`. It manages repositories, issues, pull requests, releases,
  labels, milestones and Actions secrets and variables, on gitea.com or a
  self-hosted instance, and gives scripts stable JSON output. It is the successor
  of tea. Start with `gt auth login`, then `gt --help`. Fedora's unrelated package
  `gt` (a MIDI player) has a command of the same name, so the two cannot be
  installed together.
- **tea** — the command-line client for [Gitea](https://gitea.com) and
  [Forgejo](https://forgejo.org): manage repositories, issues, pull requests,
  releases and labels from the terminal, including against self-hosted instances.
  Start with `tea --help`, then add a login with `tea login add`. Upstream
  archived tea on 2026-10-29 in favour of gitea-cli; this package stays at its
  last release.
- **syft** — [Anchore](https://github.com/anchore/syft)'s tool for generating a
  Software Bill of Materials (SBOM) from container images and filesystems, in SPDX,
  CycloneDX or its native format. Start with `syft --help`, e.g. `syft scan alpine:latest`.
- **grype** — [Anchore](https://github.com/anchore/grype)'s vulnerability scanner for
  container images, filesystems and SBOMs; pairs with syft-generated SBOMs. Start with
  `grype --help`, e.g. `grype alpine:latest`.
- **grant** — [Anchore](https://github.com/anchore/grant)'s license checker for
  container images, SBOMs and filesystems, evaluated against a configurable policy.
  Start with `grant --help`, e.g. `grant list alpine:latest` or `grant check ./sbom.json`.
- **actionlint** — [rhysd](https://github.com/rhysd/actionlint)'s static checker for
  GitHub Actions workflow files: syntax, the types in `${{ }}` expressions, action inputs,
  job dependencies, runner labels and cron schedules. It checks `run:` scripts through
  ShellCheck and pyflakes, which the package recommends. Run `actionlint` without
  arguments in a repository to check its `.github/workflows/`; see `actionlint --help`.

## Updates

Each tool is packaged via [Packit](https://packit.dev) and delivered through this
Copr, so every build is a clean, versioned RPM (no `:latest` drift) and
`sudo dnf upgrade` keeps it current.

## Upstream

- gitea-cli — https://gitea.com/gitea/cli
- tea — https://gitea.com/gitea/tea
- syft — https://github.com/anchore/syft
- grype — https://github.com/anchore/grype
- grant — https://github.com/anchore/grant
- actionlint — https://github.com/rhysd/actionlint

## Packaging recipes

Spec files and build configuration live at https://github.com/gmipf/packaging-devtools.
Hobby project, unsupported third-party recipes, not affiliated with any upstream tool author.
