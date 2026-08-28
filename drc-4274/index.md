---
id: drc-4274
title: Git probe groundwork · SECURITY.md scope section for the end-of-session git probe
status: review
source: https://linear.app/recce/issue/DRC-4274
started: 2026-08-28T07:32:51Z
completed:
verdict:
score: 0.7
worktree: .worktrees/spacedock-ensign-drc-4274
issue:
pr: "#238"
mod-block:
linear-status: 'Backlog'
milestone: 'Nothing dies quietly'
release: 'r2'
estimate: ''
reconciled:
gates:
    version: 1
    records:
        - id: gate:drc-4274:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4274-triage-1
              briefing:
                id: briefing:drc-4274:triage:attempt-1:revision-1
                digest: sha256:6b78d36f0137009cd97d5df36ef8323c1a865c5f6f1d6a45e311c59a495d865c
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4274:triage:1
                briefing: briefing:drc-4274:triage:attempt-1:revision-1
                by: person:captain
                at: "2026-08-28T07:56:48.838004Z"
                decision: approve
                reason: |-
                    APPROVED, both asks.

                    (1) THE PLAN: the additive rewrite of DRC-4274 (nothing in the body was falsified, so nothing needed demoting), the narrow milestone correction restating bound 2 in its amended nullable form, and the plan document scope — the six elements DEC-3 requires plus a SEVENTH the issue body did not cover: an intro-amendment section naming the SECURITY.md sentences that change. That addition is the substantive finding of this stage. The Scope violation sentence enumerates FILE READS and this probe is SUBPROCESS EXECUTION, so without it E4 would promote a section into a Scope whose own violation clause does not reach it. The quota precedent handled exactly this the same way.

                    (2) THE REVIEW-DEPTH REDUCTION, from full adversarial to two lenses plus an arbiter, is approved, and it is recorded as a deliberate override of a written AGENTS.md row rather than an oversight. Two rows of the Calibrating Effort table both reach this change and disagree: the security row, and the row for a change with no user-visible behaviour that nothing calls yet. Triage named the conflict openly instead of resolving it silently, and its reading is accepted — the security row exists for code that HANDLES sensitive material, and this diff only DESCRIBES a future handler, with no probe, no flag, no caller and no runtime surface in it. What is actually at risk is factual error in claims that get promoted verbatim into SECURITY.md unread, which two re-derivation lenses cover better than six diff-reading lenses cover a diff containing no code. AGENTS.md's own Calibrating Effort section records that uniform review is the expensive mistake.

                    THE ESCALATION TRIGGER IS PART OF THIS APPROVAL: escalate to full adversarial if the document specifies anything beyond the seven elements, or if either lens finds a claim that does not reproduce.

                    Evidence quality noted: both check-set questions were settled by exercise rather than by reading — the validator owned-set claim proved on a `git archive HEAD` copy where a deliberately broken scratch file produced exactly two errors and exit 1, and the CI detector simulated with its real is_prose function against the live derived list. The stage also refuted one of the FO's own premises, that two tests open a docs/plans path literally, when only one does.
              application:
                target-stage: implementation
                state: consumed
        - id: gate:drc-4274:review
          stage: review
          attempts:
            - id: gate-attempt:drc-4274-review-1
              briefing:
                id: briefing:drc-4274:review:attempt-1:revision-1
                digest: sha256:630a2c7dfa12240736694da9057e6e83b2427e30930574cce356517b3051147c
                room-ref: ./review/review/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4274:review:1
                briefing: briefing:drc-4274:review:attempt-1:revision-1
                by: person:captain
                at: "2026-08-28T08:29:36.856268Z"
                decision: revise
                reason: |-
                    REVISE — accepts the direction, one concrete ask before merge.

                    The captain accepts the reviewer's GO on substance. Both lenses ran as separated passes, every measurement in the deliverable reproduced, the escalation trigger was tested against the recovered precedent rather than waved off, and AC2 was proven from the aggregator's own mechanism rather than from the report. Nothing about that is being rejected.

                    THE ONE ASK: doc line 46 currently reads "Six of the ten harnesses have no event adapter and can never emit `session_ended` at all". That sentence is the captain's own amendment text transcribed verbatim, and it is literally true, but its plain reading tells a future reader that the other four harnesses can be probed. They cannot. The FO arbiter reproduced this rather than taking it from the review: CODEX_EVENTS at event_hook.py:160 carries no SessionEnd mapping, codex-hooks.json registers none, agy_hook.py emits only store_changed and says so in its own comment, and only two mappings in event_hook.py produce session_ended. So eight of ten rows can never be probed, not six.

                    WHY THIS IS WORTH A CORRECTION ROUND RATHER THAN A FOLLOW-UP FILING: this document is promoted into SECURITY.md unchanged and then deleted, so the sentence lands in the security posture with nobody reading it again in between. An understatement of how little coverage exists is precisely the class of error that must not ship there. The PR is prose-only with a two-minute check cycle, so the round is cheap. This is not a deferred finding being promoted into the current PR — it is a confirmed inaccuracy in the deliverable itself.

                    TWO CONSTRAINTS ON THE FIX, both from findings this cycle already produced. First, do not replace it with a harness name list or a hard count that will go stale inside a verbatim-promoted document — the implementation's own pre-PR diff review caught exactly that hazard and removed a six-harness list for it. Second, the amendment text on DRC-4122 is the captain's and is not being changed by this round; only the deliverable's wording is.

                    The rest of the document stands. The three other findings are dispositioned as recorded: the twice-versus-once refutation is conditional on hook exit code and the document is correct under both because it carries no run count, which vindicates the implementation's wording and must not be "fixed"; the race-resolution characterisation is confirmed; and the working-directory retention claim belongs in DRC-4037's design rather than this PR.

                    AFTER THE FIX: the reviewer re-verifies the corrected line and the unchanged remainder, then the merge proceeds.
review-round:
    id: round:drc-4274:review:1
    stage: review
    cycle: 1
    briefing:
        id: briefing:drc-4274:review:attempt-1:revision-1
        digest: sha256:630a2c7dfa12240736694da9057e6e83b2427e30930574cce356517b3051147c
        room-ref: ./review/review/round-1
---

