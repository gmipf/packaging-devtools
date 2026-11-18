# gitea-cli ships an official, fully static Go binary per release. We repackage
# the upstream linux-amd64 binary instead of building from source -- no Go
# toolchain or vendored modules, and COPR's source build has no network anyway
# (enable_net=off). Hence x86_64-only and no debuginfo.
%global debug_package %{nil}

# The package carries upstream's project name, as in every distribution that
# ships it; the command it installs is gt.
%global cmd gt

Name:           gitea-cli
Version:        2.0.0
Release:        1%{?dist}
Summary:        Official command-line client for Gitea (gt), the successor of tea

License:        MIT
URL:            https://gitea.com/gitea/cli
# Official upstream prebuilt static binary, VENDORED (committed flat next to this
# spec) so the COPR build is hermetic/offline -- the project runs enable_net=off
# and COPR's source build has no network. Its SHA256 is the one upstream
# publishes next to it (<asset>.sha256). The upstream-release watcher refreshes
# this file on version bumps, re-verifying that checksum. Provenance:
#   %%{url}/releases/download/v%%{version}/%%{name}-%%{version}-linux-amd64.xz
Source0:        %{name}-%{version}-linux-amd64.xz
# LICENSE shipped locally too (flat): the release ships no LICENSE asset, so it
# was taken from the v2.0.0 tag once. It's MIT and stable -- the watcher leaves
# it untouched; refresh it by hand if upstream ever relicenses.
Source1:        LICENSE

# We repackage upstream's amd64 binary -> x86_64 only.
ExclusiveArch:  x86_64

# Fedora's package gt (a modified TiMidity MIDI player) installs /usr/bin/gt and
# gt.1 as well; the two cannot be installed side by side.
Conflicts:      gt

%description
gitea-cli is the official command-line client for Gitea; its command is gt.
It manages repositories, issues, pull requests, releases, labels, milestones,
Actions secrets and variables and more, against gitea.com or a self-hosted
instance, and gives scripts stable, machine-readable JSON output. It succeeds
tea, which upstream archived.

%prep
# No upstream tarball: create an empty build dir and bring the local LICENSE in.
%setup -q -c -T
cp -p %{SOURCE1} LICENSE

%build
# Repackaging only -- decompress the prebuilt binary.
xz -dc %{SOURCE0} > %{cmd}
chmod +x %{cmd}

# Man page and shell completions: gt renders both itself (`gt man`, the full
# manual of every subcommand; `gt completion <shell>`). Render them straight
# from the binary we ship -- no network or config needed, and always in sync
# with this exact version.
./%{cmd} man > %{cmd}.1
./%{cmd} completion bash > %{cmd}.bash
./%{cmd} completion zsh  > _%{cmd}
./%{cmd} completion fish > %{cmd}.fish

%install
install -D -p -m0755 %{cmd} %{buildroot}%{_bindir}/%{cmd}
install -D -p -m0644 %{cmd}.1 %{buildroot}%{_mandir}/man1/%{cmd}.1
# Completions are looked up by the command's name, not the package's.
install -D -p -m0644 %{cmd}.bash %{buildroot}%{_datadir}/bash-completion/completions/%{cmd}
install -D -p -m0644 _%{cmd} %{buildroot}%{_datadir}/zsh/site-functions/_%{cmd}
install -D -p -m0644 %{cmd}.fish %{buildroot}%{_datadir}/fish/vendor_completions.d/%{cmd}.fish

%check
# Selftest of what this package ships, run on the builder (the binary is static
# Go and needs nothing from the buildroot): it must start and report exactly the
# version this spec packages -- a stale or swapped vendored binary fails here --
# and the docs rendered from it must not be silently empty: a generator that
# falls back to nothing still leaves a green build. The man page is already
# compressed by now, hence zcat -f.
v=$(%{buildroot}%{_bindir}/%{cmd} --version)
echo "$v"
case " $v " in
  *[!0-9.]%{version}[!0-9.]*) ;;
  *) echo "error: %{cmd} --version does not report %{version}" >&2; exit 1 ;;
esac
zcat -f %{buildroot}%{_mandir}/man1/%{cmd}.1* > %{cmd}.1.check
# gt's generator writes no version into .TH, so only presence and size.
grep -q '^\.TH ' %{cmd}.1.check
test "$(wc -l < %{cmd}.1.check)" -gt 20
# Each completion must register itself for the command gt: "gt" alone would
# also match bash's -gt.
grep -q -- '-F __start_%{cmd} %{cmd}$' %{buildroot}%{_datadir}/bash-completion/completions/%{cmd}
grep -qx '#compdef %{cmd}' %{buildroot}%{_datadir}/zsh/site-functions/_%{cmd}
grep -q '^complete -c %{cmd} ' %{buildroot}%{_datadir}/fish/vendor_completions.d/%{cmd}.fish

%files
%license LICENSE
%{_bindir}/%{cmd}
%{_mandir}/man1/%{cmd}.1*
%{_datadir}/bash-completion/completions/%{cmd}
%{_datadir}/zsh/site-functions/_%{cmd}
%{_datadir}/fish/vendor_completions.d/%{cmd}.fish

%changelog
* Wed Nov 18 2026 gmipf <gmipf64@gmail.com> - 2.0.0-1
- Initial package: repackage upstream static linux-amd64 binary of gt, the
  successor of tea
