---
id:
title: Session Operations Board
status: crucible
source: Captain rejection of future-ui-command-surface on 2026-09-01
started: 2026-09-01T00:07:26Z
completed:
verdict:
score: 1.0
worktree:
issue:
pr:
gates:
    version: 1
    records:
        - id: gate:future-ui-session-operations-board:framing
          stage: framing
          attempts:
            - id: gate-attempt:future-ui-session-operations-board-framing-1
              briefing:
                id: briefing:future-ui-session-operations-board:framing:attempt-1:revision-1
                digest: sha256:0af4a0e2729c814dd724d3b4236c0b350bee235e8df0c65e1f25fadfaf3c2b53
                room-ref: ./review/framing/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:future-ui-session-operations-board:framing:1
                briefing: briefing:future-ui-session-operations-board:framing:attempt-1:revision-1
                by: person:captain
                at: "2026-09-01T00:04:15.863052Z"
                decision: approve
                reason: Captain approved the Session Operations Board direction and explicitly requested preparation retry after the corrected artifact path was identified.
              application:
                target-stage: reconnaissance
                state: consumed
        - id: gate:future-ui-session-operations-board:crucible
          stage: crucible
          attempts:
            - id: gate-attempt:future-ui-session-operations-board-crucible-1
              briefing:
                id: briefing:future-ui-session-operations-board:crucible:attempt-1:revision-1
                digest: sha256:df255ff9ddd85ec2182b091a59a62a7c3ec2a6eae579dd60bbb80096489bebf0
                room-ref: ./review/crucible/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:future-ui-session-operations-board:crucible:1
                briefing: briefing:future-ui-session-operations-board:crucible:attempt-1:revision-1
                by: person:captain
                at: "2026-09-01T01:15:16.275796Z"
                decision: revise
                reason: 'Captain accepts the exact-session direction but requires correction: enforce stable column sizing across every desktop row; replace the broken 320px table with near-full-width mobile cards or an intentional horizontal-scroll table; remove the redundant SESSION label on session detail and make current activity the dominant lede; integrate running subagents into current activity; and separate actually active/open sessions from historical sessions so the fleet cannot imply that seven sessions are currently open when only one is active.'
review-round:
    id: round:future-ui-session-operations-board:crucible:1
    stage: crucible
    cycle: 1
    briefing:
        id: briefing:future-ui-session-operations-board:crucible:attempt-1:revision-1
        digest: sha256:df255ff9ddd85ec2182b091a59a62a7c3ec2a6eae579dd60bbb80096489bebf0
        room-ref: ./review/crucible/round-1
---

Replace the Attention-first ranking model with an exact-session operations board that lets a person scan the fleet and answer where each session is, what it is doing now, what it may do next, and whether it is blocked.

## Design bet

Cargento will become easier to understand if exact sessions are the irreducible unit of the default view. Four fleet facts lead; one comparable session surface carries WHERE, NOW, NEXT, and BLOCKED. Exceptions change sorting and emphasis but never replace or aggregate away sessions.

## Baseline and command risk

The accepted command-surface checkpoint hides fleet state behind attention subjects. It reports contradictory running and moving counts, promotes identity coverage above current work, collapses seven exact sessions into one risk, and offers no route that compares WHERE, NOW, NEXT, and BLOCKED fleet-wide. Browser-default link color, orphan list numbering, and a shared CSS class also corrupt the visual hierarchy.

## Method

Use real Codex, Claude Code, and Antigravity sessions to test the truth boundary for location, activity, plans, and blockage. Prototype the Session Operations Board on `feat/future-ui`. After each correction, run fresh visual, semantic, and cross-harness review before another captain gate.

## Acceptance criteria

**AC-1 — The default view exposes fast fleet facts without contradiction.**
Verified by: a live capture and payload comparison showing total observed sessions, working sessions, exact requests, and reported blocks are computed from the same exact-session population.

**AC-2 — A five-second scan identifies every operational session and its four command facts.**
Verified by: fresh reviewers can locate each exact session and state its WHERE, NOW, NEXT, and BLOCKED values without opening another route; unsupported facts read as not published or unknown rather than empty panels.

**AC-3 — Exceptions never erase fleet context.**
Verified by: collision, request, risk, and missing-source fixtures preserve one visible row per exact session while changing only row emphasis, badges, or sort order.

**AC-4 — Source limits remain truthful across Codex, Claude Code, and Antigravity.**
Verified by: live three-harness evidence distinguishes reported, inferred, unknown, and absent facts; an in-progress task appears under NOW, and only a pending published step may appear under NEXT.

**AC-5 — The visual system makes status and navigation legible.**
Verified by: wide and 320-pixel captures show no browser-default links, orphan numbering, false active stripes, clipped command facts, or horizontal overflow; semantic status colors and focus states meet the repository's accessibility checks.

## Iteration record

