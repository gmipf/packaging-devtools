#!/bin/bash
# verify-signed-checksums.sh OWNER/REPO TAG ASSET FILE
#
# FILE must be the release asset ASSET exactly as the GitHub release TAG of
# OWNER/REPO lists it in its checksums.txt, and that checksums.txt must carry
# a valid Sigstore signature from the upstream's own release workflow.
#
# A checksums.txt on its own only shows that the asset arrived intact: whoever
# can swap the asset on the release page can swap the checksums next to it.
# Anchore (syft, grype, grant) signs each release's <repo>_<version>_checksums.txt
# with cosign, keyless, from .github/workflows/release.yaml on main, and
# publishes the bundle next to it as <file>.sigstore.json. With the signature
# checked, an asset or checksums.txt changed after the release, and a
# signature by any other identity, are refused.
#
# Needs cosign (the watchers install it with sigstore/cosign-installer).
set -euo pipefail

if [ $# -ne 4 ]; then
  echo "::error::usage: verify-signed-checksums.sh OWNER/REPO TAG ASSET FILE"
  exit 1
fi
project=$1 tag=$2 asset=$3 file=$4
sums=${project#*/}_${tag#v}_checksums.txt
base=https://github.com/$project/releases/download/$tag
identity=https://github.com/$project/.github/workflows/release.yaml@refs/heads/main
issuer=https://token.actions.githubusercontent.com

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
for f in "$sums" "$sums.sigstore.json"; do
  if ! curl -fsSL "$base/$f" -o "$work/$f"; then
    echo "::error::Could not download $f of $project $tag"
    exit 1
  fi
done

if ! cosign verify-blob --bundle "$work/$sums.sigstore.json" \
    --certificate-identity "$identity" --certificate-oidc-issuer "$issuer" "$work/$sums"; then
  echo "::error::cosign could not verify $sums of $project $tag as signed by $identity — refusing it"
  exit 1
fi

expect=$(awk -v a="$asset" '$2 == a { print $1 }' "$work/$sums")
actual=$(sha256sum "$file" | cut -d' ' -f1)
if [ "$expect" != "$actual" ]; then
  echo "::error::SHA256 mismatch for $asset (want ${expect:-no line for it in $sums}, got $actual) — refusing it"
  exit 1
fi
echo "$asset matches $sums, signed by $identity"
