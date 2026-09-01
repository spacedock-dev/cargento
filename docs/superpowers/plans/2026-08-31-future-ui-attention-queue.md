# Future UI Attention Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the opt-in next UI's overview with a deterministic, exception-first Attention
route while keeping Projects and Sessions complete, adjacent maps of the same payload.

**Architecture:** Keep the stable dashboard byte-identical and extend only the independently
assembled `?next=true` bundle. A pure `next-attention.js` layer will turn one payload into
source-bound subjects, coverage, section order, and project summaries; route chrome and render code
will consume that model without reclassifying facts or borrowing authority across sessions.

**Tech Stack:** Python 3.11+, stdlib `unittest`, plain browser JavaScript in one concatenated script
scope, HTML/CSS, the repository's Node-backed `NextPageJsHarness`, and live Chrome verification.

**Design record:** `docs/design-next-ui.md`, NUI-15 and NUI-16

## Global Constraints

- Start from approved checkpoint `cc2f3237565b932d74199ba8faa237087998ef1b` on `feat/future-ui`;
  do not merge or target `main`.
- Read the approved spec before each task. A task implementer receives only that task, this global
  section, and the spec.
- Change only the opt-in `?next=true` UI. The stable page remains exactly 321,790 bytes with SHA-256
  `fe221aa43b27f17859e350cee10296745faa0a560217026d26fab6cafc346a50`.
- Use only existing `/api/data` fields; add no collector fields, backend capability metadata,
  endpoint, storage key, network destination, dependency, or preference.
- Never infer an all-clear, forecast, repository identity, termination cause, unread result,
  successful outcome, or captain authority from a display-label sibling.
- Use source-published tasks and reset instants only. Exclude top-level `eta_h`, `turn.eta_h`, token
  rate, and browser-retained history from checkpoint and health claims.
- Resolve authority only through the exact ask owner's `session_id`; an unresolved owner is always
  `NEEDS YOU`, never `CAPTAIN`.
- Treat `session.project` as a lossy display label. Duplicate labels create one collision signal and
  retain every exact Projects and Sessions route.
- Derive ages and order from `payload.generated` or `asks[].age_sec`; browser time is allowed only
  in the retained-view refresh notice.
- Keep missing primary facts absent. Never render empty `NEXT`, response, estimate, workflow,
  progress, or delegation fields.
- Show at most three ranked subjects per section initially. A truthful native expansion button
  reveals the ordered remainder without duplication or loss, and expansion plus control focus
  survive refresh.
- Escape every payload-derived string before HTML interpolation and encode route segments with
  `encodeURIComponent`.
- Preserve the existing two-failure refresh boundary, serialized `Retry now`, last successful view,
  exact session command frame, ask-answer endpoint, and collapsed plain-language source coverage.
- Serialize work on this one web conflict surface. Do not run another full suite in a sibling
  worktree; check `git worktree list` before the final suite.
- Every implementation task follows red, observed failure, minimal green implementation, focused
  green check, and a DCO signed-off commit. Task 8 alone regenerates byte pins.

---

## File ownership map

| File | Responsibility |
|---|---|
| `cargento/skills/cargento/cargento_runtime/web/next/next-boot.js` | Route tokens, payload guards, exact ask ownership, stable keys, source task selection, and payload-clock helpers. |
| `cargento/skills/cargento/cargento_runtime/web/next/next-attention.js` | New pure subject builder, predicates, de-duplication, comparators, coverage, project summaries, bounded section disclosure, and escaped Attention markup. |
| `cargento/skills/cargento/cargento_runtime/web/next/next-chrome.js` | Native primary navigation, titles, breadcrumbs, observed brief counts, shortcuts, disclosure state, live announcements, and focus restoration. |
| `cargento/skills/cargento/cargento_runtime/web/next/next-render.js` | Top-level dispatch and atomic `{payload, attentionModel}` refresh. |
| `cargento/skills/cargento/cargento_runtime/web/next/next-projects.js` | Complete project map, supported aggregates, and shared-model consumption without authority re-derivation. |
| `cargento/skills/cargento/cargento_runtime/web/next/next-project.js` | Missing-project wording/link and accepted project drill-down preservation. |
| `cargento/skills/cargento/cargento_runtime/web/next/next-sessions.js` | Complete flat inventory and removal of elapsed-stop-to-`done` inference. |
| `cargento/skills/cargento/cargento_runtime/web/next/next-session.js` | Missing-session wording/link and exact-owner command-frame preservation. |
| `cargento/skills/cargento/cargento_runtime/web/next/styles.css` | Wide grid, 320-pixel stacked grammar, 44-pixel targets, focus, reduced motion, and no overflow. |
| `cargento/skills/cargento/cargento_runtime/web/page.py` | Load `next-attention.js` after boot and before chrome/render. |
| `cargento/skills/cargento/tests/test_next_attention.py` | New executed-JavaScript contract for pure model, rendering, coverage, order, and hostile text. |
| `cargento/skills/cargento/tests/test_next_chrome.py` | Routes, native nav, breadcrumbs, titles, shortcut guards, focus, and announcements. |
| `cargento/skills/cargento/tests/test_next_projects.py` | Project aggregates, order, collisions, and authority consistency. |
| `cargento/skills/cargento/tests/test_next_project.py` | Project detail preservation and missing route. |
| `cargento/skills/cargento/tests/test_next_sessions.py` | Inventory preservation and bounded stop wording. |
| `cargento/skills/cargento/tests/test_next_session.py` | Session frame, exact authority, and missing route. |
| `cargento/skills/cargento/tests/test_next_live.py` | Atomic refresh, retained order, safe retry, recovery, focus, and live announcement. |
| `cargento/skills/cargento/tests/test_next_page.py` | Part inventory and mechanically regenerated byte pins. |

No Python collector, aggregate, quota, Spacedock, session, or HTTP runtime module changes.

## Shared JavaScript interfaces

Task 2 creates these exact globals. Later tasks consume them without renaming or duplicating their
predicates. The type shapes are:

```javascript
/** @typedef {"needs"|"risk"|"close"|"next"} NextAttentionSection */
/** @typedef {"session"|"ask"|"quota"|"collision"} NextAttentionSubjectKind */
/** @typedef {{kind:string, section:NextAttentionSection, detail:Object,
 * sourceIndex:number}} NextAttentionSignal */
/** @typedef {{key:string, kind:NextAttentionSubjectKind, section:NextAttentionSection,
 * primaryKind:string, signals:Array<NextAttentionSignal>, session:Object|null,
 * sessions:Array<Object>, asks:Array<Object>, sourceIndex:number,
 * responsibility:(string|undefined), checkpoint:(Object|undefined)}} NextAttentionSubject */
/** @typedef {{discovered:number, reporting:number, unknown:number, failed:number,
 * rows:Array<Object>}} NextGateCoverage */
/** @typedef {{gates:NextGateCoverage, exactRequestsReported:boolean,
 * rates:{reported:number, notReported:number, failed:number, rows:Array<Object>},
 * observedStops:number, ends:string}} NextAttentionCoverage */
/** @typedef {{needs:Array<NextAttentionSubject>, risk:Array<NextAttentionSubject>,
 * close:Array<NextAttentionSubject>, next:Array<NextAttentionSubject>,
 * healthy:{sessions:Array<Object>, moving:number, quiet:number, unknown:number},
 * coverage:NextAttentionCoverage,
 * counts:{needs:number, risk:number, close:number, next:number,
 * moving:number, quiet:number, unknown:number},
 * harnessOrder:Array<string>, representedSessionKeys:Array<string>,
 * generated:(number|null), windowHours:(number|null)}} NextAttentionModel */
/** @typedef {{exactRequests:number, risk:number, close:number,
 * working:number, quiet:number}} NextAttentionProjectSummary */
```

The exact signatures and return contracts are:

| Signature | Return |
|---|---|
| `nextPayloadSessions(payload: object)` | `Array<object>` or an empty array for malformed/missing sessions. |
| `nextPayloadAsks(payload: object)` | `Array<object>` or an empty array for malformed/missing asks. |
| `nextSessionKey(session: object)` | Stable string from exact harness and sid. |
| `nextExactAskOwner(payload: object, ask: object)` | Exact sid-matched session object or `null`. |
| `nextAskResponsibility(payload: object, ask: object)` | Exact string `CAPTAIN` or `NEEDS YOU`. |
| `nextPublishedTask(session: object)` | First in-progress task, otherwise first pending task, otherwise `null`. |
| `nextPayloadAgeSeconds(payload: object, stamp: unknown)` | Non-negative number from payload clock or `null`. |
| `nextAttentionModel(payload: object)` | Fresh `NextAttentionModel`. |
| `nextAttentionCoverage(payload: object)` | `NextAttentionCoverage`. |
| `nextAttentionRateCoverage(discoveredHarnesses: Array<object>)` | Exact reported/notReported/failed counts and rows. |
| `nextAttentionCompareSubjects(left, right, model)` | Negative, zero, or positive comparator result. |
| `nextAttentionProjectSummary(model, sessions)` | `NextAttentionProjectSummary`. |
| `nextAttentionView(model, expandedSections)` | Escaped Attention HTML string with at most three initially visible subjects per ranked section. |
| `nextAttentionSectionForKey(model, key)` | Section token or `null`. |

`nextAttentionModel(payload)` is pure: it reads no DOM, browser clock, local storage, network state,
or prior model. Rendering is the only layer that calls `esc()`.

Subject keys use these exact forms:

```javascript
const sessionKey = `session:${JSON.stringify([String(session.harness || ""), String(session.sid || "")])}`;
const askKey = ask.id == null ? `ask-index:${sourceIndex}` : `ask:${String(ask.id)}`;
const quotaKey = `quota:${JSON.stringify([String(entry.harness || ""), scopeKey])}`;
const collisionKey = `collision:${String(projectLabel)}`;
```

Signal kinds are fixed as `ask`, `input`, `attribution`, `loop`, `quota`, `long-turn`, `collision`,
`stop-dirty`, `stop-clean`, `stop-unknown`, and `task`. No task introduces a severity score.

## Acceptance-scenario coverage map

| Scenario | Owning task and test |
|---|---|
| 1. Claude exact ask with Spacedock | Task 2 — `test_exact_spacedock_ask_owns_needs_and_published_task_once` |
| 2. Codex ask beside same-label Spacedock sibling | Tasks 2/6 — `test_same_label_sibling_cannot_lend_captain_authority` |
| 3. AGY gate-blind silence | Task 5 — `test_gate_blind_agy_is_unknown_and_only_bounded_in_healthy_remainder` |
| 4. Bare gate | Task 2 — `test_bare_gate_has_bounded_detail_without_question_or_authority` |
| 5. Repeated Claude tool failures | Task 3 — `test_loop_signal_appears_and_disappears_with_exact_loop_object` |
| 6. Long Codex turn without source task | Task 3 — `test_long_turn_excludes_derived_eta_and_checkpoint` |
| 7. Quota pressure with reset | Task 3 — `test_quota_threshold_reset_and_no_forecast` |
| 8. Display-label collision | Tasks 3/6 — `test_collision_represents_members_without_claiming_repository_identity` |
| 9. Stopped dirty Codex session | Task 4 — `test_dirty_stop_reports_changed_entries_without_outcome_words` |
| 10. Stop without git evidence | Task 4 — `test_stop_distinguishes_unknown_and_clean_git_readings` |
| 11. No termination evidence | Tasks 4/5 — `test_scan_only_idle_without_stop_has_no_end_signal` |
| 12. Published Claude task | Task 4 — `test_published_task_prefers_first_in_progress_then_first_pending` |
| 13. Derived ETA excluded | Task 4 — `test_eta_fields_alone_never_create_coming_next` |
| 14. Collector failure | Task 5 — `test_failed_collector_changes_coverage_not_session_counts` |
| 15. Ask capability disabled | Task 5 — `test_missing_ask_capability_never_manufactures_zero` |
| 16. Conflicting ask attribution | Task 2 — `test_conflicting_ask_stays_needs_with_secondary_attribution` |
| 17. No published exceptions | Tasks 4/5 — `test_no_exception_sections_are_omitted_and_healthy_is_qualified` |
| 18. Empty payload | Task 5 — `test_empty_payload_is_window_bounded_and_keeps_coverage` |
| 19. Stale refresh | Task 7 — `test_stale_refresh_retains_keys_order_focus_and_recovers` |
| 20. Responsive and accessible routes | Tasks 1/5/7/9 - route, bounded disclosure, DOM-order, focus, target-size, and viewport checks |
| 21. Cross-harness stable ordering | Task 3 — `test_equal_signal_order_uses_harness_project_sid_not_input_order` |
| 22. Escaping | Task 5 — `test_every_attention_text_and_route_field_is_escaped` |

