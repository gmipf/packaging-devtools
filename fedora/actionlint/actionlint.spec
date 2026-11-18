# actionlint ships official, fully static Go binaries per release (goreleaser).
# We repackage the upstream linux_amd64 binary instead of building from source --
# no Go toolchain or vendored modules, and COPR's source build has no network
# anyway (enable_net=off). Hence x86_64-only and no debuginfo.
%global debug_package %{nil}

Name:           actionlint
Version:        1.7.12
Release:        1%{?dist}
Summary:        Static checker for GitHub Actions workflow files

License:        MIT
URL:            https://github.com/rhysd/actionlint
# Official upstream release tarball, VENDORED verbatim (committed flat next to
# this spec) so the COPR build is hermetic/offline -- the project runs
# enable_net=off and COPR's source build has no network. It is byte-for-byte the
# upstream artifact: its SHA256 is exactly the one published in the release's
# checksums.txt (which upstream does not sign). The upstream-release watcher
# refreshes it on version bumps (re-verifying that published checksum). It
# bundles LICENSE.txt, README.md, docs/ and a ready man page, so no separate doc
# source is needed.
# Provenance:
#   %%{url}/releases/download/v%%{version}/%%{name}_%%{version}_linux_amd64.tar.gz
Source0:        %{name}_%{version}_linux_amd64.tar.gz

# We repackage upstream's amd64 binary -> x86_64 only.
ExclusiveArch:  x86_64

# actionlint runs shellcheck on every `run:` script and pyflakes on every
# Python `run:` script when they are on PATH, and silently skips those checks
# when they are not. Pull them in by default; a minimal install can drop them.
Recommends:     ShellCheck
Recommends:     python3-pyflakes

%description
actionlint is a static checker for GitHub Actions workflow files. It checks
workflow syntax, types in ${{ }} expressions, action inputs and outputs,
job dependencies, runner labels, cron syntax, glob patterns and more, and it
lints the shell and Python scripts in run: steps through shellcheck and
pyflakes when they are installed.

%prep
# Upstream tarball is flat (actionlint, LICENSE.txt, README.md, docs/, man/ -- no
# top dir): create the build dir ourselves and unpack into it.
%setup -q -c -T
tar xzf %{SOURCE0}

%build
chmod +x %{name}
# Normalise the bundled doc/license modes so %%doc/%%license always install them
# world-readable regardless of upstream's archive perms.
chmod 0644 README.md LICENSE.txt docs/*.md man/%{name}.1
# actionlint ships its own man page (man/actionlint.1); nothing to render.

%install
install -D -p -m0755 %{name} %{buildroot}%{_bindir}/%{name}
install -D -p -m0644 man/%{name}.1 %{buildroot}%{_mandir}/man1/%{name}.1

%check
# Selftest of what this package ships, run on the builder (the binary is static
# Go and needs nothing from the buildroot): it must start and report exactly the
# version this spec packages -- a stale or swapped vendored binary fails here --
# it must actually lint (a clean workflow passes, a broken one is caught for its
# own reason), and the bundled man page must not be empty. The man page is
# already compressed by now, hence zcat -f.
v=$(%{buildroot}%{_bindir}/%{name} -version | head -1)
echo "$v"
if [ "$v" != "%{version}" ]; then
  echo "error: %{name} -version reports '$v', not %{version}" >&2
  exit 1
fi
printf 'on: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n' > good.yml
printf 'on: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ${{ nosuch.ctx }}\n' > bad.yml
%{buildroot}%{_bindir}/%{name} -shellcheck= -pyflakes= good.yml
if %{buildroot}%{_bindir}/%{name} -shellcheck= -pyflakes= -oneline bad.yml > bad.out; then
  echo "error: %{name} passed a workflow with an undefined context" >&2
  exit 1
fi
cat bad.out
grep -q 'undefined variable "nosuch"' bad.out
zcat -f %{buildroot}%{_mandir}/man1/%{name}.1* > %{name}.1.check
grep -q '^\.TH "ACTIONLINT"' %{name}.1.check
test "$(wc -l < %{name}.1.check)" -gt 20

%files
%license LICENSE.txt
%doc README.md docs
%{_bindir}/%{name}
%{_mandir}/man1/%{name}.1*

%changelog
* Wed Nov 18 2026 gmipf <gmipf64@gmail.com> - 1.7.12-1
- Initial package: repackage upstream static linux_amd64 binary (MIT),
  SHA256-verified against the release's checksums.txt; ship upstream's man page
  and docs; recommend ShellCheck and pyflakes for the run: script checks.
