#!/bin/sh
# Attach the installer archives to an existing GitHub release, built from the tag.
# Usage: publish-cli.sh <tag> [--dry-run]
set -eu
tag="${1:?usage: publish-cli.sh <tag> [--dry-run]}"
dry="${2:-}"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null || { echo "publish-cli.sh: no tag $tag" >&2; exit 1; }
git cat-file -e "$tag:cargento/bin/cargento" 2>/dev/null || { echo "publish-cli.sh: $tag predates bin/cargento; release a tag that contains it" >&2; exit 1; }
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
git archive "$tag" cargento | tar -x -C "$work"
sh "$(dirname "$0")/package-cli.sh" "$work/dist" "$work"
version="$(ls "$work/dist" | sed -n 's/^cargento_\(.*\)_darwin_arm64\.tar\.gz$/\1/p')"
[ "$tag" = "v$version" ] || { echo "publish-cli.sh: $tag must be exactly v$version, the plugin version" >&2; exit 1; }
if [ "$dry" = --dry-run ]; then
	echo "would run: gh release upload $tag $(cd "$work/dist" && ls | tr '\n' ' ')--clobber"
else
	gh release upload "$tag" "$work"/dist/* --clobber
fi
