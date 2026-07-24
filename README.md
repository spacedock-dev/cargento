# Cargento

[![Validate](https://github.com/spacedock-dev/cargento/actions/workflows/validate.yml/badge.svg)](https://github.com/spacedock-dev/cargento/actions/workflows/validate.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

Agnostic agent cartography and visualization.

Cargento maps live coding-agent activity on your machine into a single local dashboard — sessions, subagents, task progress, turn ETAs, and token output rate across eight harnesses: Claude Code, Codex, Gemini CLI / Antigravity CLI, GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, and Factory Droid.

This repo contains **one plugin**:

- **cargento** — the agent cartography dashboard skill

---

## 1. How to Set Up

### Prerequisites

- Codex, Claude Code, Antigravity/AGY, or Gemini CLI installed
- Python 3.8+ (the dashboard server is stdlib-only, no dependencies)

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
| `cargento` | Live agent-cartography dashboard: maps sessions, subagents, task progress, ETAs, and token rate across eight coding-agent harnesses, with macOS input-wait notifications for Claude | `/cargento:cargento` |

In Codex, invoke it as `$cargento`. In any harness you can also just ask: "open cargento" or "monitor my agents".

## 3. How It Works

The skill starts a stdlib-only Python server (`cargento/skills/cargento/server.py`) that reads local harness session stores read-only — transcripts, task files, and SQLite databases — and serves a self-refreshing dashboard at `http://localhost:4553/`. No data leaves your machine; the server binds to 127.0.0.1 only.

See [cargento/skills/cargento/SKILL.md](cargento/skills/cargento/SKILL.md) for data sources, session states, options, and troubleshooting.

## 4. Validation

```bash
python3 -m pip install -r requirements-validation.txt
python3 scripts/validate_plugins.py
python3 -m unittest scripts/tests/test_validate_plugins.py
python3 -m unittest scripts/tests/test_bump_version.py
python3 -m unittest cargento/skills/cargento/tests/test_server.py
claude plugin validate . --strict
claude plugin validate ./cargento --strict
```

See [COMPATIBILITY.md](COMPATIBILITY.md) for the cross-platform contract.

## 5. Contributing

Contributions are welcome — new harness support is especially valuable. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup, validation, and PR conventions. This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md), and security issues should be reported privately per [SECURITY.md](SECURITY.md).

## 6. License

Cargento is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for attribution.
