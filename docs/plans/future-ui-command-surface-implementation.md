# Future UI Command Surface Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the future overview, project, session, and live-refresh surfaces disclose only
meaningful source-backed command facts while keeping current activity primary.

**Architecture:** Keep the API and stable page unchanged. Add view-local evidence predicates and
render optional regions from those predicates; track last successful refresh and in-flight state in
the existing next-page client. Retain the independently assembled frontend and regenerate its byte
contracts from the final assets.

**Tech Stack:** Vanilla JavaScript assembled by `page.py`, CSS, Python `unittest` behavior harness,
SHA-256 byte-pin contract, live Chrome evidence.

**Spec:** `docs/plans/future-ui-command-surface-design.md`

## Global Constraints

- `CAPTAIN` requires both an exact ask and positive Spacedock evidence; a plain exact ask uses
  `NEEDS YOU`; no ask emits no top-level request lede.
- A project without any non-null Spacedock record omits the workflow region and wrapper entirely.
- Current activity is the invariant session lede; assignment, next, and response are optional.
- Missing command facts appear only in collapsed, plain-language source coverage.
- One failed data refresh is quiet; two failures preserve the last view and explain stale risk,
  age, cadence, and safe recovery without claiming the event stream stopped.
- Do not change collectors, the API payload, the stable UI, or version fields.
- Run focused frontend tests serially and regenerate byte pins mechanically after all asset edits.
- Keep all product commits on `feat/future-ui`; do not merge or target `main`.

---

### Task 1: Evidence-shaped overview and project workflow

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_projects.py`
- Modify: `cargento/skills/cargento/tests/test_next_project.py`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-projects.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-project.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/styles.css`

**Interfaces:**
- Consumes: `nextProjectAsks(group)`, `group.sessions[*].spacedock`, and existing route tokens.
- Produces: `nextProjectHasSpacedock(sessions) -> boolean`,
  `nextProjectRequestLabel(group, ask) -> "Captain" | "Needs you"`, and optional HTML regions.

- [ ] **Step 1: Replace the rejected overview assertions with failing evidence tests**

  Extend the fixture with a plain-project exact ask and assert these literal behaviors:

  ```python
  self.assertIn("NEEDS YOU — Plain approval", plain_html)
  self.assertNotIn("CAPTAIN — Plain approval", plain_html)
  self.assertIn("CAPTAIN — Approve the release", spacedock_html)
  self.assertNotIn("CAPTAIN — No request observed", no_ask_html)
  self.assertNotIn("Current payload only", no_ask_html)
  self.assertNotIn("RESPONSE", self.project_row(no_ask_html, "gamma/tool"))
  self.assertIn("next-project-command--situation-only", self.project_row(no_ask_html, "gamma/tool"))
  ```

- [ ] **Step 2: Replace the plain-workflow empty assertion with a failing omission test**

  Keep the FO and ensign fixtures, then assert:

  ```python
  self.assertNotIn('data-next-project-section="plan"', out["plain/repo"])
  self.assertNotIn("Workflow source unavailable", out["plain/repo"])
  self.assertIn('data-next-project-section="plan"', out["empty/fo"])
  self.assertIn("nothing is fresh enough to show", out["empty/fo"])
  self.assertIn("plan lives with its first officer", out["worker/repo"])
  ```

- [ ] **Step 3: Run both modules and preserve the red result**

  Run:

  ```bash
  python3 -m unittest \
    cargento.skills.cargento.tests.test_next_projects \
    cargento.skills.cargento.tests.test_next_project
  ```

  Expected: failures name the rejected absence lede, response cell, and plain workflow panel.

- [ ] **Step 4: Implement request authority and optional row response**

  Add a structural evidence helper and render labels from the ask's owning sessions:

  ```javascript
  function nextProjectHasSpacedock(sessions){
    return sessions.some(session => session && session.spacedock &&
      typeof session.spacedock === "object" && !Array.isArray(session.spacedock));
  }

  function nextProjectRequestLabel(group){
    return nextProjectHasSpacedock(group.sessions) ? "Captain" : "Needs you";
  }
  ```

  When no exact question exists, omit the response `<div>` and add
  `next-project-command--situation-only`; when a question exists, use the helper in both the page
  lede and project response. Do not emit any bounded-absence replacement.

- [ ] **Step 5: Omit unsupported workflow regions**

  Make `nextProjectPlanBlock(context)` return an empty string when there is no Spacedock evidence.
  In `nextProjectView`, construct the complete plan wrapper only when that return value is non-empty:

  ```javascript
  const plan = nextProjectPlanBlock(context);
  const planSection = plan ? `<div data-next-project-section="plan">${plan}</div>` : "";
  ```

  Keep concrete plans and the existing FO/ensign role-specific copy. Remove the generic fallback.

