# The drift levels check, committed half

This directory holds what the owner expected each drift-level case to read and what the two level
functions returned. It never holds the session text either one came from. The split follows the
abstention check's, and [SECURITY.md](../../SECURITY.md#the-abstention-check) holds the ruling for
both. The levels themselves, and why each source has its own floor, are in
[DEC-26](../design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn).

DRC-4692 builds the two functions in `cargento_runtime/levels.py` and measures them here before any
reader sees a level. The live estimate reads a Claude Code session's recorded checks and written
paths beside the saved intent. The analysis level reads a stored reading's per-line results. Neither
calls a model, so scoring spends nothing and can be re-run.

## What lives here

- `marks-digest.json`, written by `scripts/levels_cases.py` each time the owner saves marks. It holds
  the sha256 of `~/.cargento/drift-levels/marks.json` as written, and how many cases there are and
  how many are marked. It is committed before any reading is attached and before any result. The
  scorer reads it from `HEAD` with `git show`, never from the working copy, and refuses when the two
  differ, so the commit is the evidence that the marks came first.
- `results.json`, once a scoring run has been committed, written by `levels_cases.py --score`. Per
  case id it holds the kind, the owner's mark for each source, and for each source the level, its
  reason tokens and an outcome of `match`, `more-cautious`, `failed` or `refused:<why>`. It also
  holds the marks digest, the commit that holds it, the counts and the verdict.

A case id is `sha256("claude|<sid>|<until>|<kind>")[:16]`. Whoever holds the cases file can resolve
it, and nobody else can. A kind is one of a closed set (`failed-check`, `check-not-recorded`,
`pass-then-write`, `own-account-only`, `intent-names-no-folder`, `draft-unsaved`, `work-left-out`,
`later-direction`, `other`). A reason is one of `levels.REASONS`. Nothing here names a session, a
path, a command, the intent's words, a fact id or model prose, and a test asserts that none of them
appears in the summary.

## What does not live here

The spec the owner writes, the frozen cases (`~/.cargento/drift-levels/cases.json`), the marks and
the attached readings (`readings.json`) stay on the machine that made them. The cases hold the
transcript path, the session id, the working directory, the recorded check lines and written paths
layer 1 publishes, and the intent the owner set for the case. `levels_cases.py --build` refuses a
`CARGENTO_HOME` inside the repository.

## The order: marks, digest, readings, score

A mark written after seeing an output is agreement, not a mark, so the tool enforces this order.

1. Write a spec at `~/.cargento/drift-levels/spec.json` and build the cases. The spec has no
   readings, and an entry that carries one is refused.

   ```json
   {
     "v": 1,
     "cases": [
       {
         "kind": "failed-check",
         "transcript": "/path/to/<session id>.jsonl",
         "until": 1790222400.0,
         "intent": {"saved": true, "goal": "Build tic-tac-toe in web/", "lines": ["node --test passes"]},
         "unsettled_directions": 0
       }
     ]
   }
   ```

   `until` is a Unix time or `null`. The transcript is cut there, so a session that later changed
   is frozen as it stood. 74c70a30 is the case in point: it now ends on a passing run, so its
   failed-check case is cut before its second turn. `intent.saved: false` makes a drafted goal that
   was never saved, and a goal and lines that name no folder make the no-folder case. Both are set
   here because neither is a property of the session. `unsettled_directions` is written by hand,
   since the count comes from the page. An entry missing any field is refused, and nothing is
   defaulted.

2. Mark every case. Each screen shows the intent, the frozen checks and writes with their times
   before the cut, and the full-scan counts. It never shows a reading, a model output or what the
   rules concluded. It asks what the live estimate should read and, for every case whose intent has
   an outcome line, what an analysis should read. It takes `n`, `m`, `h`, `e`, `x` (Not enough
   recorded yet), `d` (no live level, live only), `s` to skip and `q` to stop. Any other reply,
   including an empty one, is asked again. Marking is refused once `results.json` exists.

3. Commit `marks-digest.json`.

4. Attach readings. `--attach-readings` takes `{"v": 1, "readings": {"<case id>": <reading>}}`,
   where each reading is a stored reading in the annotation store's own shape. It refuses every one
   unless the digest is committed and the local marks still hash to it, each case id is known, the
   store's own validator (`annotations._assessment`) admits the reading, and its `read_at` is after
   the digest's commit. It writes `readings.json` stamped with that digest and its commit.

5. Score. `--score` writes nothing when the digest is not committed, when the working copy differs
   from `HEAD`, when the marks no longer hash to it, or when any case is unmarked. A reading found in
   the case file, attached under another digest or commit, made before the digest's commit, or
   refused by the store reads `refused:<why>`, and the verdict is `refused`.

```bash
python3 scripts/levels_cases.py --build ~/.cargento/drift-levels/spec.json
python3 scripts/levels_cases.py                 # mark: both levels per case, no default
python3 scripts/levels_cases.py --report        # how far through the key you are
git add docs/drift-levels/marks-digest.json && git commit -s
python3 scripts/levels_cases.py --attach-readings ~/.cargento/drift-levels/readings-spec.json
python3 scripts/levels_cases.py --score         # writes results.json
```

## How to argue with a result

A level passes when it matches the owner's mark or is more cautious, meaning it reassures less. A
higher drift level is more cautious than a lower one. "Not enough recorded yet" is more cautious
than "None or low" only, because said of a case marked Medium or higher it hides drift the owner saw.
"None or low" on a case marked anything else fails. "No live level" is met only by itself.

The verdict is `refused` when any reading was refused, `failed` when any scored source failed, and
`passed` only when neither holds. A case with an analysis mark and no attached reading scores its
live level only, and `counts.no_reading` says how many. Runs that are not a pass because of the
digest or an unmarked case write no file at all.

These levels are the starting definitions DEC-26 set out, and this check measures them. Where the
ruling left a choice, `levels.py` takes the side that withholds, and the list is in
[DEC-26's build notes](../design-reading-a-session.md#what-the-levels-build-decided-2026-09-24).
One of those choices matters for marking: an analysis never reads Extreme, because Extreme needs both
of High's conditions, and one of them, most writes outside the named folders, is the live estimate's
alone. A case the owner marks Extreme on the analysis side therefore fails until a ruling says
otherwise, and that failure is a finding to report, not a figure to tune.
