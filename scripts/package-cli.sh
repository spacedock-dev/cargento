#!/bin/sh
# Build the release archives the spacedock installer reads: the cargento/ plugin
# tree with bin/cargento, one per OS/arch name, plus checksums.txt.
# Usage: package-cli.sh [out-dir] [source-root]
set -eu
out="${1:-dist}"
src="${2:-.}"
version="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$src/cargento/.claude-plugin/plugin.json" | head -n 1)"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
for target in darwin_arm64 darwin_amd64 linux_arm64 linux_amd64; do
	(cd "$src" && COPYFILE_DISABLE=1 tar -czf "$out/cargento_${version}_${target}.tar.gz" --exclude='*/tests' --exclude='__pycache__' cargento)
done
(cd "$out" && shasum -a 256 cargento_*.tar.gz > checksums.txt)
echo "$out: cargento $version"
