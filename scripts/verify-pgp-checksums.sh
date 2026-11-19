#!/bin/bash
# verify-pgp-checksums.sh OWNER/REPO TAG ASSET FILE
#
# FILE must be the release asset ASSET exactly as the gitea.com release TAG of
# OWNER/REPO lists it in its checksums.txt, and that checksums.txt must carry
# a valid OpenPGP signature by Gitea's release key.
#
# A checksums.txt on its own only shows that the asset arrived intact: whoever
# can swap the asset on the release page can swap the checksums next to it.
# Gitea (tea, gitea-cli) signs each release's checksums.txt as
# checksums.txt.sig with the key of "Teabot <teabot@gitea.io>". The key is
# fetched by its fingerprint from keys.openpgp.org, where Gitea's
# documentation points; a fingerprint names exactly one key, and the signature
# must come from that key (or one of its subkeys). A renewed expiry or a
# revocation arrives with the key: only a good signature by an unrevoked,
# unexpired key passes.
#
# Needs gpg and gpgv (both on GitHub's ubuntu-latest).
set -euo pipefail

if [ $# -ne 4 ]; then
  echo "::error::usage: verify-pgp-checksums.sh OWNER/REPO TAG ASSET FILE"
  exit 1
fi
project=$1 tag=$2 asset=$3 file=$4
base=https://gitea.com/$project/releases/download/$tag
fpr=7C9E68152594688862D62AF62D9AE806EC1592E2

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
for f in checksums.txt checksums.txt.sig; do
  if ! curl -fsSL "$base/$f" -o "$work/$f"; then
    echo "::error::Could not download $f of $project $tag"
    exit 1
  fi
done
if ! curl -fsSL "https://keys.openpgp.org/vks/v1/by-fingerprint/$fpr" -o "$work/key.asc"; then
  echo "::error::Could not download Gitea's release key $fpr from keys.openpgp.org"
  exit 1
fi
# gpgv reads only a binary keyring.
gpg --batch --quiet --homedir "$work" --dearmor < "$work/key.asc" > "$work/key.gpg"

# Not gpgv's exit code: its status lines must show a GOOD signature (not by an
# expired or revoked key), and VALIDSIG must end in the primary fingerprint
# asked for.
status=$(gpgv --status-fd 1 --keyring "$work/key.gpg" "$work/checksums.txt.sig" "$work/checksums.txt" 2>&1) || true
if ! awk -v fpr="$fpr" '$1 == "[GNUPG:]" && $2 == "GOODSIG" { good = 1 }
                        $1 == "[GNUPG:]" && $2 == "VALIDSIG" && $NF == fpr { valid = 1 }
                        END { exit !(good && valid) }' <<< "$status"; then
  echo "$status"
  echo "::error::checksums.txt of $project $tag is not signed by Gitea's release key $fpr — refusing it"
  exit 1
fi

expect=$(awk -v a="$asset" '$2 == a { print $1 }' "$work/checksums.txt")
actual=$(sha256sum "$file" | cut -d' ' -f1)
if [ "$expect" != "$actual" ]; then
  echo "::error::SHA256 mismatch for $asset (want ${expect:-no line for it in checksums.txt}, got $actual) — refusing it"
  exit 1
fi
echo "$asset matches checksums.txt, signed by Gitea's release key $fpr"
