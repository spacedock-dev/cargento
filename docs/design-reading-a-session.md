# Reading a session against what you asked for

Cargento lets a person type what a session should achieve and what it should produce, then shows
that beside what the record says. Whether it may go further, and say something about how the two
compare, is a product question rather than an engineering one, and it was settled by four rulings
rather than by code.

This file is where those rulings live for the code to cite. They were made on the Cargento
Visibility 2x2 roadmap and their full arguments stay there, but a runtime comment cannot cite a
tracker, and the shape contract below is not background: three of its rules are built into the
producer rather than checked after it.

For what each runtime file owns, see [the module map](design-runtime-architecture.md). For what
survives a redraw, including the unsent drafts in these fields, see
[the reader-state inventory](design-reader-state.md).

## DEC-15: the floor and the overlay

Two permissions, and they are not the same permission.

The floor needs no authorisation. The words a person typed, the directive the deterministic
observer retained, the observed work evidence and the end outcome are shown side by side, with
their sources and their limits. Nothing compares them. The reader does.

The overlay is a model reading of that evidence against those words, and it happens only when the
reader asks for it. Evaluation on a cadence is refused, so there is no always on drift indicator
and nothing evaluates in the background. A verdict on whether the work met the request is refused
too, which is why the shape contract below governs something narrower than "was this met".

The ruling also asked for an evaluation rubric before automatic assessments are enabled. That
sentence is the one DEC-17 had to read carefully.

## DEC-15b: an assessment may be stored

An outcome assessment and the annotation revision it read persist in session history, so both
reopen after a restart and after the live row leaves the board. That is what makes the feature
useful the morning after rather than only while the tab is open.

The price is paid rather than avoided. Each stored field gets its own named admission in the
history allowlist, appears in the prompt derived carrier inventory, is redacted before it is
bounded, inherits the existing history bounds and retention, and is deleted by the existing forget
path. No new store, and no field admitted by implication.

One hazard was worth recording because nothing in the tree caught it, and it is now closed.
`history.py` returned a reset whenever the stored version did not equal the running build's, unlike
the dismissal store. The version bump that comes with the first admission would therefore have
discarded fourteen days of every existing user's history on upgrade, silently: the store rebuilds
itself from the next collection, so a wiped history looks like a quiet morning.

`history.READABLE_VERSIONS` is the closed set of versions the build can read. An admission bumps
`SCHEMA_VERSION` and appends the old value there. Every admission is additive, because each field
is re-validated on its own and a record written before a field existed is a record with that field
absent. A version outside the set is still refused, which is the case the reset header exists to
report.

Two fields are admitted, and five more are named without being admitted.

Admitted: `annotation_goal` and `annotation_output`, the words the reader typed, with
`annotation_revision` beside them. That is the baseline a reading is read against, and it is what
lets the baseline reopen after a restart and after the live row leaves the board. The annotation
store keeps the current annotation, bounded by a session count and a revision count; history keeps
what was true at each transition, bounded by fourteen days. Those are different questions and the
second is the one a retained assessment needs.

Admitting them cost a published-row change first, because this store may hold nothing the live
snapshot does not already serve and the allowlist admits field names rather than paths into a
mapping. The row published `annotation` as one nested object; it now publishes eight flat
`annotation_*` fields, and one helper in the bundle rebuilds the object the renderers read. A
nested carrier is also the shape the store's own tests ban for `tasks`, `subagents` and
`spacedock`, and for the same reason: a name cannot reach inside one.

The transition comparison widened with them. History appends on a change rather than on a sample,
and comparing `state` alone would have held the old words until the session happened to move again,
which makes the store's copy stale by construction.

Named and not admitted: `assessment_at`, `assessment_cutoff`, `assessment_revision_read`,
`assessment_goal_result` and `assessment_output_result`. Nothing produces a reading, so no row
serves them and the store may not hold them. The names are recorded here and in SECURITY.md so the
change that admits them does not re-argue the naming, and each still needs its own allowlist line.

## DEC-16: Cargento does not write into a session

A departure is raised to the reader and nowhere else. Cargento does not write into an agent, and
the steer box holds a note in the reader's browser rather than sending one. Automatic correction is
withheld, including when a later instruction contradicts the annotation: that is an unresolved
baseline conflict for the person to settle, not agent drift for the board to declare.

