# Plan prompt: finish the milestone "Hold it to what I asked"

Paste this whole file back into a session to run the plan. Fill in **Your answers** first. The rest
is written to be trusted over a fresh session's memory: every fact below was measured in the tree or
read from Linear on 2026-09-10, and the traps were paid for once already.

Work in `/Users/jaredmscott/repos/recce/cargento/.claude/worktrees/hold-it-to-what-i-asked`, on
branch `feat/hold-it-to-what-i-asked`, PR #317 against `main`.

---

## Your answers

Nothing in Stage 0 runs until these are filled. Stage 1 and Track P do not wait on them.

**A1. The DEC-18 amendment.** Do DEC-18's four preconditions gate DRC-4541's *build*, or only the
automatic switch's *default*?

> ANSWER: they gate the default only

If they gate the default only, DRC-4541 ships off by default with delivery recorded on macOS and
honestly reported as no lane available elsewhere, and DRC-4328, DRC-4034 and DRC-4032 become
follow-ups that widen the lane. If they gate the build, those three land first and the milestone
grows by roughly 35 hours. Record the ruling on DRC-4534 as an amendment either way, because DEC-18
is a closed decision and this changes what it requires.

**A2. Final eligibility, DRC-4512's first open question.** Which observed end evidence authorises a
final reading, per harness?

> ANSWER: We need to investigate this, I do not know. For now, we only care about Claude Code and Codex. ignore others

**A3. The interim reading, DRC-4512's second open question.** Does an ending with no supported end
evidence offer a reader-requested interim reading, scoped explicitly as provisional, or withhold?

> ANSWER: withold, because the interim reading is only for supported end evidence. If there is no supported end evidence, we cannot provide a reliable reading.

**A4. History disabled, DRC-4512's third open question.** What does a reader see where history is
off and nothing can be retained?

> ANSWER: A note that history is off and nothing can be retained. The reader cannot see any past sessions or annotations, and the system should clearly indicate that history is disabled.

**A5. Merge point.** Does #317 merge at the end of Stage 4, or stay held open?

> ANSWER: stay held open

Holding it open freezes `cargento_runtime/web/` project-wide for the duration, because AGENTS.md
permits exactly one PR at a time on that directory.

**A6. The abstention corpus.** DEC-17 requires recorded sessions across two harnesses, marked by a
second person, and you are the second person. Say when those marks will exist.

> ANSWER: Remove requirement for a second person to mark the sessions. I will mark the sessions myself, and they will be available by 2026-09-15.

Until they do, `annotations.ABSTENTION_CHECK` stays at `not-run`, the `Ask for a reading` control
ships disabled, and the milestone's promise is not kept by anything Stages 2 and 3 build.

---

## The goal

Complete the milestone. Steps 1 and 2 of its journey ship in #317 already. Step 3, a reading of how
the work measures up, and step 4, a departure raised while the reader is away, do not exist because
nothing produces a reading.

## Verified state, 2026-09-10

PR #317: base `main`, `mergeStateStatus` CLEAN, +8488/-140 across 48 files, 56 commits, 12/12 CI on
`6e46515`, suite 2826 green, working tree clean.

The milestone holds **13** issues, not the six its description lists.

| State | Issues |
| -- | -- |
| Done | DRC-4510 (DEC-15), DRC-4513 (DEC-16), DRC-4532 (DEC-17), DRC-4534 (DEC-18) |
| Ready for Review, complete in #317 | DRC-4508, DRC-4509 |
| Ready for Review, surface only | DRC-4511, DRC-4512 |
| Backlog | DRC-4533, DRC-4514, DRC-4540, DRC-4541, DRC-4542 |

Linear reports the milestone at 38.46 percent, which is 5 of 13. Four issues are completed. The
discrepancy was not resolved and nothing here depends on it.

### What "surface only" means, exactly

Not "no producer exists". The rendering path is unreachable:

- `annotations.published()` emits no `assessment` key. `annotations.Annotation` has no such field.
- `next-cockpit.js:1388` reads `annotation.assessment`, and `nextCockpitReadingShape` expects
  `{criteria: {goal, output}, revision_read, stamp, cutoff}`. About 120 lines across six functions
  are reached only by seven fixture sites.
- There is no `/api/reading` POST route. The POST inventory is `/api/annotate`, `/api/answer`,
  `/api/ask`, `/api/ask/withdraw`, `/api/dismiss`, `/api/events/`, `/api/focus`,
  `/api/interaction/`, `/api/notify`, `/api/shutdown`, `/api/usage`.
- There is no `reading-ask` dispatch arm. `ReadingControlIsWiredTest` at `test_contracts.py:709`
  holds that a rendered action with no dispatch arm may not become reachable.
