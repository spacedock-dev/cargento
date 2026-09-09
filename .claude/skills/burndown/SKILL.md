---
name: burndown
description: Use when working the Cargento Visibility 2x2 Roadmap, choosing what to build next, or closing out a DRC issue.
---

# burndown

One roadmap issue, start to finish, with the records left true afterwards.

The project is **Cargento: Visibility 2x2 Roadmap** in Linear (team `DRC`). This skill owns
picking and reconciling. Invoke the required supporting skills inside the current workflow;
delegating work to another agent is a separate choice and requires its own authorization.

Invoke the `burndown` skill with no argument to pick and work the next issue, with a `DRC-####`
identifier to work that issue, or with `--pick` to print the pick and its reasoning and then stop.

## Prerequisites

Picking requires an authenticated Linear capability with read access to the `DRC` team, its
projects, issues, relations, labels and milestones. A full run also requires:

- Linear write access to update issues, relations, milestones and the project overview after merge.
- The `recce-dev:linear-deep-dive`, `superpowers:test-driven-development`, `sync-docs`,
  `sync-project` and `visual-review-and-fix` skills.
- A browser automation capability, for the two `visual-review-and-fix` passes. This is the one
  required capability whose absence degrades the run rather than stopping it: say so in the report
  and name the stages that went unwalked, rather than treating the issue as reviewed.
- A design-project read capability, whenever the picked issue carries a `## Design reference`
  section. That section names the tool and the project id. Authorization is typically a slash
  command, which a dispatched agent cannot run, so an agent that hits a refusal hands it back to
  the operator rather than proceeding.
- A Git checkout that can create one branch per issue, run the canonical pre-PR suite, make
  DCO-signed commits and push to `origin`.
- GitHub access that can inspect mirrored issues, open a pull request and confirm its merge.

If a required capability is unavailable, stop before the affected read or mutation and report the
missing prerequisite. Do not substitute the stale board export for Linear or reconcile records
before a merge can be confirmed.

Stop, everywhere in this skill, means: make no further mutation, say what has already been written
to Linear and to git, name the branch, the worktree and any server or session you started, then
wait. It does not mean pick a different issue unless the step says so. The word can fire after the
issue is `In Progress` with a branch open and a review server up, so leaving that state unnamed is
how the next agent inherits it.

## 1. Pick

If the design-project read is unavailable, skip issues carrying a `## Design reference` at this
point and say so in the pick line. Discovering the refusal in step 2 wastes a deep dive, and
discovering it in step 3 wastes a branch.

Before picking anything, check that the issues closed since your last run carry a step 4 receipt
comment. One without a receipt is an interrupted reconcile: finish it at step 4 first. This check
belongs here because the filter below drops everything `Done`, so an unreconciled issue is invisible
from that point on.

Fetch the project's issues, and page until `hasNextPage` is false. The default page is 50 against
roughly 290 issues here, so one page is the recently touched slice rather than the backlog. Order by
`createdAt`, or filter by state: the default `updatedAt` order shifts under your own cursor while you
write to Linear, which is how a page-two fetch can disagree with a page-one fetch in the same session.

Drop on the state **type**, never on a remembered list of names. Drop `completed`, `canceled`,
`duplicate` and `triage`. The DRC team has eleven states and has gained them over time, so a name
list in this file goes stale silently: an earlier version of this line said there is no `In Review`,
and there is one. As of 2026-09-09 the completed types are `Done` and `Ready for Release`, so
sorting on names alone leaves a merged, unreleased issue as a live pick.

Then, in this order:

