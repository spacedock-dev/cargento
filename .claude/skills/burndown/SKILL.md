---
name: burndown
description: Work the Cargento Visibility 2x2 Roadmap one issue at a time. Picks the next issue by dependency and release row, hands the analysis to linear-deep-dive, ships it through the repository's own gate, then reconciles the issue, its milestone and the project overview after the merge. Use for "burn down the roadmap", "what should I build next", or "close out DRC-XXXX".
---

# burndown

One roadmap issue, start to finish, with the records left true afterwards.

The project is **Cargento: Visibility 2x2 Roadmap** in Linear (team `DRC`). This skill owns picking and reconciling. Everything between those two is delegated.

```
/burndown              pick the next issue and work it
/burndown DRC-4027     work this one
/burndown --pick       print the pick and the reasoning, then stop
```

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

Hand the issue to `recce-dev:linear-deep-dive` and **stop it at step 6, Propose Approach**. This skill owns step 7 onward, so let it analyse and do not let it start its own skill chain.

Use what it returns: classification, key files, acceptance criteria, risks. Do not repeat its exploration, and do not restate its rules here; issue lifecycle, branch handling and the read-skeptically discipline are all its.

If it finds the issue needs a decision nobody filed, stop. File the decision issue, link it as a blocker, and pick again. Guessing a product-identity call is how this project ended up with two issues reading as ready to build behind an unwritten policy.

## 3. Build

Test-driven, via `superpowers:test-driven-development`. Write the failing test first and watch it fail. If a test passes the moment you write it, you are testing what already works.

Then run the canonical pre-PR suite from **AGENTS.md, "Pre-PR Checks"**. Run it from there rather than from a copy. A short local copy of that list is how someone passes locally and then fails the required check.

Then `/sync-docs`, which is a step of that gate and not optional.

PR body: open with the Linear link, `Implements [DRC-####](url) — <issue title>`, and include a `## Verification` section naming what you ran and what it said. Add `Closes #NNNN` only if a mirrored GitHub issue actually exists, one line per issue, never comma separated.

## 4. Reconcile, after the merge

This is why the skill exists. Roadmap work here has repeatedly desynced: a milestone claiming nothing had shipped after two of its items did, an issue held behind a decision it no longer depended on, a decision issue still blocking work after it closed. All five steps, in order, and only once the merge is confirmed.

1. Move the issue to `Done`. Not before the merge.
2. Fix the owning milestone description wherever the merge made it false. Keep the older dated section and label it historical rather than deleting it.
3. Refresh the project overview's "As of" block. Every derived number lives there, so it is one edit.
4. Check the closed issue's `blocks`. Move anything newly free to `Todo`.
5. If the closed issue still blocks something that no longer depends on it, remove the relation. A closed issue holding a live gate reads as a real blocker to everyone.

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