### Task 1: Migrate top-level routes and native navigation

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-boot.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-chrome.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-render.js`
- Test: `cargento/skills/cargento/tests/test_next_chrome.py`

**Interfaces:**
- Consumes: existing route codecs, `navigateNext`, `nextProjectsView`, and `nextSessionsView`.
- Produces: route `view` values `attention|projects|sessions|project|session`,
  `nextPrimaryNavigation()`, native breadcrumbs, and guarded `a|p|s` shortcuts.

- [ ] **Step 1: Write failing route and navigation tests**

Add `test_attention_is_default_and_old_overview_normalizes_to_it`: map `""`, `#n=overview`, and
`#n=unknown` through both route functions and require `view == "attention"` and
`#n=attention`. Add `test_primary_routes_are_native_links_with_current_page`: navigate through the
three top-level views and require titles `Cargento — Attention|Projects|Sessions`, three native
links in Attention/Projects/Sessions order, and exactly one `aria-current="page"`. Update breadcrumb
tests to require native links to Attention and Projects. Update shortcut tests to require matching
top-level routes while preserving input/select/textarea and modifier guards.
Retain the existing browser-history test, native Enter activation, and Escape progression from
session to project to Attention without focus trapping.

```python
self.assertEqual("attention", next_route["view"])
self.assertEqual("#n=attention", repaired_fragment)
self.assertIn('<nav aria-label="Primary"', html)
self.assertIn('href="#n=attention"', html)
self.assertIn('href="#n=projects"', html)
self.assertIn('href="#n=sessions"', html)
self.assertEqual(1, html.count('aria-current="page"'))
```

- [ ] **Step 2: Run focused tests and observe the old overview contract fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_next_chrome`

Expected: FAIL because current code repairs to `#n=overview`, uses a Projects/Sessions tab widget,
and has no Attention route or native primary nav.

- [ ] **Step 3: Implement minimal route and nav behavior**

Add `NEXT_TOP_LEVEL_VIEWS = new Set(["attention", "projects", "sessions"])`; parse those exact
tokens and normalize every invalid/bare/overview token to Attention. Make
`nextFragmentForRoute()` return explicit top-level fragments. Delete `nextOverviewTab`,
`nextOverviewShell()`, tab click handling, and `nextSelectProjects/Sessions()`. Render a native
primary nav on every route and native canonical breadcrumbs on detail routes. Dispatch top-level
views directly in `next-render.js`. Until Task 2 adds the real renderer, use and then remove:

```javascript
function nextAttentionView(){
  return '<section class="next-attention"><h1>Attention</h1></section>';
}
```

- [ ] **Step 4: Run the complete chrome module**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_next_chrome`

Expected: PASS for route repair, history, distinct h1/title, native nav/breadcrumbs, and shortcut
guards. Do not run byte-oracle tests before Task 8.

- [ ] **Step 5: Commit the route checkpoint**

```bash
git add cargento/skills/cargento/cargento_runtime/web/next/next-boot.js \
  cargento/skills/cargento/cargento_runtime/web/next/next-chrome.js \
  cargento/skills/cargento/cargento_runtime/web/next/next-render.js \
  cargento/skills/cargento/tests/test_next_chrome.py
git commit -s -m "feat(ui): make attention the default next route"
```

### Task 2: Build exact-owner Needs-you subjects

**Files:**
- Create: `cargento/skills/cargento/cargento_runtime/web/next/next-attention.js`
- Create: `cargento/skills/cargento/tests/test_next_attention.py`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-boot.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/page.py`
- Modify: `cargento/skills/cargento/tests/test_next_page.py`

**Interfaces:**
- Consumes: `esc`, numeric/duration helpers, and explicit payload objects.
- Produces: every shared helper named above; this task fully implements asks, bare gates, exact
  authority, stable subject keys, lower-signal attachment, and initial section arrays.

- [ ] **Step 1: Register the new part and write failing exact-owner tests**

Insert `next-attention.js` after `next-boot.js` in `NEXT_PARTS`; update `_write_bundle()` and the
part-name tuple without changing pins. Create `NextAttentionBehaviorTest` with a `model(payload)`
helper that JSON-serializes the payload, executes `nextAttentionModel(nextData)`, and returns the
object. Add exact fixtures for scenarios 1, 2, 4, and 16:

```python
self.assertEqual("CAPTAIN", spacedock_model["needs"][0]["responsibility"])
self.assertEqual("Run checks", spacedock_model["needs"][0]["checkpoint"]["subject"])
self.assertEqual([], spacedock_model["next"])
self.assertEqual("NEEDS YOU", sibling_model["needs"][0]["responsibility"])
self.assertEqual("input", bare_gate_model["needs"][0]["primaryKind"])
self.assertNotIn("responsibility", bare_gate_model["needs"][0])
self.assertEqual(
    ["ask", "attribution"], [signal["kind"] for signal in conflict_model["needs"][0]["signals"]]
)
self.assertEqual([], conflict_model["risk"])
```

Fixtures use exact session IDs, non-empty questions, a pending source task, same-label plain and
Spacedock siblings, a bare `needs_input` row with detail/blocked stamp, and a mismatched ask project.
Add a fifth test with two asks on one exact session and one unmatched ask: require both exact
questions as separate lines on one subject, oldest valid age as its rank, and the unmatched ask as
its own stable `ask:<id>` subject.

- [ ] **Step 2: Run the new module and observe the missing classifier**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_next_attention`

Expected: FAIL with `ReferenceError: nextAttentionModel is not defined`.

- [ ] **Step 3: Implement exact-owner foundation**

Implement every boot helper in the interface section. An owner qualifies for `CAPTAIN` only when
its exact sid matches and its `spacedock` is a non-null non-array object. Build one session subject
per harness+sid, attach asks by exact sid in source order, keep unmatched asks independent, and rank
asks by descending valid `age_sec` then source position. Add bare input only with no attached ask.
Attach attribution when matched ask.project disagrees with owner.project. Select first in-progress
or first pending task once as `checkpoint`; do not duplicate it in `model.next`. Delete Task 1's
temporary renderer and render the new Needs section in `next-attention.js`. Until Task 7 makes
publication atomic, the Attention and Projects dispatch branches pass
`nextAttentionModel(nextData || {})` directly to their renderers.

Within Needs, ask subjects precede bare input. Bare input sorts by oldest valid blocked_since;
unstamped rows follow stamped rows, then use the stable identity chain.

```javascript
function nextExactAskOwner(payload, ask){
  const sid = String(ask && ask.session_id || "");
  if(!sid) return null;
  return nextPayloadSessions(payload).find(session => String(session.sid || "") === sid) || null;
}

function nextAskResponsibility(payload, ask){
  const owner = nextExactAskOwner(payload, ask);
  const spacedock = owner && owner.spacedock;
  return spacedock && typeof spacedock === "object" && !Array.isArray(spacedock)
    ? "CAPTAIN"
    : "NEEDS YOU";
}
```

- [ ] **Step 4: Run focused Attention and authority preservation checks**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_attention \
  cargento.skills.cargento.tests.test_next_projects.NextProjectsBehaviorTest.test_plain_exact_ask_keeps_attention_without_claiming_captain_authority \
  cargento.skills.cargento.tests.test_next_session
```