1. Drop anything with an open blocker. A decision issue that is not `Done` is still a blocker, even when its body records the call. Check `blockedBy`, not prose. Drop the `Blocked` state itself only when `blockedBy` still holds an open issue. A `Blocked` issue with no open blocker is a step 4.4 that never ran, and dropping it here is what keeps it invisible.
2. Release row: `release:r1`, then `r2`, `r3`, `later`. An issue with no `release:*` label ranks after `later` and is never dropped for lacking one. Measured 2026-09-09: 21 of 46 open issues carry no release label, and one of them, DRC-4328, is named in a milestone's `What is left`, so treating the gap as "not real work" is wrong. When a milestone names it, say so in the pick line as a triage gap rather than burying it.
3. Within that row, prefer an issue whose `move:*` label is not `none`. An issue with no move label ranks as `none` until triage labels it, so this rung only separates issues triage has already reached. Step 2 is what sets the label, which means a fresh issue cannot be discriminated here and falls through to rules 4 to 7. The labels and what they mean are in [the promise map](../../../docs/promise-map.md#how-work-links-to-a-promise).
4. Then prefer what other open issues are waiting on.
5. Then risk-adjusted impact from the issue's own score table, highest first. Skip this rung for an issue that has no panel score rather than ranking it last: whole milestones here were filed outside the workshop, and their issues say so in their own Provenance.
6. Then the smaller estimate.
7. Tie-break on state: `In Progress`, then `In Review`, then `Ready for Review`, then `Todo`, then `Backlog`.

An `In Progress`, `In Review` or `Ready for Review` pick already has work in flight, and the first three rungs of that tie-break are all of that shape. Do not re-run step 2 or open a second pull request. Find its branch from Linear's `gitBranchName` and its PR, read what has landed, and enter at step 3's landing block instead.

Move the issue to `In Progress` yourself when you start one. Nothing else does: `linear-deep-dive` owns issue lifecycle, but those rules are in its step 7 and this skill stops it at step 6. An issue left in `Backlog` while you work it is what lets a sibling agent pick the same one.

Probes and captures carry no `release:*` label and no score. Give one the earliest release row among the issues it settles, and rank it on what it unblocks rather than on a number it does not have. A probe that settles nothing in an open row is not a candidate.

Promotion, the one exception to rule 2: pull a foundation or a probe out of a later row only when something it gates sits in the row you are working. A foundation whose dependents are all `r3` and `later` does not promote yet.

Print the pick and why in one line before touching anything.

Read state from Linear only. `docs/visibility-2x2/items.json` holds the panel's scores and its `state` fields are deliberately stale, kept as the dated record of what was scored. Use it for scores, never for what is shipped. Where it and the issue's own score table disagree, the issue wins and the drift is worth a line in the pick, because the board file is a dated record and the issue is the live one.

## 2. Understand

**REQUIRED SUB-SKILL:** Invoke `recce-dev:linear-deep-dive` for the issue and stop it at step 6,
Propose Approach. This skill owns step 7 onward, so use the analysis and do not continue that
skill's own workflow.

Two carve-outs, because that skill is written for a different repository shape:

- Its step 6 ends by waiting for user confirmation. Stop **at** the proposal and carry it into the
  next step. Do not wait on an approval nobody is going to give, and do not invent one.
- Its step 5 offers to add `docs/plans` to `.git/info/exclude` if it is not already ignored. Here
  `docs/plans` is tracked and `AGENTS.md` owns it. Do not add that exclude. Write scratch analysis
  to the session scratchpad instead. The exclude is local and invisible in the repository, so the
  damage surfaces later as a plan document that silently will not stage.

Use what it returns: classification, key files, acceptance criteria, risks. Do not repeat its exploration, and do not restate its rules here; issue lifecycle, branch handling and the read-skeptically discipline are all its.

Read the owning milestone as well as the issue. Three of its sections bear on this step and nothing
else in this skill reads them. `Read before building` carries contract notes left by earlier merges,
keyed by issue ID, and sometimes a whole brief written at triage: read the bullets naming your issue
and leave the rest. `Decide before building` can hold an unanswered question your User value brief
depends on, such as which promise the work extends. `Waits on` says what the group still waits for.

If the issue carries no `journey:*` label yet, draft the stage of your User value brief before the
walk and hand it over. The walk names the promise from that label, and with none it concludes the
issue has nothing user-visible and applies the skip row of its own calibration table. The criteria
below are then sourced from a walk that did not happen.

If the issue carries a `## Design reference`, read what that section names before the walk as well.
The criteria the walk produces govern markup that step 3 then checks against the design's own copy,
so writing them before the design has been opened sources the criteria and the check differently.
The subsection below says how to read it.

**REQUIRED SUB-SKILL:** Invoke the `visual-review-and-fix` skill in its `Mode 1: before development`. Open the
surface this issue touches and use it as the reader does, before any code is written. Its own
calibration table decides how deep the walk goes and says plainly when the answer is to skip it, so
invoke it for every issue and let it choose; do not pre-judge that an issue has nothing visible.

It returns two things this step needs. The acceptance criteria below come out of that walk rather
than out of the issue text, because a criterion written from source can state the wrong thing about
what the reader is told. One recorded case produced a criterion no implementation could satisfy: it
named two files as the things to test and both had been deleted from the tree. A second was a
delegated verification that was right about the code and wrong about what the reader is told. And anything it finds that predates this issue is filed, never folded
into the branch you are about to open.

If the walk contradicts the issue's plan, that is not a defect to file. Correct the issue before any
code is written. A plan has been overturned that way here by one cheap
observation, and the observation was worth more than the feature. The `visual-review-and-fix` skill
records the same experience. Neither of us kept the issue reference, so take it as a rule rather
than as a citation.

Then write the issue's **User value** brief, two sentences as its first section: who notices this and when in their day, then the promise ID and the move, in the vocabulary of [the promise map](../../../docs/promise-map.md#how-work-links-to-a-promise). Set the `journey:*` and `move:*` labels to match. At least one acceptance criterion must be a property a user can see, with its own `Verified by:` clause; when the move is `none`, the brief says instead why no user sees this change. Inside the roadmap-burndown workflow these are triage outputs and the gate approves them before Linear is written.

### If the issue carries a Design reference

Some issues carry a `## Design reference` section, and inside it a `### Prompt to use` heading with
a fenced block beneath it. That fence is an instruction, not an illustration. Both are part of the
issue's plan.

- Read the files that section names before any markup is written. It names the tool, the project
  and the exact files, and it carries a dated staleness check because the design lives outside this
  repository and is editable. Run that check rather than trusting the paths.
- Hand the fenced prompt verbatim to whatever writes the code, including yourself. It is written to
  stand alone in a session with no other context, which is why it repeats things the issue already
  says. Summarizing it defeats the point.
- The section carries its own precedence rule for the issue, the design and the repository. That
  rule governs. Do not invent one, and do not assume the design wins because it is more specific.
- A difference between the surface today and the design is the work. It is not a defect for either
  walk to file, and Mode 1 is the one that will try: that skill's hard rule is never to promote a
  Mode 1 finding into the branch, and this is the single exception, because here the gap is the
  issue's scope. Tell it so when you invoke it. Filing the gap is how one issue turns into a
  backlog of its own scope. The
  exemption reaches only what the design deliberately changes: something the design does not
  address is still a defect, and calling it a design difference is how a real one gets waved
  through.
- A design defect the issue does not take up is out of scope. File it. Where the issue does take
  one up, it is the work, and both current examples do exactly that: one says to match a known
  compromise or overturn it deliberately, the other says the route the design gives is not good
  enough. Read the issue before filing anything the design confesses to.
- An issue with no Design reference has none. Do not go hunting, and do not borrow a sibling's.
- A section missing its file list, its precedence rule or its staleness check is incomplete, not an
  invitation. Name the missing part and hand it back. The ban on inventing a precedence rule is
  exactly a ban on filling that gap yourself.

### Decisions

When the picked issue is itself a decision, there is no build and step 3 does not apply. Make the
question answerable, recommend one answer, and stop for the ruling. The ruling recorded on the issue
is what step 4.1 treats in place of a merge, the receipt says so instead of naming a merge commit,
and the `blocks` sweep at 4.4 is the whole of the remaining work. The stop below concerns a decision
nobody filed, and does not apply to a decision issue you picked deliberately.

If it finds the issue needs a decision nobody filed, stop. File the decision issue, link it as a blocker, and pick again. Guessing a product-identity call is how this project ended up with two issues reading as ready to build behind an unwritten policy.

## 3. Build

**REQUIRED SUB-SKILL:** Invoke `superpowers:test-driven-development`. Write the failing test first
and watch it fail. If a test passes the moment you write it, you are testing what already works.

Then run the canonical pre-PR suite from **AGENTS.md, "Pre-PR Checks"**. Run it from there rather than from a copy. A short local copy of that list is how someone passes locally and then fails the required check.

Then invoke the `sync-docs` skill, which is a step of that gate and not optional.

**REQUIRED SUB-SKILL:** Invoke the `visual-review-and-fix` skill in its `Mode 2: after development`, in the
worktree, **before you push**. It re-walks what it walked in step 2 and checks the regression
classes this repository has actually shipped, including the ones a green suite cannot see. Anything
your change introduced is fixed here; anything that predates it is filed with the base comparison
that proves so.

When the issue carried a Design reference, carry the design's copy and its states into that walk
yourself and check them there. `visual-review-and-fix` has no design step and is never handed the
reference, so an instruction addressed to it is one both sides skip. A string the design specifies
and the build paraphrases is a finding, because the copy on these surfaces is what says how far the
evidence goes.

Before the push rather than after, because reviewing an open PR costs a second full CI cycle:
green, blocked, fixed, green again, measured at about fifteen minutes of waiting per PR.

PR body: open with the Linear link, `Implements [DRC-####](url) — <issue title>`, one such line per issue when the PR carries more than one, and include a `## Verification` section naming what you ran and what it said. Add `Closes #NNNN` only if a mirrored GitHub issue actually exists, one line per issue, never comma separated.

Then land it.

If `sync-docs` or the Mode 2 walk changed any file, run the suite again before you push. `SKILL.md`,
`SECURITY.md` and `README.md` are all asserted by `test_documentation`, so a docs pass can turn a
branch red after the gate you already ran on it.

Pick the review depth from **AGENTS.md, "Calibrating Effort"** rather than giving every PR the same
treatment. File what a review defers; never promote it into the PR in flight.

Before merging, confirm `mergeStateStatus` is `CLEAN` and that the green checks belong to the
current head. A run that finished before a branch update still reports green. If the branch is
behind, run `gh pr update-branch` and wait for the new run rather than reading the old one.

## 4. Reconcile, after the merge

This is why the skill exists. Roadmap work here has repeatedly desynced: a milestone claiming nothing had shipped after two of its items did, an issue held behind a decision it no longer depended on, a decision issue still blocking work after it closed. All six steps, in order, and only once the merge is confirmed.

1. Move the issue to `Done`. Not before the merge.
2. **REQUIRED SUB-SKILL:** invoke `sync-project` for the milestone and the project overview. It owns
   what those surfaces say and, more to the point, what they stop saying. Do not write a dated
   "what shipped" section into either one: the pull request is where that lives, and appending one
   per merge is how the overview reached 25,000 characters before the 2026-09-08 cleanup cut it by
   about 86 percent. The 88 percent figure in `sync-project` is the overview and the milestones
   together; do not requote it of the overview alone. Take the milestone's `What is left` line for this issue out, and correct
   anything the merge made false.
3. If the merge changed a contract a *remaining* item builds on, say so in one line under a
   `## Read before building` section, on the milestone of the item that must read it. That is not
   always the milestone of the issue you just closed. One bullet per item, keyed by its ID, as
   `- DRC-1234: the note`, so the reader in step 2 can tell which bullets are addressed to them.
   Delete a bullet once its ID reaches `Done`: nothing else prunes them, and a milestone that
   accretes them is the 25,000-character failure in miniature. This is the only build history a
   milestone keeps, and it earns its place by changing what the next builder does.

   `sync-project`'s milestone template carries this section and names it as content to preserve,
   which is what stops item 2 above from deleting it on the way past. That skill still rewrites from
   the template rather than trimming in place, and item 2 runs immediately before this one, so
   confirm the section survived before adding to it and put it back if it did not.
4. Check the closed issue's `blocks`. Move anything newly free to `Todo`.
5. If the closed issue still blocks something that no longer depends on it, remove the relation, and add
   `relatedTo` in its place so the closed evidence stays reachable from the item it unblocked. A closed
   issue holding a live gate reads as a real blocker to everyone.

   **Only when the blocked side is still open.** An edge between two closed issues gates nothing and is
   part of the record of what waited on what, so leave it. Removing those turns a satisfied dependency
   into no dependency, which is a different and less true statement. The rule exists because an audit
   found six such edges and the honest question was whether to sweep them or say why not; this is the
   why not.
6. If the issue's move was `extend` or `new`, draft the change to the promise wording. `sync-docs`
   owns the two in-repository copies and `sync-project` owns the Linear one, so hand it to both and
   land the repository half in the next docs PR. A `keep` or `sharpen` merge changes no promise
   wording; say so rather than leaving it implied.

Then report on all six, in order, and say "not applicable, because ..." for any of items 3, 5 and 6
that did not apply. Four no-ops and six no-ops are indistinguishable otherwise, and items 3 and 5 are
the two whose omission produced the evidence at the end of this file.

Post that report as a comment on the Linear issue before reporting the issue closed. It is the
receipt: it lives in the system the reconcile is about, it outlives this session, and it is what
step 1 looks for. An issue that is `Done` with no receipt is an interrupted reconcile, so resume it
at step 4 before picking anything new. The roadmap-burndown workflow requires the same receipt and
learned the ordering the hard way; see [its README](../../../docs/roadmap-burndown/README.md).

## 5. Continue or stop

Stop after one issue unless the caller asked to keep going.

Either way, tear down what this issue started first: the review server, the worktree, and any
session you delegated to. `AGENTS.md` measured thirteen surviving daemons driving the load average
to 18, and that load is what produces the loopback-port and socket-timeout failures a later run
reads as regressions. Scope the teardown to what you started.

If the caller asked to keep going, then go back to step 1 with a fresh fetch, because issues move outside this session.

## Hard rules

Never edit a version field. The tag-driven Release workflow owns them and `version-guard` fails any PR that changes one.

Never mark an issue `Done` before its PR is merged to `main`. A decision issue is the one exception, because it never has a PR: the ruling recorded on the issue is what closes it.

One branch per issue. One PR per conflict surface. These are not in tension, because two branches may land as one pull request, and **AGENTS.md, "Calibrating Effort"** owns why they often should: an extra PR costs a review, a fix round, a CI cycle, and a merge serialization that puts every sibling behind.

The one constraint that forces a split runs the other way. Exactly one PR may touch `cargento_runtime/web/`. Before opening a PR that touches it, check whether one is already in flight; if so the second issue rides that PR or waits for it. Most of this project's remaining UI work touches that directory, so this is the common case rather than the exception. Never resolve the frontend byte pins textually: recompute all three from the assets, because in a conflict each side is correct for a tree that no longer exists.

If a second problem turns up mid-issue, file it and carry on. Several issues at once means several worktrees, which is normal here and has its own failure modes: read **Parallel Work** in `AGENTS.md` before starting the second one, and hand its contention list to every builder. An agent that has not been told will report a loopback-port collision as a regression.

Never write markup for an issue carrying a `## Design reference` without having read what it names.
The section exists because the design is not in this repository and can move without warning. An
implementer who skips it ships a surface that looks finished and matches nothing.

Never trust one page of Linear issues. The default page is 50 and the project holds roughly 290.

Never widen scope to make an issue feel complete. The board's estimates assume the narrow reading.

## Why step 4 is written the way it is

Evidence, as of 2026-08-21, for anyone tempted to skip it:

C6 sat behind DEC-2 after a rewrite removed its need for one, so a 56 risk-adjusted item read as blocked. E4 and E5 read as ready to build while needing a security amendment nobody had filed. *Don't be the bottleneck* said no item had shipped after B3 and B7 both had. DEC-1 closed and kept a `blocks` edge on E7, so a closed decision was still gating live work.

Each of those was one edit away from being right and nobody made it, because closing an issue felt like finishing.

That account was written from the reconcile that produced it, in PR #128, and the six closed-to-closed edges at step 4.5 come from the audit recorded in PR #147. Linear keeps no description history, so the milestone wording described here cannot be re-read now. Treat this section as the reason for the rule rather than as figures to requote.
