# Cargento Functional Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Replace the 7,357-line dashboard server and 9,942-line test module with focused runtime,
frontend, and test modules while preserving every shipped behavior and keeping `server.py` as the
stable executable.

**Architecture:** Add a top-level, stdlib-only `cargento_runtime` package beside the launcher.
Move tests and the embedded page first, then extract lower-level data functions, collectors,
application services, and finally CLI assembly in dependency order. Each numbered task is one
independently mergeable pull request based on the latest `main`.

**Tech Stack:** Python 3.11+ standard library, `unittest`, strict mypy, Ruff, coverage.py,
JavaScript executed by Node, GitHub Actions, Markdown plugin manifests.

## Global Constraints

- Preserve `python3 <skill-dir>/server.py` as the executable path.
- Preserve every command, flag, default, message, exit code, route, response schema, security
  invariant, daemon behavior, browser behavior, and session identity rule.
- Keep Python 3.11+ support and add no runtime dependency.
- Bind only to IPv4 loopback and keep live harness stores read-only.
- Keep collection sequential and preserve cache limits, invalidation, and lock grouping.
- Import the runtime only as top-level `cargento_runtime`; runtime modules use relative imports.
- Never import `cargento.skills.cargento.cargento_runtime`.
- Keep `cargento_runtime/__init__.py` empty.
- Do not re-export internal runtime symbols permanently from `server.py`.
- Transfer only the exact per-file Ruff exemptions moved code still requires; never add a
  package-wide exemption or broaden an ignore.
- Keep Python modules generally below 1,000 lines; treat that as a review threshold, not a gate.
- Move frontend source without changing its HTML, CSS, or JavaScript bytes.
- Do not change plugin version fields in any pull request.
- Run the repository `sync-docs` skill whenever a task changes paths, commands, or shipped
  structure.
- Use DCO-signed Conventional Commits.
- Record unrelated defects separately; do not fix them inside a relocation.

This planning branch and both split plans must merge before Task 1 begins. Each implementation
task then branches from the latest `main`, never from this planning branch or an earlier task
branch.

### Extraction lint-transfer protocol

Tasks 8-27 conditionally modify `pyproject.toml` even when it is not repeated in the task's file
list. Before each extraction, run focused Ruff on the destination file and the remaining
`server.py`. Transfer only an existing diagnostic that moved with the symbol: `E501`, `C901`,
`PLR0911`, `PLR0912`, or `PLR0915`. Every transferred exemption must name the exact file and exact
rule; no runtime-directory wildcard is allowed. Remove the matching `server.py` exemption as soon
as the last symbol needing it leaves. If the focused run emits none of those diagnostics, do not
edit `pyproject.toml`.

When this protocol changes `pyproject.toml`, include it in the task's staged files and merge-base
review by running `rtk git add pyproject.toml` immediately before that task's listed commit
command. Task 28 removes every obsolete `server.py` exemption and is the final backstop.

Task 6 introduces the AST runtime import contract. Every Task 7-28 PR that adds a runtime module
also modifies `tests/test_contracts.py`, even when that repeated conditional path is omitted from
the task's file list. Add the new module's exact allowlist row in the same PR; all task commit
commands stage the complete skill tree, so the contract cannot be left behind.

## Recorded Baseline

The implementation starts from `main` commit `2ac652d`. All source line anchors in this plan refer
to that commit; after earlier tasks move code, use the named symbol rather than the stale line:

| Measurement | Baseline |
|---|---:|
| Tests | 423 |
| Skipped | 1 |
| Statements | 3,871 |
| Missed statements | 537 |
| Branches | 1,648 |
| Partial branches | 209 |
| Total coverage | 84.4% |
| `server.py` coverage | 88.4% |

The one-skip measurement is the local macOS result. Skip counts are compared before/after on the
same OS and interpreter because several tests deliberately skip on unsupported platform features.
The total discovered test count must remain platform-independent.

The current command is:

```bash
rtk coverage erase
rtk coverage run -m unittest \
  cargento.skills.cargento.tests.test_server \
  scripts.tests.test_validate_plugins \
  scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded
rtk coverage report
```

The future discovery command does not work before Task 2 because
`cargento/skills/cargento/tests/__init__.py` does not yet exist. Task 2 adds that marker and changes
all command owners atomically.

If `main` moves before Task 1 begins, rerun the current command and replace this table with the new
commit, counts, and coverage before adding tests.

## Final File Responsibilities

| File | Responsibility |
|---|---|
| `server.py` | Stable executable that imports and calls `cargento_runtime.cli.main`. |
| `cargento_runtime/config.py` | Immutable process configuration and store resolution. |
| `cargento_runtime/state.py` | Mutable bounded caches, scanner state, locks, notifications, and start time. |
| `cargento_runtime/io.py` | Bounded file reads, safe globbing, optional SQLite, read-only connections, and store-error recording. |
| `cargento_runtime/records.py` | Untyped-record access, timestamps, turn signals, Gemini expansion, and fingerprints. |
| `cargento_runtime/sessions.py` | Project labels, session shape, deduplication, display IDs, activity, rates, and progress details. |
| `cargento_runtime/transcripts.py` | Shared metadata and non-Claude transcript analyzers. |
| `cargento_runtime/turns.py` | Generic incremental turn scanning and progress. |
| `cargento_runtime/claude_data.py` | Claude transcript facts and agent/session classification shared below the collector. |
| `cargento_runtime/spacedock.py` | Secure Spacedock parsing, attribution, and read policy. |
| `cargento_runtime/notifications.py` | Notification classification, hook state, cooldowns, and native notifier. |
| `cargento_runtime/collectors/*.py` | One harness collector per file; Gemini and Antigravity remain one collector. |
| `cargento_runtime/aggregate.py` | Registry, per-harness failure boundary, collection, memoization, and `Application`. |
| `cargento_runtime/diagnostics.py` | Diagnostic report and rendering over the application registry. |
| `cargento_runtime/http_api.py` | Loopback server, request validation, routes, and instance injection. |
| `cargento_runtime/lifecycle.py` | State files, probes, stop, bind, daemon fork/spawn, and shutdown. |
| `cargento_runtime/cli.py` | Argument parsing and runtime assembly. |
| `cargento_runtime/web/*` | Source assets and byte-preserving page assembly. |
| `tests/support.py` | Canonical import bootstrap, transitional launcher loader, runtime builders, server threads, and subprocesses. |
| `tests/fixtures.py` | Harness store builders and shared contract data. |
| `tests/page_harness.py` | Node DOM harness that executes the shipped `app.js`. |
| `tests/test_*.py` | Behavior-focused test modules named in the approved design. |

## Locked Interfaces

Implement these signatures once and keep them consistent in every later task:

```python
from __future__ import annotations

import threading
from _thread import LockType
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias, TypedDict

Session: TypeAlias = dict[str, Any]
Collection: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class RuntimeConfig:
    home: str
    data_home: str
    store_roots: Mapping[str, tuple[str, ...]]
    platform_name: str
    os_name: str
    state_dir: Path
    launcher_path: Path
    host: str
    port: int
    window_hours: float
    spacedock_enabled: bool
    rate_window_sec: float
    working_threshold_sec: float
    turn_gap_reset_sec: float
    tail_bytes: int
    popup_cooldown_sec: float
    global_popup_cooldown_sec: float
    popup_repeat_suppress_sec: float
    long_turn_warn_sec: float
    future_skew_tolerance_sec: float
    sql_message_limit: int
    max_cache_entries: int
    gemini_seen_entries: int
    reverse_chunk_bytes: int
    display_id_len: int
    claude_cwd_scan_lines: int
    claude_cwd_line_bytes: int
    turn_scan_max_bytes: int
    claude_agent_scan_lines: int
    claude_agent_cache_negative_min_bytes: int
    claude_agent_scan_bytes: int
    cursor_meta_rows: int
    antigravity_log_head_bytes: int
    spacedock_boot_scan_bytes: int
    spacedock_readme_bytes: int
    spacedock_entity_bytes: int
    spacedock_max_frontmatter_lines: int
    spacedock_max_stages: int
    spacedock_max_workflows: int
    spacedock_max_entities: int
    spacedock_max_entity_files: int
    spacedock_max_boot_records: int
    spacedock_max_boot_candidates: int
    collect_memo_sec: float
    daemon_ready_timeout_sec: float
    stop_release_timeout_sec: float
    state_read_cap_bytes: int
    prompt_path_collapse_min_length: int
    first_line_json_cap_bytes: int
    notification_body_cap_bytes: int


class CollectMemoEntry(TypedDict):
    ts: float
    body: bytes


@dataclass
class RuntimeState:
    config: RuntimeConfig
    server_started: float
    hook_lock: LockType = field(default_factory=threading.Lock)
    cache_lock: LockType = field(default_factory=threading.Lock)
    scanner_lock: LockType = field(default_factory=threading.Lock)
    collect_memo_lock: LockType = field(default_factory=threading.Lock)
    hook_notifications: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_popup: dict[str, float] = field(default_factory=dict)
    last_popup_message: dict[str, tuple[str, float]] = field(default_factory=dict)
    last_session_state: dict[str, str] = field(default_factory=dict)
    hook_generation: dict[str, int] = field(default_factory=dict)
    store_errors: dict[str, str] = field(default_factory=dict)
    metadata_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    claude_title_cache: dict[str, tuple[int, int, str | None]] = field(default_factory=dict)
    claude_user_event_cache: dict[str, tuple[int, int, str | None]] = field(default_factory=dict)
    cwd_cache: dict[str, str] = field(default_factory=dict)
    pi_scan: dict[str, dict[str, Any]] = field(default_factory=dict)
    turn_scan: dict[str, Any] = field(default_factory=dict)
    agent_class_cache: dict[str, tuple[bool, str, str]] = field(default_factory=dict)
    spacedock_role_cache: dict[str, str] = field(default_factory=dict)
    spacedock_boot_cache: dict[tuple[str, int], list[dict[str, Any]]] = field(default_factory=dict)
    spacedock_workflow_cache: dict[tuple[str, int, int], dict[str, Any] | None] = field(
        default_factory=dict
    )
    spacedock_entity_cache: dict[tuple[str, int, int], str] = field(default_factory=dict)
    cursor_metadata_cache: dict[str, tuple[float, str | None, str]] = field(default_factory=dict)
    collect_memo: dict[tuple[float, bool], CollectMemoEntry] = field(default_factory=dict)


Discoverer: TypeAlias = Callable[[RuntimeConfig, RuntimeState], bool]
Collector: TypeAlias = Callable[
    [RuntimeConfig, RuntimeState, float, float, bool],
    list[Session],
]


@dataclass(frozen=True)
class HarnessSpec:
    key: str
    label: str
    discover: Discoverer
    collect: Collector
```

The consolidated block above fixes names and field types, not module placement:
`RuntimeConfig` lives in `config.py`; `CollectMemoEntry` and `RuntimeState` live in `state.py`;
`Session` lives in `sessions.py`; and `Collection`, `Discoverer`, `Collector`, and `HarnessSpec`
live in `aggregate.py`. Lower modules must not import aliases from a higher layer.

Task 12 defines `Application.__init__(config, state, harnesses, *, native_notifier,
popup_notifier, diagnostic_sink, clock=time.time)`, `collect(*, show_all) -> Collection`, and
`collect_json(*, show_all) -> bytes`. Task 26 defines
`CargentoHTTPServer.__init__(address, application, page_bytes)`. Those tasks contain the concrete
constructor bodies and move the existing aggregation and HTTP behavior without algorithm changes.

Use `build_runtime_state(config, *, started)` as the only production constructor for
`RuntimeState`; tests may instantiate the dataclass directly only when exercising validation.

## Per-PR Execution Protocol

For every task:

1. Wait until the previous task is merged.
2. Update `main`, create the named branch, and verify it does not point at `main` before editing.
3. Make only the task's changes.
4. Run the focused tests, then the canonical pre-PR suite from `AGENTS.md`.
5. Run `sync-docs` if the task changes paths, commands, or shipped structure.
6. Review `git diff --check` and the merge-base diff for accidental behavior changes.
7. Commit with `rtk git commit -s`, push the branch, and open the named PR.
8. Merge only after Ubuntu, macOS, Windows, and the required quality gate pass.

Branch bootstrap:

```bash
rtk git switch main
rtk git pull --ff-only
rtk git switch -c refactor/<task-branch>
rtk git branch --show-current
```

Expected final line: the exact task branch named in that task, never `main`.

---

### Task 1: Characterize the Installed Contract

**PR:** `test(skill): characterize installed dashboard contract`

**Branch:** `refactor/characterize-installed-contract`

**Files:**

- Modify: `cargento/skills/cargento/tests/test_server.py`
- Modify: `.github/workflows/quality-gate.yml`

**Interfaces:**

- Consumes: the current `server.py` executable and `dashboard` test module.
- Produces: stable behavioral assertions that every extraction task must keep green.

- [ ] **Step 1: Add contract helpers and thirteen characterization tests**

Add `InstalledContractCharacterizationTest` to the existing test module. Use temporary directories,
an unrelated `cwd`, `PYTHONNOUSERSITE=1`, and an environment with `PYTHONPATH` removed. Add these
exact test methods:

```python
def test_launcher_runs_from_an_unrelated_working_directory(self) -> None:
def test_cli_help_diagnose_status_stop_and_invalid_arguments_are_stable(self) -> None:
def test_http_routes_pin_status_content_type_and_response_shapes(self) -> None:
def test_host_origin_dns_rebinding_and_request_limits_are_preserved(self) -> None:
def test_health_performs_no_harness_store_reads(self) -> None:
def test_collection_memo_holds_its_lock_across_one_scan(self) -> None:
def test_collection_memo_releases_its_lock_after_failure(self) -> None:
def test_session_end_cannot_be_undone_by_a_slow_notification(self) -> None:
def test_daemon_respawn_uses_the_absolute_stable_launcher(self) -> None:
def test_copied_plugin_launches_without_repository_imports(self) -> None:
def test_windows_detached_argv_preserves_an_absolute_launcher_path(self) -> None:
def test_main_and_detached_spawn_forward_current_arguments(self) -> None:
def test_served_page_bytes_equal_the_embedded_page(self) -> None:
```

