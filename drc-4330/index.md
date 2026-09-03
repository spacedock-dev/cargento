---
id:
title: 'History groundwork · SECURITY.md scope section for the local history store'
status: triage
source: https://linear.app/recce/issue/DRC-4330
started: 2026-09-03T03:29:50Z
completed:
verdict:
score: 0.6
worktree:
issue:
pr:
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
---

[DRC-4330](https://linear.app/recce/issue/DRC-4330) — Linear priority High, no estimate, labels `journey:mid-flight`, `move:none`. Filed 2026-09-02 as the groundwork for H1 (DRC-4044), the shape the quota, git-probe and ask-lane groundwork issues used: a SECURITY.md scope section that lands before the code it bounds.

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

### Feedback Cycles

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
