# grant ships official, fully static Go binaries per release (goreleaser). We
# repackage the upstream linux_amd64 binary instead of building from source — no
# Go toolchain or vendored modules, and COPR's source build has no network
# anyway (enable_net=off). Hence x86_64-only and no debuginfo.
%global debug_package %{nil}

Name:           grant
Version:        0.6.7
Release:        1%{?dist}
Summary:        Check container image, SBOM and filesystem licenses against a policy

License:        Apache-2.0
URL:            https://github.com/anchore/grant
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

# grant has no native man-page generator (cobra, no `man`/`docs` subcommand), so
# we render one from its --help/--version output at build time.
BuildRequires:  help2man

%description
grant (by Anchore) checks the licenses of container images, SBOM documents and
filesystems against a configurable policy. It surfaces the licenses of every
detected package, integrates with syft-generated SBOMs, and is used to enforce
license-compliance rules in software supply-chain pipelines.

%prep
# Upstream tarball is flat (grant, LICENSE, README.md, CHANGELOG.md — no top dir):
# create the build dir ourselves and unpack into it.
%setup -q -c -T
tar xzf %{SOURCE0}

%build
chmod +x %{name}
# Normalise the bundled doc/license modes so %doc/%license always install them
# world-readable regardless of upstream's archive perms (grype's sibling tarball
# ships CHANGELOG.md 0600 — guard against the same here on future releases).
chmod 0644 README.md CHANGELOG.md LICENSE
# Shell completions: grant is cobra-based and ships no man page generator, but it
# can emit its own completion scripts. Generate them from the exact binary we
# ship so they always match this version (no network/config needed) — the same
# "render docs straight from the shipped binary" approach as syft.
./%{name} completion bash > %{name}.bash
./%{name} completion zsh  > _%{name}
./%{name} completion fish > %{name}.fish

# Man page: rendered from --help/--version of the exact binary we ship (a
# top-level page; per-subcommand detail stays in `grant <cmd> --help`).
# Version-matched by construction, no network — same idea as the completions.
# grant's `--version` prints "grant version X.Y.Z" (unlike syft/grype's bare
# "<tool> X.Y.Z"), which help2man would splice verbatim into the .TH title as
# "grant version X.Y.Z". Feed it just the bare version (still read from the
# shipped binary at build time) so the header reads a clean "grant X.Y.Z".
grant_ver=$(./%{name} --version | awk '{print $NF}')
help2man --no-info --version-string="$grant_ver" \
  --name='check container image, SBOM and filesystem licenses against a policy' \
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
* Wed Jul 01 2026 gmipf <gmipf64@gmail.com> - 0.6.7-1
- Initial package: repackage upstream static linux_amd64 binary (Apache-2.0),
  SHA256-verified against Anchore's signed checksums.txt; ship a help2man-rendered
  man page and bash/zsh/fish completions, all generated from the shipped binary
