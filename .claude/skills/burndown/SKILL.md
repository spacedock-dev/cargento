---
name: burndown
description: Use when burning down a milestone of the Cargento Actions Front and Center project to completion, planning how to group and stack its issues, or closing out a single DRC issue.
---

# burndown

Take one milestone, group its issues by the functionality they change, build each group as a layer
of a GitHub stack, land the stack, reconcile every issue, and repeat until the milestone is closed.

The project is **Cargento: Actions Front and Center** in Linear (team `DRC`):
<https://linear.app/recce/project/cargento-actions-front-and-center-eed1852b11e6/overview>.
Invoke the required supporting skills inside the current workflow. Delegating work to a subagent is
normal here and is covered by the parallelism rules below.

## Invocation

- `burndown "<milestone name>"`: plan the milestone, wait for approval of the plan, then build,
  land and reconcile group by group until the milestone is complete or blocked.
- `burndown "<milestone name>" --plan`: print the plan and stop.
- `burndown "<milestone name>" --merge`: the caller pre-approves the plan and its merges. Still
  print the plan before the first mutation.
- `burndown DRC-####`: work that one issue, inside its milestone's plan, as a group of one if it
  groups with nothing.

The milestone name is resolved against the project with the Linear milestone lookup. Do not hand a
milestone name to `recce-dev:linear-deep-dive`: its parser treats a string without a team prefix as
a project search.

Merging to `main` is what closes an issue, and this skill merges. The caller's approval of the plan
block in step 2 is the authorization for every merge in that plan, and for nothing outside it.
Approval, and `--merge`, still cover the plan as recomputed when the only changes are discoveries
filed under step 7's **Discoveries**, a small fix riding an open layer, and issues moving later
because of `blockedBy`. A new issue in product scope, a changed review tier or a reordered `web/`
stack needs a fresh yes. The trunk is
always `main`: never stack on, target or promote a long-lived branch such as `feat/future-ui`.

## Prerequisites

- Linear read and write access to the `DRC` team: issues, relations, labels, milestones and the
  project overview.
- The `recce-dev:linear-deep-dive`, `superpowers:test-driven-development`, `sync-docs`,
  `sync-project` and `visual-review-and-fix` skills.
- `gh` with the `github/gh-stack` extension (`gh extension list`; `gh extension upgrade gh-stack`
  when it lags upstream), able to push to `origin`, open and merge pull requests.
- A Git checkout that can create worktrees, run the canonical pre-PR suite and make DCO-signed
  commits (`git commit -s`).
- A browser automation capability for the `visual-review-and-fix` walks. Its absence degrades the
  run rather than stopping it: say so, and name the walks that did not happen.
- A design-project read capability whenever an issue carries a `## Design reference` section. See
  [the design reference rules](references/design-reference.md).

If a required capability is missing, stop before the read or mutation that needs it.

## Stop, and when

Stop means: make no further mutation, say what has already been written to Linear and to git, name
every branch, worktree, stack, pull request, server and subagent this run started, then wait. It
does not mean switch to other work unless the step says so.

Stop and ask, in one block (what is waiting, the recommended answer, what yes does), when:

- an issue needs a decision nobody filed. File the decision issue in this milestone and link it as
  a blocker. This stops only that issue and its dependents: put the ruling request and the re-plan
  in one block, and once the re-plan is approved, continue the groups that do not depend on it;
- a design-project read is refused;
- a full-adversarial review returns NO-GO;
- a second correction round is wanted on a layer without a named user-visible regression it closes;
- CI is red twice on the same head after the suite was green locally;
- the plan must change;
- the run passes its estimate by half.

Between groups, report measured state only: each pull request with its head SHA and check
conclusions, the Linear state of each issue read back, the receipts posted, and every worktree,
server and subagent still alive. Check background work in the same turn you report on it.

## 1. Load the milestone

1. Resolve the milestone. Fetch the project's issues ordered by `createdAt`, page until
   `hasNextPage` is false, and keep those whose `projectMilestone` is this one. The default
   `updatedAt` order shifts under your own writes.
