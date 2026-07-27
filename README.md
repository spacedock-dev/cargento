# Cargento

[![Validate](https://github.com/spacedock-dev/cargento/actions/workflows/validate.yml/badge.svg)](https://github.com/spacedock-dev/cargento/actions/workflows/validate.yml)
[![Quality Gate](https://github.com/spacedock-dev/cargento/actions/workflows/quality-gate.yml/badge.svg)](https://github.com/spacedock-dev/cargento/actions/workflows/quality-gate.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

Agnostic agent cartography and visualization.

Cargento maps live coding-agent activity on your machine into a single local dashboard — sessions, subagents, task progress, turn ETAs, and token output rate across eight harnesses: Claude Code, Codex, Gemini CLI / Antigravity CLI, GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, and Factory Droid.

This repo contains **one plugin**:

- **cargento** — the agent cartography dashboard skill

---

## 1. How to Set Up

### Prerequisites

- Python 3.11+ — the dashboard server is stdlib-only, no dependencies
- To install it as a plugin: Codex, Claude Code, Antigravity/AGY, or Gemini CLI

You do not need all four. The dashboard maps every harness it finds on the machine regardless of
which one launched it, and it runs standalone with no client installed at all:

```bash
python3 cargento/skills/cargento/server.py --port 4553
```

### Claude Code Installation

```bash
# Add the marketplace (one-time setup)
claude plugin marketplace add spacedock-dev/cargento

# Install the cargento plugin
claude plugin install cargento@cargento-marketplace
```

Restart Claude Code after installation.

### Antigravity / AGY Installation

```bash
# From a local checkout, install the native AGY plugin
agy plugin install "$PWD/cargento"
```

Restart AGY after installation.

### Gemini CLI Installation

```bash
# From a local checkout, install the native Gemini CLI extension
gemini extensions install "$PWD/cargento"
```

Restart Gemini CLI after installation.

### Codex Installation

```bash
# Add the marketplace from a local checkout, then install the plugin
codex plugin marketplace add .
codex plugin add cargento@cargento-marketplace
```

Restart Codex after installation.

---

## 2. Skills

| Skill | What it does | Standalone invocation |
|-------|--------------|------------------------|
| `cargento` | Live agent-cartography dashboard: maps sessions, subagents, task progress, ETAs, and token rate across eight coding-agent harnesses, with input-wait notifications for Claude (native on macOS, browser notifications elsewhere) | `/cargento:cargento` |

In Codex, invoke it as `$cargento`. In any harness you can also just ask: "open cargento" or "monitor my agents".

## 3. How It Works

The skill starts a stdlib-only Python server (`cargento/skills/cargento/server.py`) that reads local harness session stores read-only — transcripts, task files, and SQLite databases — and serves a self-refreshing dashboard at `http://127.0.0.1:4553/`. No data leaves your machine; the server binds to 127.0.0.1 only.

See [cargento/skills/cargento/SKILL.md](cargento/skills/cargento/SKILL.md) for data sources, session states, options, and troubleshooting.

## 4. Validation

The canonical pre-PR suite — lint, types, embedded-asset lint, contract validator, tests under
coverage, and the native plugin validators — is in [AGENTS.md](AGENTS.md#pre-pr-checks). Contributors
should start from [CONTRIBUTING.md](CONTRIBUTING.md), which walks through setting it up.

See [COMPATIBILITY.md](COMPATIBILITY.md) for the cross-platform contract.

## 5. Contributing

Contributions are welcome — new harness support is especially valuable. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup, validation, and PR conventions. This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md), and security issues should be reported privately per [SECURITY.md](SECURITY.md).

## 6. License

Cargento is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for attribution.