### What is detected, and what is not

Built 2026-09-10. The distinction is the whole of the block, so it is written down rather than left
in the code.

**Detected: that you gave a later direction.** A person-authored entry in the observed record whose
time is after the revision you last saved and after anything you have already settled. Both halves
are available without a model: the annotation carries an epoch, every fact carries its own, and
`nextReadingPersonAuthored` already owns the authorship question, so rule 7 and this cannot
disagree about who wrote a row.

**Not detected: whether it conflicts.** Deciding that a later instruction contradicts a typed goal
is a reading of two prose strings, which DEC-15 refused and DEC-18 permits only behind four
preconditions that are not met. So the block asks and the reader answers. A block that claimed to
have found a conflict would be the false claim this whole tab exists to avoid, and the word
conflict does not appear in anything a reader sees.

**The suppression keys on the detected superset**, not on a declared conflict. Any unsettled later
direction demotes a departure to `not verifiable from available evidence`, inside
`nextCockpitReadingCriterion` with every other rule rather than as a filter over the departures
list: filtering would leave the word `departure` rendered in the row above, which is the verdict
DRC-4511 forbids, on screen. Over-suppression is the safe direction, and the cost is a suppressed
departure on a session where the reader steered without contradicting themselves, which one click
clears.

**The answer is a settlement**, three scalars in the annotation store: when the reader answered,
what they answered through, and the revision it rested on. Not a revision field, because a revision
is immutable so an assessment citing revision 1 cannot be re-pointed. Not in the session, because
this ruling forbids that. `through` comes from the client, since the moment settled is the one the
reader was looking at, and is clamped to now so a forged value cannot disable the block forever.

**The window is the record's own.** A direction older than the tail `io.read_tail` keeps is not in
the entries and cannot be counted, so on a long session the suppression can release because the
evidence aged out rather than because the question was answered. The block states what it read
rather than implying it read everything.

## DEC-17: the shape contract

DEC-15 requires an evaluation rubric "before automatic assessments are enabled". A reader requested
reading imported that gate by citing DEC-15 as its authority, and a citation cannot be broader than
the thing it cites. So the rubric gates automatic evaluation only, and a reader requested reading is
held to a shape contract instead. A shape contract removes failure classes rather than measuring a
rate, which is why it can stand where no rate has been measured.

Seven rules:

1. Three results per constraint, a closed set: `departure`, `consistent with the evidence read`,
   `not verifiable from available evidence`.
2. `not verifiable` is the fallback whenever output is absent or unparseable.
3. A `departure` carries a resolvable citation: a named evidence entry with its type and source.
   Absence of evidence never produces one.
4. `consistent with the evidence read` is not `met` and may never be rendered as one.
5. Where a harness and an evidence type do not combine, the row states the limit. A limit is never
   a `consistent`.
6. Goal and Expected Output are separate constraints, each naming itself. Never blended.
7. Asymmetric, keyed on constraint identity so it needs no clause interpretation. Expected Output
   may return nothing but `not verifiable` when every cited entry is assistant authored, because
   self report is not evidence of a deliverable. Goal may return a `departure` on assistant authored
   evidence, because a stated change of direction is what that evidence is good for, and a
   `consistent` resting only on it must say so in its evidence line.

Rules 3, 4 and 7 are load bearing: they make `met`, an uncited departure, and a deliverable claim on
a harness with no work evidence unrenderable rather than rare.

### What the contract does not remove

A false `consistent` on the Goal constraint, resting on the agent's own narration. Its rate is
unmeasured. What bounds it is that the claim is narrow, produced once per press, never aggregated
into a count and never pushed, so exposure does not compound. That bound holds only while there is
no cadence, no aggregation and no notification, and the full rubric becomes owed the moment any of
the three changes.

### The condition on enabling, not on building

The reading is built now. The `Ask for a reading` control is not enabled until an abstention check
has run and passed: at least one recorded session per case kind DEC-15 names, across both Claude and
Codex, with a person other than whoever writes the reading prompt marking each constraint in advance
with one binary expectation. Should this abstain, or not. No severity, no expected judgement text,
no threshold. Every case marked should abstain must return `not verifiable from available evidence`.
A case marked should not abstain that abstains is recorded and does not fail, because over
abstention is the safe direction.

The check cannot be run without a producer to run it on, so a recorded pass implies one exists. That
is why the control reads one gate rather than two.

