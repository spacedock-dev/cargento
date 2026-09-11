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

### Amended 2026-09-10: the store is the annotation store

The ruling above names session history and gives its reason in the same sentence, so both reopen
after a restart and after the live row leaves the board. Measured afterwards, the annotation store
already does both. It is bounded by two counts with no time to live, and an annotation is keyed on
harness and session id with no project, so it outlives the row by construction. History was named
before anyone checked.

A reading is stored beside the revisions it read. Nothing in the paragraph above about redaction
survives unchanged only by luck: the one model authored field goes through the same redact before
clip scrub the two typed fields do, on the way in and again on the way out, because any local
process can rewrite the file.

Two consequences, both accepted rather than discovered. The forget command deletes session history
alone and does not reach this file, so a reader who wants a model authored reading gone clears that
session, which deletes the reading with the words that produced it. And there is no fourteen day
expiry: a reading is evicted when its annotation is.

What this avoided is worth recording because the alternative looked cheap. Admitting the five
reserved names to history needed five new flat published row fields first, plus the allowlist
entries, plus the schema bump. The obvious way to write that bump refuses every store already on
disk, and one test would have caught it.

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
mapping. The row published `annotation` as one nested object; it now publishes fifteen flat
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

Rules 3 and 7 are load bearing: they make an uncited departure and a deliverable claim resting on
nothing that shows work unrenderable rather than rare. Rule 4 is weaker than it reads, and the
amendment below says so.

### Amended 2026-09-10: rule 7 asks whether an entry shows work, not who typed it

As written, rule 7 keys the Expected Output test on who wrote a cited entry, and that inverts its
own reason. The reason is that self report is not evidence of a deliverable, and a request is not
evidence of one either. Keyed on authorship, citing the reader's own words licensed a verdict about
her own deliverable while citing the actual work result demoted. Seven adversaries found it running
against the built producer; none of five reviewers reading the rule had.

The test is now whether a cited entry demonstrates work. On Claude and Codex nothing does, so
Expected Output stays not verifiable there, which is where it already was. The change only ever
narrows what may be said.

Two rules were added beside it, both from the same pass and both demoting on either constraint. A
verdict resting only on entries Cargento itself derived is this board quoting itself: an observer
snapshot is a paraphrase of the session, not evidence about it. And a `consistent` resting only on
the reader's own request is agreeing with the question, which is the shape a reader is most likely
to misread as corroboration because the words match. A departure on her own words is different and
stands: a stated change of direction is exactly what that evidence is good for.

### Amended 2026-09-10: rule 4 is a backstop and the word list has two halves

One flat list of forbidden words demoted six of eight natural departure sentences. "The tests
failed", "not done", "incomplete" are the ordinary vocabulary of saying a thing did not happen, so
the guard against reassurance was the thing hiding departures.

Success words always demote, because the model may never assert the work landed under any result.
Failure words demote only under a `consistent`, where claiming failure while agreeing with the
evidence is incoherent. A success word under a negator is a failure statement and keeps its
departure.

Rule 4's primitive is that the model emits a token rather than a sentence, and that prose renders
only under a departure. The word list is the second line and it is a judgement rather than a
measurement. Saying otherwise would be the same overstated claim the rule exists to stop the model
making.

### The two typed fields are one line each, and that is a security decision

Recorded here because it had no durable home. The goal and the expected output are collapsed to a
single line by the same control character scrub that stops a pasted private key body surviving into
a published string, and it runs server side on write and again on read back. Admitting newlines
means relaxing that scrub for two fields that a reader pastes into, which is the wrong two fields to
relax it for. The browser collapses on input as well, so the reader watches it happen rather than
finding out afterwards.

### What the contract does not remove

A false `consistent` on the Goal constraint, resting on the agent's own narration. Its rate is
unmeasured. What bounds it is that the claim is narrow, produced once per press, never aggregated
into a count and never pushed, so exposure does not compound. That bound holds only while there is
no cadence, no aggregation and no notification, and the full rubric becomes owed the moment any of
the three changes.

### The contract is built and unexercised