The prior `future-ui-command-surface` experiment remains archived at commit `1cb112e`. This successor records the captain's rejection of the Attention model and approval of the Session Operations Board direction.

## Known limits

Cargento currently preserves a lossy project display label rather than exact directory, repository, branch, or worktree location. Codex and Claude publish different kinds of plan evidence; Antigravity publishes no native next-action list and cannot always report blocked state.

## Out of scope

This experiment does not merge to `main`, claim exact filesystem location from project labels, or redesign stable UI outside `?next=true`.

## Reconnaissance evidence

The live server rendered the `feat/future-ui` checkpoint at `1cb112e` on
`http://127.0.0.1:4553/?next=true`. A `/api/data` observation generated at
`2026-09-01T00:11:31Z` contained seven exact sessions in the 24-hour window: one
working session, six idle sessions, one running subagent, four of four reported tasks
complete, no exact requests, and zero reported `needs_input` sessions. That last
number is not fleet-wide proof of no blockage: the harness registry says Antigravity
does not report `needs_input`.

### Exact observed sessions

| Harness | Exact source identity | Live observation | Source boundary for WHERE / NOW / NEXT / BLOCKED |
|---|---|---|---|
| Codex | `01a0555c-2da3-7c23-bd26-4ea2e275d18a` (`01a0555c` display key) | The live first-officer session was working with subagent `Einstein`; all four published plan items were already complete. | WHERE is only the lossy `recce/cargento` label. NOW is source-backed as `running 1 subagent`. No pending or in-progress plan step publishes NEXT. Codex can report `needs_input`, and this exact session had no request, so BLOCKED is **not reported**, not disproved. |
| Claude Code | `8b3e5aa1-4ed6-4ac9-91f0-7d148c3ea631` (`8b3e5aa1` API identity) | The real `CLAUDE-RECON-20260831` session completed its one-turn README task and was idle. Its transcript and the live API agree on the assignment. | WHERE is only the lossy project label. NOW is source-backed as `awaiting your message`; the assignment is published. The transcript publishes no NEXT. Claude can report `needs_input`, and this exact session had no request, so BLOCKED is **not reported**, not disproved. |
| Antigravity | `49fad07a-21aa-4b2e-9c14-ecfcbcf67ab8` (`49fad07a` display key) | The real `AGY-RECON-20260831` session completed its README task and was idle. The generated transcript preserves the marked request, while the bounded public CLI log preserves identity and lifecycle but lacks the `HandleUserInput` prompt marker before `Forwarding user message`. | WHERE is only the lossy project label and NOW is source-backed as idle. The current collector deliberately reads the public log, so assignment and NEXT are not published to the API even though the generated transcript records the request. Antigravity does not report `needs_input`; BLOCKED is therefore **unknown**, not false. |

### Live captures

- [Project overview](reconnaissance/overview-projects.jpg) — 1531×1103; two project rows aggregate seven payload sessions, so six `recce/cargento` sessions disappear behind one label.
- [Flat session inventory](reconnaissance/overview-sessions.jpg) — 1531×1047; all seven payload sessions render, but exact IDs and WHERE / NOW / NEXT / BLOCKED are not comparable visible columns.
- [Codex exact-session drill-down](reconnaissance/session-codex-01a0555c.jpg) — full UUID in the breadcrumb, source-backed current activity, completed plan, live subagent, and the expanded missing-assignment/NEXT disclosure.
- [Claude Code exact-session drill-down](reconnaissance/session-claude-8b3e5aa1.jpg) — collector identity, source-backed full assignment, idle state, and the expanded missing-NEXT disclosure.
- [Antigravity exact-session drill-down](reconnaissance/session-agy-49fad07a.jpg) — full UUID in the breadcrumb, idle state, and the expanded public-log assignment/NEXT limit.

### Fact versus inference inventory

| Command fact | Source-backed fact | Inference the board must not make | Current UI classification |
|---|---|---|---|
| Fleet | `/api/data` contains seven sessions and the flat table renders seven rows. | Two project labels are not two operational sessions, and a shared label does not establish a shared directory or worktree. | **UI failure:** the default project tab aggregates exact sessions away; the alternate table hides IDs in `data-next-session` attributes rather than showing them. |
| WHERE | Every row has a harness, exact collector identity, and lossy two-segment project label. | `recce/cargento` is not an exact path, repository, branch, or worktree. | **Mixed:** the source lacks exact location, while the UI presents the lossy label without a visible `not published` WHERE fact. |
| NOW | Codex reports working with one named subagent; Claude and Antigravity report idle. Claude also publishes its assignment. | Completed Codex plan items do not explain what the still-running subagent is doing; AGY's project-name heading is not an assignment. | **Mostly source-backed:** drill-down current activity is truthful, but the fleet view does not give NOW a stable comparable label. |
| NEXT | None of the three observed sessions publishes a pending step; each expanded source-coverage note says so. | A completed plan, transient assignment, idle state, or running subagent is not a next action. | **UI hierarchy failure:** truthful disclosures exist only collapsed inside each drill-down, so NEXT cannot be scanned fleet-wide. |
| BLOCKED | No exact request was present. Codex and Claude can report `needs_input`; Antigravity cannot. | `summary.needs_input: 0` cannot prove Antigravity is unblocked, and `awaiting your message` is not a block contract. | **Mixed, command-critical:** the source limitation is real, but no visible per-session `not reported` or `unknown` fact prevents a false all-clear. |
| Status emphasis | Only the first row is working. | A continuous green rail through every ACTIVITY cell does not mean every row is active. | **Pure UI failure:** `.next-session-activity` styles both the detail card and every table activity cell, giving idle rows the active accent. |

