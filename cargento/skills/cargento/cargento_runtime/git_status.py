"""The end-of-session git probe: one bounded command, two scalars, no pathnames.

This is the only place in the runtime that runs a program inside a directory the
user chose, and `SECURITY.md`'s "Repository git reads (the end-of-session probe)"
section is the contract it implements. The bounds are DEC-3's ruling (Linear
DRC-4122) as amended, not this module's preferences.

Why the argv is a constant and not built per call: all three flags are
independently load-bearing, and each disarms exactly one hazard that was measured.
The first two were re-measured 2026-08-28 at git 2.55.0 across four fresh
repositories, one probe each, from an identical racy-clean state; the third was
measured 2026-09-07 at git 2.55.0 with git-lfs 3.8.0:

- without `--no-optional-locks`, git rewrites `.git/index` to resolve a racy stat,
  which breaks the read-only posture the product states for everything it touches;
- without `-c core.fsmonitor=`, a `core.fsmonitor` script named by the inspected
  repository's own config executes under Cargento's identity;
- without `-c core.hooksPath=/dev/null`, hashing a tracked path whose COMMITTED
  attributes name a filter driver lets that driver install its own hooks: four
  files at mode 0755 — post-checkout, post-commit, post-merge, pre-push — written
  inside a repository the probe was only meant to read. `.git/index` was untouched
  in that arm, so neither of the other two flags sees it.

Neither of the first two disarms the other's hazard, the third disarms one they
both miss, so none may be dropped and there is no fallback to a plain
`git status`. `tests/test_git_status.py` asserts all three against real
repositories, because these are properties of git rather than of this file.

What the third flag does NOT close, measured the same day: the filter driver still
RUNS. A repository whose `.git/config` names a clean filter had that command
executed by one probe. Only the hook installation is suppressed, because git-lfs
asks git where hooks belong and is answered with a path it cannot write. Arbitrary
filter execution needs `.git/config` rather than committed content, which is the
threat model `SECURITY.md` already accepts for `core.fsmonitor`, and that section
states the residual rather than this comment restating it.

`/dev/null` as a hooks path is measured on darwin only. It is a path git cannot
find a hook under on any supported platform, but the suppression itself was
observed here, and `tests/test_git_status.py` skips where the mechanism cannot be
armed rather than passing vacuously.

What leaves this module is `GitStatus` or `None`, and `None` means not probed
rather than clean. Porcelain names paths; those pathnames are counted and dropped
here, and no caller is ever given a way to reach them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

# Bound 1 of DEC-3, as amended. A tuple rather than a list so a caller cannot
# append to the argv it was handed.
#
# `GIT_STATUS_ARGV[0]` stays the bare name because it is what the contract prints
# and what the oracles compare. What actually spawns is `_executable()` below,
# resolved once against a PATH the probe controls: measured 2026-09-07, a bare
# name let ANY empty or relative PATH element before the first real `git` supply
# the binary, and it resolved from the session-supplied directory being probed.
GIT_STATUS_ARGV: Final[tuple[str, ...]] = (
    "git",
    "-c",
    "core.fsmonitor=",
    "-c",
    "core.hooksPath=/dev/null",
    "--no-optional-locks",
    "status",
    "--porcelain",
)


# Removed from the child's environment, not merely ignored by this module. Either
# one redirects git at a different repository entirely: measured 2026-09-07, a
# probe of a CLEAN repository published a dirty reading belonging to another one,
# and a directory that is not a repository at all published it too, so the
# `isdir` gate below does not help.
DETACHING_ENV: Final = ("GIT_DIR", "GIT_WORK_TREE")


def probe_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """The child's environment: the caller's, minus what detaches the reading.

    Kept public and separate so a test can assert the scrub without spawning
    anything, and so the two names above have exactly one place that drops them.

    Every non-absolute PATH element goes, not a named list of them. The named
    list is what this was, and it was wrong: `{"", "."}` reads like the whole of
    the property but a bare `relbin`, `./bin`, `..` and `sub/bin` all survived it
    (DRC-4454, measured 2026-09-07). Any element the resolver would resolve
    against a working directory is untrusted, because the working directory
    during a probe is the session's own and the child's is the directory being
    probed — which is how one relative element let the probed directory supply
    the program.
    """
    scrubbed = {key: value for key, value in environ.items() if key not in DETACHING_ENV}
    path = scrubbed.get("PATH", "")
    if path:
        kept = [part for part in path.split(os.pathsep) if os.path.isabs(part)]
        scrubbed["PATH"] = os.pathsep.join(kept)
    return scrubbed


def _executable(environ: Mapping[str, str]) -> str | None:
    """Where `git` is, resolved once against the scrubbed PATH, or None.

    None means the same published thing as every other refusal in this module:
    not probed. `shutil.which` is given the scrubbed PATH explicitly rather than
    reading the ambient one, because the ambient one is what the hijack uses.

    The absoluteness check is here AS WELL AS in the scrub, and the duplication is
    the point rather than an oversight: the scrub is one filter and that filter has
    already been wrong once, so a future change to it cannot reopen the hijack
    while this end refuses too. This is also the end that holds if `which` is ever
    handed a PATH from anywhere but `probe_environment`.
    """
    resolved = shutil.which("git", path=environ.get("PATH"))
    if resolved is None or not os.path.isabs(resolved):
        return None
    return resolved


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
    environ = probe_environment(os.environ)
    resolved = _executable(environ)
    if resolved is None:
        return None
    try:
        result = runner(
            # The fixed argv above, with argv[0] replaced by the resolved absolute
            # path: no shell, no interpolation, nothing from the payload.
            #
            # The child's OUTPUT is not capped, and that is deferred rather than
            # overlooked: `subprocess.run` reads to EOF and takes no size limit, so
            # a cap means `Popen` plus a bounded read loop, and seven tests inject
            # through this `runner=` seam — two of them pinning `env`, `stdin` and
            # `timeout` as keyword arguments, so a rewrite has to preserve the
            # kwarg surface and not only the argv. What bounds the output today is
            # `timeout_sec` on how long git has to produce it, and `_reading`
            # counting one line at a time rather than materialising every line.
            (resolved, *GIT_STATUS_ARGV[1:]),
            cwd=cwd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout_sec,
            check=False,
            env=environ,
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
    #
    # One line at a time rather than `raw.split(b"\n")`: re-measured with
    # tracemalloc at N=20000 on Python 3.12.13, the split allocates a flat ~41 B
    # per entry ON TOP OF each line's own bytes — 1.69 MB beside an 880 KB output
    # at a 43-byte porcelain line, and 1.20x to 5.07x the output as path length
    # falls from 204 characters to 9, so there is no single multiple to quote.
    # This loop's own peak is one line (271 B in that arm), and pathnames still
    # reach nothing but `strip`.
    entries = 0
    start = 0
    size = len(raw)
    while start < size:
        stop = raw.find(b"\n", start)
        if stop < 0:
            stop = size
        if raw[start:stop].strip():
            entries += 1
        start = stop + 1
    return GitStatus(dirty=entries > 0, changed=entries)
