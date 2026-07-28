# Installation design

## One owned runtime

The standalone CLI lives under Cargento-owned user data, not inside a harness cache. Each release
archive contains the repository's authored `cargento/` tree. The installer puts it under a versioned
`releases/` directory, activates it through a stable `current` link, and writes a small launcher to
the user's bin directory.

This keeps the runtime source aligned with the plugin without making the CLI depend on Claude. A
Claude cache can move, be pruned, or contain another plugin version without breaking the launcher.
Release directories are immutable in normal use. A rerun reuses a complete directory and repairs
the activation link or launcher.

## Distribution and trust boundary

GitHub Releases are the phase-one distribution channel. The release workflow builds the runtime
archive from the released commit, normalizes archive metadata for deterministic output, renders the
tag and filenames into `install.sh`, and uploads a SHA-256 checksum beside it. A resumed workflow
rebuilds and replaces the same three assets.

The installer downloads both files from the exact tag, checks the digest, and requires every archive
member to be a regular file or directory beneath the expected root. It then extracts with the
preflighted `tar` and `gzip` commands, only into a temporary directory, before activating the
release. SHA-256 detects corruption or an asset mismatch. It does not provide an independent
signature because the archive and checksum are controlled by the same GitHub release boundary.

## Claude state is an external contract

Claude owns its marketplace and plugin state. The installer reads that state from the Claude CLI's
JSON output and mutates it only through Claude commands. It requires the `spacedock` marketplace to
point at `spacedock-dev/marketplace`, rejects a same-name collision, and verifies an enabled
`cargento@spacedock` identity after setup.

The marketplace selects the plugin version. Its metadata can lag the runtime release, so version
equality is not part of the phase-one contract. The complete result is exact identity plus enabled
state. This also keeps the installer independent of undocumented cache layouts.

## Partial installation

CLI activation happens before Claude setup. If Claude fails, the verified CLI stays installed and
the installer reports a partial result. Rerunning the same command is the repair path. Runtime,
marketplace, and plugin checks are idempotent, so repair needs no manual cleanup.

## Rejected expansions

Discovering `server.py` in Claude's versioned cache was smaller, but it made the standalone command
depend on a harness-owned implementation detail. A general per-harness adapter framework, generated
marketplace, signing system, PyPI package, Homebrew formula, update command, and uninstaller would
add distribution surfaces before phase one needs them. Native Windows also needs its own launcher
and PowerShell semantics, so it remains a separate design problem.
