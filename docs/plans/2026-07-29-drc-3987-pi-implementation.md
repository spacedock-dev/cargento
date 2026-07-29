# Pi Harness Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Add Pi as Cargento's ninth monitored harness, with correct store discovery, branch-aware
session state, token rate, turn progress, diagnostics, and documentation.

**Architecture:** Keep the stdlib-only single-file server. Add Pi-specific path, metadata,
branch-scan, analyzer, and collector helpers beside the existing JSONL harnesses, then feed their
results into Cargento's shared session and rendering helpers. The scanner caches the active
leaf-to-root branch and rebuilds it when an append switches branches; it never treats
`parentSession` as a subagent relationship.

**Tech Stack:** Python 3.11+ standard library, `unittest`, embedded HTML/CSS/JavaScript, Markdown,
JSON plugin manifests.

## Global Constraints

- Use Linear's exact branch name: `feature/drc-3987-add-support-for-pi`.
- Keep `server.py` standard-library-only.
- Preserve Windows, macOS, and Linux path semantics in the pure resolver.
- Treat `PI_CODING_AGENT_SESSION_DIR` as authoritative over `PI_CODING_AGENT_DIR`, global
  `sessionDir`, and the default.
- Scan flat custom stores (`*.jsonl`) and nested default stores (`*/*.jsonl`).
- Follow the last persisted Pi entry's ancestor path; exclude sibling branches from prompts,
  tools, usage, and turns.
- Keep forked and cloned files independent; `parentSession` never creates a subagent.
- Do not claim needs-input, Spacedock, or core-subagent support for Pi.
- Do not change any plugin version field or lower the coverage threshold.
- Follow red-green-refactor for every production-code change.

---

### Task 1: Resolve and diagnose Pi stores

**Files:**

- Modify: `cargento/skills/cargento/tests/test_server.py`
- Modify: `cargento/skills/cargento/server.py:61-226`
- Modify: `cargento/skills/cargento/server.py:6669-6760`

**Interfaces:**

- Produces: `STORE_ROOTS["pi.sessions"]: list[str]`
- Produces: `PI_SESSIONS_DIR: str`
- Extends: `resolve_store_roots(..., pi_settings: Mapping[str, Any] | None = None)`
- Extends: `STORE_ENV_VARS` with `PI_CODING_AGENT_DIR` and `PI_CODING_AGENT_SESSION_DIR`

- [ ] **Step 1: Write failing resolver tests**

Add cases to `StoreRootsTest` that assert:

```python
roots = self.resolve("darwin", {}, "/home/u")
self.assertEqual(["/home/u/.pi/agent/sessions"], roots["pi.sessions"])

roots = dashboard.resolve_store_roots(
    platform_name="linux",
    environ={
        "PI_CODING_AGENT_DIR": "/opt/pi",
        "PI_CODING_AGENT_SESSION_DIR": "/sessions",
    },
    home="/home/u",
)
self.assertEqual(["/sessions"], roots["pi.sessions"])

roots = dashboard.resolve_store_roots(
    platform_name="linux",
    environ={"PI_CODING_AGENT_DIR": "/opt/pi"},
    home="/home/u",
    pi_settings={"sessionDir": "history"},
)
self.assertEqual(["/opt/pi/history"], roots["pi.sessions"])
```

Also cover `~`, absolute settings paths, blank/non-string settings values, Windows separators,
and the precedence `PI_CODING_AGENT_SESSION_DIR` > global `sessionDir` >
`PI_CODING_AGENT_DIR/sessions`.

- [ ] **Step 2: Run the resolver tests and verify red**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_server.StoreRootsTest \
  cargento.skills.cargento.tests.test_server.DiagnoseTest
```

Expected: failures because `pi.sessions`, the Pi environment names, and `PI_SESSIONS_DIR` do not
exist.

- [ ] **Step 3: Implement path and settings resolution**

Add a bounded global-settings reader before `STORE_ROOTS` initialization:

```python
def load_pi_settings(config_dir: str) -> dict[str, Any]:
    try:
        with open(os.path.join(config_dir, "settings.json"), "rb") as source:
            value = json.loads(source.read(1_000_001))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
```

Extend `resolve_store_roots()` with an optional `pi_settings` mapping. Resolve relative
`sessionDir` values against the effective Pi config directory using the target platform's path
module; expand a leading `~` against the injected `home`. Add `pi.sessions`, load the global
settings once at startup, and expose `PI_SESSIONS_DIR`.

- [ ] **Step 4: Wire diagnostics and verify green**

Add `"pi.sessions": PI_SESSIONS_DIR` to `store_primaries()`. Extend diagnosis tests to assert both
Pi environment variables appear in `report["env"]` and Pi's candidate path appears under
`report["stores"]`.

Run the Task 1 test command. Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add cargento/skills/cargento/server.py \
  cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): resolve Pi session stores"
```