- `annotations.ABSTENTION_CHECK` is `ABSTENTION_CHECK_NOT_RUN` at `annotations.py:74`, published to
  the page as `reading_check` at `aggregate.py:778`, and the control reads that rather than a
  constant.

### The dependency chain that decides the shape

- DRC-4511 blockedBy DRC-4509 (same PR, clean up the relation at reconcile).
- DRC-4541 blockedBy DRC-4328, DRC-4034, DRC-4540, DRC-4511, DRC-4032. Three of those are in the
  *Spend attention well* milestone.
- DRC-4514 blockedBy DRC-4540, DRC-4541, DRC-4511.

### DRC-4533 is closable, after a verification pass

Nine items. Three were checked directly against the tree on 2026-09-10 and are fixed:

1. The hardcoded `actor_claim` is now `_observer_actor_claim(observer_row.get("goal_source"))` at
   `project_context.py:2216`.
2. `_attach_annotations` at `aggregate.py:528` carries the `resume_id is None` arm plus the
   `DISPLAY_ID_FLOOR` test, so a Claude row from the task store no longer claims exact binding.
3. The cached sidecar type-checks and caps `deterministic_goal` at `project_context.py:361`, and
   `stage`, `block` and `reason` beside it.

Six more are recorded as done or refuted in `docs/plans/hold-it-to-what-i-asked-burndown.md`:
newlines (product call made, single-line on a security argument), the read surface (the Intent
log), the off-switch absence reason (refuted), `save()`'s failure arm and the `persisted: false`
reply, dead `holds()` (deleted), and SECURITY.md naming the semantic work-history store. **Verify
those six against the tree before closing.** A plan file is my own writing, and this repository has
a recorded case of comments claiming tests exist that did not.

## Rulings and traps already paid for. Do not re-derive these

- **`READABLE_VERSIONS = (1, SCHEMA_VERSION)` at `history.py:73` re-arms a hazard.** Bumping
  `SCHEMA_VERSION` from 2 to 3 makes it `(1, 3)`, which refuses every v2 store. Write
  `(1, 2, SCHEMA_VERSION)`. A test pins the current pair so it will not pass silently, and the
  obvious repair is the bug.
- **`nextCockpitAnnotation`'s field list at `next-cockpit.js:58` is a three-defect site.** Three
  separate defects have landed there, all of them the page reading a field nothing publishes.
- **A reading costs the reader's own quota.** `observer.CodexGoalModel` at `observer.py:162` is the
  pattern to follow: a `codex` subprocess at `OBSERVER_MODEL_REASONING_EFFORT` against DEC-14
  capacity. DRC-4541 warns that a state-change-driven evaluator multiplies this, and says to measure
  the real rate on a real board before choosing a cap.
- **`--observer-model` exists.** It is at `cli.py:200` and reached `main` with #312. DRC-4511's
  design reference says it does not exist on main, and that sentence is now stale.
- **The abstention check and DRC-4542's case set are two corpora, not one.** DEC-17's check takes
  recorded sessions marked by a second person; DRC-4542 admits synthesised cases under cross-agent
  verification, where a case whose generator and verifier are the same agent is not admitted.
  Sharing one corpus would let a synthesised fixture satisfy a gate written for recorded sessions.
- **DRC-4542's cases stay local and uncommitted.** Only expectations and results are committed.
  `records.safe_text` redaction applies, and it redacts before it clips.
- **The baseline-conflict block detects a later direction and refuses to say whether it conflicts.**
  A semantic conflict needs a reading, which DEC-15 refused. Recorded under DEC-16 in
  `docs/design-reading-a-session.md`.
- **The Intent log reads the annotation store and never session history.** `clear()` removes an
  entry; a history observation is never retro-deleted, so a history-backed log would republish words
  the reader withdrew.
- **The two annotation fields are single-line on a security argument.** Admitting newlines relaxes
  the control-character scrub that stops a pasted PEM body surviving.
- **DEC-4 caps an off-machine payload at counts and states only.** Never a session name, project,
  title, path or request text. On the machine a departure notification may name the session; off it,
  the most it may carry is that a count changed.
- **A green test may never have run.** Mutation SURVIVED twice on this branch because a test landed
  in a class without its fixtures. Print where a test landed before trusting a green run.

---

## Stage 0. Gates, and none of it is code

Runs once the answers above exist.

1. Record the A1 ruling as an amendment on DRC-4534, and correct DRC-4541's `blockedBy` to match.
2. Write A2, A3 and A4 into DRC-4512 under `## Decided before building`, and take the matching
   entries out of its `## Open questions`.
