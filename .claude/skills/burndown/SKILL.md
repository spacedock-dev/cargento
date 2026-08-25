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
- The `recce-dev:linear-deep-dive`, `superpowers:test-driven-development` and `sync-docs` skills.
- A Git checkout that can create one branch per issue, run the canonical pre-PR suite, make
  DCO-signed commits and push to `origin`.
- GitHub access that can inspect mirrored issues, open a pull request and confirm its merge.

If a required capability is unavailable, stop before the affected read or mutation and report the
missing prerequisite. Do not substitute the stale board export for Linear or reconcile records
before a merge can be confirmed.

## 1. Pick

Fetch the project's issues. Drop anything in `Done`, `Canceled` or `Blocked`. The DRC states are `Backlog`, `Todo`, `In Progress`, `Ready for Review`, `Blocked`, `Done`; there is no "In Review".

Then, in this order:

1. Drop anything with an open blocker. A decision issue that is not `Done` is still a blocker, even when its body records the call. Check `blockedBy`, not prose.
2. Release row: `release:r1`, then `r2`, `r3`, `later`.
3. Within that row, prefer what other open issues are waiting on.
4. Then risk-adjusted impact from the issue's own score table, highest first.
5. Then the smaller estimate.
6. Tie-break on state: `In Progress`, then `Ready for Review`, then `Todo`, then `Backlog`.

Probes and captures carry no `release:*` label and no score. Give one the earliest release row among the issues it settles, and rank it on what it unblocks rather than on a number it does not have. A probe that settles nothing in an open row is not a candidate.

Promotion, the one exception to rule 2: pull a foundation or a probe out of a later row only when something it gates sits in the row you are working. A foundation whose dependents are all `r3` and `later` does not promote yet.

Print the pick and why in one line before touching anything.

Read state from Linear only. `docs/visibility-2x2/items.json` holds the panel's scores and its `state` fields are deliberately stale, kept as the dated record of what was scored. Use it for scores, never for what is shipped.

## 2. Understand

**REQUIRED SUB-SKILL:** Invoke `recce-dev:linear-deep-dive` for the issue and stop it at step 6,
Propose Approach. This skill owns step 7 onward, so use the analysis and do not continue that
skill's own workflow.

Use what it returns: classification, key files, acceptance criteria, risks. Do not repeat its exploration, and do not restate its rules here; issue lifecycle, branch handling and the read-skeptically discipline are all its.

If it finds the issue needs a decision nobody filed, stop. File the decision issue, link it as a blocker, and pick again. Guessing a product-identity call is how this project ended up with two issues reading as ready to build behind an unwritten policy.

## 3. Build

**REQUIRED SUB-SKILL:** Invoke `superpowers:test-driven-development`. Write the failing test first
and watch it fail. If a test passes the moment you write it, you are testing what already works.

Then run the canonical pre-PR suite from **AGENTS.md, "Pre-PR Checks"**. Run it from there rather than from a copy. A short local copy of that list is how someone passes locally and then fails the required check.

Then invoke the `sync-docs` skill, which is a step of that gate and not optional.

PR body: open with the Linear link, `Implements [DRC-####](url) — <issue title>`, and include a `## Verification` section naming what you ran and what it said. Add `Closes #NNNN` only if a mirrored GitHub issue actually exists, one line per issue, never comma separated.

## 4. Reconcile, after the merge

This is why the skill exists. Roadmap work here has repeatedly desynced: a milestone claiming nothing had shipped after two of its items did, an issue held behind a decision it no longer depended on, a decision issue still blocking work after it closed. All five steps, in order, and only once the merge is confirmed.

1. Move the issue to `Done`. Not before the merge.
2. Fix the owning milestone description wherever the merge made it false. Keep the older dated section and label it historical rather than deleting it.
3. Refresh the project overview's "As of" block. Every derived number lives there, so it is one edit.
4. Check the closed issue's `blocks`. Move anything newly free to `Todo`.
5. If the closed issue still blocks something that no longer depends on it, remove the relation, and add
   `relatedTo` in its place so the closed evidence stays reachable from the item it unblocked. A closed
   issue holding a live gate reads as a real blocker to everyone.

   **Only when the blocked side is still open.** An edge between two closed issues gates nothing and is
   part of the record of what waited on what, so leave it. Removing those turns a satisfied dependency
   into no dependency, which is a different and less true statement. The rule exists because an audit
   found six such edges and the honest question was whether to sweep them or say why not; this is the
   why not.

Then report: issue worked, milestone updated, overview refreshed, what became unblocked, what is next.

## 5. Continue or stop

Stop after one issue unless the caller asked to keep going. If they did, go back to step 1 with a fresh fetch, because issues move outside this session.

## Hard rules

Never edit a version field. The tag-driven Release workflow owns them and `version-guard` fails any PR that changes one.

Never mark an issue `Done` before its PR is merged to `main`.

One issue per branch. If a second problem turns up, file it and carry on. Several issues at once means several worktrees, which is normal here and has its own failure modes: read **Parallel Work** in `AGENTS.md` before starting the second one, and hand its contention list to every builder. An agent that has not been told will report a loopback-port collision as a regression.

Never widen scope to make an issue feel complete. The board's estimates assume the narrow reading.

## Why step 4 is written the way it is

Evidence, as of 2026-08-21, for anyone tempted to skip it:

C6 sat behind DEC-2 after a rewrite removed its need for one, so a 56 risk-adjusted item read as blocked for weeks. E4 and E5 read as ready to build while needing a security amendment nobody had filed. *Don't be the bottleneck* said no item had shipped after B3 and B7 both had. DEC-1 closed and kept a `blocks` edge on E7, so a closed decision was still gating live work.

Each of those was one edit away from being right and nobody made it, because closing an issue felt like finishing.
