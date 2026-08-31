# Future UI Command Surface Implementation Plan

> **Design:** `docs/plans/future-ui-command-surface-design.md`
>
> **Execution:** Inline on the existing isolated `feat/future-ui` worktree, as authorized by the captain.

**Goal:** Make `?next=true` a lede-first, source-bound command surface on the overview, project, and session routes.

**Architecture:** Add small view-local derivation helpers to the existing next-page JavaScript assets. Keep the API payload and stable page unchanged. Render the same derived command facts in an overview brief and a session command frame, and explicitly qualify all absence claims.

**Tech stack:** Vanilla JavaScript assembled by `page.py`, CSS, Python `unittest` behavior harness, SHA-256 byte-pin contract.

---

### Task 1: Pin the overview command brief

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_projects.py`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-projects.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/styles.css`

1. Replace the five-column table assertions with literal behavior assertions for captain lede, situation, response, bounded qualifier, priority order, progress, workflows, and same-label caveat.
2. Run `python3 -m unittest cargento.skills.cargento.tests.test_next_projects` and observe the new assertions fail against the old table.
3. Implement ask matching, command priority, and briefing-row rendering. Do not expose estimate/delegation placeholders.
4. Add responsive styles using existing tokens and focus behavior.
5. Re-run the focused module until green.

### Task 2: Pin the four-part session command frame

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_session.py`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-session.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/styles.css`

1. Add behavioral fixtures for a clipped Claude title/full `asked` instruction, Codex missing command facts, AGY missing command facts, an exact ask, and a published task.
2. Run `python3 -m unittest cargento.skills.cargento.tests.test_next_session` and observe the frame assertions fail.
3. Implement source-owner, assignment, execution, next, and captain derivations. Escape all payload strings at render sites.
4. Render the command frame ahead of health/tasks/subagents; retain current controls below it.
5. Re-run the focused module until green.

### Task 3: Bound workflow and state-change claims

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_project.py`
- Modify: `cargento/skills/cargento/tests/test_next_workstream.py`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-project.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-workstream.js`

1. Change behavior expectations to uncertain workflow-source copy, `OBSERVED STATE CHANGES`, full harness labels, and a tab-local empty state.
2. Run both focused modules and observe the old declarative/initialism copy fail.
3. Make the smallest renderer changes that satisfy the source boundary.
4. Re-run both modules until green.

### Task 4: Recompute byte contracts and verify candidate

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_page.py`

1. Run the focused changed modules together.
2. Derive changed part sizes and SHA-256 values directly from their bytes; derive assembled-page size and SHA-256 through `page.next_page()`.
3. Update the literal pins and run `test_next_page`.
4. Run `python3 scripts/lint_embedded.py` and `python3 scripts/validate_plugins.py`.
5. Review `git diff`, commit with DCO sign-off, and push `feat/future-ui`.

### Task 5: Capture exact-byte Chrome evidence

**Files:**
- Add: state-checkout files under `future-ui-command-surface/prototyping/`
- Modify: split-root entity `future-ui-command-surface/index.md`

1. Start the committed dashboard candidate and record its PID.
2. Use Chrome to capture overview, project, and the same Codex, Claude, and AGY session identities as reconnaissance.
3. Stop only the dashboard PID started here.
4. Append one prototyping iteration with before/after links, reconnaissance finding dispositions, candidate SHA, focused checks, and the exact stage checklist.
5. Commit and push the path-scoped state change, then emit the exact completion signal.