2. Classify by state **type**, never by name: `completed`, `canceled` and `duplicate` are finished,
   `triage` is not yet a candidate, everything else is open. The team's state names change over
   time.
3. For every `completed` issue closed by a merge or a ruling, check for a step 6 receipt comment.
   One without a receipt is an interrupted reconcile: finish it before planning anything new. A
   `canceled` or `duplicate` issue needs none.
4. Read the milestone description. `Read before building` carries contract notes keyed by issue ID,
   `Waits on` names outside blockers, and `Decide before building` names an open question.
5. Scope is the milestone. An issue in the project with no milestone, or in another milestone, is
   out of scope even when it is unblocked.
6. An open issue already `In Progress`, `In Review` or `Ready for Review` has work in flight. Find
   its branch (`gitBranchName`, `gh pr list --search DRC-####`, `git worktree list`) and its pull
   request, and plan it as that existing pull request or layer (`gh stack checkout <pr>`); never
   open a second one. If a live worktree this run did not start holds it, leave it out of the plan
   and name it.
7. An issue in the `Blocked` state whose `blockedBy` holds no open issue is a reconcile that never
   ran: move it out of `Blocked` and plan it.

## 2. Plan: group, order, estimate

Read each open issue's `blockedBy`, labels, estimate and Scope (the files and views it names). Set
the `Verification`-labelled issue aside; it runs last.

**Tag each issue:**

- Surface: `cargento_runtime/web/`, the shipped `SKILL.md`, `SECURITY.md` or `HOW_TO_USE.md`,
  `config.py`, or Python only.
- Review tier, from **AGENTS.md, "Calibrating Effort"**: full adversarial for the `Security` label,
  credential handling, data loss, or a change to a boundary `SECURITY.md` names (such as the history
  prompt-text allowlist); two lenses plus an arbiter otherwise.

**Group.** Two issues share one pull request when all of these hold: they change the same view or
the same contract (the same NUI amendment, the same drift block, the same route), one blocks the
other or neither does, they share a review tier, and their estimates sum to no more than 7 points (L 5 plus S 2).
A tier is the merge-risk unit; an issue stays the reconcile unit. Keep a full-adversarial issue out
of a group that would inflate its review with unrelated UI diff.

**Arrange.**

- Every group that touches `web/` becomes one layer of a single stack, in topological order of
  `blockedBy`. Exactly one stack whose layers touch `web/` may be in flight; a second web group
  becomes a higher layer or waits. Layers are linear by construction, so each carries correct byte
  pins for its own tree.
- A group that touches none of `web/`, `SKILL.md`, `config.py` or another in-flight group's files
  is an independent pull request on `main`, built in parallel.
- A group that touches `SKILL.md` or `config.py` but not `web/` is either a layer of the stack
  (when a `web/` layer depends on it) or a single pull request that waits until no other in-flight
  group touches that file. It is never built in parallel with one that does.
- Order by: an unblocked `Security` or Urgent or High priority group that no `web/` layer depends on
  lands first, on its own; then the longest estimate-weighted path to the Verification issue; then
  the smaller estimate. A full-adversarial group goes into the stack only when a `web/` layer
  depends on it, and then as high as its dependents allow, so the layers below can land without
  it.

**Estimate.** Give wall clock and tokens at full rigor and at calibrated rigor, from the measured
run in **AGENTS.md, "Calibrating Effort"**. Review dominates CI here: a CI cycle is about three
minutes since the parallel runner.

**Print the plan** as one block: a table of groups (issues, surface, tier, stack position or
independent, base), the order, and the estimate. With `--plan`, stop here. Otherwise wait for the
caller's yes unless they passed `--merge`.

## 3. Understand each issue in the group

**REQUIRED SUB-SKILL:** invoke `recce-dev:linear-deep-dive` for the issue and stop it at step 6,
Propose Approach. This skill owns everything after: issue lifecycle, branches and merging. Its step
6 waits for confirmation; stop at the proposal instead. Its branch handling creates branches from
`main`, which is wrong for a stack layer. Write its analysis to the session scratchpad and decline
its offer to exclude `docs/plans/`: a plan written there is not for this run, and a local exclude is
invisible to everyone else.

