# Security Policy

## Scope

Cargento ships two components that touch the network: the dashboard server
(`cargento/skills/cargento/server.py`), which reads local coding-agent session stores (transcripts,
task files, SQLite databases) and serves them over HTTP; and `notify_hook.py`, the small forwarder a
user wires into their own Claude Code hook settings, which POSTs hook payloads to the dashboard.

The posture rests on two invariants:

1. **Localhost only** — the server binds `127.0.0.1` exclusively, and `notify_hook.py` refuses to
   POST anywhere but loopback, ignores proxy environment variables, and does not follow redirects.
   Session data never leaves the machine.
2. **Read-only against harness stores** — they are opened read-only and never written. The one
   mutating endpoint is `POST /api/notify`, which updates in-memory needs-input state only; it
   writes nothing to disk.

Anything that weakens either invariant — a bind-address escape, file reads outside the documented
store paths and the project-read contract below (however the path was derived), writes to harness
stores, or the hook client reaching a non-loopback destination — is a security bug.

## Project reads (Spacedock stage strips)

One feature reads a path that is not under a store root. When a session declares itself a Spacedock
first officer, Cargento reads the **YAML frontmatter of one workflow `README.md`** so it can show
the workflow's ordered stages. That is the whole of it — no other project file is opened, and no
directory is ever walked.

The path is not guessed. The first officer's own `spacedock status --boot` output, already recorded
in its transcript, names the workflow directory as an absolute path; Cargento uses that value and
nothing else. Before the file is opened, all of the following must hold, and a path failing any one
is skipped silently:

- the directory value is **absolute** and contains no NUL;
- the path is canonicalised with `realpath`, and the README must still resolve **inside** that
  directory (`commonpath` containment), so a swapped entry cannot redirect the read;
- the README is a **regular file and not a symlink** — checked with `lstat`, and opened with
  `O_NOFOLLOW` where the platform has it. Windows has no `O_NOFOLLOW`, so there the guarantee rests
  on the `lstat` classification alone and a racing reparse-point swap could still be followed. That
  is the same unclosable class as the `FILE_SHARE_DELETE` window described in the skill body;
- the frontmatter declares `commissioned-by: spacedock@` — Spacedock's own workflow discriminator.

Hard caps: at most 64 KiB read from the file, 400 frontmatter lines scanned, 32 stage names taken,
and 8 workflows per session. Results are cached on `(realpath, st_mtime_ns, st_size)`, so an
unchanged README costs one `stat` per refresh.

**Only derived scalars reach `/api/data`** — stage names (each validated against Spacedock's
`^[a-z0-9][a-z0-9-]*[a-z0-9]$` grammar), entity slugs, and cycle markers. No file text, no
frontmatter body and no filesystem path is ever published, and the page HTML-escapes every value.
Pass `--no-spacedock` to switch the feature off; the read surface is then exactly the documented
store paths.

## Known and accepted

**Loopback is not a per-user boundary.** Any other account on the same machine can `GET /api/data`
and read every session's titles and prompts, or forge a `POST /api/notify`. The Host, `Sec-Fetch`
and Origin checks defeat browser-based DNS rebinding; they do not defeat a local process. This is
more acute on a shared Linux host than on a personal laptop. The known fix — a per-run bearer token
in a `0600` file plus a random port — is not implemented. Report a *bypass* of the checks that do
exist; the absence of per-user isolation is documented here rather than treated as a new finding.

**`--diagnose` output is sensitive.** It prints the home directory, the interpreter path, the
*values* of the store relocation variables, every candidate store path, and per-path read errors.
Nothing is transmitted — but redact it before pasting it into a public issue.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead:

- Use [GitHub private vulnerability reporting](https://github.com/spacedock-dev/cargento/security/advisories/new), or
- Email dev@reccehq.com with a description and reproduction steps.

You can expect an acknowledgment within a few days. Please allow time for a fix to land and release before public disclosure.

## Supported versions

Only the latest released version of the plugin receives security fixes.
