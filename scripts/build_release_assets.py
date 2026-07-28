#!/usr/bin/env python3
"""Build deterministic Cargento runtime and installer release assets."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import stat
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "cargento"
INSTALLER_TEMPLATE = ROOT / "scripts/install.sh.in"
STRICT_TAG = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
RELEASE_BASE = "https://github.com/spacedock-dev/cargento/releases/download"


def normalized_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Return deterministic metadata for a runtime archive member."""
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    if info.isdir():
        info.mode = 0o755
    elif info.isfile():
        info.mode = 0o755 if info.mode & 0o111 else 0o644
    return info


def build_archive(destination: Path) -> None:
    """Write the repository's authored Cargento tree as a deterministic tarball."""
    with (
        destination.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as bundle,
    ):
        bundle.add(
            RUNTIME_ROOT,
            arcname="cargento",
            recursive=True,
            filter=normalized_tar_info,
        )


def build_assets(tag: str, output_dir: Path) -> tuple[Path, Path, Path]:
    """Build and return the installer, runtime archive, and checksum paths."""
    match = STRICT_TAG.fullmatch(tag)
    if match is None:
        raise ValueError(f"tag {tag!r} is not strict semver")
    version = ".".join(match.groups())
    archive_name = f"cargento-runtime-{version}.tar.gz"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / archive_name
    checksum = output_dir / f"{archive_name}.sha256"
    installer = output_dir / "install.sh"

    build_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive_name}\n")
    rendered = (
        INSTALLER_TEMPLATE.read_text()
        .replace("@CARGENTO_TAG@", tag)
        .replace("@CARGENTO_VERSION@", version)
        .replace("@CARGENTO_ARCHIVE@", archive_name)
        .replace("@CARGENTO_RELEASE_BASE@", f"{RELEASE_BASE}/{tag}")
    )
    installer.write_text(rendered)
    installer.chmod(installer.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return installer, archive, checksum


def main() -> int:
    """Build release assets from command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        assets = build_assets(args.tag, args.output_dir)
    except ValueError as error:
        parser.error(str(error))
    for asset in assets:
        print(asset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
