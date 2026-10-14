# Changelog

Which packages, distributions and architectures this repository ships, and
since when. Newest first. Version updates are not listed; each package keeps
them in the `%changelog` of its spec.

A date is the day of the first successful build in the public COPR repository
`gmipf/devtools` (COPR keeps every build), not the day its recipe was
committed.

<!--
scripts/changelog-check.py reads the "Added", "Removed" and "Renamed" lines and
compares them with the recipes in fedora/; it runs in scripts/lint.sh, so in CI
and in the pre-commit hook. Their form:

  - Added `pkg`, `pkg` and `pkg` on Fedora. Free text.
  - Removed `pkg` on Fedora. Free text.
  - Renamed `old` to `new` on Fedora. Free text.

Distributions: Fedora (fedora/). A line may wrap; continuation lines are
indented. Every other line is free text and is not checked; scripts/texts-check.py
live makes sure every Fedora release and architecture COPR builds for is named.
-->

## 2026-08-27

- First Fedora 45 builds. COPR's `fedora-all` target adds and drops releases
  on its own; this log notes the first build.

## 2026-07-01

- Added `grype` and `grant` on Fedora. Anchore's vulnerability scanner and
  license checker.

## 2026-06-24

- Added `syft` on Fedora. Anchore's SBOM generator.

## 2026-06-22

- The COPR repository `gmipf/devtools` starts: Fedora 43, 44 and rawhide,
  x86_64.
- Added `tea` on Fedora. The command-line client for Gitea and Forgejo.