### Ranked findings

1. **Critical command risk — fleet context / all four facts:** the default view reduces seven exact sessions to two project rows. A captain cannot identify every session or compare WHERE, NOW, NEXT, and BLOCKED without changing views and opening rows; this is a UI failure because the payload already has all seven session records.
2. **High command risk — BLOCKED:** Antigravity explicitly does not report `needs_input`, yet neither overview nor row exposes BLOCKED as unknown. Any fleet-wide reading of zero reported blocks as zero blocked sessions is unsupported; source and UI share ownership.
3. **High command risk — NEXT:** none of the three live sources publishes a pending next action, but `not published` appears only in a collapsed drill-down disclosure. Completed Codex tasks plus a live subagent make silent inference especially tempting; this is a UI hierarchy failure over a truthful source gap.
4. **High comprehension risk — WHERE:** six sessions collide on `recce/cargento`; the warning says labels are lossy but supplies no exact location or explicit unknown. The missing directory/branch/worktree is a source limit, while presenting the label as the only location cue is a UI failure.
5. **High comprehension risk — identity:** the flat fleet table omits visible exact IDs, and Claude's collector intentionally reduces its source UUID to eight characters. The UI could expose the identities it receives, but it cannot reconstruct Claude's full UUID from the current payload.
6. **Medium comprehension risk — NOW emphasis:** one working row correctly owns the left accent, but the shared `.next-session-activity` selector draws an accent rail through all seven rows. This pure UI defect visually promotes idle activity and weakens the one real working signal.

## Stage Report: reconnaissance

- DONE: observe one real session each from Codex, Claude Code, and AGY, preserving exact session identity and distinguishing missing source data from UI failure.
  The three exact source identities above were matched to the live API and native records; changing a UUID, marked request, prompt-marker boundary, or harness capability would break the classification.
- DONE: capture the live project overview and an exact-session drill-down from the current Next UI without replacing the sessions under study with mock-only evidence.
  Five live 1531-pixel-wide captures preserve the seven-row payload, project aggregation, and all three exact drill-downs; removing a route, source disclosure, or observed session would make the capture set incomplete.
- DONE: record a fact-versus-inference inventory and rank findings by comprehension or command risk against WHERE, NOW, NEXT, and BLOCKED.
  The inventory binds every command fact to `/api/data`, native records, renderer behavior, or an explicit source limit; each ranked finding names source, UI, or mixed ownership.

### Summary

Three real harness sessions show that the current UI reports NOW honestly at drill-down but cannot yet operate as an exact-session board. The default aggregation erases fleet context, WHERE is lossy, NEXT is buried as missing coverage, and BLOCKED is unsafe for Antigravity; the five committed live captures preserve those boundaries for prototyping.

## Prototype checkpoint

The approved Session Operations Board is checkpointed and pushed only on
`feat/future-ui` at commit `569c8ca`. The default and legacy overview fragments
now normalize to Sessions, Projects remains the secondary inventory, and the
board renders one native-link row for every exact payload session. The four
fleet facts and the header counts derive from that same row population rather
than `summary` aggregates.

Every row visibly preserves harness identity and the collector-provided session
ID, followed by comparable WHERE, NOW, NEXT, and BLOCKED facts. WHERE explicitly
calls the project value a label and says exact location is not published. NOW
prefers a published `in_progress` task and otherwise uses only `state_detail`.
NEXT uses only a published `pending` task. BLOCKED distinguishes a reported
request, no reported block from a capable harness, and unknown from a harness
that cannot report blocks. Exceptions sort first and receive status emphasis,
but never replace or merge rows.

The prototype also separates `.next-session-current` from the removed
`.next-session-activity` table selector. In the live capture exactly one of
seven rows owns the working rail and glyph; the six idle rows no longer receive
false active styling.

### Exact-byte before and after evidence

The before capture is the reconnaissance flat inventory served from commit
`1cb112e`:

- [Before — flat session inventory](reconnaissance/overview-sessions.jpg) —
  1531×1047 JPEG,
  `sha256:fddd18cc24258c08e7bc68f478f72bc859d6b306a3bd3cee842fcb0d1298b3eb`.