[DRC-4274](https://linear.app/recce/issue/DRC-4274) — filed 2026-08-28 by this workflow's E4 cycle,
following the DRC-4061 and DRC-4177 precedent, so that a security amendment is reviewed on its own
terms rather than buried in a diff with the code it authorizes.

**Documentation only.** Delivers `docs/plans/git-probe-security-scope.md`. The precedent was traced
by commit at both ends rather than by resemblance: the plan doc lands in its own PR
(`7134a01` #71, `5ede7d1` #143), and a later implementation PR promotes it into `SECURITY.md` and
deletes it (`a98bc64`, `3e92d12`).

**Release row `r2` is inherited, not labelled.** It carries no `release:*` label and settles
DRC-4037 (E4), which is `release:r2` — so `burndown` gives it that row. It is the first entity on
this board whose deliverable is a repository change.

The amendment must state the bound, the published surface, what is never read, that the mechanism is
subprocess execution rather than a file open with the two flags that make it non-writing and
non-executing, the cadence bound, and the off switch. **Both bounds as amended 2026-08-28:** the
probe fires on `session_ended`, not `finished_at`; and the surface is nullable, `None` meaning not
probed. Do not repeat DEC-3's "twice in one invocation" figure — it did not reproduce, running once
at git 2.55.0 — and do not carry its "unconditional write" phrasing, the index write being race
resolution.

## Problem

DEC-3 ([DRC-4122](https://linear.app/recce/issue/DRC-4122)) was ruled **option B, straight** on
2026-08-28, and the ruling puts the `SECURITY.md` amendment **before any code**. Nothing has been
written yet. Until it is, [DRC-4037](https://linear.app/recce/issue/DRC-4037) (E4, risk-adjusted 74,
the highest unshipped score in this milestone) has no contract to build against and would have to
invent one in the same PR that implements it — which is the shape DEC-1 and DEC-2 both refused.

The narrower problem is that `SECURITY.md` describes shipped behaviour at every commit, and releases
here are cut from `main` by tag. A standalone `SECURITY.md` PR would leave the file documenting a
probe that does not exist for the whole window between the two merges. That window is real, not
theoretical.

## Proposed approach

Draft the section verbatim in `docs/plans/git-probe-security-scope.md`, merge it as its own
documentation-only PR, and let DRC-4037's PR promote it into `SECURITY.md` unchanged and delete it.

This is the shape both prior read/network amendments used, traced by commit at both ends rather than
by resemblance: the plan doc lands in its own PR (`7134a01` in #71, `5ede7d1` in #143), and the
implementation PR promotes and deletes it (`a98bc64`, `3e92d12`). Neither file is in the working tree
today, which is the promotion contract having worked twice.

**Simplest rejected alternative.** Amend `SECURITY.md` directly in this PR. Rejected because it
publishes a contract for a probe that does not exist, and a release tagged from `main` inside that
window ships a security document that is false about its own product. The plan-doc indirection costs
one extra PR and buys the invariant that `SECURITY.md` is never ahead of the code.

## Adversarial read against the current codebase

Six claims were checked against the repository rather than against the issue's own prose. Five
reproduced; one claim **in this workflow's own scope notes** did not.

**1. "plans included" is TRUE, and the grep that appears to refute it is looking for the wrong
thing.** `grep -n plans scripts/validate_plugins.py` returns nothing, but `validate_repo_docs`
reaches every plan document through `(ROOT / "docs").rglob("*.md")` at
`scripts/validate_plugins.py:1209` — a recursive glob, not a path literal. Proved by exercise on a
throwaway `git archive HEAD` tree: a scratch `docs/plans/git-probe-security-scope.md` carrying one
unresolvable relative link and one unresolvable heading anchor produced exactly two errors and exit
1, against exit 0 on the pristine copy. The document will be link- and anchor-checked.

**2. The scope note's second premise is wrong, and it matters for the check set.**
`test_notifications.py:1300` does **not** open `docs/plans/native-notifications.md` — the path
appears there inside a `#` comment. The only genuine literal in the whole test tree is
`docs/plans/event-driven-session-observation.md` at `test_documentation.py:216`, which is a real
`assertIn` against the file's text. So the CI detector's derived deny-list has exactly one entry
today, not two.

**3. The CI change-detector will classify this PR as prose.** Simulating the `is_prose` shell
function from `.github/workflows/quality-gate.yml` against the real derived `ASSERTED` list:
`docs/plans/git-probe-security-scope.md` → prose (`code=false`);
`docs/plans/event-driven-session-observation.md` → code (`code=true`), because a test names it. A
*new* plan file cannot be in a deny-list derived from literals in the existing tests, so the five
measurable jobs skip and only `validate` and `version-guard` run.

**4. The `changed` semantic re-measured at git 2.55.0.** In a fresh repository, one modified tracked
file plus an untracked directory holding three files yields **2 porcelain entries for 4 changed
files** — git collapses the directory to a single `?? newdir/`. The issue's wording ("counts
porcelain entries rather than files") is exact and must not be softened to "files".

**5. The off switch's respawn site exists.** `--no-spacedock` is declared at `cli.py:115`, wired at
`cli.py:203`, and forwarded on respawn at `lifecycle.py:554-555`. The issue's requirement that
`--no-git` mirror it "including the respawn forwarding branch" names a real branch: a restarted
daemon that dropped the flag would re-enable a probe the user turned off.

**6. Nothing in the issue body was falsified.** No content required demotion to a historical section
— the body is one day old and written by this workflow's own E4 cycle. The drafted rewrite below is
therefore **additive**, and the dated triage note is the correct form rather than a demotion.

### One thing the issue body does not yet require, and should

`SECURITY.md`'s **Scope** section closes with the violation sentence at lines 62-65, which enumerates
"file reads outside the documented store paths and the project-read contract below (however the path
was derived), writes to harness stores, or the hook client reaching a non-loopback destination."
**Subprocess execution inside a user's repository is not a file read**, so the probe is not covered by
that sentence as written. The quota precedent handled exactly this with an
`## Intro amendments that ride with the promotion` section naming the sentences that change. This
document needs the same, or E4 promotes a section into a Scope whose own violation clause does not
reach it. No count in `SECURITY.md` changes: the probe adds no forwarder and no endpoint.

## Linear edits made

**Nothing has been written to Linear. This gate authorizes that write.** `implementation` performs it.

### Pre-edit record — DRC-4274 issue body, verbatim as of 2026-08-28

> Foundation ticket for the end-of-session git probe. [DRC-4122](<https://linear.app/recce/issue/DRC-4122/dec-3-decision-let-cargento-read-git-state-inside-your-repositories>) (DEC-3) was decided **option B, straight** on 2026-08-28, and the build it gates is [DRC-4037](<https://linear.app/recce/issue/DRC-4037/e4-ended-with-uncommitted-work>) (E4).
>
> This ticket is **documentation only**. It exists because DEC-3 puts the `SECURITY.md` amendment before any code, as DEC-1's was. That shape is [DRC-4061](<https://linear.app/recce/issue/DRC-4061/quota-groundwork-securitymd-scope-section-for-the-quota-fetcher>) for DEC-1 and [DRC-4177](<https://linear.app/recce/issue/DRC-4177/ask-lane-groundwork-securitymd-scope-section-for-ask-operator>) for DEC-2: a separate issue whose whole deliverable is a `docs/plans/*-security-scope.md` file holding the section verbatim, merged as its own PR, promoted into `SECURITY.md` unchanged by the implementation PR, and deleted on promotion. Both were checked at both ends by commit rather than by resemblance — the plan doc added in its own PR (`7134a01` in #71, `5ede7d1` in #143), then promoted and deleted in `a98bc64` and `3e92d12`.
>
> Keeping that shape is what lets `SECURITY.md` describe only shipped behaviour at every commit. A standalone `SECURITY.md` PR breaks it: between the two merges the file documents a probe that does not exist, and releases here are cut from `main` by tag, so that window is real rather than theoretical.
>
> ## What to write
>
> Draft the section verbatim in `docs/plans/git-probe-security-scope.md`, scoped the way the existing read exceptions are scoped: exactly what is read, exactly what is published, hard boundaries. On the file-read axis this is the **second** amendment, after the Spacedock frontmatter carve-out that landed in `0a73535` with its section in the same commit as its code, and the first read-axis amendment ever put to a filed decision before the code.
>
> * **The bound.** The probe is exactly `git -c core.fsmonitor= --no-optional-locks status --porcelain`, or there is no probe.
> * **The mechanism is subprocess execution rather than a file open**, and both flags are load-bearing. Measured 2026-08-28 at git 2.55.0 across four fresh probe repositories, one probe each, from an identical racy-clean state: without `--no-optional-locks` the probe rewrites `.git/index`; without `-c core.fsmonitor=` a repo-local `core.fsmonitor` script is executed under Cargento's identity. Each flag disarms exactly one hazard and neither disarms the other's, so neither may be dropped. Two figures from DEC-3's record do not survive re-measurement and must not be carried into the text: the fsmonitor script ran at least once rather than twice, and the index write is race resolution rather than an unconditional per-invocation write — which is the normal case in a repository a live session is editing, not a corner case.
> * **The published surface, and its nullability.** Two fields per session, `dirty` and `changed`, and nothing else. `changed` counts porcelain entries rather than files, because git collapses an untracked directory to a single entry. Both fields are nullable and `null` means not probed — never a confident clean over no evidence. Six of the ten harnesses have no event adapter and can never be probed at all, so most rows will carry `null`.
> * **What is never read.** File contents, diffs, blob reads, and branch or upstream state of any kind. Porcelain emits pathnames; they are working data — matching hints, never echoed to `/api/data`, the wording `SECURITY.md` already uses for `cwd`.
> * **The cadence bound.** One-shot on the `session_ended` edge: never a poll, never on demand, never on a turn stop.
> * **The off switch. **`--no-git`, mirroring `--no-spacedock` at every one of its sites, including the respawn forwarding branch a restarted daemon needs. The probe is on by default and the flag turns it off.
>
> ## Done when
>
> * `docs/plans/git-probe-security-scope.md` is merged holding the section text verbatim, and `python3 scripts/validate_plugins.py` passes (it resolves relative links and heading anchors across the owned docs, plans included).
> * [DRC-4037](<https://linear.app/recce/issue/DRC-4037/e4-ended-with-uncommitted-work>) can quote the contract instead of inventing it, and its PR promotes the section into `SECURITY.md` unchanged and deletes the plan doc.

### Drafted rewrite — DRC-4274 issue body

The body above is **retained unchanged**. Nothing in it was falsified, so there is nothing to demote.
Three additions go at the end, under one dated heading, and one bullet gains a clause.

Amend the **published surface** bullet's first sentence to end: `...and nothing else. Both fields are
nullable; the shape is` `{dirty: bool | None, changed: int | None}`. *(The prose already says
nullable; the shape is what DRC-4037 will implement and it is not written down anywhere on this
issue.)*

Append:

> ## Triage note, 2026-08-28 — what was verified, so nobody re-derives it
>
> **The check set is settled, with evidence.** `grep -n plans scripts/validate_plugins.py` returns
> nothing, and the "plans included" claim in **Done when** is nevertheless true: `validate_repo_docs`
> reaches plan documents through `(ROOT / "docs").rglob("*.md")` at `scripts/validate_plugins.py:1209`,
> a recursive glob rather than a path literal. Confirmed by exercise on a throwaway tree — a scratch
> plan file with one bad relative link and one bad heading anchor produced two errors and exit 1.
>
> **This PR is prose as far as CI is concerned, and that is derived rather than assumed.** The
> `changes` job in `.github/workflows/quality-gate.yml` builds its deny-list by grepping
> double-quoted `"docs/*.md"` literals out of the test tree. That list has exactly one entry today,
> `docs/plans/event-driven-session-observation.md`. A file that does not exist yet cannot be in it, so
> `code=false`, the five measurable jobs skip, and `validate` plus `version-guard` are what report.
> AGENTS.md's documented prose short path says the same thing from the other side. The PR must
> therefore stay prose-only: one new file under `docs/plans/`, and nothing else.
>
> **`changed` re-measured at git 2.55.0.** One modified tracked file plus an untracked directory of
> three files gives **2 porcelain entries for 4 changed files**. "Entries, not files" is exact.
>
> **The Scope violation sentence does not reach this probe.** `SECURITY.md`'s Scope closes by
> enumerating file reads, harness-store writes and non-loopback hook traffic. Subprocess execution
> inside a user's repository is none of those. The document must carry an intro-amendment section
> naming the sentence that changes, as `quota-fetch-security-scope.md` did, or the promoted section
> lands under a clause that does not cover it. No count in `SECURITY.md` changes.

### Pre-edit record — milestone "Nothing dies quietly", the one paragraph being corrected, verbatim

The full description is ~4,000 words and is correct everywhere else; only the clause below is
falsified by DEC-3's own same-day amendment. A paragraph-scoped pre-edit record is recorded for a
paragraph-scoped edit, rather than inlining the whole description. Flagged as a deliberate departure
from the stage definition's "verbatim" for proportionality — the gate can audit the edit from this.

> [DRC-4122](<https://linear.app/recce/issue/DRC-4122/dec-3-decision-let-cargento-read-git-state-inside-your-repositories>) landed on **option B, straight**: Cargento may run a bounded `git status` probe inside a user's working repository and publish, per session, only whether the tree is dirty and how many entries changed. Four bounds are part of the ruling rather than commentary — a probe that neither writes nor executes repository-supplied code, a published surface of exactly a dirty flag and a changed count with pathnames kept as matching hints that are never echoed, one-shot at session end rather than a poll, and an off switch that is on by default. The `SECURITY.md` amendment lands before any code, as DEC-1's did, in its own PR.

### Drafted correction — milestone "Nothing dies quietly"

The paragraph states bound 2 in its **pre-amendment, non-nullable** form. DEC-3 was amended the same
day it was ruled: the surface is `{dirty: bool | None, changed: int | None}`, `None` meaning not
probed. Replace the bounds clause with:

> Four bounds are part of the ruling rather than commentary — a probe that neither writes nor executes repository-supplied code, a published surface of exactly a nullable dirty flag and a nullable changed count (`null` meaning not probed, since six of the ten harnesses can never emit the event) with pathnames kept as matching hints that are never echoed, one-shot on the `session_ended` edge rather than a poll, and an off switch that is on by default. *(Bounds 2 and 3 corrected 2026-08-28 to match the amendment recorded on DEC-3 the same day: the surface is nullable, and the edge is `session_ended` rather than the `finished_at` turn-stop stamp.)*

Nothing else in the milestone changes. It does not mention DRC-4274 and does not need to — it names
the amendment landing "before any code, in its own PR", which is this issue.

## Expected surface and tolerance

**One new file, `docs/plans/git-probe-security-scope.md`, and nothing else.**

- Estimate **110 lines ± 30**. The two precedents bracket it: `quota-fetch-security-scope.md` was 84
  lines for four required elements, `ask-operator-security-scope.md` was 193 for a feature with two
  routes and a measurement section. This has six required elements and no protocol design, so it
  belongs between them and nearer the lower end.
- **No `AGENTS.md` change.** Its docs table already lists `docs/plans/*.md` as a glob, so a new plan
  file needs no row.
- **No `SECURITY.md` change**, no code, no test, no manifest, no version field.
- **Tolerance breach = check-set change.** Any file outside `docs/plans/` flips the CI detector to
  `code=true` and the full canonical suite becomes owed. If the diff grows, re-run the detector
  simulation before deciding what to run.

**Semantics this change may move: none in code.** It moves one documentation semantic — it fixes the
contract DRC-4037 is held to, so a defect here propagates verbatim into `SECURITY.md` on promotion.
That is the whole risk of this entity and the reason its acceptance criteria point outward.

## Acceptance criteria

Each names something outside this entity and the concrete change that would falsify it.

**AC1 (offline) — The document is link- and anchor-clean under the repository's own validator.**
`python3 scripts/validate_plugins.py` exits 0 with the file in the tree.
*Verified by:* `validate_repo_docs` reaching it via `(ROOT / "docs").rglob("*.md")` at
`scripts/validate_plugins.py:1209`. *Falsified by:* any relative link target or `#heading` anchor in
the document that does not resolve — demonstrated on a throwaway tree, where one of each produced
exactly two errors and exit 1.

**AC2 (offline) — The PR is prose-only, and CI's own detector agrees.**
The merged diff touches exactly one path, `docs/plans/git-probe-security-scope.md`.
*Verified by:* the `changes` job emitting `code=false`, with the five measurable jobs reported
`skipped` and `validate` and `version-guard` reported green on the PR's current head.
*Falsified by:* any second path in the diff, which puts the file outside the `is_prose` prose set and
makes the full canonical suite owed; or a `skipped` job whose upstream dependency died rather than
being filtered, which AGENTS.md notes the aggregator rejects.

**AC3 (offline) — The bound is the exact command, and both flags are justified by the hazard each
alone disarms.** The document names
`git -c core.fsmonitor= --no-optional-locks status --porcelain` and states that dropping either flag
re-arms a distinct hazard.
*Verified by:* DEC-3's 2026-08-28 amendment, which records four fresh probe repositories showing each
flag independently load-bearing; and by the command running clean at git 2.55.0.
*Falsified by:* text presenting either flag as belt-and-braces, or naming a plain `git status`
fallback, which DEC-3 bound 1 forbids outright.

**AC4 (offline) — The published surface is two nullable fields, and `changed` is entries.**
The document states `{dirty: bool | None, changed: int | None}`, `null` meaning not probed, and
defines `changed` as porcelain entries.
*Verified by:* re-measurement in a throwaway repository — one modified tracked file plus an untracked
three-file directory yields 2 entries for 4 files at git 2.55.0; and by DEC-3's bound-2 amendment.
*Falsified by:* defining `changed` as a file count, which the measurement contradicts; or a
non-nullable surface, which would publish a confident clean for the six harnesses that can never emit
`session_ended`.

**AC5 (offline) — The cadence bound names the `session_ended` event, never `finished_at`.**
*Verified by:* DEC-3's bound-3 amendment, and by `finished_at` being a turn-stop stamp written by
`_mark_finished` on every idle overlay and popped on every working overlay.
*Falsified by:* the document naming the completion stamp, which would specify a once-per-turn-stop
probe — forty turns, forty subprocesses in the user's repository — the exact poll bound 3 forbids.

**AC6 (offline) — The off switch reaches the respawn path.**
The document specifies `--no-git`, on by default, and names daemon respawn as a site it must reach.
*Verified by:* `--no-spacedock`'s three sites, `cli.py:115`, `cli.py:203` and `lifecycle.py:554-555`,
the last being the respawn forwarding branch.
*Falsified by:* describing the switch as a CLI flag only, which would let DRC-4037 ship a daemon that
re-enables the probe on restart after the user disabled it.

**AC7 (offline) — The promotion contract DRC-4037 depends on is stated in the document itself.**
It says the section is promoted into `SECURITY.md` unchanged and this file deleted in the same PR,
and it names the intro amendment to Scope's violation sentence.
*Verified by:* both precedents having done exactly this — added in `7134a01` (#71) and `5ede7d1`
(#143), promoted and deleted in `a98bc64` and `3e92d12` — and neither file being in the tree today.
*Falsified by:* DRC-4037's PR promoting the section while leaving the plan doc in place, which leaves
the contract stated twice and free to drift; or promoting into a Scope whose violation clause
enumerates only file reads and so does not reach a subprocess execution.

**AC8 (interactive) — The section reads as a contract, not as rationale, at the length the precedents
set.** A reviewer confirms it is scoped like the two existing read exceptions (exactly what is read,
exactly what is published, hard boundaries) and that all six required elements are present.
*Verified by:* a human read against `quota-fetch-security-scope.md`'s 84-line shape.
*Falsified by:* a document that argues for the probe rather than bounding it, or that omits any of the
six. **No harness is planned to automate this**; it is a judgement about prose and it is declared
interactive here rather than dressed up as a check.

**Deliberately not an acceptance criterion.** "The document does not contain the word *twice*" and
similar greps over our own prose. A substring search over a file this workflow wrote proves only that
we wrote what we wrote. The two non-reproducing DEC-3 figures are handled as a **review instruction**
under Review depth instead, where a human is the check.

## Test plan

**Run, locally, before opening the PR:**

```bash
python3 scripts/validate_plugins.py
```

That is the whole suite this PR owes, and the reasoning is derived rather than assumed. AGENTS.md's
documented prose short path exempts a `docs/` file that no test opens by literal path; the CI
detector derives that set by grepping double-quoted `"docs/*.md"` literals from
`cargento/skills/cargento/tests/*.py`, which yields exactly one entry today, and a file that does not
yet exist cannot be in it. Simulating `is_prose` against the real list classifies
`docs/plans/git-probe-security-scope.md` as prose.

**Do not run the full unittest suite for this diff.** It measures nothing a prose-only change can
affect, and AGENTS.md's Parallel Work section records that concurrent suites here manufacture
failures that read as regressions — loopback port collisions in `test_http_api`, `--diagnose`
subprocess timeouts, `test_quota` socket timeouts. Several sibling worktrees are live. Running it
would cost time and risk a false red.

**Confirm on the PR, not just locally:** that `validate` and `version-guard` are green against the
current head, and that the five measurable jobs show `skipped` with `changes` having emitted
`code=false` — a job skipped because an upstream dependency died also shows `skipped` and fails the
gate.

**If the diff grows beyond `docs/plans/`,** re-run the detector simulation and fall back to the full
canonical pre-PR suite in AGENTS.md. Do not carry this short path forward on memory.

## Review depth

_Written at triage. This is security-surface work: AGENTS.md routes it to full adversarial review._

**Recommendation: two lenses plus an arbiter, not full adversarial — and the tension is named rather
than resolved silently.**

AGENTS.md's table has two rows that both reach this change and disagree. "Security, credential
handling, or data loss" says full adversarial. "No user-visible behaviour change and nothing calls it
yet" says self-verify. The honest reading is that the security row exists for code that *handles*
credentials or data, and this change only *describes* a future handler: there is no probe, no flag, no
caller, and no runtime surface in the diff.

What is genuinely at risk is **factual error in the claims**, because the section is promoted verbatim
and an error propagates into `SECURITY.md` unread. Two re-derivation lenses cover that better than six
diff-reading lenses cover a diff with no code in it, and AGENTS.md's own Calibrating Effort section
records that uniform six-agent review is what cost 4h27m and 6.9M tokens for 10 blocking findings.

- **Lens 1 — re-derive the measurements.** The two flags, the entries-not-files collapse, the
  `finished_at` vs `session_ended` distinction, the `--no-spacedock` sites. Refute by default.
- **Lens 2 — check the section against DEC-3's ruling *and its amendments*.** The amendments are
  appended below the ruling on DRC-4122, so a reader who stops at the ruling gets bounds 2 and 3
  wrong. This lens must confirm both non-reproducing figures are absent: the fsmonitor script ran
  **once**, not twice, and the index write is **race resolution**, not unconditional.
- **Arbiter — reproduce findings rather than rank them.**

**Escalate to full adversarial if** the document ends up specifying anything beyond the six elements,
or if either lens finds a claim that does not reproduce.

### Feedback Cycles

- Cycle 1: REVISE — review gate, one ask; surface 1 file/102 LOC vs estimate 110 ± 30 (93%); AC unchanged

## Out of scope

- **`SECURITY.md` itself.** The section is drafted here; promotion is DRC-4037's PR. Writing it now
  would document a probe that does not exist.
- **Any code.** No probe, no `--no-git` flag, no collector, no config field, no test.
- **Applying the intro amendment.** This document *names* the Scope sentence that must change; it
  does not change it.
- **Branch or upstream state.** DEC-3 option C, neither chosen nor refused. The document must state
  branch state is never read; it must not reserve room for it.
- **Pull-request state and any outbound call.** That is E5 / DRC-4038, re-gated on DEC-8
  ([DRC-4273](https://linear.app/recce/issue/DRC-4273)).
- **Re-litigating DEC-3.** It is ruled and closed. Bounds 1 and 4 are unchanged; 2 and 3 are amended.
- **C7 / DRC-4026.** Cancelled, not released — bound 2 makes it doubly unreachable.
- **Writing anything to Linear.** `implementation` does that, after this gate.

## Stage Report: triage

- DONE: The exact pre-PR command set that applies to this PR is established WITH EVIDENCE, not assumed.
  Both claims tested. "Plans included" is TRUE via `(ROOT/"docs").rglob("*.md")` at `scripts/validate_plugins.py:1209` — proved by exercise on a `git archive HEAD` tree: pristine copy exit 0, scratch plan file with one bad link + one bad anchor gave exactly 2 errors and exit 1.
- DONE: confirm or refute whether a file under `docs/plans/` is actually in its owned set.
  Confirmed in the owned set. The `grep -n plans` miss is explained: the coverage is a recursive glob, never a path literal, so no grep for "plans" could ever have found it.
- DONE: AGENTS.md's documented prose short path ... while `test_documentation.py` and `test_notifications.py` each open an existing `docs/plans/*.md` by literal path.
  **Refuted, and the scope note is wrong here.** `test_notifications.py:1300` carries the path in a `#` comment, not an open. The only real literal is `docs/plans/event-driven-session-observation.md` at `test_documentation.py:216` (an `assertIn`). The CI deny-list has one entry, not two.
- DONE: State which commands must run and why, and whether CI's own change-detector will agree.
  `python3 scripts/validate_plugins.py` alone. Simulated the real `is_prose` function from `quality-gate.yml` against the live derived `ASSERTED` list: the new file classifies as prose (`code=false`), the existing asserted one as code. CI agrees by construction — a file that does not exist cannot be in a list derived from existing test literals.
- DONE: The shape of the deliverable is taken from the two precedents as they actually were.
  Recovered both from history. `7134a01:docs/plans/quota-fetch-security-scope.md` — 84 lines, 4 headings, section fenced by `---` with "It contains no relative links on purpose", plus `## Intro amendments that ride with the promotion`. `5ede7d1:docs/plans/ask-operator-security-scope.md` — 193 lines, 9 headings, a measurement section, a `SECURITY.md` recount section, `## What the build PR does with this file`, `## Done when`. Neither is in the tree; both were deleted on promotion.
- DONE: report what section structure, length and level of specificity they actually used.
  Recorded under Expected surface (110 ± 30 lines, bracketed by 84 and 193) and Out of scope. The "never read" boundary in both was enumerated positively and negatively — quota named the two endpoints exactly and forbade unlisted ones; ask named the index-not-string rule as "the load bearing security decision".
- DONE: Acceptance criteria are written for the plan document itself, each with a `Verified by:` clause naming something outside this entity and the concrete change that would falsify it.
  Eight ACs, seven offline and one interactive (AC8, declared interactive with no harness planned rather than dressed up as a check). A prose-grep AC over our own text is explicitly declared out, with the reason, and routed to Review depth as a human instruction.
- DONE: Nothing is written to Linear and no repository file is created or modified this stage.
  No Linear write of any kind — reads only (`get_issue` ×2, `get_milestone`). No repository file touched: the validator experiment ran on `/tmp/drc4274-probe` (a `git archive HEAD` copy) and the git measurement on `/tmp/drc4274-git`. `git status` in the repo shows only the pre-existing `.gitignore` / `docs/roadmap-burndown/` entries.

### Summary

Both checks the scope note flagged are settled by exercise rather than reading: `docs/plans/` **is** in the validator's owned set (recursive glob at line 1209, which is why grepping for "plans" finds nothing), and the CI detector **will** classify a new plan file as prose, so this PR owes `validate_plugins.py` and nothing else. One premise in the scope note is refuted — `test_notifications.py` mentions its plan doc in a comment, not an open, so the derived deny-list has one entry rather than two.

Three further claims were re-derived rather than accepted: `changed` really is entries-not-files (2 entries for 4 changed files at git 2.55.0), `--no-spacedock`'s respawn forwarding branch really exists (`lifecycle.py:554-555`), and nothing in the issue body was falsified — so the drafted rewrite is additive and no content needed demotion. One gap the issue body does not yet cover was found: `SECURITY.md`'s Scope violation sentence enumerates file reads, and this probe is subprocess execution, so the document needs an intro-amendment section as the quota precedent had. The milestone correction is narrow — bound 2 is stated there in its pre-amendment non-nullable form.

Review depth is recommended **down** from full adversarial to two lenses plus an arbiter, with the AGENTS.md row conflict named openly for the captain to overrule at the gate.

## Stage Report: implementation

- DONE: The two approved Linear writes performed FIRST and read back — the additive rewrite of DRC-4274 and the narrow milestone correction restating bound 2 in its amended nullable form — and then `docs/plans/git-probe-security-scope.md` created in the worktree carrying all SEVEN elements ... The diff must touch exactly that one path.
  Both writes landed before any file was created, and both were read back. Issue: the surface bullet gained `{dirty: bool | None, changed: int | None}` and the dated triage note was appended. Milestone: the bounds clause now reads nullable-dirty/nullable-changed and `session_ended`. All seven elements present at lines 24-26, 28-39, 41-49, 51-59, 61-63, 65-68, 77-94. Diff is one path, confirmed by `git diff --name-only`.
- DONE: The emphasis guard, applied to the Linear writes themselves.
  The hazard fired exactly as warned and was caught by reading back rather than assuming: a code span inside a bold run came back split as `**The** \`changed\` **field...**`. Repaired once into a form with no emphasis/code adjacency. The milestone round-trip then drifted a pre-existing damaged run (`to* \`Todo\` *and` → `to *\`Todo\` *and`, leaving an italic that can no longer close); repaired in the same pass. Both documents now have zero emphasis/code adjacency sites, so the damage cannot progress.
- DONE: The established check set run and its output reported: `python3 scripts/validate_plugins.py` exiting 0, a grep over the diff proving no version field moved, and the `sync-docs` skill invoked with its outcome stated ... measure the actual surface against the 110 ± 30 line estimate and review the diff in the worktree; report both.
  Validator exit 0. Version grep over `*plugin.json` `*marketplace.json` `*gemini-extension.json` returned nothing; `bump_version.py --current` reports 0.18.0. Surface 1 file / 103 lines added / 0 removed, versus 110 ± 30 declared: 94% of estimate, inside tolerance. Diff reviewed in the worktree before the PR opened.
- DONE: The validator proved live against this file rather than assumed to cover it.
  Injecting one unresolvable relative link and one unresolvable heading anchor produced exactly two errors and exit 1, both naming `docs/plans/git-probe-security-scope.md`; restoring returned exit 0. The change that would make this fail: the validator ceasing to reach `docs/plans/` (the `rglob` at `scripts/validate_plugins.py:1209`), which would leave AC1 with no falsifier at all.
- DONE: `sync-docs` invoked, outcome stated.
  NOT a no-op, contrary to the checklist's expectation. The tone standard bans em dashes in `docs/plans/*.md`; both promotion precedents carry zero and my first draft had four. Fixed in `1e4114a`, shape only, no fact added or removed. `AGENTS.md` already covers `docs/plans/*.md` as a glob, so no doc row was owed. `docs-synced-through` deliberately left alone (feature branch, live siblings).
- DONE: A PR opened, DCO signed off, its body starting `Implements [DRC-4274](url) — <title>` with a `## Verification` section ... and the PR number reported back.
  **PR #238** — https://github.com/spacedock-dev/cargento/pull/238. Three commits, all `-s` signed off: `b9cbd8b`, `1e4114a`, `9d9059f`. CI confirms AC2 on the head: `quality-gate` pass, the five measurable jobs `skipping`, `validate` and `version-guard` pass, and the detector job itself passed — so the skips are the filtered kind, not the dead-upstream kind the aggregator rejects.
- DONE: NO test is written and NO `Closes #NNNN` line is added unless a mirrored GitHub issue actually exists: state explicitly in the report that no test was written, and why.
  **No test was written, deliberately.** AC1's falsifier is `scripts/validate_plugins.py`, a shipped check demonstrated above failing on this file's own injected defects. A test grepping this document for its own sentences would assert only that the file contains what we put in it — the prose-grep this workflow bans by name. No `Closes` line: `gh issue list` for both "DRC-4274" and "git probe security scope" returned empty, so no mirrored GitHub issue exists.
- DONE: The two non-reproducing DEC-3 figures kept out of the text.
  Neither "twice" nor "unconditional" appears. The index write is stated as git resolving a racy stat rather than a per-invocation habit; the fsmonitor hazard is stated as execution happening, with no run count, which cannot be wrong about a figure that did not reproduce.

### Summary

The two approved Linear writes went first and were read back, which is what caught the emphasis guard firing on both surfaces; both are now free of the adjacency that causes it. The document is 103 lines against a 110 ± 30 estimate, one path, and carries all seven elements including the intro-amendment section that was triage's own finding.

Two things were not inherited on trust. The validator was falsified against this exact file rather than against triage's throwaway tree, and the four code citations behind the document's claims (`validate_plugins.py:1209`, `cli.py:115`, `cli.py:203`, `lifecycle.py:554-555`) were each re-derived, as was the `cwd` wording precedent at `SECURITY.md:425-426`.

The pre-PR diff review earned its place and was not a formality. It caught that the cadence bound said "session-ended edge" in prose where DRC-4037 must hook the `session_ended` identifier, and that a six-harness name list would go stale inside a `SECURITY.md` this section is promoted into verbatim. `sync-docs` was also not the expected no-op: it caught four em dashes against a standard both precedents meet at zero. Review depth stays at two lenses plus an arbiter; nothing beyond the seven elements was specified, so the escalation trigger was not met.

## Stage Report: review

- DONE: LENS 1 — every measurement and code citation in `docs/plans/git-probe-security-scope.md` re-derived independently, refuting by default: the two git flags and the distinct hazard each alone disarms, `changed` counting porcelain entries rather than files, the `finished_at` versus `session_ended` distinction, the `--no-spacedock` sites including the respawn forwarding branch, and the `cwd` wording precedent in SECURITY.md. Report which reproduce, which do not, and exactly what you ran. A citation that resolves to a different line than stated is a finding, not a rounding error.
  **All reproduce.** Flags, at git 2.55.0 in six throwaway repos under `/tmp`: without `-c core.fsmonitor=` a repo-local hook script executed (evidence log written); with it, not executed. Without `--no-optional-locks`, `.git/index` mtime advanced from a racy-clean state; with it, unchanged, against a no-probe control that was also unchanged. Cross-tested for independence: `-c core.fsmonitor=` alone still rewrote the index, `--no-optional-locks` alone still ran the script — so "neither disarms the other's" holds. `changed`: 1 modified tracked file + untracked 3-file directory = **2 entries for 4 files** (` M tracked.txt`, `?? newdir/`). Citations resolve exactly: `validate_plugins.py:1209` = `paths.extend(sorted((ROOT / "docs").rglob("*.md")))`; `cli.py:115` = the `--no-spacedock` declaration; `cli.py:203` = `spacedock_enabled=not args.no_spacedock`; `lifecycle.py:554-555` = `if args.no_spacedock: argv.append(...)`, the respawn forwarding branch. `finished_at` is a turn-stop stamp exactly as AC5 states: `events.py:626` writes `overlay.at` on `OVERLAY_IDLE`, `events.py:602`/`615` set it `None` on working and needs-input, and `observation.py:354-361` pops on working/needs-input. `cwd` precedent at `SECURITY.md:425-426` — the implementation's citation is right; DEC-3's own `424-425` is the one off by a line.
- DONE: LENS 2 — the document checked against DEC-3's ruling AND ITS AMENDMENTS. The amendments are appended BELOW the ruling on DRC-4122, so a reader who stops at the ruling gets bounds 2 and 3 wrong: confirm the surface is nullable and the cadence names `session_ended`. Confirm both non-reproducing figures are ABSENT — the fsmonitor script ran once rather than twice, and the index write is race resolution rather than unconditional. Confirm all seven required elements are present AND that nothing beyond them is specified; anything beyond the seven meets the captain's escalation trigger and must be reported as such.
  Read the amendment section verbatim from Linear (`get_issue DRC-4122`, "## Amended 2026-08-28"), not from the entity — the entity file does not carry it. Bound 2 amended to `{dirty: bool | None, changed: int | None}`, matched **character-for-character** at doc line 43; bound 3 amended to `session_ended`, named at doc lines 46 and 61. Both figures absent: `twice` 0 occurrences, `unconditional` 0, `finished_at` 0. All seven elements present (lines 24-26, 28-39, 41-49, 51-59, 61-63, 65-68, 77-94). **Nothing beyond the seven, and this is now evidenced rather than asserted:** every structure outside them is the quota precedent's own shape, recovered from `git show 7134a01:docs/plans/quota-fetch-security-scope.md` — the section-local violation clause (its line 62), `## Intro amendments that ride with the promotion` (its line 68) down to the phrasing "and only these:", and `## What else the fetcher PR touches` (its line 78) whose **first bullet is "`SKILL.md` gains a `--no-usage` row in the flag table"**, of which our `--no-git` bullet is the line-for-line analogue. **Escalation trigger NOT met.**
- DONE: Each of the eight acceptance criteria reproduced from its own `Verified by:` clause rather than trusted from the implementation report, and the PR state checked on its CURRENT head — `gh pr checks 238`, `mergeStateStatus`, and whether the five skipped jobs are the filtered kind rather than the dead-upstream kind. Report every finding WITHOUT fixing any of it: this stage observes and verifies, it does not edit. Confirmed material findings route back to `implementation`, which is alive and is the correction target.
  Head `9d9059f`, `mergeStateStatus: CLEAN`, one path, +103/−0. All three runs verified by API to carry `head_sha: 9d9059fe…` — no superseded-head green. AC1 satisfied but weakly, and worth saying: the document contains **zero markdown links and zero anchors**, so "link- and anchor-clean" is true by absence; the teeth come from the implementation's injection test, not from live content. AC2 proven from the mechanism rather than from the report: the aggregator at `quality-gate.yml` passes a `skipped` job only under `[ "$res" = "skipped" ] && [ "$CODE" = "false" ]` and refuses to report at all if the detector did not succeed — so `quality-gate` passing **with all five skipped is itself proof** of `code=false`, and AC2's dead-upstream falsifier is provably absent. AC3 falsifiers both absent (no belt-and-braces framing; line 39 says outright "There is no fallback to a plain `git status`"). AC4, AC5, AC6 reproduced as above. AC7 reproduced end-to-end at both ends: `7134a01` (#71) +84 and `5ede7d1` (#143) +193 added; `a98bc64` (#75) SECURITY.md +55 with −84, and `3e92d12` (#144) SECURITY.md +100 with −193, promoting and deleting in one commit; neither file in `docs/plans/` today; and the quota doc's intro-amendment 2 is **live in SECURITY.md line 33**, which proves the intro-amendment mechanism itself, not just the promotion. AC8 is interactive and left to the captain — my reviewer's read is that it passes: 103 lines inside the 84/193 bracket, 0 em dashes matching both precedents, contract voice throughout. **Copilot: 0 inline comments, 0 top-level reviews, 0 issue comments — no review was ever requested, so nothing was merged past.** Nothing edited by this stage; no commit on the PR branch.

### Findings

None material. Four recorded, none blocking, all routed rather than fixed.

1. **`session_ended` reaches 2 of 10 harnesses, not 4 — and the sentence is the captain's own.** Doc line 46, "Six of the ten harnesses have no event adapter and can never emit `session_ended` at all", is *literally true* (4 adapters: claude/codex/gemini via `event_hook.py`, antigravity via `agy_hook.py`; 6 without) and is transcribed verbatim from the captain's amendment. But the implicature — that the other four can be probed — is false: `CODEX_EVENTS` has no `session_ended` mapping and `codex-hooks.json` registers no `SessionEnd`; `agy_hook.py` emits only `store_changed`. Only Claude and Gemini can emit it. So **8 of 10 rows can never be probed**. Classification **Needs decision**, not Material: only the captain may change amendment text, the error runs in the conservative direction (more `null`, never a confident clean), and no boundary is weakened. Flagged because it propagates verbatim into SECURITY.md.
2. **The amendment's "ran once, not twice" refutation is itself conditional — and the document was right to carry no count.** At git 2.55.0, a `core.fsmonitor` hook exiting non-zero ran **exactly twice per invocation, 3/3 trials**; a well-behaved hook printing a v2 response and exiting 0 ran **once**. DEC-3's "twice" and the amendment's "once" are each true under one hook behaviour. The document states execution with no run count, so it is correct under both — the strongest available defence of the implementation's wording. Recorded so DRC-4037 does not inherit "once" as settled. **Polish.**
3. **"The write is race resolution, not a per-invocation habit" is confirmed, with the mechanism worth writing down.** A genuinely settled repo (file mtimes backdated) saw **no index write at all** across 4 bare-`git status` runs, which is what makes the amendment's correction of DEC-3's "on a clean repo" right. A racy repo rewrote on every run until the timestamps aged out, then stopped — so the doc's "the normal case in a repository a live session is editing" is exactly the right characterisation. Note the rewrite is byte-identical content with a new mtime, i.e. a stat refresh. **No action.**
4. **Doc line 20-21, "Cargento already records each session's working directory", is the one claim DEC-3's triage explicitly flagged as only "partly true."** Nine collectors parse the absolute cwd and immediately reduce it via `sessions.project_from_cwd` to `<parent>/<basename>`; only Claude retains the absolute path, in the bounded in-memory `state.cwd_cache` (`claude_data.py:369-408`). DEC-3 recorded that E4 "would have to re-derive and hold the absolute path, which is itself a small new retention" — a SECURITY.md reader given this sentence would infer no new retention. **Polish, explicitly not Material:** no value AC and none of the seven elements requires stating the retention, and the published surface stays bounded to two fields. Belongs in DRC-4037's design doc; per AGENTS.md it should be filed, not promoted into this PR.

Two smaller notes, no disposition sought: doc line 59's "the same wording **this document** applies to `cwd`" is true only after promotion (pre-promotion, this document says nothing about `cwd`) — defensible inside a verbatim-promotion fence, and the arbiter may prefer it either way. And `--no-events` already suppresses the probe implicitly, since no events means no `session_ended`; the doc names only `--no-git`, which is correct but not complete.

### Verdict

**GO.** No material finding. Depth held at two lenses plus an arbiter and the escalation trigger was not met on either limb: nothing is specified beyond the seven elements (proven against the precedent's recovered text), and no claim *in the document* failed to reproduce. The two claims that did fail are in the supporting record — the captain's amendment and this entity's intro — not in the deliverable, which is more robust than either because it states no run count. Worktree removal and branch deletion are the merge step's, not this stage's.

### Summary

Both lenses ran as separated passes and every measurement in the document reproduced: the two flags each disarm one hazard and neither disarms the other's, `changed` really is 2 entries for 4 files, and all five code citations resolve to the exact lines claimed. The document matches DEC-3's amended bounds character-for-character on the nullable surface and names `session_ended` rather than the `finished_at` turn-stop stamp, with both non-reproducing figures absent.

The escalation trigger was tested rather than waved off. Recovering `quota-fetch-security-scope.md` from `7134a01` showed that every structure I might have called "beyond the seven" — the violation clause, the intro-amendment section, and the `SKILL.md` flag-table bullet — is the precedent's own shape, the last one line-for-line. That turned a plausible blocker into an evidenced pass.

The sharpest finding is one the document survives: the amendment's own refutation of DEC-3's "twice" figure is conditional on hook exit code, and a failing hook does run the script twice at 2.55.0. Because the implementation declined to carry any count, the text is correct either way. The finding that does need a decision is not the implementation's to fix — doc line 46 is the captain's amendment verbatim, and the harnesses that can actually emit `session_ended` number two, not four.

## Stage Report: implementation (cycle 2)

- DONE: The two approved Linear writes performed FIRST and read back
  Performed in cycle 1 and unchanged; this correction round was scoped to the deliverable's wording, and the gate directed that DRC-4122's amendment text is the captain's and stays.
- DONE: `docs/plans/git-probe-security-scope.md` created in the worktree carrying all SEVEN elements
  Still all seven, re-read end to end in `00444a7`; only the nullable-surface element's coverage sentence changed.
- DONE: The diff must touch exactly that one path
  `git diff --name-only origin/main..HEAD` returns `docs/plans/git-probe-security-scope.md` and nothing else. CI's detector agreed: `code=false`, all five measurable jobs `skipped`.
- DONE: `python3 scripts/validate_plugins.py` exiting 0
  Exit 0 locally on the corrected tree, and the `validate` check is green on head `00444a7`.
- DONE: a grep over the diff proving no version field moved
  `git diff $(git merge-base origin/main HEAD)..HEAD -- '*plugin.json' '*marketplace.json' '*gemini-extension.json' | grep -E '^[+-].*"version"'` returns nothing; `version-guard` green on the new head.
- DONE: the `sync-docs` skill invoked with its outcome stated
  Re-invoked this round and it produced **no change**: no code moved on the branch, so nothing could have drifted; check (a) docs-only, (c) validator exit 0, (e) tone clean; (b) covered above, (d) not applicable since the skill body is untouched. The marker was deliberately left unstamped, per the parallel-worktree rule.
- DONE: measure the actual surface against the 110 ± 30 line estimate and review the diff in the worktree
  102 lines added, 0 removed, one path. Inside tolerance (80-140), one line under cycle 1's 103 because the corrected paragraph was reflowed. Reviewed in the worktree before pushing.
- DONE: A PR opened, DCO signed off, body starting `Implements [DRC-4274](url) — <title>` with a `## Verification` section
  PR #238, unchanged from cycle 1 per the gate's explicit instruction not to edit it. The correction round is recorded as a PR comment instead, which also names the one figure the body now states stale (103 lines, actually 102).
- DONE: the PR number reported back
  #238. New head `00444a78532100c02ace2d5f3739485c1e038774`; `mergeStateStatus` `CLEAN`, `quality-gate`, `validate` and `version-guard` all green on that head.
- DONE: NO test is written
  No test was written. AC1's falsifier is `scripts/validate_plugins.py`, an existing shipped check already demonstrated in cycle 1 failing on this file's own injected link and anchor defects. A test grepping our own document for its own sentences is the prose-grep this workflow bans by name.
- SKIPPED: NO `Closes #NNNN` line is added unless a mirrored GitHub issue actually exists
  No mirrored GitHub issue exists for DRC-4274, so no autoclose line.

### Summary

Correction round 1. The gate returned GO on substance with one ask: doc line 46 understated how little
coverage the probe has. I reproduced the evidence independently rather than taking it from the gate —
only `event_hook.py:82` and `:200` map to `session_ended`, `CODEX_EVENTS` carries no `SessionEnd`,
`codex-hooks.json` registers none, and `agy_hook.py` emits only `store_changed` — which makes it eight
of ten rows unprobed, not six. Both constraints were honoured: no harness names and no count, because
the section is promoted into `SECURITY.md` verbatim and any number goes stale the first time an adapter
gains `SessionEnd`. The replacement states the property instead: the probe fires on `session_ended`,
most harnesses do not emit it today, so most rows carry `null`. The fsmonitor hazard, the race
characterisation, the working-directory claim and the PR body are all untouched, as directed.

## Stage Report: review (cycle 2)

- DONE: The corrected sentence re-verified on head `00444a7`: it must state the property rather than a harness name list or a hard count, must be accurate — only Claude and Gemini emit `session_ended` today, so most rows carry `null` — and must not have introduced a new claim.
  Doc lines 46-47 now read: "The probe fires on `session_ended`, and most harnesses do not emit that event today, so most rows carry `null`." **Accurate, and re-derived rather than inherited.** Two emitters, both proved from registration AND mapping: Claude (`cargento/hooks/hooks.json` registers `SessionEnd`; `CLAUDE_EVENTS` maps it at `event_hook.py:82`) and Gemini (`cargento-gemini/hooks/hooks.json:55` registers it; `GEMINI_EVENTS` maps it at `event_hook.py:200`). Codex **has an adapter and still cannot**: `CODEX_EVENTS` carries no `SessionEnd` key and `cargento/hooks/codex-hooks.json` registers eight events, none of them `SessionEnd`. Antigravity's `agy_hook.py` sends one event and it is `store_changed` (line 153). Six harnesses have no adapter. So 8 of 10 rows can never be probed, and "most" is true.
- DONE: (same item) — does it survive cycle 1's scepticism, and is it a new claim?
  **Yes, and no.** Both constraints held: zero harness names, zero counts, and the word `six` now appears 0 times in the file. "today" scopes the claim against the staleness that killed the count. The old wording's defect is genuinely gone — "no event adapter" excluded Codex and Antigravity, which *have* adapters and still cannot emit, so its plain reading over-promised coverage by two rows; "do not emit that event" reaches all eight. **Not a new claim:** line 61's cadence bound already says "one-shot, on the `session_ended` edge", so line 46 restates an element the document already carries, in the section that needs it to explain why `null` is the common case. It also drops the absolute "can never … at all" for the weaker, defensible "today", which is the right direction for text promoted verbatim.
- DONE: The remainder of the document confirmed UNCHANGED against the cycle-1 findings — seven elements, fsmonitor with NO run count, race characterisation, working-directory claim.
  Proved by diff rather than by re-reading: `git diff 9d9059f..00444a7` is **one file, one hunk, +3/−4**, entirely inside the paragraph the gate authorized. Nothing outside it could have moved. Spot-confirmed anyway: fsmonitor bullet (line 36) says the script "is executed under Cargento's identity" and carries **no run count** — still correct under both observed hook behaviours; race wording (line 33) still "git resolving a racy stat, not a per-invocation habit"; the working-directory claim at lines 20-21 verbatim. All seven elements present — 24-26, 28-38, 41-48, 50-58, 61-63, 65-68, and 76-93 (the last shifted one line up by the reflow that took the file 103 → 102). `twice`, `unconditional` and `finished_at` remain at 0 occurrences.
- DONE: The PR re-verified on its CURRENT head — one path, `mergeStateStatus`, checks green, and the five skipped jobs still the filtered kind rather than the dead-upstream kind — and a verdict given.
  Head `00444a78532100c02ace2d5f3739485c1e038774`, `mergeStateStatus: CLEAN`, state OPEN, files exactly `docs/plans/git-probe-security-scope.md`, +102/−0. **Every run confirmed by API to belong to this head, not a superseded one:** Quality Gate `33155881188`, Validate `33155881211`, Version Guard `33155881213`, all `head_sha: 00444a78…`, all `success`. Skips are the filtered kind, proved from the aggregator's mechanism as in cycle 1 rather than from the label: "Detect what the gate can measure" **passed**, and `quality-gate` reports success with all five measurable jobs `skipping` — which it can only do under `[ "$res" = "skipped" ] && [ "$CODE" = "false" ]`. AC2's dead-upstream falsifier is provably absent. Copilot: 0 inline review comments (`pulls/238/comments`), 0 reviews, 1 issue comment and it is the correction-round note the implementation posted. Nothing edited by this stage; no commit on the PR branch.

### Findings

**None.** Nothing new, and nothing from cycle 1 reopened.

One observation, no disposition sought: the PR body still states "1 file, 103 lines added" where the head is 102. It is stale by one line, the implementation named it in its PR comment, and correcting it would mean editing the body the gate's do-not-change list protects. Recorded, not routed.

### Verdict

**GO.** The one authorized sentence is right, is better than what it replaced, and honours both constraints. Nothing else in the document moved — that is a diff result, not a reading. The PR is one path, CLEAN, and green on the head those checks actually belong to.

### Summary

The correction is accurate and I proved it from the adapters rather than from the gate's account: Claude and Gemini both register `SessionEnd` and map it, Codex registers eight events with `SessionEnd` absent from both its table and its mapping, and Antigravity emits only `store_changed` — eight of ten rows unprobed, so "most" holds. The replacement also repairs a defect the original had beyond the one the gate named: "no event adapter" was the wrong predicate, because two of the four adapter-bearing harnesses still cannot emit the event.

Scope was confirmed by diff, not by re-reading. `9d9059f..00444a7` is one hunk of +3/−4 inside the authorized paragraph, so the fsmonitor wording's absent run count, the race characterisation and the working-directory claim could not have moved, and spot checks agree. All three CI runs were confirmed by API to carry head `00444a78…`, and the five skips are the filtered kind by the aggregator's own gating condition rather than by their label.