### Task 2: Parse Pi's active branch

**Files:**

- Modify: `cargento/skills/cargento/tests/test_server.py`
- Modify: `cargento/skills/cargento/server.py:875-1755`

**Interfaces:**

- Produces: `pi_meta(path: str) -> dict[str, Any]`
- Produces: `scan_pi_session(path: str) -> dict[str, Any] | None`
- Returns analyzer keys: `title`, `last_prompt`, `usage_events`, `last_tool`,
  `last_event_ts`, and `turn`

- [ ] **Step 1: Write failing Pi metadata and analyzer tests**

Create `PiTranscriptTest` with official v3-shaped JSONL fixtures. Assert:

```python
self.assertEqual(
    {"session_id": sid, "cwd": "/w/proj", "parent_session": None},
    dashboard.pi_meta(path),
)
scan = dashboard.scan_pi_session(path)
self.assertEqual("Named session", scan["title"])
self.assertEqual("Implement the fix", scan["last_prompt"])
self.assertEqual("bash", scan["last_tool"])
self.assertEqual([(now, 40)], scan["usage_events"])
```

Place a winning `session_info` record more than `TAIL_BYTES` before the leaf, then append a
clearing `session_info` record and assert the title falls back to the first active-branch user
prompt.

- [ ] **Step 2: Write failing tree and usage tests**

Build one file with two children of the same ancestor. Put a large token count and a different
tool on the abandoned child; make the final appended entry descend from the other child. Assert
the abandoned prompt, tool, usage, and turn do not appear.

Cover all documented output-usage shapes:

```python
{"type": "message", "message": {"role": "assistant", "usage": {"output": 10}}}
{"type": "message", "message": {"role": "toolResult", "usage": {"output": 3}}}
{"type": "compaction", "usage": {"output": 4}}
{"type": "branch_summary", "usage": {"output": 5}}
```

Assert corrupt lines and an incomplete final line do not erase the last complete result. Scan,
append a record whose `parentId` points to an earlier ancestor, scan again, and assert the cache
rebuilds onto the new branch.

- [ ] **Step 3: Run the Pi transcript tests and verify red**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_server.PiTranscriptTest
```

Expected: import-time test failures because `pi_meta()` and `scan_pi_session()` do not exist.

- [ ] **Step 4: Implement immutable header parsing**

Implement `pi_meta()` through `first_line_meta()`. Accept only a first record whose `type` is
`"session"`; extract string `id`, `cwd`, and optional `parentSession`. Do not interpret
`parentSession`.

- [ ] **Step 5: Implement a compact branch cache**

Add a cache protected by `_scan_lock`. Store compact projections, never full image or tool-result
payloads:

```python
{
    "id": entry_id,
    "parent_id": parent_id,
    "timestamp": epoch,
    "prompt": prompt_or_none,
    "usage": output_tokens,
    "tool": tool_name_or_none,
    "name": session_name_sentinel,
}
```

On the first scan, walk `reverse_lines()` from the final persisted entry toward `parentId: null`
and reverse the collected path. On a linear append, extend the cached path. On an append to a
cached ancestor, truncate to that ancestor and extend. If the parent is outside the cached path,
rebuild from disk. Keep the latest global `session_info` name separately so a name outside the
active branch still matches Pi's session selector.

Derive turn state from active-branch user messages using the same quiet-gap rule as
`_apply_turn_record()`. Keep only the last 50 completed durations.

- [ ] **Step 6: Run focused and regression tests**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_server.PiTranscriptTest \
  cargento.skills.cargento.tests.test_server.TurnTrackingTest
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add cargento/skills/cargento/server.py \
  cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): read Pi session branches"
```

### Task 3: Collect and render Pi sessions

**Files:**

- Modify: `cargento/skills/cargento/tests/test_server.py`
- Modify: `cargento/skills/cargento/server.py:1930-2055`
- Modify: `cargento/skills/cargento/server.py:4143-4265`
- Modify: `cargento/skills/cargento/server.py:4856-4862`

**Interfaces:**

- Produces: `collect_pi(now: float, window_hours: float, show_all: bool) -> list[dict[str, Any]]`
- Registers: `("pi", "Pi", discover_pi, collect_pi)` in `HARNESSES`
- Presents: `pi:{code:"PI",name:"Pi"}` in the embedded JavaScript map

- [ ] **Step 1: Extend the behavioral harness contract and verify red**

Add `PI_SESSIONS_DIR` to `STORE_CONSTANTS` and add:

```python
def build_pi(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "--w-proj--" / f"2026-07-29_{sid}.jsonl",
        [
            {
                "type": "session",
                "version": 3,
                "id": sid,
                "timestamp": _iso(when),
                "cwd": "/w/proj",
            },
            {
                "type": "message",
                "id": "user0001",
                "parentId": None,
                "timestamp": _iso(when),
                "message": {"role": "user", "content": title, "timestamp": int(when * 1000)},
            },
        ],
        when,
    )
    return {"PI_SESSIONS_DIR": str(root)}
```