The after captures were served from the pushed candidate commit `569c8ca` on
`http://127.0.0.1:4554/?next=true#n=sessions`. The top and scrolled tail together
show all seven exact rows in the live payload:

- [After — board header and leading rows](prototyping/after-wide-569c8ca.jpg) —
  1531×1103 JPEG,
  `sha256:dd6563eeb2ff34bfce5f9453555175d7e73da55b8d9d0e0056edf0e34d01b670`.
- [After — board tail with the seventh exact row](prototyping/after-wide-tail-569c8ca.jpg) —
  1531×1047 JPEG,
  `sha256:9c8e1484f287cb43648c2eb1e3c6b524c7a2f4448bab42dfdf549d23e94ac885`.

The live DOM and the visible board agreed on seven rows, one working row, zero
exact requests, zero reported blocks, and block-state reporting for six of seven
sessions. `document.documentElement.scrollWidth` equalled the 1531-pixel
viewport; no operation row retained browser-default link color, and exactly one
row contained a live activity glyph.

### Responsive proof and residual limitation

Focused CSS contracts exercise the 980-pixel transition to two comparable fact
columns, the 620-pixel transition to one `minmax(0,1fr)` column, unbreakable-text
wrapping, and the absence of the old shared activity selector. The assembled
Next page and its source assets also pass the HTML/CSS/JS source linter.

An exact 320-pixel visual capture is deliberately **SKIPPED**. The connected
Chrome backend advertised a viewport override and accepted `{width: 320,
height: 900}`, but both an existing tab and a fresh tab continued to report
`innerWidth: 1531`, `scrollWidth: 1531`, and the five-column computed grid. The
temporary override was reset, the falsely named capture was deleted, and no
data-URL, raw-CDP, or alternate-browser workaround was used. The responsive CSS
is mechanically verified; visual verification at exactly 320 pixels remains a
residual limitation of this stage's browser backend.

### Verification

- `python3 -m unittest cargento.skills.cargento.tests.test_next_page cargento.skills.cargento.tests.test_next_chrome cargento.skills.cargento.tests.test_next_session cargento.skills.cargento.tests.test_next_sessions` — 83 tests passed.
- Focused `ruff check` passed and `ruff format --check` reported all four touched test modules formatted.
- `python3 scripts/lint_embedded.py` reported clean JavaScript syntax, CSS structure, DOM references, and part inventory.
- Mechanically recomputed assembled Next page: 304,686 bytes,
  `sha256:0e83371a77e737a16afa995ea1ec727c01fd35c07b61cbf9d1da10ab713d176a`.

## Stage Report: prototyping

- DONE: implement one coherent candidate that makes exact sessions the default command surface and exposes fleet facts plus truthful WHERE, NOW, NEXT, and BLOCKED values without aggregating exceptions away.
  The live seven-session payload rendered seven visible native-link rows; changing any exact ID, state, request, pending task, harness capability, or project label changes the corresponding board fact rather than a detached summary.
- DONE: preserve source limits and scope with focused behavior tests, mechanically recomputed Next byte pins, and responsive source contracts.
  Eighty-three focused tests passed across the assembled page, chrome, session detail, and operations board; the 304,686-byte assembled digest and every changed part digest are pinned from current assets, and the 980/620 layouts plus unbreakable-text behavior are exercised without changing stable UI.
- DONE: checkpoint the accepted candidate only on `feat/future-ui` and capture exact-byte before/after desktop evidence.
  Pushed commit `569c8ca` is the sole product checkpoint, the prior `1cb112e` capture and two candidate captures carry exact SHA-256 digests, and neither the candidate nor the state report was merged to `main`.
- SKIPPED: capture an exact 320-pixel visual from the connected Chrome backend.
  The supported viewport control accepted 320×900 twice but both existing and fresh tabs remained 1531 pixels wide; the invalid artifact was deleted and the mechanically green responsive proof is retained with this explicit visual-verification limitation.

### Summary

The prototype replaces the rejected attention ranking with a truthful exact-session operations board. It preserves every observed session, makes source gaps explicit, fixes the false activity rail, and checkpoints reproducible code, tests, byte pins, and wide live evidence on `feat/future-ui`; only the browser-backend-dependent 320-pixel visual capture remains skipped.

## Crucible recommendation

**REVISE.** Commit `569c8ca` establishes the right exact-session information
architecture, but it is not ready for a captain gate. The live renderer defeats
its own grid at every viewport, a legal request/state skew makes the fleet block
count contradict its row, and the board does not expose either current-assignment
absence or captain responsibility. Fix those four command failures, then repeat
the live wide, 320-pixel, request-skew, and three-harness review.

### Command-question result