The served-page characterization is a compact byte oracle, not a copied golden file. Assert these
exact pre-extraction values:

```python
PAGE_BYTES = 93_713
PAGE_SHA256 = "3a2264edda06e9caf1fbd34c0226ad8c3b0b320f206a87676c183492a5241b37"
STYLE_BYTES = 27_180
STYLE_SHA256 = "e96a2292642bfc40d4bd40e9c23c733cf8d8ef524f55dfb9328685ac53f02cf1"
SCRIPT_BYTES = 66_237
SCRIPT_SHA256 = "bfe260f4c9807d4a59de41f2a37b3711e76547fc67acc73f9201ff11da4a0e48"
```

Hash the exact encoded `PAGE`, `<style>` body, and `<script>` body. The same constants move with
the page test in Task 5 and remain the byte-preservation oracle after `PAGE` is deleted.

The route test must cover `/`, `/api/data`, `/api/health`, `/api/notify`, `/api/shutdown`, and an
unknown route. Assert exact status, content type, cache header, and stable JSON keys rather than
timestamps. The security test must assert loopback bind, rejected non-loopback `Host`, rejected
cross-origin POST, accepted same-origin POST, rejected oversized and invalid `Content-Length`, and
the existing cross-site top-level navigation exception.

The copied-plugin test copies only `cargento/`, starts the absolute copied `server.py` on a free
port from a second temporary directory, polls `/api/health`, reads `/`, and stops it with the
absolute copied launcher. Its subprocess environment must be:

```python
env = dict(os.environ)
env.pop("PYTHONPATH", None)
env["PYTHONNOUSERSITE"] = "1"
env["CARGENTO_HOME"] = str(cargento_home)
```

Wrap the cycle in `try/finally`. The `finally` block invokes the copied launcher's `--stop`, then
terminates and kills the foreground subprocess if it has not exited, waits for it, and polls until
the port is released. The temporary state directory must be empty of live process artifacts before
cleanup returns.

Use `subTest` for the five CLI paths so this task adds exactly thirteen tests. The expected new
full-suite count is 436 with one skip.

- [ ] **Step 2: Run the characterization class and baseline suite**

Run:

```bash
rtk python3 -m unittest \
  cargento.skills.cargento.tests.test_server.InstalledContractCharacterizationTest
rtk python3 -m unittest cargento.skills.cargento.tests.test_server
```

Expected: 13 characterization tests pass; the dashboard module reports 384 tests with one skip
(371 existing dashboard tests plus 13 new tests). The full canonical suite reports 436 tests with
one skip.

- [ ] **Step 3: Add a required Python 3.11 runtime-floor job**

Add `runtime-floor` to `.github/workflows/quality-gate.yml`. Use Ubuntu, Python 3.11, no installed
project package, and run:

```yaml
- name: Direct-launch smoke on the supported floor
  run: |
    cd "${RUNNER_TEMP}"
    python "${GITHUB_WORKSPACE}/cargento/skills/cargento/server.py" --help
    python "${GITHUB_WORKSPACE}/cargento/skills/cargento/server.py" --diagnose --json
```

Add `runtime-floor` to the final `quality-gate.needs` list and result check.

- [ ] **Step 4: Run the full gate and record the post-characterization baseline**

Run every command in `AGENTS.md` under "Pre-PR Checks." Record 436 tests, one skip, and the measured
coverage in the PR description. Coverage may rise; it may not fall below 84.4% without an explained
measurement difference.

- [ ] **Step 5: Commit**

```bash
rtk git add cargento/skills/cargento/tests/test_server.py \
  .github/workflows/quality-gate.yml
rtk git commit -s -m "test(skill): characterize installed dashboard contract"
```

### Task 2: Establish Test Discovery and Shared Support

**PR:** `refactor(tests): establish dashboard test discovery`

**Branch:** `refactor/test-discovery-support`

**Files:**

- Create: `cargento/skills/cargento/tests/__init__.py`
- Create: `cargento/skills/cargento/tests/support.py`
- Create: `cargento/skills/cargento/tests/fixtures.py`
- Create: `cargento/skills/cargento/tests/page_harness.py`
- Modify: `cargento/skills/cargento/tests/test_server.py`
- Modify: `.github/workflows/quality-gate.yml`
- Modify: `.github/workflows/validate.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`
- Modify: `.claude/skills/sync-docs/SKILL.md`
- Modify: `scripts/validate_plugins.py`

**Interfaces:**

- Consumes: current dynamically loaded `dashboard` and `dashboard_hook`.
- Produces: one canonical transitional import, shared fixture builders, Node harness, and discovery
  commands.

- [ ] **Step 1: Add the package marker and canonical path bootstrap**

`tests/__init__.py` must prepend the resolved skill directory:

```python
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
skill_path = str(SKILL_DIR)
if skill_path in sys.path:
    sys.path.remove(skill_path)
sys.path.insert(0, skill_path)
```

In `support.py`, move the loader from `test_server.py:1-48`, but register both modules before
execution:

```python
dashboard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dashboard
SPEC.loader.exec_module(dashboard)

dashboard_hook = importlib.util.module_from_spec(HOOK_SPEC)
sys.modules[HOOK_SPEC.name] = dashboard_hook
HOOK_SPEC.loader.exec_module(dashboard_hook)
```

Move `serve_until_closed` from lines 51-68. Add `LegacyDashboardTestCase` by moving the lock-aware
cache resets and default `notify_mac` patch from lines 723-745. Add a Pi scan reset helper from
lines 541-543 and a harness-contract base from lines 7585-7620.

- [ ] **Step 2: Move shared fixtures without changing values**

Move into `fixtures.py`:

- protobuf helpers from `test_server.py:71-92`;
- `STORE_CONSTANTS`, `_iso`, `_jsonl`, `_sqlite`, every `build_*`, and `HARNESSES` from
  `test_server.py:7318-7570`.

Move `PageJsHarness` from `test_server.py:95-183` into `page_harness.py`. It must import the
support-owned `dashboard` and inherit `LegacyDashboardTestCase`; no file may load another copy of
`server.py`.

- [ ] **Step 3: Prove discovery before changing CI**

Run:

```bash
rtk python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```

Expected: the same post-Task-1 dashboard count and same-platform skip count. Also assert in a
contract test:

```python
self.assertIs(sys.modules["cargento_server"], dashboard)
self.assertNotIn("cargento.skills.cargento.cargento_runtime", sys.modules)
```

- [ ] **Step 4: Change every command owner atomically**

Replace hard-coded `test_server` commands in:

- `AGENTS.md:94-96`;
- `.github/workflows/quality-gate.yml:90-94,217-218`;
- `.github/workflows/validate.yml:37-38`;
- `.github/workflows/release.yml:155-158`;
- `.claude/skills/sync-docs/SKILL.md:87-88,301-302`;
- `CONTRIBUTING.md:58-60,142-145`;
- `scripts/validate_plugins.py:43-44`.

The coverage job must run:

```bash
coverage erase
coverage run -m unittest discover -s cargento/skills/cargento/tests -t .
coverage run -a -m unittest \
  scripts.tests.test_validate_plugins \
  scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded
coverage report
```

The platform job must use two shell-neutral steps: dashboard discovery, then the three script
modules.

- [ ] **Step 5: Expand the Python 3.11 floor job to exercise discovery**

Install `requirements-dev.txt` and `requirements-validation.txt` in the Task-1 `runtime-floor` job.
After the direct-launch smoke, run the four-command coverage sequence on Python 3.11. The ordinary
coverage job exercises it on Python 3.12, and the native platform matrix exercises non-coverage
discovery on Ubuntu, macOS, and Windows.

- [ ] **Step 6: Run both canonical sequences**

Run:

```bash
rtk coverage erase
rtk coverage run -m unittest discover -s cargento/skills/cargento/tests -t .
rtk coverage run -a -m unittest \
  scripts.tests.test_validate_plugins \
  scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded
rtk coverage report
rtk python3 -m unittest discover -s cargento/skills/cargento/tests -t .
rtk python3 -m unittest \
  scripts.tests.test_validate_plugins \
  scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded
```

Expected: counts match Task 1 and total coverage has no unexplained regression.

- [ ] **Step 7: Run `sync-docs` and commit**

The `sync-docs` skill must reconcile the command and architecture references before committing.

```bash
rtk git add cargento/skills/cargento/tests .github/workflows AGENTS.md \
  CONTRIBUTING.md .claude/skills/sync-docs/SKILL.md scripts/validate_plugins.py
rtk git commit -s -m "refactor(tests): establish dashboard test discovery"
```

#### Authoritative `CargentoServerTest` Split Manifest

The 156 methods in the original `CargentoServerTest` must move exactly once according to this
manifest. Counts sum to 156. Tasks 3-5 compare this method-name inventory before deleting the
monolith.

**`test_claude.py` (24):**

- `test_load_tasks_supports_current_and_legacy_directories`
- `test_hook_user_event_accepts_matching_project_transcript`
- `test_new_user_event_clears_hook_without_comparing_clocks`
- `test_untimestamped_user_record_clears_hook_notification`
- `test_assistant_only_tail_does_not_change_hook_user_event`
- `test_answer_result_after_tail_boundary_does_not_leave_question_open`
- `test_transcript_mtime_alone_does_not_clear_newer_hook`
- `test_claude_agent_identity_reads_only_a_bounded_prefix`
- `test_configured_agent_transcript_remains_a_top_level_session`
- `test_young_agent_identity_can_gain_a_parent_relation`
- `test_young_agent_identity_can_gain_a_name_after_parent_relation`
- `test_parent_relation_without_agent_name_is_still_a_subagent`
- `test_claude_agent_negative_cache_waits_for_conclusive_prefix`
- `test_claude_title_prefers_newest_ai_title_outside_tail`
- `test_claude_title_falls_back_to_first_user_prompt`
- `test_legacy_claude_agent_files_are_not_top_level_sessions`
- `test_modern_subagent_transcripts_fold_into_parent_session`
- `test_load_tasks_coerces_malformed_field_types`
- `test_claude_subagents_tolerate_malformed_meta`
- `test_workflow_subagents_count_as_running_subagents`
- `test_workflow_agents_keep_a_quiet_parent_working`
- `test_workflow_agent_activity_holds_a_session_in_the_window`
- `test_claude_session_cwd_reads_the_head_and_retries_when_absent`
- `test_claude_project_falls_back_when_transcript_has_no_cwd`

**`test_codex.py` (3):**

- `test_codex_meta_extracts_parent_thread_id`
- `test_codex_subagent_usage_is_added_after_own_start_boundary`
- `test_codex_meta_tolerates_malformed_payload_types`

**`test_gemini_antigravity.py` (26):**

- `test_gemini_set_snapshot_updates_summary_and_turns`
- `test_large_repeated_gemini_snapshot_does_not_churn_dedup_cache`
- `test_antigravity_sessions_are_discovered_and_collected`
- `test_antigravity_cache_primary_workspace_beats_added_directories`
- `test_antigravity_unusable_cache_workspace_does_not_block_log_fallback`
- `test_antigravity_stale_log_can_anchor_active_workspace_context`
- `test_antigravity_stale_log_can_anchor_an_additional_context`
- `test_antigravity_steps_supply_rate_action_and_turn_progress`
- `test_antigravity_subagents_are_folded_under_parent`
- `test_antigravity_folded_subagent_rate_reaches_parent`
- `test_antigravity_nested_subagent_activity_reaches_root`
- `test_antigravity_future_wal_does_not_hide_fresh_store`
- `test_antigravity_empty_wal_does_not_invent_activity`
- `test_antigravity_stale_subagents_do_not_get_running_pills`
- `test_antigravity_skips_unrelated_stale_metadata_stores`
- `test_antigravity_running_subagent_precedes_parent_tool_action`
- `test_antigravity_blank_subagent_label_uses_session_prefix`
- `test_antigravity_session_info_uses_decodable_fallback_fields`
- `test_antigravity_session_info_skips_blank_role_for_type_name`
- `test_antigravity_session_info_falls_back_for_clean_wal_store`
- `test_antigravity_session_info_does_not_bypass_live_wal`
- `test_antigravity_session_info_reads_closed_wal_store`
- `test_antigravity_session_info_returns_empty_after_both_readers_fail`
- `test_protobuf_fields_rejects_non_blob_payloads_before_conversion`
- `test_antigravity_activity_sees_uncheckpointed_wal_frames`
- `test_antigravity_activity_does_not_report_recovered_reader_error`

**`test_sqlite_collectors.py` (11):**

- `test_goose_tool_response_is_not_a_user_prompt`
- `test_opencode_show_all_returns_every_session`
- `test_cursor_reports_its_workspace_instead_of_the_harness_name`
- `test_cursor_rejects_a_meta_value_that_is_not_a_real_directory`
- `test_cursor_accepts_the_file_uri_spelling`
- `test_cursor_prefers_the_best_trusted_key_across_rows`
- `test_cursor_finds_a_workspace_past_the_first_few_meta_rows`
- `test_cursor_title_survives_a_non_string_name`
- `test_cursor_without_a_workspace_path_keeps_the_harness_name`
- `test_cursor_sessions_discovered_with_title`
- `test_goose_sessions_from_shared_db`

**`test_copilot.py` (1):**

- `test_copilot_sessions_are_discovered_and_analyzed`

**`test_droid.py` (1):**

- `test_droid_sessions_from_project_transcripts`

**`test_contracts.py` (1):**

- `test_claude_and_codex_agree_on_one_directory`

**`test_sessions.py` (11):**

