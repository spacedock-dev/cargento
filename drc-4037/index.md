---
id:
title: 'E4 · Ended with uncommitted work'
status: review
source: https://linear.app/recce/issue/DRC-4037
started: 2026-08-28T06:33:15Z
completed:
verdict:
score: 0.7
worktree: .worktrees/spacedock-ensign-drc-4037
issue:
pr: "#239"
mod-block:
linear-status: Todo
milestone: 'Nothing dies quietly'
release: 'r2'
estimate: 'L'
reconciled:
gates:
    version: 1
    records:
        - id: gate:drc-4037:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4037-triage-1
              briefing:
                id: briefing:drc-4037:triage:attempt-1:revision-1
                digest: sha256:b0573609f358b0e07223f3956f435d6ce07c889744872eda02f74fbbd03a81f5
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4037:triage:1
                briefing: briefing:drc-4037:triage:attempt-1:revision-1
                by: person:captain
                at: "2026-08-28T06:50:44.588862Z"
                decision: approve
                reason: 'APPROVED, all three asks. (1) The delivery SPLIT is approved: a documentation-only groundwork issue delivering docs/plans/git-probe-security-scope.md, with E4 blocked on it, following DRC-4061 and DRC-4177 — a precedent verified at both ends by commit rather than by resemblance (plan doc added in its own PR 7134a01 #71 and 5ede7d1 #143, then promoted into SECURITY.md and deleted by the implementation PR a98bc64 and 3e92d12). (2) TWO OF THE FOUR BOUNDS RULED ON 2026-08-28 ARE AMENDED, each because triage measured that the bound as written cannot deliver its own intent. BOUND 3 is amended from finished_at to session_ended: finished_at is a turn-stop stamp written by _mark_finished on every idle overlay and popped on every working overlay (observation.py:354-376 and 360-362), so a probe hung there fires once per turn stop — forty turns, forty subprocesses inside the user repository — which is a poll with extra steps and the exact thing bound 3 exists to forbid. The bound property (one-shot, at session end) is unchanged; only the artifact that delivers it is corrected. BOUND 2 is amended from a non-nullable {dirty: bool, changed: int} to {dirty: bool | None, changed: int | None}, None meaning not probed: six of ten harnesses have no event adapter and can never emit session_ended, and with --no-git, a non-repository directory and git absent from PATH, most rows will never be probed, so a non-nullable flag publishes a confident false over no evidence. The captain was told explicitly that this one is a judgement rather than a correction of fact — that it departs from the ruling literal words to serve its intent, and that the alternative reading, in which a fixed two-scalar surface is part of what made option B stoppable, is defensible — and ruled to amend. The precedent cited is the product own: finished_at None means no stop observed and never did not finish, and acquisition exists to disclose unknowability rather than hide it. (3) E4 own sentence that a PR carrying both the amendment and the runtime change does not satisfy it is STRUCK: it is absent from DEC-3 outcome and forbids exactly what DEC-1 and DEC-2 implementation PRs did. Evidence quality noted: the two hazard flags are now independently load-bearing across four fresh probe repositories, stronger than DEC-3 record, so neither may be dropped; and one DEC-3 figure did not reproduce and must not be repeated in the amendment — the fsmonitor script ran once, not twice, at git 2.55.0, with the security consequence unchanged. SCOPE: drafted writes A, B and C only. A dated correction note on the closed DRC-4122 recording these two bound amendments was NOT authorized and is being put to the captain separately.'
              application:
                target-stage: implementation
                state: consumed
            - id: gate-attempt:drc-4037-triage-2
              briefing:
                id: briefing:drc-4037:triage:attempt-2:revision-1
                digest: sha256:27b67a3571132db058138a8279f2fc13f56b8d8a56a3dc1701cead4c793bf8c6
                room-ref: ./review/triage/briefing-2
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4037:triage:2
                briefing: briefing:drc-4037:triage:attempt-2:revision-1
                by: person:captain
                at: "2026-08-28T09:55:46.064321Z"
                decision: approve
                reason: |-
                    APPROVED, all four asks.

                    (1) THE SHAPE: two PRs, split on cargento_runtime/web/ and nothing else. PR 1 carries the SECURITY.md promotion, the two intro amendments, the deletion of the plan document, the probe module and its session_ended wiring, the --no-git switch, the published dirty and changed fields, and the doc updates. PR 2 carries the render and the two byte-pin oracle sets. Both belong to E4 and the issue is not Done until PR 2 lands; no second issue is filed, because the render carries no decision content of its own. The split is justified by measured contention rather than by preference: the PR queue is clear of web/, but two live sibling worktrees already carry web diffs against origin/main at 76 and 30 files, E4 would be the third writer into a surface holding 56 pinned figures with no script that emits them, and a recompute forced by a sibling merge would land after review and make the expensive pass re-verify a diff it had already cleared. The promotion constraint is not broken: PR 1 ships both things the promoted section describes, so SECURITY.md is true at every commit and the plan document dies in the same commit that promotes it.

                    (2) THE REVIEW TIERS, and they override nothing. Reading the AGENTS.md table literally gives a different row per PR, which is what pick-per-PR-not-per-session asks for. PR 1 takes full adversarial — several lenses, a completeness critic, an arbiter — because it runs a subprocess inside a directory the user chose, promotes a contract and amends an invariant. PR 2 takes two lenses plus an arbiter under the conflict-prone-surface row. The captain's earlier reduction to two lenses is explicitly NOT extended: it applied to a documentation-only issue that described a future handler, and PR 1 is the handler.

                    (3) THE CORRECTIONS: the three drafted corrections to E4's own body and the one to its milestone are authorized as drafted.

                    (4) THE DRC-4122 CORRECTION NOTE IS AUTHORIZED. One appended dated note on the closed decision issue, recording that its amendment section carries the wrong predicate. The existing text is not edited. Reason for authorizing what was declined last time: that section is the source others copy from, the wrong predicate has now propagated into two downstream documents, and each propagation was caught by a worker rather than by a reader.

                    Evidence quality noted, including against the FO. This stage refuted the FO's own figure: the six --no-spacedock sites in E4's body reproduce, enumerated across cli.py twice, config.py three times and lifecycle.py once with --no-usage occupying the identical six as an independent check, and it was the groundwork cycle's three that was the miscount. On the other defect it found the root cause rather than the error alone — the six-of-ten-harnesses sentence was carried over from observation.finished_at's docstring where six is correct for a different question — and drafted a property rather than a count because Droid and Goose emit SessionEnd natively and are unreachable only for want of an adapter. Two build-shaping constraints absent from the merged contract were found by reading the tip: the session-end edge runs on the HTTP handler thread under the coordinator lock behind a two-second client timeout, and session_ended mints no overlay so the result has no carrier. One cycle-1 acceptance criterion was found unsound rather than merely incomplete and was rewritten.
              application:
                target-stage: implementation
                state: consumed
---