Recorded 2026-09-10, because a reader of this section otherwise concludes the seven rules are held
and they are not yet held against anything real.

No producer writes an assessment, and `annotations.published` emits no field for one, so
`annotation.assessment` is undefined for every row a server has ever served. About 120 lines of the
renderer, the criterion rows and the departures list among them, are reached only by tests that
inject a shape directly. Every assertion about these seven rules is therefore evidence that the
renderer is self-consistent, not that the contract is right, which is the fixture-as-specification
failure this repository has already measured once.

Whoever adds the producer adds the published field in the same change and re-derives those
assertions from it. One trap in particular: the `assessment` entry in the page's annotation rebuild
list is the only production mention of the field, and two defects on this branch have already
landed in that list. Publishing an assessment without adding it there reproduces the defect and the
suite stays green, because the fixtures bypass the rebuild.

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

#### Amended 2026-09-10: the captain marks the corpus

The second person requirement is removed. On this milestone the captain is that other person and
there is no third, so holding the check as written left the constant at not run indefinitely, the
control permanently disabled, and the promise unkept by anything the producer builds.

Three things the requirement was protecting are not relaxed, because they are what makes a mark
evidence rather than agreement. Marks are written before any producer runs against the corpus: a
mark written after seeing an output is not a mark. The corpus is recorded sessions only, and stays
separate from the synthesised case set, because sharing one would let a synthesised fixture satisfy
a gate written for recorded sessions. And cross agent verification on that case set is untouched: a
case whose generator and verifier are the same agent is not admitted.

What this costs is that the marker is also the person who wants the feature, so a mark wrong in the
permissive direction has nobody to catch it. The mitigation is the first of those three, and it is
weaker than a second reader.

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

Amended 2026-09-10: the four preconditions gate the automatic switch's default, not the
implementation. Read strictly they put three issues, two of them in another milestone, ahead of the
work on the critical path for about thirty five hours that does not change what the work is. The
delivery recording precondition stays a build gate and lands first, because a raise that records no
delivery outcome is precisely the defect the review view exists to show. Native notifications on
the other two platforms, the off machine lane, and quiet hours become follow ups that widen the
lane and, together, permit the default to change. What that accepts is a capability which on Linux
and Windows honestly reports that it cannot reach the reader, and it is defensible only while the
report stays honest, which is what the three distinct delivery states are for.

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

## DEC-19: the page may report a lane, never a delivery

Decided 2026-09-11. Cargento notifies through two independent producers. The server runs one
`osascript` call and exists on macOS alone. The page constructs a browser `Notification` and is the
only lane on Linux and Windows. They do not raise the same events, and the page reports nothing
back.

The page may now tell the server whether a notification lane exists in it: whether the browser
supports notifications, and what its permission is. On page load and on permission change, never
per raise, and carrying no session.

It may not report a delivery. Three things decided that, and the security argument was not one of
them: by this repository's own standard, which is what a forged post can suppress or mask, a
delivery report is side state of the same weight as `POST /api/notify`, which any local account can
already forge.

What decided it was that a per-raise report inflates the count by the number of open tabs, because
every tab computes the edge itself and constructs its own notification while the browser collapses
them to one banner; that it would be the first route on which the page asserts a fact about itself
rather than relaying a reader's action; and that a forged delivery is the single false statement
this milestone ranks worst, because it makes a reader's inaction read as their having ignored
something.

### The negative sentence, which is the part that is easy to get wrong

A report is stale by construction, and stale asymmetrically: a tab that opens sends one and a tab
that closes sends none. So an absence of availability means no lane has been reported since a given
moment, never that none existed when the raise happened.

The sentence says the first. It may not be tightened into the second, and the clause explaining why
is load bearing rather than decoration.

### One argument that was withdrawn

The first recommendation refused any report, on the ground that the page can only say a constructor
did not throw while the server can say what a subprocess returned. That asymmetry does not exist.
`osascript` exits zero under Do Not Disturb and with the hosting application's notifications
switched off, so a zero return means the scripting bridge accepted the call and nothing more. The
two lanes are the same strength, and a shared value name would have been defensible.