- `test_large_transcript_recovers_turn_start_before_bounded_tail`
- `test_large_append_recovers_new_turn_start_from_skipped_delta`
- `test_base_session_exposes_full_sid_and_truncated_display_id`
- `test_turn_clock_reanchors_after_quiet_gap`
- `test_local_command_output_is_not_a_turn_start`
- `test_uuidv7_sessions_started_together_get_distinct_display_ids`
- `test_display_ids_widen_only_for_the_harness_that_collides`
- `test_a_colliding_fan_out_does_not_widen_unrelated_projects`
- `test_display_ids_ignore_collisions_across_different_harnesses`
- `test_collect_widens_colliding_display_ids_end_to_end`
- `test_identical_sids_do_not_widen_display_ids_forever`

**`test_transcripts.py` (2):**

- `test_metadata_cache_is_safe_under_concurrent_reads`
- `test_read_tail_keeps_first_record_when_window_starts_on_boundary`

**`test_notifications.py` (13):**

- `test_popup_caches_are_bounded_and_globally_rate_limited`
- `test_notify_from_subagent_session_is_suppressed`
- `test_notify_repeated_identical_message_popups_once`
- `test_hook_without_marker_clears_on_newer_parsed_event`
- `test_hook_does_not_mark_actively_working_session_blocked`
- `test_idle_nudge_pops_but_never_marks_session_blocked`
- `test_structured_notification_type_overrides_message_text`
- `test_notification_disposition_covers_documented_types`
- `test_elicitation_completion_clears_dialog_hook`
- `test_session_end_hook_clears_standing_permission_state`
- `test_hook_block_uses_hook_time_and_inactive_sessions_are_idle`
- `test_transcript_open_question_outranks_fresh_activity`
- `test_background_task_flap_lifecycle_end_to_end`

**`test_http_api.py` (7):**

- `test_notify_endpoint_accepts_valid_non_object_and_deep_json`
- `test_cross_site_fetch_metadata_is_rejected`
- `test_cross_site_request_boundary`
- `test_collect_json_single_flights_concurrent_cold_requests`
- `test_collector_failure_is_exposed_in_harness_status`
- `test_health_reports_identity_without_scanning_any_store`
- `test_health_is_refused_from_a_non_local_host_header`

**`test_config_diagnostics.py` (2):**

- `test_cargento_home_honours_the_override_and_defaults_under_home`
- `test_cli_port_type_rejects_values_outside_the_tcp_range`

**`test_lifecycle.py` (41):**

- `test_state_file_roundtrips_and_names_itself_per_port`
- `test_read_state_returns_none_for_absent_corrupt_and_non_object_files`
- `test_write_state_reports_and_survives_an_unwritable_home`
- `test_probe_port_classifies_cargento_foreign_and_closed`
- `test_probe_port_calls_a_non_cargento_listener_foreign`
- `test_probe_port_rejects_recursive_and_lookalike_health_payloads`
- `test_instance_status_covers_running_stale_foreign_and_absent`
- `test_render_status_names_the_state_and_never_suggests_a_kill`
- `test_render_status_survives_a_started_value_it_cannot_convert`
- `test_port_released_is_false_while_a_server_still_holds_the_port`
- `test_stop_instance_waits_for_the_port_before_claiming_it_stopped`
- `test_await_release_sleeps_between_failed_probes`
- `test_stop_instance_reports_a_refused_shutdown_response`
- `test_status_flag_exits_zero_only_when_running`
- `test_stop_instance_stops_a_running_server_over_http`
- `test_port_release_probe_matches_the_listener_during_time_wait`
- `test_stop_instance_removes_a_stale_state_file_and_succeeds`
- `test_stop_instance_will_not_call_it_stopped_while_the_port_is_held`
- `test_stop_instance_lets_the_port_settle_a_lost_connection`
- `test_port_released_only_reads_address_in_use_as_still_held`
- `test_read_state_rejects_a_corrupt_file_instead_of_raising`
- `test_daemon_explains_a_log_it_cannot_open`
- `test_stop_instance_refuses_to_touch_a_port_owned_by_something_else`
- `test_stop_instance_is_idempotent_when_nothing_is_running`
- `test_stop_flag_exits_with_the_code_stop_instance_returned`
- `test_fork_daemon_returns_parent_role_without_touching_setsid`
- `test_fork_daemon_double_forks_and_sessions_the_daemon`
- `test_fork_daemon_exits_the_intermediate_child`
- `test_await_daemon_reports_the_pid_the_daemon_announced`
- `test_await_daemon_reports_failure_when_the_daemon_says_nothing`
- `test_await_daemon_does_not_report_a_pipe_error_as_a_timeout`
- `test_daemon_rejects_the_flags_it_cannot_combine_with`
- `test_daemon_explains_a_home_it_cannot_create_instead_of_tracebacking`
- `test_forwarded_args_carries_the_flags_the_child_needs_and_drops_daemon`
- `test_spawn_detached_uses_a_fixed_argv_and_detaching_flags`
- `test_await_spawned_reports_the_child_that_answered`
- `test_await_spawned_does_not_mistake_another_cargento_for_its_own_child`
- `test_await_spawned_keeps_waiting_while_a_foreign_answer_and_a_live_child`
- `test_await_spawned_surfaces_the_log_when_the_child_exits_at_once`
- `test_await_spawned_gives_up_after_the_timeout`
- `test_log_tail_reads_the_end_and_never_raises`

**`test_page.py` (13):**

- `test_page_marks_repeated_refresh_failures_as_stalled`
- `test_entity_slugs_elide_in_the_middle_not_the_tail`
- `test_output_rate_rows_use_hoverable_harness_badges`
- `test_pi_badge_uses_the_explicit_pi_label`
- `test_page_ships_trailing_rate_sparklines`
- `test_sparkline_buffers_behave_correctly`
- `test_browser_notifications_fire_only_on_transitions_the_server_missed`
- `test_notification_permission_control_reflects_state`
- `test_page_works_without_the_notification_api`
- `test_needs_input_ui_uses_block_anchor_and_displayed_count`
- `test_long_turn_warning_uses_styled_tooltip_not_native_title`
- `test_page_restores_sparkline_hover_and_focus_after_render`
- `test_sparkline_hover_lifecycle_across_renders_and_window_exit`

`test_spacedock.py`, `test_page_calm.py`, and `test_documentation.py` receive no methods from this
class. Preserve `_post_notify` with the notification tests and `_cursor_store`/`_collect_cursor`
with the SQLite tests.

### Task 3: Split JSONL Collector Tests

**PR:** `refactor(tests): split JSONL collector coverage`

**Branch:** `refactor/split-jsonl-collector-tests`

**Files:**

- Create: `tests/test_claude.py`
- Create: `tests/test_codex.py`
- Create: `tests/test_pi.py`
- Create: `tests/test_copilot.py`
- Create: `tests/test_droid.py`
- Create: `tests/test_contracts.py`
- Modify: `tests/test_server.py`

All paths beginning with `tests/` in Tasks 3-29 are relative to
`cargento/skills/cargento/`.

**Interfaces:**

- Consumes: `support.dashboard`, `support.LegacyDashboardTestCase`, and fixture builders.
- Produces: collector-focused tests with no duplicate application import.

- [ ] **Step 1: Move Pi and the smaller JSONL collector slices**

Move `PiTranscriptTest:185-535`, `PiCollectorTest:536-698`, and
`TurnTrackingTest:699-721` into `test_pi.py`. Move every `CargentoServerTest` method assigned by the
manifest to Codex, Copilot, and Droid destinations.

Also move:

- Codex path/label tests at `6938-6977` and
  `VerificationFixTest.test_a_future_main_file_does_not_mask_a_fresh_subagent`;
- `ReviewFixTest.test_a_future_record_does_not_mask_a_fresh_mtime` into `test_droid.py`;

Every module imports the same `dashboard` from `support.py`.

Every method moved out of the former `CargentoServerTest` must live in a class inheriting
`LegacyDashboardTestCase`, or `PageJsHarness` when it executes browser JavaScript. Pi scanner tests
retain their Pi-specific reset; harness contracts retain their contract base. Do not create a
plain `unittest.TestCase` for a former `CargentoServerTest` method.

- [ ] **Step 2: Move Claude and cross-harness contract tests**

Move the 24 manifest-listed `CargentoServerTest` methods into `test_claude.py`. Also move
`ReviewFixTest.test_a_non_dict_message_does_not_kill_the_claude_collector`,
`GlobUnderTest.test_claude_sessions_survive_a_metacharacter_in_the_projects_root`.

Move `HarnessContractTest:7573-7715` and `HostilePathContractTest:7716-7758` into
`test_contracts.py`; import builders and `HARNESSES` from `fixtures.py`.
Move the one manifest-listed cross-harness method there too.

- [ ] **Step 3: Verify inventory and isolation**

Run discovery twice, once in normal order and once with the test module names reversed through an
explicit `unittest` invocation. Expected: identical counts and no real macOS notification. Assert
that `cargento_server` has one object identity across every new module. Compare method names
against the manifest and fail on any omission or duplicate.

- [ ] **Step 4: Commit**

```bash
rtk git add cargento/skills/cargento/tests
rtk git commit -s -m "refactor(tests): split JSONL collector coverage"
```

### Task 3B: Split Composite and SQLite Collector Tests

**PR:** `refactor(tests): split composite and SQLite collector coverage`

**Branch:** `refactor/split-composite-sqlite-tests`

**Files:**

- Create: `tests/test_gemini_antigravity.py`
- Create: `tests/test_sqlite_collectors.py`
- Modify: `tests/test_server.py`

**Interfaces:**

- Consumes: the Task-3 support objects and the remaining composite/SQLite tests in the monolith.
- Produces: the two largest remaining collector test slices without mixing their storage models.

- [ ] **Step 1: Move composite Gemini/Antigravity coverage**

Move all 26 manifest-listed Gemini/Antigravity methods into `test_gemini_antigravity.py`. Preserve
their protobuf helpers through `fixtures.py`; do not duplicate fixture implementations. Every
former `CargentoServerTest` method inherits `LegacyDashboardTestCase`.

- [ ] **Step 2: Move SQLite-backed collector coverage**

Move all 11 manifest-listed SQLite methods plus `SqliteOptionalTest:6978-7033`,
`SqliteTrulyAbsentTest:7034-7087`, and `SqliteUriTest:7211-7317` into
`test_sqlite_collectors.py`. Also move
`ReviewFixTest.test_a_corrupt_database_is_reported_by_diagnose` and
`VerificationFixTest.test_query_failures_are_recorded_not_just_connection_failures`.

Keep the missing-`sqlite3` test in its fresh subprocess. Preserve `_cursor_store` and
`_collect_cursor` in this module, and keep every temporary database isolated per test.

- [ ] **Step 3: Verify inventory, shuffled order, and optional-SQLite isolation**

Run the two new modules alone, then full discovery in normal and reversed module order. Compare the
method-name inventory against the manifest and fail on any omission or duplicate. Expected:
Task-3 counts and same-platform skips are unchanged, `cargento_server` still has one identity, and
the missing-`sqlite3` subprocess cannot contaminate the parent interpreter.

- [ ] **Step 4: Commit**

```bash
rtk git add cargento/skills/cargento/tests
rtk git commit -s -m "refactor(tests): split composite and SQLite collector coverage"
```

### Task 4: Split Shared Runtime and Service Tests

**PR:** `refactor(tests): split shared runtime coverage`

**Branch:** `refactor/split-runtime-tests`

**Files:**

- Create: `tests/test_sessions.py`
- Create: `tests/test_transcripts.py`
- Create: `tests/test_spacedock.py`
- Create: `tests/test_notifications.py`
- Create: `tests/test_http_api.py`
- Create: `tests/test_config_diagnostics.py`
- Modify: `tests/test_server.py`

**Interfaces:**

- Consumes: the shared support objects from Task 2.
- Produces: behavior-owned tests ready to switch to runtime modules one extraction at a time.

- [ ] **Step 1: Move sessions and transcript tests**

Move the manifest-listed session and transcript methods to their destinations.

Also move to `test_sessions.py`: `DurationAndEpochTest:5400-5495`, `ClockSkewTest:7088-7141`,
`ReviewFixTest.test_the_same_session_in_two_stores_yields_one_row`,
`test_newest_plausible_ignores_skew`, and
`test_a_skewed_duplicate_does_not_win_deduplication` move here.

Move to `test_transcripts.py`: `ReverseLinesTest:5052-5271`, `PromptTitleTest:5272-5399`,
`MalformedRecordTest:6444-6576`, and
`ReviewFixTest.test_reverse_lines_stays_linear_on_one_long_record`.

- [ ] **Step 2: Move Spacedock, notification, and HTTP tests**

Move the manifest-listed notification and HTTP methods to their destinations.

Also move:

- `test_spacedock.py`: `SpacedockParserTest:7955-8159` and
  `SpacedockReadContractTest:8160-8517`; no `CargentoServerTest` method belongs here.
- `test_notifications.py`: `NotifyHookTest:5884-6040`, `HookOrderingTest:6577-6844`,
  `NativeNotifierTest:6845-6874`, and
  `GlobUnderTest.test_notify_session_id_cannot_inject_a_glob_pattern`; preserve `_post_notify`.
- `test_http_api.py`: `HostAndSocketTest:5802-5883`, the local-port/exclusive-bind/shutdown methods
  at `6213-6338`, and `VerificationFixTest.test_origin_with_an_implicit_default_port`.

- [ ] **Step 3: Move configuration and diagnostics tests**

Move to `test_config_diagnostics.py`: `StoreRootsTest:5496-5708`, `DiagnoseTest:5709-5801`,
`OperatingSystemExpectationTest:7759-7954`, the text I/O methods at `6875-6937`, and methods at
`6105-6131`, `6199-6212`, `6411-6421`, `7142-7166`.
Move the two manifest-listed configuration methods there too.

- [ ] **Step 4: Run discovery, shuffled module order, and coverage**

Expected: exact Task-3 test inventory, the same-platform skip count, no import duplication, no
manifest omission/duplicate among moved methods, and no coverage loss caused by a missing module.

- [ ] **Step 5: Commit**

```bash
rtk git add cargento/skills/cargento/tests
rtk git commit -s -m "refactor(tests): split shared runtime coverage"
```

### Task 5: Finish the Test Split

**PR:** `refactor(tests): finish behavior-focused test split`