3. Verify the design project still reads. The tool is DesignSync, deferred, so load it with
   ToolSearch first, then `list_files` with projectId `241b0179-ac55-471c-a6cc-dc13b0bf7235` before
   any `get_file`. A refusal needs the operator to run `/design-login` in their own session, which a
   dispatched agent cannot do. Discovering that mid-build wastes the branch. DRC-4511 and DRC-4512
   both carry a `## Design reference` with a fenced prompt written to be pasted on its own; hand it
   over verbatim rather than summarising it.
4. Move DRC-4511 and DRC-4512 to `In Progress`.

## Track P. Starts immediately, blocks nothing, longest lead in the milestone

Both corpora need a build that can type a Goal, which exists only on this branch, so run the
dashboard from this worktree and record which build produced each session. Never on the operator's
own port, and stop every server and session you start.

- **DRC-4542's case set and rubric.** Five DEC-15 kinds across Claude and Codex: supported
  departures, legitimate changes of direction, matching intent with incorrect execution, misleading
  completion claims, insufficient evidence. Expectations written before any producer runs, by
  someone other than the prompt's author. Extraction and judgement scored separately. False
  reassurance is a first-class failure alongside false alarms and missed departures. Record which
  agent generated each synthesised case and which verified it.
- **DEC-17's abstention corpus.** Recorded sessions only, one binary mark per constraint, marked by
  the captain. This is what flips `ABSTENTION_CHECK`.
- **DRC-4508's resume-capture criterion.** Capture work rather than code: live Claude and Codex
  sessions resumed and observed.

## Stage 1. DRC-4533, in #317

Verify all nine items against the tree, then close with a step 4 receipt comment. An issue moved to
Done with no receipt is invisible to the next pick filter permanently. About an hour.

## Stage 2. The producer, DRC-4511, in #317

Strict internal order. Each step is a commit.

1. **The producer and its handler.** Built *around* DEC-17's rules 3, 4 and 7 rather than checked
   against them afterwards. Three outputs must be unrenderable rather than rare: the word "met", a
   departure citing nothing, and a deliverable claim on a harness that publishes no work evidence.
   An Expected Output criterion whose every cited entry is assistant-authored returns
   `not verifiable from available evidence`. An unresolved baseline conflict never becomes an
   agent-drift verdict.
2. **The route and the dispatch arm.** A POST route beside the existing eleven, same-origin, 503
   under `--no-annotations`, and a `reading-ask` arm so `ReadingControlIsWiredTest` is satisfied by
   wiring rather than by the control staying disabled.
3. **Publish it.** `annotations.published()` emits `assessment`, and `annotations.Annotation` gains
   the field. Check `nextCockpitAnnotation`'s field list at `next-cockpit.js:58` in the same commit.
4. **Re-derive the fixture-only assertions.** About 120 lines of renderer are exercised by seven
   fixture sites today. Rewrite those assertions against the published field, and delete the comment
   at `next-cockpit.js:1261` that says nothing publishes one.

## Stage 3. DRC-4512's persistence, in #317

1. Five `assessment_*` fields, each with its own named DEC-13 admission in `PROMPT_TEXT_ALLOWLIST`,
   an entry in `PROMPT_DERIVED_CARRIERS` at `history.py:150`, a matching SECURITY.md entry,
   redaction before bounding, and deletion by the existing `--forget` path. No new store: DEC-15b
   refuses one.
2. `history.SCHEMA_VERSION` 2 to 3, and `READABLE_VERSIONS = (1, 2, SCHEMA_VERSION)`. Append, never
   replace.
3. The revision disclosure inside the reading block, labelled with the revision number and the time
   it was typed, showing that revision's goal and expected output verbatim. DRC-4511 and DRC-4512
   share it rather than each building one.
4. A2, A3 and A4 implemented as ruled.

## Stage 4. One closing pass on #317

1. Recompute all three byte-pin oracles from the assets, never from a test file:
   `tests/test_next_page.py` holds per-part sizes and digests plus the assembled page,
   `tests/test_next_flag.py` holds the assembled length and digest, `tests/test_focus.py` holds a
   digest of the assembled page. Two assertions pin the assembled length and three pin its digest.
   A working script that reads from `cargento_runtime.web.page` was written this session at
   `<scratchpad>/repin.py`; re-create it from the module if the scratchpad is gone.
2. The full pre-PR suite from AGENTS.md, run from there rather than from a copy. Append
   `/opt/homebrew/bin` to PATH to reach node; prepending swaps `python3` off pyenv and three test
   modules fail to import.
3. Invoke the `sync-docs` skill. If it changes a file, run the suite again: `SKILL.md`,
   `SECURITY.md` and `README.md` are all asserted by `test_documentation`.
