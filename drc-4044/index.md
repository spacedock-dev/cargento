---
id:
title: 'H1 · Keep a history of what happened'
status: implementation
source: https://linear.app/recce/issue/DRC-4044
started: 2026-09-03T07:17:13Z
completed:
verdict:
score: 0.5
worktree: .worktrees/spacedock-ensign-drc-4044
issue:
pr: "#260"
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
                state: consumed
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

**PR 2 — the render.** `web/` only, plus the byte pins and the two panel suites. Carries AC10, and
AC12 by the captain's ND-4 ruling of 2026-09-03: the reset header is scoped in here rather than the
clause amended, at roughly five `web/` lines plus a render test over `history_reset`. It rides in this
PR because only one PR may touch `cargento_runtime/web/`.
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

**AC12 (offline, PR 2) — the header reports a store reset with its distinguishable reason.** When a
collection publishes `history_reset`, the page's header says a history reset happened and which of
the two reasons it was; when the field is absent, the header says nothing. Added by the captain's
ND-4 ruling of 2026-09-03 ("scope the reset-header render into PR 2") rather than by amending the
clause: `SECURITY.md`'s "the board starts empty, and the header reports the reset" was a promise with
no implementer, since PR 1 publishes `history_reset` at `aggregate.py:655` and nothing reads it.
*Verified by:* a render test PR 2 adds over `history_reset`, in the header suite that already covers
the other payload-keyed header states, driving both literals — `unreadable` and `version` — and
asserting the rendered text differs between them, plus the absent-field case rendering no notice.
D1's whole point is that a corruption reset may be the user's disk while a version reset is ours, so
a render that showed one message for both would discharge the clause and lose the ruling.
*Falsified by:* a payload carrying `history_reset` and a header identical to one without it — which
is exactly the state PR 1 ships and what this criterion exists to close.

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

**Full adversarial**, from AGENTS.md's Calibrating Effort table, row "Security, credential handling,
or data loss".

**The diff property that justified it:** this PR introduces Cargento's first *persistent* store of
session observations — `history.py`, +463 net, on by default, 14-day retention — so a field that
should never be retained stops being transient in RAM and becomes retained on disk. That is the
data-loss/retention row, not the "anything else" row, and it is why the tier was not negotiated down
despite `web/` being untouched.

**Shape declared before the first spawn:** 4 lenses (contract fidelity; the never-list end to end;
bounds and lifecycle; oracle soundness), 1 completeness critic, 1 arbiter — 6 agents, ~1 per 150 net
runtime lines, against the measured run that spent 35 agents for 10 blocking findings. Amended to
**7** after the lenses returned 24 distinct findings: arbitration was split into two agents, one on
the nine findings that decide GO/NO-GO and one batch-reproducing the oracle tier, both reproducing
rather than ranking. The amendment is recorded rather than taken quietly, because the declared
number is the thing the tier is accountable to.

The arbiters earned the tier: they **refuted or downgraded 9 of the 24**, including one whose factual
premise was wrong in the PR's favour and one where a correct 4.5-second measurement was attached to a
conclusion that did not follow.

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

## Stage Report: implementation

- DONE: the authorized Linear writes performed and read back — Draft A sent verbatim and unwrapped
  Draft A joined to one line per paragraph by script (`/tmp/drc4044/draft-a.md`), no word changed, sent via `save_issue`. Live body now opens `A person who closes Cargento, or reboots, notices this next time they open the board`.
- DONE: Draft B built by script from a fresh capture with an exactly-once assertion and a diff showing one hunk
  Fresh `get_milestone` capture, then asserted: `kept on this machine for 14 days` occurs exactly once, replacement absent beforehand, 1 hunk, +6 chars, 19 lines both sides, exactly 1 line differs, changed line carries no emphasis run or code span. Round-trip compared byte-for-byte against the scripted text: identical, single bold run intact, 0 code spans.
- DONE: Draft C posted as a dated comment
  Comment `2876c1b5-3e53-4c97-ba1c-49f65d501d3e`, 2026-09-03T07:49:45Z, `## What triage measured, 2026-09-03`, returned body identical to the draft.
- DONE: the `journey:mid-flight` and `move:new` labels confirmed present
  Read back on every fetch: `origin:proposed`, `release:r3`, `journey:mid-flight`, `move:new`. Not set by this stage; confirmed only.
- DONE: the relation set read back after each write
  Unchanged across all three writes: `blocks` 5 (DRC-4051/4043/4042/4033/4009), `blockedBy` 0, `relatedTo` 3 (DRC-4234/4039/4330). No new edge, so nothing Material.
- DONE: every emphasis-boundary move reported rather than repaired
  **One move, in Draft A's `## History` section.** Sent: `**Waits on DRC-4330 — cleared 2026-09-03.**`. Stored: `**Waits on** <issue…>DRC-4330</issue> **— cleared 2026-09-03.**` — the serializer split the bold run around the issue mention it created. Not repaired, per the rule. Note this is a *new* trigger shape: triage measured the trigger as an emphasis run ending before a code span, and this run contains neither a code span nor a trailing one — the mention itself split it. Draft B and Draft C moved nothing.
- DONE: `recce-dev:linear-deep-dive` run for this issue and stopped at step 6
  Spacedock mode, non-intake stage. Steps 2-3 (fetch with relations and comments; classified Feature), step 4 codebase exploration, step 6 approach recorded. Step 7 is the FO's and was not entered; no `docs/plans/` analysis doc written, per the adapter. Step 4e skipped: the entity's twelve-item adversarial read already supplies the blind-spot pass, and no captain was present to ask. Key files it produced: `dismissals.py` (write template), `git_status.py` (leaf shape), `observation.py`, `aggregate.py`, `cli.py`, `lifecycle.py`. Key risks it produced, all three of which bit: the `["']git["']` sweep at `test_git_status.py:160`, the whole-AST import graph (so a `TYPE_CHECKING` import still counts), and the seven `test_lifecycle` namespaces.
- DONE: AC2 written first and watched to fail against a store that records the row
  Written against `observation()` returning `dict(row)`. Failed 7 ways — `title`, `last_prompt`, `state_detail`, `instruction.text`, `tasks[].subject`, `tasks[].activeForm`, `subagents[].name` — including all three nested carriers the contract's never-list omits. Narrowing that one function to the derived record turned it green with nothing else changed. Falsified by: recording the row instead of the triple.
- DONE: `history.py` as a leaf importing only `config`
  `RuntimeImportGraphTest` recomputed: `cargento_runtime.history` -> `{cargento_runtime.config}`, and `cli` is the *only* importer to gain an edge. `io.diag` is inlined and the diagnostic sink is a parameter to keep it. Falsified by: importing `records` or `io`, which the whole-graph `assertEqual` rejects.
- DONE: the recording lane, the published field, `--no-history` at all four of `--no-git`'s sites, `--forget`
  Lane at `history.Lane`, injected at assembly (see the deviation below). Published as `collection["history"]` plus `collection["history_reset"]`. Flag at `cli.build_parser`, `cli.build_runtime`, `config.RuntimeConfig`/`build_runtime_config`, and `lifecycle.spawn_argv` — read as `args.no_history` directly, which is what made the seven namespaces raise `AttributeError` (confirmed: 14 errors before the edit, not a quiet pass). `--forget` in `run_one_shot` beside `--stop`/`--status`, refused with `--daemon`.
- DONE: the contract promoted into `SECURITY.md` with the plan doc deleted in the same commit
  Both in `9b51cd2`. The fenced section was extracted by script and diffed: exactly 3 hunks, all D4/D5, every other line byte-identical.
- DONE: the three captain-authorized deviations applied and named
  Exact before/after sentences below, under **Contract deviations**.
- DONE: the `SKILL.md`, `HOW_TO_USE.md` and architecture-doc rows, and the observer-sidecar docstring fix
  `SKILL.md`: count three->four with the store enumerated, `--no-history` row added, `--no-dismiss` row's sole-occupancy claim removed. `HOW_TO_USE.md`: `--no-history` row in the off-switch table, `--forget` documented with the one-shot commands rather than in it. `docs/design-runtime-architecture.md` and `AGENTS.md`'s tree gained the module. `observer.py:4` docstring `<harness>_<sid>.observer.json` -> `<harness>_<sid>.json`, matching what `observer.py:591` writes.
- DONE: the compelled oracle edits plus `tests/test_history.py` and the `HistoryStoreContractDocumentationTest`
  Four of the five predicted were compelled and edited: `CARGENTO_RUNTIME_FILES`, `RuntimeImportGraphTest.EXPECTED`, `test_lifecycle.py`'s seven namespaces plus two tuples plus the `--forget` row, and `bench_collect.py`'s namespace. **`DECLARED_SESSION_FIELDS` was NOT compelled** — the build adds a payload field, not a row field — so it is read by AC1 rather than edited. `test_history.py` is 43 tests; `HistoryStoreContractDocumentationTest` is 8, modelled on `GitProbeContractDocumentationTest`, with the plan-doc assertion as `assertFalse(...exists())`.
- DONE: `history.py` free of the quoted literal "git"
  Regex `["']git["']` finds nothing in the file, and `test_only_git_status_constructs_a_git_subprocess` still reports `["git_status.py"]`.