If the issue has a `## Design reference`, load
[the design reference rules](references/design-reference.md) now, before the Mode 1 walk, and
never write its markup without having read what the section names.

Move the issue to `In Progress` when you start it. Nothing else does, and an issue left in
`Backlog` is what lets a sibling agent pick it.

Read the milestone's `Read before building` bullets that name the issue, and any ruling the issue
cites (the `DEC-*` sections of `docs/design-reading-a-session.md`, the `NUI-*` sections of
`docs/design-next-ui.md`).

**REQUIRED SUB-SKILL:** invoke `visual-review-and-fix` in `Mode 1: before development` for every
issue and let its own calibration table decide how deep to go. The acceptance criteria come out of
that walk rather than out of the issue text, because a criterion written from source can state the
wrong thing about what the reader is told. Anything it finds that predates the issue is filed. If
the walk contradicts the issue's plan, correct the issue before writing code.

If the issue carries no `journey:*` label, draft its User value brief before the walk: two
sentences, who notices and when, then the promise ID and the move from
[the promise map](../../../docs/promise-map.md#how-work-links-to-a-promise). Set `journey:*` and
`move:*` to match. At least one acceptance criterion is a property a user can see, with its own
`Verified by:` clause; when the move is `none`, the brief says instead why no user sees the
change.

**A decision issue** has no build. Make the question answerable, recommend one answer, and stop for
the ruling. It closes when the ruling is written into the documents its acceptance criteria name,
and that docs change is its layer.

## 4. Build a layer

**REQUIRED SUB-SKILL:** invoke `superpowers:test-driven-development`. Write the failing test first
and watch it fail.

Then, in the layer's worktree:

1. Run the canonical pre-PR suite from **AGENTS.md, "Pre-PR Checks"**, from there rather than from
   a copy. Give `scripts/run_tests.py` a `-j` share of the cores when another suite is running.
2. Invoke `sync-docs` in the layer that ships the behaviour, never once for the whole stack. The
   shipped `SKILL.md` and `HOW_TO_USE.md` change in the layer that ships what they describe. Never
   advance `COMPATIBILITY.md`'s `docs-synced-through` marker in a layer.
3. **REQUIRED SUB-SKILL:** invoke `visual-review-and-fix` in `Mode 2: after development`. Fix what
   this layer introduced; file what predates it with the base comparison that proves so.
4. Review the layer at the depth its tier sets, before it is submitted. Reviewing an open pull
   request costs a second CI cycle. Freeze the stack while a reviewer is reading: a restack rewrites
   the layers above under them and turns correct findings into false refutations. One correction
   round per layer is the default; after a round with several fixes, re-check against a live board,
   because fix rounds here produce about one new defect per four fixes. File what a review defers.
5. If `sync-docs`, the walk or a review changed a file, run the suite again. `test_documentation`
   asserts `SKILL.md`, `SECURITY.md` and `README.md`.
6. Make regenerated byte pins the last commit of any layer that touches `web/`:
   `python3 scripts/regen_byte_pins.py`, then `--check`. Never compute or resolve a pin by hand.

Keep CI waiting productive: once a layer is submitted, build the next layer on top of it while its
checks run.

## 5. Stack, submit and land

**Build the stack from one worktree.** `gh stack` keeps its tracking data per git directory, and a
linked worktree has its own, so a stack built across several worktrees does not exist as one. A
branch checked out in another worktree also cannot be rebased. Builders may work in their own
worktrees; remove them, or detach them, before adopting their branches.

- Layer by layer in the stack's worktree: `gh stack init --base main <branch-1>`, commit, then
  `gh stack add <branch-2>` for the next layer, and so on.
- Adopting existing branches: `gh stack init --base main <b1> <b2> <b3>`, then `gh stack rebase`
  so each layer contains the one below, resolving pins as below. `init` adopts without rebasing.

Name a layer's branch without an issue key unless the layer finishes that issue: Linear links a
branch named from `gitBranchName` to its issue, and a merge of that branch can close it.

**Submit.** Submit only layers that have been reviewed: `gh stack submit --auto --open` opens a pull
request for every unsubmitted layer. After the first submit, update existing layers with
`gh stack push`. Without `--open` new pull requests are drafts, and a
draft blocks the stack merge. `submit` writes the title and body only when it creates a pull
request, so then run `gh pr edit <n> --title "<type>(<scope>): <description>" --body-file <file>`
for each layer, with scratch files named per branch. Each body carries:

- `Implements [DRC-####](<issue url>)`, one line per issue, **only on the layer that finishes the
  issue**. A layer that delivers part of an issue says `Part of [DRC-####](<issue url>)`, because
  Linear moves an issue to Done the moment any merged pull request says it implements it.
- A `## Verification` section naming what ran and what it said.
- `Closes #NNNN` only for a real GitHub issue, one line each.

An independent group is an ordinary pull request on `main`: `gh pr create`, then land it as below.

**Fix a lower layer.** `gh stack checkout <branch-k>`, commit with `-s`, then
`gh stack rebase --upstack`. When a rebase stops on one of the three byte-pin test files, take
either side, run `python3 scripts/regen_byte_pins.py`, `git add` the result, and
`gh stack rebase --continue`. Resolve a conflict in a `web/` asset itself by hand, then regenerate.
Then check out each layer above from the bottom up and run `regen_byte_pins.py --check` and the
suite; where `--check` fails with no textual conflict, regenerate, amend that layer's pin commit and
`gh stack rebase --upstack` from it. Then `gh stack push`. Only layer k and the layers above
it re-run CI. A clean rebase can still break at runtime: grep the renamed symbols across every
layer.

**Main moved** (an independent pull request landed, or a sibling): once no review is reading the
stack, `gh stack sync`. It pushes every layer, and in a non-interactive shell it aborts on a
diverged branch rather than guessing. On a conflict,
`gh stack rebase` and resolve as above, then `gh stack push`. All layers re-run in parallel, which
costs one CI cycle, not one per layer.

**Merge only when every layer is ready:** `gh stack view --json` shows no rebase needed; every
layer's checks are green on its **current** head SHA (a run that finished before a push still
reports green); `mergeStateStatus` is `CLEAN`; and every review thread on every layer is resolved,
because the ruleset requires thread resolution and one open thread fails the whole atomic merge.
Read Copilot's inline comments, not only top-level reviews. Disposition each thread (fix it with
the lower-layer procedure, or reply and file it), then resolve it; a `BLOCKED` state with no failing
check means an open thread. Then:

```bash
gh stack merge --squash --yes
gh stack sync --prune
```

Always pass `--squash`. Without it `gh stack merge` uses your last-used method, and the ruleset
allows only squash and rebase. Squash is the repository's method: six native stacks, the largest
fifteen layers, landed this way with verified signatures and one push run on `main` per stack.

**Land part of a stack** when a higher layer is failing and its fix will take a while:
`gh stack merge <highest-green-pr> --squash --yes`. GitHub rebases and retargets the rest, which
changes their heads: `gh stack sync`, then wait for CI on the new heads before merging again.

**Never, on a stacked branch:** `gh pr merge` (it merges a layer into its parent branch, which
Linear reads as done while the code is off `main`: measured, PR #178 into a feature branch moved
DRC-4219 to Done in three seconds), `gh pr update-branch`, a plain `git rebase origin/main`,
`--delete-branch`, or the server-side "Rebase stack" button, whose commits are unsigned. A pull
request whose base is another feature branch but is not in a native stack gets closed when its base
is deleted (#251 and #252); link it with `gh stack link` or do not create it.

For an independent pull request: confirm `CLEAN` and current-head checks, then
`gh pr merge <n> --squash --delete-branch`, after removing any worktree that holds the branch. If
it is behind, `gh pr update-branch` and wait for the new run.

## 6. Reconcile every issue that landed

Only once the merge is confirmed on `origin/main`, and once per issue, in `blockedBy` order:

1. Confirm the issue is `Done` and its change is on `origin/main`. Linear's automation usually got
   there first. An issue a `Part of` layer delivered only partly stays `In Progress`; move it back
   if the automation flipped it anyway, and reconcile it only when its finishing layer lands.
2. **REQUIRED SUB-SKILL:** invoke `sync-project` for the milestone and the project overview. Take
   the issue's `What is left` line out and correct anything the merge made false. Never write a
   dated "what shipped" section; the pull request holds that.
3. If the merge changed a contract a remaining item builds on, add one bullet under the milestone's
   `## Read before building`, as `- DRC-1234: the note`, on the milestone of the item that must
   read it. Delete a bullet once every issue it names reached `Done`. `sync-project` preserves this section, but
   it rewrites from its template, so confirm the section survived step 2.
4. Check the issue's `blocks`. Move anything newly free to `Todo`, including out of `Blocked`.
5. Where the closed issue still blocks an open issue, replace the edge with `relatedTo`. Leave an
   edge between two closed issues alone: it records what waited on what.
6. If the move was `extend` or `new`, draft the promise wording change for `sync-docs` (the two
   repository copies) and `sync-project` (the Linear copy). For `keep` or `sharpen`, say no wording
   changes.

Post the receipt as a comment on the issue: all six items in order, "not applicable, because ..."
for any that did not apply, the pull request and the merge commit. A receipt names only its own
issue, because a comment naming another issue adds a `relatedTo` edge. Read the relations back
after each write; Linear can echo a stale save and lag on the next read.

## 7. Next group, or close the milestone

Tear down what the group started, scoped to what this run started: its review servers, worktrees
(before their branches), and subagents. Never bind, stop or kill a dashboard the run did not start.

Then refetch the milestone (issues move outside this session), recompute the plan, and continue. A
changed plan needs approval as in step 2.

**Discoveries.** A defect this milestone's work created, or a gap a review deferred, is filed in
this milestone with a `blocks` edge to the Verification issue, and burned in this run. A small fix
may ride the next open layer instead. A pre-existing defect is filed in the project with no
milestone and labelled `discovered-by-agent`, and the report names it.

**The Verification issue runs last,** once every other milestone issue is finished, on a live board
built from `origin/main`. It closes on its verdict comment, since a clean walk has no pull request.
Each defect it finds is fixed or filed as above.

**The milestone is complete** when every issue's state type is `completed`, `canceled` or
`duplicate`, every `completed` issue closed by a merge or a ruling has its receipt, and the
Verification issue closed last. Then invoke `sync-project` to rewrite the
milestone to its three-line complete form and clear its `Read before building` bullets, and report
the issue count, pull request count and date range.

**The milestone is blocked** when no open issue can start: name each blocker and stop.

## Parallel work

Read **AGENTS.md, "Parallel Work"** before starting a second builder, and hand its contention list
to every one.

- The `web/` stack is built serially in one worktree. Its layers depend on each other's trees.
- An independent group may run in its own worktree with its own subagent, its own review-server
  port, and a `-j` share of the cores.
- Dispatch subagents from the repository root and confirm each produced work before calling it
  running.
- A loopback-port failure under concurrent suites is contention, not a regression: rerun that module
  alone before believing it.

## Hard rules

- Never edit a version field. The Release workflow owns them.
- Never report an issue closed before its change is on `origin/main`, except a decision issue
  (closed by its ruling's docs change) and a Verification issue (closed by its verdict).
- Never merge a stack layer on its own with `gh pr merge`; land stacks with `gh stack merge --squash`.
- Never resolve a byte pin textually; regenerate from the assets.
- Never trust one page of Linear issues, or a state name instead of a state type.
- Never widen an issue's scope to make it feel complete. File the rest.
- Never promote a deferred review finding into the layer in flight when it costs another CI round.

## Why step 6 is written the way it is

Roadmap work here has repeatedly desynced when closing an issue felt like finishing: a milestone
claiming nothing had shipped after two of its items had, an item held behind a decision it no longer
needed, and a closed decision still holding a `blocks` edge on live work (PR #128's reconcile). Six
closed-to-closed edges found by the audit in PR #147 are why item 5 leaves those alone. Each was one
edit away from right. The receipt exists so an interrupted reconcile is visible to the next run.
