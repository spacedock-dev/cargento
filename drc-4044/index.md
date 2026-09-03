---
id:
title: 'H1 · Keep a history of what happened'
status: triage
source: https://linear.app/recce/issue/DRC-4044
started: 2026-09-03T07:17:13Z
completed:
verdict:
score: 0.5
worktree:
issue:
pr:
mod-block:
linear-status: Todo
milestone: 'Move up a level'
release: r3
estimate: L
reconciled:
promise: P2
move: new
gates:
    version: 1
    records:
        - id: gate:drc-4044:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4044-triage-1
              briefing:
                id: briefing:drc-4044:triage:attempt-1:revision-1
                digest: sha256:23393862135d5c9e76239f7002f82f9dbfd44dfee8062ccf34f371c064312665
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4044:triage:1
                briefing: briefing:drc-4044:triage:attempt-1:revision-1
                by: person:captain
                at: "2026-09-03T07:45:25.820283Z"
                decision: approve
                reason: 'Captain approved the triage gate on 2026-09-03: "Agreed and approved, agree on all your recommendations for the 4 decisions. Continue". Accepts the direction: Drafts A/B/C authorized as drafted; two-PR delivery split on web/ (PR 1 full adversarial, PR 2 two lenses plus arbiter); eleven ACs and surface estimates accepted; decisions ruled as recommended — D1 yes (version reset distinguishable), D2 not reopened, D3 yes (SECURITY.md counts five/sixth and eight POST routes), D4 yes (the store keeps the derived two-segment project label, cost accepted), D5 yes (on-by-default clause corrected during promotion). D3/D4/D5 are captain-authorized deviations from the contract literal text.'
              application:
                target-stage: implementation
                state: pending
---