- DONE: the canonical pre-PR suite from `AGENTS.md` run once
  ruff check, `ruff format --check`, mypy --strict (110 files), `lint_embedded.py`, `validate_plugins.py`, `bump_version.py --current` (0.20.0), the merge-base version diff (empty), 1817 tests OK in 33s, the seven scripts suites, `coverage report` 90.2% against `fail_under = 73`, and both native validators. **No red to re-run:** none of `test_http_api`, `test_page`, `test_lifecycle` or `test_quota` failed. Load average was 9.5, but `ps` showed no competing unittest process — the load was SkyLight and Spotlight, not a sibling suite.
- DONE: `sync-docs` invoked with its commit on this branch
  `3a12b97`. Found no remaining `.md` drift (the implementation commit already carried the doc rows) and three code-side items instead: two docstrings still claiming the dismissals file is the only thing Cargento writes on the reader's behalf (`8796828`), and a missing `--no-history` assertion in the `build_runtime` test that asserts each off switch separately (also `8796828`, falsified by deleting the `build_runtime` line and watching only that assertion fail). Marker left alone per the parallel-branch rule. One item reported unresolved: `SECURITY.md:356` carries an em dash inside the promoted contract text, which must stay byte-for-byte. Tone baseline was 3 flagged lines and is now 1.
- DONE: the diff reviewed in the worktree before opening
  It found a real defect in my own code, fixed in `83ae971`: the store's four strings reach the DOM through `/api/data` and the read-back path did no bounding or stripping, so a tampered file could put a U+202E bidi override in a project label or a 5,000-character label on the board. Four tests, failing six ways without the sanitiser.
- FAILED: the surface measured against PR 1's three estimates before the PR opens, stopping and putting it to the captain if any axis is beyond tolerance
  Measured, beyond tolerance on two axes, and **stopped as the checklist directs** — so this item is discharged by stopping, and the PR below is what it blocks. Runtime net +570 vs +440 (+30%, tol +/-20%); Docs net -48 vs -60 (+20%, within); Oracles net +828 vs +650 (+27%, tol +/-25%). File counts hit all three estimates exactly: 7/7, 6/6, 8/8. Attribution: 70 lines from the `--no-events` deviation, ~44 from the two ruff-compelled refactors, 84 from the security fix. Put to the captain through the FO with options A (accept, recommended), B (trim comments, recommended against), C (design reset, recommended against).
- FAILED: a PR opened whose body starts `Implements [DRC-4044](…) — H1 · Keep a history of what happened` with a `## Verification` section, its number and head SHA reported
  Not opened, deliberately: the stage definition says to stop and put a tolerance breach to the captain "rather than opening the PR". Branch pushed instead — `spacedock-ensign/drc-4044` at `83ae971`, four commits. The PR body is drafted and opens on the captain's ruling.
- DONE: `## Stage Report: implementation` giving AC1-AC9 an evidence citation, AC10 named as PR 2's and AC11 as the live drive the issue owes
  Below.

### Contract deviations, all captain-authorized (2026-09-03)

**D3, two counts.** `SECURITY.md` before: `The server writes three files, all under ~/.cargento … and cargento-dismissals.json, the sessions the reader marked handled, described in Dismissals below. One forwarder writes a fourth`. After: `The server writes five files … cargento-dismissals.json …; observer/<harness>_<sid>.json, the sidecar GET /api/observe records when a reader opens that panel for a session, named in invariant 2 above; and cargento-history.json, the history of what this server observed, described in Local history above. One forwarder writes a sixth`. This deviates from the plan doc's literal "four" and "fifth" because the base enumerated three while the server writes four — the sidecar was missing, so the enumeration gained it to make "five" true. Second count, before: `Writing is the seven POST routes, /api/shutdown and /api/answer among them`. After: `Writing is the eight POST routes, …`. Verified at the code rather than inherited: the exact-match table in `do_POST` holds 7 entries and `/api/events/` is prefix-matched ahead of it, so 8; invariant 2's separate "Seven endpoints mutate" is correct as it stands and was not touched.

**D4, the project label.** Kept-list before: `…turn boundaries and their timings, and tool names and counts.` After: `…turn boundaries and their timings, tool names and counts, and the derived two-segment project label the board groups by: it is published on every row, it is capped at the last two segments rather than being a path, and both panels that read the history group by it, so the history cannot be seeded without it. Never a raw working directory.` And the one-way clause, before: `which the kept-list above omits while the never-list bans the paths it is derived from`. After: `which the kept-list above keeps while the never-list bans the paths it is derived from`. Bound to the code by `test_the_kept_list_names_the_project_label_the_store_actually_keeps`.

**D5, the on-by-default precedent.** Before: `Cargento already writes local state on the user's behalf by default in the dismissals file and the observer sidecar.` After: `Cargento already writes local state on the user's behalf by default in the dismissals file, and writes the observer sidecar on demand when a reader opens that panel for a session.` Two clauses; no other sentence in that paragraph moved.

**A fourth deviation, NOT pre-authorized — from the approved `## Proposed approach`, not from the contract.** The approach places the recording lane in `observation.py`. Measured obstacle: `Application.overlays` is documented at `aggregate.py:441` as "None until the coordinator is attached, and None forever under --no-events", and `cli.py:343` builds the coordinator only inside `if not args.no_events:`. A lane reached that way would be silently dead under `--no-events`, contradicting the promoted contract's `The off switch is --no-history.` and leaving the five dependent issues reading an empty store. Built instead as `history.Lane`, injected at assembly, consumed by `aggregate` through a locally-declared `HistoryLane` Protocol so `aggregate` gains no import of `history`. Flagged to the FO when found, before the code was written. `test_a_collection_with_no_lane_publishes_nothing_and_does_not_raise` and the `source is None` branch in `_apply_overlays` are what hold it.

**One reading recorded rather than deviated from.** The promoted kept-list still names gate open/close, turn timings and tool names/counts, none of which PR 1 records. It is read as a permission ceiling, not a description, on the plan doc's own closing words — "It fixes what may be kept, how it is written, how long it survives, and how it is turned off and deleted" — so keeping less than the list is compliant and no sentence needed changing. Recorded so the review does not read it as an oversight.

### Acceptance criteria

