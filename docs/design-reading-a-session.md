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

No field is named yet, and that is deliberate. Nothing produces a reading, so there is no assessment
to store, and the baseline it would be read against already survives a restart in the annotation
store rather than in history. Naming fields for an object that does not exist is how a store ends up
carrying a shape nobody chose.

## DEC-16: Cargento does not write into a session

A departure is raised to the reader and nowhere else. Cargento does not write into an agent, and
the steer box holds a note in the reader's browser rather than sending one. Automatic correction is
withheld, including when a later instruction contradicts the annotation: that is an unresolved
baseline conflict for the person to settle, not agent drift for the board to declare.

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
