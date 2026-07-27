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

Anything that weakens either invariant — a bind-address escape, request-driven file reads outside
the documented store paths, writes to harness stores, or the hook client reaching a non-loopback
destination — is a security bug.

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