4. Invoke `visual-review-and-fix` in Mode 2, walking the **enabled** state behind a local
   uncommitted flip of `ABSTENTION_CHECK`. Mode 2 cannot walk a disabled control, and this branch's
   record is five defects found by looking at the board and none by CI. Never review on the
   operator's own port.
5. Every fix gets a test that fails on the mutation, restored by file copy rather than by
   `git checkout --`.

## Stage 5. Merge and reconcile

Per A5. Then the full six-part step 4 of the `burndown` skill:

1. DRC-4508, DRC-4509, DRC-4511, DRC-4512 and DRC-4533 to Done, each with a receipt comment.
2. Invoke `sync-project` for the milestone and the project overview. The milestone's `What is left`
   loses the closed rows, and it currently omits DRC-4533 entirely.
3. `## Read before building` bullets keyed by ID on the milestone of whoever must read them, and
   delete any bullet whose ID has reached Done.
4. Sweep `blocks` and move anything newly free to Todo. DRC-4511's `blockedBy` on DRC-4509 goes.
5. Replace a closed issue's live `blocks` edge with `relatedTo`, but only where the blocked side is
   still open.
6. **DRC-4023 (C4, My goals across sessions) is in the *Steer before waste* milestone and this
   branch shipped its user value.** The Intent log is "you can see each session's stated goal in one
   place". That reconcile lands on that milestone too. Decide there whether C4 narrows or closes.
7. Stamp `docs-synced-through` in `COMPATIBILITY.md` once from `main`, naming what the range covers.
   Never per branch: every parallel `sync-docs` wants to advance it and none can vouch for a
   sibling's work it never read.
8. Run the abstention check against Track P's corpus and flip `ABSTENTION_CHECK` if it passes.

## Stage 6. The away case, in a second PR

Order, and it does not vary: DRC-4540, then DRC-4541, then DRC-4514.

If A1 ruled that the preconditions gate the default only, DRC-4328, DRC-4034 and DRC-4032 are
follow-ups after DRC-4514. If it ruled they gate the build, they land before DRC-4541 and the
milestone grows accordingly.

**DRC-4328 cannot be verified on this desk.** Native notification backends for Linux and Windows,
on macOS, with CI that runs the unit suite on three platforms but cannot prove a notifier fired.
Say so in the report rather than absorbing it, and name the instrument that would settle it.

Three notes carried forward:

- DRC-4540 records one delivery outcome per raise, and the three states must stay distinct: a signal
  delivered, a signal attempted and failed, and a signal never attempted because no lane existed. A
  zero exit from `osascript` means the banner was handed to the OS, and the rendered string must say
  that rather than "you saw this". A raise with no record renders as unknown, never as undelivered.
- DRC-4541 raises only a departure, never a `consistent`. It evaluates on an observed state change
  rather than per turn, persists its annotation revision and evidence cutoff at raise time, caps per
  session and per day with exhaustion visible on the board, and holds under quiet hours. "Nothing
  departed" and "nothing was checked" must never render alike.
- DRC-4514 reuses the existing departure row rather than inventing a second treatment, and reaches
  for the Intent log before a sixth view. `Unknown` is a first-class third answer for what happened
  next, and the common one. A count explains nothing.

---

## The standard every stage is held to

- **A failing test first, and watch it fail.** Then break the source it defends and watch it go red.
  A mutation that comes back green means the test is wrong, not that the code is safe. Five such
  cases on this project were all real test defects.
- **Print where a test landed.** Two green tests on this branch never ran, both because a text
  anchor put them in a class without their fixtures.
- **Assert rendered text, not data shape.** Drive the assembled bundle. Name the test as a sentence
  about a person. Cover the absence, because that is where this product fails.
- **Review depth per PR, from AGENTS.md's Calibrating Effort table.** `cargento_runtime/web/` is a
  conflict-prone surface, so two lenses plus an arbiter that reproduces findings rather than ranking
  them. Review the diff in the worktree before opening or updating the PR.
- **Never promote a deferred finding into the PR in flight.** File it.
- **Multi-line commit messages use `git commit -F <file>`.** Sign off with `-s`. End the message
  with the attribution line the session is given.

## Hard rules

- Do not merge anything without an explicit instruction. A5 governs #317.
- Do not touch a version field. The Release workflow owns them and `version-guard` fails any PR that
  changes one.
- Do not weaken a validator rule to make an edit pass.
- Never emit a credential, in chat, a file, a commit message, a PR body or an issue comment.
- Say what you did not check. An unstated gap reads as a clean result.

## What to report at the end of each stage

The commit, what the suite said, which mutations were caught, what the walk saw on the screen quoted
verbatim, and what was filed rather than fixed.