Expected: PASS. The next-page byte oracle remains intentionally red until Task 8.

- [ ] **Step 5: Commit the Needs-you checkpoint**

```bash
git add cargento/skills/cargento/cargento_runtime/web/next/next-attention.js \
  cargento/skills/cargento/cargento_runtime/web/next/next-boot.js \
  cargento/skills/cargento/cargento_runtime/web/page.py \
  cargento/skills/cargento/tests/test_next_attention.py \
  cargento/skills/cargento/tests/test_next_page.py
git commit -s -m "feat(ui): classify exact attention requests"
```

### Task 3: Add At-risk predicates and deterministic ordering

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-attention.js`
- Test: `cargento/skills/cargento/tests/test_next_attention.py`

**Interfaces:**
- Consumes: Task 2 subjects, `nextSessionKey`, payload age, and harness source order.
- Produces: attribution/loop/quota/long-turn/collision signals and the complete comparator chain.

- [ ] **Step 1: Write failing risk and stable-order tests**

Add exact fixtures and assertions:

```python
self.assertEqual("loop", loop_model["risk"][0]["primaryKind"])
self.assertEqual({"errors": 4, "tool": "Bash"}, loop_model["risk"][0]["signals"][0]["detail"])
self.assertEqual([], model_without_loop["risk"])
self.assertEqual("long-turn", long_model["risk"][0]["primaryKind"])
self.assertNotIn("checkpoint", long_model["risk"][0])
self.assertEqual("quota", quota_model["risk"][0]["primaryKind"])
self.assertEqual(92, quota_model["risk"][0]["signals"][0]["detail"]["pct"])
self.assertEqual("critical", quota_model["risk"][0]["signals"][0]["detail"]["tone"])
self.assertEqual([], quota_69_model["risk"])
self.assertEqual(first_keys, reversed_input_keys)
```

The stable-order fixture supplies equal long-turn signals for Claude, Codex, and AGY, publishes
harness order Claude/Codex/AGY, reverses input sessions, and requires identical output keys. The
collision fixture requires one subject representing two `beta/app` member keys, neither member in
Healthy, and no repository/directory/branch/worktree claim in rendered HTML.
Add malformed loop, turn, quota, stop, and ask variants; require each invalid signal to disappear
without changing a different valid subject's section or order.

- [ ] **Step 2: Run risk tests and observe empty risk output**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_next_attention`

Expected: FAIL because Task 2 emits none of the risk kinds.

- [ ] **Step 3: Implement exact risk predicates and ordering**

Require positive integer `loop.errors`; require working state and `turn.long === true`; flatten only
`fiveH`, `week`, `month`, and `models[]` on usage parents with `state === "ok"`; require integer
`pct >= 70`; critical starts at 90; accept only finite positive resetAt. Use model scope keys
`model:<label>:<source-index>`. Add collisions for two or more non-empty identical labels.

Apply fixed kind order attribution, loop, quota, long-turn, collision; then kind magnitude/age,
harness-array order, raw display label, full sid, source position, and stable source ID. Collision
subjects represent member session keys and suppress lower-section/Healthy duplication. Never parse
formatted elapsed/reset text or assign a numeric severity.

Attribution uses source order; loop uses descending errors; quota uses descending pct then earliest
valid resetAt; long-turn uses stable identity; collision uses descending member count. A valid reset
stays a checkpoint line on its quota risk subject and never creates a second Coming-next subject.

```javascript
const NEXT_RISK_KIND_ORDER = new Map([
  ["attribution", 0], ["loop", 1], ["quota", 2], ["long-turn", 3], ["collision", 4],
]);

function nextAttentionQuotaSignal(entry, scope, row, sourceIndex){
  if(!entry || entry.state !== "ok" || !row || !Number.isInteger(row.pct) || row.pct < 70){
    return null;
  }
  const resetAt = typeof row.resetAt === "number" && Number.isFinite(row.resetAt) && row.resetAt > 0
    ? row.resetAt
    : null;
  return {kind: "quota", section: "risk", sourceIndex,
    detail: {harness: String(entry.harness || ""), scope, pct: row.pct,
      resetAt, tone: row.pct >= 90 ? "critical" : "warning"}};
}
```

- [ ] **Step 4: Run the complete Attention module**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_next_attention`

Expected: PASS for exact risk predicates, thresholds, collisions, forbidden copy, and stable order.

- [ ] **Step 5: Commit the risk checkpoint**

```bash
git add cargento/skills/cargento/cargento_runtime/web/next/next-attention.js \
  cargento/skills/cargento/tests/test_next_attention.py
git commit -s -m "feat(ui): rank source-bound attention risks"
```

### Task 4: Add stop, checkpoint, and compressed-remainder semantics

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-attention.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-sessions.js`
- Test: `cargento/skills/cargento/tests/test_next_attention.py`
- Test: `cargento/skills/cargento/tests/test_next_sessions.py`

**Interfaces:**
- Consumes: fixed higher-section ownership from Tasks 2–3.
- Produces: stop-dirty/clean/unknown and task signals, qualified Healthy remainder, and bounded
  Sessions activity without elapsed-stop outcome inference.

- [ ] **Step 1: Write failing stop/task/remainder tests**

Add exact fixtures for a valid idle stop with dirty true/changed 3, dirty null, dirty false, and a
scan-only idle row without finished_at. Require:

```python
self.assertEqual("stop-dirty", dirty_model["close"][0]["primaryKind"])
self.assertEqual(3, dirty_model["close"][0]["signals"][0]["detail"]["changedEntries"])
self.assertEqual("stop-unknown", unknown_model["close"][0]["primaryKind"])
self.assertEqual("stop-clean", clean_model["close"][0]["primaryKind"])
self.assertEqual([], scan_only_model["close"])
for forbidden in ("files", "failed", "unread", "unfinished", "successful", "died"):
    self.assertNotIn(forbidden, dirty_html.lower())
```

Add first-in-progress/otherwise-first-pending task fixtures preserving source order; a payload with
only top-level eta_h and turn.eta_h; all-empty exception sections; and exact moving/quiet/unknown
Healthy counts. In `test_next_sessions.py`, replace the old elapsed-stop `done` expectation: an idle
row with finished_at but no state_detail has an empty ACTIVITY cell and no done/finished/unread/died
word.

Add ask-plus-loop, risk-plus-stop, risk-plus-task, close-plus-task, and collision-member task
fixtures. Require one winning subject, all lower-ranked facts rendered once, no Close or Coming-next
duplicate, and exact display label, harness, and full session ID on collision-member facts.

- [ ] **Step 2: Run focused tests and observe missing sections plus old `done` copy**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_attention \
  cargento.skills.cargento.tests.test_next_sessions
