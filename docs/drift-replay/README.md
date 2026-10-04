# The drift replay check, committed half

This directory holds what the owner marked at each cut of the pushback sessions, and what Cargento's
drift detectors did there. It never holds the session text either one came from.
[SECURITY.md](../../SECURITY.md#the-abstention-check) holds the ruling for this check and its two
siblings, the abstention check and the [drift levels check](../drift-levels/README.md).

The question it answers is whether Cargento catches drift a person actually pushed back on. The
golden key is `tests/annotated_sessions/<sid>/annotation.md`. The data is each session's log: the
redacted copy under `tests/raw_sessions/<sid>/`, which is gitignored and made by
`scripts/redact_session.py`, or the original with `--source original`.

## What lives here

- `marks-digest.json`, written each time the owner marks. It holds the sha256 of
  `~/.cargento/drift-replay/marks.json`, the digest of the case set the marks belong to, and counts.
  It is committed before any run, and every run reads it from `HEAD`, never from the working copy.
- `results.json`, once a score has been committed. Per case it holds a case id salted with a local
  secret, the owner's final mark (drift or no drift) and its class, the case's roles, and one outcome
  per detector and intent arm. A cut marked unclear is left out. It also holds the digests and the counts. It names no session,
  path, command, word or model sentence.

## What does not live here

The cases, the marks, the live and read outputs, the spend ledger and the salt stay in
`~/.cargento/drift-replay/`. The cases name sessions and times; the outputs hold the agent's and
the person's words through the readings.

## The order: cases, blind marks, digest, runs, score

A mark written after seeing an output is agreement, not a mark, so the tool holds this order.

1. `--build` finds every cut: the last turn stop before each pushback, a seeded sample of eight
   ordinary turn stops per session, the stop before each episode's drift began, and the first stop
   after the agent answered the pushback. One cut can hold several of these roles.
2. Mark blind (no flag). One shuffled screen per cut shows your opening message and the last eight
   messages before the cut, and nothing after it: no annotation, no role, no detector output. It asks
   whether the agent had drifted from what you wanted by that point, and if so, what kind.
3. `--reconcile` shows the annotations' answer beside each blind mark that disagrees with it, and you
   decide. Both answers are kept. A mark you have not agreed to is not written (the 2026-09-28 rule).
4. Commit `marks-digest.json`. Marking closes once any output exists.
5. `--live` runs the live estimate and Steer back at every cut. No model, no spend.
6. `--read --dry-run` counts the calls that would reach the model and records that plan. `--read`
   refuses without a plan for the same cases and arms, or when the plan needs more calls than the
   ledger has left, and charges each call before it is made.
7. `--score` writes `results.json`.

```bash
python3 scripts/redact_session.py --out tests/raw_sessions ~/.claude/projects/<proj>/<sid>.jsonl ...
python3 scripts/drift_replay.py --build
python3 scripts/drift_replay.py                # blind marks; q stops, re-run continues
python3 scripts/drift_replay.py --reconcile
git add docs/drift-replay/marks-digest.json && git commit -s
python3 scripts/drift_replay.py --live
python3 scripts/drift_replay.py --read --dry-run
python3 scripts/drift_replay.py --read         # spends: capped at 440 calls in all
python3 scripts/drift_replay.py --score
```

## The intent arms

Each cut is read once per intent arm. The first two are your own words, dated before the
cut; the third is written afterwards on purpose.

- realistic: your opening prompt, saved when you typed it, which is what "Use your prompt" adopts.
- part: the first message you typed in the annotated part the cut belongs to.
- hindsight: the goal the annotation wrote afterwards. An upper bound, never a headline.
- adopted: the opening prompt taken with "Use your prompt", so the producer knows its source.
- current: a goal and up to three outcome lines drafted from your own messages before the cut, by
  agents shown nothing the session's agent said, as if you kept your intent up to date. They live in
  `~/.cargento/drift-replay/current-intents.json`, with the time they would have been saved.

## How to argue with a result

Each detector lands in one outcome per cut and arm.

On a cut you marked as drift:

- relevant flag: it flagged, and what raised it happened at or after the drift began. For the live
  estimate that is the rise it names, or else the latest failed check; for Analyze, what a
  departure cites
- irrelevant flag: it flagged on something older, such as a check that failed hours before
- unattributed flag: it flagged, and nothing says what raised it, or the cut has no drift start
- echo: an Analyze departure that cites only your own messages
- withheld: "Not enough recorded yet" or not verifiable
- reassured: None or low, or consistent; the worst outcome
- refused: the apparatus could not read the cut, or the model call failed

On a cut you marked as no drift: false alarm, quiet, withheld or refused.

Steer back is reported as offered or not. Once an intent is saved, any later message of yours makes
it available, so "offered" says little by itself. What it would have said is in the local output.

Withheld counts as a miss when the question is whether drift was found, and it is shown on its own
because abstaining is the designed behaviour. Only the first pushback of an episode counts toward
catches; a later one is persistence. A departure that rests only on your own earlier correction is
an echo, not a catch.

Four sessions from one person is a development set. It supports "caught this, here, because of that"
and "cannot see this kind at all". It does not support a rate. A rate needs sessions collected after
the check is frozen.

## The first run, 2026-10-04

The owner delegated the marking. Two fresh agents marked all 99 cuts blind, a third broke two
ties, and two more reconciled the 26 cuts where the blind answer disagreed with the annotations,
each seeing what the person typed next; the three cuts they split on are unclear and left out. None
of them had seen any detector output, and the marks digest was committed before any run. Every
marker is an agent, likely of the same model family as the Claude Code reader being scored, so this
is not a human key.

Live estimate and Steer back ran at every cut and arm. Analyze ran the realistic and part arms only
(195 calls of the 240 authorized; the hindsight arm would have passed the cap), and every call came
back as a reading. A score models a reader who presses "Keep my intent and analyze", because the
page otherwise shows a departure as not verifiable while a later direction is unsettled.

What it found, on four sessions from one person (a development set, so no rates):

- Neither detector separated drift from no drift. On the realistic arm, Analyze raised a departure at
  8 of 22 first-pushback drift cuts and 26 of 71 no-drift cuts; the live estimate flagged 8 of 22 and
  19 of 71, every time on a failed check, some of them days old.
- Two blind judges, shown each flag's evidence beside the drift without being told which detector
  raised it, rated none of the live estimate's 14 flags on drift cuts as pointing at the drift, and
  one Analyze cut as doing so: a false "running" claim, caught from the agent's own words at a later
  pushback in the same episode, so not counted among first pushbacks.
- The intent fed to Analyze drove most of the result. A goal adopted from the opening prompt keeps
  240 characters, which in one session cut off the instruction that mattered and in another kept
  only plan-file preamble, and once the person had moved the work on, every later turn read as a
  departure from it. About 7 of the 26 no-drift departures were model errors, two of them reading a
  passing run as failed.
- Most of the drift the person pushed back on (false status claims, buried questions, effects seen
  only on their screen) was invisible to the blind markers too until they saw the person's reply.
- Steer back was offered at 68% of drift cuts and 72% of the rest.

The `relevant-flag` outcome in `results.json` uses the time rule above, which nearly every flag
passes because a departure usually cites the agent's last message; the blind judges' ratings are
the stricter reading. `results.json` counts 24 drift cuts; 22 of them are first pushbacks.