**Branch:** `refactor/finish-test-split`

**Files:**

- Create: `tests/test_lifecycle.py`
- Create: `tests/test_page.py`
- Create: `tests/test_page_calm.py`
- Create: `tests/test_documentation.py`
- Delete: `tests/test_server.py`
- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`
- Modify: `.github/PULL_REQUEST_TEMPLATE.md`

**Interfaces:**

- Consumes: remaining tests in `test_server.py`.
- Produces: the final behavior-focused test layout with no monolithic compatibility module.

- [ ] **Step 1: Move lifecycle, page, calm-mode, and documentation tests**

Move:

- `test_lifecycle.py`: the 41 manifest-listed lifecycle methods, `DaemonLifecycleTest:9843-9942`,
  and the Task-1 arbitrary-CWD, CLI, daemon-respawn, copied-plugin, Windows-argv, and current-main
  argument characterization methods.
- `test_page.py`: the 13 manifest-listed page methods and the Task-1 served-page byte test.
- `test_page_calm.py`: `CalmModeTest:8518-9765`.
- `test_documentation.py`: `DocumentationMatchesCodeTest:9766-9842`.

Move the Task-1 HTTP and notification characterization methods to `test_http_api.py` and
`test_notifications.py`. Delete `test_server.py` only after `unittest discover` reports the same
inventory and the 156-method manifest reports each name exactly once.

- [ ] **Step 2: Remove monolith wording**

Update `AGENTS.md`, `CONTRIBUTING.md`, and `.github/PULL_REQUEST_TEMPLATE.md` to refer to
behavior-focused test modules and the discovery command. Do not duplicate the canonical command
outside `AGENTS.md`.

- [ ] **Step 3: Run the full cross-platform command locally**

Run discovery, the three script-test modules, coverage, Ruff, format, mypy, embedded lint, and
plugin validation. Expected: counts and same-platform skip count match Task 4 exactly.

- [ ] **Step 4: Run `sync-docs` and commit**

```bash
rtk git add cargento/skills/cargento/tests AGENTS.md CONTRIBUTING.md \
  .github/PULL_REQUEST_TEMPLATE.md
rtk git commit -s -m "refactor(tests): finish behavior-focused test split"
```

### Task 6: Extract Frontend Assets Byte-for-Byte

**PR:** `refactor(skill): extract dashboard frontend assets`

**Branch:** `refactor/extract-frontend-assets`

**Files:**

- Create: `cargento_runtime/__init__.py`
- Create: `cargento_runtime/web/__init__.py`
- Create: `cargento_runtime/web/index.html`
- Create: `cargento_runtime/web/styles.css`
- Create: `cargento_runtime/web/app.js`
- Create: `cargento_runtime/web/page.py`
- Modify: `server.py`
- Modify: `tests/page_harness.py`
- Modify: `tests/test_page.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_sqlite_collectors.py`
- Modify: `scripts/lint_embedded.py`
- Modify: `scripts/tests/test_lint_embedded.py`
- Modify: `pyproject.toml`
- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`
- Modify: `README.md`
- Modify: `.claude/skills/sync-docs/SKILL.md`

**Interfaces:**

- Consumes: the exact `PAGE` literal at `server.py:4701-6250`.
- Produces: `web.page.load_page() -> bytes`.

- [ ] **Step 1: Save the pre-move response and make asset tests fail**

Keep `test_served_page_bytes_equal_the_embedded_page` and its Task-1 length/SHA-256 constants as
the pre-move oracle. Add tests that import `cargento_runtime.web.page`, read the real assets, reject
missing assets clearly, and assert all asset paths live below the skill directory.

Run:

```bash
rtk python3 -m unittest \
  cargento.skills.cargento.tests.test_page \
  scripts.tests.test_lint_embedded
```

Expected: FAIL because `cargento_runtime.web` does not exist.

- [ ] **Step 2: Create the empty package markers and exact asset files**

Keep both `__init__.py` files empty. Extract:

- the literal HTML outside `<style>` and `<script>` into `index.html`;
- the exact `<style>` body into `styles.css`;
- the exact `<script>` body into `app.js`.

Put `{{CARGENTO_STYLES}}` and `{{CARGENTO_APP}}` at the exact extraction points. Confirm each token
occurs exactly once and does not occur in either asset.

Implement `page.py`:

```python
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent


def asset_path(name: str) -> Path:
    return WEB_DIR / name


def load_page() -> bytes:
    template = asset_path("index.html").read_text(encoding="utf-8")
    styles = asset_path("styles.css").read_text(encoding="utf-8")
    script = asset_path("app.js").read_text(encoding="utf-8")
    if template.count("{{CARGENTO_STYLES}}") != 1:
        msg = "index.html must contain one CARGENTO_STYLES slot"
        raise RuntimeError(msg)
    if template.count("{{CARGENTO_APP}}") != 1:
        msg = "index.html must contain one CARGENTO_APP slot"
        raise RuntimeError(msg)
    return (
        template.replace("{{CARGENTO_STYLES}}", styles)
        .replace("{{CARGENTO_APP}}", script)
        .encode("utf-8")
    )
```

- [ ] **Step 3: Load assets only on serving paths**

Extend `LoopbackHTTPServer` temporarily with a `page_bytes` constructor keyword and store it on the
server instance. Change `Handler` to serve `self.server.page_bytes`.

In `main()`, parse arguments and complete `--diagnose`, `--stop`, and `--status` before calling
`load_page()`. Call it before daemon log creation, bind, fork, or Windows spawn. Convert
`OSError`, `UnicodeError`, and `RuntimeError` into
`Cargento: cannot load frontend assets (<ExceptionType>: <message>).` on stderr and exit 1.

Update test server helpers to pass the assembled page explicitly. Add tests proving missing assets
do not disable help, diagnosis, status, or stop.

- [ ] **Step 4: Make the linter consume shipped source files**

Remove dynamic `server.py` loading from `scripts/lint_embedded.py`. Read `index.html`, `styles.css`,
and `app.js` directly. Retain `check_js`, `check_css`, and `check_dom_ids`; change output wording
from "embedded" to "frontend." Replace extraction tests with direct asset, missing-file, UTF-8, and
real-asset tests.

Change `page_harness.py` to execute the exact `app.js` file rather than regex-extracting
`dashboard.PAGE`.

- [ ] **Step 5: Enforce canonical package identity**

Add `cargento/skills/cargento/cargento_runtime` to `[tool.mypy].files`, add
`mypy_path = ["cargento/skills/cargento"]`, and enable `explicit_package_bases = true` so mypy
assigns the same top-level module names as runtime imports. Do not add a package-wide Ruff
exemption. Add a test that imports top-level `cargento_runtime` and asserts:

```python
self.assertNotIn("cargento.skills.cargento.cargento_runtime", sys.modules)
self.assertTrue(Path(page.__file__).resolve().is_relative_to(SKILL_DIR))
```

Run mypy with verbose module discovery once and confirm the page module is
`cargento_runtime.web.page`, never the namespace-qualified spelling.

Create `test_runtime_import_graph` in `tests/test_contracts.py` now, using the AST normalization and
rejection rules finalized in Task 28. Its first allowlist contains only the three modules that
exist in this task: the top-level and web initializers import nothing, and `web.page` imports no
runtime module. Every Task 7-28 PR that creates a runtime module must add that module's exact row to
this same test and keep all previous rows green; no runtime dependency may wait until Task 28 to be
reviewed.

In the isolated missing-`sqlite3` subprocess source, prepend `SERVER_PATH.parent` to `sys.path`
before `exec_module`. Keep the import blocker and fresh interpreter; this change makes the new
top-level runtime package resolvable without adding the repository root.

Extend the copied-plugin test to require `index.html`, `styles.css`, `app.js`, and `page.py`, and
prove the copied root page bytes match the source root page. In a fresh interpreter with repository
paths removed, walk `cargento_runtime.__path__` with `pkgutil.walk_packages`, import every discovered
module, and emit every `module.__file__`. Assert every origin is below the copied skill directory.
Also call `web.page.asset_path` for all three assets and assert each resolved path stays below that
directory. Run from an unrelated working directory with no `PYTHONPATH` and
`PYTHONNOUSERSITE=1`.

- [ ] **Step 6: Verify byte identity**

Run the focused page, linter, copied-plugin, and direct-launch tests. Assert `load_page()` has the
Task-1 page length and SHA-256, the two source assets have their Task-1 lengths and SHA-256 values,
and the root response equals `load_page()` byte-for-byte. These assertions must pass on Linux,
macOS, and Windows after the original `PAGE` literal is gone.

- [ ] **Step 7: Run `sync-docs` and commit**

Update the skill's frontend truth probes and linter ownership before running it.

```bash
rtk git add cargento/skills/cargento scripts/lint_embedded.py \
  scripts/tests/test_lint_embedded.py pyproject.toml AGENTS.md CONTRIBUTING.md README.md \
  .claude/skills/sync-docs/SKILL.md
rtk git commit -s -m "refactor(skill): extract dashboard frontend assets"
```

### Task 7: Introduce Runtime Configuration and State

**PR:** `refactor(runtime): introduce explicit configuration and state`

**Branch:** `refactor/runtime-config-state`

**Files:**

- Create: `cargento_runtime/config.py`
- Create: `cargento_runtime/state.py`
- Modify: `server.py`
- Modify: `tests/support.py`
- Modify: `tests/test_config_diagnostics.py`
- Modify: `tests/test_contracts.py`
- Modify: `pyproject.toml`
- Modify: `.claude/skills/sync-docs/SKILL.md`

**Interfaces:**

- Produces: `RuntimeConfig`, `RuntimeState`, `build_runtime_config`, and test runtime builders.
- Leaves: all business behavior in `server.py`.

- [ ] **Step 1: Add failing construction and isolation tests**

Add tests for:

- POSIX and Windows store roots from explicit environment mappings;
- documented environment overrides remaining authoritative;
- a selected-root override collapsing one store to exactly that path while other stores retain all
  normal candidates;
- Pi `sessionDir` resolution;
- `CARGENTO_HOME`, launcher path, host, port, window, and Spacedock fields;
- every existing threshold and cache limit;
- exact defaults of `first_line_json_cap_bytes=200_000` and
  `notification_body_cap_bytes=65_536`;
- exact defaults of `claude_cwd_line_bytes=200_000` and
  `antigravity_log_head_bytes=80_000`;
- a state built with a sentinel start time retaining that exact value;
- two `RuntimeState` objects having distinct dicts and locks;
- no file, socket, browser, log, or subprocess operation during import.

Use a fresh subprocess for the import-side-effect assertion. Expected failure: the two modules do
not exist.

- [ ] **Step 2: Move immutable configuration**

Move `HOME`, `DATA_HOME`, `STORE_ENV_VARS`, `resolve_store_roots`, `load_pi_settings`,
`store_roots:217`, the primary store constants at `server.py:254-289`, and
`CARGENTO_HOME_ENV:6278` into `config.py`. Leave filesystem-query helpers `glob_stores`,
`any_store_dir`, and `existing_stores` in `server.py` until Task 8 so `config.py` never imports
I/O.

Implement:

```python
def build_runtime_config(
    *,
    environ: Mapping[str, str],
    platform_name: str,
    os_name: str,
    launcher_path: Path,
    store_root_overrides: Mapping[str, str] | None = None,
    host: str = "127.0.0.1",
    port: int = 4553,
    window_hours: float = 24.0,
    spacedock_enabled: bool = True,
) -> RuntimeConfig:
```

Resolve store candidates as tuples. When `store_root_overrides` contains a key, replace that key's
entire candidate tuple with the one selected path; this preserves the current rule that a patched
primary never falls through to a real store. Wrap the finished mapping in
`types.MappingProxyType`. Resolve `state_dir` from `CARGENTO_HOME` or the current default. Do not
read ambient environment anywhere except the caller in `server.py` during this transitional task
and later `cli.py`.
Expose `store_roots(config, key) -> tuple[str, ...]` and
`primary_store(config, key) -> str`; neither function touches the filesystem.

- [ ] **Step 3: Move mutable ownership without changing use sites**

Create `RuntimeState` with every field in "Locked Interfaces." Preserve four lock domains: hook,
cache, scanner, and collection memo. Make `server_started` required and add:

```python
def build_runtime_state(config: RuntimeConfig, *, started: float) -> RuntimeState:
    return RuntimeState(config=config, server_started=started)
```

The transitional `main()` captures `time.time()` once at the current semantic point: after parsing
arguments and before validating daemon flag combinations. It passes that value into the builder;
no builder or dataclass default reads the clock. Tests construct two states with different sentinel
times and prove neither the start time nor any mutable field crosses.

Also add:

```python
def bounded_put(
    cache: dict[Any, Any],
    key: Any,
    value: Any,
    *,
    limit: int,
) -> None:
    if key not in cache and len(cache) >= limit:
        cache.pop(next(iter(cache)))
    cache[key] = value
```

Delete the source definitions of the primary constants, but retain transitional aliases in
`server.py` until Task 24 removes the final local collector. Add a clearly marked
`_legacy_runtime()` adapter. It first resolves the normal candidates, compares each alias with that
key's normal first candidate, and passes only changed aliases through `store_root_overrides`; an
unchanged alias preserves every normal candidate. It returns the resulting config with one
process-lifetime `RuntimeState`.

Before returning, assign the current config to that state so a test's patched roots and limits
reach moved functions. Extend `LegacyDashboardTestCase` to clear both the unmoved globals and this
transitional state under their owning locks. Runtime modules must not import this adapter or
`server.py`.

- [ ] **Step 4: Add direct test builders**

In `tests/support.py`, add `make_config(**changes)` using `dataclasses.replace` and
`make_runtime(*, started=1_700_000_000.0, **changes) ->
tuple[RuntimeConfig, RuntimeState]`. The helper must call `build_runtime_state`; it must not
construct an implicit current time. New runtime tests use these objects; unmoved tests may continue
through `_legacy_runtime()` until their owner moves.

- [ ] **Step 5: Run isolation, existing platform-path tests, and the full gate**