```

Expected: FAIL because Task 3 has no close/task/remainder implementation and Sessions still turns
an elapsed stop stamp into `done`.

- [ ] **Step 3: Implement bounded stops, tasks, and Healthy**

Require finite positive finished_at, idle state, and exact dirty tri-state. Sort dirty, unknown,
clean; then oldest stop and stable identity. Boolean dirty or integer changed without valid stop is
an attribution risk. A stop coexisting with working or active state is also attribution risk.

Attach every valid lower-ranked stop and selected task to the existing winning Needs, Risk, Close,
or collision subject. Collision-member attachments carry the exact member session for attribution.
Only sessions absent from those sections become task subjects. Use `nextPublishedTask()` and
preserve source order. Healthy contains every remaining session exactly once and counts only
working, idle, and unknown state. Delete `NEXT_SESSION_FINISHED_UNREAD_SEC`; make
`nextSessionActivity()` return only escaped state_detail.

Coming-next subjects sort in-progress before pending, then working before idle, then stable identity.

```javascript
function nextAttentionStopSignal(session, sourceIndex){
  const finished = typeof session.finished_at === "number" &&
    Number.isFinite(session.finished_at) && session.finished_at > 0;
  if(!finished || session.state !== "idle") return null;
  let kind = "stop-unknown";
  if(session.dirty === true) kind = "stop-dirty";
  if(session.dirty === false) kind = "stop-clean";
  return {kind, section: "close", sourceIndex, detail: {
    finishedAt: session.finished_at,
    changedEntries: Number.isInteger(session.changed) && session.changed >= 0 ? session.changed : null,
  }};
}
```

- [ ] **Step 4: Run Attention and Sessions modules**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_attention \
  cargento.skills.cargento.tests.test_next_sessions
```

Expected: PASS with no unsupported outcome word and no derived ETA checkpoint.

- [ ] **Step 5: Commit the close/checkpoint checkpoint**

```bash
git add cargento/skills/cargento/cargento_runtime/web/next/next-attention.js \
  cargento/skills/cargento/cargento_runtime/web/next/next-sessions.js \
  cargento/skills/cargento/tests/test_next_attention.py \
  cargento/skills/cargento/tests/test_next_sessions.py
git commit -s -m "feat(ui): bound attention stops and checkpoints"
```

### Task 5: Render coverage, queue grammar, empty states, and hostile text

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-attention.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/styles.css`
- Test: `cargento/skills/cargento/tests/test_next_attention.py`

**Interfaces:**
- Consumes: complete Task 4 model.
- Produces: complete coverage and Attention renderers, semantic lists, five-part grammar,
  wide/narrow CSS, and escaped links.

- [ ] **Step 1: Write failing coverage, DOM, empty, and escaping tests**

Use a discovered AGY harness with no error and `reports_needs_input:false`; require discovered 1,
reporting 0, unknown 1, failed 0, and one qualified idle session in Healthy without `AGY is clear`.
Use a discovered Claude collector with a raw PermissionError; require failed 1, no synthetic Needs
item, and no raw error in HTML. Omit top-level `ask`; require no `No exact requests published`.
Use zero sessions/window_hours 24; require `No sessions in this 24h payload`, visible COVERAGE, and
no `no agents exist` claim.

Add a semantic DOM test requiring one Attention h1, one h2 per non-empty section with count,
`<ol><li><article>`, one heading route link per item, DOM labels in why/identity/NOW/NEXT/source
order, no NEXT line when absent, one closed native coverage details, and no Healthy identity panel.

Add four ranked subjects to one section. Require exactly three initially visible items, one hidden
ordered remainder item, a `Show 1 more` button with `aria-expanded="false"`, and an expanded render
with all four items in the same order plus `Show fewer (hide 1)`. Every subject key appears once in
both renders.

Add outcome/identity fixtures: one exact session with an `asked` instruction uses that assignment;
one distinct non-empty Spacedock workflow goal uses that goal; two distinct goals fall back to
identity; last_prompt/title remain context and never become an outcome.

Add hostile strings in question, options, title, project, state detail, task, workflow name/goal,
tool, harness label, sid, and model label. Require `&lt;img`, encoded route fragments, no literal
`<img`, `<script`, `onerror=`, raw collector error, filesystem/transcript path, and identical subject
order to a benign-string fixture.

```python
self.assertEqual({"discovered": 1, "reporting": 0, "unknown": 1, "failed": 0}, gate_counts)
self.assertIn("1 session with no published exception", agy_html)
self.assertNotIn("AGY is clear", agy_html)
self.assertNotIn("PermissionError", failure_html)
self.assertNotIn("No exact requests published", ask_disabled_html)
self.assertIn("No sessions in this 24h payload", empty_html)
self.assertNotIn("<img", hostile_html)
self.assertIn("&lt;img", hostile_html)
```

- [ ] **Step 2: Run Attention tests and observe missing coverage and grammar**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_next_attention`

Expected: FAIL because Task 4 has no capability denominator, coverage disclosure, complete grammar,
window-bounded empty copy, or hostile-render contract.

- [ ] **Step 3: Implement coverage, rendering, and responsive styles**

Count discovered harnesses only. Classify error non-null as failed; no error plus
reports_needs_input true as reporting; every other discovered harness as unknown. Token-rate
coverage uses the same error boundary and explicit reports_rate boolean. Exact request reporting is
true only when payload.ask is true. Count positive stop rows without a fleet denominator. Ends is
always `fleet coverage not reported`.

Render OBSERVED NOW, visible Gates, and visible Ends before closed plain-language coverage details.
The visible line is `Gates: X/Y reporting · N unknown`, adds `M failed` only when non-zero, and
always adds `Ends: fleet coverage not reported`; Y is every discovered harness exactly once.
When and only when payload.ask is true and asks is empty, the details may say
`No exact requests published`; a missing or false capability omits that sentence. Details list
harness display names, token-rate reporting, positive observed stop counts, and
`Termination cause not reported` without schema-key copy.
Render only non-empty queue sections. Each item is one list item/article with one heading route
link; its DOM order is why, identity/outcome, now, optional next, source/responsibility/age. Healthy
is count plus Projects link only. Pass payload text through `esc()` and routes through the existing
route encoder.

For each ranked section, render no more than the first three subjects initially. Keep the ordered
remainder in the same list with `hidden`, then add one native button with truthful remainder count,
`aria-expanded`, and `aria-controls`. Rendering receives an expanded-section set but does not
change the pure model.

Append Attention CSS: wide grid at 900px; stacked labels below 900px; 44px minimum block/inline
interactive size; overflow-wrap anywhere; visible focus; no CSS order; reduced-motion rule removing
live-dot and transition animation. Preserve no page-level overflow at 320px.

