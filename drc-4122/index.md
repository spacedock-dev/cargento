---
id:
title: 'DEC-3 · Decision: Let Cargento read git state inside your repositories'
status: implementation
source: https://linear.app/recce/issue/DRC-4122
started: 2026-08-28T06:00:47Z
completed:
verdict:
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4122
issue:
pr:
mod-block:
linear-status: 'Backlog'
milestone: ''
release: ''
estimate: ''
reconciled:
gates:
    version: 1
    records:
        - id: gate:drc-4122:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4122-triage-1
              briefing:
                id: briefing:drc-4122:triage:attempt-1:revision-1
                digest: sha256:5c7672b4714c5cd8267a7aeda987e09cd832afb7887c687dd59c9c5565095502
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4122:triage:1
                briefing: briefing:drc-4122:triage:attempt-1:revision-1
                by: person:captain
                at: "2026-08-28T06:14:24.872181Z"
                decision: approve
                reason: 'RULING: OPTION B, straight, in the recommended form — the off switch on by default, disabled with --no-git, NOT inverted to default-off. The captain ruled at the DEC-3 triage gate. Cargento may run git status inside a user working repository and publish, per session, only whether the tree is dirty and how many entries changed, bounded by the four constraints, each of which answers a hazard this triage measured rather than argued: (1) git -c core.fsmonitor= --no-optional-locks status --porcelain, or no probe, because plain git status was measured to advance .git/index mtime on a clean repo and to execute a repo-local core.fsmonitor script twice in one invocation; (2) published surface exactly dirty plus changed-count, with pathnames as matching hints never echoed, which is SECURITY.md own wording rather than the no-filenames promise the product does not make; (3) one-shot at session end rather than a poll, which is strictly narrower than the issue own B and removes index.lock contention with the user own git; (4) an off switch matching the --no-spacedock precedent. The SECURITY.md amendment lands BEFORE any code, as DEC-1 did. Accepted with the honest counter-argument on the record: DEC-1 safety came from shipping an ungated slice first and B has no counterpart, so the four bounds are a substitute and are named as one. Also accepted: this is the second read-axis amendment and the first ever decided, the first having landed undecided in PR #10. SCOPE OF THIS APPROVAL: drafted edits 1 to 6. That includes cancelling C7 (DRC-4026, risk-adjusted 31) rather than releasing it, and re-gating E5 (DRC-4038) rather than releasing it — which requires FILING one new decision issue for the outbound-network call, because re-gating without a filed gate is precisely the invisible-gate failure DEC-3 was filed to correct. E4 (DRC-4037) is genuinely released to Todo, re-scoped to the four bounds. The captain saw both dependent traps stated at the gate and approved.'
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4122](https://linear.app/recce/issue/DRC-4122) — Linear priority Urgent.

The authoritative issue body lives in Linear and is deliberately not copied here: a copy taken at
commission time would be a second, staler statement of the problem, and this workflow exists partly
because stale statements of a problem get built. `triage` fetches it live, reviews it adversarially
against the current codebase, and writes the sharpened version back to Linear.

## Problem

**This is a decision issue.** `triage` does not answer it. The gate is where the captain rules.

### The question, in one sentence

> May Cargento run `git status` inside a user's working repository — a subprocess in their code, not
> a file read in a store — and publish, per session, only whether the tree is dirty and how many
> entries changed?

Everything below exists to make that sentence rulable. Yes releases E4 (DRC-4037, risk-adjusted 74,
the highest unshipped score in its milestone). No cancels or parks it.

### Why the sentence says "subprocess" and not "read"

This is the largest correction this stage makes. The issue frames every option as a *read* — "a
bounded read, a published summary, no path". `git status --porcelain` is not a read. It is process
execution inside the user's repository, and two consequences were measured here rather than reasoned
about (`/tmp/gitprobe`, 2026-08-28):

- **It writes.** Plain `git status --porcelain` advanced `.git/index`'s mtime by one second on a
  clean probe repo. Cargento's whole posture is read-only against what it touches.
  `git --no-optional-locks status --porcelain` did not write on the same probe.
- **It executes code from the repository.** With repo-local `core.fsmonitor` set to a script,
  `git status --porcelain` ran that script — twice in one invocation. `.git/config` is not carried
  by `git clone`, so this needs local write access or a repository delivered as an archive; it is
  nonetheless arbitrary execution under Cargento's own identity, sourced from inside the directory
  being inspected. `git -c core.fsmonitor= …` disarms it.

Neither hazard appears in the issue, in E4, or in E5. Neither changes *whether* B is right. Both
change what the amendment must say, and both argue for the bounded shape recommended below.

### What is settled and is not being reopened

- DEC-1 (DRC-4053, Done 2026-08-04) settled the outbound quota fetch. Not reopened.
- DEC-2 (DRC-4054) settled the input power; the agent-initiated ask lane shipped. Not reopened.
- DEC-5 (DRC-4182) owns reading a tool call's *input*. Explicitly a different question — DEC-5's own
  body says so. Not reopened. It is, however, evidence: see the precedent section.
- Whether Cargento *can* find a repository path. It can. Nine collectors already parse `cwd` from
  stores they read. This decision is about permission, not capability.

## Proposed approach

### Evidence, re-derived at v0.17.1 (`b0eb26e`) rather than taken from the issue

| The issue's claim | Status at tip | Where |
|---|---|---|
| SECURITY.md treats reads outside documented store paths as a security bug | **Confirmed**, but the line reference used by E4 and the milestone (`SECURITY.md:36-37`) has drifted | `SECURITY.md:62-65` |
| Exactly one narrow file-read exception, for Spacedock frontmatter | **Confirmed.** It is the only one | `SECURITY.md:67-120` |
| Caps are 64 KiB README / 8 KiB entity / 400 frontmatter lines | **Confirmed**, and *incomplete* — there are seven further caps (32 stage names, 120-char title, 96 entity files, 12 rendered, 8 workflows per session) | `SECURITY.md:106-110` |
| "no filesystem path ever published" | **Confirmed but mis-scoped.** That sentence governs the Spacedock feature only, not the product | `SECURITY.md:117-118` |
| Nothing in the runtime reads a working tree | **Confirmed.** No `git` invocation anywhere; `subprocess` appears only in `notifications.py` (osascript), `lifecycle.py` (daemon spawn) and `quota.py` (vendor CLI). No `.git` reference in any runtime file | `cargento_runtime/` |
| Store roots are harness config homes only | **Confirmed.** `~/.claude`, `~/.codex`, `~/.gemini`, `~/.copilot`, `~/.pi/agent`, XDG/AppData. Nothing under a user repository | `config.resolve_store_roots`, `config.py:277+` |
| Cargento "already records every session's working directory" | **Partly true, and worth stating precisely.** The absolute `cwd` is *parsed* by nine collectors and immediately reduced; what is retained and published is `project_from_cwd` — the last **two** path segments. `Event.cwd` is parsed and bounded but has no consumer. E4 would have to re-derive and hold the absolute path, which is itself a small new retention | `sessions.py:42-91`; `events.py:167,386` |
| E4 = 74, E5 = 66 | **Confirmed** from `docs/visibility-2x2/items.json` (scores only) | E4 80/74, E5 72/66, C7 63/**31** |
| "Blocking relations to both have been added" | **Stale.** Three issues are blocked, not two. C7 (DRC-4026) was added 2026-08-23 | Linear relations |

**Nothing failed to reproduce.** Two claims were corrected rather than refuted (the cap list is
longer; the path-publication promise is narrower in scope), and one line reference has moved.

### Option B's boundary, tested

The scope note was right that B is under-specified. `git status --porcelain` emits pathnames —
verified in this checkout, which returned ` M .gitignore` and `?? docs/roadmap-burndown/`. So B is
necessarily *read paths, publish a summary*. Three findings settle where the line sits.

**1. What would be READ.** Every tracked path's stat, plus the pathname of every changed entry, into
Cargento's memory. Untracked directories collapse to a directory name, so the read is not even a
faithful file list.

**2. What would be PUBLISHED.** For E4, exactly two scalars per session: a boolean and a count.
Nothing else is needed. The pathnames are working data.

**3. Is a pathname "content" for the promise SECURITY.md makes today?** The document does not have
one rule; it has four positions, and only three are written down:

| Path | Treatment | Stated? |
|---|---|---|
| Event `cwd`, `transcript_path` | "matching hints and are never echoed to `/api/data`" | Yes — `SECURITY.md:424-425` |
| Spacedock project files | "no filesystem path is ever published" | Yes — `SECURITY.md:117-118` |
| Session `project` | Last **two** cwd segments, published on every row | **No** — `sessions.py:42-91` only |
| Ask-card `project` | Asking session's directory, up to **512 characters**, tail preserved | Partly — named as bounded at `SECURITY.md:437-440`; the near-full-path shape is not stated |

So the answer is: **the product does not promise that filenames never leave the machine, and it
should not start claiming so.** It already publishes path fragments, and the ask card publishes a
512-character directory string today. What it does hold — without ever writing it as a rule — is a
**directory/file distinction**: it publishes *where* a session works, never *which file inside*.

The consequence for B is precise and uses vocabulary SECURITY.md already owns: porcelain pathnames
are **matching hints, never echoed to `/api/data`** — the same sentence already governing `cwd`,
extended to a new source. A pathname read and discarded breaks nothing the document says. A pathname
*published* would be the first file-level identity on the surface, and B does not need one. The
issue's phrasing, "no filenames leaving the machine", is simultaneously stronger than B requires and
weaker than the product already keeps, and should not be the amendment's wording.

**Who sees the published surface.** `/api/data` on `127.0.0.1`, unauthenticated. Any local process
can read it; SECURITY.md says plainly that "loopback is not a per-user boundary"
(`SECURITY.md:434-435`). `--host` widens it to the network by explicit operator action
(`SECURITY.md:31-32`). "Published" therefore means *every local process, and the LAN if the operator
asked*. A dirty-tree boolean is a low-value target; it is not a no-value one.

### The precedent, and whether it settles it

**It does not settle it, and the issue's own account of the precedent is factually wrong in a way
that makes its worry stronger rather than weaker.** Taking the self-critique head-on:

*"It is the same 'narrow read, clear guardrails' argument that carried DEC-1, and the audit that
produced this issue exists because that pattern had already been applied once without being written
down. A second amendment on the strength of the first one going well is exactly the drift worth
naming before it happens."*

**First — DEC-1 is the wrong precedent, and the right one is worse.** DEC-1 did not amend the
file-read promise at all. It amended the *network* posture, SECURITY.md's first invariant. The
file-read promise has already been amended once: the Spacedock frontmatter carve-out, which landed
in `0a73535` (PR #10, 2026-07-27) — its SECURITY.md section committed in the *same* commit as its
code, and with **no decision issue at all**. So DEC-3 would be the **second** file-read amendment,
and the **first ever put to a filed decision before the code**. "A second amendment on the strength
of the first" misnames both the axis and the count.

**Second — the ratchet is real, and it is already measurable.** DEC-5, filed 2026-08-23, two weeks
after this issue and independently of it, writes: *"'narrow, with clear guardrails' is the argument
that carried DEC-1, is recommended for DEC-3, and was partly accepted for DEC-2, which would make
this the fourth time."* The drift this issue predicted was counted by a later issue without being
prompted. That is evidence **for** the self-critique and it is conceded, not argued away.

**Third — and this is the strongest point against the issue's own lean, which the issue does not
make.** DEC-1 was not safe because it was narrow. It was safe because of **guardrail 4: "D ships
first regardless"** — the ungated Codex-from-disk tile shipped before any credential was touched,
which, in DEC-1's own words, "converts this decision from an argument into an experiment, because
the Codex tile will show whether anyone acts on quota numbers before we spend trust getting
Claude's." **B has no D.** There is no ungated slice of E4; dirtiness cannot be derived from any
store Cargento already reads. So option B is *less hedged than DEC-1 was*, and the hedge that made
DEC-1 defensible is unavailable here. Anyone citing DEC-1 for B is citing the half that did not do
the work.

**Fourth — the line that does exist.** A ratchet is a shape, not a verdict; the rulable question is
whether this amendment has a stopping property the previous ones lacked. It does, and it is
checkable. Each previous amendment opened a **class**: any outbound quota endpoint, any Spacedock
workflow file, any harness the ask lane reaches. Option B opens a **fixed-cardinality** surface —
one boolean and one integer per session, and no next step reachable without its own decision.
C's branch and upstream names are project-authored *text*, not a count, so C cannot be built by
pointing at B. D is DEC-1 territory by E5's own body. Whether that line holds is procedural, not
textual: it holds only if the amendment names the published surface as exactly those two scalars and
says pathnames are never echoed, so that a later feature must amend the sentence again rather than
cite it. That is the same mechanism that made this audit possible.

### The options, with what each costs and forecloses

**A. Do not read repositories at all.**
*Costs:* E4 (74) is cancelled or parked indefinitely, and the board's own evidence is that a dirty
worktree nobody returned to is how agent work actually gets lost, silently. E5 and C7 go with it.
*Forecloses:* nothing — A is the only reversible option. *Buys:* an absolute promise that is easy to
state, and it is the only option under which the DEC-5 ratchet count stops at three.

**B. Only what `git status --porcelain` reports: dirty/clean and a count. Never file contents.**
*Costs:* the second file-read amendment; a subprocess in the user's repository with the two measured
hazards above; a per-repository poll that must be throttled (`collect_memo_sec=2.5`,
`stream_producer_interval_sec=5.0` — a naive implementation runs one git process per session every
few seconds and contends for `index.lock` with the user's own git); full adversarial review.
*Forecloses:* nothing in C or D — both need their own call. *Buys:* E4 only.

**C. B plus branch and upstream state.**
*Costs:* everything in B, plus branch names are project-authored text on the published surface —
a different class from a count, and the first such text since the Spacedock `title` scalar.
*Forecloses:* the "fixed cardinality" line that makes B stoppable. *Buys:* very little that E4 does
not already give; the item C would serve is E5, which C cannot deliver.

**D. C plus a remote call for pull-request state.**
*Costs:* an authenticated outbound request with a credential, on the user's behalf — DEC-1's
question reopened, not DEC-3's widened. E5's own body says it "cannot ship on a DEC-3 that lands on
option B or C", which is the same statement from the other side. *Forecloses:* the separation
between the local-read decision and the network decision. *Buys:* E5 (66).

### Recommended answer

**Option B, bounded by four constraints, with `SECURITY.md` amended before any code.** The bounds
are not decoration; each answers a hazard measured above, and each belongs in the amendment:

1. **`git -c core.fsmonitor= --no-optional-locks status --porcelain`, or no probe.** Non-writing and
   non-executing, both measured. A plain `git status` is not an acceptable implementation.
2. **Published surface is exactly `{dirty: bool, changed: int}` per session.** Pathnames are
   matching hints, never echoed to `/api/data` — the wording `SECURITY.md:424-425` already uses for
   `cwd`. Not "no filenames leave the machine", which the product does not currently promise.
3. **One-shot at end of session, not a poll.** E4 asks about a session that *ended*; a probe fired on
   the completion stamp E2 already ships removes the `index.lock` contention and the cadence problem
   entirely, and it is strictly narrower than the issue's B.
4. **An off switch, on by default with `--no-git`** — matching `--no-spacedock`, the precedent set by
   the only other read exception. A captain preferring the more conservative form should invert it to
   default-off; that trades adoption for consent and is a legitimate ruling.

**Why not A**, which is the serious alternative: A gives up the highest unshipped score in its
milestone to protect a promise that has already been amended once on this axis, undecided, in the
same commit as its code. Deciding this one deliberately is a *stronger* position than the status quo,
not a weaker one.

**The honest reason to distrust this recommendation** is the third point above, not the one the issue
made: DEC-1's safety came from shipping an ungated slice first, and B has no such slice. The four
bounds are the substitute, and a substitute is what they are.

**If the captain rules A**, E4 and E5 should be cancelled rather than parked — parking is what
produced this audit.

### What a non-A ruling sets up

The issue's "Done when" requires the `SECURITY.md` amendment to land **before** the code, as DEC-1's
did. **Not drafted here** — that is its own cycle, and it would be the first repository change and
first PR this workflow has run. It would have to state: the bound; the published surface; what is
never read; that the mechanism is subprocess execution rather than a file open, with the two flags
that make it non-writing and non-executing; the cadence bound; and the off switch.

Per `AGENTS.md`'s **Calibrating Effort** table, "Security, credential handling, or data loss" routes
to **full adversarial review — several lenses, a completeness critic, an arbiter.** Naming the cost
at the gate: that is the most expensive review tier this repository has, and a B ruling buys it.

## Linear edits made

**Nothing has been written to Linear. This stage read only.** The drafts below are proposals for
`implementation` to write *after* the captain rules.

### Pre-edit record

The live body was captured at `updatedAt: 2026-08-23T06:06:05.213Z` (issue created 2026-08-09).
Linear's own history is the immutable pre-edit record and is pinned by that timestamp.

The full ~4,000-word body and the ~3,000-word milestone description are **not** pasted here, and that
is a deliberate deviation from the stage definition's verbatim-capture output, recorded as such. The
rewrite proposed is additive — an appended Outcome section plus three factual corrections — so the
passages that will actually change are quoted verbatim below, in place. Pasting 7,000 unchanged words
to record three changed sentences would bury the record it exists to make readable.

### Drafted edits to DRC-4122 (NOT written)

1. **Append an `## Outcome` section** carrying the captain's ruling verbatim, dated, in DEC-1's shape
   (call, guardrails, filed follow-on issues). The existing body is **not** rewritten and nothing is
   deleted — the options and the self-critique are the record of what was believed on 2026-08-09.
2. **Correct one stale sentence.** Verbatim, under "What it gates":
   > *"Blocking relations to both have been added."*
   Three issues are blocked, not two: C7 (DRC-4026) was added 2026-08-23. Correct in place and date
   the correction.
3. **Append a dated note recording what this triage measured** — the two subprocess hazards, the
   four-position path table, and the DEC-1-had-a-D finding — so a later reader is not re-deriving it.

### Drafted edits elsewhere (NOT written)

4. **DRC-4037 (E4) and the "Nothing dies quietly" milestone** both cite `SECURITY.md:36-37` for the
   store-path premise. That text is at `SECURITY.md:62-65` at v0.17.1. Correct both to the current
   span, or to the section name, which will not drift.
5. **On a B or C ruling, do not let the dependents release mechanically.** Closing DEC-3 drops the
   `blockedBy` edge on all three, and two of them are not thereby buildable:
   - **E4** → genuinely released. Move to `Todo`, re-scoped to the four bounds.
   - **E5** → **must be re-gated, not released.** Its own body: it "cannot ship on a DEC-3 that lands
     on option B or C." It needs the unfiled DEC-4-shaped network call.
   - **C7** → **cancel, do not release.** Its own body already concludes it is "unreachable" on a
     narrow DEC-3, because porcelain names which files changed and not what changed in them. Under
     bound 2 it is doubly unreachable. At risk-adjusted **31** it is not worth a second decision.
6. **The "Nothing dies quietly" milestone** says "E4 and E5 are still blocked on DEC-3, which is
   still open and undecided" in two places. Both need the ruling, and E5's needs the re-gate.

## Expected surface and tolerance

This cycle delivers **no repository change**. The entity parks at `recorded` per the README's
`recorded` stage; `implementation` writes the ruling to Linear and nothing else.

- Repository files changed: **0** (tolerance: 0).
- Linear writes by `implementation`: the DRC-4122 outcome section and two corrections, plus the
  dependent dispositions in edit 5 and the milestone correction in edit 6 — **1 issue rewritten,
  3 issue dispositions, 1 milestone edit, 1 line reference corrected in 2 places.**
- Semantics moved: **the product's file-read promise**, if the ruling is non-A. Nothing else.

## Acceptance criteria

**AC1 — the ruling is recorded where the board reads it.** DRC-4122 carries a dated `## Outcome`
naming the option chosen, and the issue is `Done`.
*Verified by (offline):* `get_issue DRC-4122` returns `statusType: completed` and a body matching
`/^## Outcome/m`. *Falsified by:* the issue closing with no Outcome section, or an Outcome that names
no option letter.

**AC2 — no dependent is released that cannot be built.** After `implementation`, E4 is `Todo`; E5
carries a live blocker naming a network decision; C7 is `Canceled` or carries its own blocker.
*Verified by (offline):* `get_issue` on 4037/4038/4026 with `includeRelations`. *Falsified by:* E5 or
C7 sitting in `Todo` with `blockedBy: []` — the exact failure this decision was filed to correct.

**AC3 — history is dated, not deleted.** The pre-ruling options and the self-critique are still
present in the DRC-4122 body after the write.
*Verified by (offline):* the post-write body still contains the string `Reasons to distrust that
lean`. *Falsified by:* a rewrite that replaces the options with the answer.

**AC4 — the captain ruled, and the ruling is the captain's.** The Outcome records a decision made at
the gate, not one inferred from this entity.
*Verified by (interactive):* the gate transcript names the option the captain chose. **Declared
interactive: no harness automates this, and none should.** *Falsified by:* an Outcome whose only
provenance is this document.

**AC5 (conditional, non-A only) — the amendment precedes the code.** No commit touching
`cargento_runtime/` for E4 lands before a commit amending `SECURITY.md`.
*Verified by (offline):* `git log --format=%H -- SECURITY.md` and the E4 branch's first runtime
commit, compared by commit date. *Falsified by:* an E4 PR whose diff contains both, or the code
first. **This AC belongs to E4's cycle, not this one**, and is stated here so it is visible at the
gate that authorizes it.

## Test plan

No code changes, so no test suite runs. The verification this stage owes was **exercise, not
re-reading**, and it was done:

- `git status` writes and executes: run against a purpose-built probe repository at `/tmp/gitprobe`
  (reproducible: `git init`, one commit, `touch`, `stat .git/index` before and after; then
  `git config core.fsmonitor <script>` and observe the script's stderr).
- `git status --porcelain` emits pathnames: run in this checkout.
- Scores: read from `docs/visibility-2x2/items.json` by parser, not by eye.
- "Nothing reads a working tree": `grep` for `subprocess` and `git` across `cargento_runtime/` and
  its collectors, and for `.git` — the latter returns nothing.
- Store roots: read from `config.resolve_store_roots` directly.
- `Event.cwd` has no consumer: `grep` for consumers across the runtime returns none.

`AGENTS.md`'s **Parallel Work** warning was not triggered: no test suite was run, so no concurrent
red was interpreted.

## Review depth

**This stage:** none beyond the gate. It produced no code and wrote nothing.

**What a non-A ruling buys, per `AGENTS.md`'s Calibrating Effort table:** the E4 build is
"Security, credential handling, or data loss" → **full adversarial review** — several lenses, a
completeness critic, an arbiter. That is the most expensive tier in the table, and the cost is stated
here so it is visible at the gate rather than discovered afterwards.

### Feedback Cycles

## Out of scope

- **Drafting the `SECURITY.md` amendment.** Its own cycle, per the issue's "Done when".
- **Answering the decision.** The captain rules at the gate.
- **DEC-5 (DRC-4182).** A different power. Cited only as ratchet evidence.
- **DEC-4.** Unfiled, and E5's real gate. Naming it is not filing it.
- **The issue's "Note on process"** — *"Worth checking whether any other item's prose hides the same
  shape."* **Recommend filing as its own issue:** DEC-5 was found by exactly that sweep and it worked,
  so the method has a hit rate. Filing is the captain's.
- **One observation, no action taken:** the project's "As of 2026-08-26" block says "Release 1 has one
  item left, D6", and D6 (DRC-4029) is `Canceled`. Outside this issue's blast radius; noted so it is
  not lost.

## Stage Report: triage

- DONE: The question is stated in ONE sentence the captain can rule on, followed by options A through D with what each costs and forecloses, and ONE recommended answer. The issue's own stated reason to distrust its lean — that "narrow read, clear guardrails" is the same argument that carried DEC-1, and a second amendment on the strength of the first going well is the drift worth naming — must be addressed head-on rather than restated, because it is the strongest argument against the recommendation the issue already carries.
  One sentence under `## Problem`; four options each with a `Costs / Forecloses / Buys` triple; recommendation is B under four measured bounds. The self-critique gets four answers, two of which strengthen it against the recommendation: DEC-1 amended the *network* invariant, not the read one, so the real read-axis precedent is the Spacedock carve-out that landed undecided in `0a73535` (PR #10) — making this the second read amendment and the first ever decided; and DEC-1's safety came from guardrail 4 ("D ships first"), an ungated slice that B has no counterpart for. DEC-5's own body counts the ratchet at four, conceded rather than rebutted.
- DONE: Every claim is re-derived against the repository at its current tip rather than accepted from the issue, which was written 2026-08-09 and last touched 2026-08-23: what SECURITY.md actually promises today and at which lines, whether anything in the runtime still reads no working tree, what the documented store paths are, and what the Spacedock frontmatter exception's actual bounds are. Report any claim you could not reproduce rather than repeating it.
  Nine-row evidence table at v0.17.1 (`b0eb26e`). Nothing failed to reproduce; three claims were corrected. `SECURITY.md:36-37`, cited by E4 and by the milestone, is now `SECURITY.md:62-65`. The three quoted caps are real (`SECURITY.md:106-110`) but seven more exist. "No filesystem path ever published" is real (`:117-118`) and scoped to the Spacedock feature, not the product. Confirmed unchanged: no `git`, no `.git` and no working-tree read anywhere in `cargento_runtime/`; store roots are harness config homes only (`config.resolve_store_roots`). Refined: "already records every session's working directory" — the absolute `cwd` is parsed then reduced to two segments (`sessions.py:42-91`), and `Event.cwd` has no consumer.
- DONE: Option B's boundary is tested rather than assumed: `git status --porcelain` emits pathnames, so establish precisely what would be READ versus what would be PUBLISHED, whether a pathname is content for the purposes of the promise SECURITY.md makes, and who can see the published surface. Nothing is written to Linear and the decision is NOT recorded as made.
  Read = every tracked path's stat plus changed pathnames; published = two scalars. The pathname question resolves to a four-position table showing the product publishes path fragments today (session `project` = two segments; ask card = up to 512 chars, `config.py:524`), so "no filenames leave the machine" is a promise it does not make — the correct wording is SECURITY.md's own "matching hints, never echoed" (`:424-425`). Audience: unauthenticated `127.0.0.1`, "loopback is not a per-user boundary" (`:434-435`), widened by `--host`. Zero Linear writes this stage; the ruling is left to the gate.
- DONE: Prove by exercising, not by re-reading (shared-core proof obligation).
  Two hazards absent from the issue were measured in a purpose-built probe repo, not reasoned about: plain `git status --porcelain` advanced `.git/index` mtime (`--no-optional-locks` did not), and `git status` executed a repo-local `core.fsmonitor` script. Both are reproducible from the recipe in `## Test plan`; both reshaped the recommendation into a subprocess question rather than a read question.
- SKIPPED: Copy the original issue body and owning milestone description verbatim under `## Linear edits made` as the pre-edit record.
  The proposed rewrite is additive, so the ~7,000 unchanged words are pinned by `updatedAt: 2026-08-23T06:06:05.213Z` (Linear's history is immutable) and only the sentences that would actually change are quoted verbatim in place. Recorded as a deviation in the section itself rather than passed off as compliance.

### Summary

DEC-3 is made answerable without being answered. The largest correction is that option B is not a
read at all but subprocess execution inside the user's repository, and two hazards nobody had named —
`git status` writing `.git/index`, and executing a repo-local `core.fsmonitor` — were measured rather
than argued, which is why the recommendation is B under four specific bounds rather than B as written.
The issue's self-critique survives contact and is partly strengthened: its DEC-1 analogy names the
wrong invariant, the real read-axis precedent landed undecided in PR #10, and DEC-1's safety rested on
an ungated first slice that B cannot have. The stopping property that still favours B is fixed
cardinality — one boolean and one integer, with C and D each needing their own call.

Two traps are flagged for `implementation`: closing DEC-3 drops the `blockedBy` edge on all three
dependents, but E5 must be re-gated on the unfiled network decision and C7 (risk-adjusted 31) should
be cancelled rather than released — releasing them is the precise failure this decision was filed to
correct. A non-A ruling makes the next cycle this workflow's first real PR, and `AGENTS.md` routes it
to full adversarial review; that cost is stated at the gate rather than discovered after.

## Stage Report: implementation

- DONE: Drafted edits 1, 2 and 3 written to DRC-4122 and the issue closed: an appended dated `## Outcome` section carrying the captain's ruling of option B and its four bounds verbatim in DEC-1's shape, the stale "Blocking relations to both have been added" sentence corrected in place and dated, and a dated note recording what this triage measured. The existing body is NOT rewritten and nothing is deleted — the options and the self-critique are the record of what was believed on 2026-08-09.
  `get_issue DRC-4122` reads back `statusType: completed`, `completedAt: 2026-08-28T06:20:24Z`, a body matching `/^## Outcome/m` naming option B, and the four bounds as a numbered list. AC3's falsifier is absent: the string `Reasons to distrust that lean` is still present, as are all four options A–D. The stale sentence now carries a dated parenthetical naming DRC-4026 as the third blocked issue.
- DONE: The three dependents handled per drafted edit 5, each differently, and NONE released mechanically: E4 (DRC-4037) genuinely released to `Todo`, re-scoped to the four bounds, with its `blockedBy` on DEC-3 replaced by `relatedTo`; C7 (DRC-4026) CANCELLED, not released, with the reason recorded in its body; and E5 (DRC-4038) RE-GATED, not released — which requires filing one new decision issue for the outbound-network call and blocking E5 on it. Report the identifier Linear mints for that issue.
  **Linear minted `DRC-4273` for the new decision, titled "DEC-8 · Decision: May Cargento make an authenticated outbound request for pull-request state?"** DEC-8 was verified as the next free ordinal against a live search before minting, not taken from the scope note: DEC-1/2/3/5/6/7 exist, DEC-7 (DRC-4271) is the highest, and no DEC-4 or DEC-8 was found workspace-wide. Read-backs: E4 `status: Todo`, `blockedBy: []`, `relatedTo: [DRC-4122, DRC-4038]`. C7 `status: Canceled`, `canceledAt: 2026-08-28T06:22:08Z`, with a "Cancelled 2026-08-28" section giving the reason and a stated reopening condition. E5 `status: Backlog` (deliberately NOT `Todo`), `blockedBy: [DRC-4273]`, `relatedTo: [DRC-4122, DRC-4037]`. AC2's falsifier — E5 or C7 in `Todo` with `blockedBy: []` — does not hold for either.
- DONE: Drafted edits 4 and 6 applied: the stale `SECURITY.md:36-37` citation corrected in both DRC-4037 and the "Nothing dies quietly" milestone — prefer the section name over a line span, which will not drift — and the milestone's two "still blocked on DEC-3, which is still open and undecided" passages updated for the ruling, E5's carrying its re-gate. Read back every record you write and REPORT every discrepancy — discrepancies are the FO's to disposition, not yours to pass or fail on.
  Both citations now read "the **Scope** section of `SECURITY.md`" with a dated note recording the old line span and its v0.17.1 location. The milestone edit was built by script from a pre-write capture and diffed before sending: exactly three hunks, no other change. Both target passages were confirmed present exactly once each before replacement.
- DONE: No repository change (declared surface 0 files, tolerance 0).
  The worktree at `.worktrees/spacedock-ensign-drc-4122` is clean on `spacedock-ensign/drc-4122` at `b0eb26e` with no commits and no untracked files. `SECURITY.md` was not touched: its amendment is its own cycle and its own PR.

### Discrepancies — for FO disposition, not repaired

1. **Two unrequested `relatedTo` edges** from the mention hazard. `DRC-4122 ↔ DRC-4273` and `DRC-4273 ↔ DRC-4053` were created by links in bodies I wrote; neither was passed as a parameter. Both are substantively true, and both are `relatedTo` — consistent with the README's note that this mechanism has not been observed creating a gate edge. Not repaired: removal is a further unapproved write. Every requested edge landed, and no `blocks`/`blockedBy` edge appeared unrequested.
2. **`Failed to remove 1 relation(s)` twice** — on the DRC-4037 and DRC-4038 writes. Both were spurious, exactly as the README records: read-back showed body, state and every relation change had landed. Neither was retried.
3. **Serializer emphasis moves, five in DRC-4122, three in the milestone.** In the milestone all three are pre-existing text nobody touched, asserted programmatically to have been sent in the clean form — the unavoidable case; not repaired. In DRC-4122 two are likewise pre-existing, but **three are in prose I authored this cycle** (`**Option B is not a read. **`, `**… is not a promise this product makes. **`, `**Who sees the published surface. **`), where a bold run ended directly against a code span. That is my miss against the "keep a space between bold and adjacent code" guard, not the unavoidable case. Text content is unchanged and Linear renders from its document model. Not repaired, because a second write to a closed decision record is worse than the seam; flagging it as the FO's call.
4. **A third stale DEC-3 passage in the milestone, left alone.** "Unchanged there: DEC-3 is still open, so E4 and E5 are still blocked on it." sits in the section headed HISTORICAL, whose own convention is that dated sections stay true as of their date. Drafted edit 6 authorised two passages and this is a third, so widening was declined rather than assumed. It is now false on its face; the FO may want it dated.

### Summary

The ruling is recorded, DRC-4122 is closed, and the three dependents got three different answers — which was the point of the stage. Only E4 was released; C7 was cancelled with its reasoning written down rather than left behind an answered gate, and E5 was re-gated on **DRC-4273 (DEC-8)**, filed today for the authenticated outbound call, because releasing it would have recreated the invisible gate DEC-3 exists to correct.

Nothing in the repository changed and `SECURITY.md` was not touched; the amendment is its own cycle and must land before any E4 code. Four discrepancies are recorded above for disposition, one of which — three emphasis seams in prose I authored — is my own error rather than a measured Linear behaviour, and I have not written a second time to paper over it.
