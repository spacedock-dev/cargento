---
id: drc-4330
title: 'History groundwork · SECURITY.md scope section for the local history store'
status: review
source: https://linear.app/recce/issue/DRC-4330
started: 2026-09-03T03:29:50Z
completed:
verdict:
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4330
issue:
pr: "#258"
mod-block:
linear-status: 'Todo'
milestone: 'Move up a level'
release: ''
promise: 'P2'
move: 'none'
estimate: ''
reconciled:
gates:
    version: 1
    records:
        - id: gate:drc-4330:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4330-triage-1
              briefing:
                id: briefing:drc-4330:triage:attempt-1:revision-1
                digest: sha256:b8601df7c5586a8f0f8314a5e5140c1ad30fad6f3c6b6024e0b2dc69630c4e7a
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4330:triage:1
                briefing: briefing:drc-4330:triage:attempt-1:revision-1
                by: person:captain
                at: "2026-09-03T03:48:29.370321Z"
                decision: approve
                reason: 'Captain approved the triage drafts at the gate 2026-09-03: "I approve, also fold in the siblings. and also fix the seed paragraph if needed". Accepts the direction — the history-store security contract goes to docs/plans/history-store-security-scope.md, promoted into SECURITY.md by H1, with the Linear body rewrite and the one-hunk milestone correction authorized as drafted; additionally authorizes one dated correction comment on each of DRC-4326, DRC-4327 and DRC-4329, and correcting the entity opening paragraph mis-citation.'
              application:
                target-stage: implementation
                state: consumed
        - id: gate:drc-4330:review
          stage: review
          attempts:
            - id: gate-attempt:drc-4330-review-1
              briefing:
                id: briefing:drc-4330:review:attempt-1:revision-1
                digest: sha256:1697f98403e7495f0e9cc0647b8ef1ee7ca55f34b3591b0740ebac7d4e393ef6
                room-ref: ./review/review/briefing-1
review-round:
    id: round:drc-4330:review:1
    stage: review
    cycle: 1
    briefing:
        id: briefing:drc-4330:review:round-1:revision-1
        digest: sha256:20a7b62ae334e0be52f28223ebf9680002bb2cdfc798176a31a074f6bd7c3dcc
        room-ref: ./review/review/round-1
---

