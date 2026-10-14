## Install

```sh
sudo dnf copr enable gmipf/devtools
sudo dnf install tea syft grype grant
```

## Tools

- **tea** — the official command-line client for [Gitea](https://gitea.com) and
  [Forgejo](https://forgejo.org): manage repositories, issues, pull requests,
  releases and labels from the terminal, including against self-hosted instances.
  Start with `tea --help`, then add a login with `tea login add`.
- **syft** — [Anchore](https://github.com/anchore/syft)'s tool for generating a
  Software Bill of Materials (SBOM) from container images and filesystems, in SPDX,
  CycloneDX or its native format. Start with `syft --help`, e.g. `syft scan alpine:latest`.
- **grype** — [Anchore](https://github.com/anchore/grype)'s vulnerability scanner for
  container images, filesystems and SBOMs; pairs with syft-generated SBOMs. Start with
  `grype --help`, e.g. `grype alpine:latest`.
- **grant** — [Anchore](https://github.com/anchore/grant)'s license checker for
  container images, SBOMs and filesystems, evaluated against a configurable policy.
  Start with `grant --help`, e.g. `grant list alpine:latest` or `grant check ./sbom.json`.

## Updates

Each tool is packaged via [Packit](https://packit.dev) and delivered through this
Copr, so every build is a clean, versioned RPM (no `:latest` drift) and
`sudo dnf upgrade` keeps it current.

## Upstream

- tea — https://gitea.com/gitea/tea
- syft — https://github.com/anchore/syft
- grype — https://github.com/anchore/grype
- grant — https://github.com/anchore/grant

## Packaging recipes

Spec files and build configuration live at https://github.com/gmipf/packaging-devtools.
Hobby project, unsupported third-party recipes, not affiliated with any upstream tool author.
