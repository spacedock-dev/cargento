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
  secret, the owner's final mark (drift, no drift, unclear) and its class, the case's roles, and one
  outcome per detector and intent arm. It also holds the digests and the counts. It names no session,
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
6. `--read --dry-run` counts the calls; `--read` makes them, charged on this tool's own ledger.
7. `--score` writes `results.json`.

```bash
python3 scripts/redact_session.py --out tests/raw_sessions ~/.claude/projects/<proj>/<sid>.jsonl ...
python3 scripts/drift_replay.py --build
python3 scripts/drift_replay.py                # blind marks; q stops, re-run continues
python3 scripts/drift_replay.py --reconcile
git add docs/drift-replay/marks-digest.json && git commit -s
python3 scripts/drift_replay.py --live
python3 scripts/drift_replay.py --read --dry-run
python3 scripts/drift_replay.py --read         # spends: capped at 240 calls
python3 scripts/drift_replay.py --score
```

## The intent arms

Each cut is read three times, once per intent, and each intent is built only from words dated
before the cut.

- realistic: your opening prompt, saved when you typed it, which is what "Use your prompt" adopts.
- part: the message that opened the annotated part holding the cut.
- hindsight: the goal the annotation wrote afterwards. An upper bound, never a headline.

## How to argue with a result

Each detector lands in one outcome per cut and arm.

On a cut you marked as drift:

- relevant flag: it flagged, and what it cited is dated at or after the drift began
- irrelevant flag: it flagged on something older, such as a check that failed hours before
- withheld: "Not enough recorded yet" or not verifiable
- reassured: None or low, or consistent; the worst outcome
- refused: the apparatus could not read the cut

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