- [ ] **Step 6: Add the reflow rule and run both modules green**

  ```css
  .next-project-command--situation-only{grid-template-columns:1fr}
  ```

  Re-run the Step 3 command. Expected: both modules pass.

### Task 2: Current-activity-first session disclosure

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_session.py`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-session.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/styles.css`

**Interfaces:**
- Consumes: `nextSessionInstruction`, `nextSessionNextFact`, `nextSessionAsks`, and
  `session.spacedock`.
- Produces: `nextSessionCommandSurface(session, asks) -> escaped HTML` containing one invariant
  activity lede, optional fact cards, and optional collapsed coverage.

- [ ] **Step 1: Rewrite plain-session behavior to fail on the fixed four-cell frame**

  Assert the current-activity section precedes every optional fact and unsupported facts are absent:

  ```python
  self.assertIn('data-next-session-command="activity"', html)
  self.assertIn("CURRENT ACTIVITY", html)
  self.assertIn("working · running tests", html)
  self.assertNotIn("ASSIGNMENT</h2>", html)
  self.assertNotIn("NEXT</h2>", html)
  self.assertNotIn("CAPTAIN</h2>", html)
  self.assertNotIn("NEEDS YOU</h2>", html)
  self.assertIn("SOURCE COVERAGE", html)
  self.assertIn("Claude transcript did not publish an assignment or next action", html)
  self.assertNotIn("<details class=\"next-session-source-coverage\" open", html)
  ```

- [ ] **Step 2: Add failing progressive-disclosure variants**

  Prove a full `asked` instruction renders `ASSIGNMENT`, a task renders `NEXT`, a plain exact ask
  renders one `NEEDS YOU` fact, and adding a Spacedock record changes only that fact's label to
  `CAPTAIN`. Assert the exact ask text occurs once inside the command surface and that source copy
  contains no internal terms such as `instruction`, `field`, or `schema`.

- [ ] **Step 3: Run the session module and preserve the red result**

  Run:

  ```bash
  python3 -m unittest cargento.skills.cargento.tests.test_next_session
  ```

  Expected: failures identify the fixed frame, empty primary cards, duplicated ask, and absent
  progressive labels.

- [ ] **Step 4: Implement the semantic command surface**

  Replace `nextSessionCommandFrame` with `nextSessionCommandSurface`. Derive:

  ```javascript
  const assignment = nextSessionInstruction(session, "asked");
  const context = nextSessionInstruction(session, "agent") ||
    nextSessionInstruction(session, "earlier");
  const next = asks.length ? null : nextSessionNextFact(session, []);
  const authority = session.spacedock && typeof session.spacedock === "object" &&
    !Array.isArray(session.spacedock);
  ```

  Render activity first. Append fact sections only for non-null assignment, next, or ask. Use
  `CAPTAIN` only when `authority` is true, otherwise `NEEDS YOU`. Escape every payload string.

- [ ] **Step 5: Implement secondary source coverage**

  Collect missing labels (`assignment`, `next action`) and render nothing when none are missing.
  Otherwise emit a closed native details element:

  ```html
  <details class="next-session-source-coverage">
    <summary>SOURCE COVERAGE</summary>
    <p>Claude transcript did not publish an assignment or next action.</p>
  </details>
  ```

  Keep the source name from `nextSessionSourceOwner`; do not mention payload fields or schemas.

- [ ] **Step 6: Replace frame styles and run the session module green**

  Style `.next-session-activity` as the primary bordered lede, `.next-session-command-facts` as an
  auto-fitting compact grid, and `.next-session-source-coverage` as subdued secondary evidence.
  Remove unused `.next-session-command-frame` rules and their narrow-screen overrides. Re-run the
  Step 3 command. Expected: pass.

### Task 3: Honest and recoverable live-refresh failure state

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_chrome.py`
- Modify: `cargento/skills/cargento/tests/test_next_live.py`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-chrome.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-render.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-live.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/styles.css`

**Interfaces:**
- Consumes: the existing `refreshNext()` fetch path and live/legacy polling constants.
- Produces: `nextRefreshInFlight: boolean`, `nextLastRefreshSuccessAt: number | null`,
  `nextRefreshRetryMs() -> number`, and `nextRefreshNotice() -> escaped HTML`.

- [ ] **Step 1: Rewrite the repeated-failure test with exact explanatory behavior**

  Stub `Date.now()` so the successful receipt is 40 seconds old at the second failure, then assert:

  ```python
  self.assertNotIn('data-next-state="stalled"', out["once"])
  self.assertIn("Live refresh failed twice", out["twice"])
  self.assertIn("Displayed data may be stale", out["twice"])
  self.assertIn("Last updated 40s ago", out["twice"])
  self.assertIn("Retrying automatically every 20s", out["twice"])
  self.assertIn("Retry now", out["twice"])
  self.assertNotIn("stream stopped", out["twice"].lower())
  self.assertIn('aria-label="live">●</span> 1 running', out["twice"])
  ```

