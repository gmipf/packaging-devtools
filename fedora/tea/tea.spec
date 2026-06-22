# tea ships an official, fully static Go binary per release. We repackage the
# upstream linux-amd64 binary instead of building from source — no Go toolchain
# or vendored modules. Hence x86_64-only and no debuginfo.
%global debug_package %{nil}

Name:           tea
Version:        0.14.1
Release:        2%{?dist}
Summary:        Command-line tool to interact with Gitea and Forgejo

License:        MIT
URL:            https://gitea.com/gitea/tea
# Official upstream prebuilt static binary, VENDORED (committed flat next to this
# spec) so the COPR build is hermetic/offline — the project runs enable_net=off
# and COPR's source build has no network. The upstream-release watcher refreshes
# this file on version bumps. Provenance:
#   %%{url}/releases/download/v%%{version}/%%{name}-%%{version}-linux-amd64.xz
Source0:        %{name}-%{version}-linux-amd64.xz
# LICENSE shipped locally too (flat): the release ships no LICENSE asset and
# gitea.com /raw/ + /archive/ return an HTML challenge. Watcher refreshes via API.
Source1:        LICENSE

# We repackage upstream's amd64 binary -> x86_64 only.
ExclusiveArch:  x86_64

%description
tea is the official command-line client for Gitea and Forgejo. It manages
repositories, issues, pull requests, releases, labels and more from the
terminal, including against self-hosted instances.

%prep
# No upstream tarball: create an empty build dir and bring the local LICENSE in.
%setup -q -c -T
cp -p %{SOURCE1} LICENSE

%build
# Repackaging only — decompress the prebuilt binary.
xz -dc %{SOURCE0} > %{name}
chmod +x %{name}

# Man page: tea generates its own via the hidden `tea man` subcommand (urfave/
# cli-docs, upstream cmd/man.go). Render it straight from the binary we ship — it
# introspects its own command tree, needs no network/config, and is always in
# sync with this exact version. No converter, no vendored doc, no watcher work.
./%{name} man > %{name}.1

%install
install -D -p -m0755 %{name} %{buildroot}%{_bindir}/%{name}
install -D -p -m0644 %{name}.1 %{buildroot}%{_mandir}/man1/%{name}.1

%files
%license LICENSE
%{_bindir}/%{name}
%{_mandir}/man1/%{name}.1*

%changelog
* Mon Jun 22 2026 gmipf <gmipf64@gmail.com> - 0.14.1-2
- Ship a man page, generated at build time from the binary's `tea man` output

* Mon Jun 22 2026 gmipf <gmipf64@gmail.com> - 0.14.1-1
- Initial package: repackage upstream static linux-amd64 binary