| Question | Result from the live candidate |
|---|---|
| Overall situation | **Partial.** The live board truthfully showed 7 observed, 1 working, 0 exact requests, 0 reported blocks, and 6/7 block reporters, but the adversarial request/state case makes the last two facts disagree. |
| Current assignment | **No, fleet-wide.** The working Codex row shows its title/last prompt, `I approve the direction, continue the work`, while the payload has `instruction: null`; only the collapsed drill-down disclosure says the assignment was not published. Antigravity says only `Title not published`. |
| Execution state | **Yes at the source boundary.** Every live row visibly says Working or Idle and the one working row alone owns the live glyph and rail. |
| Current activity | **Yes at the source boundary.** Codex says `running 1 subagent`; Claude and Antigravity say `awaiting your message`. What the subagent itself is doing remains unpublished. |
| Next action | **Yes at the source boundary.** Every live row says `No pending step published`; no completed task or active subagent is promoted into NEXT. |
| Captain responsibility | **No on the board.** A Spacedock-owned fixture request renders only `BLOCKED / Reported / Approve release?`; the exact same session renders `CAPTAIN` after drill-down. |

### Reproduced material findings

1. **BLOCKER — the comparable board is not a grid.** In the live 1531-pixel
   page every `.next-operation-row` computed to `display: inline-flex`, because
   `#app a` outranks `.next-operation-row`. Across the first four rows the WHERE
   x-coordinate was 408, 374, 363, and 673 pixels; NOW was 630, 596, 585, and
   895. The columns therefore do not compare despite their headers. At an actual
   320×900 override, `innerWidth` and `scrollWidth` both measured 320, but the
   five cells stayed side by side at widths 76/59/47/56/46 pixels and heights
   411/355/262/194/331 pixels, wrapping labels and values to one or two
   characters per line. This is a visual-hierarchy, information-architecture,
   responsive, and accessibility failure owned by the candidate CSS.
2. **HIGH — fleet and row disagree about a live exact request.** The ask
   registry and collector state are independent. With both fixture gate states
   changed to Idle while retaining `ask-live`, the rendered fleet facts were
   7 observed, 2 working, 1 exact request, and **0 reported blocks**, while the
   matching row still said **BLOCKED / Reported / Approve release?**. The row
   counts an ask or `needs_input`; the fleet count uses only `needs_input`.
   Ownership is the board aggregation, not the source contract.
3. **HIGH — current assignment is not answerable or explicitly absent on the
   board.** Session identity uses `title || last_prompt`, which is not the
   assignment contract. The live Codex drill-down correctly admits the missing
   assignment only inside SOURCE COVERAGE. Ownership is mixed: collectors own
   publication, while the board owns exposing `not published` instead of a
   potentially misleading title substitute.
4. **HIGH — captain responsibility disappears at fleet level.** Adding
   Spacedock metadata to the exact asking fixture produced no `CAPTAIN` marker
   in its BLOCKED fact, while its drill-down rendered `<h2>CAPTAIN</h2>`. The
   default command surface therefore requires navigation to answer who must
   act. Ownership is the board renderer.

### Prior-round dispositions and surviving uncertainty

| Prior finding | Disposition |
|---|---|
| Fleet context and four comparable facts | **Partial:** seven live payload sessions remain seven visible rows, but finding 1 reopens comparability. |
| BLOCKED truth for Antigravity | **Partial:** live Antigravity correctly says Unknown and 6/7 coverage is explicit, but finding 2 reopens fleet truth. |
| NEXT hidden in drill-down | **Resolved:** NEXT is visible and refuses completed/in-progress inference. |
| WHERE overstates a lossy label | **Resolved at the available boundary:** each row says Project label and Exact location not published. Exact path/branch/worktree remains a collector/runtime uncertainty. |
| Exact identity hidden | **Resolved at the available boundary:** each row exposes the collector identity. Claude's eight-character identity remains collector-owned. |
| False active rail on idle rows | **Resolved:** one live working row owns the glyph and rail; idle rows do not. |

The remaining source-owned uncertainties are exact path/branch/worktree for all
three harnesses, Codex/Antigravity assignment coverage, the activity of the live
Codex subagent, and block state for Antigravity. Candidate-owned uncertainties
are the four reproduced findings above. The semantic tree otherwise exposes a
Primary navigation, one H1, a Fleet facts region, native session links, and
repeated per-fact labels; four keyboard Tabs reached the first exact-session link
with a computed 2-pixel visible outline. The focused 83-test suite stayed green,
which demonstrates that its source-token contracts do not exercise the computed
CSS cascade or the request/state disagreement.

## Stage Report: crucible

- DONE: recommend revise, reframe, or accept, explicitly testing whether users can quickly answer overall situation, current assignment, execution state, current activity, next action, and captain responsibility while naming every material uncertainty and its owner.
  **REVISE:** the command-question table records three yes, one partial, and two no results; the recommendation names the candidate, collector, and runtime owners that must converge before another gate.