```javascript
function nextAttentionRateCoverage(discovered){
  const failed = discovered.filter(row => row.error != null);
  const reported = discovered.filter(row => row.error == null && row.reports_rate === true);
  const notReported = discovered.filter(row => row.error == null && row.reports_rate === false);
  return {reported: reported.length, notReported: notReported.length, failed: failed.length,
    rows: discovered};
}

function nextAttentionCoverage(payload){
  const rows = Array.isArray(payload && payload.harnesses) ? payload.harnesses : [];
  const discovered = rows.filter(row => row && row.discovered === true);
  const failed = discovered.filter(row => row.error != null);
  const reporting = discovered.filter(row => row.error == null && row.reports_needs_input === true);
  const unknown = discovered.filter(row => row.error == null && row.reports_needs_input !== true);
  return {
    gates: {discovered: discovered.length, reporting: reporting.length,
      unknown: unknown.length, failed: failed.length, rows: discovered},
    exactRequestsReported: payload && payload.ask === true,
    rates: nextAttentionRateCoverage(discovered),
    observedStops: nextPayloadSessions(payload).filter(session =>
      typeof session.finished_at === "number" && session.finished_at > 0).length,
    ends: "fleet coverage not reported",
  };
}
```

- [ ] **Step 4: Run Attention behavior and embedded lint**

Run:

```bash
python3 -m unittest cargento.skills.cargento.tests.test_next_attention
python3 scripts/lint_embedded.py
```

Expected: PASS with bounded coverage, semantic grammar, safe hostile text, and clean JS/CSS lint.

- [ ] **Step 5: Commit the render checkpoint**

```bash
git add cargento/skills/cargento/cargento_runtime/web/next/next-attention.js \
  cargento/skills/cargento/cargento_runtime/web/next/styles.css \
  cargento/skills/cargento/tests/test_next_attention.py
git commit -s -m "feat(ui): render the source-bound attention queue"
```

### Task 6: Reuse Attention truth in Projects and preserve drill-down scope

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-attention.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-projects.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-project.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-session.js`
- Test: `cargento/skills/cargento/tests/test_next_projects.py`
- Test: `cargento/skills/cargento/tests/test_next_project.py`
- Test: `cargento/skills/cargento/tests/test_next_session.py`

**Interfaces:**
- Consumes: `nextAttentionProjectSummary`, `nextExactAskOwner`, and `nextAskResponsibility`.
- Produces: complete supported Projects rows/order, no second authority predicate, bounded missing
  route states, and unchanged present-subject detail frames.

- [ ] **Step 1: Write failing map-reuse and missing-detail tests**

Replace overview-tab fixture calls with the Projects route. Build five display-label groups owning,
respectively, an exact ask, loop, dirty stop, working row, and quiet row. Require group order exact
request/risk/close/active/quiet; every session in one group; non-zero supported aggregates only; and
no empty response/progress/workflow field.

Keep mixed plain-plus-Spacedock fixtures and require NEEDS YOU on Attention/Projects/session. Add the
inverse exact Spacedock owner and require CAPTAIN on all three. Add missing detail assertions:

```python
self.assertIn("Not present in the current payload", missing_html)
self.assertIn('href="#n=projects"', missing_project_html)
self.assertIn('href="#n=sessions"', missing_session_html)
self.assertNotIn("deleted", missing_html.lower())
self.assertNotIn("completed", missing_html.lower())
```

Add zero-session Projects and Sessions fixtures: each keeps its own h1 and route-specific empty
sentence, remains reachable from primary navigation, and does not redirect to Attention.

- [ ] **Step 2: Run map/detail tests and observe old ownership/order fail**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_projects \
  cargento.skills.cargento.tests.test_next_project \
  cargento.skills.cargento.tests.test_next_session
```

Expected: FAIL because Projects owns separate predicates/priority, fixtures select the removed tab,
and missing detail branches lack canonical map links.

- [ ] **Step 3: Implement project-summary reuse and bounded missing states**

Implement the exact summary shape from session-owned subjects and collision membership:

```javascript
const all = model.needs.concat(model.risk, model.close, model.next);
const keys = new Set(sessions.map(nextSessionKey));
const sessionSubjects = all.filter(item => item.session && keys.has(nextSessionKey(item.session)));
const collisionSubjects = model.risk.filter(item => item.kind === "collision" &&
  item.sessions.some(session => keys.has(nextSessionKey(session))));
return {
  exactRequests: sessionSubjects.reduce((total, item) => total + item.asks.length, 0),
  risk: sessionSubjects.filter(item => item.section === "risk").length + collisionSubjects.length,
  close: sessionSubjects.filter(item => item.section === "close").length,
  working: sessions.filter(session => session.state === "working").length,
  quiet: sessions.filter(session => session.state === "idle").length,
};
```

Select subjects by exact session keys; unresolved project-named asks do not become project-owned.
Replace project priority/request responsibility with shared summary/helpers. Remove Projects-wide
request lede. Sort descending exact requests/risk/close/working/quiet, then first-seen group. Preserve
progress, concrete workflow chips, collision caveat, and routes. Change only missing branches in
project/session detail; preserve workflow omission, distinct strips, GOING ON, completed source
tasks, workstream, four-part command frame, source coverage, and answer controls.

- [ ] **Step 4: Run all map/detail modules**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_projects \
  cargento.skills.cargento.tests.test_next_project \
  cargento.skills.cargento.tests.test_next_sessions \
  cargento.skills.cargento.tests.test_next_session
```

Expected: PASS with complete inventories, consistent authority, and no detail regression.

- [ ] **Step 5: Commit the map checkpoint**

```bash
git add cargento/skills/cargento/cargento_runtime/web/next/next-attention.js \
  cargento/skills/cargento/cargento_runtime/web/next/next-projects.js \
  cargento/skills/cargento/cargento_runtime/web/next/next-project.js \
  cargento/skills/cargento/cargento_runtime/web/next/next-session.js \
  cargento/skills/cargento/tests/test_next_projects.py \
  cargento/skills/cargento/tests/test_next_project.py \
  cargento/skills/cargento/tests/test_next_session.py
git commit -s -m "refactor(ui): share attention truth with project maps"
```

### Task 7: Make refresh, focus, and announcements atomic

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-chrome.js`
- Modify: `cargento/skills/cargento/cargento_runtime/web/next/next-render.js`
- Test: `cargento/skills/cargento/tests/test_next_chrome.py`
- Test: `cargento/skills/cargento/tests/test_next_live.py`

**Interfaces:**
- Consumes: final model, stable keys, sections, and existing refresh state.
- Produces: global `nextAttention`; in-page `nextAttentionExpandedSections`;
  `nextCaptureFocus()` returning a subject or disclosure snapshot;
  `nextRestoreFocus(snapshot, model)`; `nextAttentionAnnouncement(previous,current)`.

