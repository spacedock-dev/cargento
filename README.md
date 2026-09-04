# Cargento

[![Validate](https://github.com/spacedock-dev/cargento/actions/workflows/validate.yml/badge.svg)](https://github.com/spacedock-dev/cargento/actions/workflows/validate.yml)
[![Quality Gate](https://github.com/spacedock-dev/cargento/actions/workflows/quality-gate.yml/badge.svg)](https://github.com/spacedock-dev/cargento/actions/workflows/quality-gate.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

Agnostic agent cartography and visualization.

Run as many coding agents as you like. Cargento tells you which ones need you, which ones are fine,
and when it is safe to walk away. One local screen, every harness you use, and nothing leaves your
machine that you cannot switch off.

It answers five questions, in the order a working day hits them. Which of my agents are running.
What is each one doing, and when should I come back. Is anything waiting on me. Will I hit the quota
wall before the work finishes. Did anything die quietly.
[What Cargento promises](docs/promise-map.md) states each answer, names the shipped capability
behind it, and says where it stops.

Under that, Cargento maps live coding-agent activity on your machine into a single local dashboard.
It shows sessions, subagents, task progress, turn ETAs, quota windows, and token output rate across
ten harnesses: Claude Code, Codex, Pi, Gemini CLI, Antigravity CLI, GitHub Copilot CLI, OpenCode,
Cursor CLI, Goose, and Factory Droid. Gemini CLI stopped serving consumer accounts in June 2026 and
Antigravity CLI succeeds it there, but enterprise and API-key use continues, so that row reads
either historical or live sessions depending on the account.

This repo contains one plugin, `cargento`, the agent cartography dashboard skill.

---

## 1. How to set up

### Prerequisites

- Python 3.11+. The server is stdlib-only, so there is nothing to install alongside it.
- To install it as a plugin: Codex, Claude Code, Antigravity/AGY, or Gemini CLI.

You do not need all four. The dashboard maps every harness it finds on the machine regardless of
which one launched it, and it runs standalone with no client installed at all:

```bash
python3 cargento/skills/cargento/server.py --port 4553 --daemon
```

`--daemon` detaches so the dashboard keeps running after this shell exits. Stop it with `--stop`;
drop `--daemon` to run it in the foreground instead.

### Claude Code installation

Cargento is listed in the shared Spacedock marketplace, so if you already have that marketplace you
only need the second line.

```bash
# Add the Spacedock marketplace (one-time setup, shared with the other Spacedock plugins)
claude plugin marketplace add spacedock-dev/marketplace

# Install the cargento plugin
claude plugin install cargento@spacedock
```

Restart Claude Code after installation.

### Antigravity / AGY installation

```bash
# From a local checkout, install the native AGY plugin
agy plugin install "$PWD/cargento"
```

Restart AGY after installation.

### Gemini CLI installation

```bash
# From a local checkout, install the native Gemini CLI extension
gemini extensions install "$PWD/cargento-gemini"
```

Restart Gemini CLI after installation.

Gemini installs from its own directory rather than from `cargento/`. Both Claude Code and Gemini CLI
load extension hooks from `<root>/hooks/hooks.json` and neither lets that path be moved, so one shared
root would hand each harness the other's event names. `cargento-gemini/` carries the Gemini manifest,
Gemini's hooks, and the two hook scripts they run.

### Codex installation

```bash
# Add the marketplace from a local checkout, then install the plugin
codex plugin marketplace add .
codex plugin add cargento@cargento-marketplace
```

Restart Codex after installation.

Installing the plugin is most of the setup. What is left is configured by hand, because a plugin
cannot write it for you: the ask-lane MCP server, Claude's lifecycle hooks, Antigravity's status
line. See [HOW_TO_USE.md](HOW_TO_USE.md) for one procedure per task.

---

## 2. Skills

| Skill | What it does | Standalone invocation |
|-------|--------------|------------------------|
| `cargento` | Live agent-cartography dashboard: maps sessions, subagents, task progress, ETAs, and token rate across ten coding-agent harnesses, with input-wait notifications (native on macOS, browser notifications elsewhere) | `/cargento:cargento` |

In Codex, invoke it as `$cargento`. In any harness you can also just ask: "open cargento" or "monitor my agents".

## 3. How it works

The skill starts a stdlib-only Python server: `cargento/skills/cargento/server.py` is a small
launcher, and the dashboard itself lives in the importable `cargento_runtime` package beside it. The
server reads local harness session stores read-only, meaning transcripts, task files, and SQLite
databases, and assembles the HTML, CSS and JavaScript under `cargento_runtime/web/` into a
self-refreshing dashboard at `http://127.0.0.1:4553/`. The server binds to 127.0.0.1 unless you ask
for another address with `--host`, which has no authentication behind it. Your session data stays on
the machine: the one request that leaves it is the quota poll, which carries a vendor token out and
quota numbers back and no session content, and `--no-usage` turns it off. A second pathway is
documented and unused: Cargento asking a harness a bounded question, which would carry
session-derived text and is opt-in for that reason. See [SECURITY.md](SECURITY.md) for both, and
before you use `--host`.

The dashboard opens on Sessions, which puts the work that is active now above the work that is only
recent history and gives each active session the same four facts: where it is, what it is doing now,
what it does next, and whether it is blocked. Projects groups the same sessions by working directory,
and Attention collects what needs a human. Keyboard shortcuts `s`, `p` and `a` switch between them,
and the route lives in the URL fragment so a reload or a pasted link comes back to the same view.

See [cargento/skills/cargento/SKILL.md](cargento/skills/cargento/SKILL.md) for data sources, session states, options, and troubleshooting.

## 4. Validation

The canonical pre-PR suite lives in [AGENTS.md](AGENTS.md#pre-pr-checks): lint, types,
frontend-asset lint, the contract validator, tests under coverage, and the native plugin validators.
Contributors should start from [CONTRIBUTING.md](CONTRIBUTING.md), which walks through setting it up.

See [COMPATIBILITY.md](COMPATIBILITY.md) for the cross-platform contract.

## 5. Contributing

Contributions are welcome, and new harness support is especially useful. Start with
[CONTRIBUTING.md](CONTRIBUTING.md) for setup, validation, and PR conventions. This project follows
the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). Please report security issues
privately, as described in [SECURITY.md](SECURITY.md).

## 6. License

Cargento's code and documentation are licensed under the [Apache License 2.0](LICENSE). See
[NOTICE](NOTICE) for attribution. The bundled Space Grotesk and Space Mono font subsets retain their
SIL Open Font License notices in `cargento/skills/cargento/cargento_runtime/web/fonts/`.