- DONE: independently exercise the live candidate at the layer where it can fail across visual hierarchy, information architecture, command truth, cross-harness comprehension, session drill-down, accessibility, and adversarial states.
  Live 1531- and 320-pixel rendering, computed layout geometry, keyboard focus, semantic structure, the exact Codex drill-down, all three harness rows, and request/collision/source-gap fixtures were exercised; changing the cascade, route, harness boundary, or request predicate changes the recorded evidence.
- DONE: reproduce every material finding, resolve disagreements with direct evidence, and record a disposition for every finding without treating green tests as convergence.
  Four findings were reproduced from computed browser state or renderer output, all six prior findings have explicit dispositions, and the 83 passing focused tests are recorded as evidence of the oracle gap rather than acceptance.

### Summary

The exact-session model is the right reframe and four prior command gaps are
resolved, but the candidate fails its core promise at the rendered layer and in
two legal source states. Revise the CSS cascade, fleet block predicate,
assignment absence, and fleet-level responsibility label, then return the same
candidate to crucible with fresh wide and 320-pixel proof.

## Stage Report: prototyping — correction round 1

- DONE: make active work unmistakable and separate recently observed history without falsely claiming either that historical records are open or that idle records are closed.
  Commit `8f4ba8e` uses only explicit working, needs-input, or exact-request evidence for `Active now`; every other observed record remains reachable under `Recent history`, whose visible copy says that recent observation is not proof the harness process is still open or closed. The live mixed capture shows one active row and three recent-history rows without dropping an exact session.
- DONE: implement stable comparable desktop columns, an intentional near-full-width 320-pixel card interaction, and a session-detail hierarchy led by current activity with running subagents integrated.
  All four live desktop rows computed to `display: grid` with the identical `333.047px 222.047px 277.547px 277.562px 249.797px` column template. At a real 320×900 Chrome viewport, `innerWidth` and `scrollWidth` were both 320 pixels, column headers were hidden, and the active card measured 304 pixels wide at x=8. The exact-session capture places current activity at y=185 above identity at y=390, includes the running-subagent count and Einstein activity inside that lede, removes the redundant `SESSION` label, and has no detached subagent section.
- DONE: prove fleet/row request agreement and the redesigned hierarchy with adversarial tests, mechanically recomputed Next byte pins, and matched wide/mobile/active-history/detail captures on `feat/future-ui` only.
  The 215-test Next suite exercises explicit active/history membership, idle plus exact-request promotion, request/state skew, an exact request from a harness without block reporting, fleet and row block agreement, assignment absence, captain responsibility, CSS specificity, the 620/360 breakpoints, and detail ordering. The product checkpoint and all evidence are on `feat/future-ui`; nothing was committed or merged to `main`.

### Verification

- `python3 -m unittest discover -s cargento/skills/cargento/tests -t . -p 'test_next*.py'` — 215 tests passed.
- Focused `ruff check` and `ruff format --check` passed for all six touched Next test modules.
- `python3 scripts/lint_embedded.py` reported clean JavaScript syntax, CSS structure, DOM references, and part inventory; `git diff --check` passed before the product checkpoint.
- Mechanically recomputed Next parts:
  - `next-chrome.js`: 13,147 bytes, `sha256:577ce15c7c396e2aaaa718a14a458dc21ab397fa78115aa53c85d574dd498c4d`
  - `next-sessions.js`: 10,685 bytes, `sha256:74ae6544e03de5335254a87d4fd66dd00484c78d1ee2b5630b8b494894292a95`
  - `next-session.js`: 15,905 bytes, `sha256:976d297c1d1298617bf44af69e656441be1117505212f62970042e18418ba696`
  - `styles.css`: 36,343 bytes, `sha256:c21ec6085310d06192f54235d1994f970917b9c6b7ebd905231a5b52a3e2b13c`
  - assembled Next page: 308,256 bytes, `sha256:a8333a8baca65896bacb2bab4f7aecc2ddfeb73a1e0fc01be8ac77124c439574`
- Exact-byte capture evidence under `prototyping/correction-1/`:
  - `wide-mixed-active-history-8f4ba8e.jpg` — 1531×1047, `sha256:771b17730e77ec1befffaf19e1eb4d61a85f41ed8ee5839d45dd1c39ddab0810`
  - `wide-active-only-8f4ba8e.jpg` — 1531×320, `sha256:94c171cd1c4f910080e51dac4c142ae542c4010a05ffb6fbd634744f9c47e0b6`
  - `mobile-320-overview-8f4ba8e.jpg` — 320×900, `sha256:98cc5964d7d02c1ec0d91865e26840d506baf0ffaafa6e50b752239a11470b9e`
  - `mobile-320-active-card-8f4ba8e.jpg` — 320×900, `sha256:bd4faa8b29e91ddb93ab0c36cdca290149a33eda12b0071deac11be533135794`
  - `detail-activity-led-8f4ba8e.jpg` — 1531×1047, `sha256:4f693824cb8a146ceb7825fb00462582d116f856fbd09591c926f417c3e5ecab`

### Summary

