# packaging-devtools

RPM packages of public command-line and infrastructure tools for Fedora,
repackaged from each upstream's own release binaries and published in the
[`gmipf/devtools`][copr] COPR repository (x86_64). This repository holds only
the recipes; the tools come from their upstream projects.

## Tools

| Tool | What it is |
|---|---|
| [gitea-cli](https://gitea.com/gitea/cli) | the official Gitea command-line client, `gt`; successor of tea |
| [tea](https://gitea.com/gitea/tea) | command-line client for Gitea and Forgejo; archived upstream |
| [syft](https://github.com/anchore/syft) | SBOM generator (SPDX, CycloneDX) |
| [grype](https://github.com/anchore/grype) | vulnerability scanner for images, filesystems and SBOMs |
| [grant](https://github.com/anchore/grant) | license checker for images, SBOMs and filesystems |
| [actionlint](https://github.com/rhysd/actionlint) | static checker for GitHub Actions workflow files |

A watcher per tool checks upstream every day; a new release is packaged and
built on COPR automatically, and `dnf upgrade` picks it up. What each package
tracks, how it is built and checked: [docs/how-it-works.md](docs/how-it-works.md).
Which package arrived when: [CHANGELOG.md](CHANGELOG.md).

[copr]: https://copr.fedorainfracloud.org/coprs/gmipf/devtools/

## Install

```sh
sudo dnf copr enable gmipf/devtools
sudo dnf install gitea-cli tea syft grype grant actionlint
```

## Status

Unsupported third-party recipes. Personal hobby project, not affiliated with
Fedora or with any upstream tool author.
