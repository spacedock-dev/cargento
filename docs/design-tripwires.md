# Workflow stage conditions

The [runtime map](design-runtime-architecture.md) owns module boundaries and
[SECURITY.md](../SECURITY.md#saved-workflow-stage-conditions) owns the read and persistence limits.
This document records why a stage condition needs its own evidence and latch.

## Exact workflow identity

One rule belongs to the canonical definition directory and entity-state directory pair. The
published id is SHA-256 over a versioned JSON tuple of those paths. Equal directory basenames or
entity slugs do not join two workflows; two sessions observing the same pair share one rule.
Workflow title and source-session labels distinguish the choices. If those display labels still
collide, saving is refused. Choosing the first match would bind intent to a workflow the reader
could not distinguish.

Only current entity frontmatter can establish a stage entry. Boot dispatchability and worker names
remain useful display evidence but cannot enter the evaluator. Each observation carries its slug,
stage, source `entity-state`, file write time and observation time. Initial and terminal stages
count too. The evaluator reads at most 96 entities per workflow, independently of the twelve-row
display, and reports both the evaluated count and partial coverage. It claims nothing about an
entity outside that bounded observation. If both flat and folder layouts publish the same slug,
that slug is unavailable and coverage is partial, even when one copy falls beyond the read cap.

## First sight is a baseline

Saving a stage establishes a baseline of the current observation. An entity trips the rule only
when its previous observed stage differs from the selected stage, its current stage matches, and
both its file write time and observation time have advanced. No ordering of the stage list is
used: observing build and then done does not prove a visit to review.

A restart, missing source, unknown stage, future file stamp, backwards clock, taxonomy or directory
identity change, or a gap exceeding twice the reconcile interval drops continuity. The default
gap bound is 60 seconds. Reacquisition establishes a new baseline. The absence of an observation is
never an observation of departure. A durable tripped latch survives every baseline reset.

## A latch precedes the attempt

The first qualifying entity trips the entire rule. The latch stores the observed transition and
rule revision before attempting a notification. A failed atomic store replacement leaves the old
bytes intact, retains the pending transition in process memory, and attempts no notification.
Another collection can retry that pending latch without needing the entity to repeat its entry.

A restart never replays a saved latch. This deliberately accepts a lost notification if the process
stops after persistence and before the attempt. Notifying before persistence instead would repeat
the alert after a failed write. Neither ordering can make two independent dashboard processes
exactly once; the existing last-writer-wins exposure remains disclosed.

Save with the same stage and expected revision preserves the entire rule. A changed-stage Save
creates a new revision and baseline. Rearm is the only action that rearms an unchanged condition.
The distinction was checked after an unchanged Save was found to mint a revision and silently
rearm a tripped rule. Remove also requires the expected revision and remains available without a
source. Corrupt or oversized stores refuse writes instead of replacing unreadable intent.

## What the reader can observe

Course offers the typed selector; Projects also lists saved rules whose source session disappeared.
A draft choice and an error cue survive redraw. Save and Rearm temporarily disable controls, so the
focused control must be captured before that render and restored after the final enabled render.
A newer keyboard or pointer interaction cancels that restoration to avoid stealing focus.

A dedicated rule-id and revision event identifies the alert. Browser delivery uses the existing
leader election, including polling without EventSource, and primes the first snapshot silently; follower tabs consume event identities
without replaying them on promotion. A native notifier owns the attempt when present. The delivery
record names the stage-condition lane and reports service acceptance, refusal, absence or an
unrecorded attempt. None proves a banner appeared or a person saw it.

Old browser-local tripwire notes remain inert and are not migrated. Conditions do not execute an
action, interpret free text, call a model or write into a session.
