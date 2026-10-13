#!/bin/sh
# Attach the four installer archives and their checksums to an existing GitHub release.
#
# The release workflow builds one archive per target on a matching host, downloads them into one
# directory, and calls this from the only job that holds the write token. Nothing here builds or
# runs the archives.
#
# Spacedock's installer reads releases/latest, one compass_<version>_<os>_<arch>.tar.gz per target
# and a checksums.txt of `sha256  filename` lines, with <version> the tag without its `v`.
#
# Usage: publish-cli.sh <tag> <archive-dir> [--dry-run]
set -eu
tag="${1:?usage: publish-cli.sh <tag> <archive-dir> [--dry-run]}"
dir="${2:?usage: publish-cli.sh <tag> <archive-dir> [--dry-run]}"
dry="${3:-}"
version="${tag#v}"

case "$version" in
*[!0-9.]* | .* | *. | *..* | "") echo "publish-cli.sh: $tag is not a plain X.Y.Z tag" >&2; exit 1 ;;
esac
[ "$(echo "$version" | tr -cd . | wc -c)" -eq 2 ] || { echo "publish-cli.sh: $tag is not a plain X.Y.Z tag" >&2; exit 1; }
[ -d "$dir" ] || { echo "publish-cli.sh: no directory $dir" >&2; exit 1; }
dir="$(cd "$dir" && pwd)"

# Exactly the four expected archives: a missing target would leave installs on that platform
# failing, and a stray file would ship under the release unreviewed.
set --
for target in darwin_arm64 darwin_amd64 linux_arm64 linux_amd64; do
	name="compass_${version}_${target}.tar.gz"
	[ -f "$dir/$name" ] || { echo "publish-cli.sh: missing $name in $dir" >&2; exit 1; }
	set -- "$@" "$name"
done
for found in "$dir"/*; do
	case " $* checksums.txt " in
	*" $(basename "$found") "*) ;;
	*) echo "publish-cli.sh: unexpected file $(basename "$found") in $dir" >&2; exit 1 ;;
	esac
done

if command -v shasum >/dev/null 2>&1; then
	(cd "$dir" && shasum -a 256 "$@" >checksums.txt)
else
	(cd "$dir" && sha256sum "$@" >checksums.txt)
fi

if [ "$dry" = --dry-run ]; then
	echo "would run: gh release upload $tag $* checksums.txt --clobber"
	exit 0
fi
[ -z "$dry" ] || { echo "publish-cli.sh: unknown option $dry" >&2; exit 1; }
# --clobber: a re-run of the release workflow attaches again rather than failing on the first run's files.
(cd "$dir" && gh release upload "$tag" "$@" checksums.txt --clobber)