- [ ] **Step 1: Write failing retained-focus and announcement tests**

Extend only these test fixtures with app querySelector/querySelectorAll targets that record focus.
First payload has two Needs subjects with the second focused. Require first failure no notice and
same keys/order; second failure stale notice and same keys/order/focus; recovery removing the
focused subject moves focus to needs h2; later removal of the section moves focus to Attention h1.
Require count change copy exactly `Attention updated: 2 need you, 1 at risk`, with no moved/because
explanation. Strengthen Retry-now: two rapid clicks create one fetch, retained HTML remains, and
recovery clears notice/failure count.

Add four Needs subjects, expand the section, focus its expansion button, and publish a successful
refresh with the same remainder. Require expanded markup, the truthful collapse label, and focus on
the replacement expansion button. If a later refresh removes the remainder, require the normal
section-heading fallback.

```python
self.assertEqual(first_keys, once_keys)
self.assertEqual(first_keys, twice_keys)
self.assertNotIn("Live refresh failed", once_html)
self.assertIn("Live refresh failed twice", twice_html)
self.assertEqual(["next-attention-needs", "next-attention-title"], focus_calls)
self.assertEqual("Attention updated: 2 need you, 1 at risk", announcement)
```

- [ ] **Step 2: Run refresh tests and observe model/focus gaps**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_live \
  cargento.skills.cargento.tests.test_next_chrome
```

Expected: FAIL because refresh swaps nextData alone, whole-app rendering loses subject focus, and
there is no count-change announcement.

- [ ] **Step 3: Implement atomic replacement and focus restoration**

Initialize `nextAttention = nextAttentionModel({})`. In refresh, JSON-parse and classify before
publishing either:

```javascript
const fresh = await response.json();
const freshAttention = nextAttentionModel(fresh);
nextObserveWorkstream(fresh);
nextData = fresh;
nextAttention = freshAttention;
nextRefreshFailures = 0;
nextLastRefreshSuccessAt = Date.now();
```

Capture focus before replacing app.innerHTML. If the key survives, focus its new heading link. If
it disappears and old section survives, focus section h2 with tabindex -1; otherwise Attention h1.
Find subjects by iterating `[data-next-subject-key]` and comparing dataset values, never by putting
untrusted keys into a selector. Do nothing when no queue subject held focus. Keep one persistent
polite status node; announce only successful count changes, never initial load/reorder/failure.

Keep expanded section keys in an in-page Set outside the pure model and pass it to the renderer.
Expansion clicks toggle that set and re-render without changing subject order. Capture a focused
expansion button by its bounded section token, then restore the corresponding replacement button
after refresh. If the button no longer exists, use the same bounded section/h1 fallback.

```javascript
function nextAttentionSectionForKey(model, key){
  for(const section of ["needs", "risk", "close", "next"]){
    if(model[section].some(item => item.key === key)) return section;
  }
  return null;
}
```

- [ ] **Step 4: Run live/chrome/Attention modules**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_live \
  cargento.skills.cargento.tests.test_next_chrome \
  cargento.skills.cargento.tests.test_next_attention
```

Expected: PASS with atomic publication, retained stale state, bounded live copy, and deterministic
focus.

- [ ] **Step 5: Commit the refresh checkpoint**

```bash
git add cargento/skills/cargento/cargento_runtime/web/next/next-chrome.js \
  cargento/skills/cargento/cargento_runtime/web/next/next-render.js \
  cargento/skills/cargento/tests/test_next_chrome.py \
  cargento/skills/cargento/tests/test_next_live.py
git commit -s -m "feat(ui): preserve attention state across refresh"
```

### Task 8: Regenerate byte pins once and run the serialized frontend suite

**Files:**
- Modify: `cargento/skills/cargento/tests/test_next_page.py`
- Verify: `cargento/skills/cargento/cargento_runtime/web/page.py`
- Verify: all `cargento/skills/cargento/cargento_runtime/web/next/` assets

**Interfaces:**
- Consumes: final assembled parts from Tasks 1–7.
- Produces: exact part and assembled pins; stable page oracle unchanged.

- [ ] **Step 1: Run the byte oracle and observe intentionally stale pins**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_page.NextPageAssetContractTest.test_load_next_page_preserves_its_byte_oracles
```

Expected: FAIL first on part inventory, part/style size or digest, or assembled next-page values.
This is the one planned stale-pin interval.

- [ ] **Step 2: Print and copy the mechanical source of every pin**

Run:

```bash
python3 - <<'PY'
import hashlib
from cargento.skills.cargento.cargento_runtime.web import page

for name in page.NEXT_PARTS:
    data = page.next_asset_path(name).read_bytes()
    print(name, len(data), hashlib.sha256(data).hexdigest())
styles = page.next_asset_path("styles.css").read_bytes()
print("styles.css", len(styles), hashlib.sha256(styles).hexdigest())
assembled = page.load_next_page()
print("assembled", len(assembled), hashlib.sha256(assembled).hexdigest())
stable = page.load_page()
print("stable", len(stable), hashlib.sha256(stable).hexdigest())
PY
```

Copy exact output into `expected_parts`, stylesheet assertions, and assembled assertions. Do not
alter stable-page values.

- [ ] **Step 3: Run the complete next-frontend batch once**

First run `git worktree list` and confirm no sibling suite is running. Then run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_next_page \
  cargento.skills.cargento.tests.test_next_attention \
  cargento.skills.cargento.tests.test_next_projects \
  cargento.skills.cargento.tests.test_next_project \
  cargento.skills.cargento.tests.test_next_activity \
  cargento.skills.cargento.tests.test_next_sessions \
  cargento.skills.cargento.tests.test_next_session \
  cargento.skills.cargento.tests.test_next_chrome \
  cargento.skills.cargento.tests.test_next_live \
  cargento.skills.cargento.tests.test_next_workstream \
  cargento.skills.cargento.tests.test_next_delegation \
  cargento.skills.cargento.tests.test_next_controls \
  cargento.skills.cargento.tests.test_next_flag \
  cargento.skills.cargento.tests.test_next_isolation
```

Expected: PASS. Rerun any load-related failing module alone and record both results before changing
code.

- [ ] **Step 4: Prove stable and next byte oracles together**

Run:

```bash
python3 -m unittest \
  cargento.skills.cargento.tests.test_page.FrontendAssetContractTest.test_load_page_preserves_all_three_byte_oracles \
  cargento.skills.cargento.tests.test_next_page.NextPageAssetContractTest.test_load_next_page_preserves_its_byte_oracles
```

Expected: PASS; stable stays 321,790 bytes with the global SHA and next matches Step 2 output.

- [ ] **Step 5: Commit the one byte-pin checkpoint**

