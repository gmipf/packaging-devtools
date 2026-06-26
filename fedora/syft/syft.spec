# syft ships official, fully static Go binaries per release (goreleaser). We
# repackage the upstream linux_amd64 binary instead of building from source — no
# Go toolchain or vendored modules, and COPR's source build has no network
# anyway (enable_net=off). Hence x86_64-only and no debuginfo.
%global debug_package %{nil}

Name:           syft
Version:        1.46.0
Release:        1%{?dist}
Summary:        CLI tool for generating a Software Bill of Materials (SBOM)

License:        Apache-2.0
URL:            https://github.com/anchore/syft
# Official upstream release tarball, VENDORED verbatim (committed flat next to
# this spec) so the COPR build is hermetic/offline — the project runs
# enable_net=off and COPR's source build has no network. It is byte-for-byte the
# upstream artifact: its SHA256 is exactly the one published in Anchore's
# cosign-signed checksums.txt for this release. The upstream-release watcher
# refreshes it on version bumps (re-verifying that published checksum). It
# bundles LICENSE/README/CHANGELOG, so no separate doc source is needed.
# Provenance:
#   %%{url}/releases/download/v%%{version}/%%{name}_%%{version}_linux_amd64.tar.gz
Source0:        %{name}_%{version}_linux_amd64.tar.gz

# We repackage upstream's amd64 binary -> x86_64 only.
ExclusiveArch:  x86_64

# syft has no native man-page generator (cobra, no `man`/`docs` subcommand), so
# we render one from its --help/--version output at build time.
BuildRequires:  help2man

%description
syft (by Anchore) generates a Software Bill of Materials (SBOM) from container
images and filesystems. It detects packages and their metadata across many
ecosystems and emits SPDX, CycloneDX or its native format, and is widely used
as the SBOM stage in software supply-chain and vulnerability-scanning pipelines.

%prep
# Upstream tarball is flat (syft, LICENSE, README.md, CHANGELOG.md — no top dir):
# create the build dir ourselves and unpack into it.
%setup -q -c -T
tar xzf %{SOURCE0}

%build
chmod +x %{name}
# Shell completions: syft is cobra-based and ships no man page generator, but it
# can emit its own completion scripts. Generate them from the exact binary we
# ship so they always match this version (no network/config needed) — the same
# "render docs straight from the shipped binary" approach as tea's man page.
./%{name} completion bash > %{name}.bash
./%{name} completion zsh  > _%{name}
./%{name} completion fish > %{name}.fish

# Man page: rendered from --help/--version of the exact binary we ship (a
# top-level page; per-subcommand detail stays in `syft <cmd> --help`).
# Version-matched by construction, no network — same idea as the completions.
help2man --no-info --name='generate a Software Bill of Materials (SBOM)' \
  ./%{name} > %{name}.1

%install
install -D -p -m0755 %{name} %{buildroot}%{_bindir}/%{name}
install -D -p -m0644 %{name}.1 %{buildroot}%{_mandir}/man1/%{name}.1
install -D -p -m0644 %{name}.bash %{buildroot}%{_datadir}/bash-completion/completions/%{name}
install -D -p -m0644 _%{name} %{buildroot}%{_datadir}/zsh/site-functions/_%{name}
install -D -p -m0644 %{name}.fish %{buildroot}%{_datadir}/fish/vendor_completions.d/%{name}.fish

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/%{name}
%{_mandir}/man1/%{name}.1*
%{_datadir}/bash-completion/completions/%{name}
%{_datadir}/zsh/site-functions/_%{name}
%{_datadir}/fish/vendor_completions.d/%{name}.fish

%changelog
* Fri Jun 26 2026 gmipf <gmipf64@gmail.com> - 1.46.0-1
- Automated sync to upstream syft release v1.46.0; re-vendored linux_amd64 tarball (SHA256-verified), Release reset to 1.

* Wed Jun 24 2026 gmipf <gmipf64@gmail.com> - 1.45.1-1
- Initial package: repackage upstream static linux_amd64 binary (Apache-2.0),
  SHA256-verified against Anchore's signed checksums.txt; ship a help2man-rendered
  man page and bash/zsh/fish completions, all generated from the shipped binary
