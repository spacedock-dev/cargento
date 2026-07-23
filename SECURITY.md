# Security Policy

## Scope

Cargento's dashboard server reads local coding-agent session stores (transcripts, task files, SQLite databases) and serves them over HTTP. Its security posture rests on two invariants:

1. **Localhost only** — the server binds `127.0.0.1` exclusively. Session data never leaves the machine.
2. **Read-only** — harness stores are opened read-only; the server never writes to them.

Anything that weakens either invariant — a bind-address escape, request-driven file reads outside the documented store paths, or writes to harness stores — is a security bug.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead:

- Use [GitHub private vulnerability reporting](https://github.com/spacedock-dev/cargento/security/advisories/new), or
- Email dev@reccehq.com with a description and reproduction steps.

You can expect an acknowledgment within a few days. Please allow time for a fix to land and release before public disclosure.

## Supported versions

Only the latest released version of the plugin receives security fixes.
