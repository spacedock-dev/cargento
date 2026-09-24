# Reading a session against what you asked for

Cargento lets a person type what a session should achieve and what it should produce, then shows
that beside what the record says. Whether it may go further, and say something about how the two
compare, is a product question rather than an engineering one, and it was settled by four rulings
rather than by code.

This file is where those rulings live for the code to cite. They were made on the Cargento
Visibility 2x2 roadmap, now closed, and their full arguments stay on its issues, but a runtime
comment cannot cite a tracker, and the shape contract below is not background: three of its rules
are built into the producer rather than checked after it.

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

Amended 2026-09-23: a Drift mark read from a stored record is not the indicator this section
refuses, because it evaluates nothing on a cadence. [DEC-20](#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)
says why and what may show it.

### Amended 2026-09-24: a live estimate runs after every turn

[DEC-26](#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn) amends this section and its
2026-09-23 amendment. A live drift estimate is computed after every turn, which is evaluation on a
cadence, and it shows a level in the Drift section and the session header. It uses no model: it
reads the checks and file paths
[DEC-23](#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work) admits against the
reader's saved intent. The switch that shows it is off by default and lives in the browser only, so
off hides the level and the pill; it does not stop the server computing the level. The level never
reaches a row, a total, a notification or the unasked lane. The overlay is still a reading the
reader asks for, and a verdict on whether the work met the request is still refused.

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

### Amended 2026-09-12: a stored row says why it is not verifiable

A stored reading has to mean the same thing when it is read back later, and six of its demotions
did not. A constraint never put to the model, a departure the rules demoted for citing nothing,
rule 4's backstop and rule 7's three all stored as `not verifiable from available evidence` and
nothing else, which is what a model that said `unverifiable` on its own leaves behind too. Rule 2
is the exception, and it was measured rather than assumed: a reply that could not be read stores no
`result` at all, so the page tells that row apart without help. The page was right on screen, because
it derives the limit from today's harness table, and wrong in the store, because a reading re-read
after that table moved rendered a never-asked constraint as a model verdict.

Each criterion now carries `why`, a token from a closed set the producer owns: empty when the
result is the model's own, otherwise the rule that withdrew it. The page maps a token to a sentence
it already owns rather than printing it, so this field is not a second route for producer prose.
Tokens rather than sentences was the call, and it was made on the same ground the shape contract
stands on: the page's own re-derivation stays authoritative, and a stored reason fills only the gap
that derivation leaves.

This is the second downgrade cost stacked in one release, beside `revision_read_at`. Both land in
the same release on purpose: no shipped release carries either, so a reader stepping back meets one
refusal, not two. The refusal is the existing one. A build that does not know the key refuses the
reading whole, publishes `reading_refused` beside the press count, and writes the raw reading back
untouched, so stepping forward again reads it. A reading stored before the field reads back with
the reason absent, which is a reading with less in it, not a diverged one; a token this build does
not know refuses the reading whole, like every other bad value in the store.

### Amended 2026-09-24: an intent revision and a reading hold more

[DEC-24](#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
adds stored items, each taking its own admission under the rules above: a revision's window start
beside its save time (item 13), its outcome lines with each line's source (item 3, flat per-line
fields in the history copy), a reading's `evidence_through` (item 6), and a digest of each copied
correction, bounded per session (item 9). It adds one token, the reader's Not accurate mark on a
reading, stored with the annotation entry and removed with it, never sent and not reached by
`--forget` (item 10). It also changes when a reading may run: a session waiting at its prompt after
a turn stop may be read through its last turn (item 13).

The outcome lines cost a downgrade, and this one crosses a shipped release: v0.27.0 stores one
`output`. A build that old reads a revision holding lines as one with no expected output, and its
next save writes the lines away. It refuses a reading keyed by line and keeps it verbatim, as it
refuses any reading it cannot read. The owner accepted the loss on 2026-09-24. Going forward, a
revision or reading stored with one `output` reads as one typed line and is written back as lines
by the next save. The history copy carries up to six line fields where it carried one, so an
annotated session's records are larger and the size cap ages other sessions out sooner. The owner
accepted that too.

The larger store costs a second downgrade, and the owner ruled on it on 2026-09-24: the read limit
stays at 16 MiB. A build that old refuses a store over 2.5 MiB as unreadable, and its next save
writes every session's saved words away, not only the lines. This build does the opposite: a store
it cannot read whole, whether unreadable, over its limit or not JSON, is never written over, and
every save answers `untrusted` until the file is readable again, and the board says so in place
of "nothing typed". A missing store is not that state; it is empty and takes the first save. One
session's entry that this build cannot read, such as seven lines or an unknown source from a later
build, is kept as it was: it is written back unchanged, and a save, adoption or discard of that
session answers `unreadable` rather than renumbering it from revision 1.

The window start (DRC-4679) costs less, because the revision field is optional. A build without it
drops `window_start` from a revision on its next save, and that revision then opens at its save
time, which is what every build did before. A reading is different: it carries the key
`window_start` and may carry the scope token `last-turn`, and a build that knows neither refuses
the reading whole and keeps it verbatim, the existing refusal. It lands in the same release as the
outcome lines, so a reader stepping back meets that refusal once. A withheld reason this build adds
("This session stopped its turn moments ago...") reads back as no reason on an older build. The
session publishes `annotation_window_start`, a scalar time, and it is not admitted to
`history.OBSERVATION_FIELDS`: nothing in history reads it yet, so it stays out, as `settled_at`
does.

## DEC-16: Cargento does not write into a session

A departure is raised to the reader and nowhere else. Cargento does not write into an agent, and
the steer box holds a note in the reader's browser rather than sending one. Automatic correction is
withheld, including when a later instruction contradicts the annotation: that is an unresolved
baseline conflict for the person to settle, not agent drift for the board to declare.

### Amended 2026-09-24: a correction you copy, and a later direction you keep or add

[DEC-24](#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
amends this section in four places, and Cargento still writes nothing into a session. It composes a
correction without a model, from your goal, your outcome lines with their state and the cited entry
numbers and times, for you to edit and copy (item 7). Sending it into the session stays refused;
DEC-25, the follow-on that would decide that, is not ruled (DRC-4698). Before an analysis, an
unsettled later direction is still detected and not judged: "Keep my intent and analyze" settles
every one of them, as "The baseline still applies" does, and "Add it to my intent" puts the
direction's raw text into a new outcome line for review (items 4 and 8). A later message that
matches a correction you copied is not an unsettled later direction (item 9).

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

Amended 2026-09-23: [DEC-20](#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)
labels this block "Conflict to settle", decided knowing it breaks the sentence above. The label puts
a question to the reader and records no finding: what raises it is still any unsettled later
direction, the detected superset, and nothing reads whether the two strings disagree. A block that
claimed a contradiction was found remains refused.

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

#### Amended 2026-09-24: a check's own result word is not a verdict (owner ruling)

Owner ruling, 2026-09-24 (DRC-4677 review). Under
[DEC-23](#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work) item 8 the only
`consistent` Expected Output can carry rests on a cited check whose latest run passed, and the row
the model read says so in Cargento's own words ("passed, as the tool reported"). A model that
described that evidence truthfully tripped the success-word half of the backstop, so every such
reading was withdrawn as a stated verdict, and "no later write" or "not inspected" tripped the
negator half on its own. The two sentences above still hold everywhere else. For an Expected Output
`consistent` that rests on a cited check passing item 8:

1. `passed`, `passes` and `passing` are the tool's report, not a verdict, and so is "failed" when
   the cited row itself says an earlier run failed.
2. A negator counts only beside a success word that remains, so "not complete" still withdraws it
   and "no later write" does not. A negated pass word still withdraws it, read in word order before
   the pass words are set aside: "did not pass" and "no tests passed" are failure statements, and so
   is a negated "work" or "expected".
3. Every other success word still withdraws it: met, complete, verified, works, delivered and the
   rest of the list.

The prompt now asks for `detail` only under a departure, and says a check's result words are
Cargento's, so the prose the rule reads is rarer at the source. A consistent's prose is never shown,
so this adds no prose to the page. Goal verdicts and departures are unchanged.

### Amended 2026-09-12: rules 3, 4, 5 and 7 are told apart in the stored shape

The seven rules say what a row may conclude and did not say how a row records which rule
concluded it. Rule 5's limit row is told apart on the page, which derives the limit itself, and was
not told apart in the store, where the limit was never written. Rule 3's demotion of an uncited
departure, rule 4's backstop and rule 7's three stored byte-identically to a model that said
`unverifiable` on its own. Rule 2 is the one that already recorded itself, by leaving `result`
absent.

Every row now names the rule that left it without a verdict, as a token: `not-asked` for rule 5,
`unreadable` for rule 2 (a row the page still answers from its own derivation, since that token
never accompanies a result), `uncited` for rule 3, `verdict-stated` for rule 4's backstop, and
`no-work-shown`, `board-quoting-itself` and `uncorroborated` for rule 7 and the two rules added
beside it. Where more than one fires the producer records the one the page would have said, in the
page's order, so a live row and its stored copy never disagree about the reason. The contract
otherwise stands as written: the results are unchanged, the fallback for an unreadable reply is
still an absent result rather than a present one, and the token set is closed on both sides.

### Amended 2026-09-24: rules 4, 6 and 7 meet a checklist, a tool outcome and a level

Rule 6:
[DEC-24](#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
makes the Goal and each outcome line separate constraints, each naming itself and never blended, so
a reading has up to seven (item 3).

Rule 7 and its 2026-09-10 amendment: on Claude Code a check's recorded result, read under
[DEC-23](#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work), now demonstrates
work, so "On Claude and Codex nothing does" holds for Codex and for everything else on Claude Code.
A `consistent` on an outcome line needs the latest run of a relevant check passing inside the
evidence window with no later write, and says it is as the tool reported, not inspected. On an
outcome line the agent's own account still yields `not verifiable`, as rule 7 says. On the Goal, a
`consistent` resting on the agent's own account says "Consistent with what the session said at #<n>;
not a check". A message that matches a copied correction is not person-authored evidence (DEC-24
item 9).

Rule 4: [DEC-26](#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn)'s "None or low"
names a level, never `met`. Its floor for an analysis needs every outcome line `consistent` on a
tool-reported check. The live estimate says it reads checks and file paths, not what the intent
says, and the analysis says it read each line of the intent against the checks and messages it
cited. A result is never "Done" and never a check mark (DEC-24 item 6).

### The two typed fields are one line each, and that is a security decision

Recorded here because it had no durable home. The goal and the expected output are collapsed to a
single line by the same control character scrub that stops a pasted private key body surviving into
a published string, and it runs server side on write and again on read back. Admitting newlines
means relaxing that scrub for two fields that a reader pastes into, which is the wrong two fields to
relax it for. Since DEC-24 item 3 the expected output is a checklist, and each of its lines is held
to the same rule: one line, the same scrub, on write and on read back. The browser collapses on input as well, so the reader watches it happen rather than
finding out afterwards.

### What the contract does not remove

A false `consistent` on the Goal constraint, resting on the agent's own narration. Its rate is
unmeasured. What bounds it is that the claim is narrow, produced once per press, never aggregated
into a count and never pushed, so exposure does not compound. That bound holds only while there is
no cadence, no aggregation and no notification, and the full rubric becomes owed the moment any of
the three changes.

#### Amended 2026-09-24: a cadence makes the full rubric owed

[DEC-26](#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn) adds a cadence, a live
estimate after every turn, so by the paragraph above the full rubric is now owed. The measured
levels DRC-4692 validates are its first measured part.
[DEC-23](#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work) adds a second
surviving class beside this one: a false `consistent` on Expected Output resting on a success the
tool reported, which DRC-4666 qualifies the producer against. Neither level is aggregated into a
count or pushed.

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

The original ruling below was amended on 2026-09-14 to allow the captain's acceptance of the
recorded case review to enable the control.

The reading is built now. The `Ask for a reading` control (`Check for drift` since DRC-4639, `Analyze drift` once DRC-4680 ships) is not enabled until an abstention check
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

#### Amended 2026-09-14: the captain accepts the case review

After answering all twelve recorded Claude and Codex snapshots, the captain accepted that review
as sufficient to unlock reader-requested readings. That decision supersedes the requirement to
wait for a scoring run before enabling the control.

The build publishes `reading_check: "accepted"` and enables the control and its HTTP route.
`passed` remains the scorer-backed enablement state; accepting the review does not manufacture
a scoring result. The local answer key is bound to the frozen packet, and the committable
[acceptance record](abstention/acceptance.json) carries its hashes and marks without session text.

The producer's evidence and lifecycle rules, the explicit press and disclosure, and the
`--observer-model` opt-in still apply to each request. The evaluator retains its existing verdicts
and coverage rules for future scoring. This amendment concerns the reader-requested control.

Amended again 2026-09-23: [DEC-21](#dec-21-a-reading-works-the-first-time-you-ask) replaces the
`--observer-model` opt-in for reader-requested readings with a remembered first-press answer and a
daily cap, once DRC-4640 ships. The press and the disclosure still apply to each request.

#### How the check is run, 2026-09-12

Two scripts, both outside the gate and neither in CI. `scripts/mark_abstention.py --build` draws
cases from the live board into `~/.cargento/abstention-cases.json`, and its marking mode collects
the captain's `judge` or `abstain` per constraint into `~/.cargento/abstention-marks.json`.
`scripts/score_abstention.py --score` then hands each case to `reading.produce` with the two
constant yardstick sentences as a synthetic revision, through `reading.CodexReadingModel`, and
writes two halves: a local results file beside the cases, and a committable summary under
`docs/abstention/`. Where the cases live and what each file may hold is the security ruling, in
[SECURITY.md](../SECURITY.md#the-abstention-check).

Historical cases can instead use a frozen row, semantic facts and evaluation clock. This avoids
scoring today's changed or absent session against yesterday's mark. The packet is prepared before
marking; the key binds to its digest, and the producer's lifecycle rules still apply at the frozen
time. The format and procedure live in the
[abstention documentation](abstention/README.md#historical-replay-case-format-4).

Each (case, constraint) lands in exactly one of `withheld:<reason>`, `unparsed`, `abstained`,
`judged:consistent` or `judged:departure`. Withheld is its own column because the corpus this was
written against made the trap concrete: twenty of twenty three cases had an empty ledger, so the
producer refused them before any model call. Folding that into "abstained" would have reported a
producer that never abstains as one that always does, on three exercised sessions. A withheld case
counts for neither side. `unparsed` is kept apart from `abstained` because rule 2's fallback renders
the same sentence and is a different fact.

The output column is mostly the ruling's. Only a case whose record shows work is asked the Expected
Output question (`asks_output`, which reads the entries the prompt carries; the check never grants
tool output, so that is a Pi case with a work result), the collector fixes the mark to `abstain`
everywhere else, and `resolve` answers `not verifiable` there without asking. The scorer records `asks_output` per case
and the report says how many output columns were never asked, so twenty three abstentions on a
corpus with no Pi session read as the ruling's answer rather than as the model abstaining twenty
three times.

PASS therefore needs two things. No case marked should-abstain judged; a judge mark that abstains is
recorded and does not fail. And the coverage floor: at least one evidence-bearing, kind-tagged,
recorded case per DEC-15 kind, on both Claude and Codex, that reached the model. Ten, minimum. The
kind tags come from the rubric expectation file's `recorded` entries, so tagging a case after the
fact does not touch the marks. Below the floor the verdict is `short` and PASS is refused with the
shortfall printed per harness. The summary also carries the sha256 of the marks file as scored, and
a later report whose marks no longer hash to it says the marks moved and refuses PASS.

The scorer never writes to the annotation store, never posts to the reading route, and never flips
`annotations.ABSTENTION_CHECK`. The flip is a separate change, made by hand, after a run has passed
on a corpus that meets the floor or the captain has accepted the case review under the amendment
above.

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

Settled 2026-09-10, and built 2026-09-12: the cases stay local and uncommitted, only expectations
and results are committed, `records.safe_text` applies to anything synthesised, and a synthesised
case is admitted only when a different agent verified it than generated it. The rubric scores
judgement and extraction as two columns, never one. Judgement lands in one of five outcomes,
`correct`, `false-reassurance`, `false-alarm`, `missed-departure` and `over-abstention`, and the
report carries them as five counts with no composite figure, because the composite is exactly what
hides the one DEC-15 calls most damaging. Extraction is which expected citations the producer hit,
which it missed, and which it cited that were not expected. The file format and the admission rule
are in [docs/abstention/README.md](abstention/README.md); the cases and expectations themselves are
the captain's to write.

### What the build had to decide, 2026-09-11

The ruling settles the shape and leaves three choices to the implementation. All three were made
against the ruling rather than for convenience, and each is the kind of thing a later reader would
otherwise re-derive.

Two gates, not one, and they are different rules. One reading per collection is a flag on the loop
that offers rows; one reading at a time is an in-flight slot released when the worker finishes.
Relying on the slot for both was tried and reverted: it is released by the worker, so the
per-collection guarantee would rest on a `codex` subprocess outliving the loop rather than on
anything the function does. Measured with a synchronous worker, twenty candidate rows started twenty
readings.

The per-day cap counts over a rolling twenty-four hours rather than a calendar day. The reader this
exists for walked away at an arbitrary hour, so a midnight reset would hand a fresh allowance to a
board nobody is watching, and a calendar day needs a timezone this runtime does not otherwise carry.

The lane rides `record_history` rather than owning a second is-this-diagnose signal. `--diagnose` is
the one caller that says no to that flag, it runs a collection, and it must not start a subprocess
while reporting what the stores hold. A second flag meaning the same thing is the thing there must
not be two of.

Quiet hours are deferred to DRC-4032 and the switch ships off, which is what the amendment above
permits: the preconditions gate the default rather than whether the thing may be built.

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

### Three sentences, not two, and what the build had to decide

The ruling names two cases. Building it found a third, and two rules the ruling implies without
saying.

A report has a time, and the time changes what it is evidence of. A lane reported three hours before
a raise and one reported a minute before are different evidence, and a sentence that omits the gap
makes them read alike. So the positive case carries the gap, and a report that arrived after the
raise gets its own sentence saying it is about a later moment. Rendering the positive sentence with a
negative gap would have been the quiet version of the same overclaim.

Only a working lane is a report. A tab reporting that it has no lane records nothing and clears
nothing, because several tabs can be open and one without permission says nothing about another that
has it. The absence of any report is the negative sentence above, which already claims nothing either
way.

The page resends on disagreement rather than on a timer. A report lives in the server's memory, so a
restart loses it, and the page has no way to know a restart happened. The condition is that this tab
has a lane and the payload says none has been reported. That covers the first render, the permission
grant and the restart, with no heartbeat and no token for the boot.

### One argument that was withdrawn

The first recommendation refused any report, on the ground that the page can only say a constructor
did not throw while the server can say what a subprocess returned. That asymmetry does not exist.
`osascript` exits zero under Do Not Disturb and with the hosting application's notifications
switched off, so a zero return means the scripting bridge accepted the call and nothing more. The
two lanes are the same strength, and a shared value name would have been defensible.

## DEC-20: the first screen shows goal beside direction, and drift has one home

Decided 2026-09-23 (DRC-4633), on the Actions Front and Center project. DRC-4636 to DRC-4642 build
it. The session page (item 4, the session page half of item 3, and the primary control) is built by
DRC-4639 and DRC-4642. The landing view and its one screen-level sentence are built by DRC-4636,
and every session's page is one click away by DRC-4638. The row's goal slot and recorded Drift mark
are built by DRC-4637 and DRC-4641, as the amendment to
[NUI-16](design-next-ui.md#nui-16-operations-lead-observation-stays-reachable) describes.

The question was what a person sees about drift when they open Cargento. Measured on a default run
the day it was decided, the honest answer was nothing: four of four sessions had no typed goal, none
had been read, and a departure comes only from a model reading, which a default run does not make.
A first screen built from drift results would have been an empty state. So the ruling puts DEC-15's
floor on the first screen and lets a result add to it, rather than the other way round.

1. Cargento opens on Sessions. Drift belongs to a session, the journey never asks for grouping, and
   Projects caps each row's members and draws no member lines for a project whose sessions are all
   idle. NUI-3, NUI-5 and NUI-16 are amended to match.
2. Every row puts your goal beside the NOW line and leaves the comparison to you, which needs no
   model and no permission. With no typed goal, the goal slot shows the prompt DEC-22 permits,
   labelled "your latest prompt". Expected Output stays on the session page, because on Claude and
   Codex it reads not verifiable under DEC-17 rule 7 and a first screen of those would say nothing.
3. The word drift may name a mark, a section and a control. It never names a result: no surface says
   a session has no drift, because DEC-17 rule 4 forbids rendering `consistent with the evidence
   read` as met. An unsettled later instruction of yours is DEC-16's baseline question and reads
   "Conflict to settle", never Drift. The label asks; it does not say a contradiction was found.
4. Held to merges into the session view and the `held-to` slug aliases to it. A session with no
   project gets the same drift block once its page is routed, but reaching that page is a routing
   question this merge does not settle, so the dead end such a session reaches is not claimed
   removed here.

| State | Words on the row | Source record | Surfaces |
| -- | -- | -- | -- |
| A departure is on record, asked or unasked | Drift | the reading or the unasked check that raised it | first screen row, session page |
| A later instruction of yours is unsettled | Conflict to settle | DEC-16's later-direction floor | session page |
| A reading found the work consistent | none on the row | the stored reading, with its evidence line | session page only |
| Not checked | none on the row; the control offers "Check for drift" | absence of a stored reading | session page; one screen-level sentence on a default run |
| No goal typed | none on the row; the goal slot shows your latest prompt or is empty | absence of an annotation revision | first screen goal slot, session page |

The session page has at most one primary control, and it reads "Check for drift", replacing "Ask
for a reading" and the DRC-4603 ruling that held that label. A session blocked on you, by needs
input or an exact request, gives the primary to the raise when one is offered; without one nothing
is primary while the question is open, and the check sits below it as an ordinary control. The rule
is at most one primary, and none while a question is open without a raise.

### Amended 2026-09-24: the panel is Intent and drift, and the control is Analyze drift

[DEC-24](#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
and [DEC-26](#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn) amend items 2 and 3,
the state table and the primary-control paragraph.

Item 2: on the session page, a session with no saved goal shows the reader's first prompt as an
unsaved draft marked "from your prompt" (DEC-24 item 2). Expected Output becomes a checklist of up
to six lines, and on Claude Code a line may now be read against a check the session ran (DEC-23).
The row's goal slot still shows "your latest prompt": DEC-24 drafts on the session page only (item 2, as
DEC-22's 2026-09-24 amendment scopes it).

Item 3: answers name departures and never say "no drift" (DEC-24 item 1). The word drift may now
also name a level, in the Drift section and the session header pill only. "None or low" is a level
with a per-source floor, never a statement that a session has no drift, and it never reaches a row.
DEC-24 item 4 puts a question about an unsettled later direction in the Drift section. Whether it
replaces the "Conflict to settle" label for the same state is not ruled.

The state table: the "Not checked" row's control offers "Analyze drift". A level adds no words to a
row, and the Drift row mark still comes from a stored departure alone.

The primary control reads "Analyze drift", replacing "Check for drift". The rule of at most one
primary, and none while a question is open without a raise, is unchanged.

### What the session page build had to decide

Built 2026-09-23 (DRC-4639, DRC-4642). The ruling as first written said a blocked session "keeps
its answer control as the primary", and the first build read that as the first option of the first
exact request. The owner overruled that reading on 2026-09-23: no answer option is ever emphasised,
because a filled first option reads as advice to approve, and every option stays a plain control.
The primary goes to the raise that selects the waiting terminal's pane when one is offered, and
otherwise nothing on the page is primary while the question is open.

The block sits after the session's identity header rather than above it, and a blocked session's
question sits between the two, because the question outranks the check. The CURRENT ACTIVITY card is
the agent's direction beside the reader's words, moved into the block rather than copied, so the
NOW line has one renderer. The subagent rows follow the drift block, rather than sharing the
CURRENT ACTIVITY card: on a live session with 31 historical workers, those rows pushed the check
to 2019px on a 900px screen. All worker rows remain on the page.

Inside the block the check is on the first screen: the two goal fields, then the direction, then
`Check for drift` with its send disclosure beside it, then the reading, then the later-direction
block and the caveats on the typed words (the binding sentence, the discard explanation and its
button), then the departures. Measured on a live board at 1440 by 900 with a goal saved, the
button's top sat at 1010px while the disclosure stacked above it, and at 840px once the two shared a
row. The reading says it is never a verification once, in the server's disclosure, and the page's
own sentence renders only where no disclosure was published.

The way back beside a departure is the header's own resume and raise controls, drawn per departure
whatever the session's state; what is missing is said once per departures section, because a limit
repeated under every row is furniture. The raise's own caveat follows the rows it qualifies.

The departures section draws only with the unasked lane on, a departure on record, or a reading the
reader asked for, whose cutoff is printed there and nowhere else. That restores DRC-4543 on this
page: a panel on every session of a board whose switch is off is noise. Under `--no-annotations`
the check stays on the page, inert, with the annotations-off sentence as its one refusal.

### Where a drift row sorts, and why that makes no count

A session with drift on record joins the active group whatever its state, after sessions blocked on
you and before working ones. It is not counted in the `Active now` figure, which keeps NUI-16's
definition of that number. A `consistent` reading sorts exactly where not checked does.

The Sessions projection changes membership without changing the shared active-evidence model.
The mark reads stored departures only; it performs no fresh comparison. Its age comes from the
raise timestamp or the reading's `read_at`, not the time the goal was typed. Older readings carry
only an hour-and-minute stamp, so their age stays unknown. Both the store and page admit the new
optional timestamp while keeping those older records readable. A superseded revision uses the
session page's existing sentence. With annotations off, no mark or promotion is offered.

DEC-17 bounds its surviving failure class, a false `consistent` on Goal, partly by a reading never
being "aggregated into a count". Ordering rows by whether a departure is on record produces no count,
and because `consistent` neither shows on a row nor moves one, a false `consistent` gains no reach it
lacked. So the ranking is not the aggregation that would make a full rubric owed. A drift total on any
screen would be, and none is permitted.

### What DEC-15's indicator sentence now means

DEC-15 says there is no always on drift indicator. That sentence refused evaluation on a cadence, and
it still does: nothing here reads a session in the background. A Drift mark is a stored record shown
where it applies, the same kind of thing as an ended label, and it appears only after a reading the
reader asked for or the unasked lane DEC-18 permits. The skill body carries the same sentence and is
amended when DRC-4641 ships the mark, not before, because it describes the shipped product.

#### Amended 2026-09-24: an indicator on a cadence now exists, off by default

[DEC-26](#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn) amends this subsection. The
live estimate does evaluate after every turn, without a model, in the Drift section and the header
pill only. It is shown only once the reader turns its switch on, and the switch lives in the browser,
so off does not stop the server computing the level. The Drift row mark is still a stored record
shown where it applies. The skill body's cadence sentence is amended by DRC-4696 when the live
estimate ships.

## DEC-21: a reading works the first time you ask

Decided 2026-09-23 (DRC-4634). Items 1 and 2 are built by DRC-4640; item 3 by DRC-4649.
Item 4 is built and gated by DRC-4650; the amendment below records what that means. [The light harness usage bounds](../SECURITY.md#light-harness-usage-asking-a-harness-a-bounded-question)
record the current permission and producer boundaries.

On a default run the reading control tells the reader to restart the server with a flag. The press
already carries a disclosure and is already the consent a browser can give, so the startup flag was
doing a different job: it was one of the three things that stop a local process, which sends no
fetch metadata, from spending readings through a route with no capability token. Removing it is
allowed only with something that does that job instead.

1. The first press of "Check for drift" shows the reading disclosure with "Allow and check". The
   answer is kept in `~/.cargento`, so every tab and a respawned daemon agree; `--forget` clears it,
   and the session page carries the off switch. The startup flag is no longer needed for
   reader-requested readings. It still governs goal summaries, which keep their own consent.
2. A daily cap on reader-requested readings replaces the flag as the bound on a local process. It
   counts over a rolling twenty-four hours, as the unasked lane's cap does, because this runtime
   carries no timezone for a calendar day.
3. `--no-observer-model` and its alias `--no-harness-usage` refuse every model call, the unasked
   lane included. Measured the day this was decided, the unasked lane did not read the flag at all,
   so `--unasked-readings --no-harness-usage` still started Codex readings. That was a security bug
   under the bounds, not a feature, and DRC-4649 fixed it: the off switch now attaches no lane.
4. A reading runs on the session's own harness: a Claude Code session is read by Claude Code, a
   Codex session by Codex. When that harness is not installed the check falls back to the other and
   says so before the press, so session text reaches a second provider only after the page has named
   it. The Claude Code producer needs its own caller entry under the bounds and a fresh abstention
   check before it is offered (DRC-4650).
5. The unasked check stays off by default for this milestone.

This amends DEC-17's 2026-09-14 amendment, which keeps the `--observer-model` opt-in on each
request. The press, remembered answer and daily cap now supply that opt-in. The cap is twelve
actual or reserved attempts per rolling twenty-four hours, admitted atomically before launch.
Off/on and `--forget` revoke consent without erasing unexpired spend; otherwise either would be
a way to refill the budget. A known missing Codex CLI is refused before admission.

### Amended 2026-09-23: Claude Code is built and gated

DRC-4650 builds item 4 and does not offer it. The owner ruled three things on 2026-09-23.

1. The Claude Code producer has its own gate, `annotations.CLAUDE_ABSTENTION_CHECK`, recorded
   `not-run` because no eligible recorded case exists for it. While it stays there, no route,
   fallback, unasked lane, goal summary, page or forged request can offer, select or invoke it.
   Codex's 2026-09-14 `accepted` status was a review of Codex readings, so it does not open this
   gate.
2. While Claude Code is gated, Codex keeps reading a Claude Code session on a machine that has
   Codex, and the disclosure before the press names Codex and OpenAI and says Claude Code checks
   are built but not yet qualified. On a machine without Codex, "not yet qualified" is a state of
   its own, worded apart from "not installed". Once the gate passes, item 4 applies as written:
   the session's own harness first, then the other provider, disclosed before the press, and
   nothing else.
3. Qualifying the producer is DRC-4666's work, scorer included. The unasked lane and goal
   summaries stay on Codex.

One resolver, `reading_route.resolve`, decides the provider from the session's harness and this
machine. It reads each provider's gate before it looks for that provider's CLI, so a gated
provider is never even looked up. The page renders the route published for that session's
harness. The reading route resolves the route again from the payload's harness and refuses a
press that named a different provider, before it writes consent or reserves an attempt.
Permission is kept per provider, because allowing Codex to send a reader's words to OpenAI is not
allowing Claude Code to send them to Anthropic. An answer saved before the split reads as Codex's.
Turning readings off and `--forget` revoke every provider, and the twelve-attempt rolling cap is
shared, so a second provider cannot double it. If the CLI is missing at launch, or a call fails,
nothing else is tried: a fresh press is the only retry. The flags the Claude Code call runs with,
and the fact that they are CLI restrictions rather than an OS sandbox, are in
[the light harness usage bounds](../SECURITY.md#claude-code-reading-calls).

### Amended 2026-09-24: Analyze drift and Allow and analyze

[DEC-24](#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
renames item 1's labels: the first press of "Analyze drift" shows the reading disclosure with "Allow
and analyze". Where the answer is kept, what `--forget` revokes and the off switch are unchanged.
"Keep my intent and analyze" counts as the allow when the disclosure beside it has not been allowed
yet, and a cancelled analysis is a spent attempt against the cap.
[DEC-23](#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work) item 7 adds one
condition: the first reading that would send tool output needs a fresh "Allow and analyze" whose
disclosure names tool output and the receiving vendor as configured, and an answer given before that
does not cover it.

### Where the unasked default stands

The unasked check is the only model reading that finds drift nobody went looking for. DEC-18 gates its
default on four preconditions and on the rubric's acceptance thresholds. Measured 2026-09-23:

| Precondition | State | Settled by |
| -- | -- | -- |
| Native delivery on Linux and Windows | not met | `notifications.native_notifier` returns a backend on darwin only; DRC-4328 |
| The off machine lane | built | #356, DRC-4034 |
| A delivery outcome recorded per raise | built | #320, DRC-4540 |
| A producer exists | met | `unasked.Lane` and `reading.CodexReadingModel`, DRC-4511 |
| DEC-17's abstention check has run and passed | not met | the check is `accepted` (2026-09-14), not `passed`; [docs/abstention](abstention/README.md) holds the acceptance record and no scorer result |
| Quiet hours exist | met | #357, DRC-4032 |
| The rubric's acceptance thresholds | not written | DRC-4542 owns the case set; no threshold exists to meet |

Two rows are not met and one cannot be met until someone writes it. That is the list this ruling
leaves open.

## DEC-22: your own prompt may become your goal

Decided 2026-09-23 (DRC-4635). Built by DRC-4643: the annotation store keeps typed and explicitly
adopted words with their source.

Most sessions have no goal from the reader, so there is nothing to check drift against. The fastest
goal is the one the reader already gave the agent. Existing rulings settle what may not be adopted:
text the agent wrote is DEC-17's surviving failure class by construction, and an observer goal is
derived the way the observer snapshot is, which the rule 7 amendment calls "a paraphrase of the
session, not evidence about it", and a paraphrase is no better as a baseline. Workflow goals are refused too, because who wrote one is mixed and they
join on newlines where the typed fields are one line each.

1. The reader's latest prompt or first prompt may be adopted. The latest is what the board already
   shows: on Claude the `asked` instruction, the first line of the newest prompt clipped to 140
   characters; on Codex the published title, only when `states_work` accepts it, because Codex titles
   a bare continuation too. The first prompt is a new published field on both harnesses, admitted to
   the history prompt-text allowlist with its own reason.
2. On a session with no goal, "Check for drift" adopts the prompt the goal slot shows and checks
   against it, so the path is one press. Choosing the first prompt, or adopting without checking, is
   in the goal field.
3. An adopted revision stores its source prompt's time beside the save time, and DEC-16's
   later-instruction floor and reading eligibility key on the source time. Both keyed on the save
   time when this was decided, so adopting a first prompt would have settled every later instruction
   silently, and adopting on an ended session would have withheld the reading with a false reason.
   Codex now publishes the timestamp paired with its latest and first prompts. A missing or
   invalid source time still refuses adoption with a sentence saying why.
4. The mark, "from your prompt", shows in the goal's source line, in the reading's evidence line and
   in one sentence of the board-wide disclosure. Editing adopted words makes an ordinary typed
   revision, because the reader has then typed them.
5. Adopted words do not make a session eligible for the unasked lane, so one press on many rows
   cannot quietly widen what that lane spends.

Authorship is inferred, not proven. A prompt counts as the reader's because the harness recorded it
as a user message and the injected-prompt filter did not recognise it, and that filter fails open. A
dispatch prompt from an orchestrator or a headless run also arrives as a user message. The mark
exists so a reading against adopted words says where they came from.

A source token and a source time are new published fields and take the three hand declarations
AGENTS.md's Measured Invariants names. They need a DEC-15b admission only if the history copy keeps
provenance. The first prompt needs the allowlist admission above whatever else is decided.

### What prompt adoption preserves

The server accepts a closed latest/first choice and the displayed text/time pair, then resolves
that pair from its own row. A changed pair refuses rather than choosing new words silently.
Implicit adoption refuses an existing goal; an explicit first/latest choice also compares the
saved revision. Save time remains the time of the reader's act. Source time controls the later
direction floor and final-reading eligibility. The assessment carries its own source even after
its revision is evicted. Output-only edits preserve goal provenance; explicitly saving a goal
makes a typed revision even when the letters match. No adopted current goal enters the unasked
lane, including one with typed output or older typed revisions.

First prompts are bounded published excerpts, not full transcripts. The first-record scan reads
at most two MiB, refuses an unread prefix, and never calls a later record the first. Both source
controls show the excerpt before adoption; clipped sources are named as excerpts. The same
annotation scrub and 240-character bound apply on save.


### Amended 2026-09-24: the session page drafts from your first prompt

[DEC-24](#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
amends items 2 and 3. On a session with no saved goal, the session page's goal field shows your
first prompt as a draft marked "from your prompt", and pressing Analyze drift adopts that draft in
the same press. The evidence window of adopted words starts at their source time. A message that
matches a correction you copied is never adopted as a goal.

## DEC-23: a Claude Code session's record of its checks may show the work

Decided 2026-09-24 (DRC-4674). DRC-4676 builds the record and keeps it off every model prompt.
DRC-4677 builds items 7 to 10 for the single Expected Output constraint: the tool-output grant keyed
by provider and destination, the destination named or refused, the result-bearing prompt row with
its output tail quoted as data, the reader's words reserved first in the byte bound, and item 8's
rules in the resolver and on the page, with the window read from the revision's stored window start
(DEC-24 item 13, built by DRC-4679), or from its `baseline_at` on a revision saved before it stored one. A pass that a later command may have changed files after, in
the same call or a later one, carries no `consistent` either (item 3's blocker, applied to a
reading). What counts as work is per harness: a work result on Pi and a check on Claude Code, and
never the agent's own final answer on Claude Code or Codex; on Pi the harness publishes its result as
work. Per-line outcome lines are DRC-4685's. SECURITY.md's
[Tool output in a Claude Code reading](../SECURITY.md#tool-output-in-a-claude-code-reading) says
what is sent and where.

A Claude Code reader who asks whether the session did what they asked gets "not verifiable" every
time, because the rule 7 amendment found that on Claude and Codex nothing in the record
demonstrates work. The Claude transcript does record every tool call and its result, and
`records.tool_outcome` already joins a call to its result by id and keeps the name only. DEC-5 let
the after-tool hook post a shape identifier and a tool name and nothing more. Pi, the one harness
whose record shows work, publishes only a derived count of validation checks passed, with no
command or output (`project_context._work_evidence`).

The ruling is yes, bounded, and readable by a model. Two other answers were put beside it. Page
only, never sent to a model, shows the work but leaves no reading able to judge Expected Output on
Claude Code. Refusing leaves every check on a Claude Code session not verifiable. What the ruling
costs is a new content class that leaves the machine under the destination rule in item 7, and a
new surviving failure class: a false `consistent` resting on a success the tool reported. DRC-4666
qualifies the producer against it.

1. Three things are never conflated: what was run, what the harness recorded as its result, and
   whether the requested outcome exists, which Cargento never claims. Evidence is the recorded
   result. A background launch is not a success, and an absent or malformed error flag is unknown,
   never success. `records.tool_outcome` turns an absent flag into `False` today, and that is the
   reading this item refuses.
2. A check's result comes from one of three sources, in this order, and otherwise reads "ran,
   result not recorded". First, the harness's explicit error flag, which is the whole call's status
   and is attributed as the closed lists set out: a pipe into `tail`, `head` or `grep` reports the
   last stage. Second,
   a runner summary line in the recorded output tail, from the closed set below. Third, for failure
   only, a failure marker in the recorded output tail, from the closed set below, which may record
   a failure and never a pass. Output text is never read as success any other way.
3. A check is a shell command whose runner is on the closed list below, matched per segment, split on
   `&&`, `||`, `;`, `|`, `&` and newlines, after stripping `cd ...`, `NAME=value` assignments and the wrappers the list names.
   The shell's `test` and `[` builtins are never checks. Among shell commands, only checks can
   support a departure or be cited in a correction (DEC-24 item 7); a person's or the agent's own
   words keep what DEC-17 and DEC-24 items 6 and 9 let them support. Other commands and probes, such as a
   `grep` with no match or an `ls` of a missing path, are counted and not listed. A segment that is
   neither a check nor on the closed read-only list below may change files without the transcript
   recording a write, so one run after any check's latest passing run blocks the live estimate's
   "None or low" (DEC-26 item 1). It is never counted as drift. The owner ruled this on review the same day,
   as part of this ruling.
4. For each distinct check only its latest run is listed and counts, and it says when an earlier
   run of the same check failed without listing that run. A file write after a passing run marks
   that pass as before the last change. At most 12 entries are listed, chosen in this order: latest
   runs that failed, then latest runs with no recorded result, then latest runs that passed, then
   written paths, newest first within each. The rest are counted ("and N more"). Every answer about
   checks is derived from the full scan, never from the listed entries alone, so a dropped entry
   can never produce "No check was recorded" or a reassuring answer.
5. Fields read: the check's own segment, its runner form and arguments and never the rest of the
   shell line (the owner narrowed this on review the same day, as part of this ruling), after
   credential redaction and masking, word by word, of the forms redaction cannot recognise: a
   `NAME=value` assignment; the value after `--password`, `--token`, `--api-key`, `--secret`,
   `--auth`, `-p` or `-P`, joined by `=` or in the next word; an `Authorization:` or `X-Api-Key:`
   header value; and the password in `user:password@`, up to the last `@`. These forms and no
   others, as SECURITY.md says. A substituted command is shown as `$(…)` and a trailing comment is
   dropped. Clipped to 120 characters; the last 180 characters of
   output, the existing ledger cap, with redaction run over the whole read window first; a
   written path relative to the working directory; and, for a segment that is neither a check nor
   on the read-only list, its time only, never its text, used on this machine. No file content is read as a field, and never an
   Edit or Write result body; the output tail is whatever the runner printed.
6. Where it lives: the observed record only, as a new fact type the reading counts as work. It is
   kept out of the semantic history store and out of every session row field, and it is named in
   `history.PROMPT_DERIVED_CARRIERS`. SECURITY.md adds it to the named reads, moving the count
   `test_documentation` pins, and scopes the irreversible-actions sentence about tool output.
7. Where it may go: to the reading producer that reads the session, or to the fallback route
   `reading_route.resolve` selects and discloses before the press, and on either only after a fresh
   "Allow and analyze" (DEC-21's "Allow and check" as DEC-24 item 5 renames it) whose disclosure
   names tool output and the receiving vendor. An answer given before tool output was named does not
   cover it. The disclosure names the destination as configured, including an `ANTHROPIC_BASE_URL`,
   Bedrock or Vertex setting in the daemon's environment or in managed settings, which still apply
   under `--restricted`. Where the destination cannot be named, tool output is not sent. Those
   settings are examples, and SECURITY.md names the Codex route's equivalent. The live drift
   estimate (DEC-26) is a further consumer on the machine: it derives a level from these facts,
   published on the session payload only, never on a row, in history or in any off-machine payload.
8. What a reading may conclude. The latest run of a relevant check failing inside the evidence
   window may support a departure. A `consistent` on Expected Output needs the latest run of a
   relevant check passing inside the window with no later write, and is labelled as reported by the
   tool, not inspected. Absence supports neither. DEC-24 item 13 sets the evidence window.
9. Tool output is quoted into the reading's prompt as untrusted data, never into an instruction
   Cargento writes.
10. The unasked lane never receives tool outcomes until DEC-18's rubric thresholds exist.

This amends the rule 7 amendment of 2026-09-10, whose "On Claude and Codex nothing does" no longer
holds for a Claude Code check; DEC-17 carries the amendment.

### The closed lists

Writing these lists out is part of item 3, which names the kinds (test, build, lint and type-check
runners) and leaves the list to this section. Each segment, split on `&&`, `||`, `;`, `|`, `&` and newlines, is matched
after stripping `cd ...`, `NAME=value` assignments and the wrappers `uv run`, `poetry run`,
`pipenv run`, `npx`, `pnpm exec`, `bunx`, `timeout N`, `time` and `rtk`. The list is closed: a runner not
named here is not a check. The owner ruled `rtk` a wrapper on 2026-09-24, with one rule of its own:
because rtk may rewrite a runner's output, a check it wraps takes its result from the error flag
only, never from a summary line or a failure marker.

Runners, matched on the first word or words of a stripped segment:

- Test: `pytest`, `py.test`, `python -m pytest`, `python3 -m pytest`, `python -m unittest`,
  `python3 -m unittest`, `nose2`, `tox`, `nox`, `node --test`, `npm test`, `npm run test`,
  `pnpm test`, `pnpm run test`, `yarn test`, `bun test`, `deno test`, `jest`, `vitest`, `mocha`,
  `go test`, `cargo test`, `cargo nextest`, `mvn test`, `gradle test`, `./gradlew test`,
  `dotnet test`, `rspec`, `bundle exec rspec`, `rake test`, `phpunit`, `swift test`, `ctest`,
  `make test`, `make check`, and a program file whose name holds `test` or `tests` as a word of its
  own, with the name split on `_`, `-` and `.`: `run_tests.py`, `./test.sh` and
  `python3 scripts/run_tests.py` count, and `runtests.py` and `fetch_latest_creds.py` do not. Never
  the shell's `test` or `[` builtins.
- Build: `npm run build`, `pnpm build`, `pnpm run build`, `yarn build`, `bun run build`,
  `cargo build`, `go build`, `make build`, `mvn package`, `gradle build`, `./gradlew build`,
  `dotnet build`, `swift build`, `vite build`, and `tsc` without `--noEmit`.
- Lint: `ruff check`, `ruff format --check`, `flake8`, `pylint`, `black --check`, `eslint`,
  `prettier --check`, `stylelint`, `golangci-lint`, `cargo clippy`, `rubocop`, `shellcheck`.
- Type-check: `mypy`, `pyright`, `tsc --noEmit`, `cargo check`, `go vet`.

Read-only commands, matched the same way, for segments that are not checks: `git status`,
`git log`, `git diff`, `git show`, `ls`, `cat`, `head`, `tail`, `grep`, `rg`, `find`, `wc`, `pwd`,
`echo`, `which`, `file`, `stat`, `tree` and `less`. Any other segment that is not a check, run after
any check's latest passing run, is the blocker item 3 names. This list is closed too. A segment is
not read-only, whatever its command, when it holds a command substitution (`$(` or a backtick), a
process substitution, or a redirect `>` into anything but `/dev/null` or another descriptor, or a
writing option: `find -delete`, `-exec`, `-execdir`, `-ok`, `-fprint`, `-fprint0`, `-fprintf` or
`-fls`, `tree -o`, and `git diff`, `git log` or `git show` with `--output`.

Formatters and fixers are changes: `prettier --write`, `black` without `--check`, `ruff format`
without `--check`, and any run with `--fix` or `--write`, `ruff check --fix` and `eslint --fix`
among them. A change ages every earlier pass as a recorded write does, and a check that fixes, or a
fixer later in the same call, ages that check's own pass, so no timestamp tie inside one call hides
it.

The error flag, source (i), is the status of the whole call, not of one segment. The orchestrator
clarified how it is attributed on 2026-09-24, in the withholding direction, after review found a
failure credited to a check that never ran and a pass credited to one whose execution was unknown:

- a passing flag with only `&&` joiners in the call passes every check in it, because a chain of
  `&&` that exits zero ran every stage and each exited zero;
- a passing flag otherwise speaks only for a check that is the last segment of the call;
- a failing flag is attributed only to a check that is the last segment of the call, and every
  other check in that call reads "ran, result not recorded";
- summary lines and failure markers attribute only when the call holds exactly one check;
- anything after `||` has unestablished execution, so the flag says nothing about it and it reads
  "ran, result not recorded";
- `&` sends the whole `&&`/`||` list before it to the background, back to the previous `;`,
  newline or `&`, so `pytest && echo started &` runs pytest in the background.

The orchestrator clarified the attribution further on 2026-09-24, in the withholding direction,
after a verifier reproduced false results against the first clarification:

- a result Claude Code records as moved to the background ("Command running in background with
  ID", or "Command did not complete within its N s timeout and was moved to the background") makes
  every check in that call a background run: no result, and it supersedes as unrecorded;
- a failing flag is a run that exited nonzero only when the result opens `Exit code N` with N above
  zero; any other failing result is a call that never ran (a rejection, a cancelled parallel call, a
  sibling error, a hook block or an input error), so it is no run, is not listed and supersedes
  nothing;
- a failing flag is attributed only when the call holds exactly one segment after stripping `cd`,
  assignments and wrappers; otherwise every check in it reads "ran, result not recorded";
- summary lines and failure markers attribute only when the call holds exactly one check,
  background ones counted, and no other segment that is not read-only;
- beside a passing flag, only a failure summary line makes the check failed; a failure marker alone
  makes it "ran, result not recorded";
- an `rtk` check with a passing flag and failure text in its output reads "ran, result not
  recorded", never passed.

Summary lines, source (ii), read from the recorded output tail, may record a pass or a failure:
pytest's `N passed`, `N failed` and `N error` or `N errors`; unittest's `OK`, only as the whole line, and `FAILED (`; jest's
and vitest's `Tests:` line with its passed and failed counts; node's `ℹ pass N` and `ℹ fail N`
lines, where `ℹ fail 0` is a pass; cargo's `test result: ok` and `test result: FAILED`; mypy's
`Success: no issues found` and `Found N errors`; ruff's `All checks passed!` and `Found N errors`.
A pass needs a pass pattern and nothing in the same tail that records a failure: a failed count
above zero, a failure summary or a failure marker. So `1 failed, 9 passed` is a failure. go prints
`ok  <pkg>` once per package, so a later package's `ok` cannot vouch for the run, and it is never
read as a pass. go's `FAIL` is a failure, and a go pass comes from the error flag alone. ruff's
`Found N error (N fixed, 0 remaining)` after a fix is not a failure summary, and neither is
eslint's `(0 errors, N warnings)`. A pass whose count
is zero (`ℹ pass 0`, `0 passed`, `Ran 0 tests`), or a go run reporting `[no tests to run]`, or
`[no test files]` with no package reporting `ok`, reads "ran, result not recorded". Failure evidence
outranks a passing flag: when the flag passes and the tail holds a failure summary, the check
failed, since a script can swallow its runner's exit status; a failure marker alone withholds the
pass instead.

Failure markers, source (iii), read from the recorded output tail as evidence of failure only:
node's `✖` test lines, `failing tests:` and `ℹ cancelled N` above zero (a timed-out test prints
`ℹ fail 0` beside it and exits 1), `AssertionError`, `ERR_ASSERTION`, pytest's `FAILED ` and `ERROR `,
go's `--- FAIL:`, cargo's `panicked at`, and tsc's `error TS`. tsc prints nothing on success, so
its pass comes only from the error flag.

The owner settled these points on review the same day, as part of the ruling rather than as an
amendment: a program file counts only when `test` or `tests` stands alone as a word in its name; a
summary-line pass counts only when nothing in the same tail records a failure, a go pass comes only
from the error flag, and unittest's `OK` counts only as the whole line; and the read-only list above.
The orchestrator added, on review the same day and in the withholding direction: the error-flag
attribution above, failure evidence outranking a passing flag, node's `ℹ cancelled N`, and go's
`[no test files]`. The owner added `rtk` as a wrapper whose checks read the flag alone.

### What was measured before the text was fixed

On this repository's own transcripts, measured 2026-09-24, 775 of 848 test and lint runs were piped
and 1 set `pipefail`. That is why the error flag counts only when the runner is the final stage. A
list that matched only a command's leading form found 14 of 941 real check invocations, which is
why a check is matched per segment after stripping.

Five recorded Claude Code sessions the same day (Haiku 4.5; the session ids are on DRC-4673)
changed the ruling twice. Node's test runner prints its summary in its own form, so that form joined
the summary set. And a failing `node --test 2>&1 | tail -20` was recorded with the error flag
false. Node prints its failure details after its summary, so `tail` cut the summary line out, and
the last 180 characters held only the assertion object (`code: 'ERR_ASSERTION'`, `actual`,
`expected`). Under the flag and the summary line alone that run reads "ran, result not recorded",
never a failure; unpiped, the same failure sets the flag. The failure markers were added for it, and
because a marker can only record a failure, it cannot produce a false pass.

The same sessions confirmed item 1. A background launch records only a "will notify" result, and its
output is read later through a file Read, so it is never a recorded result. The field names these
readings rely on are in
[the transcript capture](captures/claude/transcript-tool-shapes-2.1.281-macos.jsonl). It also shows
the limit on writes: a shell command's result records its command and output and no path, so a
written path comes only from a file-write tool call, and a file a shell command changes is not a
recorded write.

### Amended 2026-09-24: the live estimate reads these facts on the machine

[DEC-26](#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn) amends items 6 and 7. The
drift level is a derived state of the tool-outcome facts. It is published on the session payload
only, never on a row, in history or in an off-machine payload, and item 6's rule that nothing enters
a row field or the semantic history store holds for the level as it does for the facts.

## DEC-24: your intent is a drafted goal and a checklist, and a correction is yours to copy

Decided 2026-09-24 (DRC-4675). It brings the Session Drift Detection design's option C, "Unified
intent and drift panel", into the rulings. The panel is built by DRC-4680, the copied-correction
route by DRC-4678, Cancel by DRC-4693, Steer back by DRC-4681 and Update intent instead by
DRC-4697, among the milestone's other layers.

A reader who opens a session to see whether it drifted meets DRIFT, GOAL and EXPECTED OUTPUT, empty
fields, and a result that says "0 departures" beside "raised nothing and confirmed nothing". This
decides the words, the intent, the answer, when an analysis may run, and what Cargento may hand
back.

The owner ruled four things first. The goal is drafted from the reader's first prompt. The expected
outcome is a checklist the reader writes, and nothing is inferred for it. Copy, not Send. Claude
Code only: other harnesses show the panel with a stated limit. The drift level is its own decision,
[DEC-26](#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn).

The ruling is the full shape below. The two alternatives were the words and the checklist with no
correction, and today's shape unchanged. What it costs: amendments to DEC-15b's eligibility,
DEC-16, DEC-17 rules 6 and 7, DEC-20 (item 2, its control label and its primary-control paragraph),
DEC-21 item 1, SECURITY.md's reader-requested section (labels "Analyze drift" / "Allow and
analyze") and DEC-22; new stored items (a revision's window start, its outcome lines with each
line's source, a reading's `evidence_through`, a digest of each copied correction) and one new
token, a reader's "not accurate" mark; and reader edits inside a copied correction are exempt from
the later-direction floor (item 9).

1. Words. The panel is "Intent and drift": an "Intent" section (Goal, Expected outcome) and a
   "Drift" section. The action is "Analyze drift", replacing DEC-20's "Check for drift". Answers
   name departures, never "no drift": "Departs from your intent", "Can't tell", "Nothing found
   against what it read". The attempt count stays beside the control.
2. The goal draft. On a session with no saved goal, the goal field shows the reader's first prompt
   as Cargento publishes it (one line, a clipped excerpt marked as such), marked "from your
   prompt", unsaved. "Looks right" saves it; an edit saves it as typed; pressing Analyze drift
   adopts it in the same press (DEC-22). Nothing is inferred for the expected outcome.
3. The checklist. The expected outcome is up to six lines the reader types, each at most 240
   characters and one line, each read and shown as its own constraint under DEC-17's rules. Each
   line records its source: typed, or added from entry #n. The bounds, fixed by DRC-4685, the layer
   that first stores and sends outcome lines:
   - The store holds 6 lines of at most 240 characters on each revision. A seventh line, or a line
     over 240 characters, is refused rather than clipped. The store's read limit is 16 MiB, and a
     write trims the least recently written entries until the file fits, so the next read reads
     what the write kept (owner, 2026-09-24). The entry being written is never the one trimmed:
     when it cannot fit even alone, nothing is written and the save answers `unwritable`.
   - The history copy is one flat field per line, at most 256 characters each, with a closed
     source token beside it and no entry id.
   - The goal and the lines take at most 9,216 of 16,384 bytes of the prompt. Over that share,
     every line is dropped together as not asked, never some of them.
   - The reply cap is 8,192 bytes, and a reply cut at the cap keeps each answer that arrived
     whole.
   - The annotation request body cap is 12,288 bytes. The widest body the page can send is a
     goal and six lines pasted as control characters, which the browser writes as six bytes each
     before the store collapses them: 10,238 bytes with a 64-character session id.
4. A later direction before an analysis. When the record holds an unsettled later direction of the
   reader's, the Drift section asks before the press, naming how many are unsettled. For one it
   says "You gave a later direction at #<n>: "<first line>"."; for several, "You gave <N> later
   directions since saving your intent, the latest at #<n>: "<first line>"." Then it offers "Keep
   my intent and analyze" or "Add it to my intent". Keep settles all of them (DEC-16's "The
   baseline still applies") and analyzes in one press, and counts as "Allow" where the disclosure
   beside it has not been allowed yet. Add opens a new outcome line holding the direction's raw text
   for review. A direction over 240 characters or on several lines is edited by the reader to one
   line before saving, and never saved as a summary. When six lines exist, the reader replaces or
   merges an existing line, and a seventh line is refused with a sentence saying why. The goal is
   kept.
5. Background analysis. Analyze drift starts a job the server owns: a job id; phases that match
   real work ("Preparing what is sent", "Waiting for <provider>", "Checking the reply"), published
   over the existing push so a reload keeps them; and Cancel. The call runs in its own process
   group (a Job Object on Windows), so Cancel never signals the daemon's group. Cancel kills that
   group, releases the one-in-flight slot only after the child is reaped and its temporary files
   are removed, records a "cancelled" withheld reason as a spent attempt, and discards a reply that
   arrives after it. The hint under the button says what is read ("Reads the session up to
   <cutoff> against your intent. Runs in the background.") and carries the DEC-21 disclosure. The
   button reads "Allow and analyze" until allowed.
6. The result. Per line: "Departs at #<n>" with its cited evidence, only for a valid departure. A
   consistent line names its source by the cited entry's type: "Consistent with #<n>, as the tool
   reported; not inspected" for a tool outcome, "Consistent with what the session said at #<n>; not
   a check" for the agent's own account, on the Goal only: on an outcome line the agent's own
   account yields `not verifiable` (DEC-17 rule 7). Never "Done" and never a check mark. Otherwise
   "Can't tell: nothing recorded shows this yet". A headline and short account render only under a departure,
   built from departure detail with its citations. "Where the work went" groups written paths by
   folder without a model. The session's activity flags each entry a departure cites ("Cited") and
   a later direction ("A later direction you gave"). A reading stores `evidence_through`, and it is
   stale when the intent revision or the evidence after that time changes: "Your intent changed
   after this analysis" or "New work since this analysis", each with "Analyze again".
7. Steer back. The server composes a correction without a model, from these fields only: the goal,
   each outcome line with its state, and the cited entry numbers and times. No model prose, no tool
   output, and no recorded command as an instruction. It is editable before copying, at most 2,000
   characters, and offered from an analysis and, with no analysis, from the recorded facts (a
   failed check, a later direction). Copy only, and the panel uses Copy-only wording where the
   design had a Send hint. Sending it into the session is DEC-25, a follow-on that is not ruled
   (DRC-4698).
8. Update intent instead. It opens Intent for editing and offers the later direction as a new
   outcome line under item 4's rules. It never replaces the goal.
9. A copied correction coming back. The server records a digest of the exact text the reader
   copied, edited or not, per session: bounded per session, one use per digest, matched only after
   the copy. The Claude collector computes each user message's digest from its raw text before any
   clipping. A later message that matches exactly is Cargento-assisted: not adopted as the goal,
   not person-authored evidence, and not an unsettled later direction. No match, no special
   treatment. SECURITY.md names the route and its local-process residual.
10. Not accurate. A token the reader can set on a reading, stored with the annotation entry and
    removed with it. `--forget` does not reach it. It is never sent, never counted and never entered
    into abstention marks, and SECURITY.md notes it.
11. Numbering. The activity list numbers entries in the evidence window, and a citation says
    "#<n>". It says "turn" only where the harness supplies a stable turn identity. Stored readings
    cite fact ids, so a number is recomputed, never stored.
12. The unasked lane receives none of this: no outcome lines, no work evidence, no drafted or
    confirmed goal, no correction, no digest and no Not accurate token. None of them makes a
    session eligible for the lane, or triggers, orders or gates it.
13. When an analysis may read, and against what. A session waiting at its prompt after a turn stop
    may be read through its last turn, saying so, and never as a reading of how it ended; a goal
    saved after the stop does not withhold it. The evidence window starts at the words' own time:
    the source time for adopted words (DEC-22); for typed words, the time of the latest
    person-authored message at or before the save, else the save time. It is stored on the revision
    beside the save time, as a new revision field admitted under DEC-15b, and a build that does not
    know it falls back to the save time. The page shows both times and labels work before the save
    as "from the last turn". The unasked lane still withholds at a turn stop.
14. The answer reducer. Any valid departure gives "Departs from your intent", and other lines keep
    their own state. Otherwise any saved constraint without a valid `departure` or `consistent`,
    including a malformed or missing result and a line the reading could not ask, gives "Can't
    tell". Otherwise the answer is "Nothing found against what it read. This is not a check that the
    work was done." A failed check in the window outranks both "Nothing found" and "Can't tell". A
    departure count renders only beside a departure. "No reading was produced" and the refusals are
    process states, never answers. All of it is session-page only: never on a row, a total or a
    notification. Elsewhere than Claude Code the panel states the harness limit ("Cargento can't
    read work from this harness"). "Stop session" is not offered (DEC-16, SECURITY.md).

### What the last-turn build decided, 2026-09-24

DRC-4679 built item 13. These are the calls the ruling left open, each made by the orchestrator
within the milestone's scope and recorded on the issue.

- Only Claude Code is read at a turn stop. `eligibility` takes an `admit_turn_stop` switch that is
  off by default, and only the reading route turns it on, for a harness in
  `reading.TURN_STOP_HARNESSES`. The unasked lane fires on every working-to-idle change, which is
  every turn stop, so it keeps the closed default. The test for that runs the lane with the real
  `reading.produce` and a model that counts its calls, because a lane test built on a fake producer
  cannot see the gate.
- A turn stop gets the same eight-second settle as a session end, with its own sentence, since the
  end's sentence says the session ended.
- Through the last turn means through the observed stop: the reading drops every entry timed after
  `finished_at`. A resumed turn whose state update lags leaves the row idle at the old stop while the
  record moves on, and without the cap a check from the new turn was cited in a reading that said it
  covered the last one.
- Words typed after a session end are still withheld. Only the turn stop is relaxed, and the
  withholding test still compares the save time, `baseline_at`. The window start moves only the
  evidence.
- The window start is recomputed on every save, a lines-only save included. For typed words it is
  the latest `user_message` of this session at or before the save, read on the server from the
  session's record, found in the all-sessions collection so a save from that view on an aged session
  still finds it. A permission approval is not a message, so it never moves the window. A record
  that cannot be read opens the window at the save and never refuses the save. Adopted words,
  including an adopted goal carried under a lines-only save, open at their source time.
- A stored window start that is not a moment at or before its own save refuses the entry, as a bad
  provenance does, because reading around it could restore older words.
- A check keeps its call time. The window start alone fixes the case the live walk found: none of
  22 recorded Bash calls had a message from the reader between the call and its result. Using the
  result time would move layer 1's published timestamps, so it is filed separately.
- The page reads the window from the reading, and derives it the old way for a reading stored
  without one. It labels work "from the last turn" only on a Claude Code session waiting at its
  prompt, and only the observed last turn inside the window: from the reader's latest message at or
  before the stop (or the window start, if later) up to the stop, never on the reader's own messages.
  The first build labelled from the window start to the save. That range is fixed at the save, so
  the next turn made it name an older one, and a save made mid-turn left the rest of that turn
  unlabelled.
- The hint says what an analysis reads: "Reads the session up to <cutoff> against your intent.",
  where the cutoff is now, its end, or its last turn, from the same end kind HOW IT LANDED shows. It
  shows only where a press could read: a provider, no refusal beside it, saved words, and words
  given before any observed end. The background job (DRC-4686) added "Runs in the background."
  after it.
- The later-direction floor stays at the save time. By construction no message of the reader's lies
  between the window start and the save, so moving it would change nothing on consistent data and
  would, on a fetch the server missed, turn a message into a later direction.

### What the background build decided, 2026-09-24

DRC-4686 built the background half of item 5; Cancel is DRC-4693. The owner's calls are on the
issue, and the rest were made within them.

- The press answers `202` with the job before the model is called. Every refusal the press had
  before stays synchronous and first. A second press answers `409` with the running job and starts
  nothing; `409` rather than `200`, because a forged press is read by its status.
- The job registry sits beside the one-in-flight slot in `reading`, under its lock, rather than
  replacing it. The unasked lane takes the same slot, and with the slot replaced it would either lose
  its guard or appear as a job the reader never started. A press that meets the lane's slot answers
  `409` with no job.
- The job is published board-wide as `reading_jobs`, keyed as the page keys a session, and not as a
  field on every row. A row field would be declared in three places and would enter history.
- Each phase begins at a real point: preparing at the press, waiting at the CLI's spawn (after the
  spend is committed), checking when a reply arrived. A withheld gate ends a job while it prepares
  and a failed call ends it while it waits; nothing publishes a phase that did not happen. The
  design's timed steps and its "Analyzing 38 turns" heading are overruled: the heading reads
  "Analyzing drift", because a Claude Code session has no stable turn identity (item 11).
- The store is written first, then the job is removed and the slot freed as one step, then one
  revision is published. Any other order lets a page show a finished box with no result, or a result
  under a running box.
- The permission and budget are read again at the model seam inside the job. A refusal there ends
  the job with nothing written, and the board's published permission already says why.
- A job lost to a restart is recorded, not dropped. A marker written before the reservation becomes
  a spent `interrupted` attempt at the next start, so the count stays equal to what the budget
  charged. Letting it vanish was the alternative, and it leaves a charged attempt nowhere in the
  count. Written before rather than after, because a marker that fails after the spend leaves the
  spend uncounted; the cost is that a dashboard dying between the marker and the reservation counts
  one attempt the budget never charged.
- One job is one attempt. The outcome is stored under the job's id and a second write for that id
  counts nothing, and a marker is claimed by an atomic rename before it is recovered. The review
  measured a double count in up to 36 of 40 runs when the dashboard died between the write and the
  marker's removal; reordering alone would have traded it for a lost count.
- A marker's pid means a running dashboard only when a state file on this state directory names it,
  and this process's own pid means an earlier run: a container's dashboard is PID 1 on every start,
  and a bare liveness check never recovered its markers.
- A graceful stop records `interrupted` too. The shutdown kills the call before the next start can
  find its marker, so without this the job wrote "did not complete" for what was a stop.
- Every model call, the goal lane's and the unasked lane's included, uses the supervised runner. A
  timeout that kills only the direct child leaks the grandchild, which those lanes had too.
- Shutdown kills every supervised group, because a child in its own group no longer receives the
  terminal's signals. Leaving that to Cancel would have left one layer of the stack with a child
  that outlives the daemon. SIGHUP and SIGQUIT unwind through the same cleanup as SIGTERM, since a
  closed terminal otherwise left the CLI running untimed, and the shutdown closes the runner under
  its spawn lock, since a CLI spawned during the teardown was measured outliving it. A signal the
  server inherited as ignored stays ignored, or `nohup` would stop protecting it. A reading not yet
  sent when the runner closes is refused before the reservation, so a stop never charges for it.
- On POSIX the group is signalled only while its leader is unreaped: the exit is watched without
  reaping (`waitid` with `WNOWAIT`, a kqueue exit filter on macOS, which has no `waitid`), the group
  is swept, and only then is the leader reaped, with the end of signalling marked in the same step
  under the group's lock. A group id signalled after the reap could name a stranger's group. kqueue
  reports a registration error as an event, so only ESRCH there counts as an exit; any other error
  leaves the exit unwatchable, and the call then polls rather than reading it as an exit and killing
  a running CLI. A helper that leaves the group is not reached, and the docs say so.
- A spent outcome the store refuses keeps its marker, marked as refused, and the next start records
  that the analysis ran and its outcome could not be stored, not that Cargento stopped.
- A finished step is a filled mark and never a check mark. Item 6's rule is about results, but a
  check shape beside a reading is close enough to its reason that the design's check circle was
  not copied.

## DEC-26: four drift levels, and a live estimate after every turn

Decided 2026-09-24 (DRC-4691). DRC-4692 defines and validates the levels on recorded Claude Code
sessions. DRC-4696 builds the live estimate in the panel and the header, and amends the skill body's
sentence "Nothing here evaluates on a cadence" when it ships, not before, because the skill body
describes the shipped product.

A reader who glances at a session wants to know how far it has moved from their intent without
pressing anything. The ruling takes option C's four levels as designed, None or low, Medium, High
and Extreme, with a live estimate after every turn and a header pill. The owner accepted these
costs knowingly:

- It amends DEC-15, including its 2026-09-23 amendment, which refused evaluation on a cadence.
- It amends DEC-17 rule 4 (consistent is never rendered as met) and "What the contract does not
  remove": a cadence makes the full rubric owed, and the levels research below is its first
  measured part.
- It amends DEC-20 item 3 (no surface says a session has no drift), its state table, and "What
  DEC-15's indicator sentence now means".
- It amends DEC-23 items 6 and 7: the level is a derived state of the tool-outcome facts, published
  on the session payload only, never on a row, in history or in an off-machine payload.
- It accepts the A9 failure class, a level that reads safe when little is seen, and puts a measured
  basis in front of it.

Six sub-questions were ruled the same day, each as recommended.

1. The basis is a separate rule per source. Each level has a written definition over named
   evidence, and DRC-4692 measures it. "None or low" has a floor for each source. For the live
   estimate: the latest run of every check has a recorded result and passed, nothing was written
   after that pass, no shell command that is neither a check nor on DEC-23's read-only list ran
   after that pass, and, where the saved intent names folders, every write is inside them; it says
   it read checks and file paths, not what the intent says. For an analysis: every outcome line is
   `consistent` on a tool-reported check under DEC-23 item 8, with no departure, and the Goal may
   rest on the session's own account; it says "From the analysis at <time>: each line of your intent
   against the checks and messages it cited." For both: no failed check, and no unsettled later
   direction. A later direction blocks "None or low", and so, for the live estimate, does such a
   shell command; neither is ever counted as drift. A check with no recorded result, and a pass
   before a later write, never count toward it. With too little evidence the level reads "Not
   enough recorded yet", never "None or low". Zero is too little: the live estimate needs at least
   one check whose latest run passed, and an analysis needs at least one outcome line, so a session
   with no check, or an intent with no outcome line, reads "Not enough recorded yet". DRC-4692
   measures what else is too little. A write here is a file-write tool call the transcript
   recorded. A file a shell command changes is not seen (DEC-23's capture), so "nothing was written
   after that pass" means no recorded write, not that nothing changed. The shell-command blocker
   narrows that gap. A read-only command is not read-only when it carries a command substitution,
   a redirect into a file, or a writing option the closed lists name (`find -delete`, `-exec` and
   `-fprint`, `tree -o`, `git diff`/`log`/`show --output`); what is still not seen is a command on
   the read-only list that changes files through anything else.
2. Two sources, labelled. "Live estimate" is computed without a model after each turn, from DEC-23's
   evidence and the reader's saved intent: failed checks, passes followed by writes, and the share
   of writes outside the folders the intent names. An unsettled later direction, and a shell command
   after any check's latest passing run that is neither a check nor read-only, only block "None or low".
   The folder signal is not used when the intent names no folder, so it is never read as 0%. Over
   an unsaved draft there is no live level: the Drift section reads "Save your intent to see a live
   estimate" and the pill is hidden. "Analysis" derives the level from a reading's per-line
   results, with no new model output. Each source says what it is and when it was computed.
3. Where it shows: the Drift section and the session header pill. Not a Sessions row, not a total
   and not a sort key. DEC-20's "Drift" row mark, its table, and DEC-23's no-row-field rule stay.
4. The live monitor switch is off by default, as the design's "Turn on for a quick, low-cost drift
   check after every turn" says. It is remembered per session in the browser only, and never sent
   to the server: there is no server-side store and no new route. DRC-4696 adds its row to
   [the reader-state inventory](design-reader-state.md). Off hides the live level and the pill;
   the analysis level is unaffected.
5. No notification, desktop or page, comes from the live estimate (DEC-18, DEC-19). The live
   estimate and the analysis level never make a session eligible for the unasked lane, never
   trigger, order or gate it, and never feed it. The live estimate is not DEC-18's unasked reading:
   it calls no model and raises nothing.
6. History. Neither level is stored. The analysis level is recomputed from the stored reading, and
   "Rose from Medium at #33" from recorded evidence within the run. Each source keeps its own line
   from item 1: the live estimate says it reads checks and file paths, not what the intent says, and
   the analysis says it read each line of the intent against the checks and messages it cited.

The owner answered two questions from review the same day, and both answers are part of this ruling
rather than an amendment. A shell command that is neither a check nor read-only, run after any
check's latest passing run, blocks the live estimate's "None or low" and is never drift (item 1, and DEC-23 item
3; the read-only list is in DEC-23's closed lists). The analysis level has its own source line, and
the line "reads checks and file paths, not what the intent says" is the live estimate's alone (items
1 and 6).

### The starting definitions

These are what DRC-4692 validates, not a measured result. Medium: a pass is followed by writes, or
some writes fall outside the named folders. High: the latest run of any check failed, or most writes
fall outside the named folders. Extreme: both hold. "None or low" is the per-source floor in item 1.
