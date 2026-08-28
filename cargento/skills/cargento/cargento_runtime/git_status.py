"""The end-of-session git probe: one bounded command, two scalars, no pathnames.

This is the only place in the runtime that runs a program inside a directory the
user chose, and `SECURITY.md`'s "Repository git reads (the end-of-session probe)"
section is the contract it implements. The bounds are DEC-3's ruling (Linear
DRC-4122) as amended, not this module's preferences.

Why the argv is a constant and not built per call: both flags are independently
load-bearing, and each disarms exactly one hazard the ruling measured. Re-measured
2026-08-28 at git 2.55.0 across four fresh repositories, one probe each, from an
identical racy-clean state:

- without `--no-optional-locks`, git rewrites `.git/index` to resolve a racy stat,
  which breaks the read-only posture the product states for everything it touches;
- without `-c core.fsmonitor=`, a `core.fsmonitor` script named by the inspected
  repository's own config executes under Cargento's identity.

Neither flag disarms the other's hazard, so neither may be dropped and there is no
fallback to a plain `git status`. `tests/test_git_status.py` asserts both against
real repositories, because these are properties of git rather than of this file.

What leaves this module is `GitStatus` or `None`, and `None` means not probed
rather than clean. Porcelain names paths; those pathnames are counted and dropped
here, and no caller is ever given a way to reach them.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable

# Bound 1 of DEC-3, as amended. A tuple rather than a list so a caller cannot
# append to the argv it was handed.
GIT_STATUS_ARGV: Final[tuple[str, ...]] = (
    "git",
    "-c",
    "core.fsmonitor=",
    "--no-optional-locks",
    "status",
    "--porcelain",
)


@dataclass(frozen=True)
class GitStatus:
    """What one probe observed. Frozen: a reading, not a mutable row field."""

    dirty: bool
    # Porcelain ENTRIES, not files. Git collapses an untracked directory into one
    # entry, so a new directory holding three files counts 1. Every rendering of
    # this number has to say entries, or it is a file count under a false name.
    changed: int


def probe(
    cwd: str,
    *,
    timeout_sec: float,
    runner: Callable[..., Any] = subprocess.run,
) -> GitStatus | None:
    """Run the one bounded command in `cwd`, or return None having run nothing.

    None is the whole of the disclosure for a row that was not probed, and it
    covers every cause: the directory is gone or is not a repository, git is not
    on PATH, the probe timed out, or git refused. `False` is never substituted for
    it — a confident clean over no evidence is the DRC-4101 failure, one field
    over.

    `stdin` is closed rather than inherited so that a repository configured to ask
    for a credential or an askpass answer cannot block the probe until its
    timeout; the timeout would catch it, but a probe that reliably burns its full
    budget is a probe that stalls its own worker.
    """
    if not os.path.isdir(cwd):
        return None
    try:
        result = runner(
            # The fixed argv above: no shell, no interpolation, nothing from the payload.
            GIT_STATUS_ARGV,
            cwd=cwd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout_sec,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        # OSError covers git absent from PATH and a cwd that vanished between the
        # isdir check and the spawn; SubprocessError covers the timeout. Caught as
        # one because every one of them means the same published thing: not probed.
        return None
    if getattr(result, "returncode", 1) != 0:
        # Not a repository, or a repository this process may not read. stderr is
        # deliberately not read, logged or returned: it quotes pathnames.
        return None
    return _reading(getattr(result, "stdout", b""))


def _reading(stdout: object) -> GitStatus:
    """Count porcelain entries. The only thing that ever looks at the output."""
    if isinstance(stdout, str):
        raw = stdout.encode("utf-8", "replace")
    elif isinstance(stdout, (bytes, bytearray)):
        raw = bytes(stdout)
    else:
        raw = b""
    # One entry per line. Counted rather than parsed, because the parse would have
    # to hold pathnames and nothing published needs them.
    entries = sum(1 for line in raw.split(b"\n") if line.strip())
    return GitStatus(dirty=entries > 0, changed=entries)
