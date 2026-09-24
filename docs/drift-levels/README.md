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
  how many are marked. It is committed before any result, and the commit order is the evidence
  that the marks came first.
- `results.json`, once a scoring run has been committed, written by `levels_cases.py --score`. Per
  case id it holds the kind, the owner's mark for each source, and for each source the level, its
  reason tokens and an outcome of `match`, `more-cautious`, `failed` or `unmarked`. It also holds
  the marks digest as scored, the committed digest it was checked against, the counts and the
  verdict.

A case id is `sha256("claude|<sid>|<until>|<kind>")[:16]`. Whoever holds the cases file can resolve
it, and nobody else can. A kind is one of a closed set (`failed-check`, `check-not-recorded`,
`pass-then-write`, `own-account-only`, `intent-names-no-folder`, `draft-unsaved`, `work-left-out`,
`later-direction`, `other`). A reason is one of `levels.REASONS`. Nothing here names a session, a
path, a command, the intent's words, a fact id or model prose, and a test asserts that none of them
appears in the summary.

## What does not live here

The spec the owner writes, the frozen cases (`~/.cargento/drift-levels/cases.json`) and the marks
themselves stay on the machine that made them. The cases hold the transcript path, the session id,
the recorded check lines and written paths layer 1 publishes, the intent the owner set for the case
and any stored reading's per-line results. `levels_cases.py --build` refuses a `CARGENTO_HOME` inside
the repository.

## Making the cases and marking them

Write a spec at `~/.cargento/drift-levels/spec.json`. Each entry names one case:

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

`until` is a Unix time or `null`. The transcript is cut there, so a session that later changed is
frozen as it stood. 74c70a30 is the case in point: it now ends on a passing run, so its failed-check
case is cut before its second turn. `intent.saved: false` makes a drafted goal that was never saved,
and a goal and lines that name no folder make the no-folder case. Both are set here because neither
is a property of the session. `unsettled_directions` is written by hand, since the count comes from
the page. An entry may carry `reading`, a stored reading object, for the analysis source. An entry
missing any required field is refused, and nothing is defaulted.

```bash
python3 scripts/levels_cases.py --build ~/.cargento/drift-levels/spec.json
python3 scripts/levels_cases.py            # mark: one level per source per case, no default
python3 scripts/levels_cases.py --report   # how far through the key you are
git add docs/drift-levels/marks-digest.json && git commit -s   # the digest, before any score
python3 scripts/levels_cases.py --score    # later: writes results.json
```

Each marking screen shows the intent, the frozen checks and writes with their times before the cut,
the full-scan counts, and any stored reading's per-line results. It never shows what the rules
concluded. The tool asks what the live estimate should read, and, only when the case carries a
reading, what the analysis level should read. It takes `n`, `m`, `h`, `e`, `x` (Not enough recorded
yet), `d` (no live level), `s` to skip and `q` to stop. Any other reply, including an empty one, is
asked again. A saved mark set is bound to the cases it was made against, and a rebuild that would
orphan marks is refused.

## How to argue with a result

A level passes when it matches the owner's mark or is more cautious, meaning it reassures less. A
higher drift level is more cautious than a lower one. "Not enough recorded yet" is more cautious
than "None or low" only, because said of a case marked Medium or higher it hides drift the owner saw.
"None or low" on a case marked anything else fails. "No live level" is met only by itself.

The verdict is `stale` when the marks no longer hash to the committed digest, or no longer belong
to the case set, and a stale run is never a pass. It is `unmarked` when any scored source has no
mark, `failed` when any source failed, and `passed` only when none of those hold.

These levels are the starting definitions DEC-26 set out, and this check measures them. Where the
ruling left a choice, `levels.py` takes the side that withholds. A check launched in the background
withholds the floor. So does a pass the twelve listed entries cannot place, or a write the listing
dropped where the intent names folders. An analysis never reads Extreme, because Extreme needs both
of High's conditions, and one of them, most writes outside the named folders, is the live
estimate's alone. A case the owner marks Extreme therefore fails the analysis source until a ruling
says otherwise, and that failure is a finding to report, not a figure to tune.