Expected: all behavior remains in `server.py`; configuration/state tests pass; the copied plugin
loads top-level modules from its own directory; mypy covers both modules. Transfer only specific
Ruff exemptions that these two files demonstrably require.

- [ ] **Step 6: Run `sync-docs` and commit**

Update the skill's config/state truth probes so later documentation passes inspect the new owners.

```bash
rtk git add cargento/skills/cargento/cargento_runtime \
  cargento/skills/cargento/server.py cargento/skills/cargento/tests pyproject.toml \
  .claude/skills/sync-docs/SKILL.md
rtk git commit -s -m "refactor(runtime): introduce explicit configuration and state"
```

### Task 8: Extract Pure I/O and Record Operations

**PR:** `refactor(runtime): extract io and record operations`

**Branch:** `refactor/runtime-io-records`

**Files:**

- Create: `cargento_runtime/io.py`
- Create: `cargento_runtime/records.py`
- Modify: `server.py`
- Modify: `tests/test_transcripts.py`
- Modify: `tests/test_config_diagnostics.py`
- Modify: `tests/test_sqlite_collectors.py`

**Interfaces:**

- Consumes: `RuntimeConfig` and `RuntimeState`.
- Produces: lower-level functions imported by transcript, turn, and collector modules.

- [ ] **Step 1: Point focused tests at the missing modules**

Change tests for tail reads, reverse lines, typed record access, timestamps, globbing, SQLite URI,
Gemini record expansion/fingerprinting, and turn signals to import their new owner. Expected:
import failure.

- [ ] **Step 2: Move I/O symbols without algorithm changes**

Move into `io.py`:

- `glob_stores:233`, `any_store_dir:242`, `existing_stores:247`;
- `read_tail:499`, `reverse_lines:522`, `glob_under:870`;
- the bounded first-record read, total-prefix read, and independently bounded text-line iterator
  used by transcript metadata, Antigravity, and Claude classification;
- `sqlite_available:798`, `sqlite_ro_uri:885`, `_sql_ro:4124`;
- `record_store_error:786` and `diag:803`, changing them to accept explicit state or sink.

Use these signatures:

```python
def read_tail(config: RuntimeConfig, path: str) -> list[str]:
def read_first_json(config: RuntimeConfig, path: str) -> dict[str, Any]:
def read_prefix_bytes(path: str, *, max_bytes: int) -> bytes:
def iter_bounded_text_lines(
    path: str,
    *,
    max_lines: int,
    per_line_bytes: int,
) -> Iterator[str]:
def reverse_lines(
    config: RuntimeConfig,
    path: str,
    end_pos: int | None = None,
    *,
    max_bytes: int | None = None,
    contains: bytes | None = None,
) -> Iterator[bytes]:
def glob_stores(config: RuntimeConfig, key: str, *pattern: str) -> list[str]:
def any_store_dir(config: RuntimeConfig, key: str, *parts: str) -> bool:
def existing_stores(config: RuntimeConfig, key: str) -> list[str]:
def sqlite_ro_uri(path: str, *, immutable: bool = False, windows: bool | None = None) -> str:
def open_sqlite_read_only(path: str, state: RuntimeState) -> sqlite3.Connection:
def record_store_error(state: RuntimeState, path: str, exc: BaseException) -> None:
```

Keep optional `sqlite3` import behavior inside `io.py`. A fresh-interpreter test must prove JSONL
harness support remains importable when `sqlite3` is absent. `read_first_json` reads no more than
`config.first_line_json_cap_bytes` and returns the existing empty result for missing, malformed,
oversized, or non-object input. `read_prefix_bytes` performs one total-prefix read and returns at
most `max_bytes`. `iter_bounded_text_lines` performs at most `max_lines` calls to
`readline(per_line_bytes)` with UTF-8 replacement and never performs an unbounded `readline()`.

Pin all consumer contracts with before/after-bound fixtures:

- first-line metadata: one line capped at `config.first_line_json_cap_bytes`;
- Claude CWD: up to `config.claude_cwd_scan_lines` independently capped lines, each capped at
  `config.claude_cwd_line_bytes`;
- Claude agent identity/setting: one `config.claude_agent_scan_bytes` byte prefix, at most
  `config.claude_agent_scan_lines`, dropping a partial final record when the file continues;
- Antigravity: one `config.antigravity_log_head_bytes` byte prefix, decoded with replacement and
  `splitlines()`, with no line-count cap and retaining the partial prefix tail exactly as today.

- [ ] **Step 3: Move record symbols below both analyzers**

Move into `records.py`:

- `notification_text:369`, renamed `safe_text` because its control-character stripping and UTF-8
  replacement are shared by notifications and Antigravity;
- `parse_ts`, `parse_utc_sql`, `norm_epoch`;
- `extract_text`, `as_dict`, `as_list`, `message_dict`, `alnum`;
- `record_fingerprint`, `gemini_records`, `incremental_gemini_records`;
- `_turn_signal`.

Keep the exact implementation:

```python
def safe_text(value: Any, limit: int) -> str:
    text = str(value or "").encode("utf-8", "replace").decode("utf-8")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return text[:limit]
```

Pass cache limits and incremental state explicitly. `records.py` may import only config/state and
stdlib modules; it must not import transcripts or turns.

- [ ] **Step 4: Replace legacy call sites**

Update `server.py` callers to import `io` and `records` modules and pass `_legacy_runtime()` values.
Delete the moved definitions from `server.py`; do not alias them back. Update focused tests to call
the new modules with explicit runtime objects.

- [ ] **Step 5: Verify security and malformed-input boundaries**

Run transcript, config/diagnostic, SQLite, hostile-path, optional-SQLite, and copied-plugin tests.
Add the existing notification-text cases and Antigravity prompt/protobuf cases to the focused run.
Run the full gate and inspect the diff for any algorithmic edit.

- [ ] **Step 6: Commit**

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract io and record operations"
```

### Task 9: Extract Session Construction and Identity

**PR:** `refactor(runtime): extract session identity and assembly`

**Branch:** `refactor/runtime-sessions`

**Files:**

- Create: `cargento_runtime/sessions.py`
- Modify: `server.py`
- Modify: `tests/test_sessions.py`
- Modify: `tests/test_contracts.py`

**Interfaces:**

- Consumes: config and record timestamp helpers.
- Produces: shared session shape and deterministic aggregation helpers.

- [ ] **Step 1: Redirect session tests and verify failure**

Point project-label, project-from-CWD, base-session, age/freshness, rate, detail, deduplication, and
display-ID tests at `cargento_runtime.sessions`. Expected: import failure.

- [ ] **Step 2: Move the exact symbol groups**

Move:

- `encoded_home_prefix:292`, `project_label:401`, `project_from_cwd:408`;
- `fmt_duration:486`, `age:822`, `is_fresh:846`, `newest_plausible:852`;
- `dedupe_sessions:727`, `assign_display_ids:748`;
- `base_session:2284`, `rate_from:2316`, `working_detail:2340`.

Use explicit configuration where a threshold or platform decision is needed:

```python
def project_label(config: RuntimeConfig, dirname: str) -> str:
def project_from_cwd(config: RuntimeConfig, cwd: str) -> str:
def rate_from(info: dict[str, Any] | None, now: float, config: RuntimeConfig) -> int:
def base_session(harness: str, sid: Any, project: str) -> Session:
def dedupe_sessions(sessions: list[Session]) -> list[Session]:
def assign_display_ids(config: RuntimeConfig, sessions: list[Session]) -> None:
```

Derive the encoded home prefix from `config.home` inside `project_label` and remove `HOME_PREFIX`
in this task. Cross-platform tests vary `config.home` and `config.os_name` rather than passing
hidden optional platform overrides.

- [ ] **Step 3: Update callers and remove old definitions**

Import the module from `server.py`, pass the transitional config, and delete the old symbols.
Preserve sorting, identity, future-skew, and tie-breaking byte-for-byte.

- [ ] **Step 4: Run direct and all-harness contract tests**

Expected: session schemas, project labels, display IDs, ordering, and hostile-path contracts remain
unchanged on POSIX and Windows expectations.

- [ ] **Step 5: Commit**

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract session identity and assembly"
```

### Task 10: Extract Shared Transcript Analysis

**PR:** `refactor(runtime): extract shared transcript analysis`

**Branch:** `refactor/runtime-transcripts`

**Files:**

- Create: `cargento_runtime/transcripts.py`
- Modify: `server.py`
- Modify: `tests/test_transcripts.py`
- Modify: collector test modules

**Interfaces:**

- Consumes: config, state, I/O, records, and sessions.
- Produces: metadata parsers and non-Claude analyzers.

- [ ] **Step 1: Redirect metadata and analyzer tests**

Point first-line metadata, Codex, Gemini, Copilot, Droid, and Pi metadata tests and non-Claude
transcript analyzer tests at the new module. Expected: import failure.

- [ ] **Step 2: Move metadata and prompt helpers**

Move `first_line_meta:923`, `codex_meta:944`, `gemini_meta:980`, `copilot_meta:995`,
`droid_meta:1009`, `pi_meta:1024`, `shorten_paths:1069`, `clip:1081`, and `prompt_title:1104`.
Change cache use to explicit `RuntimeState`.

Use:

```python
def first_line_meta(
    config: RuntimeConfig,
    state: RuntimeState,
    path: str,
    parse: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
def codex_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
def gemini_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
def copilot_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
def droid_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
def pi_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
def shorten_paths(config: RuntimeConfig, text: str) -> str:
def prompt_title(config: RuntimeConfig, text: str, limit: int = 80) -> str | None:
```

`first_line_meta` must call `io.read_first_json`; it must not reopen the file itself.
`shorten_paths` uses `config.prompt_path_collapse_min_length`, preserving the current value 25.

- [ ] **Step 3: Move non-Claude analyzers**

Move `analyze_codex_transcript:1330`, `analyze_gemini_transcript:1405`,
`analyze_copilot_events:1447`, and `analyze_droid_transcript:1503`. Keep Claude title, last-user,
CWD, hook, and classification functions in `server.py` until Task 21.

Each analyzer accepts `(config: RuntimeConfig, state: RuntimeState, path: str)` so bounded reads and
caches remain explicit.

- [ ] **Step 4: Update legacy callers and verify malformed records**

Pass config/state through server call sites, delete old definitions, and run transcript plus every
affected collector test. Confirm malformed records remove only themselves and broken files remove
only themselves.

- [ ] **Step 5: Commit**

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract shared transcript analysis"
```

### Task 11: Extract Generic Turn Scanning

**PR:** `refactor(runtime): extract generic turn scanning`

**Branch:** `refactor/runtime-turns`

**Files:**

- Create: `cargento_runtime/turns.py`
- Modify: `server.py`
- Modify: `tests/test_transcripts.py`
- Modify: `tests/test_sessions.py`
- Modify: collector tests

**Interfaces:**

- Consumes: config, state, I/O, and records.
- Produces: generic incremental scanning and turn display data.

- [ ] **Step 1: Redirect turn tests and verify import failure**

Move direct ownership for `_apply_turn_record:1888`, `_latest_turn_context:1923`,
`scan_turns:1971`, `turns_from_events:2035`, and `turn_progress:2051` into the expected module.

- [ ] **Step 2: Move generic scanner code**

Implement the moved functions with these public signatures:

```python
def scan_turns(
    config: RuntimeConfig,
    state: RuntimeState,
    path: str,
    harness: str,
) -> dict[str, Any] | None:
def turns_from_events(events: list[tuple[float, bool]]) -> dict[str, Any]:
def turn_progress(
    scan: dict[str, Any] | None,
    session_state: str,
    now: float,
    config: RuntimeConfig,
) -> dict[str, Any]:
```

Use `state.scanner_lock` and `state.turn_scan`. Keep Pi branch scanning in `server.py`.

- [ ] **Step 3: Update callers and remove old definitions**

Pass config/state from the legacy adapter, update all non-Pi collectors, and delete the moved
symbols. Confirm `transcripts.py` and `turns.py` both import `records.py`, never one another.

- [ ] **Step 4: Run quiet-gap, incremental, future-skew, and collector tests**

Expected: no changes to turn elapsed time, ETA, long-turn flags, cache bounds, or partial-write
handling.

- [ ] **Step 5: Commit**

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract generic turn scanning"
```

### Task 12: Establish the Application and Registry Boundary

**PR:** `refactor(runtime): establish application boundary`

**Branch:** `refactor/application-boundary`

**Files:**

- Create: `cargento_runtime/aggregate.py`
- Create: `cargento_runtime/collectors/__init__.py`
- Modify: `server.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_http_api.py`
- Modify: `tests/test_config_diagnostics.py`
- Modify: `.claude/skills/sync-docs/SKILL.md`

**Interfaces:**

- Consumes: `RuntimeConfig`, `RuntimeState`, `HarnessSpec`, and legacy collector callables supplied
  by `server.py`.
- Produces: `Application.collect`, `Application.collect_json`, an injected transitional registry,
  and per-harness failure boundaries.

- [ ] **Step 1: Add failing application isolation and registry tests**

Construct two applications with different configs, states, clocks, and single fake harnesses.
Assert their store roots, collection memo, collector errors, native notification field, popup
notifier, diagnostic sink, and generated timestamps do not cross. Assert discovery exceptions mark
only that harness absent and collector exceptions set only its `error`.
These isolation assertions use runtime-native fake callbacks that consume the supplied config and
state; they do not use the transitional legacy adapters below.

- [ ] **Step 2: Implement concrete application injection**

Keep `collectors/__init__.py` empty. `aggregate.py` has no default registry yet; the transitional
`server.py` supplies the complete tuple explicitly. Use this constructor:

```python
class Application:
    def __init__(
        self,
        config: RuntimeConfig,
        state: RuntimeState,
        harnesses: tuple[HarnessSpec, ...],
        *,
        native_notifier: Callable[[str], str],
        popup_notifier: Callable[[str, str], None],
        diagnostic_sink: Callable[[str], None],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.state = state
        self.harnesses = harnesses
        self.native_notifier = native_notifier
        self.popup_notifier = popup_notifier
        self.diagnostic_sink = diagnostic_sink
        self.clock = clock
```