Correction round 1 preserves the exact-session model while making its command truth legible: explicit active evidence leads, recent observations are clearly historical, every row shares one desktop geometry, mobile becomes a near-full-width card, exact requests agree from fleet to row, and current activity—including subagents—leads session detail. Product commit `8f4ba8e` and matched live captures replace the rejected `569c8ca` candidate on `feat/future-ui` without touching `main`.

## Crucible re-review — correction round 1

**REVISE.** Commit `8f4ba8e` resolves all four prior findings when session IDs
are unique, and the active/history, desktop, mobile, and detail redesigns survive
live review. It still violates the product's canonical `(harness, sid)` session
identity at two command-critical joins: routes use only project plus SID, and
asks use only SID. One legal cross-harness SID collision therefore makes an
exact session unreachable and duplicates or misassigns an exact request.

### Correction-package result

| Surface | Independent result |
|---|---|
| Active now versus recent history | **Pass.** The live API contained one Working Codex row and three Idle Claude/Antigravity rows. The DOM placed exactly one SID under Active now and the other three under Recent history; the copy says active evidence is Working, Needs input, or an exact request and explicitly refuses to infer that a recent harness process is open or closed. |
| Stable desktop geometry | **Pass.** All four live rows computed to `display: grid`, width 1360 at x=86, child x-coordinates 86/419/641/918/1196, and the identical `333.047px 222.047px 277.547px 277.562px 249.797px` template across both groups. |
| Intentional 320-pixel cards | **Pass.** A real 320×900 override measured `innerWidth = scrollWidth = 320`; both column headers computed to `display: none`, and the first link was a 304-pixel card at x=8 with one 302-pixel grid column and vertically stacked, readable facts. Four keyboard Tabs reached that card with a computed 2-pixel visible outline. |
| Activity-led detail | **Pass.** Live current activity began at y=185, the identity header followed at y=368, and the Faraday row at y=270 was inside current activity. The semantic tree announced current activity and one running subagent before the H1; no detached subagent section remained. |
| Six captain questions | **Pass for the live population:** overall situation is 1 active of 4 recently observed; assignment is published or explicitly absent; state, activity, and NEXT are visible; no captain action is currently reported. The collision finding below invalidates responsibility and drill-down for a legal adversarial population. |

### Prior-finding dispositions

1. **Resolved — computed CSS cascade.** The higher-specificity row selector now
   wins at desktop, 980, and 620/360 breakpoints; the live desktop and 320-pixel
   measurements above disprove the prior inline-flex failure.
2. **Resolved for one canonical identity — request/state skew.** After changing
   both fixture gate states to Idle while retaining one exact ask, fleet facts
   rendered Active 3, Working 2, Exact requests 1, Reported blocks 1; the one
   owner row moved into Active now and said `BLOCKED · NEEDS YOU / Reported /
   Approve release?`.
3. **Resolved — assignment absence.** Every live row now exposes the assignment
   or `ASSIGNMENT · Not published`; the title remains separately labelled as
   session identity.
4. **Resolved for one canonical identity — captain responsibility.** A unique
   Spacedock asking fixture said `BLOCKED · CAPTAIN` on the board and `CAPTAIN`
   in drill-down.

### New reproduced finding

**BLOCKER — exact-session ownership drops the harness.** Runtime aggregation and
the UI's own `nextSessionKey` define identity as `(harness, sid)`, but
`nextSessionFind`, `nextExactAskOwner`, `nextSessionAsks`, and
`nextOperationsAskFor` do not preserve that pair.

- With Cursor and Antigravity rows sharing SID `idle-mid` and project
  `idle/mid`, both rendered links had the identical
  `#n=session:idle%2Fmid:idle-mid` route. The Antigravity row titled `Shadow AGY`
  was visible on the board, but navigation always resolved the Cursor row titled
  `Middle idle`; `Shadow AGY` had no reachable drill-down.
- With the duplicate Antigravity row instead carrying Spacedock metadata and one
  Antigravity ask, the fixture should have rendered Active 5, Exact requests 2,
  Reported blocks 3, and one `BLOCKED · CAPTAIN` owner. It rendered **6 / 2 / 4**
  and repeated `Choose the release lane` on both rows as **BLOCKED · NEEDS YOU**.
  The question, block, active membership, and responsibility were all attributed
  by SID alone to the wrong number of sessions and the wrong owner.

The candidate owns this identity join. Source-owned uncertainty remains exact
path/branch/worktree for every harness, assignment for live Codex and
Antigravity, the live subagent's task, Antigravity's unblocked state, and whether
a Recent history process is open or closed; the corrected UI now labels each of
those boundaries without inference. The independently rerun 215-test Next suite
and embedded-source linter were green, but neither contains a cross-harness SID
collision, so they do not contradict the reproduced blocker.

## Stage Report: crucible (cycle 2)