- **AC1** — `EveryStoredFieldIsAPublishedFieldTest`, 4 tests. The record's key set is `{harness, sid, project, state, last_activity}`; containment is asserted against `test_sessions.CargentoServerTest.DECLARED_SESSION_FIELDS` and disjointness against a literal 7-name ban tuple, both from outside `history.py`. Falsified by adding `state_detail` to a record, or keying on a raw `cwd` (asserted absent).
- **AC2** — `NothingPromptDerivedReachesTheStoreTest`, 2 tests, written first and watched to fail 7 ways. Reads the store file as bytes. Paired with a positive so a store that writes nothing cannot pass. Falsified by recording the row.
- **AC3** — `EvictionTest`, 3 tests. Age eviction, then the cap dropping oldest-first, then the store unchanged after the cap is raised. The middle test asserts the newest observation survived and the oldest did not, which is what fails under `dismissals.py`'s refuse-when-full policy.
- **AC4** — `OwnerOnlyWriteTest`, 3 tests. `0o600` on the file and `0o700` on the directory, both skipped on Windows where the mode is advisory (`platform-tests` re-runs there); plus a failed write that leaves no `.tmp` behind and reports rather than raises. Falsified by `open()` then `os.chmod`, or writing in place.
- **AC5** — `UnreadableStoreIsDiscardedTest`, 5 tests. Corrupt bytes and an oversized file report `RESET_UNREADABLE`; a bumped `v` reports `RESET_VERSION` (D1's distinguishable reason); a missing file reports neither; one malformed record does not discard the others. Falsified by repairing a partial store, or one reason for all three.
- **AC6** — `OffMeansOffTest` (2) and `LaneTest.test_the_lane_writes_nothing_when_the_store_is_off`. No file after a cycle under the flag, and a pre-seeded store reads back empty. Falsified by gating only the read, which would leave the file growing while the user believed it off.
- **AC7** — `SpawnArgvOptOutTest.test_no_history_is_forwarded` and `…_is_absent_when_not_requested`, plus `--no-history` in the whole-set opt-out tuple. The recommendation was taken: `spawn_argv` reads `args.no_history` directly, which is what forces the seven-namespace edit — measured as 14 `AttributeError`s, not a quiet pass.
- **AC8** — `ForgetIsACommandAndNotARouteTest`, 4 tests, plus `ForgetTest`'s 3. Exit 0 with the file gone and `CargentoHTTPServer` never constructed; the message when there was nothing to delete; deletion with the store disabled; `--forget` added to the `--daemon` rejection loop; and the POST surface asserted unchanged by AST — one route table of exactly 7 entries and exactly 1 prefix match, none naming history or forget, with `http_api.py` containing neither the store filename nor `/api/history`.
- **AC9** — `HistoryStoreContractDocumentationTest`, 8 tests. The section heading survived; the plan doc does not exist; `The off switch is --no-history.` is bound to `build_parser().parse_args(["--no-history"])`, and the `--forget` sentence to its flag, so neither is a grep over our own prose; the documented path is bound to `store_path`, the 14-day figure to `history_retention_sec`, and D4's kept-list clause to `OBSERVATION_FIELDS`.
- **AC10** — **PR 2's.** No file under `cargento_runtime/web/` is touched; `test_next_page.py` is untouched and its six byte pins are unrecomputed, correctly.
- **AC11** — **the live drive the issue owes.** Not attempted here: it needs a fresh browser tab against a restarted server, and it is gated on PR 2 publishing the panels. PR 1's honest intermediate claim is the one triage wrote — the store records, `/api/data` carries it, `--no-history` turns it off, `--forget` deletes it, and the panels do not use it yet.

### Summary

PR 1 is built, committed on `spacedock-ensign/drc-4044` (`9b51cd2`, `8796828`, `3a12b97`, `83ae971`) and green on the whole canonical suite, but **the PR is deliberately not open**: the runtime surface came in at +30% and the oracles at +27% against +/-20% and +/-25%, and the stage definition says a tolerance breach goes to the captain as a design reset rather than into a PR. The file counts hit 7/6/8 exactly and no scope widened; the entire overage is three correctness items the triage estimate could not have priced — the `--no-events` coupling that made the approved lane placement unbuildable, two refactors ruff's own complexity caps compelled once `--forget` and the published field landed, and a disclosure defect the mandated worktree diff review found in my own code, where the store's strings reached the DOM unbounded and unstripped on the read-back path. Three contract deviations were applied exactly as authorized and each is recorded above with its before/after sentence; a fourth, from the approved approach rather than the contract, was flagged to the FO before any code was written. Two findings worth the reviewer's attention beyond that: `DECLARED_SESSION_FIELDS` was not in fact compelled, because the store publishes a payload field rather than a row field, and the emphasis-boundary guard moved on a shape triage had not measured — an issue mention splitting a bold run, with no code span involved.

## Stage Report: implementation (cycle 2)

Correction round against the FO's authorization of the lane placement and its two conditions. Code branch `spacedock-ensign/drc-4044`, now five commits, head `5f73639`. Still no PR, because the surface question the first report raised is now larger rather than settled.

- DONE: the lane placement recorded with both citations
  `aggregate.py:441` ("None until the coordinator is attached, and None forever under `--no-events`") and `cli.py:343` (`if not args.no_events:` guarding the only construction). Both are already in the cycle-1 report's **Contract deviations** block and both go in the PR body's `## Verification`. Authorized as a mechanism change inside approved scope, not a scope or AC change.
- DONE: condition 1a — the lane writes only on an observed transition, never per collection cycle
  The transition rule is now enforced by a returned flag rather than implied: `history.appended()` returns `(kept, changed)` and the caller skips `save()` entirely when `changed` is false. Test: `AQuietBoardDoesNotGrowTheStoreTest`, 2 tests, and the oracle is the **file** rather than a record count — twenty collections of an unchanged board leave both the bytes and `st_mtime_ns` untouched. Falsified by appending per cycle, which the coordinator's `reconcile_interval_sec` tick would turn into roughly 2,880 records a day per session in a store nothing had happened in.
- DONE: condition 1b — the write is outside the coordinator lock
  `observation._collect` takes `self._lock` only to snapshot `_dirty` and clear `_coalesce_until`/`_urgent`, releases it, and *then* calls `application.collect_json`. The write therefore never runs under the coordinator lock. The lane holds a lock of its own during the write; it is lane-local, is never held across a collection, and is the same shape `dismissals.dismiss` uses.
- FAILED: condition 1b — the write is off the HTTP handler thread
  **Not done, and I recommend not doing it. Reporting rather than quietly accepting.** It genuinely can run there: `http_api.py:473` calls `collect_json` on the request thread, which collects when the snapshot is stale, so a transition observed by a `GET /api/data` writes on that thread. What the measurements say, all at the 1 MiB cap, which needs ~8,885 recorded transitions to reach:
  - a real `Application.collect` over this machine's stores: **154 ms** median;
  - `Lane.record` with a transition: **21 ms** (was 44 ms before this round's in-memory baseline, because the re-read was 23 ms of it against the write's 6);
  - `Lane.record` on a quiet board: **1.8 ms**, and no disk touch at all.
  So the write is 14% of a collection it already rides inside, on the rarest path, and zero on the common one. Taking it off the request thread needs a writer thread, a one-slot mailbox, and a shutdown flush wired through `lifecycle.serve` — roughly 70 more lines on a PR already over tolerance — and it introduces a failure mode the synchronous write does not have: a shutdown that loses the last transitions, which is a hole in the one promise this issue exists to keep. I have not built it. Say the word and I will.
- DONE: condition 2 — AC2's fixture drives through the real aggregate path
  `NoOperatorTextSurvivesTheRealCollectionTest`. A stub harness returns a `base_session` row carrying all seven sentinels, and the assertion travels the real path: `collect` -> `dedupe_sessions` -> `_redact_published_text` -> `_apply_overlays` -> the lane -> disk. It asserts the row really did publish its sentinel (so the fixture cannot silently stop carrying one) and that none of the seven is in the store's bytes. Falsified by reverting `observation()` to `dict(row)`: fails seven ways there while the unit form of AC2 still passes, which is the gap the condition names.
- DONE: `DECLARED_SESSION_FIELDS` recorded as one fewer oracle edit than estimated
  Not compelled, because the build publishes a payload field (`collection["history"]`) rather than a row field, so `sessions.base_session` is unchanged and the declared set is *read* by AC1 rather than edited. Counted against the estimate: the oracle axis was costed at 8 files including it, and came in at 8 files with `test_config_diagnostics.py` taking its place — that one was not estimated at all and is where the `--no-history` `build_runtime` assertion went.

### Surface after this round

| Axis | Estimate | Cycle 1 | Cycle 2 | Tolerance | Verdict |
|---|---|---|---|---|---|
| Runtime | +440 / 7 files | +570 (+30%) | **+618 (+40%)** | +/-20% | OUT |
| Docs | -60 / 6 files | -48 (+20%) | -48 (+20%) | +/-25% | within |
| Oracles | +650 / 8 files | +828 (+27%) | **+948 (+46%)** | +/-25% | OUT |

File counts still hit 7/6/8 exactly. Every increment since triage is a correctness requirement rather than scope: 70 lines for the `--no-events` lane placement, ~44 for two refactors ruff's own complexity caps compelled, 84 for the read-back disclosure fix the worktree diff review found, and 168 for this round's two conditions. AC1-AC9 remain the whole of it and no file under `cargento_runtime/web/` is touched.

The honest reading is that the triage estimate was made before three things were known: that the approved lane placement was unbuildable, that the store's strings reached the DOM unbounded, and that the review would require the transition rule and AC2 to be proven rather than asserted. The estimate is not wrong about the shape of the work; it is wrong about the cost of proving it correct. That is a design-reset question only the captain can answer, and it is the one blocking the PR.

### Summary

Both of the FO's conditions are satisfied and each is falsifiable: the transition-only rule is enforced by a flag and checked against the file's own mtime, and AC2 now travels the real aggregate path and fails seven ways without the derivation. The lane placement is recorded with both citations. One condition I did not meet and am not hiding: the write can still run on an HTTP handler thread, and I recommend leaving it there on the evidence that it costs 21 ms at the absolute worst case inside a 154 ms collection, is 1.8 ms and disk-free on a quiet board, and that moving it would add a writer thread plus a shutdown-flush path whose failure mode is losing the last transitions before a restart. The surface is now +40% runtime and +46% oracles, worse than when I first escalated, because satisfying correctness conditions costs lines; the captain's A/B/C ruling is still what this stage is waiting on.

## Stage Report: implementation (cycle 3 — tolerance ruled, PR opened)

- DONE: a PR opened whose body starts `Implements [DRC-4044](https://linear.app/recce/issue/DRC-4044) — H1 · Keep a history of what happened` with a `## Verification` section, its number and head SHA reported
  **PR [#260](https://github.com/spacedock-dev/cargento/pull/260), head `5f736392e61a2c9f81baebf0af00a81703b0993d`.** Supersedes the cycle-1 `FAILED` entry for this item, which was held pending the tolerance ruling. Body verified after opening: first line exact, `## Verification` present, no `Closes` line (no mirrored GitHub issue exists).
- DONE: the tolerance overage accepted and recorded
  `captain-ruling[2026-09-03]` — verbatim: "Yea A - Accept and open the PR". Both overages accepted as compelled correctness rather than scope, with the causes on the record. Quoted in the PR body's surface section alongside both sets of figures.
- DONE: the surface figures carried into the PR with the ruling's own numbers distinguished from the head's
  The ruling was given against cycle 1's figures at `83ae971` (runtime +30%, oracles +27%); the head carries cycle 2's (runtime +40%, oracles +46%), because the two review conditions landed after the ruling. Both columns are in the PR body's table rather than only the accepted ones, so the delta is visible in review rather than discovered there. Flagged to the FO before opening.
- DONE: opened from the head that contains the correction round, not the SHA named in the authorization
  The FO's instruction named `83ae971`. That commit predates the two conditions the same FO required — it lacks the transition-only flag, the real-path AC2 test and the in-memory baseline. Opened from `5f73639` so the conditions ship, and the discrepancy was put to the FO rather than resolved silently.

- DONE: the required checks confirmed green on the PR head, not just locally
  All twelve pass at `5f73639`, and they belong to this head rather than a superseded one: `quality-gate` (the required context), `validate`, `version-guard`, Lint, `mypy --strict`, Runtime floor (3.11), Tests + coverage threshold, `latest-client-smoke`, and **platform-tests on all three OSes** — ubuntu 27s, macos 1m38s, **windows 1m32s**, which is the run that exercises AC4's advisory-mode skips rather than asserting a POSIX mode on a platform that ignores it.

### Summary

The captain ruled A and PR [#260](https://github.com/spacedock-dev/cargento/pull/260) is open at head `5f73639` with every required check green, carrying AC1-AC9 with `## Verification` naming every command and what it said, all four deviations with their before/after sentences and file:line citations, the threading and lock discipline with its measurements, and the surface figures against the estimate with the ruling quoted. Two departures from the letter of the authorization, both reported rather than taken quietly: the PR was opened from `5f73639` instead of the named `83ae971`, because the named commit predates the FO's own conditions, and the accepted figures are labelled as cycle 1's beside the head's higher ones. Implementation is complete; the stage's remaining exposure is AC11, the live drive the issue owes once PR 2 renders the panels.

### FO dispositions recorded (2026-09-03)

- **The tolerance ruling applies on the principle, not on a number.** The captain's "Yea A - Accept and open the PR" accepted the overage as compelled correctness; the FO takes the post-ruling increment under that same ruling, having directed it. So the figures of record are the head's — **runtime +618 (+40%), oracles +948 (+46%), docs -48 (+20%), file counts 7/6/8 exact** — with the four causes attributed: 70 lines for the `--no-events` lane placement, ~44 for the ruff-compelled refactors, 84 for the read-back disclosure fix, and **168 FO-directed** for the two review conditions. If a smaller PR is wanted, the review gate is where that is said.
- **The writer-thread decline is accepted as the disposition, not left as the worker's preference.** Measured trade on the record so the adversarial review argues with numbers rather than with the shape: a real `Application.collect` over this machine's stores is **154 ms** median; `Lane.record` is **21 ms** with a transition at the 1 MiB cap (~8,885 recorded transitions to reach it) and **1.8 ms with no disk touch at all** on a quiet board. So the write is 14% of a collection it already rides inside, on the rarest path, and zero on the common one. Against that: roughly 70 lines for a writer thread, a one-slot mailbox and a shutdown flush through `lifecycle.serve`, plus a failure mode the synchronous write does not have — a shutdown that loses the last transitions, which is a hole in the one promise this store exists to keep. The write is confirmed **outside the coordinator lock** (`observation._collect` releases `_lock` before `collect_json`); the lane's own lock is lane-local and never held across a collection.
- **What the conditions were worth, measured.** Condition 1a caught an unbounded writer before review: without the transition rule the coordinator's `reconcile_interval_sec` tick would have appended roughly **2,880 records a day per session** to a store nothing had happened in. Condition 1b's lock audit is what surfaced the redundant re-read, taking a transition-bearing collection from **44 ms to 21 ms** — the re-read was 23 ms of it against the write's 6, on a path that can be answering an HTTP request. Condition 2 closed a real gap: the unit form of AC2 passes for a caller that hands whole rows to a narrow record, and the real-path form fails it seven ways.

## Stage Report: review

- DONE: Review depth stated up front as the full adversarial tier the gate assigned, the fan-out declared before any spawn, each lens given one question, and the arbiter reproducing rather than ranking
  `## Review depth` above carries the tier, the justifying diff property, the declared 6-agent shape and the recorded amendment to 7. Arbiters refuted or downgraded **9 of 24** findings; the fix set that survived is ~15 code lines and ~70 test lines, no redesign.
- DONE: the promoted `SECURITY.md` section diffed against the plan doc's fenced section at `5a156bc`, exactly the three authorized deviations, plan doc confirmed absent
  Mechanical `diff -u` plus `--word-diff` of the extracted fenced section (65 lines) against the promoted section (69 lines): **exactly three hunks**, all authorized — D4 kept-list clause with its reason, the `omits`→`keeps` consequence of the same D4 edit, D5's dismissals/sidecar correction. D3's numbers verified *at the code*, not inherited: five real write sites (`lifecycle.py:126` + the log, `dismissals.py:166`, `observer.py:636`, `history.py:282`) and eight POST routes (7 exact-match entries + prefix-matched `/api/events/`), with `http_api.py` byte-identical to `main` so no route was added. Plan doc absent: `git show 5f73639:docs/plans/history-store-security-scope.md` → `fatal`. Amendments landed at `SECURITY.md`, `SKILL.md`'s file count and `--no-dismiss` row, and `cli.py`'s help string; no sole-occupancy claim survives anywhere in the tree.
- DONE: AC1 through AC9 each reproduced from its own `Verified by:` clause, with falsifying mutations re-applied
  AC1 sound and non-vacuous — the containment set really is imported from `test_sessions.CargentoServerTest.DECLARED_SESSION_FIELDS` and the ban list is a literal; `test_sessions.py` was correctly not compelled because the PR publishes a payload field, not a row field. **32 mutations applied in throwaway copies: 20 RED, 12 GREEN.** Every falsification the entity names by name goes RED (`state_detail` in the record → 5 tests; a raw `cwd` key → 3; a whole-row copy → 17; refuse-when-full → `test_inside_the_window_the_size_cap_drops_the_oldest_first`; gating only the write → 2; `--forget` only when enabled → 1; omitting the `spawn_argv` branch → 2). AC7's recommendation was taken — `spawn_argv` reads `args.no_history` directly, so a missing namespace field raises. AC4's mode is `0o600` from `os.open` with the Windows skip present rather than absent. AC8's POST surface asserted unchanged by AST. AC9's eight tests bind prose to `parse_args`, `store_path` and `OBSERVATION_FIELDS` rather than grepping our own words. The strongest oracle in the file is the transition-only bytes+mtime test. **AC10 is PR 2's** — `web/` is untouched and `test_next_page.py`'s six byte pins are correctly unrecomputed. **AC11 is the live drive the issue owes**, gated on PR 2; no capture exists under `docs/captures/`, correctly.
- DONE: the four recorded implementation decisions each independently checked
  (1) The `--no-events` lane placement: both citations verified — `aggregate.py` documents `overlays` as None forever under `--no-events` and `cli.py` builds the coordinator only inside `if not args.no_events:`, so the `history.Lane`-injected-by-`cli` shape is correct and `aggregate` gains no import of `history`. (2) The read-back sanitiser: the inlined table is **behaviourally identical** to `records._UNSAFE_CHARS` across all 1,112,064 non-surrogate code points (0 differing), ZWJ/ZWNJ carve-out intact in both — the two pattern *strings* differ only in source escaping. (3) The transition-only write: confirmed byte-for-byte and `st_mtime_ns`-for-`st_mtime_ns` over 20 quiet collections through the real `Application.collect`, and the ~2,880/day arithmetic checks out against `reconcile_interval_sec = 30.0`. (4) The declined writer thread: 4 of 5 figures reproduce (`Lane.record` 22.5 ms transition / 1.92 ms quiet; `save` 6.88 ms; `load` 22.41 ms; 8,666 records to the cap vs the claimed ~8,885), the 154 ms `collect` measured 136.5 ms here (within 12%, and the figure is a property of the store), and the lock claim is **correct as read** — the write is outside the coordinator lock and the lane's lock is lane-local. The decline stands on the median; see **DR-1** for where the worst case does not support it.
- DONE: CI read on head `5f73639`, `mergeStateStatus`, Copilot inline comments, and the surface figures re-derived
  All **twelve** required checks `success` and every one belongs to `head_sha` `5f73639`, not a superseded head: `quality-gate`, `validate`, `version-guard`, `Detect what the gate can measure`, Lint, `Type check (mypy --strict)`, `Runtime floor (Python 3.11)`, `Tests + coverage threshold`, `latest-client-smoke`, and **platform-tests on all three OSes** (`Tests (ubuntu-latest)`, `(macos-latest)`, `(windows-latest)` — the Windows run is what exercises AC4's advisory-mode skips). `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`. **Copilot left no inline comments and no top-level review — there are zero of both**, because no review was ever requested; `gh pr edit --add-reviewer Copilot` fails on this repo with `Could not resolve user with login 'copilot'`, so Copilot review is not available here rather than merely unread. Surface re-derived with `git diff --numstat` against merge base `5a156bc`: **runtime +618 / 7 files, oracles +948 / 8 files, docs −48 / 6 files** — all three match the head figures of record exactly. No version field moved.
- DONE: the local gate reproduced independently of CI
  `ruff check` all passed; `ruff format --check` 149 files formatted; `mypy` clean over 110 files; `validate_plugins.py` OK; `bump_version.py --current` → 0.20.0. Full suite run **once**, cleanly: **1824 tests, OK, 1 skipped, 34.0s**. First attempt was abandoned rather than reported: it was launched at load average **40.7** with four concurrent agent unittest processes, which AGENTS.md's measured rule says makes contention failures near-certain, so it was killed and re-run at load 6 instead of banking a red I would then have had to disprove.
- DONE: a GO or NO-GO verdict with findings under their disposition labels
  **NO-GO.** Five Material findings, all reproduced by an arbiter against `5f73639`. Details below.
- SKIPPED: on GO, the worktree removed before the branch is deleted
  Verdict is NO-GO, so nothing was removed. The worktree at `.worktrees/spacedock-ensign-drc-4044` is untouched and still on `spacedock-ensign/drc-4044` at `5f73639`; no merge, no branch deletion, and no edit to the PR branch from this stage.

### Findings under their disposition

Five **Material**. Each was reproduced by an arbiter in a throwaway `git archive` copy, never on the branch.

**M-1 — the store persists a full home-relative filesystem path, not a two-segment label.**
- *Released user and normal workflow:* store on by default, no flag, an ordinary Claude session. When a transcript carries no `cwd` record in its first 50 lines, `collectors/claude.py` falls back to `sessions.project_label(...)`, which strips only the encoded home prefix and returns **every remaining segment** joined by `-`. Same code shape at `collectors/gemini.py` and `collectors/droid.py`.
- *Observable harm:* a multi-segment path, sometimes username-bearing, sits in `~/.cargento/cargento-history.json` for 14 days and is republished in `/api/data`. Real measured values include `repos-recce-recce-cloud-infra--claude-worktrees-drc-3976-finish` — six segments of the user's actual layout.
- *Affected boundary:* `contract[SECURITY.md#local-history-the-session-history-store]` — never-list "**Paths.** Neither a session's working directory nor any path a tool touched", plus the kept-list's "Never a raw working directory"; and `captain-ruling[2026-09-03]` D4, which authorized a *derived two-segment* label and nothing wider. The section's own closing clause names "a path … reaching it by any route" a security bug.
- *Trigger evidence:* **29 of 3888** real transcripts (0.75%) have no `cwd` in the first 50 lines; 1 of 27 in the last 24 h. Reproduced end-to-end through `cli.build_application(...).collect_json()` with the path landing verbatim in the store file.
- *Narrowed by the arbiter, and it matters:* the live board publishes the identical string, so **AC1's field-provenance rule is NOT violated** — this is a retention violation only, and any write-up claiming a containment breach is wrong. The droid/gemini fallback could not be made to fire on this machine's real stores.

**M-2 — `--forget` does not forget while the dashboard is running.**
- *Released user and normal workflow:* `--daemon` is the documented persistent shape and `--forget` is the only delete route. `Lane` latches its baseline in memory on first read and never re-reads.
- *Observable harm:* the user is told `Cargento: deleted …`, and every record returns on the next state transition. Reproduced: 2 entries → `forget()` → file gone → one transition → **3 entries back on disk**.
- *Affected boundary:* `contract[SECURITY.md#local-history-the-session-history-store]` — "`--forget` deletes the store and exits … because what it does is **not reversible by running the next command without it**", and "the bounds above and **the delete below** are what answer" the default-on trust cost.
- *Trigger evidence:* the reproduction above, plus the two-dashboard corollary — lanes A and B over one config leave B's record **permanently** lost. `HOW_TO_USE.md` and `SECURITY.md` are the only two mentions and neither says stop the server; `HOW_TO_USE.md` actively files `--forget` with `--status` and `--stop`, three lines under text saying those two "find a live instance by probing the port". `lifecycle.instance_status` is that probe, so detection is one cheap call already in the module.

**M-3 — a tampered store takes the whole board down, and `--diagnose` cannot diagnose it.**
- *Released user and normal workflow:* `history.py`'s own docstrings name this threat model four times ("this file is one any local process could have replaced"), so the module accepts it; the validation is incomplete against it. `_entry` gates `last_activity` with `isinstance(stamp, (int, float))` and never bounds it, and `json.loads` accepts `Infinity`/`NaN` by default.
- *Observable harm:* two shapes. (i) `Infinity` (or `1e400`) makes `aggregate.py:953`'s `json.dumps` emit a bare `Infinity` token, so the **entire** `/api/data` body is rejected by `JSON.parse` — the whole board, not the history panel. (ii) a JSON integer too large for a float raises `OverflowError`, which is **not** in `_decode`'s except tuple, escapes `load` → `Lane._open` → `Lane.record` → `Application.collect` → `collect_json`, and is never latched because `_open` sets `_opened = True` only after `load` returns — so every subsequent collection raises again. A live server returns **HTTP 000, empty reply, permanently**, and `--diagnose` crashes on the same line, so the tool `SKILL.md` tells the user to run first cannot report it. Nothing names the history store outside a raw traceback frame.
- *Affected boundary:* `contract[SECURITY.md#local-history-the-session-history-store]` — "A store that cannot be read is discarded rather than repaired. Corrupt bytes, an unreadable file, a version the running build does not understand: **in every case** the store is dropped, the board starts empty, and the header reports the reset." Neither shape drops the store; one poisons the payload silently, the other refuses to serve.
- *Trigger evidence:* I reproduced (i) myself end-to-end before any arbiter ran — the body contained a bare `Infinity` and `node -e "JSON.parse(...)"` threw `SyntaxError`. Arbiter A independently reproduced both, plus HTTP 000 from a live server on `--port 47311` and the `--diagnose` traceback. Arbiter B found the same root cause distorts eviction ordering via `NaN` while `load` reports a **clean open** (`reset=None`). One `math.isfinite` guard plus `OverflowError` in the except tuple closes all of it.

**M-4 — retention is enforced only as a side effect of a write.**
- *Released user and normal workflow:* `evict` is reachable only from `appended`, which returns `held, False` before reaching it when no transition was produced, and `load`/`_decode` never evict. A finished project, an uninstalled harness, or a machine left running with no active sessions produces exactly that.
- *Observable harm:* observations older than 14 days stay on disk without bound and are published in `/api/data`. Reproduced: 5 entries aged **100 days**, published and on disk, against a genuinely empty board.
- *Affected boundary:* `contract[SECURITY.md#local-history-the-session-history-store]` — "Retention is 14 days by default" and "an unbounded store … is a security bug"; also `cargento/skills/cargento/SKILL.md` "kept for up to 14 days". `value-ac[AC-3]` holds for `history.evict` in isolation and fails for the store as a lifecycle, which is why AC3 passed.
- *Trigger evidence:* above. Two lenses split Material vs Deferred; the arbiter resolved to **Material** because the on-disk half needs no trigger at all. A reproduction warning worth carrying: overriding only `CLAUDE_CONFIG_DIR` refutes this finding falsely — the real droid and codex stores still produce transitions, which evict the whole store. `HOME` must be blanked.

**M-5 — `--diagnose` writes the persistent store, and recreates it after `--forget`.**
- *Released user and normal workflow:* `cli.build_application` attaches a `Lane` unconditionally and `diagnostics.diagnose` calls `collect(show_all=True)`. `SKILL.md` tells the user to run `--diagnose` **first** whenever a harness is missing, and it is the natural way to verify a delete.
- *Observable harm:* one `--diagnose` into a clean `CARGENTO_HOME` created a **26,086-byte, 189-record** store spanning **13.41 days**, of which **176 records are outside `window_hours=24`** and would never be recorded by a serving collection. `--forget && --diagnose` **recreates** the deleted store.
- *Affected boundary:* `contract[SECURITY.md#local-history-the-session-history-store]` — the `--forget` irreversibility sentence; plus `cargento/skills/cargento/SKILL.md` "Reads local paths only" and `HOW_TO_USE.md` "It reads local paths, transmits nothing, and starts no server".
- *Trigger evidence:* figures reproduced to the byte by the arbiter (26,086 / 189 / 13.41). The arbiter **upgraded** this from the critic's Needs decision, and was explicit about why: it conceded the doc sentences are genuinely ambiguous between "does not transmit" and "does not write", and rested the upgrade instead on `--forget && --diagnose` restoring a store, which no reading of any sentence permits.

**Needs decision (4)** — the task cannot own the scope these require.
- **ND-1 — `SECURITY.md` says both bounds "are configurable"; neither is.** No flag, no env var, no parameter — `build_runtime_config` accepts only `history_enabled`. **Arbiter-refuted as this PR's defect:** the sentence is verbatim at `5a156bc:docs/plans/history-store-security-scope.md:49`, inside a section the merged plan ordered promoted *unchanged*. Either wire two knobs or amend the merged contract. `contract[SECURITY.md#local-history-the-session-history-store]`.
- **ND-2 — D1's distinguishable reset reason is a tautology.** Setting `RESET_VERSION = "unreadable"` passes 115 tests across three modules; no test pins either literal. **Arbiter-downgraded from Material:** the shipped constants *are* distinguishable, so there is no released user and no observable harm. But D1 is the recommendation the gate specifically ruled on, and whether an assertion that cannot fail discharges that ruling is the gate's call. `captain-ruling[2026-09-03]` D1. One-line fix.
- **ND-3 — the corrected file count landed in `SECURITY.md` only** (five) while `SKILL.md` says four, omitting the observer sidecar. **Arbiter corrected the premise in the PR's favour:** pre-PR both said "three" and *both were already wrong*, each omitting a sidecar that shipped before this PR; the plan doc instructs "four … the count only" for `SKILL.md`, which the implementer followed exactly. Not a regression — an incomplete pre-existing fix. Should D3's correction travel to the second site? `contract[cargento/skills/cargento/SKILL.md]` vs `contract[SECURITY.md#process-lifecycle-written-paths-and-apishutdown]`.
- **ND-4 — the contract's "the header reports the reset" has no scheduled implementer.** `history_reset` is published at `aggregate.py:655` and read by nothing; PR 2's planned surface is `next-workstream.js`/`next-delegation.js`/`next-render.js` with no header work, and no AC binds a reset render. The clause is also verbatim inherited from the plan doc. Either scope it into PR 2 (~5 `web/` lines + a test, and only one PR may touch `web/`) or amend the clause to future tense.

**Deferred risk (7)** — each carries its promote-to-material condition; per AGENTS.md these are **filed, not promoted into this PR**.
- **DR-1 — `evict` re-serialises the whole store per dropped record.** Reproduced: **4.505 s / 593 `json.dumps` calls** on a store compacted by an external tool, and 0.261 s for a 31-session burst, inside `collect_memo_lock` on the HTTP request thread. **Arbiter-downgraded from Material, and this is the clearest correct-measurement-wrong-conclusion case in the set:** the 4.5 s stall is **one-shot** (the first eviction rewrites with default separators, so the loop is short forever after) and needs a third-party tool to have compacted the file; the ordinary paths cost 0.261 s and 26 ms. *Promote if* any shipped code path, hook or documented procedure writes the store with non-default separators, or if the loop is ever reached on a store held above the cap across restarts. The `evict` docstring's premise ("an oversized store never reaches this loop") is **false** — `load` caps raw file bytes while `_payload` re-serialises 8.16% larger — and that half rides in this PR as Polish.
- **DR-2 — the feature's default production path has no test.** `_apply_overlays` reaches `_history_fields` from two exits; every history test leaves `overlays` unset, i.e. the `--no-events` shape, while default flags take the other exit. Mutating the default exit to `return {}` disables the entire feature for every default user — no store, no payload key — and **423 tests stay green**. Code is correct today. *Promote if* anything touches `_apply_overlays`'s return paths. ~8 test lines.
- **DR-3 — the record-before-dismissal-subtraction ordering has no oracle**, and the harm its comment names is real: with the call moved after `_subtract_dismissed`, a dismissed session's transitions are recorded **not at all**, demonstrated pristine-vs-mutated, with 62 tests green. Dismissal is a normal reader action. *Promote if* the two lines are reordered. ~10 test lines.
- **DR-4 — the `(harness, sid)` dedupe key is unfalsified**; no test uses more than one session. Collapsing to `harness` alone keeps `test_history` green and does **two** things, one worse than reported: it suppresses two real transitions *and* **fabricates one that never happened** — in a store whose entire contract is field provenance. *Promote if* the key is narrowed or `latest` restructured. ~12 test lines.
- **DR-5 — AC4's atomicity has no oracle.** Writing in place instead of temp+rename passes all 46 tests, and `test_a_failed_write_leaves_no_temp_file_behind` then passes **vacuously** — its setup makes `state_home` a regular file, so `os.makedirs` raises before `os.open` is reached and **zero** `os.open` calls occur. No test in the repo asserts temp+rename for any store. *Promote if* the write path is simplified. ~8 test lines.
- **DR-6 — `load`'s `except OSError` branch is dead to the suite.** Deleting it keeps 93 tests green; with it gone, a directory at the store path raises `IsADirectoryError` out of `Lane._open` into `Application.collect`, breaking the board instead of opening it empty. *Promote if* the exception boundary is narrowed. ~4 test lines.
- **DR-7 — AC2's fixture never sets `spacedock`.** Arbitrated by me, since it reached neither arbiter — recorded as a gap in my own fan-out rather than left silent. `spacedock` is in AC1's banned **key** tuple but has **no sentinel** in `SENTINELS`, so a widening that routes Spacedock workflow text into the existing `project` field passes AC1 (key set unchanged) and AC2 (no sentinel to find) — Lens 2 demonstrated exactly that with 46 tests green and the text on disk. *Promote if* any change routes spacedock-derived text into a stored field. ~4 fixture lines.
- Also filed, not independently reproduced: the predictable `<target>.<pid>.tmp` path is opened without `O_NOFOLLOW`/`O_EXCL` and `makedirs(exist_ok=True)` does not tighten a pre-existing `~/.cargento`. Arbitrated only through the containment argument — `state_home` is `0o700` at all four creation sites, so another local user cannot traverse in — and it is the identical construction `lifecycle.write_state` and `dismissals.save` already use, so it belongs to a separate issue covering all three writers.

**Polish (10)** — no current user-visible loss; listed for the implementer to take or decline, not to block.
`evict`'s false docstring premise (DR-1's second half) · the kept-list naming gate open/close, turn timings and tool names/counts that the five-field store does not hold — **verbatim inherited** from the plan doc, though "What is kept is…" reads as description rather than the PR body's "ceiling", since the next paragraph uses "may keep" · `config.py`'s "~110 bytes / roughly nine thousand", measured **122 B / 8,594** for the commonest harness and 153 B / 6,853 for Codex · three of five sanitiser ranges unpinned (tables identical today, so drift protection only; the finding's docstring citation was itself wrong) · AC3's age-then-size ordering, provably equivalent for totally-ordered timestamps — **but Arbiter B refuted the "impossible state" conclusion by finding a `NaN` input where the orderings genuinely diverge**, so the comment is right and M-3's `math.isfinite` fix closes this too · `FIELD_CAP_CHARS` pinned to itself (the `history_max_bytes` half **refuted** — the plan doc explicitly declines to fix the cap's value) · owner-only asserted by test name only, harm negligible under `0o700` containment and identical to established practice at `test_events_ingress.py:313` · the payload key asymmetry (`{"history": []}` for a None lane, key absent under `--no-history`) contradicting its own comment · no write-path length cap on `sid`/`project` — mechanism real, **materiality refuted**: `io.read_first_json` bounds every cited collector at 200,000 bytes and a longer first line yields *no* metadata, so the reachable ceiling is ~199,900 chars against the 1,044,998 needed to empty the store · `Lane.__init__`'s "`--diagnose` reads no store" comment, true of construction and misleading as read · amendment 2's sentence landed penultimate rather than "at the end", and one 65-char ragged line in the D5-amended paragraph.

### Summary

**NO-GO**, on five Material findings that fully green CI could not see: the store persists a full
home-relative path on a fallback the never-list bans outright (0.75% of real transcripts), `--forget`
is undone by the running dashboard it is the only delete route for, a tampered store takes the entire
board permanently hard-down while `--diagnose` crashes on the same line, retention is enforced only as
a side effect of a write so a quiet store never expires, and `--diagnose` both creates the store and
recreates it after a delete. None is a redesign — the surviving fix set across every tier is roughly
15 code lines and 70 test lines, and one `math.isfinite` guard plus `OverflowError` in the except
tuple closes M-3 and two Polish items at once.

The change is otherwise in good order and better tested than the ACs required: the contract was
promoted with exactly the three authorized deviations, D3's corrected counts are right at the code,
the sanitiser is behaviourally identical to the one it mirrors across a million code points, the
transition-only write holds on bytes and mtime, and 20 of 32 mutations went red. What the ACs missed
they missed structurally — AC3 tested `evict` rather than the store's lifecycle, AC8 scoped the
command rather than the concurrent process, and no AC covered `--diagnose` at all — which is the
argument for this tier rather than against it.

Findings route to `implementation` over the `feedback-to` edge with their evidence and classifications
unchanged; nothing was fixed, re-triaged, or promoted here, and the four Needs-decision items are the
captain's. No edit to the PR branch, no merge, no worktree or branch removed.

## Stage Report: implementation (correction round 1)

New head `461c605` on `spacedock-ensign/drc-4044`, pushed to PR #260 (not merged). Rejected snapshot
was `5f73639`. **Round surface** `git diff --numstat 5f73639..HEAD`: 9 files, **+931 / −109** —
runtime 4 files +216/−33, oracles 1 file +692/−64, docs 4 files +23/−12. **Cumulative** against merge
base `5a156bc`: 21 files, **+2527 / −187** — runtime 7 files +832/−31, oracles 6 files +1579/−5, docs
8 files +116/−151 (bucketed by path: `cargento_runtime/` runtime, `tests/` oracles, everything else
docs; that rule reproduces the head figures of record to within two lines on each axis). Nothing was
trimmed to hit a number.

**Every fix was falsified before it was believed.** Seventeen mutations applied one at a time in a
throwaway `git archive` copy at `/tmp/drc4044-mut`, never on the branch; each ran only the test class
it targets. **All seventeen go RED.** Two went green on the first attempt and both were my fault, not
the tests' — recorded here rather than quietly fixed: the `--diagnose` assertion was vacuous on a
machine with no stores (no rows, so no write whatever lane is attached — fixed by seeding one
transcript in the isolated home), and my first DR-3 mutation *added* a second `_apply_overlays` call
instead of moving the first (the correct move-mutation is RED).

- DONE: **M-1** — the `project_label` fallback stored a full home-relative path
  `history.observation` now bounds the label through `_bounded_project`, so the store cannot hold more
  than two segments whatever a row carries. The separator is chosen, not guessed: a `/` label came from
  `project_from_cwd` and its own segments may contain `-`. Fixture is end-to-end through the real Claude
  collector — a transcript with no `cwd` under a six-directory encoded name — and the row publishes
  `repos-recce-recce-cloud-infra--claude-worktrees-drc-3976-finish` while the store's bytes hold
  `3976-finish`. Removing the bound reddens `AFallbackProjectLabelIsNotAPathTest`. **The arbiter's
  narrowing stands: this was a retention violation, not an AC1 provenance breach** — the live board
  publishes the identical string, and AC1's key set never changed. Applied at the derivation only, not
  at `_entry`: no store written by a shipped build can hold a pre-fix path, since nothing has shipped.
- DONE: **M-2** — `--forget` while a dashboard runs
  Both halves. `cli.run_one_shot` refuses when `lifecycle.instance_status(config, args.port)` reports
  `running`, exits 1, and names `--stop`; `Lane._forget_a_deleted_baseline` drops the in-memory
  baseline when the store file has gone, which is what covers an instance on a port the probe cannot
  see. Tests: the refusal keeps the file and asserts the probe was called with the port; the lane test
  records two transitions, deletes the store out of band, and asserts one entry back rather than three.
  Removing either half reddens `ForgetIsRefusedWhileADashboardCouldWriteItBackTest`.
- DONE: **M-3** — `Infinity` / `NaN` / overflow in a tampered store
  Three mechanisms, and the first is a deviation worth naming: `_decode` passes `parse_float`,
  `parse_int` and `parse_constant` to `json.loads`, so all three shapes are **corrupt bytes** and earn
  the reset the contract promises. The `math.isfinite` guard the disposition asked for is in `_finite`
  and covers `observation` too (the write path has no parse hook, and `stamp <= 0` is false for NaN);
  `OverflowError` is in `_decode`'s except tuple; `_opened` is latched **before** the read so a raising
  `load` discards once with `RESET_UNREADABLE` instead of raising on every collection. A per-record
  drop alone would have given no reset reason, which is why the hooks exist. Tests: three tampered
  files each yield `((), RESET_UNREADABLE)`; the published body carries neither `Infinity` nor `NaN`
  (the token is the oracle — Python's own decoder accepts both); a mocked raising `load` is called once
  and both collections still serve; `--diagnose` over the overflow store exits 0. Also closes the two
  Polish items the arbiter tied to it (AC3's ordering divergence needed a NaN input).
- DONE: **M-4** — retention enforced only on write
  `appended` now falls through to `evict` whenever anything has expired, not only when something was
  appended, and reports `changed` as `kept != held` so identical bytes are never rewritten. A quiet
  board with nothing expired pays one comparison per record and still touches the file never
  (`AQuietBoardDoesNotGrowTheStoreTest` is unchanged and green). Test: five 100-day entries against a
  genuinely empty board — no rows at all — leaves zero entries on disk and `[]` published. `HOME` and
  every `STORE_ENV_VARS` path are blanked by the fixture per the arbiter's warning.
- DONE: **M-5** — `--diagnose` wrote the store
  `build_application` takes `record_history: bool = True` and the `--diagnose` branch passes `False`,
  so the lane is constructed only when the caller will serve. Shape deviation, stated: moving the
  construction to `main` outright would have made 30-odd test call sites restate a default they do not
  care about. Tests: `--diagnose` over an isolated home holding one discoverable session leaves no
  store, and `--forget && --diagnose` leaves none. Both would pass vacuously without the seeded
  session, which is why it is there.
- DONE: **ND-2** — pin the two reset-reason literals
  `test_the_two_reset_reasons_are_the_literals_the_header_will_read` asserts `"unreadable"`,
  `"version"` and that they differ; setting `RESET_VERSION = "unreadable"` now reddens
  `UnreadableStoreIsDiscardedTest`, which it did not before.
- DONE: **ND-3** — carry D3's corrected count to `SKILL.md`
  Before: "The server writes **four** files … `cargento-dismissals.json`, the sessions marked handled;
  and `cargento-history.json`". After: "The server writes **five** files … `cargento-dismissals.json`,
  the sessions marked handled; `observer/<harness>_<sid>.json`, the sidecar an observer panel records
  when a reader opens one; and `cargento-history.json`". No test pins that sentence, so no oracle
  changed with it.
- SKIPPED: **ND-1** — `SECURITY.md` says both bounds "are configurable"
  HELD for the captain, per the disposition. Untouched: no knob wired, no sentence amended. No ruling
  reached me during the round.
- SKIPPED: **ND-4** — "the header reports the reset" has no implementer
  HELD for the captain, per the disposition. `history_reset` is still published and still read by
  nothing; no `web/` file was touched and no clause was amended.
- DONE: **DR-1** — `evict` re-serialised per dropped record, and its docstring's premise was false
  It now sizes the store from each record's own length (`_store_bytes` over an empty-envelope constant
  plus the two `, ` bytes per join) and drops the oldest with running arithmetic, so the whole store is
  never re-serialised in the loop. The false premise is gone and replaced with the measured reason:
  4.505 s / 593 `json.dumps` calls on an externally compacted store, and `load` caps raw bytes while
  `_payload` re-serialises 8.16% larger. Tests: `_store_bytes` equals `len(_payload(...))` at 0, 1, 2
  and 17 records (setting the separator to 0 reddens it), and a 600-record store over a 2,000-byte cap
  lands inside the cap with the newest kept while putting the next-oldest back exceeds it — which is
  what fails if the arithmetic over-subtracts.
- DONE: **DR-2** — the default production exit of `_apply_overlays` had no test
  `TheDefaultProductionPathRecordsTest` attaches a real (inert) `observation.Observation` the way `cli`
  does and asserts both the published field and the store's bytes. Mutating that exit to `return {}`
  reddens it.
- DONE: **DR-3** — record-before-dismissal-subtraction had no oracle
  A dismissed session (marked through `dismissals.dismiss`) is absent from `payload["sessions"]` and
  its transition is still in `payload["history"]`. Moving `_apply_overlays` after `_subtract_dismissed`
  reddens it with `['working'] != []`.
- DONE: **DR-4** — the `(harness, sid)` dedupe key was unfalsified
  Two sessions, two collections: the store holds exactly `sid-1 working`, `sid-2 idle`, `sid-2 working`.
  Collapsing the key to `harness` alone reddens it — and the assertion is on the tuples, not the count,
  because the collapse both suppresses the real transition and fabricates one.
- DONE: **DR-5** — AC4's atomicity had no oracle, and the failed-write test was vacuous
  `test_the_store_is_written_through_a_temp_file_and_renamed` spies `os.open` and `os.replace`: exactly
  one open, on a `.tmp` path that is not the target, and one rename of that path onto it. Writing in
  place reddens `OwnerOnlyWriteTest`. The failed-write test's setup is fixed too — it made `state_home`
  a regular file so `makedirs` raised before `os.open` was ever reached; it now fails at the rename,
  which is the shape that actually leaves a temp file to clean up.
- DONE: **DR-6** — `load`'s `except OSError` branch was dead
  A directory at the store path yields `((), RESET_UNREADABLE)`, and a lane over one still serves the
  collection and reports the reset. Deleting the branch reddens
  `ADirectoryAtTheStorePathOpensEmptyTest` with `IsADirectoryError`.
- DONE: **DR-7** — AC2's fixture never set `spacedock`
  `SENTINELS` gains `spacedock_workflow` and `loaded_row` carries it in a first-officer `spacedock`
  object. Routing that text into `project` reddens `NothingPromptDerivedReachesTheStoreTest`, which it
  passed before.
- SKIPPED: **FILE, not fix** — the predictable `<target>.<pid>.tmp` without `O_NOFOLLOW`/`O_EXCL`
  The write primitive is unchanged: `save`'s `os.open` flags and temp path are byte-identical to
  `5f73639`, and the FO files the issue spanning `lifecycle.write_state`, `dismissals.save` and
  `history.save`. The new atomicity oracle asserts temp+rename and deliberately asserts nothing about
  the flags, so it will not have to change when that issue lands.
- DONE: **Polish taken** — six, all in files this round already opened
  `evict`'s docstring (with DR-1); `config.py`'s byte figures, re-measured here rather than inherited
  — 1 MiB holds **7,825** observations at the **132** bytes a Claude record takes over this machine's
  real board of 2,713 rows, or **6,853** at **151** bytes for Codex (the review's 8,594/122 did not
  reproduce; its Codex fit of 6,853 did, exactly); the payload-key asymmetry, resolved to one shape —
  the key is present exactly when the store is on and a lane is attached, which is `dismiss`'s keying,
  with the comment rewritten and its test flipped to `assertNotIn`; `Lane.__init__`'s `--diagnose`
  comment deleted, moot after M-5; and both `SECURITY.md` seams — amendment 2's sentence moved to the
  end of Scope invariant 2 where the merged contract put it, and the D5-amended paragraph rewrapped.
- DONE: **Polish declined** — four, one line each
  The kept-list wording: inherited verbatim from approved plan-doc prose, and the arbiter's own reading
  ("What is kept is…" as description) makes it correct as it stands. `FIELD_CAP_CHARS` self-pin:
  refuted. The `sid`/`project` write-path cap: materiality refuted — `io.read_first_json` bounds every
  cited collector at 200,000 bytes against the 1,044,998 chars needed. The owner-only test-name
  assertion: established practice at `test_events_ingress.py:313`, and the mode is now spied at
  `os.open` anyway.
- DONE: Constraints on the round, each checked
  No file under `cargento_runtime/web/` (the round's 9 files are listed above); no version field moved
  (`git diff` over `*plugin.json`, `*marketplace.json`, `*gemini-extension.json` since the merge base
  is empty, and `bump_version.py --current` reports 0.20.0); no Linear write of any kind;
  `history.py` still contains no quoted literal `"git"` (`grep -c '"git"'` → 0).
- DONE: the canonical suite re-run once, at a load average this machine could be trusted at
  `uptime` first: **4.34** at the start and 5.81 at the last run, never near the 20 the lenses left
  behind, so no red had to be re-run alone and none appeared. `ruff check` clean, `ruff format --check`
  149 files, `mypy --strict` clean over 110 files, `lint_embedded` clean, `validate_plugins` OK,
  **1,847 tests OK (1 skipped) in 33.6 s**, script tests 190 OK, `coverage report` exit 0 at **90.4%**
  against a `fail_under` of 73, `claude plugin validate --strict` passed. The suite was run twice in
  total: once before a one-token tidy (`float(stamp)` → `stamp`, already a float) and once after.
- DONE: CI read on the new head, and the head it belongs to checked
  All **twelve** required checks `success` on `461c605` and every check-run queried by that SHA
  belongs to it, not to a superseded head: `quality-gate`, `validate`, `version-guard`, `Detect what
  the gate can measure`, Lint, `Type check (mypy --strict)`, `Runtime floor (Python 3.11)`,
  `Tests + coverage threshold`, `latest-client-smoke`, and platform-tests on ubuntu, macOS and
  Windows. `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`. Pushed, not merged.
- DONE: two existing tests made machine-independent rather than left to pass by luck
  `ForgetIsACommandAndNotARouteTest`'s two `--forget` tests now patch `lifecycle.instance_status` to
  report nothing on the port. Without that they fail on any machine with a dashboard on 4553 — this one
  has, so M-2 would have shipped a suite that passes only where no Cargento is running.

### Summary

All five Material findings, both FO-authorized Needs-decision items, DR-1's mechanism and all six
deferred test gaps are fixed on `461c605`; ND-1 and ND-4 are untouched and still the captain's, and the
tmp-path hardening is left for the FO's issue with the write primitive byte-identical. The round is
+931/−109 over nine files, two thirds of it the oracles: seventeen mutations, seventeen reds, including
the six the review filed as unfalsifiable and the two shapes of tampered numeric that used to take the
whole board down. Three figures were re-measured rather than inherited — the record's byte size, the
1 MiB fit, and the store's own size arithmetic against the bytes `save` writes — and the one that did
not reproduce is reported as it measured here rather than as the review had it.

## Stage Report: implementation (correction round 1, captain rulings ND-1 and ND-4)

New head `b5616b6`, pushed to PR #260 (not merged). **Round surface** re-measured from the rejected
snapshot `5f73639`: 12 files, **+1184 / −113** — runtime 5 files +311/−37, oracles 3 files +832/−64,
docs 4 files +41/−12. The two rulings alone, `461c605..b5616b6`: 8 files, **+253 / −4**. Cumulative
against merge base `5a156bc`: 21 files, **+2777 / −188**.

- DONE: **ND-1** — two knobs wired, so "both are configurable" is true as written
  `--history-days` (default 14) and `--history-max-bytes` (default 1048576) follow `--window-hours`'s
  shape, carry through `build_runtime_config` into the two fields the lane reads, and take their
  defaults from named `config.py` constants because argparse and the constructor otherwise state the
  same figure twice. `SECURITY.md` unchanged, as instructed — the sentence needed no edit once the
  build could do it. `history.py` still holds no quoted literal `"git"` (`grep -c '"git"'` → 0).
- DONE: **ND-1, rejected on nonsense values**
  `positive_float` and `positive_int` are argparse `type=` callables, so zero, negative,
  non-finite and non-numeric are refused at parse time — before a daemon can be respawned with a bound
  its parent would not have taken. Rejection at the type rather than in `main` on purpose: `main` is
  already at ruff's branch cap and carries the exemption for it.
- DONE: **ND-1, forwarded on the daemon respawn path the way `--no-history` is**
  `_history_bound_argv` sends whichever bound was moved and neither when both are the shipped
  defaults; it reads `args.history_days` and `args.history_max_bytes` directly, so an omission raises.
  The FO's prediction held exactly — the seven hand-written namespaces in `test_lifecycle.py` produced
  **16 AttributeErrors** and forced the edit rather than passing quietly. Split into its own function
  only because two more branches put `spawn_argv` at complexity 11 against ruff's 10, and widening
  `lifecycle.py`'s per-file ignores to swallow that would have been the wrong trade.
- DONE: **ND-1 tests** — the flag reaches the bounds, and the bounds are what evicts
  `BothBoundsAreConfigurableTest`: the defaults are the contract's literals (14 days, 1 MiB, written
  as literals rather than read from the subject's constants); both flags reach the config; a
  `--history-days 1` lane really drops a two-day-old observation; a `--history-max-bytes 140` lane
  keeps exactly the newest record (measured: 111 bytes each against a 23-byte envelope, so one store
  is 134 and two are 247); and six nonsense values each exit 2. Four new `test_lifecycle` tests cover
  the respawn both ways. And the prose is bound to the parser the way the off switch already was:
  `test_the_bounds_the_contract_calls_configurable_are_flags` asserts the contract sentence and then
  parses both flags, so ND-1 cannot recur as prose about a build that cannot do it.
- DONE: **ND-1 docs** — both flags documented beside `--no-history`
  `HOW_TO_USE.md` gains a "Move the history's two bounds" section with the command, the refusal, the
  respawn behaviour and the one thing a user has to know (what leaves the file is gone from it).
  `SKILL.md`'s options table gains a row each. `validate_plugins.py` OK, so no link or anchor moved.
- DONE: **ND-1 falsified before believed** — six mutations, six reds
  Dropping the two arguments from `build_runtime` (config never moves), removing the respawn call
  (bounds not forwarded), forwarding unconditionally (`if True`), accepting non-positive floats,
  dropping the int guard, and misspelling the flag so the contract sentence is unbound: each reddens
  the class named above, run one at a time in a throwaway copy at `/tmp/drc4044-mut2`, never on the
  branch.
- DONE: **ND-4** — scoped into PR 2, and no code in this PR
  `AC12 (offline, PR 2) — the header reports a store reset with its distinguishable reason` is
  recorded under `## Acceptance criteria` on this entity, with a *Verified by:* naming the render test
  PR 2 adds over `history_reset` (both literals, and the absent-field case) and a *Falsified by:* — a
  payload carrying `history_reset` and a header identical to one without it, which is exactly what PR
  1 ships. `## Delivery shape` now records AC12 against PR 2's surface at ~5 `web/` lines plus a
  render test, and why it rides there: only one PR may touch `cargento_runtime/web/`. PR #260's body
  gained one line under `## Verification` saying the clause is PR 2's against `history_reset`, per the
  ruling. **No `web/` file and no runtime file was touched for ND-4.**
- DONE: the canonical suite run once, at a load average this machine could be trusted at
  `uptime` first: **3.92**, nowhere near the 20 the lenses left behind, so nothing had to be re-run
  alone and nothing failed. `ruff check` clean, `ruff format --check` 149 files, `mypy --strict` clean
  over 110 files, `lint_embedded` clean, `validate_plugins` OK, `bump_version --current` 0.20.0,
  **1,857 tests OK (1 skipped) in 37.8 s**, script tests 190 OK, `coverage report` exit 0 at
  **90.4%** against `fail_under` 73, `claude plugin validate --strict` passed. No version field moved.
- DONE: pushed so #260's head moved, and the checks read on the head that owns them
  **12/12 required checks `success` on `b5616b6`**, every check-run returned by that SHA;
  `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`. Pushed, not merged.

### Summary

Both rulings are applied on `b5616b6`. ND-1 is two flags with the shipped defaults, validated at parse
time, forwarded on respawn only when moved, and now bound to the contract sentence by a test — the
promoted prose is true rather than amended, which is what the captain asked for. ND-4 took no code:
AC12 is on the entity with a falsifier that names the exact state PR 1 ships, PR 2's surface records
it, and the PR body says so. Six more mutations, six more reds, on top of round 1's seventeen. The
round is now +1184/−113 over twelve files against `5f73639`, two thirds of it oracles.