- [ ] **Step 3: Move aggregation and memoization**

Move `HarnessSpec`, `collect:4646`, `_collect_memo:6253`, and `collect_json:6258` into
`aggregate.py`. Convert `HARNESSES:4585` into a tuple of `HarnessSpec` objects supplied by
`server.py`; do not add `default_harnesses()` yet. Discovery receives config and state. Collector
calls receive config, state, `now`, `window_hours`, and `show_all`.

Keep the existing per-harness exception boundaries, sequential order, session sorting, response
schema, JSON encoding, and collection memo lock scope. Use `state.collect_memo_lock` and
`state.collect_memo`.

- [ ] **Step 4: Supply legacy callables without a reverse import**

In `server.py`, define a private frozen `LegacyHarnessAdapter` bound to exactly one config, state,
legacy discovery callable, and legacy collector callable. Its standard `discover(config, state)`
and `collect(config, state, now, window_hours, show_all)` methods first require identity with the
bound config/state, then call the global-reading legacy function. They must never install config or
state by mutating globals. A mismatch raises `RuntimeError("legacy harness used by another
application")`.

Build these adapters only for the one transitional application. Pass their callbacks into
`Application`; `aggregate.py` must never import `server.py`. Each later collector task replaces one
adapter with a runtime-native callback. Delete the legacy `collect` and `collect_json`
implementations, leaving only temporary adapters for unmoved service code.

- [ ] **Step 5: Run contract, memoization, diagnostics, and route tests**

Expected: all harness registry keys and labels match, diagnostics and `/api/data` use the same
application, one cold concurrent collection occurs, and failure releases the memo lock.

- [ ] **Step 6: Run `sync-docs` and commit**

Update the skill's truth probes to recognize `Application` while the registry remains supplied by
the transitional server.

```bash
rtk git add cargento/skills/cargento .claude/skills/sync-docs/SKILL.md
rtk git commit -s -m "refactor(runtime): establish application boundary"
```

### Task 13: Extract the Codex Collector

**PR:** `refactor(collectors): extract Codex collection`

**Branch:** `refactor/collector-codex`

**Files:**

- Create: `cargento_runtime/collectors/codex.py`
- Modify: `server.py`
- Modify: `tests/test_codex.py`
- Modify: `tests/test_contracts.py`

**Interfaces:**

- Produces: `discover(config, state) -> bool` and the standard collector signature.

- [ ] **Step 1: Redirect Codex direct tests and verify import failure**

Import the new module in `test_codex.py`. Keep the all-harness contract test going through
`Application`.

- [ ] **Step 2: Move Codex behavior**

Move `codex_subagent_rate:2325` and `collect_codex:3377` plus the Codex discovery predicate. Use:

```python
def discover(config: RuntimeConfig, state: RuntimeState) -> bool:
def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[Session]:
```

Read metadata from `transcripts`, turn data from `turns`, and identity/rates from `sessions`.

- [ ] **Step 3: Swap one transitional registry entry and remove legacy symbols**

Replace only the `"codex"` callbacks in the server-supplied tuple. Delete Codex collector
definitions from `server.py`; do not re-export them. Tasks 13-23 follow this same rule: they replace
one server-owned transitional entry and do not modify `aggregate.py`.

- [ ] **Step 4: Run Codex direct, registry, copied-plugin, and full-gate tests**

Confirm parent/subagent folding, rates, Windows path labels, malformed records, and the aggregate
schema are unchanged. Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(collectors): extract Codex collection"
```

### Task 14: Extract the Pi Collector

**PR:** `refactor(collectors): extract Pi collection`

**Branch:** `refactor/collector-pi`

**Files:**

- Create: `cargento_runtime/collectors/pi.py`
- Modify: `server.py`
- Modify: `tests/test_pi.py`
- Modify: `tests/test_contracts.py`

**Interfaces:**

- Produces: state-aware Pi discovery and collection with Pi branch scanner state.

- [ ] **Step 1: Redirect Pi scanner, discovery, and collector tests**

Expected failure: `collectors.pi` is missing.

- [ ] **Step 2: Move the complete Pi responsibility**

Move `_PI_NO_NAME:1545`, `_pi_projection:1549`, `_pi_complete_end:1595`,
`_pi_latest_name:1617`, `_pi_state:1631`, `_pi_last_complete_branch:1641`, `_pi_rebuild:1676`,
`_pi_extend:1704`, `_pi_turn:1731`, `_pi_info:1751`, `scan_pi_session:1777`,
`discover_pi:3437`, and `collect_pi:3450`.

Use `state.scanner_lock`, `state.pi_scan`, and `transcripts.pi_meta(state, path)`. Discovery
must accept state because it shares the bounded first-line metadata cache with collection.

- [ ] **Step 3: Swap the Pi registry entry and delete old code**

Preserve flat/nested store search, valid-header discovery, duplicate selection, partial writes,
branch rebuilding, quiet-gap behavior, and parent-session separation.

- [ ] **Step 4: Run Pi transcript, collector, turn, contract, and full-gate tests**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(collectors): extract Pi collection"
```

### Task 15: Extract the Copilot Collector

**PR:** `refactor(collectors): extract Copilot collection`

**Branch:** `refactor/collector-copilot`

**Files:**

- Create: `cargento_runtime/collectors/copilot.py`
- Modify: `server.py`
- Modify: `tests/test_copilot.py`
- Modify: `tests/test_contracts.py`

**Interfaces:** Produces the standard discovery and collector callables.

- [ ] **Step 1: Redirect Copilot tests and verify import failure**

- [ ] **Step 2: Move `collect_copilot:4075` and its discovery predicate**

Use `transcripts.copilot_meta`, `transcripts.analyze_copilot_events`, generic turns, sessions, and
config-owned store roots. Preserve current and history store discovery.

- [ ] **Step 3: Swap only the Copilot registry entry and remove legacy code**

- [ ] **Step 4: Run Copilot, all-harness, malformed-record, and full-gate tests**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(collectors): extract Copilot collection"
```

### Task 16: Extract the Droid Collector

**PR:** `refactor(collectors): extract Droid collection`

**Branch:** `refactor/collector-droid`

**Files:**

- Create: `cargento_runtime/collectors/droid.py`
- Modify: `server.py`
- Modify: `tests/test_droid.py`
- Modify: `tests/test_contracts.py`

**Interfaces:** Produces the standard discovery and collector callables.

- [ ] **Step 1: Redirect Droid tests and verify import failure**

- [ ] **Step 2: Move `collect_droid:4543` and its discovery predicate**

Use Droid metadata/analyzer, generic turns, sessions, and config roots. Preserve session-start
identity, project selection, title, activity, and malformed-record behavior.

- [ ] **Step 3: Swap only the Droid registry entry and remove legacy code**

- [ ] **Step 4: Run Droid, all-harness, hostile-path, and full-gate tests**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(collectors): extract Droid collection"
```

### Task 17: Extract the OpenCode Collector

**PR:** `refactor(collectors): extract OpenCode collection`

**Branch:** `refactor/collector-opencode`

**Files:**

- Create: `cargento_runtime/collectors/opencode.py`
- Modify: `server.py`
- Modify: `tests/test_sqlite_collectors.py`
- Modify: `tests/test_contracts.py`

**Interfaces:** Produces the standard discovery and collector callables using read-only SQLite.

- [ ] **Step 1: Redirect OpenCode tests and verify import failure**

- [ ] **Step 2: Move `collect_opencode:4137` and its discovery predicate**

Use `io.open_sqlite_read_only`, record accessors, `turns_from_events`, sessions, and state-held store
errors. Keep discovery false when SQLite is unavailable.

- [ ] **Step 3: Swap only the OpenCode registry entry and remove legacy code**

- [ ] **Step 4: Prove read-only and optional-SQLite behavior**

Run OpenCode, SQLite URI, truly-absent-SQLite, corrupt-query, hostile-path, contract, and full-gate
tests. Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(collectors): extract OpenCode collection"
```

### Task 18: Extract the Cursor Collector

**PR:** `refactor(collectors): extract Cursor collection`

**Branch:** `refactor/collector-cursor`

**Files:**

- Create: `cargento_runtime/collectors/cursor.py`
- Modify: `server.py`
- Modify: `tests/test_sqlite_collectors.py`
- Modify: `tests/test_contracts.py`

**Interfaces:** Produces the standard collector and owns Cursor metadata cache entries in state.

- [ ] **Step 1: Redirect Cursor tests and verify import failure**

- [ ] **Step 2: Move Cursor constants and functions**

Move `_CURSOR_CWD_KEYS`, `_ABS_PATH_RE`, `_CURSOR_META_ROWS`, `_cursor_workspace:4261`,
`_cursor_meta:4287`, `collect_cursor:4363`, and the discovery predicate. Replace
`_cursor_meta_cache` with `state.cursor_metadata_cache` under `state.cache_lock`.

- [ ] **Step 3: Swap only the Cursor registry entry and delete old symbols**

- [ ] **Step 4: Run Cursor, cache, SQLite, hostile-path, and full-gate tests**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(collectors): extract Cursor collection"
```

### Task 19: Extract the Goose Collector

**PR:** `refactor(collectors): extract Goose collection`

**Branch:** `refactor/collector-goose`

**Files:**

- Create: `cargento_runtime/collectors/goose.py`
- Modify: `server.py`
- Modify: `tests/test_sqlite_collectors.py`
- Modify: `tests/test_contracts.py`

**Interfaces:** Produces the standard discovery and collector callables using read-only SQLite.

- [ ] **Step 1: Redirect Goose tests and verify import failure**

- [ ] **Step 2: Move `goose_user_prompt:4399`, `collect_goose:4412`, and
`collect_goose_db:4423`**

Move the Goose discovery predicate too. Preserve all candidate DB locations, content filtering,
turn construction, query failure recording, and no-SQLite behavior.

- [ ] **Step 3: Swap only the Goose registry entry and delete old symbols**

- [ ] **Step 4: Run Goose, SQLite, cross-platform store, contract, and full-gate tests**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(collectors): extract Goose collection"
```

### Task 20: Extract Composite Gemini and Antigravity Collection

**PR:** `refactor(collectors): extract Gemini and Antigravity collection`

**Branch:** `refactor/collector-gemini-antigravity`

**Files:**

- Create: `cargento_runtime/collectors/gemini.py`
- Modify: `server.py`
- Modify: `tests/test_gemini_antigravity.py`
- Modify: `tests/test_contracts.py`

**Interfaces:**

- Produces: one `"gemini"` discovery and collection boundary covering both source families.

- [ ] **Step 1: Redirect all Gemini/Antigravity tests and verify import failure**

- [ ] **Step 2: Move Antigravity parsing and collection as one unit**

Move `antigravity_log_head_lines:3500` through `collect_antigravity:3891`, including protobuf
parsing, WAL checks, metadata, step activity, cache/log fallback, and subagent folding.
Replace its three calls to the former `notification_text` with `records.safe_text` at the same
limits. Replace `antigravity_log_head_lines`' direct read with `io.read_prefix_bytes`, passing
`config.antigravity_log_head_bytes`, then preserve the existing replacement decode and
`splitlines()` behavior; keep the before/after-cap fixtures from Task 8 green.

- [ ] **Step 3: Move Gemini orchestration**

Move `collect_gemini:4002` and the composite discovery predicate. Keep
`collect_gemini -> collect_antigravity` composition and one registry key, label, discovery result,
and error boundary. Do not create `collectors/antigravity.py`.

- [ ] **Step 4: Swap the one registry entry and delete all moved symbols**

- [ ] **Step 5: Run snapshot, WAL, protobuf, cache, subagent, future-time, copied-plugin, and full
gate tests**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(collectors): extract Gemini and Antigravity collection"
```

### Task 21: Extract Shared Claude Data

**PR:** `refactor(runtime): extract shared Claude transcript data`

**Branch:** `refactor/claude-data`

**Files:**

- Create: `cargento_runtime/claude_data.py`
- Modify: `server.py`
- Modify: `tests/test_claude.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_spacedock.py`

**Interfaces:**

- Produces: Claude transcript facts and classification below Spacedock, notifications, and the
  Claude collector.

- [ ] **Step 1: Redirect direct Claude data tests and verify import failure**

- [ ] **Step 2: Move shared Claude facts**

Move `claude_session_title:1127`, `claude_last_user_event:1188`, `analyze_transcript:1224`,
`claude_session_cwd:1272`, `claude_hook_user_event:1316`, `claude_agent_identity:2677`,
`claude_agent_setting:2739`, and `claude_prefix_is_agent:3129`, with their regex/constants.

Replace title, user-event, CWD, and agent-class globals with the corresponding `RuntimeState`
caches under `state.cache_lock`. Replace direct bounded reads in CWD and agent classification: CWD
uses `io.iter_bounded_text_lines` with the configured per-line and line-count limits; agent identity
and setting use `io.read_prefix_bytes`, cap the parsed line list, and retain the current
partial-tail drop rule. Tests must put a relevant record immediately before and after each bound
and assert the after-bound record is never consumed.

- [ ] **Step 3: Update still-local consumers**

Update `server.py` Spacedock, notification, and Claude collector callers to pass config/state.
Delete moved definitions. `claude_data.py` may import config, state, I/O, records, transcripts, and
sessions; it may not import collectors, Spacedock, notifications, HTTP, lifecycle, or CLI.