[DRC-4330](https://linear.app/recce/issue/DRC-4330) — Linear priority High, no estimate, labels `journey:mid-flight`, `move:none`. Filed 2026-09-02 as the groundwork for H1 (DRC-4044), the shape the quota, git-probe and ask-lane groundwork issues used: a security contract written under `docs/plans/` before the code it bounds, promoted into `SECURITY.md` by the feature's own PR.

**Pick, 2026-09-03.** Captain-directed. The captain asked to start with A6 (DRC-4009); A6 is `blockedBy` H1 (DRC-4044, `Todo`), which is `blockedBy` this issue, which has no open blocker. Rule 1 drops A6 and H1; this issue is the unblocked root of that chain, so it goes first and A6 stays the destination. Not a rules pick — recorded so a reader can disagree with the step.

The authoritative issue body lives in Linear and is deliberately not copied here. `triage` fetches it live, reviews it adversarially against the current codebase, and drafts the sharpened version for the gate.

## User value

Nobody sees this directly. It is the written boundary that lets H1 (DRC-4044) ship, and through it
the whole Move up a level milestone. P2, `move:none`: the history store's security contract, written
and reviewed on its own cycle before any code exists, exactly as the quota, ask-lane and git-probe
groundwork did.

**Why no user sees this change.** The deliverable is one new file under `docs/plans/`. No flag
changes, no route changes, no page changes, and — deliberately — no user-facing document changes
either. The two flags this contract bounds do not exist yet, so the PR that documents them for users
is H1's, not this one. The only person who reads this file is the person reviewing or building H1.

Labels are already correct on the issue: `journey:mid-flight` and `move:none`. Nothing to set.

## Problem

DEC-6 (DRC-4234) ruled on 2026-09-02 that Cargento may keep a local history of its own observations
across restarts. H1 (DRC-4044) builds it. The ruling is precise — seven bounded elements — and it
lives in a closed Linear issue, which is not where anyone building or reviewing H1 will look for a
security boundary. Without the contract written down in the repository, H1's boundary is whatever
its implementer remembers of a Linear comment.

Three shipped features solved exactly this, and all three solved it the same way. The evidence, by
commit:

| Groundwork issue | File written | Size | Promoted and deleted by |
|---|---|---|---|
| DRC-4061 (quota) | `docs/plans/quota-fetch-security-scope.md` | 84 lines | `a98bc64` (DRC-4064) |
| DRC-4177 (ask lane) | `docs/plans/ask-operator-security-scope.md` | 193 lines | `3e92d12` (DRC-4172) |
| DRC-4274 (git probe) | `docs/plans/git-probe-security-scope.md` | 102 lines | `ac6ac29` (DRC-4037) |

Added in `7134a01` (#71), `5ede7d1` (#143) and `701b7f0` (#238) respectively. None of the three
wrote into `SECURITY.md`. Each wrote a plan file that the feature's own PR promoted into
`SECURITY.md` unchanged and deleted in the same commit. `AGENTS.md` names that lifecycle
explicitly: `docs/plans/*.md` holds "transient plans for unshipped work. Delete a plan once its work
ships."

The problem is still real, it is still H1's blocker, and it is still worth its own cycle. What has
to change is the file it lands in.

## Proposed approach

Write `docs/plans/history-store-security-scope.md` — one new file, nothing else in the tree — stating
the contract DEC-6 allowed and nothing wider, plus the promotion contract H1 executes and the list of
`SECURITY.md` sentences the store makes false.

**The simplest rejected alternative is the issue as filed**: add the section straight into
`SECURITY.md` now, and document `--no-history` and `--forget` in `HOW_TO_USE.md` in the same PR. It
cannot deliver the value, for three reasons, in ascending order of how fast someone gets hurt.

`SECURITY.md` is a published security policy describing shipped software. A reader reasonably takes
"the store lives under Cargento's own directory, owner-only, written through a temp file and a
rename" as a statement of what the installed program does. Landing that before H1 makes the
repository's security policy false for as long as H1 takes — and H1 is a size-L issue with five
dependents.

`HOW_TO_USE.md` is worse, because it is not a policy but an instruction list. Its "Turn a feature
off" table is the set of flags a user may pass today. `--no-history` and `--forget` are not flags the
parser accepts:

```
$ python3 -c "from cargento_runtime import cli; cli.build_parser().parse_args(['--no-history'])"
-c: error: unrecognized arguments: --no-history      # exit 2; --forget the same
```

A row for either is a documented lie a user disproves in one command. `--forget` also does not
belong in that table on its own terms: every other row names a reversible per-run switch, and
`--forget` deletes a file.

And the repository's own way of holding such a section honest is unavailable until H1 exists.
`GitProbeContractDocumentationTest` in `cargento/skills/cargento/tests/test_documentation.py` binds
the git-probe section to the code by asserting both that `SECURITY.md` says "The off switch is
`--no-git`." and that `cli.build_parser().parse_args(["--no-git"])` succeeds. The history-store
analogue cannot be written before the parser accepts the flag, so a section landing in `SECURITY.md`
now is the one contract section in that file with no oracle behind it. Worse, a `SECURITY.md`-only
diff is classified prose by the CI detector (`is_prose` at `.github/workflows/quality-gate.yml:77`),
so the five measurable jobs skip and `test_documentation.py` does not even run on the PR.

The plan-file route loses nothing. The contract is still written before the code, still reviewed on
its own cycle, still the thing H1 is built and reviewed against — that is DRC-4274's stated purpose
for the pattern, in the docstring of the test above. It gains a mechanical promotion step, and it
keeps every user-facing document true on the day it merges.

**One coordination note for the gate.** Three sibling groundwork issues were filed in the same pass
and carry the same instruction: DRC-4326 (hand-off), DRC-4327 (reach) and DRC-4329
(irreversible-actions). If each writes into `SECURITY.md` directly, four in-flight PRs contend on one
file — the shape `AGENTS.md` calls a conflict hotspot. DRC-4327 additionally rewrites the "nothing
leaves the machine" headline, which this contract's own closing clause restates. Plan files do not
contend. Fixing the siblings is out of scope here; naming the hazard is not.

## Adversarial read against the current codebase

Every claim in the live body, checked against the tree at `900b51c`.

**Still true.** The store's permitted fields are all fields the snapshot already serves: `last_tool`
is set in `transcripts.py` (four collectors) and `claude_data.py:353`; `tool_names` and turn
boundaries live in `turns.py:35` and `turns.py:289`; session identity and state are `sessions.py`'s
whole job. So "holds nothing the live snapshot does not already serve" is a checkable claim, not a
slogan.

**Still true.** "Next to the dismissals file" resolves: `SECURITY.md:295` puts
`~/.cargento/cargento-dismissals.json` there, opened `0600` with the mode in the `open` call and
written through a temp file and `os.replace`. The advisory-mode caveat the body invokes exists at
`SECURITY.md:415` and `SECURITY.md:469`.

**Still true, and worth stating as a positive finding.** "The promise map's P2 section gains no new
promise until H1 ships." `docs/promise-map.md:64-78` still describes only what a live session is
doing right now, and its first honesty rule is that a promise enters the file only when a shipped
capability backs it. Adding nothing is correct. (H1's own body labels itself "P2, new", while the
map's move table says `new` means territory no promise covers and creates a new promise rather than
extending P2. That tension is H1's to resolve at its own triage; it does not touch this issue.)

**Describes a state that does not exist: the precedent claim.** The body says this follows "the
quota, git-probe, hand-off, reach and irreversible-actions groundwork". Two of those five are not
groundwork that happened — DRC-4326 and DRC-4327 are unshipped siblings filed the same day, and
DRC-4329 likewise, so they are cited as precedent for themselves. Of the three that did ship, none
wrote into `SECURITY.md`. The entity's own opening paragraph repeats the error ("a SECURITY.md scope
section that lands before the code it bounds") and is corrected by this read rather than rewritten,
since the frontmatter block above it is not mine to edit.

**Describes a state that does not exist: the two flags.** Verified by running the parser, above.

**Incomplete: the sentences the store falsifies.** `SECURITY.md:261` opens Process lifecycle with
"The server writes three files, all under `~/.cargento`", and Scope invariant 2 (`SECURITY.md:35`
onward) enumerates every writer with visible care — seven mutating endpoints, six in memory, one
`GET` that writes, one forwarder that writes. A history store is a new writer of a new kind: written
by the server continuously rather than on a request edge. Neither sentence survives H1 unamended.
The filed body does not mention them. DRC-4274 hit precisely this and made it AC7 — its section
would have been promoted into a Scope clause enumerating only file reads, which does not reach a
subprocess execution.

**Divergent wording, minor, resolved toward H1.** The filed body says a corrupt store "starts empty
and the board says so"; DEC-6 says the same; H1's acceptance criteria say "the header reports the
reset". The contract should use H1's wording, because H1's tests are what will enforce it.

**Not found, and looked for.** No existing `--forget`, `--no-history`, history module, or retention
constant anywhere in `cargento_runtime`. No prior art in `config.py` to conflict with. Nothing in
`docs/plans/` at all — the directory does not currently exist, which is itself the evidence that all
three precedents completed their promote-and-delete step.

## Linear edits made

Nothing has been written to Linear. Both records below are the pre-edit capture; the drafts are for
the gate to authorize and for `implementation` to write as its first action.

Drafts are stored unwrapped — one line per paragraph — per the workflow rule measured on DRC-4037:
Linear reads a hard-wrapped newline as a hard break and re-marks emphasis per line. Send them as
written. No emphasis run in either draft ends immediately before a code span, which is the
structural avoidance the milestone rule proved round-trips byte-identical.

**Read back the relation set after the body write.** The rewrite references DRC-4044 and DRC-4234;
any issue reference becomes a mention and a mention silently adds `relatedTo` edges. Current
relations are `blocks: DRC-4044` and `relatedTo: DRC-4234`. A new `blocks` or `blockedBy` edge would
be Material immediately.

### Pre-edit record — DRC-4330 issue body, verbatim as of 2026-09-03

The `<issue …>` wrappers are Linear's own mention markup and are reproduced as captured.

```markdown
## User value

Nobody sees this directly. It is the written boundary that lets H1 ship, and through it the whole Move up a level milestone. P2, none: a SECURITY.md section landed before any code, as the quota, git-probe, hand-off, reach and irreversible-actions groundwork did.

## What needs to be done

Add a SECURITY.md scope section for the local history store (H1, <issue id="b119a23f-5d65-4dcd-b471-c116835f06ca" href="https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened">DRC-4044</issue>) before its code lands. It states: the store holds nothing the live snapshot does not already serve, so session identity, states, transitions, gate open and close, turn boundaries and timings, tool names and counts, and never prompt text, tool input, a path or file content; it lives under Cargento's own directory next to the dismissals file, owner-only, written through a temp file and a rename, with the Windows advisory-mode caveat the other files carry; retention is 14 days by default with a size cap, both configurable, evicted by age first; `--no-history` turns the store off and `--forget` deletes it; a corrupt store starts empty and the board says so; nothing in it ever leaves the machine.

In the same PR, HOW_TO_USE.md documents the two flags and where the file lives, and the promise map's P2 section gains no new promise until H1 ships.

Verified by: the section exists in SECURITY.md, HOW_TO_USE.md names both flags, and <issue id="b119a23f-5d65-4dcd-b471-c116835f06ca" href="https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened">DRC-4044</issue>'s PR links to this issue (offline).
```

### Pre-edit record — milestone "Move up a level" description, verbatim

Captured from `get_milestone` on 2026-09-03. Only the DRC-4330 line under "What remains" is touched;
the rest is recorded so this section is a restore point rather than a diff. `implementation` must
still re-capture the live description before writing and assert the target passage is present exactly
once, because the whole body is resent on every write.

```markdown
## The user value

**Nothing here is promised yet, and that is the point: this group changes what the user's job is rather than how well they watch.**

## What remains

[DRC-4041](https://linear.app/recce/issue/DRC-4041/f1-these-four-are-one-project-make-it-a-workflow): Cargento notices when several sessions belong to one project and points it out, instead of leaving them as separate tabs to track by hand.
[DRC-4042](https://linear.app/recce/issue/DRC-4042/f2-you-have-done-this-five-times-make-it-a-skill): Cargento turns a decision you keep answering the same way into a skill, instead of asking again.
[DRC-4043](https://linear.app/recce/issue/DRC-4043/f3-where-your-attention-actually-went): Cargento shows you where your attention went over the past week, making the case for delegating more.
[DRC-4044](https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened): The board remembers what happened before a restart, kept on this machine for 14 days, instead of opening with no memory of sessions that already ran.
[DRC-4045](https://linear.app/recce/issue/DRC-4045/f4-cloud-and-local-on-one-board): Your cloud sessions appear on the same board as your local ones, instead of living in a separate tab.
[DRC-4047](https://linear.app/recce/issue/DRC-4047/f5-cowork-and-hosted-sessions): Claude Cowork and other hosted sessions show up on the board next to your local ones, instead of staying invisible.
[DRC-4048](https://linear.app/recce/issue/DRC-4048/f6-promote-a-session-to-a-workflow): Cargento promotes a cluster of related sessions into a Spacedock workflow the first officer runs, instead of you orchestrating them by hand.
[DRC-4049](https://linear.app/recce/issue/DRC-4049/f7-across-machines-or-across-a-team): Every machine's sessions show up in one place, instead of one board per machine.
[DRC-4330](https://linear.app/recce/issue/DRC-4330/history-groundwork-securitymd-scope-section-for-the-local-history): The SECURITY.md section for the local history store, before any code.

## Waits on

[DRC-4330](https://linear.app/recce/issue/DRC-4330/history-groundwork-securitymd-scope-section-for-the-local-history) (history groundwork) gates [DRC-4044](https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened).
[DRC-4044](https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened) (H1) gates [DRC-4042](https://linear.app/recce/issue/DRC-4042/f2-you-have-done-this-five-times-make-it-a-skill) and [DRC-4043](https://linear.app/recce/issue/DRC-4043/f3-where-your-attention-actually-went), and A6 and D10 and G4 in their own milestones.
[DRC-4041](https://linear.app/recce/issue/DRC-4041/f1-these-four-are-one-project-make-it-a-workflow) (F1) gates [DRC-4048](https://linear.app/recce/issue/DRC-4048/f6-promote-a-session-to-a-workflow); the Spacedock write-API decision is filed when F1 ships.
```

**The target passage, and the near-miss it must not match.** The line to replace, and the "Waits on"
line that shares a long prefix with it and stays as it is:

```markdown
[DRC-4330](https://linear.app/recce/issue/DRC-4330/history-groundwork-securitymd-scope-section-for-the-local-history): The SECURITY.md section for the local history store, before any code.
```

```markdown
[DRC-4330](https://linear.app/recce/issue/DRC-4330/history-groundwork-securitymd-scope-section-for-the-local-history) (history groundwork) gates [DRC-4044](https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened).
```

The second is correct as it stands and is captured only so the exactly-once assertion on the first
does not match it by accident.

### Drafted rewrite — DRC-4330 issue body

```markdown
## User value

Nobody sees this directly. It is the written boundary that lets H1 ship, and through it the whole Move up a level milestone. P2, none: the history store's security contract, written and reviewed on its own cycle before any code exists, exactly as the quota, ask-lane and git-probe groundwork did.

## What needs to be done

Write `docs/plans/history-store-security-scope.md`, the security contract for the local history store (H1, DRC-4044), before its code lands. H1's PR promotes it into SECURITY.md unchanged and deletes the file in the same commit. That is the shape all three shipped groundwork issues used: added in 7134a01, 5ede7d1 and 701b7f0, promoted and deleted in a98bc64, 3e92d12 and ac6ac29.

The contract states what DEC-6 (DRC-4234) allowed on 2026-09-02 and nothing wider. The store holds nothing the live snapshot does not already serve: session identity, states, transitions, gate open and close, turn boundaries and timings, tool names and counts, and never prompt text, tool input, a path or file content. It lives under Cargento's own directory next to the dismissals file, owner-only, written through a temp file and a rename, carrying the same advisory-mode caveat on Windows that the state file and the dismissal store already carry. Retention is 14 days by default with a size cap, both configurable, evicted by age first. The store is on by default, for the reason DEC-6 recorded. `--no-history` turns it off and must reach the daemon respawn path, so a restart cannot re-enable a store the user disabled; `--forget` deletes it and is a one-shot command rather than a feature toggle. A corrupt or unreadable store is discarded, the board starts empty, and the header reports the reset. Nothing in the store ever leaves the machine.

The document also names every sentence in SECURITY.md that the store makes false, so H1's promotion is mechanical rather than a rediscovery. Two are known: the Process lifecycle opener, "The server writes three files, all under `~/.cargento`", and Scope invariant 2's enumeration of what writes and where.

Nothing lands in SECURITY.md, HOW_TO_USE.md or the promise map in this PR. `--no-history` and `--forget` are not flags the parser accepts today, so a row for either in the user-facing off-switch table would be a documented lie a user disproves in one command; both entries ship with H1, in the PR that makes them true. The promise map gains nothing either: P2 describes what a live session is doing right now, and a promise enters that file only when a shipped capability backs it.

Verified by: `docs/plans/history-store-security-scope.md` exists, `python3 scripts/validate_plugins.py` exits 0 with it in the tree, the document states the promotion contract, and DRC-4044's PR links to this issue (offline).

## History

**2026-09-02, superseded 2026-09-03.** As filed, this issue said to add the section directly to SECURITY.md and to document `--no-history` and `--forget` in HOW_TO_USE.md in the same PR, "as the quota, git-probe, hand-off, reach and irreversible-actions groundwork did". Triage checked that citation against the commits. Two of the five named are unshipped siblings filed the same day and cite themselves; of the three that shipped, none wrote into SECURITY.md — each wrote a docs/plans file the feature's own PR promoted and deleted. Landing the section early would have made the repository's published security policy describe a store that does not exist, and the HOW_TO_USE rows would have named two flags the parser rejects. The content of the contract is unchanged from what was filed; only its destination and the timing of the user-facing rows moved.
```

### Drafted correction — milestone "Move up a level"

One replacement, one hunk, nothing else moves.

```markdown
[DRC-4330](https://linear.app/recce/issue/DRC-4330/history-groundwork-securitymd-scope-section-for-the-local-history): The history store's security contract, written and reviewed before any code, and promoted into SECURITY.md by H1's own PR.
```

The "Waits on" line is already accurate and is not touched. If the scripted diff shows more than one
hunk, stop and report rather than sending: the whole description is resent on every write, so a
second hunk is an unreviewed change to a record other people read.

## Expected surface and tolerance

**One new file, `docs/plans/history-store-security-scope.md`, and nothing else in the tree.**

- Estimate **130 lines ± 30**. The three precedents bracket it: 84 lines for the quota fetcher's four
  elements, 102 for the git probe's six, 193 for the ask lane, which carried protocol design this
  does not. DEC-6 has seven elements plus a promotion contract plus the amendment list, so it sits
  above the git probe and well below the ask lane.
- **Oracles: zero new test files, and this is a declaration rather than an omission.** The
  repository's way of pinning a contract section is the `GitProbeContractDocumentationTest` shape,
  which asserts the prose and then parses the flag it names. `--no-history` does not parse today, so
  that test cannot be written here without being a prose-grep over our own file — which
  `docs/roadmap-burndown/README.md` bans outright. The document states that H1 owes the test, and
  that is the honest place for it.
- **No existing required check compels a test file.** Checked, not assumed: `validate_plugins.py`
  reaches the file through `(ROOT / "docs").rglob("*.md")` and needs only resolvable links; the CI
  detector's derived deny list is built by grepping `"docs/…"` string literals out of the test
  files, and no test names this path, so it stays prose; there is no import-graph allowlist or
  protocol fake in play for a Markdown file.
- **No `AGENTS.md` row.** Its docs table already lists `docs/plans/*.md` as a glob.
- **No code, no manifest, no version field.** `version-guard` fails any PR that moves one.

**Semantics this change may move: none in code.** It moves one documentation semantic, and that is
the whole risk of this entity: a defect here propagates verbatim into `SECURITY.md` when H1 promotes
it. This is why the acceptance criteria below point outward, at the runtime and at the precedent
commits, rather than at this document's own prose.

**Tolerance breach is a check-set change, not just a bigger diff.** Any second path in the diff flips
the CI detector to `code=true` and the whole canonical suite becomes owed. If the diff grows beyond
the one file, re-run the detector reasoning before choosing what to run locally.

## Acceptance criteria

**AC-1 — The merged diff is exactly one new file under `docs/plans/`, and CI's own detector agrees
the PR is prose-only.** (offline)
Verified by: the `changes` job emitting `code=false`, with the five measurable jobs reported
`skipped` and `validate` plus `version-guard` green on the PR's current head.
Falsified by: any second path in the diff — `is_prose` at `.github/workflows/quality-gate.yml:74`
sends `docs/*.md` through the derived deny list and everything else to `emit true` — or a job
reported `skipped` because an upstream dependency died rather than being filtered, which the
aggregator rejects.

**AC-2 — The document is link- and anchor-clean under the repository's own validator.** (offline)
Verified by: `python3 scripts/validate_plugins.py` exiting 0 with the file in the tree;
`validate_repo_docs` reaches it via `(ROOT / "docs").rglob("*.md")` at
`scripts/validate_plugins.py:1233`.
Falsified by: any relative link target or `#heading` anchor in the document that does not resolve, or
the `localhost` spelling of the dashboard URL — each is an error and a non-zero exit from that
function.

**AC-3 — Every field the contract permits is a field the runtime already publishes, and the
never-list is exactly DEC-6's.** (offline)
Verified by: each permitted field naming a live producer — `last_tool` at `claude_data.py:353` and in
four `transcripts.py` collectors, `tool_names` at `turns.py:35`, turn boundaries at `turns.py:289`,
session identity and state throughout `sessions.py` — and the never-list matching DEC-6's four items:
prompt text, tool input, a path, file content.
Falsified by: a permitted field with no producer in the current snapshot, or a never-list item DEC-6
did not name. Either widens the contract past what the decision allowed, which is the one thing this
document may not do.

**AC-4 — The document names every sentence in `SECURITY.md` that the store makes false, so H1's
promotion is mechanical.** (offline)
Verified by: it naming the Process lifecycle opener at `SECURITY.md:261` ("The server writes three
files, all under `~/.cargento`") and Scope invariant 2's enumeration of writers beginning at
`SECURITY.md:35`; both are checkable by reading those lines against the document's list.
Falsified by: promoting into a Process lifecycle section that still counts three files, which leaves
`SECURITY.md` contradicting itself the day H1 lands. This is DRC-4274's AC7 failure mode, where the
Scope violation clause enumerated only file reads and did not reach a subprocess execution.

**AC-5 — The off switch is specified as reaching the daemon respawn path, and `--forget` is
specified as a one-shot command rather than a feature toggle.** (offline)
Verified by: the three sites the existing switches occupy — `cli.py:130` (the parser),
`cli.py:213` (the runtime flag) and `lifecycle.py:558-559`, the respawn forwarding branch that
re-appends `--no-git` to a detached restart's argv — and by `--forget` being placed beside `--stop`
and `--status` rather than in the off-switch table.
Falsified by: describing `--no-history` as a CLI flag only, which would let H1 ship a daemon that
re-enables the store on restart after the user disabled it; or filing `--forget` as a feature
toggle, which would put a destructive one-shot in a table where every other row is a reversible
per-run switch.

**AC-6 — Nothing in this PR states a flag, a path or a promise that does not exist yet.** (offline)
This is the criterion closest to a property a user could see, stated as the negative it is.
Verified by: the merged diff touching neither `HOW_TO_USE.md`, `SECURITY.md` nor
`docs/promise-map.md`; and by
`python3 -c "from cargento_runtime import cli; cli.build_parser().parse_args(['--no-history'])"`
exiting 2 today, which is why. Same for `--forget`; both were run on 2026-09-03 at `900b51c`.
Falsified by: a `HOW_TO_USE.md` row for either flag, which a user disproves in one command; or a
promise-map edit, which that file's own first honesty rule forbids — a promise enters it only when a
shipped capability backs it.

**AC-7 — The document reads as a contract rather than as rationale, at the length the three
precedents set, and a stranger could build H1's boundary from it alone.** (interactive)
Verified by: a human read against `docs/plans/git-probe-security-scope.md` as it stood at `701b7f0`
(102 lines) and `quota-fetch-security-scope.md` at `7134a01` (84 lines), confirming all seven of
DEC-6's elements are present and bounded.
Falsified by: a document that argues for the history store rather than bounding it, or that omits any
of the seven elements. **No harness is planned to automate this.** It is a judgement about prose,
declared interactive here rather than dressed up as a check.

**Deliberately not an acceptance criterion.** Any grep asserting the document contains a phrase we
put in it. `docs/roadmap-burndown/README.md` bans prose-greps over files this workflow authored: the
expected value comes from inside the file under test, so a valid paraphrase fails it and an inverted
clause passes it.

## Test plan

No new tests. The full canonical suite is not owed — the diff is prose by the CI detector's own rule
— but two things get run locally before the PR opens, because CI will skip the jobs that would catch
them:

- `python3 scripts/validate_plugins.py` — the check AC-2 rests on, and the one check a prose change
  most needs, since it resolves every relative link and heading anchor across the repository docs.
- `python3 -m unittest cargento.skills.cargento.tests.test_documentation` — not owed by CI on a
  prose-only diff, and run anyway. It reads `SECURITY.md` by literal path, so it is the cheapest
  proof that this PR left that file alone.

Then the `sync-docs` skill, per the pre-PR block in `AGENTS.md`, which also holds the prose to the
voice standard nothing in CI checks.

## Review depth

_Chosen at review from AGENTS.md's Calibrating Effort table._

Triage's recommendation, for the reviewer to accept or overrule: **two lenses plus an arbiter**, the
table's default. It is tempting to call this "no user-visible behaviour change and nothing calls it
yet" and self-verify — but something does call it. H1 promotes this text verbatim into the published
security policy, so a defect here is a security-document defect on a delay fuse. The diff is small;
the leverage is not.

**Chosen at review, 2026-09-03: accepted as recommended — two lenses plus an arbiter, stated before
the review started.** The diff property that decided it is not the size (one file, 127 lines, no
code) but the destination: the document's own lines 7-8 instruct H1 to promote the section
"unchanged", so every sentence inside the `---` fences at lines 16 and 79 is a draft of published
security policy, and the entity's own tolerance section already named that as the whole risk here.
The Calibrating Effort row "no user-visible behaviour change and nothing calls it yet" was overruled
on the second half: H1 calls it. The row actually used is "anything else — two lenses plus an
arbiter".

Two lenses, dispatched in parallel and told to refute by default, each given one question:
DEC-6 fidelity and scope width against the ruling's verbatim text (lens A), and every
outward-pointing citation against the tree at `900b51c` plus an exhaustive hunt for a further
`SECURITY.md` sentence the store falsifies (lens B). They returned 6 and 9 findings, 15 in all. I
arbitrated by reproducing every one myself rather than ranking them: 5 survived as proposed
Material, 3 as Deferred risk, 3 as Polish, and 4 were refuted — including lens A's two strongest,
which were correct readings attached to the wrong conclusion.

**Re-review depth, 2026-09-03 (cycle 2): self-verify by reproduction**, chosen from the property of
the correction round rather than of the whole change and stated before the re-review started. The
document was read at two lenses plus an arbiter at `c46f045` and every citation in it reproduced;
that work stands and was not repeated. What is new is five hunks of clause-level prose inside spans
round 1 had already read, so the question is narrower than the one the lenses answered: did each
authorized fix land, did anything else move, and do the two points AC-7 failed on now settle. Every
claim the new clauses make was reproduced against the tree rather than taken from the implementation
report, and AC-2 was driven from its `Falsified by:` clause in a throwaway copy of the head. What
would have made me climb back to two lenses: a hunk reaching outside the six authorized spans, an
outward citation I could not reproduce, a second path in the diff, or a fix that restructured the
fenced section rather than editing clauses inside it. None of the four held.

### Feedback Cycles

- Cycle 1: NO-GO — review gate, two lenses plus an arbiter, 5 Material + 1 Polish fixed in one file, 3 Deferred risk filed not promoted; surface 1 file/139 LOC vs estimate 130 ± 30 (107%); AC unchanged

## Out of scope

- **Writing anything into `SECURITY.md`, `HOW_TO_USE.md` or `docs/promise-map.md`.** All three are
  H1's, in the PR that makes their contents true.
- **Building the history store.** That is H1 (DRC-4044), size L, with five dependents.
- **The `GitProbeContractDocumentationTest` analogue for the history store.** It cannot exist before
  the parser accepts `--no-history`. The document says H1 owes it; this PR does not write it.
- **Correcting the three sibling groundwork issues** (DRC-4326, DRC-4327, DRC-4329), which carry the
  same mis-citation of the precedent and the same instruction to write straight into `SECURITY.md`.
  One issue per branch. The hazard is named under Proposed approach so the captain can decide
  whether to file it; triage did not file it unasked.
- **The "P2, new" tension in H1's own User value section**, where a `move:new` issue names an
  existing promise. That is H1's to resolve at its own triage.
- **Choosing the store's on-disk format, its size-cap value, or its retention constant.** DEC-6 fixed
  the defaults and said both are configurable; where the numbers live in `config.py` is an
  implementation choice H1 makes.

## Stage Report: triage

- DONE: Pre-edit record first: the live DRC-4330 body and the owning `Move up a level` milestone
  description copied verbatim under `## Linear edits made` before any drafting; the rewritten issue
  body and any milestone correction drafted in this entity only, with nothing written to Linear —
  the gate authorizes that write.
  Both captures proven byte-identical to the `get_issue` and `get_milestone` payloads by a
  `difflib` comparison, not by re-reading: the check caught and corrected one word-run I had
  dropped from the milestone ("and A6 and D10 and G4"), which had already produced a fabricated
  note about a milestone defect that does not exist. Zero Linear writes this stage; drafts are
  stored unwrapped, per the DRC-4037 hard-break rule.
- DONE: Adversarial read against the tree as it stands today: check each claim in the body against
  SECURITY.md's existing groundwork sections, DEC-6's (DRC-4234) recorded ruling, HOW_TO_USE.md, and
  the promise map's P2 section; name every part of the body that describes a state that no longer
  exists, and say whether the problem is still real and the approach still the one that fits.
  Three claims still true (permitted fields have live producers; the dismissals-file location and
  the advisory-mode caveat resolve; P2 correctly gains nothing). Two describe a state that does not
  exist: the precedent citation, refuted by the six commits in the Problem table — none of the three
  shipped groundwork issues wrote into `SECURITY.md` — and the two flags, refuted by running the
  parser (`--no-history` and `--forget` both exit 2 at `900b51c`). One omission: the two
  `SECURITY.md` sentences the store falsifies. Problem still real; approach changed, file only.
- DONE: Acceptance criteria as end-state properties, each marked offline or interactive with a
  `Verified by:` clause and a `Falsified by:` change; since the move is `none`, one sentence on why
  no user sees this; plus an expected surface with tolerance that costs the oracles separately and
  names which existing required check (`scripts/validate_plugins.py` link/anchor resolution,
  `tests/test_documentation.py`, the sync-docs voice pass) a docs-only PR will have to satisfy.
  Seven ACs, six offline and one interactive, each pointing outward at a commit, a line of runtime,
  or a CI job rather than at this entity's prose. The `move:none` sentence is the second paragraph
  of User value. Surface is 130 lines ± 30 across one file, bracketed by the three precedents at 84,
  102 and 193; oracles costed separately at zero new test files, with the reason stated — the
  `GitProbeContractDocumentationTest` analogue cannot exist until the parser accepts the flag, and
  writing it anyway would be the prose-grep the workflow README bans. All three named checks are
  addressed: the validator in AC-2, `test_documentation.py` in the Test plan as a locally-run check
  CI will skip on a prose diff, and the sync-docs voice pass as the last pre-PR step.

### Summary

The issue's content survives triage intact; its destination does not. Filed as "add a SECURITY.md
scope section", it cites five precedents — two of which are unshipped siblings citing themselves, and
three of which did the opposite of what is claimed: each wrote a `docs/plans/*-security-scope.md`
file that the feature's own PR promoted and deleted. Landing it early would put a false statement
about shipped software in the published security policy and two non-existent flags in the
user-facing off-switch table. The rewrite keeps every word of DEC-6's contract, moves it to
`docs/plans/history-store-security-scope.md`, and hands the user-facing rows to H1's PR, where they
become true.

Two things for the gate beyond the drafts. Three sibling groundwork issues (DRC-4326, DRC-4327,
DRC-4329) carry the same mis-citation and the same instruction; fixing them is out of scope on a
one-issue-per-branch rule, so the hazard is named rather than acted on. And the milestone correction
is one hunk against a capture proven byte-exact, so `implementation` can script it with an
exactly-once assertion instead of hand-reconstructing the description.

## Stage Report: implementation

- DONE: First action, before any file in the tree changes: the authorized Linear writes performed
  and read back — the drafted DRC-4330 body rewrite sent verbatim and unwrapped, the one-hunk
  `Move up a level` milestone correction built by script from a fresh capture with an exactly-once
  assertion and a diff showing exactly one hunk, one dated correction comment on each of DRC-4326,
  DRC-4327 and DRC-4329 (captain-authorized 2026-09-03) stating what the three shipped precedents
  actually did, the relation set read back after the body write, and every emphasis-boundary move
  reported rather than repaired; then the entity's own opening paragraph corrected so it no longer
  calls the deliverable "a SECURITY.md scope section".
  All five writes landed before the tree changed. Body: `get_issue` read-back diffed against the
  stored draft by script, byte-identical once the three `<issue …>` mention wrappers are normalized
  away; the single bold run round-tripped intact. Milestone: fresh `get_milestone` capture proved
  byte-identical to the entity restore point, target passage asserted to occur exactly once (the
  "Waits on" near-miss did not match), scripted diff showed one hunk, and the read-back matched the
  intended text once Linear's own change was normalized. That change is reported not repaired: the
  serializer wrapped all 16 link hrefs in angle brackets, in pre-existing text this edit was not
  touching, and no emphasis run moved. Comments: three posted, one per sibling, tailored so each
  states only what its own body actually cites. Seed paragraph corrected in the same pass.
- DONE: `docs/plans/history-store-security-scope.md` written as the only file in the diff on the
  worktree branch, DCO signed off; `python3 scripts/validate_plugins.py` exit 0 and
  `python3 -m unittest cargento.skills.cargento.tests.test_documentation` run locally and their
  results reported; the surface measured with `git diff --numstat "$(git merge-base main HEAD)"..HEAD`
  against 130 ± 30 lines in one file before the PR opens, with the percentage; the diff reviewed in
  the worktree; `sync-docs` invoked and any doc commit landed on this branch.
  Commit `c46f045`, one file, `127 0 docs/plans/history-store-security-scope.md`, 2.3% under the
  130-line estimate and inside the ±30 band. Validator exit 0; it reaches the file through
  `(ROOT / "docs").rglob("*.md")`, so a link or anchor that did not resolve, or the banned
  `localhost` spelling, would fail it. `test_documentation` 14 tests OK; `GitProbeContractDocumentationTest`
  reads `SECURITY.md` by literal path, so editing its git-probe clauses is the change that turns it
  red, which is what makes it proof this PR left that file alone. The self-review before the PR
  found a third falsified sentence triage had not (Dismissals' "the only thing Cargento writes on
  your behalf"), now amendment 3. `sync-docs` ran as a pre-PR-gate pass: checks a, b, c, d clean,
  and check e caught one em dash in the new file, fixed and amended into the same commit. No
  separate doc commit was owed; the marker in `COMPATIBILITY.md` was deliberately left alone, per
  the branch rule.
- DONE: A PR opened whose body starts `Implements [DRC-4330](https://linear.app/recce/issue/DRC-4330) — History groundwork · SECURITY.md scope section for the local history store`
  and carries a `## Verification` section, its number and head SHA reported; and a
  `## Stage Report: implementation` on this entity giving AC-1 through AC-7 each an evidence
  citation or naming it as owed to review (AC-7 is interactive: say what the reviewer reads and
  against which precedent commit).
  PR #258, head `c46f0455fad90910898239a87274d92bd04a50a1`, base `main` at `900b51c`,
  `mergeStateStatus: BLOCKED` because review is outstanding, which is the intended state. Body's
  first line verified against the required string by `gh pr view --jq`; it carries `## Verification`.
  Per-AC evidence below.

### Acceptance criteria, with evidence

- AC-1 (one new file, detector agrees prose-only): `git diff --name-only` over the merge-base range
  returns exactly `docs/plans/history-store-security-scope.md`. `is_prose` derives its deny list by
  grepping `"docs/…"` literals from the test files; no test names this path (checked), so the
  `changes` job emits `code=false`. The job-level half is owed to CI on the PR head.
- AC-2 (link- and anchor-clean): `python3 scripts/validate_plugins.py` exit 0 with the file in the
  tree. The document contains no relative links at all, by design, so it can be promoted without
  rewriting.
- AC-3 (permitted fields all have live producers; never-list is DEC-6's): session identity and state
  at `sessions.py:207`, `:264` and `:288`; gate open and close at `events.py:660`, `:676`, `:693`
  (`blocked_since` set and cleared); turn boundaries and timings at `turns.py:90-112`
  (`turn_start`, `durations`); tool names at `turns.py:35`, `claude_data.py:353` and four
  `transcripts.py` collectors (`:611`, `:703`, `:866`, `:954`). Never-list is DEC-6's four verbatim.
  Discrepancy: AC-3 cites `turns.py:289` for turn boundaries; that line is the `tool_names` entry in
  the turn-scan state dict, and the boundary producer is `turn_start` at `:90-112`. Cited the
  sharper site rather than the AC's.
- AC-4 (names every sentence the store falsifies): three, not two. `SECURITY.md:261` Process
  lifecycle opener plus the "One forwarder writes a fourth" sentence that counts from it,
  `SECURITY.md:35` Scope invariant 2's writer enumeration, and `SECURITY.md:294` Dismissals'
  "the only thing Cargento writes on your behalf".
- AC-5 (off switch reaches respawn; `--forget` is one-shot): the contract names the three sites the
  existing switch occupies, verified at `cli.py:130` (parser), `cli.py:213` (runtime flag) and
  `lifecycle.py:558-559` (the branch that re-appends `--no-git` to a detached restart's argv), and
  places `--forget` with `--stop` and `--status` rather than in the off-switch table.
- AC-6 (nothing states a flag, path or promise that does not exist): the diff touches neither
  `HOW_TO_USE.md`, `SECURITY.md` nor `docs/promise-map.md`. Re-run on this tree at `900b51c`:
  `parse_args(['--no-history'])` and `parse_args(['--forget'])` both exit 2.
- AC-7 (reads as a contract, at the precedents' length): owed to review, interactive by
  declaration. The reviewer reads `docs/plans/history-store-security-scope.md` against
  `git show 701b7f0:docs/plans/git-probe-security-scope.md` (102 lines) and
  `git show 7134a01:docs/plans/quota-fetch-security-scope.md` (84 lines), checking all of DEC-6's
  elements are present and bounded and that the document bounds the store rather than arguing for it.

### Discrepancies and findings for the FO

- Comment mentions create relations, which the workflow README documents only for body text. All
  three correction comments added `relatedTo` edges, all reciprocal: DRC-4326 gained DRC-4061,
  DRC-4177, DRC-4274, DRC-4330; DRC-4327 gained those four plus DRC-4326 and DRC-4329; DRC-4329
  gained those four plus DRC-4326 and DRC-4327; and DRC-4330 itself gained DRC-4326, DRC-4327 and
  DRC-4329. No `blocks` or `blockedBy` edge appeared anywhere, so nothing is Material. Reported, not
  repaired. Baselines are in the read-backs above; DRC-4330's relation set immediately after the
  body write was unchanged at `blocks: DRC-4044`, `relatedTo: DRC-4234`.
- Triage's adversarial read says "Nothing in `docs/plans/` at all — the directory does not currently
  exist". False at `900b51c`: `git ls-files docs/plans` returns
  `event-driven-session-observation.md` and `native-notifications.md`, both tracked. The
  promote-and-delete evidence stands on the six commits and does not need the directory to be empty.
- DRC-4326's body cites only the quota and git-probe groundwork, both of which shipped, so the
  self-citation half of the mis-citation applies to DRC-4327 and DRC-4329 only. Its comment says the
  accurate thing rather than the uniform thing.
- Linear workflow status left at `Todo`. Changing it was not among the four writes the gate
  authorized, and the workflow's post-merge reconcile owns the transition.

### Summary

The three authorized Linear writes and the entity's seed paragraph went first, each read back and
diffed by script rather than by eye; the only drift was Linear's own serializer wrapping 16 link
hrefs in the milestone, reported and left alone. The deliverable is one 127-line file,
`docs/plans/history-store-security-scope.md`, stating DEC-6's contract and nothing wider, with the
promotion contract H1 executes and the `SECURITY.md` sentences the store falsifies. Reviewing it
before opening the PR found a third such sentence triage had missed, in Dismissals, which is the
AC-4 failure mode caught rather than shipped. PR #258 is open at `c46f045` and waits for review.

## Stage Report: review

- DONE: Review depth chosen from the property of the diff and stated up front: one 127-line file
  under `docs/plans/` that H1's PR will promote verbatim into the published security policy; triage
  recommended two lenses plus an arbiter, and the report says whether that is accepted or overruled
  and why; then AC-1 through AC-7 each reproduced from its own `Verified by:` clause against PR
  #258's head rather than trusted from the implementation report — AC-7 is interactive, so read the
  document against `git show 701b7f0:docs/plans/git-probe-security-scope.md` and
  `git show 7134a01:docs/plans/quota-fetch-security-scope.md` and say whether all seven DEC-6
  (DRC-4234) elements are present and bounded, and whether anything in it is wider than DEC-6
  allowed.
  Depth accepted as recommended and recorded under `## Review depth` above, before the review
  started. Seven ACs reproduced below, each from its own clause and several from their `Falsified
  by:` clause as well. DEC-6 read verbatim from DRC-4234 rather than through the entity: all seven
  elements are present, and nothing in the document is wider than the ruling in the hard sense — no
  permission, default, retention window, network posture or capability exceeds it, and the
  on-by-default rationale and the four-item never-list are DEC-6's own words. Where it drifts it
  drifts into DEC-6's silences, and one such drift is a false statement about the shipped board.
- DONE: CI read on the current head `c46f045`: the `changes` job's `code` output, `validate` and
  `version-guard` results, and whether the measurable jobs were skipped by the filter or by an
  upstream failure; `mergeStateStatus` and the head the checks belong to; Copilot inline review
  comments read in addition to top-level reviews; and the DRC-4330 body as it stands in Linear
  compared against the approved draft under `## Linear edits made` on this entity, since approved
  prose is immutable and the read-back is the check.
  All three runs belong to `c46f0455fad90910898239a87274d92bd04a50a1` and none predates it;
  `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE` (implementation reported `BLOCKED`, which was
  the pre-check state). Detail below.
- DONE: A GO or NO-GO verdict with the findings that produced it under their disposition labels,
  written as `## Stage Report: review` with every evidence line on its own line — with no edit to
  the PR branch, no merge, and no worktree or branch removed: the captain's gate authorizes the
  merge and the FO runs the ceremony.
  Verdict **NO-GO**, on M1 and M2. `git status --porcelain` in the worktree is empty and HEAD is
  still `c46f045`; nothing was merged, no worktree or branch removed. Adversarial work ran in three
  `git archive` copies under `/tmp/drc4330rev/`, never in the candidate tree.

### CI and PR state, on the current head

- Head `c46f045`, base `main` at `900b51c`, one file, `127 0 docs/plans/history-store-security-scope.md`.
- `changes` ("Detect what the gate can measure") **success**, and its log emits `code=false` with
  "Every changed path is prose the gate cannot measure."
- The five measurable jobs are `skipped` **by the filter, not by an upstream failure**: the detector
  itself succeeded, and the aggregator's own log shows it accepting `skipped` only under
  `CODE: false` (`R_LINT`/`R_TYPECHECK`/`R_FLOOR`/`R_TEST`/`R_PLATFORM: skipped`, `R_CHANGES: success`).
- `validate` **pass** (36s), `version-guard` **pass** (5s), `quality-gate` **pass**.
- **Copilot: no inline comments, and no review of any kind.** `pulls/258/comments` is length 0,
  `pulls/258/reviews` is empty, `reviewRequests` is empty. This is the repository's normal state
  rather than an omission on this PR — PRs #257, #256 and #253 each carry zero reviews and zero
  inline comments. Nothing was merged past an unread inline finding; there is no Copilot pass to
  read unless the FO requests one.
- **Linear read-back: byte-identical to the approved draft.** The live DRC-4330 description diffed
  against the `## Linear edits made` draft by `difflib` after normalizing away the three `<issue …>`
  mention wrappers: identical, 3661 characters both sides. Relations are `blocks: DRC-4044`,
  `blockedBy: []` — no blocking edge appeared, so the hazard triage flagged did not fire. The
  milestone's `What remains` line carries the drafted correction and the `Waits on` near-miss line
  is untouched.
- Two live-state notes the implementation report predates, neither a finding: the Linear workflow
  status is now `Ready for Review`, not `Todo` — `stateHistory` puts the transition at
  2026-09-03T04:00:20Z, the moment PR #258 was attached, so it is the GitHub integration rather than
  an unauthorized write; and `docs/plans/` holds two other tracked files, as the report itself
  corrected.

### Acceptance criteria, reproduced

- **AC-1 — one new file, detector agrees prose-only. PASS.** `git diff --name-only` over the
  merge-base range returns exactly `docs/plans/history-store-security-scope.md`; `code=false` read
  from the `changes` job log, not inferred; five jobs `skipped` with the aggregator confirming the
  filter as the cause. The `Falsified by:` half checked too: no test names this path, while
  `test_documentation.py:208` names `docs/plans/event-driven-session-observation.md`, so the deny
  list is genuinely per-path rather than a blanket pass for `docs/plans/`.
- **AC-2 — link- and anchor-clean. PASS, with negative controls.** `python3 scripts/validate_plugins.py`
  exit 0 in the worktree. Exit 0 alone proves nothing, so both `Falsified by:` clauses were driven
  in a throwaway `git archive` copy: appending `[broken](./no-such-file.md)` produces
  "docs/plans/history-store-security-scope.md: Markdown link target does not exist" and exit 1, and
  appending `http://localhost:4553` produces "contains 'http://localhost:4553'" and exit 1. The
  validator does reach this file. The document contains no inline links at all, so it can be
  promoted without rewriting.
- **AC-3 — permitted fields have live producers; never-list is DEC-6's. PASS on both halves, but see
  M1 and M2.** Producers confirmed: session identity `sessions.py:262-265`, state and detail
  `:288-289`, `project` `:265`; gate open and close `events.py:676` (set) and `:660`/`:693`
  (cleared); turn boundaries and timings `turns.py:90-113`; tool names `sessions.py:447` and
  `claude_data.py:353` plus four `transcripts.py` collectors. Never-list is DEC-6's four items, in
  DEC-6's order, nothing added or dropped — read against the ruling's verbatim text. The
  implementation's own disclosure stands: `turns.py:289` is the `tool_names` state-dict entry, and
  `turns.py:35` is an internal `tool_id → name` map whose publish sites are `turns.py:377` and
  `sessions.py:447`. Wrong sites, right claims.
- **AC-4 — names every `SECURITY.md` sentence the store makes false. PASS.** All three quoted
  strings exist verbatim: `SECURITY.md:261` "The server writes three files, all under `~/.cargento`",
  `:265` "One forwarder writes a fourth", `:35` "Read-only against harness stores.", `:294`
  "Marking a session handled writes one file, and it is the only thing Cargento writes on your
  behalf". Invariant 2's enumeration counted independently and matches the document's paraphrase
  exactly: seven mutating endpoints, six in memory, one `POST` to disk, one forwarder, one `GET`
  sidecar. Amendment 1's arithmetic is right — bumping `:261` without `:265` really would leave two
  files called the fourth. **Is there a fourth inside `SECURITY.md`? No.** An independent sweep for
  count claims, "writes" claims, network-posture claims and restart/retention claims found only the
  three the document names; `:320` and `:33` survive the store unchanged. The document's own scope
  hedge is "elsewhere in `SECURITY.md`", and within that scope it is complete. M3 and M4 are outside
  it.
- **AC-5 — off switch reaches the respawn path; `--forget` is one-shot. PASS.** Every occurrence of
  the flag in runtime code is exactly three — `cli.py:130` (declaration), `cli.py:213`
  (`git_probe_enabled=not args.no_git`), `lifecycle.py:558-559` (`if args.no_git:
  argv.append("--no-git")`, beside six sibling flags) — so "mirrors `--no-git` at every one of that
  flag's sites" is accurate, and it is the sentence pattern `SECURITY.md:173` already uses for
  `--no-spacedock`. `--forget`'s placement is checkable: `--stop` and `--status` are real one-shot
  commands at `cli.py:168` and `:173`, and all six rows of the `HOW_TO_USE.md` off-switch table
  (`:339-344`) are reversible per-run switches, so the document's reason for keeping it out of that
  table holds.
- **AC-6 — nothing states a flag, path or promise that does not exist. PASS.** The diff touches
  neither `HOW_TO_USE.md`, `SECURITY.md` nor `docs/promise-map.md`. Re-run at `c46f045`:
  `parse_args(['--no-history'])` and `parse_args(['--forget'])` both exit 2 with "unrecognized
  arguments", while `--no-git` exits 0 — so the parser is answering, not erroring for another
  reason. `test_documentation` 14 tests OK; it reads `SECURITY.md` by literal path and pins "The off
  switch is `--no-git`." (`test_documentation.py:259-261`), so an edit to that file's git-probe
  clauses is what turns it red, which is what makes the pass evidence this PR left it alone.
- **AC-7 — reads as a contract, at the precedents' length, buildable by a stranger. PASS on shape,
  FAIL on the last clause; this is where M1 and M2 land.** Read against both precedents at their
  own commits. Shape is precedent-faithful to the sentence pattern: the same opening formula, the
  same "The section, verbatim" fence, the same "A violation of any boundary in this section is a
  security bug:" closing enumeration, the same "Intro amendments that ride with the promotion" and
  "What else the build PR does with this file". 127 lines against 102 and 84 — above the git probe,
  as the entity predicted, and inside 130 ± 30. It bounds rather than argues: the one rationale
  paragraph (49-52) is DEC-6's own recorded reasoning reproduced almost verbatim, and the quota
  precedent carries a comparable "Consent and the off switch" paragraph, so it is in keeping. All
  seven DEC-6 elements are present. **What a stranger could not settle from it alone** is whether
  the published `state_detail` may be kept (M2) and whether the size cap triggers eviction (M5),
  and one sentence they would rely on is false (M1).

### Review-finding disposition

Five proposed **Material**, three **Deferred risk**, three **Polish**, four refuted. Every finding
below was reproduced by me against the tree at `c46f045`, not accepted from the lens that raised it.
Materiality is proposed, not authorized: this is an `actor:ensign` round and its resolution is
advisory. No fix was made and no candidate byte changed.

**M1 — Material — the section asserts a set equality that `SECURITY.md` itself contradicts.**
Released user and normal workflow: a reader of the published security policy, from the day H1
promotes the section; today only H1's builder and reviewer reach it.
Observable harm: line 36 says of the four-item never-list "That list is the same one the board
itself is held to". The board is held to a strictly looser list. `SECURITY.md:382-383` — "The
dashboard reads those stores and publishes prompt text: the session title, the line beneath it,
`last_prompt`, the observer goal, and a Codex title". `SECURITY.md:440` — "Reading `/api/data` is
the whole board: every session's titles, prompts and project paths". Promoted verbatim, `SECURITY.md`
would deny at one section what it asserts at two others — the "contradicting itself two sections
apart" failure amendment 3 was written to prevent, this time inside the fenced section rather than
the intro.
Affected value AC or boundary: `value-ac[AC-7]` — a stranger cannot build a boundary from a document
whose framing sentence is false; and `contract[SECURITY.md#published-text-credential-redaction]`,
which exists because the board publishes prompt text.
Trigger evidence: doc line 36 read against `SECURITY.md:382-383` and `:440`, both quoted above. The
operative second half of the sentence ("a field that is not already published on the live board is
not a field history may keep") is a sound necessary condition and survives; it is the first clause
that is wrong. Raised by lens B, reproduced independently.

**M2 — Material — the contract does not exclude `state_detail`, and its own rule points at keeping it.**
Released user and normal workflow: a user whose board showed a permission prompt, after H1 ships a
store that keeps 14 days of it.
Observable harm: `state_detail` is a published snapshot field (`sessions.py:289`), and
`SECURITY.md:289-290` says plainly that "a state detail can carry a permission prompt's own text, an
open question's, or a plan's first line" — which is why the dismissals record leaves the title and
the state detail "deliberately absent". The history store is the closest analogue to that record and
the document's never-list does not exclude either field, while its line 24 rule ("holds nothing the
live snapshot does not already serve") plus M1's false set-equality reads as a licence to keep
anything published. If H1 keeps it, `SECURITY.md:410-411` — "The fourth thing carrying this text is
a file: the observer sidecar" — becomes false, and the store is the first durable, rolling home for
that text rather than one file per session.
Affected value AC or boundary: `contract[SECURITY.md#published-text-credential-redaction]`, the
section that exists because this text can carry a live credential — `SECURITY.md:384-385` records
seven distinct live Anthropic credentials found in ordinary local prompt history.
Trigger evidence: `sessions.py:289` against doc lines 24-26 and 30-34. The fix stays inside AC-3's
"exactly DEC-6's" letter if it is written as an elaboration of never-item 1 rather than a fifth item,
exactly as that list already elaborates "tool input" and "paths". Raised by lens B, reproduced
independently.

**M3 — Material — the "three files" count also lives in `SKILL.md`, and the document does not name it.**
Released user and normal workflow: anyone reading the shipped skill body after H1 lands.
Observable harm: `SKILL.md:146` — "The server writes three files, all under `~/.cargento`" — with
the same enumeration. The day the store ships, `SKILL.md` says three and the amended `SECURITY.md`
says four. Doc line 115 states `SKILL.md`'s whole obligation as one `--no-history` flag row, so the
miss is caused by an exhaustive-sounding sentence rather than by silence.
Affected value AC or boundary: `contract[cargento/skills/cargento/SKILL.md#start]` — the shipped
product surface, a validated artifact per `AGENTS.md`'s documentation table.
Trigger evidence: `SKILL.md:146-150` quoted against doc line 115. Its forwarder sentence carries no
ordinal, so only the count needs bumping there. Raised by lens B, reproduced independently.

**M4 — Material — the sole-occupancy clause amendment 3 removes lives at four further sites.**
Released user and normal workflow: a user reading `--help`, or the shipped skill body, after H1 lands.
Observable harm: the claim that the dismissals file is the only thing Cargento writes on the user's
behalf also sits at `SKILL.md:295` ("The rollback switch for the one file Cargento writes on your
behalf.") and, as user-facing output rather than a comment, at `cli.py:144` inside `--no-dismiss`'s
help text. A repository-wide grep finds five sites in all; the document names one. Amendment 3's own
rationale — "easy to miss because the false part is a subordinate clause rather than a heading or a
count" — applies word for word to the sites it missed.
Affected value AC or boundary: `contract[cargento/skills/cargento/SKILL.md#options]` for the skill
row, and the `--help` string as shipped program output.
Trigger evidence: `grep -rn 'on your behalf'` over the tree at `c46f045` returns `SECURITY.md:294`,
`SKILL.md:295`, `cli.py:144`, `dismissals.py:3` and `tests/test_dismissals.py:1`. Raised by lens B
for three sites; the two docstrings are mine and are Polish, below.

**M5 — Material — line 47 denies the size cap two lines after requiring it.**
Released user and normal workflow: a reader of the promoted policy; and H1's reviewer, who will read
it against H1's own acceptance criteria.
Observable harm: line 45 states "Retention is 14 days by default, with a size cap, and both are
configurable", and line 47 then states "Retention is what bounds the store; nothing else does".
DEC-6's own words are "Retention is 14 days by default with a size cap, both configurable, evicted
by age first", and H1's acceptance criteria say "Records older than the retention bound, **or beyond
the size cap**, are evicted oldest first". Line 47 read literally denies the bound H1 must
implement, while lines 74-75 simultaneously call "an unbounded store" a security bug.
Affected value AC or boundary: `value-ac[AC-7]` — the retention element is present but not cleanly
bounded, which is the second thing a stranger could not settle from the document alone.
Trigger evidence: doc lines 45-47 read against DEC-6's ruling paragraph on DRC-4234 and H1's
acceptance-criteria paragraph on DRC-4044, both fetched live. The clause is the document's own
addition; DEC-6 does not contain it. Raised by lens A, reproduced independently.

**D1 — Deferred risk — the discard trigger gains a case DEC-6 does not name.**
Line 65 lists "a version the running build does not understand" among the discard triggers. DEC-6
says only "A corrupt store starts empty and the board says so", and H1 says "a corrupt or unreadable
store is discarded". DEC-6 does not forbid it, so this is silence resolved permissively rather than a
boundary breached, but it licenses discarding an intact, readable store on any format bump.
Promote-to-material condition: H1 ships a version-mismatch discard path that loses a readable store
without the header reporting it.

**D2 — Deferred risk — "adds no endpoint" is promoted as a security boundary DEC-6 never imposed.**
Doc lines 62, 70 and 76 make the absence of any new route a violation criterion ("a history file
reachable over the port"). DEC-6 says only "Nothing in it leaves the machine." D10 (DRC-4033), the
away-digest, is the dependent this store exists for, and a loopback route serving a digest would then
be a documented security violation rather than a design choice. The narrowing is in keeping with the
git-probe precedent's own "There is no fallback to a plain `git status`", so it is probably the right
posture — it should be intentional. Promote-to-material condition: D10's design needs a route this
clause forbids. File against D10.

**D3 — Deferred risk — two pre-existing `SECURITY.md` counts are already loose, and one survives the
mechanical amendment.**
`SECURITY.md:261`'s "three files" omits the observer sidecar the same document says the server writes
under `~/.cargento` (`:50-51`, `:411-412`) while counting the equally per-conversation status-line
memo as "a fourth". And `SECURITY.md:441` says "the seven POST routes" where there are eight —
`/api/events/<harness>` at `http_api.py:845` plus the seven-entry table at `:852-858` — because it
borrows invariant 2's seven-mutating figure, which excludes `/api/shutdown`, and then names
`/api/shutdown` as one of them. Counted independently. Neither is falsified by the store, and doc
lines 106-107's "No count in Scope's network paragraph changes" is correct. File separately rather
than promoting into this PR.

**P1 — Polish — "is not history" is softer than the bullet around it.**
Doc lines 30-31: "Prompt text, of any session, at any point. The title a row shows is derived from a
prompt and is not history." The bullet sits under the heading "What is never written to it:", so its
plain force is exclusion and lens A's reading of it as a licence does not survive. But "is not
history" is the one exclusion in the list phrased as a category claim rather than as a write ban,
and it is a sentence an implementer under pressure would reach for.

**P2 — Polish — the sole-occupancy claim also sits in two docstrings.**
`dismissals.py:3` ("The one thing Cargento writes on the reader's behalf") and
`tests/test_dismissals.py:1`. Cosmetic rather than user-facing, unlike M4's three sites.

**P3 — Polish — three citation audits, all wrong site and right claim.**
`turns.py:289` is the `tool_names` state-dict entry rather than the turn-boundary producer at
`:90-113`; `turns.py:35` is an internal `tool_id → name` map whose only reader is `:46`, with the
publish sites at `turns.py:377` and `sessions.py:447`; `sessions.py:264` is `"harness"` rather than
the session id at `:263`, though harness is half the session key. None of the three claims fails —
each holds at a different line. The first was already disclosed by implementation.

**Refuted — four, including both of lens A's strongest.**
R1: that the allow-list omits the `project` label H1's interactive rail criterion needs, so H1 must
either store a forbidden field or fail its own AC. Refuted: `SECURITY.md:166` and `:485-486` already
draw exactly this line — raw `cwd` is "a matching hint" and "never echoed to `/api/data`", while the
two-segment `project_from_cwd` label at `sessions.py:265` is published and `:440` says so. Storing
the published label is not storing a path. What survives is M1: the reason a reader could reach the
wrong answer is the false set-equality, not a missing field.
R2: that the one-directional content rule at lines 36-37 is itself a defect for dropping the
allow-list's closure. Refuted as a separate finding — the necessary-condition form is correct; it is
the clause beside it that is false, which is M1.
R3: that "mirrors `--no-git` at every one of that flag's sites" overstates the evidence. Refuted:
the flag occupies exactly three runtime sites, and `SECURITY.md:173` uses this identical formula for
`--no-spacedock`, which has the identical three-site shape. Lens B's useful residue is passed to H1
rather than treated as a finding: `test_lifecycle.py:1281` asserts a fixed five-flag forwarding set,
so it will not fail if `--no-history` is left out of the respawn branch and must be hand-updated.
R4: the hypothesis that a fourth falsified sentence hides inside `SECURITY.md`. Refuted by an
independent sweep — the document's three are the three. The genuine misses are outside the file, and
are M3 and M4.

### Summary

Verdict **NO-GO**, on M1 and M2 alone; the other three Material findings are worth the same round
but would not by themselves have blocked. The document is a faithful, precedent-shaped statement of
DEC-6 — all seven elements present, nothing wider in any hard sense, the never-list and the
default-on rationale DEC-6's own words, and every citation it makes about the runtime and about
`SECURITY.md` checks out, including invariant 2's counts and amendment 1's arithmetic. Six of the
seven acceptance criteria pass on reproduced evidence, two of them driven from their `Falsified by:`
clause in a throwaway checkout rather than trusted from an exit code.

What blocks it is one sentence and one omission, and they are the same defect seen twice. Line 36
tells the reader the store's four-item never-list "is the same one the board itself is held to"; the
board publishes prompt text and project paths, and `SECURITY.md` says so at `:382-383` and `:440`.
Paired with the closure rule beside it, that reads as a licence to keep anything the board publishes
— which includes `state_detail`, the field carrying "a permission prompt's own text, an open
question's, or a plan's first line", the field the dismissals record deliberately excludes for that
reason, and the field a 14-day store would be the first durable home for. Both fixes are one clause
each and neither touches DEC-6's scope.

The remaining three are the completeness of the promotion, which is this document's central promise:
the sole-occupancy clause lives at five sites and the document names one, the "three files" count
lives at two and the document names one, and line 47 denies the size cap that line 45 requires and
H1's own criteria enforce. CI is green on the current head with `code=false` read from the log and
the measurable jobs skipped by the filter rather than by a failure; `mergeStateStatus` is `CLEAN`;
there is no Copilot review to read on this PR or on the three before it; and the Linear body is
byte-identical to the approved draft. Nothing on the branch was edited, nothing merged, no worktree
or branch removed.

## Stage Report: implementation (correction round 1)

- DONE: M1 — remove or correct the set-equality clause at line 36, keep the necessary condition
  `docs/plans/history-store-security-scope.md:38-40`; the false clause is gone and replaced with the one-way reading ("The condition runs one way only — the board publishes prompt text and project paths, and the never-list above bans both"). Reproduced the reviewer's citations first: `SECURITY.md:382-383` publishes the title, the line beneath it, `last_prompt`, the observer goal and a Codex title; `SECURITY.md:440` publishes project paths.
- DONE: M2 — write the `state_detail` exclusion into never-item 1 as an elaboration, not a fifth item
  `:30-33`; item 1 now bans prompt text "whatever field carries it" and names the row title, `last_prompt` and the state detail. The never-list is still exactly DEC-6's four (AC-3 holds).
- DONE: M3 — add `SKILL.md:146`'s three-files count to the promotion list
  `:120-124`; the `SKILL.md` bullet bumps the count only and says why — verified `SKILL.md:147-148` names `statusline_hook.py` as the forwarder with no ordinal, unlike `SECURITY.md`'s "One forwarder writes a fourth".
- DONE: M4 — name `SKILL.md:295` and `cli.py:144` as sites the sole-occupancy amendment must reach
  `:108-109` (amendment 3 now says it is not done until both go) and `:125-127` (the promotion list carries them). Both strings reproduced verbatim: the `--no-dismiss` flag row and its `--help` text each call the dismissals file "the one file Cargento writes on your behalf". The two docstrings are listed as non-user-facing and load-bearing on nothing, per the P2 decline.
- DONE: M5 — reword line 47 so age retention and the size cap bound the store together
  `:48-51`; "Retention is what bounds the store; nothing else does" is replaced by "The age window and the size cap bound the store together, and raising either does not stop the other applying". Age-first eviction is unchanged in the sentence above and in the violation list at `:79`.
- DONE: P1 — rephrase lines 30-31 as a write ban rather than a category claim
  `:30-31`; "The title a row shows is derived from a prompt and is not history" became "Not a row's title, which is derived from a prompt", inside the M2 elaboration. Every never-item is now a ban.
- DONE: D1, D2, D3 declined and P2, P3 recorded — none touched
  The version-mismatch discard trigger (`:68-71`), the "adds no endpoint" boundary (`:66`, `:73-74`) and the two loose `SECURITY.md` counts in amendments 1-2 (`:90-102`) are byte-identical to `c46f045`; `git diff c46f045..HEAD` touches only the six spans above.

### Surface, checks and head

- New head: `0016542` (`00165422447ea3a9c39f6de026def656edcabf5c`), pushed to `spacedock-ensign/drc-4330`; PR #258 head confirmed moved, still one file in the diff.
- Round surface, `git diff --numstat c46f045..HEAD`: `19 7 docs/plans/history-store-security-scope.md`.
- Cumulative, `git diff --numstat "$(git merge-base main HEAD)"..HEAD`: `139 0`, one file. Against the 130 ± 30 estimate that is 107% of the midpoint, inside the band (100-160). AC-1 holds — one new file, nothing else in the diff.
- `python3 scripts/validate_plugins.py` — exit 0, "Validated 1 skills across 1 plugins". It resolves every relative Markdown link and heading anchor across the owned docs, so a broken link or a renamed heading in this file would fail it.
- `python3 -m unittest cargento.skills.cargento.tests.test_documentation` — 14 tests, OK. These bind doc prose to code: the git-probe pair asserts `SECURITY.md` says "The off switch is `--no-git`." *and* that the parser accepts `--no-git`, so dropping either half fails. Nothing in them reads this plan file yet — the history analogue is owed by H1, as `:128-131` says.
- Commit is DCO signed off (`Signed-off-by` present). Not merged.
- Document re-read end to end after patching, before the push. That pass caught four seams the patches left — an awkward "earns a field nothing here" tail on M1, a loose "The two bounds" antecedent on M5, an ambiguous "two lines already in it" on M3, and two ragged rewraps — all fixed in the same commit.

### Discrepancy for the FO

- The M2 disposition says `state_detail` is what "the dismissals record deliberately omits for that reason". `SECURITY.md:288-290` attributes that omission to the **bounded record of state disputes**, not the dismissals store: "the row's title and its state detail are deliberately absent". I wrote the accurate attribution rather than the disposition's wording. The exclusion M2 asked for is unaffected; only the cited precedent's name changed.
- `sync-docs` was not re-invoked this round. It was run in round 0, this round's diff is prose inside one `docs/plans/` file that no test opens by literal path, and a sync-docs commit touching a second path would breach AC-1.

### Summary

Five material findings and one polish, all six landing as clause-level edits to `docs/plans/history-store-security-scope.md` and nothing else. Every citation the reviewer made was reproduced against `c46f045` before editing, and all five held. The one judgement call was M2's precedent: `SECURITY.md` credits the state-dispute record, not the dismissals record, with omitting state detail, so the document says that instead — flagged above rather than silently reconciled. The `state_detail` exclusion went in as an elaboration of never-item 1, keeping the list at DEC-6's four as AC-3 requires, so the `route for decision` escape was not needed.

## Stage Report: review (cycle 2)

- DONE: Each of the six authorized correction-round fixes (M1, M2, M3, M4, M5, P1) verified against
  PR #258's current head `0016542` by reading the file at that SHA, each stated as closed or not with
  the line cited; and D1, D2, D3 confirmed untouched by `git diff c46f045..0016542`, which must reach
  only the six spans the round claims.
  All six closed, lines cited below. `git diff -U0 c46f045..0016542` is five hunks — `@@ -30,2 +30,4`
  (M2+P1), `@@ -36,2 +38,3` (M1), `@@ -47 +50,2` (M5), `@@ -104 +108,2` (M4), `@@ -115 +120,8`
  (M3+M4) — and reaches nothing else; D1's discard triggers (`:68-71`), D2's no-endpoint clauses
  (`:66`, `:73-74`) and D3's amendments 1-2 (`:90-102`) are byte-identical to `c46f045`.
- DONE: AC-1 through AC-7 re-verified on head `0016542` from their own `Verified by:` clauses, plus
  CI green on this head, `mergeStateStatus`, and Copilot inline comments read.
  Seven PASS, reproduced below; three checks all carry `head_sha=00165422447ea3a9c39f6de026def656edcabf5c`,
  `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`, and `pulls/258/comments`, `pulls/258/reviews`
  and `issues/258/comments` are each length 0 — no Copilot pass exists to read on this PR.
- DONE: A GO or NO-GO verdict with any new or surviving finding under its disposition label, with no
  edit to the branch, no merge, no worktree or branch removed.
  Verdict **GO**. One new **Deferred risk** and two **Polish**, none blocking, all below.
  `git status --porcelain` in the worktree is empty and HEAD is still `0016542`; nothing merged,
  no worktree or branch removed. Negative controls ran in `/tmp/drc4330rev2`, a `git archive` copy.

### The six fixes, at `0016542`

- **M1 — closed.** The false set-equality is gone. `:38-40` now reads "The store may never widen that
  list: a field that is not already published on the live board is not a field history may keep. The
  condition runs one way only — the board publishes prompt text and project paths, and the
  never-list above bans both." Both halves reproduced: `SECURITY.md:382-383` publishes the title,
  `last_prompt`, the observer goal and a Codex title; `SECURITY.md:440` publishes project paths.
- **M2 — closed, and AC-3 survives it.** `state_detail` is banned inside never-item 1 at `:30-33`
  ("not a session's state detail, which can carry a permission prompt's own text, an open question's,
  or a plan's first line"), not as a fifth item. The list is still four bullets (`:30`, `:34`, `:35`,
  `:36`), items 2-4 byte-identical to `c46f045`. Producer confirmed: `sessions.py:289`.
- **M3 — closed.** `:120-124` adds `SKILL.md`'s own count to the promotion list. Reproduced:
  `SKILL.md:146` is verbatim "The server writes three files, all under `~/.cargento`", and the
  sentence after it names `statusline_hook.py` with no ordinal, so "the count only" is right.
- **M4 — closed at all three user-facing sites.** `:108-109` makes amendment 3 unfinished until the
  other sites go; `:120-124` carries `SKILL.md:295` and `:125-127` carries `cli.py:144`. Both strings
  reproduced verbatim. A repository-wide grep at this head returns exactly the five sites the round-1
  finding named; the two docstrings are recorded at `:127` as non-user-facing, per the P2 decline.
- **M5 — closed.** `:50-51` replaces the denial with "The age window and the size cap bound the store
  together, and raising either does not stop the other applying"; age-first eviction is unchanged at
  `:48-50` and the violation list at `:78-79` still reads "an unbounded store or one evicted by
  anything but age first". Nothing now contradicts H1's "or beyond the size cap" criterion.
- **P1 — closed.** `:30-31` is a write ban ("Not a row's title, which is derived from a prompt")
  rather than the category claim "is not history". Every never-item is now phrased as an exclusion.

### Acceptance criteria, reproduced on `0016542`

- **AC-1 — PASS.** `git diff --name-status "$(git merge-base main HEAD)"..HEAD` is one line,
  `A docs/plans/history-store-security-scope.md`, `139 0`. The `changes` job log on this head emits
  "Every changed path is prose the gate cannot measure." then `code=false`, and the aggregator log
  shows `CODE: false` with `R_CHANGES: success` and `R_LINT`/`R_TYPECHECK`/`R_FLOOR`/`R_TEST`/`R_PLATFORM: skipped`
  — the filter, not a dead dependency.
- **AC-2 — PASS, with a negative control.** `python3 scripts/validate_plugins.py` exit 0 in the
  worktree at this head. Exit 0 alone proves nothing, so a `git archive 0016542` copy with
  `[broken](./no-such-file.md)` appended gives "docs/plans/history-store-security-scope.md: Markdown
  link target does not exist" and exit 1 — the validator reaches this file at this head. The document
  still contains no inline link and no `localhost` spelling (`grep -nE '\]\(|localhost|http://'`
  returns nothing), so it can still be promoted without rewriting.
- **AC-3 — PASS.** The never-list is exactly DEC-6's four items, `state_detail` inside item 1 rather
  than a fifth; the permitted list at `:24-26` is untouched this round, so round 1's producer
  reproduction still holds.
- **AC-4 — PASS.** The three `SECURITY.md` sentences and amendment 1's arithmetic are untouched by
  this round's diff; `SECURITY.md` is unchanged in the tree.
- **AC-5 — PASS.** `:58-61` and `:63-66` are untouched; round 1's three-site reproduction stands.
- **AC-6 — PASS.** The diff touches neither `HOW_TO_USE.md`, `SECURITY.md` nor `docs/promise-map.md`.
  Re-run at this head: `parse_args(['--no-history'])` and `parse_args(['--forget'])` both exit 2 with
  "unrecognized arguments" while `--no-git` exits 0, so the parser is answering rather than erroring
  for another reason; `test_documentation` 14 tests OK, and it pins "The off switch is `--no-git`."
  in `SECURITY.md` by literal path, so an edit to that file's git-probe clauses is what turns it red.
- **AC-7 — PASS, including the clause that failed at `c46f045`.** Read against
  `git show 701b7f0:docs/plans/git-probe-security-scope.md` (102 lines) as round 1 did. The shape is
  unchanged and still precedent-faithful — same opening formula, same fenced section, same "A
  violation of any boundary in this section is a security bug:" enumeration, same two closing
  sections — at 139 lines against 102 and 84, inside 130 ± 30. Both points a stranger could not
  settle are now settled from the document alone: `state_detail` may not be kept (`:30-33`, with the
  reason and the precedent named), and the size cap is an enforced bound, not decoration (`:50-51`
  read with `:78-79`). All seven DEC-6 elements remain present, and every edit narrows what the store
  may keep rather than widening it.

### Findings

**D4 — Deferred risk — M1's gloss calls the board's published project label a path the never-list
bans.** Released user and normal workflow: none today; H1's builder, when it designs the store's
fields. Observable harm: `:39-40` says "the board publishes prompt text and project paths, and the
never-list above bans both", while never-item 3 bans "a session's working directory" and "any path a
tool touched" — the published `project` (`sessions.py:265`) is a derived two-segment label, and
`SECURITY.md:485-486` says raw `cwd` is "never echoed to `/api/data`". Round 1 refuted R1 on exactly
that distinction; this clause blurs it in the safe direction. Affected boundary:
`value-ac[AC-7]`, weakly — the kept-list at `:24-26` is exhaustive and already omits `project`, so a
stranger still builds one consistent store (no project label), which is why this is not Material.
Trigger evidence: `:39-40` read against `:35`, `sessions.py:265` and `SECURITY.md:440`, `:485-486`.
Promote-to-material condition: H1's interactive rail needs the project label and its builder reads
this clause as forbidding it. **File against DRC-4044; do not promote into this PR.**

**P4 — Polish — "may never widen that list" (`:38`) names the prohibition list where the operative
sense is the set of fields kept.** Pre-existing phrasing, and the colon-clause beside it states the
rule unambiguously. No fix asked.

**P5 — Polish — "the bound above" (`:56`) is singular where `:48-51` now sets two bounds.** A seam
left by M5's rewording. No fix asked.

Nothing else new, and nothing from round 1 survives: M1-M5 and P1 are closed, D1-D3 and P2-P3 stand
declined and untouched.

### The FO's flagged judgement

The implementer is right and the round-1 disposition was wrong. `SECURITY.md:287-290` attributes the
omission of the title and the state detail to **the bounded record of state disputes** — "The same
route serves the bounded record of state disputes … the row's title and its state detail are
deliberately absent, because a state detail can carry a permission prompt's own text, an open
question's, or a plan's first line". The Dismissals section begins at `:292` and makes no such
statement. The document's `:32-33` says "the bounded record of state disputes", which is accurate;
M2's wording was mine to get wrong, and the correction did not change what the fix excludes.

### Summary

**GO.** All five Material findings and the one Polish landed as clause-level edits inside the six
authorized spans and nothing else moved: five hunks, one file, `139 0` cumulative, and the three
deferred findings byte-identical to `c46f045`. Every claim the new clauses make about `SECURITY.md`,
`SKILL.md` and `cli.py` was reproduced at this head rather than read back from the implementation
report, and all of them hold.

AC-7's failing clause is repaired at its root: the false framing sentence is gone, the `state_detail`
exclusion is written into never-item 1 with its reason and its precedent, and the size cap is an
enforced bound rather than a denied one — so the two questions a stranger could not answer at
`c46f045` are answerable from the document alone, and the never-list is still DEC-6's four. CI is
green on `0016542` with `code=false` read from the job log and the measurable jobs skipped under
`CODE: false`, `mergeStateStatus` is `CLEAN`, and there is no Copilot review or inline comment on
this PR to read. One new Deferred risk (D4) is filed for H1 rather than promoted, per the workflow's
own rule, and two Polish seams are recorded without a fix request. Nothing on the branch was edited,
nothing merged, no worktree or branch removed.
