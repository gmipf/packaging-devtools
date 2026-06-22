# tea ships an official, fully static Go binary per release. We repackage the
# upstream linux-amd64 binary instead of building from source — no Go toolchain
# or vendored modules. Hence x86_64-only and no debuginfo.
%global debug_package %{nil}

Name:           tea
Version:        0.14.1
Release:        1%{?dist}
Summary:        Command-line tool to interact with Gitea and Forgejo

License:        MIT
URL:            https://gitea.com/gitea/tea
# Official upstream prebuilt static binary (repackaged, not built here).
Source0:        tea-0.14.1-linux-amd64.xz
# LICENSE shipped locally (flat source): gitea.com /raw/ and /archive/ return an
# HTML challenge in the build env and the release has no LICENSE asset. The
# version watcher refreshes it from the API on upstream bumps.
Source1:        LICENSE

# We repackage upstream's amd64 binary -> x86_64 only.
ExclusiveArch:  x86_64

%description
tea is the official command-line client for Gitea and Forgejo. It manages
repositories, issues, pull requests, releases, labels and more from the
terminal, including against self-hosted instances.

%prep
# No upstream tarball: create an empty build dir and bring the local LICENSE in.
%setup -q -c -T -n packaging-devtools-0.14.1
cp -p %{SOURCE1} LICENSE

%build
# Repackaging only — decompress the prebuilt binary.
xz -dc %{SOURCE0} > %{name}

%install
install -D -p -m0755 %{name} %{buildroot}%{_bindir}/%{name}

%files
%license LICENSE
%{_bindir}/%{name}

%changelog
* Mon Jun 22 2026 gmipf <gmipf64@gmail.com> - 0.14.1-1
- Initial package: repackage upstream static linux-amd64 binary