Append `("pi", build_pi)` to the contract `HARNESSES`. Run
`HarnessContractTest` and `HostilePathContractTest`; expect failures because Pi is not registered.

- [ ] **Step 2: Write Pi-specific collector tests**

Assert:

- nested and flat session layouts are both discovered;
- two files with the same header ID keep the newer row;
- two files connected by header `parentSession` remain two rows;
- a non-session JSONL file is ignored;
- a future-dated event contributes no activity or token rate;
- the row exposes project `w/proj`, title, last prompt, rate, tool detail, and turn progress.

- [ ] **Step 3: Implement `collect_pi()`**

Gather and deduplicate:

```python
paths = set(glob_stores("pi.sessions", PI_SESSIONS_DIR, "*.jsonl"))
paths.update(glob_stores("pi.sessions", PI_SESSIONS_DIR, "*", "*.jsonl"))
```

Validate each header, keep the newest file per logical ID, isolate per-file read failures, and
build rows with `base_session("pi", ...)`, `project_from_cwd()`, `rate_from()`,
`working_detail()`, and `turn_progress()`. Use only plausible timestamps for activity and rate.

- [ ] **Step 4: Register Pi and add the UI label**

Add Pi discovery to `HARNESSES`, add the JavaScript `PI` monogram metadata, and add a page-contract
assertion that the embedded map contains the explicit Pi label.

- [ ] **Step 5: Run focused contracts and verify green**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_server.PiCollectorTest \
  cargento.skills.cargento.tests.test_server.HarnessContractTest \
  cargento.skills.cargento.tests.test_server.HostilePathContractTest
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add cargento/skills/cargento/server.py \
  cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): display Pi sessions"
```

### Task 4: Reconcile the shipped contract and verify the branch

**Files:**

- Modify: `README.md`
- Modify: `COMPATIBILITY.md`
- Modify: `docs/design-daemon.md`
- Modify: `docs/design-cross-platform.md`
- Modify: `cargento/skills/cargento/SKILL.md`
- Modify: `cargento/.claude-plugin/plugin.json`
- Modify: `cargento/.codex-plugin/plugin.json`
- Modify: `cargento/plugin.json`
- Modify: `cargento/gemini-extension.json`
- Modify: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**

- Documents Pi as the ninth monitored harness.
- Documents both Pi environment variables and the limits of CLI/project-local session
  directories.
- Keeps the four manifest descriptions identical.

- [ ] **Step 1: Make the existing documentation-parity test fail**

Extend `test_documented_env_overrides_are_the_ones_honoured()` with both Pi variables and their
expected roots before editing `SKILL.md`. Run that single test and confirm it fails because the
shipped skill omits the variables.

- [ ] **Step 2: Update owned documentation and manifest descriptions**

Add Pi to the harness lists, store list, token-rate sources, turn-boundary description, platform
path contract, and honest limitations. Update “eight” to “nine” in current durable docs. Add Pi
to all four identical manifest descriptions and the Codex long description. Leave all version
fields byte-for-byte unchanged.

- [ ] **Step 3: Apply the repository `sync-docs` skill**

Read `.claude/skills/sync-docs/SKILL.md` in full, follow its diff and voice checks, and commit any
additional documentation corrections on this branch.

- [ ] **Step 4: Run the canonical pre-PR suite**

Run every command in AGENTS.md, including the version-diff guard and native validators when
installed:

```bash
ruff check .
ruff format --check .
mypy
python3 scripts/lint_embedded.py
python3 scripts/validate_plugins.py
python3 scripts/bump_version.py --current
git diff "$(git merge-base origin/main HEAD)"..HEAD \
  -- '*plugin.json' '*marketplace.json' '*gemini-extension.json' |
  grep -E '^[+-].*"version"'
coverage erase
coverage run -m unittest cargento.skills.cargento.tests.test_server \
  scripts.tests.test_validate_plugins scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded
coverage report
claude plugin validate ./cargento --strict
agy plugin validate ./cargento
```

The version-diff `grep` must produce no output. Every validator and test must pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add README.md COMPATIBILITY.md docs/design-daemon.md \
  docs/design-cross-platform.md cargento/skills/cargento/SKILL.md \
  cargento/.claude-plugin/plugin.json cargento/.codex-plugin/plugin.json \
  cargento/plugin.json cargento/gemini-extension.json \
  cargento/skills/cargento/tests/test_server.py
git commit -s -m "docs(skill): document Pi monitoring"
```

- [ ] **Step 6: Push and open the pull request**

Search for the repository PR template, push the exact branch, and open a PR whose body includes:

```markdown
Closes DRC-3987
```

Report the PR URL and the final verification results.