### Repeated calls

A reading is produced only in response to a discrete reader action, asserted rather than assumed,
and never on render, poll, reconnect, resume, focus change or revision save. One reading in flight
per session. No retry on failure, because a fresh press is required. Each reading is counted and the
count is shown beside the control, against the capacity surface Cargento already renders, so the
reader spends their own capacity and can see it going.

### Two arguments that were withdrawn

Recorded so nobody rebuilds them. The claim that a case set cannot be assembled before a judgement
producer exists is false: cases drawn from recorded sessions with expectations written by a person
need no producer, and only a measured threshold does. And the claim that a reader requested reading
is safe because it is attended is weak: the reader asks precisely because they cannot judge it
themselves, and DEC-15b's persistence makes the same reading unattended when it is re read later.

## DEC-18: an unasked reading is permitted, and gated on delivery first

Decided 2026-09-10 (DRC-4534), replacing DEC-15's "for now" refusal of automatic evaluation.
DEC-17 named this decision as the owner of the tension it could not resolve, and this is the answer.

Automatic evaluation is permitted. A reading you have to ask for only helps someone already looking
at the board, and the whole point is the person who set a session going and walked away.

It is refused in practice until four things are true, in order.

1. Delivery is real and recorded. DRC-4328 closes the Linux and Windows server side gap, DRC-4034
   owns the off machine lane, DRC-4540 records the outcome per raise.
2. A producer exists. DRC-4511.
3. DEC-17's abstention check has run and passed.
4. Quiet hours exist. DRC-4032.

Delivery leads rather than the rubric, and that ordering is the substance of the ruling. Measured in
this tree on the day it was decided: `notify_mac` runs one `osascript` call and records nothing
about whether the notification was shown or seen, and `native_notifier` returns a backend on darwin
alone, so Linux and Windows fall back to a browser notification that needs the dashboard tab open.
An automatic evaluation shipped against that would spend the reader's capacity unattended and raise
a departure that reaches nobody on two of three platforms, and could not afterwards say whether it
had arrived on any of them.

### What an off machine signal may carry

DEC-4 permits counts and states only in an off machine payload, never a session name, project,
title, path or request text. On the machine a departure notification can name the session and say
what departed. Off the machine it cannot, and the most it may carry is that a count changed.
DEC-18 does not lift that and did not try.

### The two amendments to the shape

Off by default behind its own switch, evaluating on an observed state change rather than per turn,
raising only a `departure` and never a `consistent`, held under quiet hours. Two things were added
to that draft.

Every raise persists the annotation revision and evidence cutoff it rested on, at raise time. By the
time it is read the annotation may be at a later revision and the evidence window has moved, so a
raise that does not carry its own baseline cannot be understood on return.

The cumulative cap is per session and per day, and exhaustion is visible on the board. The reader is
by construction not present, so "nothing departed" and "nothing was checked" must never render
alike.

### The alternative that was rejected

Automatic evaluation writing into the board only, with no push. It would have sidestepped the
notification contract, quiet hours, delivery recording and the platform gap, and it was the
recommendation put to the captain. Rejected because it gives up the capability the reopening was
about: a board only raise helps only the reader who comes back to look. It stays available as a
first slice if the delivery preconditions prove more expensive than they look.

### What still bounds the surviving failure class

DEC-17 records one class its rules do not remove: a false `consistent` on Goal resting on the
agent's own narration. What bounded it was that a reading was produced once per press, never
aggregated and never pushed. This decision breaks all three, which is why the rubric's acceptance
thresholds gate the switch defaulting to anything other than off. The case set is written in
parallel rather than after the build, because cases need no producer and only a threshold does.
DRC-4542 owns it.

One thing the ruling did not anticipate, found while filing that issue. A case set of source shaped
records is by construction a corpus of real session text, and `docs/captures/README.md` bans exactly
that from this repository: no prompt text, no tool input, no tool output, no file path, and never a
value a person or a model wrote. So where the cases live and what they may contain is settled on
DRC-4542 before any session is read, and it may need a ruling of its own. Synthesising the cases
instead is cheaper and carries no disclosure risk, but DEC-17 warns that a rubric validated on
fixtures the same pass writes is not validated, so the two pull opposite ways and the answer is
written down rather than settled by convenience.