```bash
git add cargento/skills/cargento/tests/test_next_page.py
git commit -s -m "test(ui): pin the attention queue bundle"
```

### Task 9: Verify live cross-harness behavior and finish the branch

**Files:**
- Verify: all files changed by Tasks 1–8
- Capture: `/Users/jaredmscott/repos/recce/cargento/docs/future-ui-exploration/.spacedock-state/future-ui-command-surface/prototyping-attention/attention-wide.png`
- Capture: `/Users/jaredmscott/repos/recce/cargento/docs/future-ui-exploration/.spacedock-state/future-ui-command-surface/prototyping-attention/attention-narrow.png`
- Capture: `/Users/jaredmscott/repos/recce/cargento/docs/future-ui-exploration/.spacedock-state/future-ui-command-surface/prototyping-attention/projects.png`
- Capture: `/Users/jaredmscott/repos/recce/cargento/docs/future-ui-exploration/.spacedock-state/future-ui-command-surface/prototyping-attention/sessions.png`
- Capture: `/Users/jaredmscott/repos/recce/cargento/docs/future-ui-exploration/.spacedock-state/future-ui-command-surface/prototyping-attention/session-claude.png`
- Capture: `/Users/jaredmscott/repos/recce/cargento/docs/future-ui-exploration/.spacedock-state/future-ui-command-surface/prototyping-attention/session-codex.png`
- Capture: `/Users/jaredmscott/repos/recce/cargento/docs/future-ui-exploration/.spacedock-state/future-ui-command-surface/prototyping-attention/session-agy.png`

**Interfaces:**
- Consumes: final candidate and live Claude, Codex, and AGY identities when present.
- Produces: live wide/narrow/route evidence tied to commit and page digest, a clean final suite, and
  a pushed `feat/future-ui`. No UI code originates in this task.

- [ ] **Step 1: Run static, type, and version checks**

Run serially:

```bash
ruff check .
ruff format --check .
mypy
python3 scripts/lint_embedded.py
python3 scripts/validate_plugins.py
python3 scripts/bump_version.py --current
git diff --check
git diff "$(git merge-base origin/main HEAD)"..HEAD -- '*plugin.json' '*marketplace.json' '*gemini-extension.json'
```

Expected: all commands exit zero and version-field diff prints nothing. If installed, run
`claude plugin validate ./cargento --strict` and `agy plugin validate ./cargento`; record a missing
binary as explicit native-validator skip.

- [ ] **Step 2: Run the repository full suite once with coverage**

Check `git worktree list`, then run:

```bash
coverage erase
coverage run -m unittest discover -s cargento/skills/cargento/tests -t .
coverage run -a -m unittest \
  scripts.tests.test_validate_plugins scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded scripts.tests.test_bench_collect \
  scripts.tests.test_capture_hook scripts.tests.test_bench_event_latency \
  scripts.tests.test_derive_prompt_shapes
coverage report
```

Expected: zero failures and coverage at or above `pyproject.toml` fail_under.

- [ ] **Step 3: Start only the server used for live proof**

Run `python3 cargento/skills/cargento/server.py --port 4553 --status`. If another instance owns the
port, leave it untouched and use 4601 below. Otherwise run:

```bash
python3 cargento/skills/cargento/server.py --port 4553 --daemon
python3 cargento/skills/cargento/server.py --port 4553 --status
```

Record PID, product commit, next-page size/SHA, URL, and exact three session IDs before capture.

- [ ] **Step 4: Capture and judge live wide/narrow behavior**

Use `chrome:control-chrome` to open `http://127.0.0.1:4553/?next=true#n=attention` (or port 4601).
At wide viewport capture Attention, Projects, Sessions, and exact Claude/Codex/AGY session routes.
At 320 CSS pixels capture Attention and evaluate:

```javascript
JSON.stringify({
  width: document.documentElement.scrollWidth,
  viewport: document.documentElement.clientWidth,
  headings: Array.from(document.querySelectorAll("main h1")).map(node => node.textContent),
  current: Array.from(document.querySelectorAll('nav[aria-label="Primary"] [aria-current="page"]'))
    .map(node => node.textContent),
  smallTargets: Array.from(document.querySelectorAll("a,button,summary")).filter(node => {
    const box = node.getBoundingClientRect();
    return box.width < 44 || box.height < 44;
  }).map(node => node.textContent.trim())
})
```

Require width <= viewport, one route h1, one current top-level link, no small target, item DOM order
matching grammar, visible uncertainty, and no all-clear/prediction/repository/unread/death/borrowed
authority copy. If live data lacks ask/risk/stop, tie those branches to executed fixtures rather
than inventing state.

Use source-present routes for normal Attention and detail evidence. When live data lacks the gate,
stale retry, answer, or disclosure states, render one deterministic browser-only representative
payload and retained refresh state. At 320 CSS pixels, measure project/session breadcrumbs, the
needs-input gate, Retry now, answer buttons, coverage summary, and expansion/collapse control.
Require every actionable link, button, summary, and link-role control to measure at least 44 by 44,
with no horizontal overflow, one h1, and the correct current Primary link. Record which evidence was
live and which was fixture-driven.

- [ ] **Step 5: Stop only the server from Step 3**

Run:

```bash
python3 cargento/skills/cargento/server.py --port 4553 --stop
python3 cargento/skills/cargento/server.py --port 4553 --status
```

Use 4601 in both commands if selected. Expected: port free and status not running; do not broadly
kill processes.

- [ ] **Step 6: Reconcile docs and commit only actual generated drift**

Invoke repository `sync-docs`; let that skill select and commit only the owned documentation it
changes. Then inspect its exact checkpoint:

```bash
git status --short
git show --stat --oneline --decorate HEAD
git diff --check HEAD^..HEAD
```

If the skill reports no drift, create no empty commit and record that outcome.

- [ ] **Step 7: Push and stop for the workflow gate**

```bash
git status --short
git log --oneline cc2f323..HEAD
git push origin feat/future-ui
git rev-parse HEAD
git rev-parse origin/feat/future-ui
```

Expected: clean product worktree, matching local/remote heads, and DCO sign-off on each commit. Do
not open a PR, merge, or target main. Return exact checkpoint, checks, page digest, capture hashes,
and source limits to the Spacedock report.

## Execution handoff

Plan complete and saved to
`docs/superpowers/plans/2026-08-31-future-ui-attention-queue.md`. After captain selection, use one:

1. **Subagent-Driven (recommended)** — use `superpowers:subagent-driven-development`; one fresh
   implementer per task and two-stage review before the next task touches the web surface.
2. **Inline Execution** — use `superpowers:executing-plans`; execute in order with a review
   checkpoint after each signed-off commit.

Do not begin either mode until the captain chooses it.