- [ ] **Step 4: Run Claude, notification race, Spacedock attribution, malformed-record, and full
gate tests**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract shared Claude transcript data"
```

### Task 22: Extract Spacedock Cartography

**PR:** `refactor(runtime): extract Spacedock cartography`

**Branch:** `refactor/spacedock`

**Files:**

- Create: `cargento_runtime/spacedock.py`
- Modify: `server.py`
- Modify: `tests/test_spacedock.py`
- Modify: `tests/test_claude.py`

**Interfaces:**

- Consumes: config/state, Claude classification, and secure local I/O.
- Produces: parsed workflow and entity attribution used by the Claude collector.

- [ ] **Step 1: Redirect Spacedock parser/read tests and verify import failure**

- [ ] **Step 2: Move the complete secure-read boundary**

Move Spacedock constants at `server.py:2350-2416`; `sd_frontmatter_lines:2419` through
`sd_boot_entity_dir:2646`; `sd_transcript_boot:2780`; `SdMismatchError:2834`;
`sd_open_regular:2809`,
`sd_read_frontmatter:2839`, `sd_read_workflow:2875`, `sd_entity_stage:2928`,
`sd_entity_files:2949`, `sd_read_entities:3001`, `sd_attribute_worker:3030`, and
`sd_session_workflows:3062`.

Move role, boot, workflow, and entity caches into `RuntimeState`. Preserve `lstat`/`fstat` identity
checks, symlink refusal, read bounds, descriptor cleanup, and no-walk fast paths.

- [ ] **Step 3: Update Claude orchestration and remove old symbols**

Keep `claude_spacedock` collector-side until Task 24. It calls the new lower API and respects
`config.spacedock_enabled`.

- [ ] **Step 4: Run every Spacedock parser/read/security test and the full gate**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract Spacedock cartography"
```

### Task 23: Extract Notification State and Native Alerts

**PR:** `refactor(runtime): extract notification handling`

**Branch:** `refactor/notifications`

**Files:**

- Create: `cargento_runtime/notifications.py`
- Modify: `server.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_http_api.py`
- Modify: `tests/test_contracts.py`

**Interfaces:**

- Consumes: config/state and `claude_data`.
- Produces: native notifier selection, popup policy, hook lookup, and HTTP-neutral payload handling.

- [ ] **Step 1: Redirect notification tests and verify import failure**

- [ ] **Step 2: Move notification ownership**

Move notification constants at `server.py:311-333`, `normalized_notification_type:376`,
`notification_disposition:381`, `native_notifier:2181`,
`notify_mac:2198`, `hook_generation:2223`, `current_hook:2229`, and `maybe_popup:2253`.
Import `records.safe_text` for notification payload sanitization.

Add:

```python
def handle_payload(
    config: RuntimeConfig,
    state: RuntimeState,
    payload: dict[str, Any],
    *,
    now: float,
    popup_notifier: Callable[[str, str], None],
) -> dict[str, Any]:
```

Move the SessionEnd, generation, suppression, cooldown, repeat, state-clear, and popup decisions
from `Handler.do_POST` into this function. It calls `claude_data` and the injected
`popup_notifier`; it returns the current JSON response object for the HTTP layer to encode.

Make `notify_mac(config, title, message, *, diagnostic_sink)` explicit in both platform selection
and error reporting. CLI assembly binds it to the application's config/sink and supplies that bound
two-argument callable as `Application.popup_notifier`. No notification path may recover either
dependency from a module global.

- [ ] **Step 3: Make HTTP delegate without importing a collector**

Leave route parsing and request-size validation in `server.py`, but replace notification policy
with one `handle_payload` call. Delete notification globals and moved definitions. The HTTP code
must not import the Claude collector.

- [ ] **Step 4: Prove race ordering and two-state isolation**

Run SessionEnd generation, concurrent notification, native notifier, HTTP, two-application,
subagent suppression, popup cooldown, and full-gate tests.

- [ ] **Step 5: Run `sync-docs` and commit**

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract notification handling"
```

### Task 24: Extract the Claude Collector

**PR:** `refactor(collectors): extract Claude collection`

**Branch:** `refactor/collector-claude`

**Files:**

- Create: `cargento_runtime/collectors/claude.py`
- Modify: `cargento_runtime/aggregate.py`
- Modify: `server.py`
- Modify: `tests/test_claude.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_spacedock.py`
- Modify: `.claude/skills/sync-docs/SKILL.md`

**Interfaces:**

- Consumes: shared Claude data, notifications, Spacedock, sessions, and generic turns.
- Produces: the final standard collector callback.

- [ ] **Step 1: Redirect Claude collector tests and verify import failure**

- [ ] **Step 2: Move tasks, subagents, and collection**

Move `load_tasks:2081`, `claude_agent_transcripts:2134`, `load_claude_subagents:2151`,
`collect_claude:3145`, and `claude_spacedock:3345`, plus the Claude discovery predicate.

- [ ] **Step 3: Swap the Claude registry entry and remove legacy symbols**

Preserve hook-vs-transcript ordering, SessionEnd generation, task roots, subagent folding,
Spacedock strips, popup transitions, timestamps, and response schema. Collector code may read
notification state through public notification functions, not notification dictionaries directly.

- [ ] **Step 4: Finalize the registry in `aggregate.py`**

Add `default_harnesses() -> tuple[HarnessSpec, ...]` in the existing key/label order. It imports
the collector modules and binds each module's `discover` and `collect` functions. Collector modules
must import `Session` from `sessions.py`, never `HarnessSpec` or another name from `aggregate.py`.
Replace the temporary server-supplied registry with `default_harnesses()` and delete
`LegacyHarnessAdapter` plus the transitional primary-root aliases.

- [ ] **Step 5: Assert `server.py` now owns no collector**

Add a source contract assertion that no `def collect_claude`, `def collect_codex`, `def collect_pi`,
or other harness collector remains in `server.py`, and that every registry callback resolves to a
module below `cargento_runtime.collectors`.

- [ ] **Step 6: Run every collector module, contracts, diagnostics, HTTP, copied-plugin, and full
gate**

Update the skill's collector-registry truth probe from the transitional server tuple to
`aggregate.default_harnesses`, then run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento .claude/skills/sync-docs/SKILL.md
rtk git commit -s -m "refactor(collectors): extract Claude collection"
```

### Task 25: Extract Diagnostics

**PR:** `refactor(runtime): extract dashboard diagnostics`

**Branch:** `refactor/diagnostics`

**Files:**

- Create: `cargento_runtime/diagnostics.py`
- Modify: `server.py`
- Modify: `tests/test_config_diagnostics.py`
- Modify: `tests/test_contracts.py`

**Interfaces:**

- Consumes: the same `Application`, config, state, and registry used for normal collection.
- Produces: structured and ASCII diagnostic output.

- [ ] **Step 1: Redirect diagnostics tests and verify import failure**

- [ ] **Step 2: Move diagnostics as one service**

Move `store_primaries:7071`, `candidate_report:7089`, `diagnose:7125`, and
`render_diagnosis:7170`. Use:

```python
def diagnose(application: Application) -> dict[str, Any]:
def render_diagnosis(report: dict[str, Any]) -> str:
```

Derive store primaries from `application.config`, call `application.collect(show_all=True)`, clear
and snapshot `application.state.store_errors` under the cache lock, and iterate
`application.harnesses`. Do not create a second harness list or store-path table.

- [ ] **Step 3: Replace server adapters and delete old definitions**

The current `--diagnose` path calls this module and preserves JSON formatting, ASCII rendering,
stderr behavior, exit code, corrupt-store reporting, and optional-SQLite details.

- [ ] **Step 4: Run diagnosis, all-harness, optional-SQLite, unreadable/special-file, and full-gate
tests**

Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract dashboard diagnostics"
```

### Task 26: Extract HTTP Handling and Instance Injection

**PR:** `refactor(runtime): extract loopback HTTP service`

**Branch:** `refactor/http-service`

**Files:**

- Create: `cargento_runtime/http_api.py`
- Modify: `server.py`
- Modify: `tests/test_http_api.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/support.py`
- Modify: `.claude/skills/sync-docs/SKILL.md`

**Interfaces:**

- Consumes: one `Application` and one assembled page.
- Produces: `CargentoHTTPServer` and its private request handler.

- [ ] **Step 1: Add a failing two-server isolation test**

Start two servers concurrently with different fake harness labels, generated data, config ports,
states, and page bytes. Assert `/`, `/api/data`, `/api/health`, and notification POSTs return only
the owning server's data. A SessionEnd on server A must not clear server B.

- [ ] **Step 2: Move network helpers and server class**

Move `normalize_host:644`, `reuse_address_allowed:673`, `bind_error_message:686`,
`LoopbackHTTPServer:706`, and `Handler:6851` into `http_api.py`. Rename the server
`CargentoHTTPServer` and the handler `_RequestHandler`.

Implement:

```python
class CargentoHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        application: Application,
        page_bytes: bytes,
    ) -> None:
        self.application = application
        self.page_bytes = page_bytes
        self.allow_reuse_address = reuse_address_allowed(application.config.os_name)
        super().__init__(address, _RequestHandler)
```

The handler reads `self.server.application` and `self.server.page_bytes`. It keeps Host and Origin
checks, DNS-rebinding defense, request limit, GET navigation exception, response headers, route
status codes, and reply-before-shutdown ordering. The request body cap comes only from
`application.config.notification_body_cap_bytes`; reject an oversized declared length before
reading and never perform an unbounded request-body read.
If exclusive port setup fails, report through `application.diagnostic_sink` before continuing.

- [ ] **Step 3: Delegate application and notification behavior**

`/api/data` calls `application.collect_json`; `/api/notify` calls
`notifications.handle_payload` with `application.popup_notifier`; `/api/health` reads only PID,
port, and
`application.state.server_started`; `/` serves the instance page. No health call may inspect
registry discovery or stores. Add a sentinel-start test that asserts the health JSON reports the
exact value captured by `build_runtime_state`, with no second clock read.

- [ ] **Step 4: Update server construction and remove old HTTP definitions**

Import `CargentoHTTPServer` in `server.py` and pass application/page explicitly. Update support
thread helpers and tests. Delete old server/handler classes and temporary page storage.

- [ ] **Step 5: Run route, security, shutdown, two-server, health-no-I/O, and full-gate tests**

Update the skill's route and HTTP-owner truth probes, then run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento .claude/skills/sync-docs/SKILL.md
rtk git commit -s -m "refactor(runtime): extract loopback HTTP service"
```

### Task 27: Extract Process Lifecycle

**PR:** `refactor(runtime): extract dashboard lifecycle`

**Branch:** `refactor/lifecycle`

**Files:**

- Create: `cargento_runtime/lifecycle.py`
- Modify: `server.py`
- Modify: `tests/test_lifecycle.py`
- Modify: `tests/test_http_api.py`
- Modify: `tests/support.py`

**Interfaces:**

- Consumes: config and the injected HTTP server.
- Produces: state-file, probe, stop, bind, fork/spawn, and serving operations.

- [ ] **Step 1: Redirect lifecycle unit tests and verify import failure**

Keep the real detach/outlive/status/stop tests invoking the stable `server.py`; redirect direct
helper tests to the new module.

- [ ] **Step 2: Move state and probe operations**

Move `tcp_port:6295`, `cargento_home:6306`, `state_path:6319`, `log_path:6323`,
`ensure_cargento_home:6327`, `write_state:6339`, `read_state:6369`, `remove_state:6390`,
`probe_port:6395`, `port_released:6439`, `await_release:6481`, `instance_status:6500`,
`render_status:6523`, and `stop_instance:6553`.

Replace ambient home and port reads with config or explicit parameters. Keep health identity checks,
PID/state-file rules, non-200 stop refusal, timeout behavior, and release probing.
For `await_release`, `await_daemon`, and `await_spawned`, keep `timeout: float | None = None` and
read the matching config value inside the function body. Do not bind a configurable timeout in a
default argument.

- [ ] **Step 3: Move daemon operations**

Move `_FORK`, `_SETSID`, `fork_daemon:6625`, `daemon_redirect_stdio:6665`,
`daemon_announce:6681`, `await_daemon:6689`, `forwarded_args:6751`, `spawn_detached:6765`,
`log_tail:6781`, and `await_spawned:6795`.

Replace the flags-only `forwarded_args` helper with one complete `spawn_argv` contract. Use
`config.launcher_path` as the only respawn script:

```python
def spawn_argv(config: RuntimeConfig, args: argparse.Namespace) -> list[str]:
    argv = [
        sys.executable,
        str(config.launcher_path),
        "--port",
        str(args.port),
        "--window-hours",
        str(args.window_hours),
    ]
    if args.no_spacedock:
        argv.append("--no-spacedock")
    return argv
```

`spawn_detached` must call `subprocess.Popen(spawn_argv(config, args), ...)` directly; it must not
prefix another interpreter or launcher. Do not forward `--daemon`; the spawned child is the
foreground server. Add an exact Windows-path assertion for the entire argv list.

- [ ] **Step 4: Move branch-specific serve/cleanup ordering**

Preserve these three distinct sequences; there is deliberately no generic "bind before detach"
rule:

1. Windows daemon parent validates assets, state home, and log path, then spawns a foreground child
   and awaits that child's PID/health identity. The parent never constructs or binds
   `CargentoHTTPServer`.
2. POSIX daemon binds in the attached process, forks, lets the daemon write state and announce
   readiness, then serves.
3. Foreground mode binds, writes state, and serves in the same process.

The serving process in either branch removes only its own state and closes its socket in `finally`.
Add a Windows unit test that substitutes the server constructor with a failure and proves the
daemon parent never calls it; the spawned foreground child remains responsible for bind errors.

- [ ] **Step 5: Delete old lifecycle code and run all lifecycle gates**

Run unit helpers, real daemon, busy-port, stop refusal, Windows argv, arbitrary-CWD, copied-plugin,
platform expectations, and full gate. Run `sync-docs` and commit:

```bash
rtk git add cargento/skills/cargento
rtk git commit -s -m "refactor(runtime): extract dashboard lifecycle"
```

### Task 28: Extract CLI Assembly and Reduce the Launcher

**PR:** `refactor(skill): reduce server to stable launcher`

**Branch:** `refactor/thin-server-launcher`

**Files:**

- Create: `cargento_runtime/cli.py`
- Modify: `server.py`
- Modify: `tests/test_lifecycle.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_config_diagnostics.py`
- Modify: `pyproject.toml`
- Modify: `.claude/skills/sync-docs/SKILL.md`

**Interfaces:**