- DONE: independently verify that active-now and recent-history grouping is source-bound, unmistakable, and never implies either seven open sessions or false closure of idle records.
  The live API-to-DOM comparison placed one Working row in Active now and all three Idle rows in Recent history while the visible copy withheld both open and closed inference; changing state or adding an exact ask changes membership.
- DONE: exercise identical desktop column geometry, near-full-width 320-pixel cards, and activity-led session detail with subagents integrated at the rendered and accessibility layers.
  Fresh computed geometry, wide/mobile screenshots, semantic snapshots, and keyboard focus prove all four claims; restoring inline-flex, horizontal facts, identity-first order, or detached subagents would change the measurements.
- DONE: reproduce request/state skew and every prior material finding against commit 8f4ba8e, disposition regressions or new findings, and recommend revise, reframe, or accept without relying on green tests alone.
  All four prior findings are resolved for unique IDs, but a cross-harness SID collision reproduced one unreachable detail and duplicated/misassigned ask truth despite 215 green tests; recommendation is **REVISE**.

### Summary

Correction round 1 successfully fixes the prior candidate and establishes a
clear active/history command surface, readable mobile cards, and activity-led
detail. Revise the remaining identity boundary so routes and asks preserve
`(harness, sid)`, add the collision fixture at renderer and navigation layers,
then repeat only the affected fleet/request/drill-down proofs.

## Stage Report: prototyping — correction round 2

- DONE: Desktop sessions use shared headers only, mobile cards retain only necessary local labels, and historical or missing optional facts do not compete with active evidence.
  At checkpoint `f57b136`, the wide DOM reports the shared header as `grid` and
  row-local labels as `none`; the 320-pixel DOM reports the shared header as
  `none`, local labels as `block`, zero visible history NOW/NEXT/BLOCKED facts,
  zero history assignments, and `scrollWidth === innerWidth === 320`. The
  historical-assignment fixture now fails if identity/project-only history
  regresses, while the CSS contract fails if either responsive label boundary
  is reversed.
- DONE: Session routes, asks, and the accessible copy-ID control preserve canonical harness-plus-session identity and prove collision-safe navigation and ownership.
  The collision fixtures exercise two harnesses with the same SID through route
  production, route parsing, detail lookup, focus restoration, exact ask
  ownership, and operations-board request state. Removing either harness key
  changes those assertions. Rendered rows expose a title link and sibling
  keyboard-operable Copy ID button, zero nested link/button controls, tooltip
  text containing the full ID, clipboard writes, and a polite copied/failed
  status; the raw ID is not visible row metadata.
- DONE: Projects receive the same active-versus-history and omit-missing-data discipline, with focused tests, recomputed Next byte pins, and matched wide/mobile captures on feat/future-ui only.
  Projects render Active projects before Recently observed projects, derive
  situation/workflow/assignment claims only from active evidence, and leave
  history at identity/scope. Focused fixtures fail on stale history claims,
  negative placeholders, absent assignments, or collapsed summary spacing.
  The final `feat/future-ui` checkpoint is `f57b136`; the assembled Next page is
  315,840 bytes with SHA-256
  `06b03556fae32f180fcb78a72d28f48059f52da18482b357bccb42504c399cef`.

### Exact captures

- [Wide Sessions, 1531×1103](prototyping/correction-2/wide-sessions-f57b136.jpg) — SHA-256 `b15dab90804ec42595ba6ed3e19450e7a0648c6fc36e66cd9e06766eeb05a9f5`.
- [Mobile Sessions, 320×1752](prototyping/correction-2/mobile-320-sessions-f57b136.jpg) — SHA-256 `219868e19143d7b4acb1cb065a899a227f82fe1383218f0c59321033c27a2ecf`.
- [Wide Projects, 1531×1103](prototyping/correction-2/wide-projects-f57b136.jpg) — SHA-256 `a48da311750a400ec6706d1e1d0f79ccde8d59c83ef3a688cac4d8df279f27f6`.
- [Mobile Projects, 320×900](prototyping/correction-2/mobile-320-projects-f57b136.jpg) — SHA-256 `2aec5adaa78a35e21c652668377db2b400894a39c98a5df3beecdb24b4e40b46`.

### Verification

- `python3 -m unittest discover -s cargento/skills/cargento/tests -t . -p 'test_next*.py'`: 222 tests passed.
- Focused Ruff check and format check passed for the changed Next test modules.
- `python3 scripts/lint_embedded.py`: frontend assets clean.
- `git diff --check`: clean before each accepted checkpoint.
- Browser proof at both widths: no horizontal overflow; two Copy ID buttons,
  no nested interactive controls, zero mobile history operational facts, and
  zero history assignments.

### Summary

Correction round 2 closes the remaining identity-boundary blocker and the
responsive/history evidence defects found during capture review. Sessions now
remain collision-safe from fleet row to ask ownership and detail navigation,
history is observational, Projects reserve operational claims for active
evidence, and the accessible copy control replaces visible raw identifiers.
