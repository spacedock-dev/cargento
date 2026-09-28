# The drift levels check, committed half

This directory holds what the owner expected each drift-level case to read and what the two level
functions returned. It never holds the session text either one came from. The split follows the
abstention check's, and [SECURITY.md](../../SECURITY.md#the-abstention-check) holds the ruling for
both. The levels themselves, and why each source has its own floor, are in
[DEC-26](../design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn).

DRC-4692 builds the two functions in `cargento_runtime/levels.py` and measures them here before any
reader sees a level. The live estimate reads a Claude Code session's recorded checks and written
paths beside the saved intent. The analysis level reads a stored reading's per-line results. Neither
calls a model, so scoring spends nothing and can be re-run. The readings the analysis level needs
come from `--read`, the one mode that calls a model (see
[Readings replayed from the frozen cases](#readings-replayed-from-the-frozen-cases)).

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

The spec the owner writes, the frozen cases (`~/.cargento/drift-levels/cases.json`), the marks,
the replayed readings (`replayed-readings.json`, with `replay.json` recording what each case got)
and the attached readings (`readings.json`) stay on the machine that made them. The cases hold the
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
   including an empty one, is asked again.

   Marking is closed for a case set once it has been scored, however the files that showed the
   result were removed. It is refused when `results.json` exists, when the local marker
   `~/.cargento/drift-levels/scored-<case set digest>.json` exists, or when git history on any ref
   already holds a result or a marks digest for this case set. `marks-digest.json` and
   `results.json` carry the case set's digest so that history can be matched, and the marks digest is
   committed once per case set.

3. Commit `marks-digest.json`.

   Then make the readings, with `--read` (next section), on the owner's go-ahead. It is the only
   step that spends.

4. Attach readings. `--attach-readings` takes `{"v": 1, "readings": {"<case id>": <reading>}}`,
   where each reading is a stored reading in the annotation store's own shape. It refuses every one
   unless the digest is committed and the local marks still hash to it, each case id is in those
   committed marks, the
   store's own validator (`annotations._assessment`) admits the reading, and its `read_at` is after
   the digest's commit. It writes `readings.json` stamped with that digest and its commit.

   This check trusts two times it cannot verify: the reading's own `read_at` and the digest
   commit's committer date. It catches a reading made before the marks by mistake. It does not prove
   the order against someone who edits `read_at` forward or rewrites the commit's date.

5. Score. `--score` writes nothing when the digest is not committed, when the working copy differs
   from `HEAD`, when the marks no longer hash to it, or when any case is unmarked. A reading found in
   the case file, attached under another digest or commit, made before the digest's commit, or
   refused by the store reads `refused:<why>`, and the verdict is `refused`.

```bash
python3 scripts/levels_cases.py --build ~/.cargento/drift-levels/spec.json
python3 scripts/levels_cases.py                 # mark: both levels per case, no default
python3 scripts/levels_cases.py --report        # how far through the key you are
git add docs/drift-levels/marks-digest.json && git commit -s
python3 scripts/levels_cases.py --read --reading-home ~/.cargento/drift-levels-readings --dry-run
python3 scripts/levels_cases.py --read --reading-home ~/.cargento/drift-levels-readings   # spends
python3 scripts/levels_cases.py --attach-readings ~/.cargento/drift-levels/replayed-readings.json
python3 scripts/levels_cases.py --score         # writes results.json
```

## Readings replayed from the frozen cases

The owner ruled on 2026-09-28 that the analysis readings are made by replaying the frozen cases,
not by pressing Check for drift on a live board and not by recording new sessions.

A live press cannot read these cases. The sessions are old, and the board has no turn stop or
session end for them. `reading.end_kind` counts a stop only from a row's `finished_at` or
`ended_at`, which come from hook events, and the history store holds only state snapshots for
them. So the press withholds `idle-unknown` before any model call. That happened on the first try,
and seeding the reading home's history from the real store did not change it. A case cut before
its session's end had a second problem: the board reads the session as it stands now, which is more
than the frozen facts, so the prep left all three cut cases out as `cut-not-live`.

`--read` calls the same producer a press calls, `reading.produce`, with the case's own record:

- The evidence is the case's frozen facts, the same facts the owner marked against and `--score`
  reads. The board is never read.
- The intent is the case's goal and lines, as one revision stamped at 1.0, before every record. The
  owner marked each line against the whole frozen record, so the evidence window opens before all
  of it. DRC-4666's replay stamps its intent the same way.
- The row is a Claude Code session stopped at the case's own `captured_at` (its cut, or its last
  recorded fact). That is the moment the case stands at, and the moment the owner marked. It is the
  one input the replay supplies that the recording does not hold, and the reason replay is possible
  at all. The reading's scope reads "through the last turn".
- The route is Codex to OpenAI, the board's route for a Claude Code session on this machine. The run
  refuses if `reading_route.destination("codex")` names anything else. The prompt, the evidence
  rules, the admission of a turn stop and the outcome lines are the press's. With a stored grant
  for tool output to OpenAI, each check goes with its line, result, times and changed-after flag.
  The cases froze no output tails, so no check's output is sent. Without a grant, the checks stay
  off the prompt and the cutoff says so, as it does on a press.

**One count.** Every call is charged where the board charges a press: `reading_policy.reserve`, on
the reading home's `cargento-reading-permission.sqlite3`, through the same `GuardedModel` seam. A
charge happens after every check `produce` makes and before the subprocess, so a case the producer
withholds costs nothing. A call that starts and then fails is still charged. `--reading-home` names
the home the reading board ran on. The run refuses before any call if Codex is not allowed there,
or if the calls it needs do not fit in the ledger's rolling 12. That ledger counts a rolling day. The
owner's DRC-4692 authorization is a total (12 readings, 5 spent before this), and nothing on disk
holds that total, so whoever runs `--read` adds its calls to the count logged on DRC-4692.

**Refused before any call:** a digest that is not committed, local marks that no longer hash to it,
cases that changed since they were marked (the marks file carries the case set's digest, and the
committed digest binds the marks file), or a chosen case that is unmarked, has no analysis mark, is
not a Claude Code case, or has an intent that was never saved or has no outcome line.

**Refused by the producer:** whatever `produce` withholds is recorded in `replay.json` as `refused`
with its reason token. A reading the annotation store's validator would refuse is recorded as
`store-refused`. Nothing stands in for a refused case. It reaches `--score` as a case with no
reading, which `counts.no_reading` counts.

Two cases with the same producer inputs share one call, and the reading is attached to both. The
same session and cut, frozen as two kinds, is one reading: 3f4e7b30 is `check-not-recorded` and
`work-left-out`. A case that already has a replayed reading is kept and not read again, so running
the command twice does not spend twice.

`--read` writes `replayed-readings.json` in exactly the shape `--attach-readings` takes, and
`--attach-readings` and `--score` run on it unchanged. `replay.json` holds, per case id, the status,
the withheld token, whether the call spent, whether it was charged, and when. It holds no session id,
intent text or model prose. `--dry-run` runs the producer up to the model with a stub that sends
nothing, and prints only case ids, the number of calls, prompt sizes, fact counts and the ledger's
count. It makes no call, charges nothing and writes no file.

With no `--case`, `--read` reads the cases the marking prep named, the four uncut sessions
1b4a141f, 3f4e7b30, cfc97e82 and a2364dbf. That is five case ids and four calls. `--case <id>`,
repeated, chooses others. The cut cases can be read this way too, since replay reads them as they
were frozen.

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