- Consumes: every completed runtime module.
- Produces: `cli.main(argv: Sequence[str] | None = None) -> int` and the final stable launcher.

- [ ] **Step 1: Add failing CLI and launcher-forwarding tests**

Test `cli.main` with explicit argument lists for help, invalid combinations, diagnosis JSON/text,
status, stop, foreground, POSIX daemon, and Windows daemon. Patch service boundaries, not module
globals. Add a `runpy.run_path` test that substitutes `cargento_runtime.cli.main` and proves
`server.py` calls it once only with `runpy.run_path(SERVER_PATH, run_name="__main__")`.

- [ ] **Step 2: Move argument parsing and runtime assembly**

Move `main:7219` into `cli.py` and change it to return exit codes instead of raising except where
`argparse` owns `SystemExit`. Use:

```python
def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
```

Use this common prefix:

1. parse arguments, with help and parser-owned errors remaining under `argparse`;
2. capture the process start time once, before the daemon-combination check, matching current
   `main()`;
3. validate argument combinations;
4. build config/state/application without operational side effects, injecting the captured time;
5. handle diagnose, stop, and status exits;
6. warn about missing optional SQLite;
7. load frontend assets;
8. validate daemon home/log;

After the common prefix, branch explicitly:

- Windows daemon: spawn the foreground child and await its identity; do not construct a server in
  the parent.
- POSIX daemon: construct/bind the server, fork, then serve in the daemon.
- Foreground: construct/bind the server, then serve.

This keeps recovery commands available when assets are missing, reports asset/log errors while
stderr is attached, preserves the current Windows child-owned bind, and preserves the POSIX
bind-before-fork behavior.

- [ ] **Step 3: Delete all transitional adapters and globals**

Remove `_legacy_runtime`, legacy root constants, cache dictionaries, locks, registry wrappers,
application/page adapters, and every remaining business function from `server.py`. Tests must use
`make_runtime` and injected services. Remove the transitional dynamic `server.py` loader from
`tests/support.py`; standard runtime imports become the default, while launcher checks use
`runpy` or isolated subprocesses. Remove the old `server.py` Ruff complexity/line-length
exemptions; retain only narrowly justified exemptions on the runtime files that still require
them.

- [ ] **Step 4: Replace `server.py` with the stable launcher**

Final content:

```python
#!/usr/bin/env python3
"""Launch the Cargento dashboard."""

from cargento_runtime.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

No internal symbol re-exports are permitted.

- [ ] **Step 5: Assert final import and source contracts**

Assert:

- `server.py` imports only `cargento_runtime.cli.main`;
- no namespace-qualified runtime module exists in `sys.modules`;
- a fresh copied-plugin interpreter walks `cargento_runtime.__path__` with
  `pkgutil.walk_packages`, imports every discovered module, and reports every `module.__file__`
  under the copied skill directory;
- the same probe resolves all three `web.page.asset_path` values below that copied directory;
- importing every runtime module opens no stores, sockets, browsers, logs, or subprocesses;
- help, diagnose, status, and stop still work with missing assets;
- direct launch works from an unrelated directory on Python 3.11.

Run the copied-origin probe from an unrelated directory with repository paths removed,
`PYTHONPATH` absent, and `PYTHONNOUSERSITE=1`. It must inspect every walked module, not a
hand-maintained subset.

- [ ] **Step 6: Finalize line-count, dependency, and full behavior checks**

Finalize the `test_runtime_import_graph` contract introduced in Task 6. Parse every runtime `.py`
file with `ast`, normalize `Import` and `ImportFrom` targets to top-level runtime modules, and reject
any direct runtime dependency not listed below:

| Module | May import only these runtime modules |
|---|---|
| `config` | none |
| `state` | `config` |
| `io` | `config`, `state` |
| `records` | `config`, `state` |
| `sessions` | `config`, `records` |
| `transcripts` | `config`, `state`, `io`, `records`, `sessions` |
| `turns` | `config`, `state`, `io`, `records` |
| `claude_data` | `config`, `state`, `io`, `records`, `transcripts`, `sessions` |
| `spacedock` | `config`, `state`, `io`, `records`, `claude_data`, `sessions` |
| `notifications` | `config`, `state`, `records`, `claude_data` |
| each `collectors/*` module | `config`, `state`, `io`, `records`, `transcripts`, `turns`, `sessions`, `claude_data`, `spacedock`, `notifications` |
| `aggregate` | `config`, `state`, `sessions`, `collectors` |
| `diagnostics` | `config`, `state`, `io`, `aggregate` |
| `http_api` | `config`, `state`, `aggregate`, `notifications` |
| `lifecycle` | `config`, `io`, `http_api` |
| `cli` | any runtime module |
| `web.page` | none |
| all three package initializers (`cargento_runtime`, `collectors`, `web`) | none |

Collector modules may not import another collector or `aggregate`; the test handles that
submodule-level rule separately. Type-checking imports count like runtime imports, so there is no
`TYPE_CHECKING` escape hatch. Fail on namespace-qualified
`cargento.skills.cargento.cargento_runtime` imports and on relative imports that climb above the
runtime package. The allowlist may change only in the PR where a reviewed ownership decision
requires it, never merely to make the test pass.

Then use Ruff, mypy, and this source contract to enforce inward dependencies. Review modules above
1,000 lines manually and split only if they hold more than one responsibility.

- [ ] **Step 7: Run `sync-docs` and commit**

Update the skill's launcher, CLI-flag, and runtime-owner probes before running it.

```bash
rtk git add cargento/skills/cargento pyproject.toml .claude/skills/sync-docs/SKILL.md
rtk git commit -s -m "refactor(skill): reduce server to stable launcher"
```

### Task 29: Validate the Complete Shipped Runtime

**PR:** `build(plugin): validate shipped runtime inventory`

**Branch:** `refactor/runtime-packaging-validation`

**Files:**

- Modify: `scripts/validate_plugins.py`
- Modify: `scripts/tests/test_validate_plugins.py`
- Modify: `.github/workflows/plugin-compatibility.yml`
- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`

**Interfaces:**

- Consumes: the stable final file layout.
- Produces: validator-owned required-file inventory and installed-copy end-to-end smoke.

- [ ] **Step 1: Add failing validator inventory tests**

Test that a complete copied plugin passes; a missing launcher, hook, package initializer, runtime
module, collector, or frontend asset fails with its relative path; and a directory in place of a
required file fails.

- [ ] **Step 2: Add the exact required-file tuple**

Add this validator-owned inventory:

```python
CARGENTO_RUNTIME_FILES = (
    "skills/cargento/server.py",
    "skills/cargento/notify_hook.py",
    "skills/cargento/cargento_runtime/__init__.py",
    "skills/cargento/cargento_runtime/cli.py",
    "skills/cargento/cargento_runtime/config.py",
    "skills/cargento/cargento_runtime/state.py",
    "skills/cargento/cargento_runtime/io.py",
    "skills/cargento/cargento_runtime/records.py",
    "skills/cargento/cargento_runtime/transcripts.py",
    "skills/cargento/cargento_runtime/turns.py",
    "skills/cargento/cargento_runtime/sessions.py",
    "skills/cargento/cargento_runtime/claude_data.py",
    "skills/cargento/cargento_runtime/notifications.py",
    "skills/cargento/cargento_runtime/spacedock.py",
    "skills/cargento/cargento_runtime/aggregate.py",
    "skills/cargento/cargento_runtime/diagnostics.py",
    "skills/cargento/cargento_runtime/lifecycle.py",
    "skills/cargento/cargento_runtime/http_api.py",
    "skills/cargento/cargento_runtime/collectors/__init__.py",
    "skills/cargento/cargento_runtime/collectors/claude.py",
    "skills/cargento/cargento_runtime/collectors/codex.py",
    "skills/cargento/cargento_runtime/collectors/pi.py",
    "skills/cargento/cargento_runtime/collectors/gemini.py",
    "skills/cargento/cargento_runtime/collectors/copilot.py",
    "skills/cargento/cargento_runtime/collectors/opencode.py",
    "skills/cargento/cargento_runtime/collectors/cursor.py",
    "skills/cargento/cargento_runtime/collectors/goose.py",
    "skills/cargento/cargento_runtime/collectors/droid.py",
    "skills/cargento/cargento_runtime/web/__init__.py",
    "skills/cargento/cargento_runtime/web/index.html",
    "skills/cargento/cargento_runtime/web/styles.css",
    "skills/cargento/cargento_runtime/web/app.js",
    "skills/cargento/cargento_runtime/web/page.py",
)
```

Implement `validate_runtime_files(plugin_root, validation)` near `validate_skills` and call it for
Cargento. Use `Path.is_file()` and path-specific diagnostics. Do not add native-manifest fields or
edit versions.

- [ ] **Step 3: Make plugin compatibility test the installed copy**

Persist the installed Codex plugin path in `.github/workflows/plugin-compatibility.yml`. Launch
that absolute installed `server.py`, not the checkout, from an unrelated directory. Remove
`PYTHONPATH`, set `PYTHONNOUSERSITE=1`, give the process a temporary `CARGENTO_HOME` and unique free
port, read health/root/data, and stop it.

Install `requirements-validation.txt` explicitly and invoke
`validate_runtime_files(installed_plugin_root, validation)` from the validator. The workflow must
not repeat `CARGENTO_RUNTIME_FILES` in YAML or shell. Keep the inventory check separate from the
end-to-end launch so a missing file produces its precise validator diagnostic.

Register a shell cleanup trap before launch. On success or any intermediate failure, call the
installed launcher's `--stop`, then terminate/kill and wait for the captured foreground PID if
needed, and verify the chosen port is released. The trap must use only the temporary state
directory and captured PID; it must not kill by process name.

- [ ] **Step 4: Run validator mutation tests and installed-copy smoke locally**

Delete one required file at a time only inside temporary copies. Expected: each category is caught.
Run the validator-owned inventory against a temporary installed copy, then the isolated
arbitrary-CWD launch smoke. Run native Claude and AGY validators when available.

- [ ] **Step 5: Run `sync-docs` and commit**

```bash
rtk git add scripts .github/workflows/plugin-compatibility.yml AGENTS.md CONTRIBUTING.md
rtk git commit -s -m "build(plugin): validate shipped runtime inventory"
```

### Task 30: Publish Durable Architecture and Retire the Plans

**PR:** `docs(architecture): document modular dashboard runtime`

**Branch:** `refactor/document-runtime-architecture`

**Files:**

- Create: `docs/design-runtime-architecture.md`
- Modify: `docs/design-daemon.md`
- Modify: `docs/design-cross-platform.md`
- Modify: `docs/design-session-identity.md`
- Modify: `docs/design-spacedock.md`
- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`
- Modify: `COMPATIBILITY.md`
- Modify: `README.md`
- Modify: `SECURITY.md`
- Modify: `.claude/skills/sync-docs/SKILL.md`
- Delete: `docs/plans/2026-07-29-cargento-functional-split-design.md`
- Delete: `docs/plans/2026-07-29-cargento-functional-split-implementation.md`

**Interfaces:**

- Consumes: the shipped final structure.
- Produces: durable documentation owned by subject and no stale transient plan.

- [ ] **Step 1: Write the durable architecture owner**

`docs/design-runtime-architecture.md` must own:

- the final package tree and one-responsibility file map;
- inward-only dependency direction;
- top-level canonical import identity;
- RuntimeConfig, RuntimeState, Application, HTTP instance, and CLI ownership;
- package-relative frontend loading;
- independently testable collectors;
- the rejected one-shot move, partial-only split, permanent facade, and line-count gate.

- [ ] **Step 2: Reconcile existing durable owners**

Update:

- `design-daemon.md` for `lifecycle.py` and the thin launcher;
- `design-cross-platform.md` for config/I/O ownership;
- `design-session-identity.md` for sessions/aggregate ownership;
- `design-spacedock.md` for the Spacedock/Claude boundary;
- `SECURITY.md` for component ownership without weakening any invariant.

Link to the new owner instead of repeating its module map.

- [ ] **Step 3: Reconcile contributor and compatibility surfaces**

Update `AGENTS.md`, `CONTRIBUTING.md`, `COMPATIBILITY.md`, and `README.md` for:

- the final runtime/test tree;
- Python 3.11 floor smoke versus Python 3.12 full/platform gates;
- behavior-focused discovery;
- frontend asset linting;
- required runtime-file validation;
- adding a collector through `HarnessSpec`;
- stable launcher and copied-plugin contract.

Update `.claude/skills/sync-docs/SKILL.md` truth probes, code paths, test commands, and asset wording.
This is a final consolidation and stale-reference audit; Tasks 2, 6, 7, 12, 24, 26, and 28
already update the probes at each ownership transition, so Task 30 must not be the first PR that
teaches the skill about any shipped owner.

- [ ] **Step 4: Delete only the completed split plans**

Delete this implementation plan and its design. Keep `docs/plans/native-notifications.md`.

- [ ] **Step 5: Run `sync-docs` and the final acceptance matrix**

Run the `sync-docs` skill, then every pre-PR command in `AGENTS.md`, native validators when
available, arbitrary-CWD launch, copied-plugin launch, Python 3.11 smoke, and all three platform
jobs. Confirm:

- `server.py` is launcher-only;
- no runtime/test module combines unrelated responsibilities;
- no unexplained coverage regression exists;
- `fail_under` is unchanged or higher;
- no plugin version changed;
- all Markdown links and anchors resolve;
- no completed split plan remains.

- [ ] **Step 6: Commit**

```bash
rtk git add docs AGENTS.md CONTRIBUTING.md COMPATIBILITY.md README.md SECURITY.md \
  .claude/skills/sync-docs/SKILL.md
rtk git commit -s -m "docs(architecture): document modular dashboard runtime"
```

## Completion Handoff

After Task 30 merges, update `main`, prune only merged local task branches, and run the final
acceptance matrix once from the merged tree. The refactor is complete only when the stable launcher,
copied-plugin smoke, native platform suite, Python 3.11 smoke, required runtime inventory, and
`sync-docs` all pass from `main`.