[DRC-4037](https://linear.app/recce/issue/DRC-4037) — Linear priority Urgent, estimate L.
Triage run 2026-08-28 against `main` at `ef425b2` (**v0.18.0**, not v0.17.1 — see Re-derivations).

## Problem

A session ends and leaves a dirty worktree nobody goes back to. That is how agent work actually
gets lost — quietly, in a checkout, with no failure anywhere to look at. Cargento watches the
sessions and says nothing about the tree they left behind.

DEC-3 ([DRC-4122](https://linear.app/recce/issue/DRC-4122)) ruled on 2026-08-28 that Cargento may
look, on **option B, straight**: run a bounded `git status` inside the session's working repository
at the end of the session, and publish whether the tree is dirty and how many entries changed.
Nothing else. Four bounds are part of that ruling.

The work left is a policy artifact and a bounded probe, in that order.

## Proposed approach

**Recommendation: split, following the precedent. File a groundwork issue, block E4 on it, build
E4 second.**

The groundwork issue's whole deliverable is `docs/plans/git-probe-security-scope.md`, holding the
`SECURITY.md` section text verbatim. E4's implementation PR then promotes that text into
`SECURITY.md` unchanged and deletes the plan doc.

Why that shape and not a standalone `SECURITY.md` PR:

- **It is what the precedent actually did, at both ends, twice.** `DRC-4061` (DEC-1) and `DRC-4177`
  (DEC-2) are both documentation-only issues delivering a `docs/plans/*-security-scope.md` file in
  its own PR (#71 `7134a01`, #143 `5ede7d1`), promoted and deleted by the implementation PR
  (`a98bc64` and `3e92d12` each show `SECURITY.md` grown and the plan doc deleted in one commit).
  Both are `Done`.
- **`SECURITY.md` describes only shipped behaviour at every commit.** `DRC-4177` states that as the
  reason for the shape. A standalone `SECURITY.md` PR breaks it: between the two merges the file
  documents a probe that does not exist, and any release tag cut in that window ships a security
  document that lies about the product. Releases here are tag-driven off `main`, so that window is
  real rather than theoretical.
- **It gets the thing DEC-3 actually wanted.** The ruling's purpose is that the contract is settled
  and reviewed before anyone writes the code — "its own cycle and its own PR". The plan-doc PR is
  its own cycle and its own PR.

**One conflict the gate has to rule on.** DRC-4037's own 2026-08-28 re-scope adds a sentence that is
not in DEC-3's outcome text: *"A PR whose diff carries both the amendment and the runtime change does
not satisfy it."* Under the precedent, the implementation PR **does** carry both — that is exactly
what `a98bc64` and `3e92d12` do. DEC-3 itself says only "as DEC-1's did", and DEC-1's did this. So
the sentence and the precedent it invokes cannot both be honoured. Recommend the precedent, and
delete that sentence from the rewritten body; the gate may instead keep the sentence and accept a
window where `SECURITY.md` is untrue.

**Rejected alternative — one issue, amendment and code in one cycle.** Simplest, one CI cycle
instead of two, no cross-issue dependency. It cannot deliver the value because the value DEC-3
bought is a security contract reviewed on its own merits before an implementation exists to argue
from. Reviewing both together is how the Spacedock frontmatter carve-out shipped (`0a73535`), and
correcting that is why DEC-3 was filed.

### The build, once the contract is merged

Fire the probe from the event coordinator on the **`session_ended`** edge, using the absolute path
the event already carries. Parse porcelain into two scalars. Publish them. Gate on `--no-git`.

## Re-derived at the tip (2026-08-28, `ef425b2`, v0.18.0)

Nothing below is accepted from the issue body, which was last substantively written 2026-08-09 and
re-scoped 2026-08-28. Five claims were re-measured; two did not survive, one is refined, two hold.

### 1. The absolute working directory — HOLDS as a fact, REFUTED as a cost

The issue says the absolute `cwd` "is parsed by nine collectors and immediately reduced" and that
E4 "has to re-derive and hold the absolute path, which is a small new retention". The first half is
right; the second is wrong, and this was the question that decided whether the build is possible.

- `sessions.project_from_cwd` (`sessions.py:42-91`) reduces an absolute path to its last two
  segments. Every collector calls it with a local variable and keeps nothing (`collectors/claude.py:522`,
  `codex.py:235`, `gemini.py:109`, `droid.py:54`, `pi.py:561`, `copilot.py:515`, `cursor.py:744`,
  `goose.py:168`). No session row carries an absolute path.
- **But the probe does not need a collector.** `Event.cwd` (`events.py:167`) is the absolute path,
  allowlisted at `events.py:89`, parsed at `events.py:386`, bounded at `MAX_PATH_LEN = 4096`
  (`events.py:125`) — and it has no consumer. `event_hook.py:282` forwards it from every harness
  payload.
- **A real `SessionEnd` payload carries it.** `docs/captures/claude/hooks-2.1.222-macos.jsonl`
  records `"event":"SessionEnd"` with `keys` including `"cwd"`; so does
  `docs/captures/droid/notification-0.202.0-macos.jsonl`. This is measured payload, not desk
  research.
- `_text` (`events.py:210-224`) **drops** an oversized value rather than truncating it, so
  `Event.cwd` is either a complete absolute path or `None`. There is no half-path that would send
  `git -C` at a parent directory.

**Consequence:** running the probe inside the event coordinator on the event that carries the path
costs **zero new retention**. The issue's second correction should be struck rather than built to.

### 2. Bound 3's named artifact is the wrong one — REFUTED

Bound 3 says the probe "fires on the completion stamp E2 already ships". That stamp is `finished_at`
(`sessions.py:311-318`), and it is a **turn-stop** stamp, not a session-end stamp:

- It is written by `observation._mark_finished` (`observation.py:354-376`) on an `OVERLAY_IDLE`
  overlay, which is what `turn_stopped` maps to (`events.py:460-468`).
- It is **popped** on `OVERLAY_WORKING` / `OVERLAY_NEEDS_INPUT` (`observation.py:360-362`), so it
  re-arms on every turn. A probe hung there runs once per turn stop — forty turns, forty
  subprocesses inside the user's repository. That is a poll with extra steps, and it is the exact
  thing bound 3 exists to forbid.
- The consumption side has no edge at all: `aggregate._apply_overlays` (`aggregate.py:704-738`) and
  `events.reduce_overlays` (`events.py:509`) recompute from scratch every collection pass.
- The genuine one-shot edge is **`session_ended`** (`events.py:66`), dispatched at
  `observation.py:304-308` through `retires_overlays` (`events.py:491`). It is deliberately
  *excluded* from `_mark_finished` by the `elif` at `observation.py:309` — E2 had to work around it
  because it pops the ledger whole.

**Consequence:** build to `session_ended`, and say so in the rewrite. Bound 3's *property*
(one-shot, at session end) is right; the artifact it names cannot deliver it.

### 3. The two hazard flags — BOTH REPRODUCE, and each is independently load-bearing

Re-measured on this machine at **git 2.55.0**, four fresh probe repositories, one probe each, from
an identical racy-clean state (`git init`, one commit, `touch`):

| Invocation | `.git/index` rewritten | `core.fsmonitor` script runs |
| --- | --- | --- |
| `git status --porcelain` | **YES** | **1** |
| `git --no-optional-locks status --porcelain` | no | **1** |
| `git -c core.fsmonitor= status --porcelain` | **YES** | 0 |
| `git -c core.fsmonitor= --no-optional-locks status --porcelain` | no | 0 |

Each flag disarms exactly one hazard and neither disarms the other's, so bound 1 cannot be
satisfied by either flag alone. This is stronger than DEC-3's record, which measured the two
hazards separately.

**One discrepancy.** DEC-3 recorded the `core.fsmonitor` script executing **twice in one
invocation**. At git 2.55.0 it executed **once**. The security consequence is unchanged — a repo-local
`.git/config` gets arbitrary code executed under Cargento's identity — but the "twice" figure should
not be repeated in the amendment. Report it as one.

A second refinement: the index rewrite is **race resolution**, not an unconditional per-invocation
write. On an already-settled index, repeated plain `git status --porcelain` did not rewrite it. It
fires whenever a file's mtime is inside the racy window — which, in a repository a live agent
session is editing, is the normal case rather than the corner case. The hazard stands; the wording
"advanced `.git/index`'s mtime on a clean repository" reads as unconditional and is not.

### 4. `changed: int` counts porcelain entries, not files — NEW

Measured: a tree with one modified file and five untracked files inside a new directory produces
**two** porcelain lines (` M a.txt`, `?? newdir/`) — git collapses an untracked directory to one
entry under default `-unormal`. So `changed` is "porcelain entries", and a UI label reading
"6 files uncommitted" would be false by an unbounded factor. Name the unit in the surface, in the
amendment, and in whatever the frontend renders.

### 5. The published surface — HOLDS, and is cheaper than expected

- One declaration site: `sessions.base_session` (`sessions.py:207`, keys at `sessions.py:263-347`),
  which every collector starts from.
- There is **no publish-side allowlist**: `aggregate.collect_json` (`aggregate.py:857-878`) does
  `json.dumps(self.collect(...))` on the whole dict. Two new keys reach `/api/data` by being
  declared, and nothing else must change.
- The key set is pinned by `tests/test_sessions.py:338`
  (`test_every_session_row_declares_the_same_field_set`), against a hand-written
  `DECLARED_SESSION_FIELDS` at `tests/test_sessions.py:304-336` — deliberately not derived from
  `base_session`, so the two cannot move together. That test is the designated place to say so.
- Snapshot revision needs nothing: `snapshot.py:49-52` publishes opaque bytes with a
  `(server_started, counter)` revision and no schema version.

### 6. Bound 2 cannot express "not probed" — NEW, and it needs a ruling

Bound 2 fixes the surface at `{dirty: bool, changed: int}`. Six of the ten harnesses have no event
adapter and can never emit `session_ended` (`aggregate._mark_unreachable_by_events`,
`aggregate.py:685-703`, marks them `acquisition: "scan-only"`). Add `--no-git`, a directory that is
not a repository, and git absent from `PATH`, and **most rows will never be probed**. A non-nullable
`dirty: bool` publishes `false` for all of them — a confident "clean" over no evidence at all.

The product already has the right precedent and states it explicitly: `finished_at: None` means
"no stop observed" and *never* "did not finish" (`sessions.py:311-318`), and `acquisition` exists to
disclose unknowability rather than hide it. Recommend reading bound 2 as
`{dirty: bool | None, changed: int | None}`, `None` meaning not probed. **The gate should rule on
this**, because it is a literal departure from the ruling's words in service of the ruling's intent.

### 7. Two stale references, minor

- The dispatch and the burndown notes say `main` is at **v0.17.1**. It is at **v0.18.0** (`ef425b2`).
  The `SECURITY.md:62-65` line citation, already corrected once to the **Scope** section name, is
  another reason to keep citing section names.
- `AGENTS.md`'s Parallel Work applies: five worktrees are live on this repository right now
  (`git worktree list`). No test was run for this stage, so no red was interpreted.

## Linear edits made

**Nothing has been written to Linear. This section is the pre-edit record plus the drafts the gate
authorizes.** Captured 2026-08-28 from the live API.

- Issue `DRC-4037`, `updatedAt: 2026-08-28T06:21:20.501Z`, status `Todo`, `blockedBy: []`,
  `relatedTo: [DRC-4122, DRC-4038]`.
- Milestone `Nothing dies quietly`, id `59f12a37-c757-4074-b734-3d87df40801f`, progress 16.

### Pre-edit record A — DRC-4037 issue body, verbatim

```markdown
Board item **E4** from the Visibility 2x2 board (`docs/visibility-2x2/items.json`).

**Outcome:** the work does not evaporate
**Outcome group:** Nothing dies quietly (close the loop)
**Journey stage:** End of sessions · **Release row:** Release 2 · **Kind:** information
**State:** Not yet — Needs a new source or a new power

## Scores (blind-panel medians)

*Legend: Access = how hard this is to get WITHOUT Cargento today — higher = harder = more differentiated. Build = engineering effort, 0–100. Detector risk = points docked from impact for heuristic uncertainty. This issue's priority derives from risk-adjusted impact; its estimate derives from build.*

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 80 | 74 | 70 | 45 | 6 |

*Quadrant: differentiated · score confidence: high · panel median of 3 blind lenses; boundary audit, promote, strong*

## Board note

This is how agent work actually gets lost. Not dramatically, but in a dirty worktree nobody went back to. Cargento already knows every session's working directory, which is the hard half of the problem.

## What it needs

Bigger than I first called it. I described this as a smaller policy question than DEC-1, and that was wrong. SECURITY.md treats file reads outside the documented store paths as a security bug, with one narrow and heavily guarded exception for Spacedock frontmatter. Reading git state inside a user's repository is a third amendment, and arguably more invasive than fetching a quota number, because it touches their code rather than their account.

## Dependencies and overlaps

* **Preferred over:** E5
* **Cheaper route:** Narrower than E5 and scores higher, so it is the version to build.

---

## Audited 2026-08-09 — the gate this describes now exists as an issue

Verified unshipped and unchanged. Searching the runtime for `subprocess`, git invocation or repository reads finds only `osascript` (the macOS notifier) and the daemon spawn. Nothing reads a working tree, and no code path is close to it.

The finding is structural rather than technical. This issue's own "What it needs" paragraph describes a policy amendment — *"Reading git state inside a user's repository is a third amendment"* — and the **Scope** section of `SECURITY.md` confirms the premise, treating file reads outside the documented store paths as a security bug *(citation corrected 2026-08-28: this was written as* `SECURITY.md:36-37`*, which had drifted to* `SECURITY.md:62-65` *by v0.17.1 — the section name will not drift again)*. But **no decision issue existed, and this issue carried no blocking relation at all.** So the highest risk-adjusted score in its milestone, 74, has been reading as ready to build while resting on a call nobody had made.

[DRC-4122](<https://linear.app/recce/issue/DRC-4122/dec-3-decision-let-cargento-read-git-state-inside-your-repositories>) (DEC-3) now records that decision and blocks this issue, in the same shape DEC-1 and DEC-2 use. Its recommended direction is option B: read only what `git status --porcelain` reports, never file contents — which is the narrowest amendment that still answers this item.

Unchanged and still true: Cargento already records every session's working directory, which the board correctly calls the hard half. What is left is a policy call and a bounded read, in that order.

---

## Unblocked and re-scoped 2026-08-28 — DEC-3 landed on option B

[DRC-4122](<https://linear.app/recce/issue/DRC-4122/dec-3-decision-let-cargento-read-git-state-inside-your-repositories>) (DEC-3) was decided by the captain on 2026-08-28: **option B, straight**. Cargento may run `git status` inside a user's working repository and publish, per session, only whether the tree is dirty and how many entries changed. This issue is genuinely released — it is the only one of DEC-3's three dependents that is, and it moves to `Todo`.

The blocking relation is replaced by a related one. DEC-3 is closed, and a closed issue holding a live gate reads as a real blocker to everyone; the related edge keeps its evidence reachable from here.

### The four bounds this issue is now scoped to

They are part of the ruling rather than commentary, and each answers a hazard DEC-3's triage measured rather than argued. An implementation that misses any of them is out of scope, not merely imperfect.

1. The probe is `git -c core.fsmonitor= --no-optional-locks status --porcelain`, or there is no probe. Both flags were measured to matter: a plain `git status --porcelain` advanced `.git/index`'s mtime on a clean repository, and with a repo-local `core.fsmonitor` script set it executed that script twice in one invocation. A plain `git status` is not an acceptable implementation of this issue.
2. The published surface is exactly `{dirty: bool, changed: int}` per session, and nothing else. Porcelain emits pathnames; they are working data — matching hints, never echoed to `/api/data`, the wording `SECURITY.md` already uses for `cwd`. Publishing a pathname would be the first file-level identity on the surface, and this issue does not need one.
3. The probe is **one-shot at end of session, not a poll.** This item asks about a session that *ended*, so it fires on the completion stamp E2 already ships. That is strictly narrower than option B as DEC-3 originally wrote it, and it removes both the cadence question and `index.lock` contention with the user's own git.
4. There is an off switch, on by default, matching `--no-spacedock` — the precedent set by the only other read exception.

### The amendment ships before the code, in its own PR

DEC-3's ruling puts the `SECURITY.md` amendment **before any code**, as DEC-1's was. That is a separate cycle and a separate PR, and it must state the bound, the published surface, what is never read, that the mechanism is subprocess execution rather than a file open (naming the two flags that make it non-writing and non-executing), the cadence bound, and the off switch. A PR whose diff carries both the amendment and the runtime change does not satisfy it.

### Two corrections to this issue's own text

* **"A third amendment" undercounts in one direction and overcounts in another.** On the file-read axis this is the **second** amendment, not the third: the first was the Spacedock frontmatter carve-out, which landed in `0a73535` (PR #10, 2026-07-27) with its `SECURITY.md` section in the same commit as its code and no decision issue at all. DEC-1 amended the *network* invariant, not this one. So this is also the first read-axis amendment ever put to a filed decision before the code.
* **"Cargento already records every session's working directory" is not quite what happens.** The absolute `cwd` is parsed by nine collectors and immediately reduced; what is retained and published is the last **two** path segments. `Event.cwd` is parsed and bounded but has no consumer. So this issue has to re-derive and hold the absolute path, which is a small new retention rather than a free read of something already held. It does not change the board's "hard half" claim — finding the path is still solved — but it is a line of work this issue did not previously name.

### Review depth

Per the **Calibrating Effort** table in `AGENTS.md`, this change is "security, credential handling, or data loss" and routes to **full adversarial review**: several lenses, a completeness critic, an arbiter. That is the most expensive tier the repository has, and DEC-3's gate named the cost before authorizing the work rather than discovering it afterwards.
```

### Pre-edit record B — milestone `Nothing dies quietly` description, verbatim

```markdown
Thematic grouping, not a delivery sequence — sequence by the release:* labels. Outcome group: close the loop. Finished, crashed, and abandoned all look the same from outside. Board items in this project: E2, E3, E4, E5, E6, E7 (E1 already shipped and is excluded).

## Update 2026-08-23 — E7 is still gated, but the reason changed twice and this group's record did not keep up

E7 is the only item here touching DEC-2, and DEC-2 moved twice since the sections below were written. Both left E7 blocked, so its state is unchanged and its *reason* is not. Correcting that here because the 2026-08-21 note below presents itself as the current status of whether the input power is allowed, and it stopped being current on 2026-08-22.

**DEC-2's refusal is now partial rather than total.** It was reopened and re-decided on 2026-08-22 after a survey of ACP, MCP, A2A and AG-UI. The input power is allowed in exactly one shape, where the session asks and Cargento answers, and refused in every other. ACP, AG-UI and A2A are refused as a standing answer, because each requires Cargento to own the session.

**That allowed shape has shipped**, as [DRC-4172](<https://linear.app/recce/issue/DRC-4172/let-a-session-ask-cargento-a-question-and-wait-for-the-answer-dec-2s>) in [spacedock-dev/cargento#144](<https://linear.app/recce/review/featskill-let-a-session-ask-cargento-a-question-and-wait-for-the-7be078bb146e>) on 2026-08-23. So Cargento can now put something into a running session's context. E7 still cannot use it, and the distinction is the whole point: the ask lane fires only when the session asks, and E7 is Cargento telling a session to write a hand-off when the wall is coming. Nothing about a shipped ask lane makes an unasked-for prompt allowed.

**Option E's premise was also corrected, without changing its refusal.** DEC-2 had said no harness offers a supported way to type into a running session. Claude Code does: a per-session inbox socket, documented, verified inside a live session's own environment. It is plain text only, rate limited, and cannot answer a permission prompt by design. E stands refused anyway, and DEC-2 records that the refusal now rests on the socket being known rather than assumed, which is a stronger place for it to rest. That socket is E7's shape, so this is the finding most likely to be misread as E7 becoming feasible. It did not.

**Option C is still neither chosen nor refused.** One narrow verb, ask this session for a hand-off summary. It remains the cheapest route to E7 and a separate small call, and the ask lane's shipping does not settle it, because C is Cargento-initiated and the lane is not.

**DEC-3 was decided on 2026-08-28, and E4 and E5 got different answers.** This line previously read "E4 and E5 are still blocked on DEC-3, which is still open and undecided", and that stopped being true on 2026-08-28.

[DRC-4122](<https://linear.app/recce/issue/DRC-4122/dec-3-decision-let-cargento-read-git-state-inside-your-repositories>) landed on **option B, straight**: Cargento may run a bounded `git status` probe inside a user's working repository and publish, per session, only whether the tree is dirty and how many entries changed. Four bounds are part of the ruling rather than commentary — a probe that neither writes nor executes repository-supplied code, a published surface of exactly a dirty flag and a changed count with pathnames kept as matching hints that are never echoed, one-shot at session end rather than a poll, and an off switch that is on by default. The `SECURITY.md` amendment lands before any code, as DEC-1's did, in its own PR.

[DRC-4037](<https://linear.app/recce/issue/DRC-4037/e4-ended-with-uncommitted-work>) (E4) is **released**, moved to `Todo` and re-scoped to those four bounds. [DRC-4038](<https://linear.app/recce/issue/DRC-4038/e5-branch-or-pr-left-behind>) (E5) is **not**. Its own body says it cannot ship on a DEC-3 that lands on option B or C, so closing DEC-3 would have released it onto an unfiled gate; it is re-gated instead on [DRC-4273](<https://linear.app/recce/issue/DRC-4273/dec-8-decision-may-cargento-make-an-authenticated-outbound-request-for>) (DEC-8), filed the same day for the authenticated outbound call E5 actually needs. A third item outside this group, C7, was cancelled rather than released: a porcelain status names which files changed and not what changed in them, and bound 2 makes it doubly unreachable.

---

## Update 2026-08-21 — the group's first two items shipped, and one of them is structural

**E6 is Done** ([spacedock-dev/cargento#135](<https://linear.app/recce/review/featdashboard-mark-a-session-handled-and-clear-it-off-the-board-drc-56ad712bcf29>)) and **E2 is Done** ([spacedock-dev/cargento#136](<https://linear.app/recce/review/featdashboard-tell-a-finished-session-from-one-still-waiting-drc-4035-2c9ca6ec9c7b>)). Both Release 1. This group was at 0% and is no longer.

### E6 mattered more than its score

At 42 risk-adjusted it was the lowest-scoring Release 1 item here. It was also the right one to build first, for the reason the 2026-08-09 note gave: it is the cheapest place to answer **where user state lives**, and three items outside this group were waiting on that answer.

`cargento_runtime/dismissals.py` is the product's **first user-owned persisted state**. Nothing user-authored had survived a run before. The decisions it sets, which C1, D9 and H1 now inherit rather than re-make, are recorded in `docs/design-dismissals.md` and in SECURITY.md, and the three inheriting issues each carry a comment naming what they get and what they still have to decide for themselves.

Three worth repeating here because they will be quoted at future issues:

* **Bounded by count, never by TTL.** A TTL adds no boundedness the cap does not, and it silently reverses the user's intent by re-showing a session that never came back.
* **The watermark is the server's clock; the request body carries no timestamp.** A client-supplied bound is the one input that could hide a row forever, and refusing it is what lets SECURITY.md state what a forged POST can achieve.
* **Degrade to nothing, never crash, and no optimistic client-side hide.** A row removed before the server agreed is a claim the board cannot back.

Two accepted exposures are documented rather than solved: concurrent dashboards resolve last-writer-wins on the whole file, and clearing an unanswered gate suppresses its desktop popup. The second is the point of the feature and the one thing here that can make a reader miss something.

### E2 had to be re-read before it could be built

**Its premise was dead.** The issue argues against the `stale` flag's gloss, and that flag was retired in v0.12.0 by [DRC-4162](<https://linear.app/recce/issue/DRC-4162/calm-mode-collapse-idle-sessions-by-default>) — four commits before the build started. `SKILL.md` now carries the opposite contract, with a live test asserting the word cannot reappear. So E2 shipped as a **new signal**, a word in the existing `idle / wait` cell, not a refinement of a chip that no longer exists.

The threshold is **1,200 seconds, measured**: 10,119 human returns to a stopped turn across 1,355 local transcripts, p50 106s, p75 312s, p90 966s, p95 2,427s. Marking on the stop itself was rejected because it restates Idle in a second vocabulary — the exact fault [DRC-4162](<https://linear.app/recce/issue/DRC-4162/calm-mode-collapse-idle-sessions-by-default>) retired the old chip for — and the dead 7,200s was rejected rather than reused: only 2.5% of returns land past it, so it would stay silent through the whole window in which collecting the finished work is still worth something.

The `session_ended` trap was real and is closed: that event **pops a session's whole overlay ledger**, and for a one-shot `claude -p` the stop and the exit arrive back to back, so a mark held in the ledger would die for exactly the sessions the item exists for. The mark lives outside the ledger but is fed **through** the reducer, which is what makes it inherit the [DRC-4101](<https://linear.app/recce/issue/DRC-4101/a-working-session-reads-idle-forever-once-turn-stopped-arrives-because>) activity guard. A mutation check proves it: removing the guard produced *"a session that worked again is not finished"*.

Also shipped: the six adapter-less harnesses (Pi, Copilot, OpenCode, Cursor, Goose, Droid) now **disclose that the answer is unknowable** through the previously unrendered `acquisition` channel, and a test forbids any collector from filling the completion stamp itself.

### What this changes for the rest of the group

* **E3 is cheaper, but not in the half that was hard.** E2 built one output of the classifier the two share, and E3 can reuse the stamp, the reducer route, the rendering slot and the threshold precedent. But E2 could ship because a *stop* is a positive signal, and death is the **absence** of one — which E2's own design forbids inferring. Recorded on the issue.
* **E4 and E5 are no longer both blocked, and they did not get the same answer.** Updated 2026-08-28; this bullet read "still blocked on DEC-3, which is still open and undecided". DEC-3 was decided on option B — see the DEC-3 note above. E4 is released to `Todo` and re-scoped to the ruling's four bounds. E5 is re-gated rather than released, on DEC-8, the decision filed that day for the authenticated outbound call, because option B is precisely the ruling E5's own body says it cannot ship on.
* **E7 is unchanged**, still blocked on DEC-2. Its option C — one narrow verb, ask this session for a hand-off summary — was neither chosen nor refused and remains a separate small call. *(Still true on 2026-08-23, though DEC-2's reasoning underneath it has changed twice: see the update above.)*

---

## Update 2026-08-21 (earlier) — DEC-2 has been decided, and E7 is still gated (HISTORICAL: superseded on whether the input power is allowed by the 2026-08-23 update above)

[DRC-4054](<https://linear.app/recce/issue/DRC-4054/dec-2-decision-let-cargento-act-not-just-observe>) was decided on 2026-08-21: **A now, B after one check, E refused.** Read the 2026-08-09 note below as still correct about *what* E7 needs, and this as the status of *whether it is allowed ***as of 2026-08-21 only**. DEC-2 was reopened and re-decided on 2026-08-22 and the three bullets below are stale in the ways the newest section names.

* **E7 remains blocked.** Both powers DEC-2 covers, putting text into a running session and writing another system's state records, are refused for this cycle. The decision issue stays open because the gate is live; a decision recorded is not a gate lifted. *(Stale: the input half is now allowed in the agent-initiated shape, which shipped. E7 stays blocked because its own shape is not that one.)*
* **E7's own proposal survived the call.** The note below suggests a single narrow verb, *ask this session for a hand-off summary*, instead of B4's ten write paths. DEC-2 lists that as its option C and **neither chose nor refused it**. *(Still true.)*
* **The route DEC-2 did leave open does not reach E7.** Answering a permission prompt by returning a decision from a hook covers allow-or-deny on a tool call and nothing else. *(And that route has since been measured shut on Claude — see [DRC-4163](<https://linear.app/recce/issue/DRC-4163/can-claudes-permissionrequest-hook-output-decide-settles-dec-2-option>).) (Stale twice over: that route was measured shut, and the route DEC-2 leaves open today is the agent-initiated ask lane, which also does not reach E7.)*

Unchanged there: DEC-3 is still open, so E4 and E5 are still blocked on it.

---

## Status as audited 2026-08-09 (historical; the updates above supersede it on E2 and E6)

Nothing has shipped as an E item. The audit found one structural defect that had been hiding this group's real state, and it is the most consequential finding across the four milestones reviewed.

**The two highest-scoring items here were gated on a decision nobody had filed.** E4 (74 risk-adjusted, the highest unshipped score in the group) and E5 (66) both need Cargento to read git state inside a user's repository. E4's own body says so — "a third amendment" — and the **Scope** section of `SECURITY.md` confirms the premise by treating file reads outside the documented store paths as a security bug. (Citation corrected 2026-08-28: this was written as `SECURITY.md:36-37`, which had drifted to `SECURITY.md:62-65` by v0.17.1. The section name will not drift again.) But neither issue carried any blocking relation, and no decision issue existed, so both have been reading as ready to build. [DRC-4122](<https://linear.app/recce/issue/DRC-4122/dec-3-decision-let-cargento-read-git-state-inside-your-repositories>) (DEC-3) now records that call and blocks both. Recommended direction is option B: read only what `git status --porcelain` reports, never file contents.

**E7's two stated prerequisites have both landed**, which nothing recorded. A1 shipped, so the wall is visible now rather than hypothetically, and A5's burn projection shipped beside it. DEC-1 closed 2026-08-04.

Per item, by risk-adjusted impact:

* **E4** (74) — blocked on DEC-3. Cargento already records every session's working directory, which the board rightly calls the hard half; what remains is a policy call and a bounded read, in that order.
* **E5** (66) — blocked on DEC-3, and it sits at that decision's widest option, because it needs an authenticated outbound call as well as the file read. It cannot ship on a DEC-3 that lands narrow.
* **E7** (56) — DEC-2 only. It carries the strongest demand evidence on the board: a ritual recorded verbatim from a user who performs it by hand.
* **E2** (54) — still partial, and more separable than it was. *(Done 2026-08-21; its premise had died in the meantime — see above.)*
* **E3** (46) — unshipped, and one entry of "the other eight vary" is now measured, unfavourably. `SessionEnd` maps for Claude; `CODEX_EVENTS` has none. *(Half its classifier shipped with E2 — see above.)*
* **E6** (42) — cheap, correctly ungated, confirmed not to be DEC-2 territory, and the only Release 1 item here that is ready to build today. It is also the cheapest place to answer a question C1, D9 and H1 all need answered: where user state lives. *(Done 2026-08-21, and that is exactly what it did.)*

**What this group is honest about that the others are not.** Every item here carries single-digit detector risk except E3 and E7. The uncertainty is not in the detection, it is in whether the product is allowed to look. That is why two separate decisions now sit under six items.
```

### Draft A — rewritten DRC-4037 body, for the gate to authorize

Shorter than what it replaces (92 → 58 lines). Both prior dated sections are demoted whole into
`## History`, unedited except for a one-line supersession note at the top of each.

```markdown
Board item **E4** from the Visibility 2x2 board (`docs/visibility-2x2/items.json`).

**Outcome:** the work does not evaporate · **Outcome group:** Nothing dies quietly (close the loop)
**Journey stage:** End of sessions · **Release row:** Release 2 · **Kind:** information

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 80 | 74 | 70 | 45 | 6 |

*Quadrant: differentiated · score confidence: high · panel median of 3 blind lenses.*

## The problem

Agent work is not lost dramatically. It is lost in a dirty worktree nobody went back to, after a
session that ended without failing. Cargento watches the session and says nothing about the tree.

## What ships

At the end of a session, run one bounded git probe inside that session's working repository and
publish two scalars on the row. [DRC-4122](https://linear.app/recce/issue/DRC-4122) (DEC-3) ruled
**option B, straight** on 2026-08-28 and released this issue. Its four bounds are part of the
ruling, not commentary; an implementation missing any of them is out of scope rather than imperfect.

1. **The probe is `git -c core.fsmonitor= --no-optional-locks status --porcelain`, or there is no
   probe.** Each flag disarms one measured hazard and neither disarms the other's, so both are
   required. Re-measured 2026-08-28 at git 2.55.0, four fresh probe repositories, one probe each:
   plain rewrites `.git/index` and runs a repo-local `core.fsmonitor` script; `--no-optional-locks`
   alone stops the write but not the script; `-c core.fsmonitor=` alone stops the script but not the
   write; both together stop both. *(DEC-3 recorded the script running twice per invocation; at
   2.55.0 it runs once. And the index write is race resolution rather than an unconditional
   per-invocation write — it fires whenever a file's mtime is inside the racy window, which in a
   repository a live session is editing is the normal case.)*
2. **The published surface is `dirty` and `changed`, per session, and nothing else.** Porcelain
   emits pathnames; they are matching hints, never echoed to `/api/data` — the wording `SECURITY.md`
   already uses for `cwd`. **`changed` counts porcelain entries, not files**: git collapses an
   untracked directory to one entry, so five new files under one new directory read as `1`. Label it
   as entries wherever it renders. **Both fields are nullable, and `null` means not probed** —
   `false` would be a confident "clean" over no evidence for the majority of rows, which never get
   probed at all. This follows `finished_at`, where `None` means "no stop observed" and never "did
   not finish".
3. **One-shot, on the `session_ended` edge.** *(Corrected 2026-08-28 at triage: DEC-3 named "the
   completion stamp E2 already ships". That stamp is `finished_at`, and it is a **turn-stop** stamp —
   `observation._mark_finished` pops it on every `working` overlay, so it re-arms each turn and a
   probe hung there would run once per turn. The real one-shot edge is the `session_ended` event,
   which E2 deliberately excluded from that stamp because it pops the overlay ledger whole. Bound
   3's property is unchanged; the artifact it named cannot deliver it.)* The absolute path comes from
   `Event.cwd`, which that event already carries — measured in the Claude and Droid `SessionEnd`
   captures — so no new retention is needed.
4. **An off switch, on by default, `--no-git`**, mirroring `--no-spacedock` at every one of its six
   sites, including the `lifecycle.spawn_argv` forwarding branch that a respawned daemon needs.

Six of the ten harnesses have no event adapter, so they can never be probed. They disclose that
through the existing `acquisition` marker and a null surface, never a false clean.

## Blocked by the amendment

`SECURITY.md` must state the contract before any code, per DEC-3. Following the shape DEC-1 and
DEC-2 both used ([DRC-4061](https://linear.app/recce/issue/DRC-4061),
[DRC-4177](https://linear.app/recce/issue/DRC-4177)), that is a separate documentation-only issue
delivering `docs/plans/git-probe-security-scope.md` in its own PR; this issue's PR promotes that
text into `SECURITY.md` unchanged and deletes the plan doc. That keeps `SECURITY.md` describing only
shipped behaviour at every commit, which matters because releases are cut from `main` by tag.

## Dependencies

* **Related:** [DRC-4122](https://linear.app/recce/issue/DRC-4122) (DEC-3, the ruling).
* **Preferred over:** [DRC-4038](https://linear.app/recce/issue/DRC-4038) (E5), which is re-gated on
  DEC-8 and needs an authenticated outbound call this issue does not.
* **Review depth:** full adversarial — `AGENTS.md`'s Calibrating Effort routes security work there.

## History

### Audited 2026-08-09 (superseded 2026-08-28 by the ruling above; retained as the record of what was believed)

<the 2026-08-09 section, verbatim and unedited>

### Unblocked and re-scoped 2026-08-28 (superseded the same day at triage on bounds 2 and 3, and on the retention claim; retained as the record of the re-scope as first written)

<the 2026-08-28 section, verbatim and unedited>
```

**Struck from the body, with reasons.** Both are demoted into `## History` rather than deleted, so
the two placeholders above carry the original text unchanged.

- *"A PR whose diff carries both the amendment and the runtime change does not satisfy it."* Not in
  DEC-3's outcome text, and it forbids exactly what DEC-1's and DEC-2's implementation PRs did. See
  Proposed approach; the gate rules.
- *"This issue has to re-derive and hold the absolute path, which is a small new retention."*
  Refuted — `Event.cwd` already carries it on the event the probe fires from.

### Draft B — milestone `Nothing dies quietly`, one correction

**Date it; do not correct it.** The stale sentence is the last line of the section headed *"Update
2026-08-21 (earlier) … (HISTORICAL: superseded on whether the input power is allowed by the
2026-08-23 update above)"*:

> Unchanged there: DEC-3 is still open, so E4 and E5 are still blocked on it.

Three reasons dating wins:

1. **The section's own convention is inline dating.** Its three bullets already carry italic
   *(Stale: …)* annotations rather than rewrites. This sentence is the only line in the section
   carrying none.
2. **The header's supersession does not reach it.** That header scopes itself to "whether the input
   power is allowed" — DEC-2. The DEC-3 sentence is outside that scope, which is why it reads as
   live.
3. **A naive correction would introduce a second error.** "E4 and E5 are still blocked" is *half*
   true today: E5 is still blocked, on DEC-8. Rewriting to "both are unblocked" would be wrong.

The current state is already stated correctly in the newest section, under **"DEC-3 was decided on
2026-08-28, and E4 and E5 got different answers."** Nothing else in the milestone needs to move.

Drafted replacement for that one line:

```markdown
Unchanged there: DEC-3 is still open, so E4 and E5 are still blocked on it. *(Stale as of
2026-08-28: DEC-3 was decided that day, on option B. E4 was released to `Todo` and re-scoped; E5 was
re-gated on DEC-8 rather than released, so it is still blocked but no longer on DEC-3. See the DEC-3
paragraphs in the 2026-08-23 update above.)*
```

### Draft C — the groundwork issue to file, if the gate takes the split

Title: **Git probe groundwork · SECURITY.md scope section for the end-of-session git probe.**
Milestone `Nothing dies quietly`, priority High, documentation only. E4 `blockedBy` it.

Done when `docs/plans/git-probe-security-scope.md` is merged holding the section text verbatim and
`python3 scripts/validate_plugins.py` passes; and E4's PR can promote it into `SECURITY.md`
unchanged and delete the plan doc. The text must state the bound, the published surface and its
nullability, what is never read, that the mechanism is subprocess execution rather than a file open
(naming both flags and what each one disarms), the cadence bound, and the off switch. Those are the
groundwork issue's acceptance criteria, not this issue's; the criteria below cover only what E4
itself delivers.

## Expected surface and tolerance

Assumes the amendment has already merged as its own PR, so E4's diff carries the promotion plus the
code.

| Area | Files | Notes |
| --- | --- | --- |
| New runtime module | `cargento_runtime/gitprobe.py` | subprocess invocation, porcelain parse, bounded timeout |
| Probe wiring | `observation.py` | the `session_ended` branch at `observation.py:304-308` |
| Row surface | `sessions.py` (`base_session`) | two keys, both nullable |
| Row plumbing | `aggregate.py` | carry the two scalars onto the row |
| Off switch | `cli.py`, `config.py` (×3), `lifecycle.py` (`spawn_argv`) | the six `--no-spacedock` sites |
| Runtime inventory | `scripts/validate_plugins.py` | `CARGENTO_RUNTIME_FILES` gains the new module |
| Frontend | `cargento_runtime/web/` and `web/next/` | **claims the single `web/` PR lane** |
| Tests | `tests/test_gitprobe.py` (new), `test_sessions.py`, `test_lifecycle.py`, `test_config_diagnostics.py`, `test_page.py`, `test_next_page.py` | |
| Docs | `SECURITY.md` (promotion), `SKILL.md` flags table, `HOW_TO_USE.md` flags table, `docs/design-runtime-architecture.md` | |

**Estimate: ~18 files, +380 / −40 lines. Tolerance ±40%.** The variance is almost entirely the
frontend: rendering means recomputing byte pins in **two** oracle sets (`test_page.py:105-181` and
`test_next_page.py:578-592`), at least four digests. Per `AGENTS.md`, exactly one in-flight PR may
touch `cargento_runtime/web/`; E4 must hold that lane for its cycle, and the digests must be
recomputed from the assets rather than resolved textually.

**Semantics that may move.** `Event.cwd` gains its first consumer, so `events.py`'s "no consumer"
comment and any doc repeating it go stale. `SECURITY.md`'s read-only invariant gains a subprocess
clause. Nothing about `project`, `finished_at` or `acquisition` changes meaning.

## Acceptance criteria

Every criterion is **offline** except AC7. Each names the concrete change that would falsify it.

**AC1 (offline) — exactly one git invocation exists, and it carries both flags.**
The argv the probe builds is `["git", "-c", "core.fsmonitor=", "--no-optional-locks", "status",
"--porcelain"]` and no other `git` subprocess exists anywhere in `cargento_runtime/`.
*Verified by:* a test in `tests/test_gitprobe.py` asserting the built argv against that literal,
plus a repository-wide assertion that `"git"` is constructed as a subprocess at exactly one site.
*Falsified by:* dropping either flag, or adding a second git call path (a `rev-parse` for
"is this a repo?" is the likely one, and must be folded into the single invocation).

**AC2 (offline) — the probe neither writes nor executes.**
Against a racy-clean probe repository the probe leaves `.git/index`'s mtime unchanged, and against
a repository whose `.git/config` sets `core.fsmonitor` to a logging script the script is not run.
*Verified by:* a test that builds both probe repositories in a tmpdir (`git init`, one commit,
`touch`) and asserts the stat and the empty log — the 2026-08-28 measurement above, turned into a
test. Requires `git` on `PATH`; skip cleanly when absent, since `platform-tests` runs on three OSes.
*Falsified by:* removing `--no-optional-locks` (index mtime advances) or `-c core.fsmonitor=` (log
gains one line). Each was measured to fail independently at git 2.55.0.

**AC3 (offline) — the row gains exactly two keys and no pathname reaches the wire.**
`DECLARED_SESSION_FIELDS` grows by `dirty` and `changed` and nothing else, and porcelain pathnames
never appear in `/api/data`.
*Verified by:* `tests/test_sessions.py:338` with the two names added, plus a test that feeds
porcelain output containing a distinctive filename through the probe and asserts that filename is
absent from `aggregate.collect_json()`'s bytes.
*Falsified by:* publishing a `files` list, a sample path, or a porcelain line; or adding a third key.

**AC4 (offline) — one probe per session, on the session-end edge, never on a turn stop.**
*Verified by:* a coordinator test driving `turn_stopped → turn_started → turn_stopped →
session_ended` with a counting fake probe runner, asserting exactly one invocation and that it
occurred on the `session_ended` arrival.
*Falsified by:* hanging the probe off `observation._mark_finished` (`observation.py:354`), which
pops on `OVERLAY_WORKING` (`observation.py:360-362`) and therefore re-arms every turn — that
sequence would produce two invocations, both at the wrong moment.

**AC5 (offline) — `--no-git` is off by default, disables the probe, and survives respawn.**
*Verified by:* a parse assertion mirroring
`tests/test_config_diagnostics.py:113 test_build_runtime_freezes_the_parsed_launch_options`, plus
`tests/test_lifecycle.py:1302 test_every_opt_out_reaches_the_respawned_daemon` extended to include
`--no-git`, plus a coordinator test asserting zero invocations when the flag is set.
*Falsified by:* omitting the `lifecycle.spawn_argv` branch (`lifecycle.py:554`) — the flag is then
silently dropped on the respawned daemon, which is the defect that test was written for after
`--no-usage` was lost on Windows.

**AC6 (offline) — an unprobed session publishes `null`, never `false`.**
A row that was not probed — a scan-only harness, `--no-git`, a non-repository directory, a missing
`Event.cwd`, git absent, or a probe that timed out — carries `dirty: null` and `changed: null`.
*Verified by:* a test asserting `dirty is None` on a row whose `acquisition` is `"scan-only"`
(`aggregate.py:685-703`), and one per remaining cause.
*Falsified by:* defaulting `dirty` to `False` in `base_session` — every unprobed row then reads
clean, which is the same confident-green-over-absent-evidence failure recorded at DRC-4101.

**AC7 (interactive) — it is true of a real session.**
A human runs the dashboard, ends a real Claude session in a repository with a known dirty state, and
the row shows dirty with the porcelain entry count.
*Verified by:* a live drive, with the `SessionEnd` payload captured under `docs/captures/claude/`
if its shape differs from `hooks-2.1.222-macos.jsonl`.
*Falsified by:* the published count disagreeing with `git -c core.fsmonitor= --no-optional-locks
status --porcelain | wc -l` taken at the moment the session ended.
**No harness is planned to automate this**, because the falsifier needs a real harness process to
exit; AC4 covers the wiring offline and AC7 covers only that the wiring meets a real payload.

## Test plan

`tests/test_gitprobe.py` is new and owns AC1, AC2, AC3's redaction half and AC6's causes; it builds
throwaway repositories with `git init` in a tmpdir and skips when `git` is absent. AC4 and AC5's
coordinator half extend the existing event-coordinator tests. AC3's key-set half and AC5's flag half
extend `test_sessions.py` and `test_lifecycle.py` / `test_config_diagnostics.py` respectively. Byte
pins in `test_page.py` and `test_next_page.py` are recomputed from the assets, never edited to match.

Run the canonical pre-PR suite from `AGENTS.md`. Per **Parallel Work**, confirm any failure in
`test_http_api`, `test_page`, `test_lifecycle` or `test_quota` by re-running that module alone before
believing it, and report both results.

## Review depth

**Full adversarial** — several lenses, a completeness critic, an arbiter. `AGENTS.md`'s Calibrating
Effort routes "security, credential handling, or data loss" there, and DEC-3's gate named the cost
before authorizing the work. The lenses worth naming: the probe's subprocess surface (argv
construction, environment, timeout, a repository that is a symlink or a submodule), the null-versus-
false surface, and the `web/` byte pins.

### Feedback Cycles

**No correction round ran.** No reviewer was dispatched and no gate rejection occurred, so there is
no `Cycle N` line. The entry below is the finding-disposition record.

- Disposition 2026-08-28, implementation — eleven discrepancies reported across a report and an
  addendum, none acted on. **FO authorization: DECLINE on all eleven.** Items 1–6 and 7–11 are all
  Polish or findings rather than defects, and three of them corrected rules the FO had written.
  - *Item 9 settles 7 and 8 by itself.* Both halves were measured in one cycle: sending the clean
    `` **label.** `code` `` returns the damaged `` **label. **`code` ``, and a later write drops the
    damaged form's mark entirely. **There is no stable state to repair toward**, so declining is the
    only coherent action rather than a judgement call.
  - *Item 8 corrected the rule.* The README said the boundary moves; the damage is **progressive** —
    move, then lose the mark — and it happened through a `patch` **append** op that re-transmitted no
    existing byte, which is the sharpest confirmation that a targeted patch is not a targeted write.
    Accepted visible cost, recorded rather than unnoticed: option B's label on DRC-4122 is now
    unbolded while A, C and D remain bold.
  - *Item 10 is the strongest measurement of the run.* The worker's appended section round-tripped
    **byte-identical, zero boundary moves**, through the same API that damaged the hard-wrapped draft
    beside it — a control and a treatment in one cycle. That converted the structural avoidance from
    a plausible mitigation into a proven one, hours after the FO had written it as theory.
  - *Items 1 and 2 also corrected FO rules:* markdown links do **not** prevent mention-created
    relations, because a link whose href is a Linear issue URL is parsed as a mention too; and a
    space does **not** prevent an emphasis split when a code span *follows* the run. Both mitigations
    had been written by the FO and never tested.
  - *Item 3 was the worker's own error, named as such:* an approved draft sent with 100-column hard
    wrapping, which Linear read as hard breaks and re-marked per line. **Send Linear bodies
    unwrapped** is now a rule, from the worker's own lesson.
  - *Item 11* was checked unprompted and correctly: the risk that mentions would convert DRC-4122's
    `blocks` edge to DRC-4026 was real and specific, and it was verified from the far end. The
    promote-to-material condition remains unobserved across six cycles.
- **Two process notes.** The worker stopped and asked whether "a state that reflects being blocked"
  meant the Linear workflow state rather than guessing — the FO's wording was genuinely ambiguous,
  and *name the artifact, not a category* is now a checklist-authoring rule. And its addendum, which
  correctly preserved the original report as written, reused the `## Stage Report: {stage}` heading
  and thereby hid three evidenced items from the parser; the completion guard caught it, the fix was
  content-neutral, and *an addendum must nest as a `###`* is now a rule. **The guard was satisfied
  rather than bypassed**, even though clearing the worktree had already disarmed it.

_None yet._

## Out of scope

- The `SECURITY.md` text itself — the groundwork issue owns it, per Proposed approach.
- E5 ([DRC-4038](https://linear.app/recce/issue/DRC-4038)) and DEC-8
  ([DRC-4273](https://linear.app/recce/issue/DRC-4273)): branch state, upstream state, pull-request
  state, and any outbound authenticated call.
- Option C and beyond: branch or upstream information of any kind, even though it is local.
- Any per-file identity: filenames, counts by status letter, diffs, blob reads. Bound 2.
- Any cadence other than one-shot at session end: no polling, no refresh, no probe on demand.
- Giving the six adapter-less harnesses a probe. They need an event adapter first, which is its own
  issue per harness.
- Acting on the result — no notification, no dismissal integration, no nudge to commit.

## Stage Report: triage

- DONE: E4 re-scoped to DEC-3's four bounds, and the delivery SHAPE decided with reasons: whether the `SECURITY.md` amendment is a separate groundwork issue following the DRC-4061 and DRC-4177 precedent, or part of this issue. Recommend one. Acceptance criteria are written only for whatever THIS issue will itself deliver, and each carries a `Verified by:` clause naming something outside the entity plus the concrete change that would falsify it.
  **Recommend the split.** Precedent verified at both ends: plan doc added in its own PR (`7134a01` #71, `5ede7d1` #143), promoted into `SECURITY.md` and deleted by the implementation PR (`a98bc64`, `3e92d12`). Seven ACs, six offline and one interactive; each `Verified by:` names a test file:line, a capture, or a live drive.
- DONE: Every load-bearing claim re-derived at the current tip rather than accepted from the issue, which was last touched 2026-08-09: what the runtime actually holds of a session's working directory and whether it is enough to run a probe against, where the published surface would have to be assembled, whether the two hazard-disarming flags behave the same on this machine's git, and what E2's session-completion stamp actually is, since bound 3 fires the probe on it. Report any claim you could not reproduce rather than repeating it.
  Seven re-derivations under "Re-derived at the tip"; two of the issue's claims refuted, one refined, the rest hold. One DEC-3 figure did not reproduce (below).
- DONE: Nothing is written to Linear. The stale DEC-3 passage carried forward from the previous cycle — "Unchanged there: DEC-3 is still open, so E4 and E5 are still blocked on it", in the milestone's HISTORICAL section — is assessed and drafted, not written. Say whether it should be dated or corrected, and why.
  **Dated, not corrected** — Draft B. No Linear write, no repository file changed; the only writes this stage made are this entity and two throwaway probe repositories under `/tmp`.

### What did not reproduce, and what changed the build

- **DEC-3's "twice in one invocation" for the `core.fsmonitor` script did not reproduce.** At git
  2.55.0 on this machine it ran **once**. The security consequence is unchanged; the figure should
  not be repeated in the amendment.
- **The two flags reproduce, and each is independently load-bearing.** Four fresh probe
  repositories, one probe each, from an identical racy-clean state: plain rewrites `.git/index`
  *and* runs the script; `--no-optional-locks` alone stops the write only; `-c core.fsmonitor=`
  alone stops the script only; both stop both. That is stronger than DEC-3's record, which measured
  the two hazards separately, and it means neither flag can be dropped. The index write is race
  resolution rather than an unconditional per-invocation write — real in a repository a live session
  is editing, but the ruling's wording reads as unconditional and is not.
- **Bound 3 names the wrong artifact.** `finished_at` is a *turn-stop* stamp: `_mark_finished`
  (`observation.py:354`) pops it on every `working` overlay (`observation.py:360-362`), so a probe
  hung there fires once per turn. The one-shot edge is `session_ended` (`events.py:66`,
  `observation.py:304-308`), which E2 deliberately excluded from that stamp. Bound 3's property
  survives; its named hook does not.
- **The retention cost is zero, not "a small new retention".** `Event.cwd` (`events.py:167`, bounded
  4096, oversized values dropped rather than truncated) is the absolute path and has no consumer,
  and the real `SessionEnd` captures for Claude and Droid both carry `cwd`.
- **Bound 2 cannot express "not probed".** Six of ten harnesses can never be probed; a non-nullable
  `dirty: bool` publishes a confident `false` for most rows. Recommend nullable, following
  `finished_at`. **This needs the captain's ruling** — it departs from the ruling's literal words to
  serve its intent.
- **`changed` counts porcelain entries, not files.** One modified file plus five untracked files in
  one new directory measures as `2`.
- **One conflict for the gate.** DRC-4037's own sentence "a PR whose diff carries both the amendment
  and the runtime change does not satisfy it" is absent from DEC-3's outcome and forbids exactly what
  DEC-1's and DEC-2's implementation PRs did. Recommend striking it.
- Minor: `main` is at **v0.18.0** (`ef425b2`), not v0.17.1 as the dispatch says.

### Summary

E4 is buildable, and the question that decided it — whether an absolute working directory still
exists when the runtime could use one — answers better than the issue expected: `Event.cwd` already
carries it on the very event the probe should fire from, so no new retention is needed. Two of the
four bounds need adjustment before code: bound 3 names `finished_at`, which re-arms every turn and
would turn a one-shot into a per-turn poll, and bound 2's non-nullable surface would publish a
confident "clean" for the majority of rows that can never be probed. Both are drafted as
corrections that keep the ruling's intent, and both are the gate's to accept. The delivery shape
follows DRC-4061 and DRC-4177 exactly: a documentation-only groundwork issue delivering
`docs/plans/git-probe-security-scope.md`, with E4 blocked on it. Nothing was written to Linear.

## Stage Report: implementation

- DONE: Draft A written to DRC-4037: the body re-scoped to the four bounds AS AMENDED — bound 3 building to `session_ended` rather than `finished_at`, and bound 2 as `{dirty: bool | None, changed: int | None}` with `None` meaning not probed — with the struck single-PR sentence removed, prior text demoted to dated history rather than deleted, and the issue left in a state that reflects being blocked on the groundwork issue.
  Written 06:58Z; `updatedAt` moved `06:21:20.501Z` → `06:58:06.747Z`, which also proves the pre-edit capture was still the live body at write time. Assembled by `/tmp/drc4037-impl/build_draftA.py` from that capture: both History placeholders asserted present exactly once, both source sections asserted present exactly once. Read-back confirms the single-PR sentence occurs once in the whole body and that occurrence is inside `## History`; same for the refuted retention claim.
- DONE: Draft C filed as a new documentation-only groundwork issue delivering `docs/plans/git-probe-security-scope.md`, following DRC-4061 and DRC-4177, with its `blocks` edge added onto DRC-4037 so E4 is blocked on it. Report the identifier Linear mints. Do not invent the identifier and do not write the plan document itself — that is the groundwork issue's own cycle and its own PR.
  **Linear minted [DRC-4274](https://linear.app/recce/issue/DRC-4274).** Milestone `Nothing dies quietly`, priority High, documentation only, status `Backlog` (team default, not set by me). Read back from both ends: `DRC-4274.blocks = [DRC-4037]` and `DRC-4037.blockedBy = [DRC-4274]`. No plan document written and no repository file touched — the worktree is clean at `ef425b2` with zero commits on `spacedock-ensign/drc-4037`.
- DONE: Draft B applied to the "Nothing dies quietly" milestone: the stale DEC-3 passage DATED as historical rather than corrected, per the gate. Build the milestone edit by script from a pre-write capture, assert each target passage is present exactly once, and diff before sending — report the hunk count. Read back every record written and REPORT every discrepancy; discrepancies are the FO's to disposition, not yours to pass or fail on.
  Built by `/tmp/drc4037-impl/build_draftB.py` from a capture re-fetched live before the write and confirmed byte-identical to pre-edit record B. Target passage asserted present exactly once; replacement asserted to retain the original sentence verbatim before appending the dated note. **Diff: 1 hunk, 1 line changed, +261 chars, nothing else moved.** The four hard-wrapped lines of the approved draft were joined into one line to match the milestone's one-line-per-paragraph convention; wording is unchanged.

### Discrepancies on read-back — the FO's to disposition, per the checklist

1. **Five unrequested `relatedTo` edges, despite every identifier being written as a markdown link.** DRC-4274 gained DRC-4122, DRC-4061, DRC-4177; DRC-4037 gained DRC-4061, DRC-4177. This refines the README's mention rule: writing identifiers as markdown links is **not** sufficient — a link whose href is a Linear issue URL is parsed as a mention too. **No `blocks`/`blockedBy` edge appeared unrequested** (the README calls that Material immediately); the only blocking edge is the authorized one. Not repaired — removing them would be a second unapproved write.
2. **The emphasis guard's documented mitigation is incomplete, measured twice today.** A space between a bold or italic run and an adjacent code span did **not** prevent the move. On DRC-4274 I wrote ``**The off switch.** `--no-git` `` and it came back ``**The off switch. **`--no-git` `` — the run swallowed the space. On the milestone I wrote ``E4 was released to `Todo` and re-scoped`` inside one italic run and it came back split at the code span: ``released to* `Todo` *and re-scoped``. The five sibling bullets on DRC-4274 whose bold runs are followed by ordinary text round-tripped clean, so the trigger is a code span *following* the run, not adjacency generally.
3. **DRC-4037's body round-tripped worse than the documented shape, and the cause is mine to name.** I sent the approved Draft A with the entity file's 100-column hard wrapping intact. Linear read those newlines as hard breaks inside emphasis runs and re-marked per line, producing artifacts like ``no****\n****probe.**`` and an italic aside re-serialized as bold. Text content is unchanged and Linear renders from its document model, so the guard's "nothing is visibly wrong where people read it" should hold — but the rendered body now carries ragged mid-sentence line breaks the draft did not intend. Not repaired: the rule forbids it and altering approved prose is a second unapproved change. **The lesson for the next cycle is to send Linear bodies unwrapped**; Drafts B and C were sent unwrapped and show none of this.
4. **One pre-existing mark lost in the milestone, in text nobody touched.** `*whether it is allowed ***as of 2026-08-21 only**` came back as `whether it is allowed **as of 2026-08-21 only**` — the serializer normalized malformed nested emphasis by dropping the stray italic. Words unchanged. Unavoidable and unrepairable per the measured rule.
5. **Milestone `progress` moved 16 → 15.38**, because DRC-4274 joined the milestone and changed the denominator. Expected, not caused by the description edit.
6. **`Failed to remove 1 relation(s)` did not occur.** All three writes returned clean.

### Open question, put to the FO and unanswered at report time

Whether "the issue left in a state that reflects being blocked" means the Linear **workflow state**. I left DRC-4037 at `Todo` and expressed the blocking through the authorized `blockedBy` edge plus the body's `## Blocked by the amendment` section. The issue's own precedent cuts the other way — it sat in `Backlog` while blocked on DEC-3 and the move to `Todo` was justified by being "genuinely released" — but no approved draft authorizes a status change, and the entity's `linear-status: Todo` is frontmatter I must not touch. One `save_issue` call closes it either way.

### Summary

The three authorized writes all landed: Draft A rewrote DRC-4037 to the amended bounds with both prior sections demoted verbatim into a dated `## History`, Draft C was filed as **DRC-4274** and now blocks E4, and Draft B dated the stale DEC-3 sentence in the milestone in exactly one hunk. Nothing else was written — no plan document, no repository file, no note on DRC-4122, and the worktree stands empty at `ef425b2`. The cycle's substantive finding is that two documented Linear-write mitigations are weaker than recorded: markdown links do not stop mention-created relations, and a space does not stop an emphasis run from splitting at a following code span. Both are reported rather than repaired, along with the hard-wrapping artifact on DRC-4037's body, which is mine and is the one thing here worth changing in the next cycle's method.

### Addendum — FO answer applied, and one authorized scope extension

Appended rather than merged into the report above, which stands as written at the time it was written.

- DONE: **DRC-4037 moved to `Backlog`.** FO answer to the open question the report above logged.
  `status` read back as `Backlog`, `statusType: backlog`, at `07:03:01Z`. The `blockedBy` edge to DRC-4274 and Draft A's `## Blocked by the amendment` section are both retained, per the instruction. The entity's `linear-status` frontmatter is the FO's to sync and I have not touched it. The body re-read byte-identical to its previous read-back, so the state change did not re-serialize it.
- DONE: **Fourth write — a dated note appended to DRC-4122.** FO SCOPE EXTENSION, authorized by the captain, reversing the earlier "do not touch DRC-4122" instruction.
  One appended section, `## Amended 2026-08-28 — two of the four bounds, by the captain, after triage measured them`, recording exactly the four things specified: bound 3 amended to `session_ended` with the turn-stop reasoning; bound 2 amended to the nullable surface, stated as a deliberate departure from the ruling's literal words rather than a correction of fact; the two figures that did not reproduce (script ran once, not twice; index write is race resolution, not unconditional); and the pointer that E4 carries the current scope. Bounds 1 and 4 named as unchanged, both flags in bound 1 named as mandatory. Sent as a `patch` `append` op so no existing byte was re-transmitted by me; the existing `## Outcome` text was not edited.

### Further discrepancies on read-back — the FO's to disposition

7. **The `patch` re-serialization dropped five pre-existing bold runs on DRC-4122 outright.** Not moved — dropped. Every one is the shape `**Some label. **` immediately followed by a code span: option **B**'s lead-in in the options list, the Recommended direction lead-in, and three lead-ins in the triage note (`Option B is not a read.`, `"No filenames leave the machine"…`, `Who sees the published surface.`). Words are unchanged in all five. The visible cost is that option B's label is now unbolded while A, C and D are still bold, so the list reads inconsistently.
8. **The damage compounds across writes, which the README's rule does not yet record.** Those five spots were already in the damaged `**label. **`code`` form — a *previous* write's bold-swallows-the-space artifact. This write resolved that malformed nesting by discarding the mark entirely. So the sequence is: move the boundary, then lose the mark. The README's "text content was unchanged in every case" still holds; "the boundary moves" understates it. **Recommend the rule be extended** to say the damage is progressive and that the only real mitigation is structural — never place a code span immediately after an emphasis run.
9. **Not repaired, and a repair provably cannot succeed here.** Today's DRC-4274 write measured that sending the clean form ``**label.** `code` `` comes back as ``**label. **`code` `` — the damaged form. So repairing these five would re-create the exact input that the next write drops again. That is the README's claim, now measured on both halves of the cycle rather than one.
10. **My own appended section round-tripped byte-identical — zero boundary moves.** Achieved by never placing a code span immediately after a bold run and never putting one inside an italic run. Combined with discrepancy 2 above, this isolates the trigger: it is a code span *following* an emphasis run, not adjacency in general, and it is avoidable in text one authors.
11. **No relation was silently converted.** The risk was that mentions in DRC-4122's body would re-add `relatedTo` and convert its `blocks` edge to DRC-4026. Checked from the far end: `DRC-4026.blockedBy = [DRC-4122]`, `relatedTo: []`. Intact. No unrequested edges were created by this write either, because every issue its text links was already an edge.

### Summary

The FO's answer was applied — DRC-4037 sits at `Backlog` with the blocking edge and the body section both intact — and the authorized fourth write landed on DRC-4122 as a single appended dated section that did not touch the ruling's original text. The cycle's most useful result is now a two-sided measurement of the emphasis guard: text authored to keep code spans away from emphasis runs round-trips perfectly, while text already carrying the damaged form loses its marks entirely on the next write, and cannot be repaired into a stable state. That is a stronger claim than the README currently records and is offered for the FO to fold into the rule.

---

## Re-derived at the tip, cycle 2 (2026-08-28, `origin/main` at `701b7f0`)

Nothing below is accepted from E4's live Linear body. Twelve load-bearing claims were re-measured or
re-read against the tree. Nine reproduce, three do not, and two facts nobody had written down are new.

**The checkout is one commit behind.** `main` here is `ef425b2` (v0.18.0); `origin/main` is `701b7f0`
(PR #238, merged 2026-08-28T08:52:15Z, one file, +102/−0). Everything below was read through
`git show origin/main:<path>` rather than by checking out, because this stage may not modify the tree.
`701b7f0` adds only `docs/plans/git-probe-security-scope.md`, so every runtime line number cited here
is identical on both.

### Reproduced

1. **Bound 1's two flags, each independently load-bearing.** Re-measured today at git 2.55.0, four
   fresh repositories, one probe each, from an identical racy-clean state (`git init`, one commit,
   rewrite the file with identical content, `core.fsmonitor` set to a logging script):

   | flags | fsmonitor script runs | `.git/index` |
   | --- | --- | --- |
   | (none) | 1 | written |
   | `--no-optional-locks` | 1 | not written |
   | `-c core.fsmonitor=` | 0 | written |
   | both | 0 | not written |

   Each flag disarms exactly one hazard, neither disarms the other's, the script runs **once** and not
   twice, and the index write is race resolution. The merged contract's paragraph is exact.
2. **`changed` counts porcelain entries, not files.** One modified tracked file plus an untracked
   directory holding three files gives **2 entries for 4 changed files**.
3. **`--no-spacedock` has six sites, and E4's body is the figure that is right.** Enumerated:
   `cli.py:115` (argparse), `cli.py:203` (`spacedock_enabled=not args.no_spacedock`), `config.py:46`
   (dataclass field), `config.py:384` (builder parameter, default `True`), `config.py:424` (builder
   assignment), `lifecycle.py:554-555` (`spawn_argv` respawn forward). The groundwork cycle's figure
   of three counted `cli.py` twice and `lifecycle.py` once and missed `config.py`'s three. `--no-usage`
   occupies the identical six. **Correct the record: the wrong number was the groundwork cycle's.**
4. **`Event.cwd` is parsed and has no consumer.** Parsed at `events.py:386` under `MAX_PATH_LEN`; the
   only other `cwd` in the runtime is a docstring at `transcripts.py:104`. The probe is its first
   consumer, so no new retention is needed and the superseded "small new retention" claim stays refuted.
5. **The promotion is mechanical.** Every anchor the contract names exists verbatim: `SECURITY.md:67`
   `## Project reads (Spacedock stage strips)`, `SECURITY.md:122` `## Usage quota reads (the quota
   fetcher)`, `SECURITY.md:65` the Scope closing sentence containing `writes to harness stores,`, and
   `SECURITY.md:35` Invariant 2 `Read-only against harness stores.`
6. **The groundwork shipped.** DRC-4274 is `Done`, PR #238 merged, `blockedBy` on E4 is empty and its
   Linear status is `Todo`. (The entity frontmatter still reads `linear-status: Backlog`; Linear moved
   to `Todo` at 09:00:04Z. Frontmatter is not this stage's to edit — flagged for the FO.)
7. **No git invocation exists in the runtime today.** A grep for `git` across `cargento_runtime/`
   returns nothing.
8. **Six harnesses have no event adapter.** Ten collectors ship; `events.IDENTITY_NORMALIZERS`
   (`events.py:305-310`) holds four — `claude`, `codex`, `antigravity`, `gemini`. That half of the
   sentence is true.
9. **Full adversarial is the routed tier.** `AGENTS.md`'s Calibrating Effort row "Security, credential
   handling, or data loss" reads "Full adversarial — several lenses, a completeness critic, an arbiter."

### Falsified

**F1 — "Six of the ten harnesses have no event adapter, so they can never be probed." The predicate is
wrong; the count is right for a different question.** Having an adapter is necessary and not
sufficient: the harness's vocabulary must also contain a session-end event. `CODEX_EVENTS`
(`event_hook.py:160-166`) registers five names and `SessionEnd` is not among them. Antigravity's
adapter derives events from `agent_state` and maps only `working`/`idle` (`statusline_hook.py:118-121`),
with `store_changed` from `agy_hook.py:153`. So Codex and Antigravity have adapters and still cannot
emit `session_ended`. **Eight of ten rows can never be probed, not six.**

The count was carried across from `finished_at`, where six *is* correct — that field needs any
overlay-producing event, which Codex and Antigravity both supply. `observation.finished_at`'s own
docstring (`observation.py:378-386`) says "the six harnesses with no event adapter", and the sentence
was reused for a narrower predicate. Draft the correction as a property, not a count, for the reason
the merged contract gives: a number goes stale the first time an adapter gains the event. Droid and
Goose already emit `SessionEnd` natively (`docs/captures/droid/notification-0.202.0-macos.jsonl`,
`docs/captures/goose/tool-confirmation-1.47.0-macos.jsonl` both record it in the harness's own
vocabulary) and are unreachable only because Cargento has no adapter for them — so the eight is a
statement about Cargento, not about the harnesses, and it will move.

**F2 — "They disclose that through the existing `acquisition` marker and a null surface."** The marker
cannot carry this. `acquisition` has exactly two values, `event` and `scan-only` (`events.py:109-110`),
and `aggregate._mark_unreachable_by_events` (`aggregate.py:685-703`) sets `scan-only` for precisely the
harnesses **absent from `IDENTITY_NORMALIZERS`**. Codex and Antigravity are present, so their rows read
`acquisition: "event"` and will never be probed anyway. The marker under-discloses by two rows, and it
says nothing at all about the other five causes of a null: `--no-git`, a directory that is not a
repository, an event with no `cwd`, git absent from `PATH`, and a probe that timed out. **`null` is the
whole of the disclosure**, and the body must stop crediting `acquisition` with work it does not do.

**F3 — "measured in the Claude and Droid `SessionEnd` captures."** The Droid capture is a verdict
record, not a payload capture: it evidences that Droid *fires* `SessionEnd`
(`events_observed_before_the_gate`) and records no payload keys at all, so it cannot evidence `cwd`.
The two captures that do list `cwd` among a `SessionEnd` payload's keys are **Claude**
(`docs/captures/claude/hooks-2.1.222-macos.jsonl`) and **Gemini**
(`docs/captures/gemini/hooks-0.53.1-macos.jsonl`). Correct the pairing to Claude and Gemini — which is
also exactly the pair that can reach the probe, so the sentence gets shorter and truer at once.

### New, and both bear on the build

**N1 — the session-end edge runs on the HTTP handler thread, under the coordinator lock, behind a
two-second client timeout.** `coordinator.submit()` is called at `http_api.py:838` inside the request
handler of a `ThreadingHTTPServer` (`http_api.py:98`); `submit` calls `_record`, which takes
`self._lock` at `observation.py:300` and handles `retires_overlays` inside it at `observation.py:302-307`.
The hook client's HTTP timeout is **2 s** (`notify_hook.py:34`; `event_hook.py` shares its transport
guards). A probe run synchronously there would (a) hold the coordinator lock for the duration, stalling
every other event and the collection loop, and (b) hold the harness's own `SessionEnd` hook open past
its timeout. `git status` on a large tree routinely exceeds 2 s. **The probe must not be synchronous
inside `_record`.** Neither the merged contract nor E4's body names this, and it is the constraint most
likely to produce a real defect.

**N2 — `session_ended` mints no overlay, so there is no carrier for the result.** `overlay_for()`
returns `None` for it (`events.py:430`, falling through at `:478`); `retires_overlays`
(`events.py:482-491`) pops the ledger rather than producing a claim. The published pair therefore has to
follow the `finished_at` pattern exactly: a bounded side-channel dict on the coordinator, a `_mark_*`
writer under the `event_overlay_max_sessions` refusal guard (`observation.py:363-371`), a public reader,
a new method on the `OverlaySource` Protocol (`aggregate.py:129-136`), and a read in `_apply_overlays`
(`aggregate.py:719-738`). It also means the two names must be added to `events.PATCHABLE`
(`events.py:105-107`) **and restated in all three `patch.update` blocks** of `reduce_overlays`
(`events.py:594`, `:607`, `:620`), or the fields survive a state change they should not.

`events.retires_overlays`'s docstring records one more thing the body should say out loud: Claude fires
`session_ended` on `/clear` as well as on exit, and a `turn_started` for the same session may follow
inside one coalescing window. So the probe is one-shot **per session-end event**, not per session — the
bound still forbids polling, but "one probe per session" is not what will be observed.

## Delivery shape (cycle 2) — recommended: two PRs, split on `web/` and nothing else

**PR 1 — contract, probe, published field. Touches no file under `cargento_runtime/web/`.**
Promotes the section from `docs/plans/git-probe-security-scope.md` into `SECURITY.md` unchanged, applies
the two intro amendments the document names, deletes the plan doc, adds the probe module and its
`session_ended` wiring, adds `--no-git`, publishes `dirty` and `changed` on every row, and updates
`SKILL.md`, `HOW_TO_USE.md` and `docs/design-runtime-architecture.md`.

**PR 2 — the render.** `web/` and `web/next/` only, plus the two byte-pin oracle sets.

Both PRs belong to E4; the issue is not `Done` until PR 2 lands. No second issue is filed, because the
render carries no decision content of its own and a second issue would cost a triage cycle to say so.

**Why split here and nowhere else.** `AGENTS.md` names exactly one constraint that genuinely forces a
split — "exactly one PR may touch `cargento_runtime/web/`" — and that surface is contended right now.
`gh pr list` shows one open PR (#224) touching no web file, so the *queue* is clear, but two live
sibling worktrees already carry `web/` diffs against `origin/main`: `docs/sync-next-ui-design-parity`
(76 files, including `web/calm.js` and four `web/next/*.js`) and `worktree-spacedock-boot-rendering`
(30 files, `next-activity.js` and `next-session.js`). E4 would be the third writer.

What that costs if the halves ride together: `test_page.py` pins 28 figures and `test_next_page.py`
pins another 28 — 56 in total, with **no script that emits them**; `AGENTS.md` and
`docs/design-next-ui.md` both say recompute from the assets, and the only recompute path is by hand
from the failure output. A textual resolution across three writers ships a number wrong for every side.
Worse, a recompute forced by a sibling merge lands *after* review, so the full adversarial pass would
have to re-verify a diff it had already cleared.

**Why the split does not break the promotion constraint.** The promoted section describes running one
bounded git command and publishing two nullable fields. PR 1 ships both. The section says nothing about
rendering. So `SECURITY.md` describes only shipped behaviour at PR 1's merge and at every commit after
it, and the plan doc is deleted in the same commit that promotes it — the precedent's shape, unbroken.
The intermediate state claims exactly this and nothing more: *the probe runs on session end, `/api/data`
carries `dirty` and `changed`, `--no-git` turns it off, and the dashboard does not show it yet.* True,
releasable, and honest against any tag cut in the window.

**What it costs.** One extra CI cycle; a `gh pr update-branch` plus a full re-run on PR 2 once PR 1
lands, because a ruleset requires branches be up to date; and one extra review at the cheaper tier.
`AGENTS.md` measures the waiting at roughly fifteen minutes per extra PR. Called against the byte-pin
exposure above, that is the cheap side.

**Rejected — one PR carrying everything.** One cycle instead of two, no cross-PR sequencing. It cannot
deliver, because it puts the security-critical diff on the same branch as 56 byte pins with two live
siblings already in that surface, and it forces the most expensive review tier the repository has onto
the render as well. `AGENTS.md`'s Calibrating Effort names uniformity, not depth, as what made the
measured run expensive: 35 agents, 10 blocking findings.

**Rejected — three PRs (promotion, then probe, then render).** Forbidden by the constraint the merged
contract states outright: the promotion and the deletion ride together, and a promotion PR that ships no
probe leaves `SECURITY.md` describing behaviour that does not exist. That is the exact failure the
groundwork shape exists to prevent.

**One consequence worth stating at the gate.** The split lets review depth be set per PR rather than per
session, which is what `AGENTS.md` asks for. PR 1 is the "Security, credential handling, or data loss"
row and takes the full adversarial tier. PR 2 is the "Owns a conflict-prone surface (`web/` byte pins,
`SKILL.md`, `config.py`)" row and takes two lenses plus an arbiter. Neither is an override; both are the
table read literally.

## Acceptance criteria (cycle 2)

These supersede the cycle-1 set above. AC1-AC8 belong to PR 1, AC9-AC10 to PR 2, AC11 to the issue.
Every criterion is **offline** except AC11. Each names something outside this entity that decides it,
and the concrete change that would falsify it.

**AC1 (offline) — exactly one git invocation exists in the runtime, and it carries both flags.**
The argv is `["git", "-c", "core.fsmonitor=", "--no-optional-locks", "status", "--porcelain"]`, built at
one site, and no other `git` subprocess exists anywhere under `cargento_runtime/`.
*Verified by:* a test asserting the built argv against that literal, plus a repository-wide assertion
that `git` is constructed as a subprocess at exactly one site. Today that grep returns nothing, so the
"exactly one" baseline is established rather than assumed.
*Falsified by:* dropping either flag, or adding a second git call path. A `rev-parse` to answer "is this
a repository?" is the likely one and must be folded into the single invocation — a non-repository is
already distinguishable from the one command's exit status.

**AC2 (offline) — the probe neither writes nor executes.**
Against a racy-clean repository the probe leaves `.git/index`'s mtime unchanged; against a repository
whose `.git/config` sets `core.fsmonitor` to a logging script, the script does not run.
*Verified by:* a test building both repositories in a tmpdir and asserting the stat and the empty log —
the four-repository measurement above turned into a test. It must skip cleanly when `git` is absent,
because `platform-tests` re-runs the suite on Ubuntu, macOS and Windows.
*Falsified by:* removing `--no-optional-locks` (index mtime advances) or `-c core.fsmonitor=` (the log
gains one line). Each was measured to fail independently at git 2.55.0 today.

**AC3 (offline) — the probe never runs on the event-ingress thread and never under the coordinator
lock.**
`ObservationCoordinator.submit()` returns without having waited on a git subprocess.
*Verified by:* a test that submits a `session_ended` envelope with a probe runner injected to block on
an event, and asserts `submit()` returns before that runner is released; plus an assertion that the
probe call site is not inside the `with self._lock` block of `observation._record`.
*Falsified by:* calling the probe inline in `observation.py:302-307`. `submit` is reached from
`http_api.py:838` on a `ThreadingHTTPServer` handler thread, and the hook client's timeout is 2 s
(`notify_hook.py:34`), so an inline probe both stalls every other event behind the lock and times out
the harness's own `SessionEnd` hook on any repository large enough to take two seconds.

**AC4 (offline) — the probe fires on the session-end edge and on no other, at most once per edge.**
A `turn_stopped → turn_started → turn_stopped → session_ended` sequence produces exactly one probe, on
the `session_ended` arrival. Two `session_ended` events for one session produce at most two probes, one
each, and never a third.
*Verified by:* a coordinator test driving that sequence with a counting fake runner.
*Falsified by:* hanging the probe off `observation._mark_finished` (`observation.py:354`), which pops on
`OVERLAY_WORKING` (`observation.py:360-362`) and re-arms every turn — that sequence would produce two
invocations, both at the wrong moment. The second half of the criterion exists because Claude fires
`session_ended` on `/clear` as well as on exit (`events.py:483-491`), so "once per session" is not
observable and must not be asserted.

**AC5 (offline) — the row gains exactly two nullable keys, and no pathname reaches the wire.**
`base_session()` (`sessions.py:263-...`) declares `dirty` and `changed`, both defaulting to `None`;
`events.PATCHABLE` (`events.py:105-107`) grows by the same two names and no others; and porcelain
pathnames never appear in `/api/data`.
*Verified by:* `test_sessions.test_every_session_row_declares_the_same_field_set`
(`tests/test_sessions.py:337-345`) with `DECLARED_SESSION_FIELDS` (`:303-334`) grown by exactly two
names, plus a test that feeds porcelain output containing a distinctive filename through the probe and
asserts that filename is absent from `aggregate.collect_json()`'s bytes.
*Falsified by:* publishing a `files` list, a sample path or a porcelain line; adding a third key; or
adding the names to `PATCHABLE` without restating them in all three `patch.update` blocks of
`reduce_overlays` (`events.py:594`, `:607`, `:620`), which would let a stale pair survive a state change.

**AC6 (offline) — an unprobed row publishes `null`, for every cause, and nothing claims `acquisition`
discloses it.**
Each of the seven causes yields `dirty: null, changed: null`: a harness with no event adapter, a harness
whose adapter has no session-end event, `--no-git`, a directory that is not a repository, an event with
no `cwd`, git absent from `PATH`, and a probe that timed out.
*Verified by:* one test per cause. The second cause must be tested with a **Codex or Antigravity** row,
whose `acquisition` reads `"event"` — `aggregate._mark_unreachable_by_events` (`aggregate.py:685-703`)
marks `scan-only` only for harnesses absent from `IDENTITY_NORMALIZERS`, so a test that asserts against
`scan-only` alone would pass while leaving two of the eight unprobeable harnesses unchecked.
*Falsified by:* defaulting `dirty` to `False` in `base_session` — every unprobed row then reads clean,
the confident-green-over-absent-evidence failure recorded at DRC-4101 — or by asserting the Codex case
through the `acquisition` marker, which cannot see it.

**AC7 (offline) — `--no-git` is on by default, disables the probe, and survives a respawn.**
*Verified by:* a parse assertion in the shape of
`tests/test_config_diagnostics.py:113 test_build_runtime_freezes_the_parsed_launch_options`;
`tests/test_lifecycle.py:1303 test_every_opt_out_reaches_the_respawned_daemon` extended to include
`--no-git`; and a coordinator test asserting zero probe invocations when the flag is set.
*Falsified by:* omitting the `lifecycle.spawn_argv` branch (`lifecycle.py:554`) — the flag is then
silently dropped on the respawned daemon, which is the defect that test was written for after
`--no-usage` was lost on Windows. Note that the seven `argparse.Namespace` fixtures in
`test_lifecycle.py` (`:247`, `:473`, `:1259`, `:1288`, `:1315`, `:1330`, `:1534`) are
positional-complete, so a missing attribute raises rather than defaulting — they are part of the
falsifier, not incidental.

**AC8 (offline) — the promotion is byte-identical, both intro amendments land, and the plan doc is gone
in the same commit.**
`SECURITY.md` carries the section between `## Project reads (Spacedock stage strips)` and `## Usage
quota reads (the quota fetcher)`, byte-identical to the merged text between the two `---` rules in
`docs/plans/git-probe-security-scope.md`; the Scope closing sentence (`SECURITY.md:65`) has gained its
clause; Invariant 2 (`:35`) has gained its sentence; and `docs/plans/git-probe-security-scope.md` no
longer exists.
*Verified by:* `git show <sha> --stat` on the single commit showing `SECURITY.md` grown and the plan doc
deleted together — the check `a98bc64` and `3e92d12` are cited for — plus a diff of the promoted span
against `git show 701b7f0:docs/plans/git-probe-security-scope.md`, plus
`python3 scripts/validate_plugins.py`, which resolves every relative link and heading anchor across the
owned docs and would fail on a dangling reference to the deleted file.
*Falsified by:* editing a word of the section during promotion, splitting the deletion into a follow-up
commit, or omitting either amendment — the second leaves the section filed under a Scope clause that
enumerates file reads, harness-store writes and non-loopback hook traffic, none of which is subprocess
execution.

**AC9 (offline) — the render says entries, and renders an unprobed row as absent.**
Wherever `changed` appears it is labelled as entries rather than files, and a row whose `dirty` is
`null` renders no dirty state at all — not "clean", not `0`.
*Verified by:* a rendering test on both frontends, since they share no JavaScript: the regular UI's
badge helper beside `spark.js:318 finishedMark()` and the next UI's own reimplementation in
`next/next-sessions.js:34-44`. `tests/test_documentation.py:94` is the precedent for pinning a JS
constant against prose and should pin the label.
*Falsified by:* rendering `changed` as a file count, or falling back to a clean badge when the value is
`null` — the same false-clean AC6 forbids on the API, one layer up.

**AC10 (offline) — both byte-pin oracle sets are recomputed from the assets.**
`tests/test_page.py:104 test_load_page_preserves_all_three_byte_oracles` and the mirror in
`tests/test_next_page.py:577-592` pass, with every figure they assert derived from the shipped bytes.
*Verified by:* the two tests passing on a branch rebased onto whatever `web/` state is on `main` at the
time, and `python3 scripts/lint_embedded.py`, whose part-inventory check (`check_stray_scripts`) imports
`web/page.py` by path so the linter and the loader cannot disagree about which parts exist.
*Falsified by:* editing a digest to match a failure message rather than recomputing — the failure that
`AGENTS.md` records as shipping a number wrong for both sides. There is no script that emits these
figures; the count is 28 in `test_page.py` (12 parts times size and digest, plus `styles.css`, plus the
assembled page) and 28 again in `test_next_page.py`.

**AC11 (interactive) — it is true of a real session.**
A person runs the dashboard, ends a real Claude session in a repository with a known dirty state, and
the row shows dirty with the porcelain entry count.
*Verified by:* a live drive, with the `SessionEnd` payload captured under `docs/captures/claude/` if its
shape differs from `hooks-2.1.222-macos.jsonl`.
*Falsified by:* the published count disagreeing with `git -c core.fsmonitor= --no-optional-locks status
--porcelain | wc -l` taken at the moment the session ended.
**No harness is planned to automate this.** The falsifier needs a real harness process to exit; AC3 and
AC4 cover the wiring offline and AC11 covers only that the wiring meets a real payload. Declared here,
at the gate, rather than discovered later.

## Expected surface and tolerance (cycle 2)

Supersedes the cycle-1 table. Split across the two PRs.

**PR 1 — contract, probe, published field.**

| Area | Files | Notes |
| --- | --- | --- |
| New runtime module | `cargento_runtime/git_status.py` | subprocess, porcelain parse, bounded timeout. Not `gitprobe.py`: `probe.py` already owns "the coarse store probe" and two names one letter apart in one package is a reading hazard. |
| Probe wiring | `observation.py` | side-channel dict, `_mark_*` writer under the `event_overlay_max_sessions` guard, public reader, off-thread dispatch (AC3) |
| Overlay plumbing | `events.py` | `PATCHABLE` (`:105-107`) plus all three `patch.update` blocks (`:594`, `:607`, `:620`) |
| Row surface | `sessions.py` (`base_session`) | two keys, both `None` |
| Row plumbing | `aggregate.py` | `OverlaySource` Protocol (`:129-136`), read in `_apply_overlays` (`:719-738`) |
| Off switch | `cli.py` ×2, `config.py` ×3, `lifecycle.py` ×1 | the six `--no-spacedock` sites, enumerated above |
| Config threshold | `config.py` | `git_probe_timeout_sec`, mirroring `usage_fetch_timeout_sec=10` (`config.py:500`). A named conflict hotspot. |
| Runtime inventory | `scripts/validate_plugins.py:131` | `CARGENTO_RUNTIME_FILES` gains the new module |
| Tests | `tests/test_git_status.py` (new), `test_observation.py`, `test_events.py`, `test_sessions.py`, `test_lifecycle.py`, `test_config_diagnostics.py` | plus the seven positional-complete `Namespace` fixtures |
| Docs | `SECURITY.md` (promotion + two amendments), `SKILL.md` flag table `:294`, `HOW_TO_USE.md` `:343`, `docs/design-runtime-architecture.md` | and delete `docs/plans/git-probe-security-scope.md` |

**Estimate: ~17 files, +420 / −120 lines. Tolerance ±35%.** The −120 is mostly the deleted plan doc.
**SUPERSEDED 2026-08-28 by the captain's re-declaration below.** Retained as written, because the
figure the build was held to is part of the record and the reason it moved is only legible against it.

#### Re-declared 2026-08-28 — accepted by the captain, not stretched

The build measured **24 files, +918 / −114** against `origin/main` at `701b7f0`: files +41.2% and
added +118.6% on a ±35% tolerance, deleted −5.0% and within. `implementation` stopped at the gate
with the work finished and green rather than opening the PR, and the captain **accepted the overrun
and re-declared** rather than authorising a trim.

**Why it moved: the estimate was wrong about test volume, not the work wrong about scope.**

| Area | Declared | Actual | Reading |
| --- | --- | --- | --- |
| Runtime | the 8 files this table names | 8 files, +310 | on estimate |
| Docs and scripts | 5 files + the deleted plan doc | 7 files, +67 / −104 | on estimate; `AGENTS.md` added by `sync-docs` |
| Tests | 6 files | 9 files, +541 | **the whole overrun** |

Three of the nine test files were **compelled by existing required checks rather than chosen**, which
is the part an estimate can be taught to see: `test_contracts.py`, because
`test_runtime_import_graph_matches_the_reviewed_allowlist` rejects any new runtime module until its
node and edges are declared; `test_notifications.py`, because it holds an `OverlaySource` fake that
must satisfy the protocol once it grows a method; and `test_documentation.py`, which carries the
drift-guard holding `SECURITY.md`'s promoted prose to the code.

The rest is the acceptance criteria's own test demands, under-costed at triage: AC2 builds two real
repositories, AC3 needs two threading oracles, AC4 two edge sequences, AC6 one test per cause across
seven causes, AC1 a repository-wide single-invocation assertion, AC5 a pathname-absence check at two
layers, AC7 three. Reaching the +35% ceiling would have meant deleting roughly 350 lines of exactly
the oracles the full-adversarial tier was routed here to examine, so no trim was offered.

**The acceptance does not generalise.** Recorded by the FO as a workflow rule at the same time: cost
the oracles separately from the runtime, and check whether any existing required check compels a new
test file, before declaring. An overrun of this shape again fixes the estimating method rather than
the tolerance.

**PR 2 — the render.**

| Area | Files |
| --- | --- |
| Regular UI | `web/spark.js` (the shared badge helper), `web/regular.js`, `web/calm.js`, `web/session.js`, `web/styles.css` |
| Next UI | `web/next/next-sessions.js`, `web/next/next-session.js`, `web/next/next-workstream.js`, `web/next/styles.css` |
| Oracles | `tests/test_page.py` (28 figures), `tests/test_next_page.py` (28 figures) |
| Tests | `tests/test_page_calm.py`, `tests/test_next_sessions.py` |

**Estimate: ~13 files, +170 / −40 lines. Tolerance ±50%** — the variance is the pins, which are counted
rather than estimated but move with whatever else lands in `web/` first.

**Semantics that may move.** `Event.cwd` gains its first consumer, so any prose repeating "no consumer"
goes stale. `SECURITY.md`'s read-only invariant gains a subprocess clause. `acquisition` does **not**
change meaning and must not be extended to cover the probe — see F2. Nothing about `project` or
`finished_at` changes.

## Review depth (cycle 2)

**Not overriding any row. Reading the table literally gives two different answers, one per PR.**

- **PR 1 — full adversarial: several lenses, a completeness critic, an arbiter.** `AGENTS.md`'s
  "Security, credential handling, or data loss" row. This PR runs a subprocess inside a directory the
  user chose, promotes a security contract, and amends an invariant. The captain's earlier reduction to
  two lenses applied to the documentation-only groundwork issue on the reading that it *described* a
  future handler; this PR *is* the handler, so that reading does not extend. Lenses worth naming: the
  subprocess surface (argv construction, environment, timeout, a symlinked or submodule repository, a
  repository the user lacks permission to read); the null-versus-false surface; the threading and
  lock-holding constraint in AC3; and whether the promoted text is byte-identical.
- **PR 2 — two lenses plus an arbiter.** `AGENTS.md`'s "Owns a conflict-prone surface (`web/` byte
  pins, `SKILL.md`, `config.py`)" row. No new power, no new read, no security surface; its risk is
  entirely that 56 pinned figures are recomputed rather than edited.

Naming this at the gate rather than assuming it, per the checklist. If the captain would rather run one
tier across both, that is a decision to make here — but the split exists precisely so it does not have
to be.

## Drafts for `implementation` to write (cycle 2)

Nothing below has been written to Linear. Three edits, all corrections; the body's structure stands.

### Draft A2 — three corrections to the live DRC-4037 body

**A2.1.** In bound 3, replace *"measured in the Claude and Droid `SessionEnd` captures"* with
*"measured in the Claude and Gemini `SessionEnd` captures"*. Reason F3: the Droid capture records no
payload keys, and Claude and Gemini are also exactly the two harnesses that can reach the probe.

**A2.2.** Replace the paragraph *"Six of the ten harnesses have no event adapter, so they can never be
probed. They disclose that through the existing `acquisition` marker and a null surface, never a false
clean."* with:

```markdown
A row can be probed only where an adapter maps a native session-end event onto `session_ended`.
Today that is Claude Code and Gemini CLI. Codex and Antigravity have adapters whose vocabularies
carry no session-end event, and the remaining six harnesses have no event adapter at all — so most
rows are never probed. They disclose that by publishing `null`, and by nothing else: the
`acquisition` marker separates adapter-less harnesses from the rest and cannot see this gap, nor
any of the other reasons a probe does not run.
```

Reasons F1 and F2. Stated as a property rather than a count, following the merged contract, because
Droid and Goose already emit `SessionEnd` natively and are unreachable only for want of an adapter.

**A2.3.** In bound 4, replace *"at every one of its six sites"* with the enumeration:
*"at each of its six sites — `cli.py` twice, `config.py` three times, and the `lifecycle.spawn_argv`
forwarding branch a respawned daemon needs."* The number is right (re-derivation 3); the enumeration is
what makes it checkable, and it is the half an implementer actually needs.

No history section changes. The two superseded sections stay as written and dated.

### Draft B2 — milestone `Nothing dies quietly`, one correction

The DEC-3 paragraph in the 2026-08-23 update now carries F1's wrong predicate, introduced by the
previous cycle. Replace the parenthetical *"(`null` meaning not probed, since six of the ten harnesses
can never emit the event)"* with *"(`null` meaning not probed, since only the harnesses whose adapter
maps a session-end event can be probed at all — today, two of the ten rows)"*.

Nothing else in the milestone moves. The Draft B annotation from the previous cycle is in place and
correct.

### Draft C2 — nothing to file

No new issue. The render is PR 2 of this issue, per **Delivery shape** above.

### Reported, not drafted — DRC-4122 carries the same wrong predicate

DRC-4122's `## Amended 2026-08-28` section states *"Six of the ten harnesses have no event adapter and
can never emit `session_ended`"* — F1 exactly, and it is where E4 inherited it. DRC-4122 is closed, and
the previous cycle's gate recorded that a dated correction note there **was not authorized** and was
being put to the captain separately. Reported here rather than drafted; if that separate question is
still open, this is a second reason to answer it.

## Out of scope (cycle 2)

Unchanged from the cycle-1 list above, with two additions:

- **Giving Codex, Antigravity, Droid or Goose a session-end event.** Droid and Goose emit `SessionEnd`
  natively and Cargento has no adapter for them; Codex and Antigravity would need a vocabulary change.
  Each is its own issue per harness, and each would widen the probe's reach without changing its bounds.
- **Extending `acquisition` to disclose the probe gap.** F2 shows the marker cannot carry it. A third
  acquisition value is a change to a field three other features read, and it is not needed: `null` is
  the disclosure.

## Stage Report: triage (cycle 2)

- DONE: The delivery SHAPE decided with reasons: whether the `SECURITY.md` promotion, the runtime probe, the published field and the frontend render are one PR or several.
  **Two PRs, split on `cargento_runtime/web/` and nothing else** — see **Delivery shape (cycle 2)**. PR 1 carries promotion, probe, published field and docs; PR 2 carries the render and the two byte-pin oracle sets.
- DONE: Two hard constraints bear on it — the promotion must land in the same PR that deletes `docs/plans/git-probe-security-scope.md`, and exactly one in-flight PR may touch `cargento_runtime/web/`.
  Constraint 1 is satisfied by PR 1: the promoted section describes running the probe and publishing two nullable fields, both of which PR 1 ships, so `SECURITY.md` is true at every commit. Constraint 2 forced the split: `gh pr list` shows the PR queue clear of `web/`, but `git diff --name-only origin/main..<branch>` shows two live sibling worktrees already in it (`docs/sync-next-ui-design-parity`, 76 files; `worktree-spacedock-boot-rendering`, 30 files).
- DONE: Recommend one shape.
  One recommended, with the two rejected alternatives and their reasons: one PR carrying everything (rejected — puts 56 byte pins on the security branch and forces the expensive tier onto the render), and three PRs (rejected — a promotion PR shipping no probe is the failure the groundwork shape prevents).
- DONE: Acceptance criteria are written only for what THIS issue delivers, each with a `Verified by:` clause naming something outside the entity and the concrete change that would falsify it.
  Eleven criteria under **Acceptance criteria (cycle 2)**, offline/interactive split declared (AC11 alone is interactive, with the reason no harness will automate it). Every `Verified by:` names a test file and line, a shipped command, or a commit-shape check. Three are new this cycle: AC3 (off-thread, off-lock), AC8 (byte-identical promotion), AC9/AC10 (the render's label and the pins). AC6 was rewritten because its cycle-1 oracle was unsound — see below.
- DONE: Every load-bearing claim in E4's own body re-derived at the current tip and every falsified one reported and drafted for correction.
  Twelve claims re-derived against `origin/main` at `701b7f0`; nine reproduce, three are falsified (F1, F2, F3), two new facts recorded (N1, N2). Corrections drafted as A2.1-A2.3 and B2; nothing written to Linear.
- DONE: the body says "Six of the ten harnesses have no event adapter, so they can never be probed", which is the exact predicate the merged contract replaced.
  **REFUTED as a predicate, and the count is wrong for this question: eight of ten, not six.** `CODEX_EVENTS` (`event_hook.py:160-166`) registers no `SessionEnd`; Antigravity maps only `working`/`idle` (`statusline_hook.py:118-121`). Root cause found: the sentence was carried over from `observation.finished_at`'s docstring (`observation.py:378-386`), where six *is* right because that field needs any overlay-producing event. Drafted as a property, not a count (A2.2), because Droid and Goose emit `SessionEnd` natively and are unreachable only for want of an adapter.
- DONE: it says `--no-spacedock` appears at "every one of its six sites" where the groundwork cycle found three.
  **Six reproduces; the groundwork cycle's three was the wrong figure.** Enumerated: `cli.py:115`, `cli.py:203`, `config.py:46`, `config.py:384`, `config.py:424`, `lifecycle.py:554-555`. The groundwork count missed `config.py`'s three. `--no-usage` occupies the identical six, which is the independent check. Drafted A2.3 to replace the number with the enumeration — the number is right, the enumeration is what an implementer can act on.
- DONE: Report any figure you cannot reproduce rather than repeating it.
  One figure is reported unreproduced rather than repeated: none of E4's own. Two figures from DRC-4122's pre-amendment record (script runs twice; unconditional index write) were already corrected upstream and were re-checked today at git 2.55.0 — script runs once, write is race resolution. A third defect is reported without a draft: DRC-4122's `## Amended 2026-08-28` carries F1's wrong predicate, and a correction note there was explicitly not authorized at the previous gate.
- DONE: Nothing written to Linear and no repository file created or modified this stage.
  Linear access was read-only (`get_issue` on DRC-4037, DRC-4122, DRC-4274; `get_milestone`). The main checkout was never checked out, pulled or written — `701b7f0` was read through `git show origin/main:<path>`. Measurements ran in `mktemp -d` directories under `/tmp`, since removed. The only files written are this entity and this report, in the state checkout.
- DONE: Review depth recommended with reasons.
  **PR 1 full adversarial; PR 2 two lenses plus an arbiter.** No row overridden — see **Review depth (cycle 2)**. Reading `AGENTS.md`'s table literally gives two answers because the split puts each PR in a different row, which is what "pick per PR, not per session" asks for. The captain's earlier reduction to two lenses is explicitly not extended: it applied to a documentation-only issue that *described* a future handler, and PR 1 *is* the handler.

### What changed the build, beyond the two known defects

Two facts nobody had written down, both found by reading the tip rather than the issue:

- **N1 — the session-end edge is on the HTTP handler thread, under the coordinator lock, behind a 2 s client timeout.** `http_api.py:838` → `observation._record`, which takes `self._lock` at `:300` and handles the retire branch at `:302-307`; `notify_hook.py:34` sets the hook client's timeout at 2 s. A synchronous probe stalls every other event *and* times out the harness's own `SessionEnd` hook. Neither the merged contract nor E4's body names this. It became AC3.
- **N2 — `session_ended` mints no overlay**, so the result has no carrier: `overlay_for()` returns `None` for it (`events.py:430`, falling through at `:478`). The pair must follow `finished_at`'s side-channel pattern and be restated in all three `patch.update` blocks of `reduce_overlays`. It became AC5's falsifier.

And one cycle-1 acceptance criterion was unsound rather than merely incomplete: AC6 proposed proving the null surface by asserting `dirty is None` on a row whose `acquisition` is `"scan-only"`. `aggregate._mark_unreachable_by_events` (`:685-703`) sets `scan-only` only for harnesses absent from `IDENTITY_NORMALIZERS`, so that test passes while leaving Codex and Antigravity — two of the eight unprobeable rows — unchecked. Rewritten to require a Codex or Antigravity row.

One frontmatter discrepancy for the FO, not mine to edit: `linear-status:` reads `Backlog`; DRC-4037 moved to `Todo` at 2026-08-28T09:00:04Z.

### Summary

The contract merged as `701b7f0` and E4 is genuinely unblocked, so this cycle's work was the shape and
the acceptance criteria rather than the argument. Recommended shape is **two PRs split on
`cargento_runtime/web/`**: the promotion, probe and published field in one, the render in the other,
because the frontend is the only surface `AGENTS.md` says forces a split and two live sibling worktrees
are already writing to it — and because splitting there lets each half take the review tier the table
actually assigns it instead of one tier for both.

Of the two known defects, one was E4's and one was not: the "six of ten harnesses" predicate is wrong
(eight, and it should be stated as a property), while "six `--no-spacedock` sites" is right and the
groundwork cycle's three was the miscount. Both are drafted. Two constraints the merged contract does
not name were found by reading the tip — the probe cannot run synchronously on the event-ingress thread,
and `session_ended` produces no overlay to carry the result — and one cycle-1 acceptance criterion
turned out to prove less than it claimed. Nothing was written to Linear and no repository file was
touched.

## Stage Report: implementation

- DONE: The authorized Linear writes performed FIRST and read back: the three drafted corrections to DRC-4037's body (A2.1-A2.3), the drafted milestone correction (B2), and one appended dated note on the closed DRC-4122 recording that its amendment section carries the wrong "six of the ten harnesses have no event adapter" predicate — appended only, its existing text unedited. Report every read-back discrepancy; they are the FO's to disposition.
  All five landed before any file was touched. A2.1-A2.3 by patch ops on DRC-4037; B2 by full-description write (milestones have no patch API); the DRC-4122 note by an `append` op, which is why nothing above it could be edited. Read back on all three surfaces — see **Discrepancies** below.
- DONE: PR 1 built and opened, touching NO file under `cargento_runtime/web/`: the section promoted from `docs/plans/git-probe-security-scope.md` into `SECURITY.md` byte-identically, the two intro amendments the document names applied, the plan document DELETED in the same commit that promotes it, the probe wired to `session_ended`, `--no-git` added at all six `--no-spacedock` sites, `dirty` and `changed` published as nullable on every row, and the doc updates. Test-first: write the failing test, watch it fail for the right reason, and say what it asserted before it passed.
  **Built, green, and opened as [#239](https://github.com/spacedock-dev/cargento/pull/239) after the captain accepted the overrun.** It was held at the surface gate first — see the re-declaration under **Expected surface and tolerance (cycle 2)** — and opened only once tolerance had been re-declared rather than stretched silently. `gh pr view` confirms no file under `web/` and neither byte-pin oracle. Every other clause is satisfied: `4ece71f` carries the promotion (byte-identical, verified against `git show 701b7f0:docs/plans/git-probe-security-scope.md`, 3231 bytes), both intro amendments, and the plan doc's deletion in that one commit; `be1723d` is the `sync-docs` pass. No file under `cargento_runtime/web/`, `tests/test_page.py` or `tests/test_next_page.py` is touched.
- DONE: The two constraints the merged contract does not name are satisfied and proven, not assumed.
  Both proven by behaviour rather than by inspection. AC3: `test_the_probe_does_not_run_while_the_coordinator_lock_is_held` calls `_lock.acquire(blocking=False)` from inside the probe and asserts it succeeds, so the assertion is about the running lock rather than about the source; `test_submit_returns_without_waiting_for_the_probe` blocks the probe on an Event and asserts `submit` has already returned. Falsifier exercised: moving the dispatch inside the `with self._lock` block does not merely fail, it **deadlocks** the suite, because a synchronous spawn re-enters a non-reentrant lock. N2: `dirty`/`changed` follow `finished_at`'s side channel (`observation._git`, `_mark_git` under the `event_overlay_max_sessions` refusal guard, `git_for` reader, `note_rows` bound) and are restated in all three `patch.update` blocks; `test_every_key_a_reducer_emits_is_patchable` and `test_the_patchable_set_is_exactly_the_documented_eight` both bite if either is dropped.
- DONE: Run the full canonical pre-PR suite from AGENTS.md.
  Read from `AGENTS.md` § Pre-PR Checks, not a copy. `ruff check` clean; `ruff format --check` 100 files formatted; `mypy` clean, 110 files; `lint_embedded.py` clean; `validate_plugins.py` clean, and `--runtime-files ./cargento` reports 88 files with the new module in the inventory; `bump_version.py --current` 0.18.0 with **no version field moved** since the merge base. Suite run **once**, load average 3.4: 1991 tests, 91.4 s, OK (1 skip). Scripts tests 192, OK. `coverage report` 90.8% against `fail_under = 73`. Native validators both pass. No red in `test_http_api`, `test_page`, `test_lifecycle` or `test_quota`, so no single-module re-run was owed.
- DONE: measure the surface against the estimate before opening the PR, review the diff in the worktree first.
  Measured before opening, which is what caught it. Diff reviewed in the worktree; `sync-docs` ran there too and found one pre-existing false claim (below).
- DONE: report the PR number and head SHA.
  **[#239](https://github.com/spacedock-dev/cargento/pull/239), head `be1723d`** on `spacedock-ensign/drc-4037`. Opened after the captain accepted the overrun and the re-declaration was recorded above. `mergeStateStatus: BLOCKED` on the required review, which is the expected state for an unreviewed PR under the ruleset. No `Closes #NNNN` line: `gh issue list` finds no mirrored GitHub issue, and the stage definition allows the line only when one actually exists.

### Surface versus estimate — the reason the PR is not open

Against `origin/main` at `701b7f0`:

| | declared | actual | delta |
|---|---|---|---|
| files | 17 | 24 | **+41.2%** |
| added | 420 | 918 | **+118.6%** |
| deleted | 120 | 114 | −5.0% (within) |

Tolerance is ±35%, so two axes are outside it. **The overrun is test volume, not scope.** Runtime is
+310 across the 8 files the estimate's own table draws; docs and scripts are +67/−104. Tests are
**+541 across 9 files**, against 6 declared. Three of the extra files were forced rather than chosen:
`test_contracts.py` (the reviewed import-graph allowlist is a required check and rejects a new
module), `test_notifications.py` (it holds an `OverlaySource` fake that must satisfy the protocol),
and `test_documentation.py` (the contract drift-guard holding `SECURITY.md`'s prose to the code).

No feature was added beyond the four bounds and the two constraints. What was under-counted is the
cost of the acceptance criteria's own test demands: AC2 builds two real repositories, AC3 needs two
threading oracles, AC4 two edge sequences, AC6 one test per cause across seven causes, AC1 a
repository-wide single-invocation assertion, AC5 a pathname-absence check at two layers, AC7 three.

Trimming to fit is not offered as an option. Reaching the +35% ceiling means deleting roughly 350
lines of the tests the ACs specify, which are exactly the oracles the full-adversarial tier was
routed here to examine. The choices are to accept the overrun, or to re-declare the estimate —
and tolerance is captain-owned, so neither is mine.

### Discrepancies on read-back — the FO's to disposition

- **A2.3 was applied to the sentence tail, not the clause as drafted.** The draft says replace *"at every one of its six sites"*. Applied literally that leaves the existing trailing clause `, including the lifecycle.spawn_argv forwarding branch that a respawned daemon needs.` standing after a replacement that already names it and already ends in a period. I replaced through the end of the sentence instead. Content is the draft's, verbatim; the span is wider than the draft's literal words.
- **Linear's round-trip mangled emphasis across DRC-4037's bounds 1, 2 and 3 and its Dependencies list — text none of my three patches touched.** Bound 3 went from `**One-shot, on the** \`session_ended\` **edge. ***(Corrected` to `**One-shot, on the **\`session_ended\` *edge. **(Corrected`, and the `Dependencies` bullets lost their bold labels. This is the known progressive, unrepairable emphasis hazard firing on a surgical patch. The three corrections themselves landed exactly as drafted. Not repaired, because repairing it means another full-body write and another round-trip.
- **The milestone did not suffer the same damage** despite being a full-description write. B2 landed clean.
- **`relatedTo` read back unchanged on both issues.** DRC-4037 holds the same five; DRC-4122 holds the same five plus its `blocks` edge on DRC-4026. No unrequested edges, and no removal was attempted.
- **DRC-4122's note rendered my `DRC-4037` reference as an `<issue …>` mention element.** Content preserved; it is Linear's mention rendering, not an edit.
- **One pre-existing doc claim was false and is corrected in `be1723d`.** `docs/design-runtime-architecture.md` called `observation.py` "the only runtime module that starts a thread"; `http_api.py`, `quota.py` and `lifecycle.py` each start one. My change made it more visible rather than causing it.

### Summary

PR 1 is built, committed and fully green on the canonical suite, and is deliberately not opened. The
promotion is byte-identical to the merged contract and dies with the plan doc in one commit; the
probe is the one bounded argv with both flags proven independently load-bearing against real
repositories rather than asserted; the two unwritten constraints are satisfied and proven by
behaviour, with the off-lock falsifier demonstrated to deadlock rather than merely fail.

What stops the PR is the surface gate: 24 files and +918 lines against a declared 17 and +420 at
±35% tolerance. The excess is test volume the acceptance criteria themselves specify, not widened
scope, and trimming it would remove the oracles the review tier exists to check. That is a captain's
call on tolerance, so it goes back rather than being decided here.

### Addendum — the captain accepted the overrun, and PR 1 is open

The tolerance question came back **accept and re-declare, do not trim**. The reasoning is recorded
in **Expected surface and tolerance (cycle 2)** rather than only here: the estimate was wrong about
test volume, not the work wrong about scope, and three of the nine test files were compelled by
existing required checks rather than chosen. The FO verified every figure independently, including
that `test_runtime_import_graph_matches_the_reviewed_allowlist` is real, before putting it up.

Order of operations, deliberately: the re-declaration landed in this entity **before** the PR opened,
so a reviewer arriving at #239 reads the corrected surface rather than the stale one.

A workflow rule was attached to the acceptance and is not this stage's to apply, but is recorded so
the next estimate inherits it: **cost the oracles separately from the runtime, and check whether any
existing required check compels a new test file, before declaring.** An overrun of this shape again
fixes the estimating method rather than the tolerance.

Both disclosed judgement calls stand as made — A2.3 applied to the sentence tail, and the emphasis
mangling left unrepaired.

**PR [#239](https://github.com/spacedock-dev/cargento/pull/239), head `be1723d`.** `mergeStateStatus`
is `BLOCKED` pending the full-adversarial review the PR body routes to itself. PR 2 — the render and
the two byte-pin oracle sets — is a separate round after this one merges, and E4 is not `Done` until
it lands.

### CI green on `be1723d`, and one figure reconciled

**All required checks pass on the PR head**, including `platform-tests` on all three runners:
`quality-gate`, Tests on ubuntu / macos / windows, Tests + coverage threshold, Runtime floor
(Python 3.11), Lint, Type check, `validate`, `version-guard`, `latest-client-smoke`.
`mergeStateStatus` stays `BLOCKED` on the required review, which is the expected state.

**A weakness in my own test, disclosed rather than left for review.** The two hazard tests build a
POSIX shell script for `core.fsmonitor`. A positive control run by hand confirms the mechanism is
live where it was checked — unflagged, the hook fires; flagged, the log is never created — so the
assertion is genuine on macOS and Linux. On Windows it may pass because nothing could execute rather
than because the flag worked. It is not a false green on the flag itself, which
`test_the_probe_is_exactly_the_one_bounded_command` pins on every platform, but it is weaker on one
runner than it reads as. The fix is a positive control inside the test (assert the hook DOES fire
without the flag, so the test proves the mechanism is armed on whatever platform it runs on). Not
added unilaterally: the PR is open and this would cost a second CI cycle, so it is the FO's to
authorize as a fix now or file as deferred risk.

**The `once` versus `twice` figure is not a contradiction — both are right, and the variable is the
hook's exit status.** DEC-3 recorded the `core.fsmonitor` script running twice per invocation;
triage re-measured at git 2.55.0 and recorded once, and DRC-4122's amendment and E4's bound 1 both
carry that as a correction of a wrong figure. Measured here at git 2.55.0, same machine, identical
repositories, varying only the hook's exit code:

| hook exits | invocations |
| --- | --- |
| `0` | 1 |
| `1` | 2 |

Git re-runs the hook when it signals failure. So the original figure was not an error, it was a
different hook, and the record currently reads as though someone had miscounted. The security
consequence is unchanged and both records already say so. **Nothing shipped repeats either figure**
— the promoted `SECURITY.md` section deliberately states no count, which is why this reconciliation
touches the Linear record only and not the artifact. Reported, not drafted: DRC-4122 is closed and
its correction note is already written, so any further edit there is the FO's to disposition.