- [ ] **Step 2: Add failing manual-retry and recovery tests**

  Click `data-next-action="retry-refresh"` twice before resolving a deferred fetch and assert only
  one new fetch occurred and the button is disabled while pending. Resolve a successful response
  and assert the notice disappears and the new payload renders. Keep the existing closed-stream
  fallback test and update its message assertions to the same explanatory copy.

- [ ] **Step 3: Run both modules and preserve the red result**

  Run:

  ```bash
  python3 -m unittest \
    cargento.skills.cargento.tests.test_next_chrome \
    cargento.skills.cargento.tests.test_next_live
  ```

  Expected: failures name the context-free notice, missing receipt age/cadence, and unsafe retry.

- [ ] **Step 4: Track success age and serialize refresh attempts**

  Initialize:

  ```javascript
  let nextRefreshInFlight = false;
  let nextLastRefreshSuccessAt = null;
  ```

  At the start of `refreshNext`, return early if already in flight; set the flag before fetching and
  clear it in `finally`. On success set `nextLastRefreshSuccessAt = Date.now()`, replace `nextData`,
  and clear failures. On failure increment the counter and retain `nextData` unchanged.

- [ ] **Step 5: Render exact recovery state and wire the button**

  Derive cadence from `NEXT_LIVE_SUPPORTED ? NEXT_FALLBACK_POLL_MS : NEXT_LEGACY_POLL_MS`. Render
  the age only when a success timestamp exists, disable the button while in flight, and handle
  `retry-refresh` in the existing delegated click handler with `void refreshNext()`.

- [ ] **Step 6: Run both modules green**

  Re-run the Step 3 command. Expected: pass, including first-failure quietness, retained counts,
  serialized manual retry, and successful recovery.

### Task 4: Focused contract regeneration and candidate commit

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_page.py`
- Verify: every file changed in Tasks 1–3

**Interfaces:**
- Consumes: final next-page asset bytes and `cargento_runtime.web.page.next_page()`.
- Produces: exact per-part and assembled-page byte sizes and SHA-256 digests.

- [ ] **Step 1: Run all changed behavior modules serially**

  ```bash
  python3 -m unittest \
    cargento.skills.cargento.tests.test_next_projects \
    cargento.skills.cargento.tests.test_next_project \
    cargento.skills.cargento.tests.test_next_session \
    cargento.skills.cargento.tests.test_next_chrome \
    cargento.skills.cargento.tests.test_next_live
  ```

- [ ] **Step 2: Regenerate pins from the final tree**

  Use the existing pin-oracle pattern from `test_next_page.py` to print each changed part's byte
  count and SHA-256, then print `len(next_page())` and its SHA-256. Copy only those measured values
  into the literal expectations.

- [ ] **Step 3: Verify the byte contract and frontend validators**

  ```bash
  python3 -m unittest cargento.skills.cargento.tests.test_next_page
  python3 scripts/lint_embedded.py
  python3 scripts/validate_plugins.py
  git diff --check
  ```

- [ ] **Step 4: Review, commit, and push the candidate**

  Inspect the full diff for unsupported absence claims and unescaped payload strings. Commit with
  DCO sign-off using the repository convention, then push only `feat/future-ui`.

### Task 5: Same-identity live proof and workflow report

**Files:**
- Add: correction-cycle captures under the split-root Spacedock entity directory
- Modify: split-root `future-ui-command-surface/index.md`

**Interfaces:**
- Consumes: the exact pushed candidate SHA and the existing Codex, Claude Code, and AGY session IDs.
- Produces: before/after visual evidence and the complete correction-round stage report.

- [ ] **Step 1: Start only the committed candidate and record its PID**

  Launch the future UI through the repository's existing server entry point on a free loopback port.
  Record the exact SHA, URL, PID, and payload session IDs before opening Chrome.

- [ ] **Step 2: Capture overview, project, and all three same identities**

  Save live Chrome screenshots for the overview and project plus the same Codex, Claude Code, and
  AGY session IDs used in the prior round. Record exact routes and link each capture to its rejected
  predecessor.

- [ ] **Step 3: Stop only the recorded dashboard PID**

  Verify that process exited and do not kill unrelated harness or sibling-worktree daemons.

- [ ] **Step 4: Append and push the path-scoped stage report**

  Report each crucible finding, the accepted semantic ruling, red/green evidence, byte pins,
  validators, candidate SHA, capture routes, checklist wording, and any residual risks. Commit only
  the entity path on `spacedock-state/future-ui-exploration`, push it, restore the product branch,
  and emit the exact completion signal.