[DRC-4044](https://linear.app/recce/issue/DRC-4044) — Linear priority Medium, estimate L.

The authoritative issue body lives in Linear and is deliberately not copied here: a copy taken at
commission time would be a second, staler statement of the problem, and this workflow exists partly
because stale statements of a problem get built. `triage` fetches it live, reviews it adversarially
against the current codebase, and writes the sharpened version back to Linear.

## User value

_Drafted at triage 2026-09-03. Two sentences, then the promise ID and the move, per
[the promise map](../../promise-map.md#how-work-links-to-a-promise)._

A person who closes Cargento — or reboots — notices this the next time they open the board: the
project view still shows the state changes and the delegation split from before, instead of starting
its arithmetic over. They notice it again a minute later, because those two panels stop captioning
themselves `SINCE THIS TAB OPENED`.

P2 (`journey:mid-flight`), move `new`. The move is `new` because a durable record of past turns and
sessions is territory no promise covers: P2 describes a live session only. See **The `P2, new` label
tension** below — the labels are right, the body's sentence about them is not, and `new` permits a
promise-map change without compelling one.

## Problem

Checked against `main` at `5a156bc`, not restated from the issue.

The board is rebuilt from the harness stores on every start and Cargento keeps no record of its own
observations, so everything derived by watching over time is lost. Two shipped panels say so out
loud rather than degrading quietly, which is the right behaviour and is also the defect:

- The workstream rail captions itself `since this tab opened` and, with nothing accumulated, prints
  `No state changes observed since this tab opened.`
- The delegation figure withholds itself below a ten-minute observed window, printing `no figure
  yet` with `Waiting for one complete token-rate window in this tab.`

Five issues wait on the store rather than on either panel: A6, D10, G4, F3 and F2. That is what
makes this the structural item on the board.

**Triage found the windowing is narrower than the issue claimed, in the direction that matters.**
Both panels are bounded by **tab** lifetime, not by server restart. The transition history they draw
is manufactured in the browser by diffing consecutive `/api/data` polls, and the origin is stamped
once on the first poll of each page load. So a page reload discards it even with the server up, and
no amount of server-side persistence reaches those panels until the server both records transitions
and publishes them. The issue's premise — that the server already serves this and only forgets it
across a restart — is false.

**Three of the four things the issue says the snapshot already serves, it does not.**

| The issue's kept-list | What the snapshot actually serves |
|---|---|
| session identity | Yes: `session`, `sid`, `harness` |
| states | Yes: `state`, `active` — **current state only** |
| the transitions between them | **No.** Browser-derived by diffing polls |
| gate open and close | **No.** A live overlay ledger only: one slot per kind, overwritten, in memory, refusing at 512 |
| turn boundaries and timings | Partly: `started_at`, `finished_at`, and `turn` only while working. The per-turn duration history is trimmed to the last 50 and never published |
| tool names and counts | Names only, and only through `state_detail` — **which the never-list bans**. **No tool-count field exists anywhere** |

This does not sink the approach, but it fixes the reading of the store's one rule. "The store holds
nothing the live snapshot does not already serve" has to mean **field provenance** — every field
written is one the board already publishes — and not record identity, because the records the store
must keep are records the board publishes nothing of. Under the record reading the feature is
impossible; under the provenance reading it is exactly DEC-6's shape. The store observes the same
published `state` over time and derives transitions server-side, which is the browser's present job
moved behind the never-list.

Two consequences the issue does not carry:

- **Tool names and counts must leave the kept-list.** Their only published carrier is `state_detail`,
  and `state_detail` is banned outright — it can hold a permission prompt's own text, an open
  question's, or a plan's first line. Keeping them would need a new published tool field first, which
  is a different issue.
- **The never-list is incomplete against the row.** The runtime already enumerates its operator-text
  row fields as `title`, `last_prompt`, `state_detail`, plus `instruction.text` — the contract's
  never-list matches that exactly. But it also enumerates two nested carriers the contract names
  nowhere: `tasks[].subject` and `tasks[].activeForm`, and `subagents[].name`, which on four
  harnesses is the child session's title. A store that retains whole rows retains those. `spacedock`
  is a third nested object with the same exposure.

## Proposed approach

A leaf store module plus a server-side recording lane, then the panels seeded from it.

`cargento_runtime/history.py` — a leaf on purpose, importing `config` and nothing else, the shape
`git_status.py` took. It owns the path under Cargento's own directory, the append, the age-first then
size-cap eviction, and the discard-on-unreadable read. It is written the way `dismissals.py`,
`lifecycle.write_state` and the observer sidecar are written: directory `0o700`, the file opened
`0o600` in the `open` call rather than chmodded after, temp file plus `os.replace`, a failed write
reported rather than raised. Mode advisory on Windows, as it already is for all three.

`observation.py` gains the recording lane, beside the existing collection lane: it already holds the
finished stamps and the overlay ledger, so it is where a transition becomes observable. The store
records a derived transition triple rather than a row copy, which is what keeps the never-list
satisfiable by construction instead of by review.

The panels are then seeded from a published field on the existing `/api/data` payload, and the two
JS files gain a seeding entry point plus honest captions.

**Rejected — persist the browser's ring buffer.** The rail already keeps a 100,000-entry ring
buffer, so writing it to `localStorage` would make both panels survive a reload today with no store,
no flag and no security section. It cannot deliver: it survives a reload but not a new tab, another
browser or a cleared profile; it puts the record outside the never-list's reach, in a store Cargento
cannot bound, evict or delete, so `--forget` would be a lie; and it delivers nothing to the five
issues waiting, none of which reads a browser. DEC-6 authorized a store under Cargento's directory
and this is not one.

**Rejected — reuse `dismissals.py`'s store.** It is the closest precedent and the wrong mechanism.
It is a count-bounded record set of 256 that **refuses rather than evicting** when full, which for a
time series would stop recording on the day it filled and keep the oldest data, the exact inverse of
age-first eviction. Its `SCHEMA_VERSION` is read but never enforced, which is what D1 below is about.
H1 inherits its posture and almost none of its mechanism, as the 2026-08-21 comment already said.

## Adversarial read (2026-09-03)

Read against `main` at `5a156bc` and against `docs/plans/history-store-security-scope.md` **as
corrected by that commit** — blob `cd42a19`, md5 `e26451d9`, re-read at the end of the stage and
unchanged from the read the findings were made against. The tiny docs PR the dispatch warned might
land did land, mid-triage, at `5a156bc`, and it changed the clause D4 turns on: the derived
two-segment project label is now placed in an explicit gap rather than described as a path. Every
finding below is against that corrected text, not against `950822b`'s. Everything below is checked against the code, not against the
issue's prose. Claims that survive are marked HOLDS; claims that describe a state that no longer
exists, or never did, are marked FALSE.

### 1. "The store records what the live snapshot already serves" — FALSE as written, salvageable

Three of six kept categories are not served: transitions, gate open and close, and tool counts. Tool
names are served only through a banned field. Detail and the salvaging re-reading are in **Problem**
above. The approach survives; the sentence does not.

### 2. "the delegation figure and workstream rail no longer render as windowed" — FALSE about the cause

They are windowed by **tab** lifetime, not by server restart. A page reload resets them with the
server untouched. So the AC as written could pass a build that persists nothing, if the tester never
reloads, and fail a correct build tested in the same tab. AC11 above fixes this by requiring a fresh
tab. This is the finding most likely to have shipped a wrong verification.

### 3. "It lives under Cargento's own directory next to the dismissals file" — HOLDS

`~/.cargento`, resolved from `CARGENTO_HOME` when nonblank, deliberately not per-port unlike the
instance state file. The dismissals store, the state file and the observer sidecar are all there and
all written the same way. The precedent is exactly as the issue claims.

### 4. The on-by-default justification names the observer sidecar — FALSE, and load-bearing

This sentence is in the **merged contract**, in the paragraph justifying the on-by-default posture.
The sidecar is not written by default: it is written only when a reader opens the observer panel for
a specific session, on a `GET`. The contract's own amendment list calls it "a `GET` that writes a
sidecar", so the two halves of the file disagree. The dismissals half of the sentence is correct.

This is a **fourth seam**, beyond the three that 5a156bc corrected. It matters because it is the
argument for shipping the store on by default, and it overstates that argument by half. The gate is
asked to rule; see **D5**.

### 5. Amendment 1's arithmetic is wrong, because its base is — CONFIRMS D3

`SECURITY.md`'s "The server writes three files" enumerates the state file, the log and the dismissals
file, and **omits the observer sidecar** — which the server writes, and which invariant 2 names two
hundred lines earlier. So `SECURITY.md` already contradicts itself. The server writes four kinds of
file today, not three, and the statusline memo the next sentence calls "a fourth" is the fifth.

The merged contract says the count "rises to four" and "a fourth" becomes "a fifth". Applied
literally to a base that is already short by one, that ships a wrong count. Corrected: **five** and
**sixth**. H1 therefore cannot both apply amendment 1 verbatim and fix D3 — they conflict, and D3
wins. Recorded here so the review does not read the deviation as a missed instruction.

### 6. "the seven POST routes" — CONFIRMS D3, and the mechanism is exact

There are **eight**. `do_POST` prefix-matches `/api/events/` before reaching an exact-match table of
seven. Invariant 2's "Seven endpoints mutate" is separately correct — it counts mutators, and
`/api/shutdown` is not one — but the later sentence borrows that seven while naming
`/api/shutdown` among them, which is where the off-by-one is. Fix: eight.

### 7. "adds no endpoint" versus an AC that needs the history in the browser — a seam, not a conflict

The contract lists "a history file reachable over the port" as a security bug, and AC11 needs the
history's contents to reach the browser over exactly that port. These are reconcilable and should be
stated so before review, not during it: the ban is on exposing the **file** — a path, a download, a
raw dump — while the board serving observations it already publishes is what the board is. PR 1 adds
a field to the existing `/api/data`, no route and no method. The related boundary question on D10's
digest is filed as D2 on DRC-4033 and is not reopened here.

### 8. The `P2, new` label tension — the labels HOLD, the sentence explaining them is FALSE

The body says "P2, new: a durable history of past turns and sessions is territory no promise covers
today". Naming P2 as the promise served while asserting that no promise covers the work is
self-contradictory as prose. The move table resolves the pair — the `journey:*` label says which of
five board columns the work lands in, the move says how it touches the map, and every issue in this
milestone carries `move:new` — so the labels are right and stay. The sentence is what needs
rewriting, and Draft A rewrites it.

The consequence the body does not draw: `new` reads "May change this file: **Yes**, a new promise".
Permitted is not compelled. H1 should write **no** new promise, and the reason is the promise map's
first honesty rule — a promise enters only when a shipped capability backs it. The user-facing
promise history unlocks is "what happened while I was away", and that is D10's, with G4 and F3
claiming the rest. A promise written at H1 would sit in the file ahead of the capability that
delivers it, which is the precise failure that rule exists to prevent. The merged contract already
leans this way: `promise-map.md` "gains whatever the shipped capability earns, judged then rather
than now". Declared here so the gate is not surprised by a `move:new` PR that changes no promise.

### 9. The 2026-08-21 comment — HOLDS entirely, and two of its carried exposures are still live

Its central claim is confirmed by measurement: the dismissals store is a 256-entry count-bounded set
that **refuses rather than evicting**, which is the inverse of what a time series needs. Both carried
exposures reproduce: `diagnostics.py` reports neither Cargento-owned file, and whole-file
last-writer-wins is unchanged. Its observation that history had no decision issue is now stale —
DEC-6 exists and ruled — and Draft A dates it as history rather than deleting it.

### 10. The 2026-08-25 comment — now FALSE, and correctly so

"DEC-6 now blocks H1... H1 must not start until DEC-6 is Done." DEC-6 ruled on 2026-09-02 and
DRC-4330 merged today, so both gates are clear and Linear's `blockedBy` is empty. Demoted to history
in Draft A, not deleted: it is the record of why H1 sat still for a week.

### 11. The triage-notes comment (2026-09-03) — read, and one item sharpened

D1, D3 and D4 are carried into the decisions below. Its closing note says
`test_lifecycle.py`'s respawn test "asserts a fixed flag set, so it will not fail if `--no-history` is
left out". Correct, and the mechanism is worth having: the two exact-set assertions are blind to the
omission, but seven hand-written namespace objects would raise `AttributeError` if the branch reads
the attribute directly. So the file gets edited either way — the note's conclusion is right; what
forces the edit is not the assertion it names.

### 12. Is the approach still the one that fits? — YES

DEC-6 authorized a local store; a local store is what this builds; the precedent for how to write it
is three files old and unchanged. The one cheaper alternative is browser storage, and it fails on
`--forget` alone. What triage changed is the **cost**, not the direction: the store no longer looks
like a serialization of something the server already has, because the server does not have it. The
recording lane is new work, and the panels need publishing and seeding rather than only surviving.

## Decisions for the gate

Nothing here is written to Linear. Five items; each has a recommendation, because the captain is owed
one. **D4 gates AC11**, the only user-visible criterion, and is the one that most needs a ruling.

**D1 — may a readable store be discarded on a format bump?** DEC-6 named only a corrupt store; the
contract added "a version the running build does not understand".
*Recommend yes, with the header naming which reset it was.* A fourteen-day time series whose reader
must tolerate every past shape forever is how a silent mis-parse ships, and the precedent argues for
it rather than against: `dismissals.py` carries a `SCHEMA_VERSION` that is read and never enforced,
so the repository has one inert version field already and should not add a second. A version the
build cannot read *is* a store it cannot read, so this sits inside DEC-6 rather than widening it. The
distinguishable reason is the part worth paying for: a corruption reset may be the user's disk, a
version reset is ours, and one message for both hides the difference. Cost: one field and one test.

**D2 — the "adds no endpoint" boundary.** Filed on DRC-4033 for D10's digest. Not reopened. H1's
position is stated in adversarial item 7 and needs no ruling: a field on `/api/data`, no route.

**D3 — fix the two loose `SECURITY.md` counts with the promotion.**
*Recommend yes, and note that it changes amendment 1's numbers.* Confirmed by measurement in items 5
and 6: the server writes four files today and not three, so the promotion takes it to five and the
forwarder's memo to sixth, not four and fifth as the contract says; and the POST count is eight.
Approving this approves a deliberate deviation from a merged contract's literal text, which is why it
is a gate item rather than a small fix.

**D4 — may the store keep the derived two-segment project label? This gates AC11.**
The corrected contract puts the label in a deliberate gap: the kept-list omits it, the never-list
bans only "the paths it is derived from". Measured: both panels group by that label and cannot be
seeded without a grouping key, so with the gap left open, AC11 is not deliverable and H1 ships no
user-visible change at all.
*Recommend: add it to the kept-list explicitly, with the reason recorded.* It is already published on
every row, which is the one-way condition the store's rule turns on. It is not a path: it is capped
at the last two segments, home-relative, and its own docstring says the two segments exist so as not
to "paste a whole path into the row". And the alternative is worse in a way worth stating — keying on
an opaque digest of the label would preserve grouping while retaining no directory names, but it
loses the label a project panel has to display when none of that project's sessions is live, so the
restored history would render under no name. A third option, one segment instead of two, collides
sibling worktrees into one project, which is the exact case the two-segment choice was made for.
*What saying yes costs:* the store retains, for fourteen days, the last two directory names of every
project observed. That is the honest price and the reason this is the captain's call.

**D5 — the fourth seam: the on-by-default justification overstates the precedent.** The merged
contract says Cargento writes the observer sidecar "by default"; it writes it only when a reader
opens the observer panel. See item 4.
*Recommend correcting the clause during promotion, and recording the deviation.* The instruction is
to promote the section unchanged, so this is a second authorized deviation rather than a licence to
edit — the fix is to name the dismissals file as the by-default precedent and the sidecar as an
on-demand one, which is what the contract's own amendment list already says. Promoting unchanged
ships a sentence `SECURITY.md` contradicts elsewhere, in the paragraph that justifies the default,
which is the worst place to leave a seam. Two clauses; no other sentence moves.

## Delivery shape — recommended: two PRs, split on `web/` and nothing else

**PR 1 — store, flag, `--forget`, promotion, docs. Touches no file under `cargento_runtime/web/`.**
`history.py`, the recording lane in `observation.py`, the published field, `--no-history` at all four
of `--no-git`'s sites, `--forget`, the promotion into `SECURITY.md` with its amendments and D3's two
count fixes, the plan doc deleted in the same commit, and the `SKILL.md`, `HOW_TO_USE.md` and
architecture-doc rows. Carries AC1-AC9.

**PR 2 — the render.** `web/` only, plus the byte pins and the two panel suites. Carries AC10.
Both PRs belong to H1; the issue is not `Done` until PR 2 lands, and no second issue is filed because
the render carries no decision content of its own.

**Review tier, read straight off AGENTS.md's table.** PR 1 is the "Security, credential handling, or
data loss" row — a new persistent store of session observations is squarely there — and takes the
full adversarial tier: several lenses, a completeness critic, and an arbiter that reproduces findings
rather than ranking them. PR 2 is the "Owns a conflict-prone surface (`web/` byte pins)" row and
takes two lenses plus an arbiter. Neither is an override.

**Why split here, and the honest state of the evidence.** Three reasons, and the strongest is not
the one the precedent used.

1. **Five issues wait on the store, none on the render.** A6, D10, G4, F3 and F2 need `history.py`
   and the recording lane. Landing PR 1 first unblocks all five a full review cycle earlier. The E4
   precedent had no such argument; H1 does, and it is the reason to split even if nothing else
   applied.
2. **Tier asymmetry.** Riding together forces the full adversarial tier onto the render as well.
   AGENTS.md's measured finding is that **uniformity** cost that run — 35 agents, 4h27m, 6.9M tokens,
   10 blocking findings — not depth. A 6-figure byte-pin recompute does not want a completeness
   critic.
3. **`web/` contention, and this reason is weaker than it was for E4 — measured, not assumed.**
   `test_page.py` no longer exists, so the byte pins live in one file rather than two, and H1 changes
   two assets, so the recompute is **six figures, not fifty-six**. No open PR touches `web/`: #259
   and #224 touch none. Two sibling worktrees do carry web diffs — `docs/sync-next-ui-design-parity`
   and `worktree-spacedock-boot-rendering` — but both sit on the **pre-flattening** layout, with a
   `web/next/` subdirectory, `calm.js` and `main.js` that `main` no longer has, and neither has moved
   since 2026-08-26 and 2026-08-28 respectively. Neither is a near-term merge candidate, and their
   large diffs against `main` are mostly that restructure rather than in-flight work. So the queue is
   clear and the exposure is a sixth of E4's. Stated plainly because the precedent's rationale would
   otherwise be reused stale, and reasons 1 and 2 are what carry the decision.

**Why the split does not break the promotion constraint.** The promoted section describes keeping a
store, its fields, its bounds, its flag and its deletion. It says nothing about either panel. PR 1
ships all of that, so `SECURITY.md` describes only shipped behaviour at PR 1's merge and at every
commit after, and the plan doc dies in the commit that promotes it — the precedent's shape unbroken.
PR 1's honest intermediate claim is: *the store records observations, `/api/data` carries them,
`--no-history` turns it off, `--forget` deletes it, and the panels do not use it yet.* True and
releasable against any tag cut in the window.

**What it costs.** One extra CI cycle; a `gh pr update-branch` and a full re-run on PR 2 once PR 1
lands, because a ruleset requires branches be up to date; one extra review at the cheaper tier.
AGENTS.md measures the waiting at roughly fifteen minutes per extra PR.

**Rejected — one PR carrying everything.** One cycle, no sequencing, and with the byte-pin exposure
now a sixth of E4's this is closer than it was. It still cannot deliver: it holds the store — the
thing five issues wait on — hostage to a render review, and it forces the most expensive tier the
repository has onto three JS files.

**Rejected — three PRs, promotion then store then render.** Forbidden by the contract outright: the
promotion and the deletion ride together, and a promotion PR shipping no store leaves `SECURITY.md`
describing behaviour that does not exist. That is the exact failure the groundwork shape prevents.

## Linear edits made

Nothing has been written to Linear at this stage. This section is the pre-edit record plus the
drafts `implementation` will write once the gate approves them.

### Pre-edit record: live DRC-4044 body, verbatim (fetched 2026-09-03, `updatedAt` 2026-09-03T04:49:01.323Z)

Live at fetch time: status `Todo`, priority Medium, estimate L, milestone `Move up a level`,
labels `origin:proposed`, `release:r3`, `journey:mid-flight`, `move:new`; blocks DRC-4051, DRC-4043,
DRC-4042, DRC-4033, DRC-4009; `blockedBy` empty; related to DRC-4234, DRC-4039, DRC-4330.

```markdown
## User value

A person who restarts Cargento or the machine notices this once the board remembers what happened earlier instead of opening with no memory of sessions that already ran. P2, new: a durable history of past turns and sessions is territory no promise covers today, since P2 only describes what a live session is doing right now.

## What needs to be done

Keep a local history of Cargento's own observations across restarts, in the shape DEC-6 (DRC-4234) allowed on 2026-09-02, and no other.

The store records what the live snapshot already serves and nothing more: session identity, states and their transitions, gate open and close, turn boundaries and timings, tool names and counts. Never prompt text, tool input, a path or file content. It lives under Cargento's own directory next to the dismissals file, owner-only, written through a temp file and a rename. Retention is 14 days by default with a size cap, both configurable; eviction is by age first. `--no-history` turns the store off, `--forget` deletes it. On start, a corrupt or unreadable store is discarded, the board starts empty, and the header says history was reset. Nothing in the store ever leaves the machine.

This is the foundation for D10 (DRC-4033), G4 (DRC-4051), F3 (DRC-4043), F2 (DRC-4042) and A6 (DRC-4009), all of which stay gated on this issue. Ship the store and the restart-survival of the existing views first; each dependent adds its own reader.

Acceptance criteria: after a restart, the session rows and transitions observed in the previous run are present and the delegation figure and workstream rail no longer render as windowed for that period (interactive). Every field written to the store is a field the snapshot serves, checked by a test over the record schema (offline). Records older than the retention bound, or beyond the size cap, are evicted oldest first (offline). With `--no-history` nothing is written; `--forget` removes the file and the next start is empty (offline). A store with a corrupted byte starts empty and the header reports the reset (offline). The file is created owner-only through a temp file and rename (offline, mode advisory on Windows).

## Waits on

DRC-4330 (History groundwork · SECURITY.md scope section), which lands before this code.

## Scores (blind-panel medians)

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 48 | 48 | 76 | 50 | 0 |

Score legend: see the Visibility 2x2 board README.
```

The `<issue …>` inline reference tags Linear stores around each identifier are elided above for
legibility; the identifiers and their order are unchanged, and no prose was altered.

### Pre-edit record: `Move up a level` milestone description, verbatim (fetched 2026-09-03)

Milestone UUID `f3bc7f67-a75b-44cb-96ac-0e63002e7a10`, `progress` 3.51, `sortOrder` 4941.

```markdown
## The user value

**Nothing here is promised yet, and that is the point: this group changes what the user's job is rather than how well they watch.**

## What remains

[DRC-4041](<https://linear.app/recce/issue/DRC-4041/f1-these-four-are-one-project-make-it-a-workflow>): Cargento notices when several sessions belong to one project and points it out, instead of leaving them as separate tabs to track by hand.
[DRC-4042](<https://linear.app/recce/issue/DRC-4042/f2-you-have-done-this-five-times-make-it-a-skill>): Cargento turns a decision you keep answering the same way into a skill, instead of asking again.
[DRC-4043](<https://linear.app/recce/issue/DRC-4043/f3-where-your-attention-actually-went>): Cargento shows you where your attention went over the past week, making the case for delegating more.
[DRC-4044](<https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened>): The board remembers what happened before a restart, kept on this machine for 14 days, instead of opening with no memory of sessions that already ran.
[DRC-4045](<https://linear.app/recce/issue/DRC-4045/f4-cloud-and-local-on-one-board>): Your cloud sessions appear on the same board as your local ones, instead of living in a separate tab.
[DRC-4047](<https://linear.app/recce/issue/DRC-4047/f5-cowork-and-hosted-sessions>): Claude Cowork and other hosted sessions show up on the board next to your local ones, instead of staying invisible.
[DRC-4048](<https://linear.app/recce/issue/DRC-4048/f6-promote-a-session-to-a-workflow>): Cargento promotes a cluster of related sessions into a Spacedock workflow the first officer runs, instead of you orchestrating them by hand.
[DRC-4049](<https://linear.app/recce/issue/DRC-4049/f7-across-machines-or-across-a-team>): Every machine's sessions show up in one place, instead of one board per machine.

## Waits on

[DRC-4044](<https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened>) (H1) gates [DRC-4042](<https://linear.app/recce/issue/DRC-4042/f2-you-have-done-this-five-times-make-it-a-skill>) and [DRC-4043](<https://linear.app/recce/issue/DRC-4043/f3-where-your-attention-actually-went>), and A6 and D10 and G4 in their own milestones.
[DRC-4041](<https://linear.app/recce/issue/DRC-4041/f1-these-four-are-one-project-make-it-a-workflow>) (F1) gates [DRC-4048](<https://linear.app/recce/issue/DRC-4048/f6-promote-a-session-to-a-workflow>); the Spacedock write-API decision is filed when F1 ships.
```

### Pre-edit record: the two existing comments on DRC-4044

Both authored by Jared Scott, both to be preserved untouched — the rewrite demotes their live
content into a dated historical section rather than relying on the comments to carry it.

- `2026-08-25` "Update 2026-08-25": records that DEC-6 (DRC-4234) then blocked H1 and that H1 must
  not start until DEC-6 is Done and its retention boundary recorded.
- `2026-08-21` "Cargento now persists something between runs — H1's premise has moved": records
  that E6/DRC-4039 falsified the "persists nothing between runs" premise, what E6 settles for H1
  (posture) and does not (mechanism: a 256-entry hard cap that refuses rather than evicting), that
  history is a record of behaviour rather than of an instruction, and two carried exposures —
  whole-file last-writer-wins between concurrent dashboards, and `diagnostics.py` not reporting the
  store's path.

**Length, measured.** Draft A's forward-looking content is **409 words** against the original
body's **419** — shorter, as the stage definition asks. With the required dated historical section it
comes to 517 words (123%). The whole of that overage is the `## History` section, which the original
body did not have and which this stage forbids deleting. Stated as a figure rather than a claim so it
can be contradicted. The reduction comes from one change of principle: the old body **restated** the
security contract clause by clause, and Draft A points at it instead. A copy in Linear of a document
this same PR promotes into SECURITY.md is precisely the second, staler statement this workflow exists
to prevent.

### Draft A — rewritten DRC-4044 body, for the gate to authorize

Two mechanical instructions for `implementation`, both from the workflow rules:

1. **Send it unwrapped.** Join each paragraph to a single line before the write. Linear reads the
   100-column newlines below as hard breaks and re-marks emphasis per line. The wording does not
   change.
2. **Read back the relation set afterwards.** Every identifier below becomes a mention and mentions
   add `relatedTo` edges nobody asked for; a Markdown link does not prevent it. A `blocks` or
   `blockedBy` edge appearing is Material immediately.

No emphasis run in this draft ends immediately before a code span, which is the measured trigger for
the serializer moving a mark boundary.

---

## User value

A person who closes Cargento, or reboots, notices this next time they open the board: the project
view still shows the state changes and delegation split from before, instead of starting its
arithmetic over. Those two panels also stop captioning themselves as covering only the current tab.

Promise P2, move `new`: a durable record of past turns and sessions is territory no promise covers,
since P2 describes a live session only. The move permits a promise-map change without compelling
one, and this issue makes none — what history unlocks belongs to D10, G4 and F3.

## What needs to be done

Keep a local history of Cargento's own observations across restarts, in the shape DEC-6 (DRC-4234)
allowed on 2026-09-02 and no other.

**The contract is not restated here.** It is the section in
docs/plans/history-store-security-scope.md, which this issue's own PR promotes into SECURITY.md
unchanged and deletes in the same commit. It governs what may be kept, how it is written, how long
it survives, and how it is turned off. A copy here would be a second, staler statement of it.

What this issue adds is the scope boundary. Ship the store, the server-side recording lane, the
published field the panels read, and the restart-survival of the workstream rail and the delegation
figure. Tool names and counts are out: their only published carrier is the row's state detail, which
the contract bans. Every reader beyond those two panels belongs to the issue that needs it — D10
(DRC-4033), G4 (DRC-4051), F3 (DRC-4043), F2 (DRC-4042) and A6 (DRC-4009) stay gated here and each
adds its own.

## Acceptance criteria

Eleven, ten offline and one interactive, each with a verifying clause and a falsifying change, held
in this issue's burndown entity. The one a user sees: after a restart, in a fresh tab, the rail lists
the earlier transitions and the delegation figure renders instead of withholding itself. Why the
fresh tab matters is in the triage comment below.

## Delivery

Two PRs, split on the web assets and nothing else: the store, flags, promotion and docs, then the two
seeded panels with their byte pins. Not done until the second lands.

## Scores (blind-panel medians)

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 48 | 48 | 76 | 50 | 0 |

Score legend: see the Visibility 2x2 board README.

## History

**Waits on DRC-4330 — cleared 2026-09-03.** The SECURITY.md scope section had to land before this
code. It merged that day and released this issue.

**Blocked on DEC-6 — cleared 2026-09-02** (from the comment of 2026-08-25). DEC-6 asked whether
Cargento may persist history across restarts at all, even staying local. It ruled, so the bar on
starting before then is satisfied.

**"Cargento persists nothing between runs" — false since 2026-08-21.** An earlier version of this
issue and of its milestone rested on that premise; E6 (DRC-4039) falsified it. The comment of
2026-08-21 records what E6 settled and what it did not, and triage confirmed both halves today.

---

### Draft B — milestone `Move up a level`, one correction

One clause is now false. This issue's line reads:

> The board remembers what happened before a restart, kept on this machine for 14 days, instead of
> opening with no memory of sessions that already ran.

The contract bounds the store by an age window **and** a size cap together, and says raising either
does not stop the other applying. So a fourteen-day figure stated flat overstates it: the cap can
evict inside the window. Corrected clause:

> kept on this machine for up to 14 days

Nothing else in the description changes. The "Waits on" section is accurate as it stands — this issue
does gate F2 and F3 here, and A6, D10 and G4 in their own milestones — and the earlier "Confirmed
absent: Cargento persists nothing between runs" sentence the 2026-08-21 comment complained about is
already gone from the live description.

**Why it goes by script.** The `save_milestone` call has no patch operation, so the whole
description is resent. Build the edit programmatically from the verbatim capture recorded above:
assert `kept on this machine for 14 days` appears **exactly once**, replace it, diff the result, and
confirm the hunk count is one and nothing else moved. Do not hand-assemble the body.

**Risk assessment, against the measured rule.** The measured trigger for the serializer moving or
dropping an emphasis mark is a code span following an emphasis run. This description contains **one**
emphasis run — the bold sentence under "The user value" — and **no code spans at all**, so the
trigger is absent. The resend is low risk. Report any boundary move in the stage report and do not
repair it; a repair provably cannot succeed.

If the diff comes back with more than one hunk, abandon the write and put the correction in a dated
comment on the milestone instead, per the workflow rule. It renders with the description, is
additive, and carries no resend risk.

---

### Draft C — new comment on DRC-4044, for the gate to authorize

A dated comment rather than body text, for the reason this issue's other two findings are comments:
it is a record of what was measured and when, it is additive, and it carries no resend risk. Keeping
it out of the body is also what let the rewrite come in shorter than what it replaced.

---

## What triage measured, 2026-09-03

Three corrections to this issue as it stood, each checked against the code at main `5a156bc` rather
than against the issue's own prose.

**The snapshot does not serve most of what this issue said it served.** The body claimed the store
would record "what the live snapshot already serves and nothing more", listing transitions, gate open
and close, and tool counts among them. None of those three is served. State transitions are
manufactured in the browser by diffing consecutive polls of the data endpoint. Gate open and close
exist only as a live overlay ledger, one slot per kind, overwritten in memory and refusing new
sessions past its bound. No tool-count field exists anywhere in the runtime; the nearest thing counts
consecutive tool failures inside the current turn.

This does not change the approach, but it fixes how the store's one rule reads. "Nothing the live
snapshot does not already serve" has to mean **field provenance** — every field written is one the
board already publishes — rather than record identity, because the records the store must keep are
records the board publishes nothing of. Under the record reading this feature is impossible. The
store observes published state over time and derives transitions server-side, which is the browser's
present job moved behind the never-list.

**Tool names and counts leave the scope.** Their only published carrier is the row's state detail, and
that field is banned outright: it can hold a permission prompt's own text, an open question's, or a
plan's first line. Keeping them would need a new published tool field first, which is a different
issue.

**Both panels are windowed by tab lifetime, not by server restart.** This is the correction most
likely to have shipped a wrong verification. The browser stamps the observation origin once per page
load, so a reload discards the accumulated history with the server untouched. The old acceptance
criterion — that after a restart the panels "no longer render as windowed" — could therefore pass
against a build that persists nothing if the tester never reloaded, and fail a correct build tested in
the same tab. The rewritten criterion requires a fresh tab.

**Two more things worth carrying, both still true.** The never-list names the three operator-text row
fields the runtime itself enumerates, but not the nested carriers it also enumerates: a task's subject
and active form, and a subagent's name, which on four harnesses is the child session's title. A store
that retained whole rows would retain those. And the diagnostics report still names neither
Cargento-owned file, so a second one will not appear there either — carried from the 2026-08-21
comment as an accepted exposure rather than fixed here.

## Expected surface and tolerance

Two PRs; see **Delivery shape**. Oracles costed separately from the runtime, per the stage
definition, and every file the repository's own gates **compel** is named rather than estimated.

**PR 1 — store, flag, `--forget`, promotion, docs.**

| | Estimate |
|---|---|
| Runtime | **+440 net across 7 files**, tolerance ±20% |
| Docs | **−60 net across 6 files** (a +55 promotion against a −140 deletion), tolerance ±25% |
| Oracles | **+650 net across 8 files**, tolerance ±25% |

Runtime: `history.py` new (~+300); `observation.py` recording lane (~+60); `aggregate.py` and
`sessions.py` for the published field (~+40); `cli.py` two argparse blocks, the `build_runtime` line,
the `--forget` arm, the `--daemon` combination guard and the `--no-dismiss` help-string amendment
(~+22); `config.py` one bool beside the other five flags plus two thresholds, one kwarg, one
constructor line (~+16); `lifecycle.py` one forwarding branch (+2).

Docs: `SECURITY.md` promotion and amendments; `docs/plans/history-store-security-scope.md` deleted
(−140); `SKILL.md`, `HOW_TO_USE.md`, `docs/design-runtime-architecture.md`, `AGENTS.md`'s tree.

**Compelled, not chosen** — five of the eight oracle files are edits a required check forces:

- `scripts/validate_plugins.py`'s `CARGENTO_RUNTIME_FILES`, because a discovery test asserts set
  equality against what the checkout ships. A new module fails it immediately.
- `test_contracts.py`'s `RuntimeImportGraphTest.EXPECTED`, an `assertEqual` over the whole graph: a
  new key, plus the importer sets of `cli`, `lifecycle` and `observation`.
- `test_sessions.py`'s `DECLARED_SESSION_FIELDS`, written out deliberately so it cannot move with the
  function it checks. Compelled the moment a row field is added.
- `test_lifecycle.py`, and this one is the largest single cost. Seven hand-written `Namespace`
  objects would raise `AttributeError` rather than fail if the forwarding branch reads
  `args.no_history` directly, so all seven need the field. Two tuples want the new flag —
  the opt-out loop and the `--daemon` rejection loop — and the installed-contract case tuple wants a
  `--forget` row.
- `scripts/bench_collect.py`'s `Namespace`, for the same reason, and its own comment records this
  breaking once before.

Chosen: `tests/test_history.py` new (~+420, against `test_dismissals.py`'s 366 for a simpler store);
`test_documentation.py`'s new contract class (~+55, owed by the merged contract); `test_observation.py`
for the recording lane (~+90).

One constraint rather than an edit: a repository-wide sweep asserts that only `git_status.py`
constructs a git subprocess, by globbing for the quoted literal `"git"` in **any** runtime `.py`,
comments and docstrings included. `history.py` must not contain it — a plausible trap, since the
store's fields sit beside `dirty` and `changed`.

**PR 2 — the render.**

| | Estimate |
|---|---|
| `web/` | **+60 net across 3 files**, tolerance ±25% |
| Oracles | **+150 net across 3 files**, tolerance ±25% |

`next-workstream.js` a seeding entry point and three framing sites; `next-delegation.js` the six-hour
window clamp, which otherwise caps the widened figure at six hours against a fourteen-day store;
`next-render.js` the wiring. Byte pins compelled in `test_next_page.py`: **six figures** — two changed
parts at a size and a digest each, plus the assembled page's own pair. `test_next_workstream.py` and
`test_next_delegation.py` for behaviour.

**Semantics this may change:** command grammar (`--no-history`, `--forget`), stored formats (a new
on-disk store, and the only one Cargento keeps as a time series), and runtime behaviour (the store is
on by default). Not authority: no endpoint, no route, no outbound request.

## Acceptance criteria

Eleven criteria. AC1-AC8 belong to PR 1, AC9-AC10 to PR 2, AC11 to the issue. AC11 is the only
interactive one and the only one a user can see. Each names something outside this entity that
decides it, and the change that would flip it.

**AC1 (offline) — every field in the store is a field the board publishes, and none is on the
never-list.** The record's field set is a subset of the published session field set, and its
intersection with the operator-text carriers is empty — including the nested ones the contract omits.
*Verified by:* a test in `tests/test_history.py` that builds a record, takes its key set, and asserts
containment in `test_sessions.py`'s `DECLARED_SESSION_FIELDS` and disjointness from a literal ban
tuple covering `title`, `last_prompt`, `state_detail`, `instruction`, `tasks`, `subagents`,
`spacedock`. The expected sets come from the declared table and a literal, not from `history.py`'s
own constants — the tautology tell the workflow rules name.
*Falsified by:* adding `state_detail` to a record, or keying rows on a raw `cwd`.

**AC2 (offline) — nothing in the store is prompt-derived, proven against a fixture that would
carry it.** Given a session whose title, `last_prompt`, `state_detail`, `instruction.text`,
`tasks[].subject` and `subagents[].name` are all set to distinct sentinel strings, no sentinel
appears anywhere in the store's bytes after a full recording cycle.
*Verified by:* a test in `tests/test_history.py` that drives a recording cycle over that fixture,
reads the store file as bytes, and asserts each sentinel is absent. The sentinels are literals in the
test, so the expected value comes from outside the code under test.
*Falsified by:* recording the row instead of a derived triple. This is the check that would have
caught the nested carriers the never-list omits, which is why it reads the bytes rather than the
schema.

**AC3 (offline) — eviction is by age first and the cap cannot resurrect a dropped observation.**
With retention exceeded, records outside the window are gone; with the size cap exceeded inside the
window, the oldest surviving records go first; and raising the cap after an age eviction does not
bring the dropped records back.
*Verified by:* three tests over a store built at controlled timestamps, the third asserting the store
is unchanged after the cap is raised.
*Falsified by:* evicting on size before age, or `dismissals.py`'s refuse-when-full policy, under
which the third test would find the newest records missing instead of the oldest.

**AC4 (offline) — the file is created owner-only through a temp file and a rename.** The mode is
`0o600` from the `open` call rather than a later `chmod`, the directory is `0o700`, and a reader
during a write sees either the whole old file or the whole new one.
*Verified by:* a `stat` assertion plus a test that the temp name is unlinked on a failed write, both
skipping the mode assertion on Windows where it is advisory — `platform-tests` re-runs the suite
there. `test_dismissals.py` is the template.
*Falsified by:* `open()` then `os.chmod`, which is briefly world-readable, or writing in place.

**AC5 (offline) — an unreadable store is discarded, the board starts empty, and the header says so
with a distinguishable reason.** Corrupt bytes, an unreadable file and a version the build does not
understand each produce an empty board and a header reset notice, and the version case is
distinguishable from the corruption case.
*Verified by:* three tests over three prepared files, asserting the empty result and the reason each
reports.
*Falsified by:* repairing a partial store, or reporting one reason for all three. See **D1** — the
distinguishable reason is the recommendation the gate rules on.

**AC6 (offline) — with the store off, nothing is written and nothing is read back.** `--no-history`
leaves no file on disk after a recording cycle, and an existing file is not read.
*Verified by:* a test asserting the path does not exist after the cycle, and a second that a
pre-seeded store yields an empty board under the flag.
*Falsified by:* gating only the read, which would leave the file growing while the user believes the
feature is off.

**AC7 (offline) — the off switch survives a respawn.** `--no-history` appears in the argv
`spawn_argv` builds, and does not when it was not requested.
*Verified by:* two tests in `SpawnArgvOptOutTest`, plus the flag added to the opt-out tuple.
*Falsified by:* omitting the forwarding branch. Note the existing exact-set assertions do **not**
catch that omission, which is the triage note's point; the seven hand-written namespaces are what
force the edit, and only if the branch reads the attribute directly. Recommendation: read it
directly, so the "a future flag has to be added here consciously" property the docstring claims
stays true.

**AC8 (offline) — `--forget` deletes the store and exits, and adds no route.** It removes the file
whether or not the store is enabled, exits without binding a socket, is refused in combination with
`--daemon`, and no HTTP method reaches it.
*Verified by:* a test asserting the file is gone and the exit code, the `--daemon` rejection loop
gaining `--forget`, and an assertion that the POST route table and the prefix match are unchanged in
number.
*Falsified by:* deleting only when enabled, or adding an endpoint.

**AC9 (offline) — the promotion left the contract in exactly one place, bound to the parser.**
`SECURITY.md` contains the section heading and the sentence `The off switch is` naming
`--no-history`; the parser accepts that flag; and the plan document does not exist.
*Verified by:* a new `HistoryStoreContractDocumentationTest`, the direct analogue of
`GitProbeContractDocumentationTest`, whose plan-doc assertion is `assertFalse(...exists())`. The
prose half is bound to a parser call, so it is not a grep over our own words.
*Falsified by:* promoting without deleting the plan doc, or shipping the sentence with the flag
unparsed.

**AC10 (offline) — the seeded panels are pinned at their bytes and their behaviour.** The two
changed parts and the assembled page match their recorded sizes and digests, and the rail seeded with
prior observations reports the true window rather than the tab's.
*Verified by:* `test_next_page.py`'s six recomputed figures, plus a behaviour test driving the seeding
entry point and asserting the caption is not `since this tab opened`.
*Falsified by:* editing a web asset without recomputing, or seeding the data while leaving the
caption hardcoded — which would make the panel lie about its own provenance.

**AC11 (interactive) — the board remembers after a restart, and the two panels say so.** With the
store on, a project observed across state changes, then Cargento stopped and started and a **fresh
tab** opened: the rail lists the earlier transitions and captions itself with the real window, and
the delegation figure renders instead of printing `no figure yet`.
*Verified by:* `live session:<path>` — a scripted drive recorded under `docs/captures/`, graded on
durable before-and-after state plus the observed captions, with a negative case under
`--no-history` that must show the empty rail and the withheld figure. The workflow rules require a
live scenario for a runtime claim and a negative case that reds the grade.
*Falsified by:* the fresh tab showing an empty rail — which is what a store that persists but is
never published produces, and the failure the panels' tab-lifetime windowing makes easy to ship
unnoticed. A page reload, not merely a server restart, is the honest test.

## Test plan

`tests/test_history.py` is the bulk and carries AC1-AC6, modelled on `test_dismissals.py` with an
age-first eviction group `test_dismissals.py` has no analogue for. AC2 is the one to write first: it
is a byte-level negative over a fixture built to carry every operator-text field, and it is the only
check that fails when a nested carrier sneaks in. Test-first per the workflow rules — write it, watch
it fail against a store that records the row, then narrow the record.

`test_observation.py` covers the recording lane: a transition observed once is recorded once, an
unchanged state records nothing, and the lane is silent when the store is off.

`test_documentation.py` gains the contract class (AC9). `test_lifecycle.py` gains AC7's pair, the two
tuples and the seven namespaces. `test_next_page.py` and the two panel suites carry AC10.

No E2E harness is needed for the offline set. AC11 needs a live drive, and it is the only one; budget
it as the scripted scenario plus its negative, recorded as a capture rather than as a committed test,
since nothing in CI can open a browser tab.

**Run the suite once.** Three concurrent suites took it from 73s to 590s here and manufacture
failures in `test_http_api`, `test_quota` and the two subprocess-heavy lifecycle classes. Two sibling
worktrees are live; confirm any failure in those modules by running that module alone before
believing it, and report both results.

## Review depth

_Chosen at review from AGENTS.md's Calibrating Effort table._

### Feedback Cycles

## Out of scope

- **Any reader of the store.** A6, D10, G4, F3 and F2 each add their own, and the issue says so.
  Restart-survival of the two existing panels is in scope; a digest, a streak, a weekly view and a
  skill suggestion are not.
- **Tool names and counts.** Removed from the kept-list by the finding above: the only published
  carrier is banned. Publishing a tool field first is a separate issue, and the gate is asked to
  confirm the removal rather than have it assumed.
- **`diagnostics.py` reporting the store path.** Measured still true today: it reports neither the
  dismissals file nor the observer sidecar, only harness store roots. Carried from the 2026-08-21
  comment as an accepted exposure for a second file, not fixed here.
- **Concurrent-writer safety beyond last-writer-wins.** The 2026-08-21 comment flags that a history
  writer cannot tolerate whole-file last-writer-wins the way a dismissal writer can. Two dashboards
  on two ports is the case. Not solved here; named so the review does not treat it as an omission.
- **A new promise in `docs/promise-map.md`.** See the label tension below.
- **The observer sidecar's filename drift.** Its module docstring says the file is named
  `<harness>_<sid>.observer.json`; the code writes `<harness>_<sid>.json`. Found while checking what
  Cargento already writes. A one-line docstring fix, and by the captain's standing directive it rides
  in the PR in flight rather than becoming an issue — but it is PR 1's neighbour, not its subject.

## Stage Report: triage

- DONE: Pre-edit record first — the live DRC-4044 body and the `Move up a level` milestone description copied verbatim under `## Linear edits made` before any drafting
  Committed alone as `fce6277` before the first draft existed, so the ordering is in the log rather than asserted; also captures the three comments and the live label/relation set.
- DONE: then the rewrite and any milestone correction drafted in this entity only, nothing written to Linear
  Drafts A (body), B (milestone one-clause fix), C (findings comment) live under `## Linear edits made`. Zero Linear write calls made this stage — only `get_issue`, `list_comments`, `get_milestone`.
- DONE: the adversarial read done against the tree at today's `main` tip AND against the merged contract `docs/plans/history-store-security-scope.md`
  Twelve numbered items against `main` `5a156bc` and contract blob `cd42a19`. Main advanced from `950822b` to `5a156bc` mid-stage; the docs PR the dispatch warned of landed and moved the clause D4 turns on, so findings were re-based onto the corrected text and the blob re-read at the end.
- DONE: naming every claim in the body that describes a state that no longer exists
  Six FALSE claims. The load-bearing one: three of the six kept categories (transitions, gate open/close, tool counts) are not served by the snapshot at all, and tool names reach the wire only through `state_detail`, which the never-list bans. Also FALSE: the panels are windowed by **tab** lifetime, not by server restart — so the old AC could pass against a build that persists nothing.
- DONE: (including its own "P2, new" label tension against the promise map's move table
  Item 8: the labels hold — the journey label names a board column, and every issue in this milestone carries `move:new` — but the body's sentence naming P2 while denying any promise covers it is self-contradictory. `new` permits a promise-map change without compelling one; recommendation is that H1 writes none, since the promise history unlocks is D10's.
- DONE: and the triage notes left as comments on DRC-4044 today)
  D1, D3, D4 carried into `## Decisions for the gate` with recommendations. D3 independently confirmed at the code: the POST table holds seven entries with `/api/events/` prefix-matched outside it (eight), and the "three files" count omits the sidecar. Comments re-fetched at the end — three, unchanged.
- DONE: and whether the approach still fits
  Item 12: yes. What triage changed is the cost, not the direction — the recording lane is new work because the server does not have transitions to serialize.
- DONE: Delivery shape decided and justified from measured facts, not preference
  Two PRs, split on `web/` and nothing else. Justified primarily on two facts the E4 precedent did not have: five issues wait on the store and none on the render, and the tiers differ. The precedent's own byte-pin rationale is recorded as **weaker now** — `test_page.py` no longer exists, so the pins are six figures in one file rather than fifty-six in two.
- DONE: check `git worktree list` and each sibling's web diff against `origin/main` before deciding
  Nine worktrees; two carry web diffs (`docs/sync-next-ui-design-parity`, `worktree-spacedock-boot-rendering`). Both sit on the pre-flattening layout — a `web/next/` subdirectory, `calm.js`, `main.js` that `main` no longer has — and neither has moved since 2026-08-26 / 2026-08-28. `gh pr list`: #259 and #224 touch no web file, so the queue is clear.
- DONE: with each PR's review tier from AGENTS.md's Calibrating Effort table stated
  PR 1: "Security, credential handling, or data loss" → full adversarial. PR 2: "Owns a conflict-prone surface (`web/` byte pins)" → two lenses plus an arbiter. Read straight off the table, no override.
- DONE: Acceptance criteria as end-state properties, each marked offline or interactive with a `Verified by:` clause and a `Falsified by:` change
  Eleven ACs, ten offline and one interactive; audited programmatically that all eleven carry both clauses (AC2 was missing `Verified by:` and was fixed).
- DONE: at least one a property a user can see (the board remembers after a restart)
  AC11, the only interactive one: after a restart and **in a fresh tab**, the rail lists the earlier transitions and the delegation figure renders. Falsified by an empty rail — the exact failure a store that persists but is never published produces. Graded live with a `--no-history` negative case, per the live-scenario rule.
- DONE: an expected surface with tolerance that costs the oracles separately from the runtime
  PR 1: runtime +440/7 files ±20%, docs −60/6 files ±25%, oracles +650/8 files ±25%. PR 2: web +60/3 ±25%, oracles +150/3 ±25%.
- DONE: and names which existing required checks compel new test files
  Five compelled, enumerated by reading each gate's own logic rather than estimating: `CARGENTO_RUNTIME_FILES` (a discovery test asserts set equality), `RuntimeImportGraphTest.EXPECTED` (`assertEqual` over the whole graph), `DECLARED_SESSION_FIELDS`, `test_lifecycle.py`'s seven hand-written namespaces (`AttributeError`, not a failure), and `scripts/bench_collect.py`'s namespace. Plus the `GitProbeContractDocumentationTest` analogue the contract owes, the six `web/` byte pins, and one constraint rather than an edit — the repo-wide sweep asserting only `git_status.py` contains the literal `"git"`, which `history.py` must not trip.
- DONE: and a test plan
  `## Test plan`. AC2 is written first: a byte-level negative over a fixture carrying every operator-text field, which is the only check that catches the nested carriers the never-list omits.

### Summary

H1's body survives as an approach and fails as a description: three of the six things it says the
snapshot already serves are not served, its only user-visible criterion was windowed on the wrong
axis (tab lifetime, not server restart) and could have passed against a build that persists nothing,
and its kept-list must shed tool names and counts because their sole published carrier is a banned
field. The store's one rule is re-read as field provenance rather than record identity, which is the
only reading under which DEC-6's shape is buildable. Five items go to the gate: **D4 is the one that
matters**, because the corrected contract leaves the derived project label in an explicit gap, both
panels group by it, and without a ruling AC11 is not deliverable and H1 ships nothing a user sees.
Two further deviations from the merged contract are recommended and flagged rather than taken
quietly — amendment 1's count arithmetic is wrong because its base already omits the observer
sidecar, and the paragraph justifying on-by-default cites that sidecar as written by default when it
is written on demand. Delivery is two PRs split on `web/`, and the report records that the
precedent's byte-pin rationale is now the weakest of the three reasons rather than reusing it stale.
