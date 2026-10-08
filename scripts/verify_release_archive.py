#!/usr/bin/env python3
"""Prove the exact release commit's `git archive` before `stable` can move.

Usage:
    python3 scripts/verify_release_archive.py --repo . --commit <final> \
        --verified <verified target> --version 0.2.0

The Release workflow verifies the frontend in a job that holds no credentials and
then bumps version fields in a job that does. The bump commit is therefore a tree
nobody built, and this is the check that it still ships what was verified. It
runs in the privileged job with Python only: nothing here starts Node, pnpm or any
frontend dependency, and the smoke runs in a scrubbed environment with a throwaway
home and an empty PATH.

Checks, in order, each of which stops the release on failure:

    versions   the three owned manifests carry the tag's version, in parity
    changes    the release commit is the verified commit or its direct child and
               differs from it in the version manifests alone
    bundle     the React bundle files in the archive equal the verified blobs
    inventory  the archive's own runtime inventory check passes
    page       Python's integrity check accepts the archived React page
    launch     the archived launcher starts and diagnoses with --frontend react

The bundle is version-independent: build provenance carries no release version, so
a bump never changes it, and a changed bundle byte means a rebuild nobody verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

PLUGIN = "cargento"
SKILL = "cargento/skills/cargento"
WEB = f"{SKILL}/cargento_runtime/web"
BUNDLE_FILES = (
    f"{WEB}/react.html",
    f"{WEB}/react.integrity.json",
    f"{WEB}/react-licenses.txt",
    f"{WEB}/vendor/xterm.js",
    f"{WEB}/vendor/xterm.css",
)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
# -I for the page probe: no user site, no PYTHON* variables, no script directory,
# so the only code that can import is the interpreter's own plus the archive path
# the probe inserts itself. server.py cannot use -I (it imports its sibling
# package from the script directory, which -I removes), so the launch uses the two
# flags that remove the same ambient inputs without removing that directory.
PAGE_FLAGS = ["-I"]
LAUNCH_FLAGS = ["-E", "-s"]
TIMEOUT = 120
GIT = shutil.which("git") or "git"
PAGE_PROBE = """
import hashlib, json, sys
sys.path.insert(0, sys.argv[1])
from cargento_runtime.web import page
data = page.load_frontend_page("react")
print(json.dumps({"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}))
"""


class ArchiveError(Exception):
    """A release archive failed a check; the message is safe to print."""


@dataclass
class Report:
    checks: list[str] = field(default_factory=list)


def git_bytes(repo: Path, *args: str) -> bytes:
    result = subprocess.run(  # noqa: S603 -- argv is a list built from validated values
        [GIT, "-C", str(repo), *args], capture_output=True, check=False, timeout=TIMEOUT
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        message = f"git {args[0]} failed: {detail}"
        raise ArchiveError(message)
    return result.stdout


def git_text(repo: Path, *args: str) -> str:
    return git_bytes(repo, *args).decode("utf-8").strip()


def full_sha(repo: Path, name: str, value: str) -> str:
    if not FULL_SHA.fullmatch(value):
        message = f"{name} must be a full lowercase commit SHA"
        raise ArchiveError(message)
    return git_text(repo, "rev-parse", "--verify", f"{value}^{{commit}}")


def isolated_env(home: Path) -> dict[str, str]:
    """Nothing ambient: no PATH entry to resolve Node, no real home, no secrets."""
    empty = home / "no-executables"
    empty.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": str(empty),
        "HOME": str(home),
        "USERPROFILE": str(home),
        "CARGENTO_HOME": str(home / "state"),
        "PYTHONNOUSERSITE": "1",
        "LC_ALL": "C.UTF-8",
    }


def run_python(
    home: Path, args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 -- the interpreter running this script
            [sys.executable, *args],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd or home,
            env=isolated_env(home),
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        message = f"python {' '.join(args[:2])} exceeded {TIMEOUT} seconds"
        raise ArchiveError(message) from exc


def tail(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout + result.stderr).strip()[-600:]


def _safe_target(name: str, root: Path) -> Path:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        message = f"archive member {name!r} escapes the extraction directory"
        raise ArchiveError(message)
    return root.joinpath(*pure.parts)


def extract_archive(archive: Path, destination: Path) -> None:
    """Extract files, directories and in-tree relative symlinks; refuse the rest.

    `tarfile.extractall` filters differ across the supported Python floor, and an
    archive of a commit that could hold a hostile member is the case this exists
    for, so the member policy is spelled out here instead of inherited.
    """
    root = destination.resolve()
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        for member in members:
            target = _safe_target(member.name, root)
            if member.issym():
                link = PurePosixPath(member.linkname)
                resolved = os.path.normpath(os.path.join(os.path.dirname(target), member.linkname))
                inside = Path(resolved).is_relative_to(root)
                if link.is_absolute() or not inside:
                    message = f"archive link {member.name!r} points outside the tree"
                    raise ArchiveError(message)
            elif not (member.isfile() or member.isdir()):
                message = f"archive member {member.name!r} is not a file, directory or link"
                raise ArchiveError(message)
        for member in members:
            target = _safe_target(member.name, root)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.issym():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(member.linkname)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:  # pragma: no cover -- isfile() members always open
                    message = f"archive member {member.name!r} is unreadable"
                    raise ArchiveError(message)
                target.write_bytes(source.read())
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def verified_manifest_paths(repo: Path, verified: str, scratch: Path) -> list[str]:
    """The paths a bump may touch, read from the verified tree's own script.

    Taken from the verified commit, not the release commit: a release commit that
    widened the list in order to change more would otherwise bless itself.
    """
    script = scratch / "verified-bump" / "scripts" / "bump_version.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(git_bytes(repo, "show", f"{verified}:scripts/bump_version.py"))
    home = scratch / "home"
    home.mkdir(exist_ok=True)
    result = run_python(home, [*PAGE_FLAGS, str(script), "--paths"])
    if result.returncode:
        message = f"the verified tree's bump script could not list its paths: {tail(result)}"
        raise ArchiveError(message)
    return result.stdout.split()


def check_versions(tree: Path, paths: list[str], version: str) -> None:
    found: dict[str, str] = {}
    for relative in paths:
        try:
            manifest = json.loads((tree / relative).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            message = f"{relative} is missing or unreadable in the archive"
            raise ArchiveError(message) from exc
        found[relative] = str(manifest.get("version")) if isinstance(manifest, dict) else ""
    if len(set(found.values())) != 1:
        message = f"version fields are not in parity: {found}"
        raise ArchiveError(message)
    carried = next(iter(found.values()))
    if carried != version:
        message = f"manifests carry {carried} but the tag's version is {version}"
        raise ArchiveError(message)


def check_changes(repo: Path, commit: str, verified: str, allowed: list[str]) -> None:
    if commit != verified and git_text(repo, "rev-parse", f"{commit}^") != verified:
        message = "the release commit must be the verified commit or its direct child"
        raise ArchiveError(message)
    changed = git_text(repo, "diff", "--name-only", verified, commit).splitlines()
    extra = sorted(set(changed) - set(allowed))
    if extra:
        message = f"release commit changed files beyond the version manifests: {extra}"
        raise ArchiveError(message)


def check_bundle(repo: Path, tree: Path, verified: str) -> None:
    for relative in BUNDLE_FILES:
        expected = hashlib.sha256(git_bytes(repo, "cat-file", "blob", f"{verified}:{relative}"))
        try:
            actual = hashlib.sha256((tree / relative).read_bytes())
        except OSError as exc:
            message = f"{relative} is missing from the archive"
            raise ArchiveError(message) from exc
        if actual.hexdigest() != expected.hexdigest():
            message = f"{relative} changed after verification"
            raise ArchiveError(message)


def check_inventory(tree: Path, home: Path) -> None:
    result = run_python(
        home,
        [
            *PAGE_FLAGS,
            str(tree / "scripts/validate_plugins.py"),
            "--runtime-files",
            str(tree / PLUGIN),
        ],
    )
    if result.returncode:
        message = f"runtime inventory failed: {tail(result)}"
        raise ArchiveError(message)


def check_page(repo: Path, tree: Path, verified: str, home: Path) -> None:
    result = run_python(home, [*PAGE_FLAGS, "-c", PAGE_PROBE, str(tree / SKILL)])
    if result.returncode:
        message = f"react page failed its integrity check: {tail(result)}"
        raise ArchiveError(message)
    try:
        served = json.loads(result.stdout.strip().splitlines()[-1])["sha256"]
    except (IndexError, KeyError, ValueError) as exc:
        message = f"react page probe returned no digest: {tail(result)}"
        raise ArchiveError(message) from exc
    expected = hashlib.sha256(git_bytes(repo, "cat-file", "blob", f"{verified}:{BUNDLE_FILES[0]}"))
    if served != expected.hexdigest():
        message = "react page integrity check passed on bytes other than the verified document"
        raise ArchiveError(message)


def check_launch(tree: Path, home: Path) -> None:
    result = run_python(
        home, [*LAUNCH_FLAGS, str(tree / SKILL / "server.py"), "--frontend", "react", "--diagnose"]
    )
    if result.returncode:
        message = f"archived launcher failed --frontend react --diagnose: {tail(result)}"
        raise ArchiveError(message)


def verify_archive(repo: Path, commit: str, verified: str, version: str) -> Report:
    """Run every check against `git archive <commit>`; raise ArchiveError on the first failure."""
    if not SEMVER.fullmatch(version):
        message = f"version {version!r} is not strict semver"
        raise ArchiveError(message)
    commit = full_sha(repo, "commit", commit)
    verified = full_sha(repo, "verified", verified)
    scratch = Path(tempfile.mkdtemp(prefix="cargento-release-archive-"))
    report = Report()
    try:
        archive = scratch / "release.tar"
        git_bytes(repo, "archive", "--format=tar", "-o", str(archive), commit)
        tree = scratch / "tree"
        tree.mkdir()
        extract_archive(archive, tree)
        home = scratch / "home"
        home.mkdir()
        paths = verified_manifest_paths(repo, verified, scratch)
        check_versions(tree, paths, version)
        report.checks.append("versions")
        check_changes(repo, commit, verified, paths)
        report.checks.append("changes")
        check_bundle(repo, tree, verified)
        report.checks.append("bundle")
        check_inventory(tree, home)
        report.checks.append("inventory")
        check_page(repo, tree, verified, home)
        report.checks.append("page")
        check_launch(tree, home)
        report.checks.append("launch")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", type=Path, default=Path())
    parser.add_argument("--commit", required=True)
    parser.add_argument("--verified", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        report = verify_archive(args.repo, args.commit, args.verified, args.version)
    except ArchiveError as exc:
        print(f"::error::release archive proof failed: {exc}")
        return 1
    print(f"Release archive proof passed: {', '.join(report.checks)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
