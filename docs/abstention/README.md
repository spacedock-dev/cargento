# The abstention check, committed half

What DEC-17's abstention check expected and what the producer did, and never the session text
either was drawn from. The ruling that fixes this split is restated in
[SECURITY.md](../../SECURITY.md#the-abstention-check); the reasoning behind the check is
[DEC-17](../design-reading-a-session.md#the-condition-on-enabling-not-on-building).

## What lives here

`results.json`, written by `scripts/score_abstention.py --score`. One file, one run. It holds:

- `marks_digest`, the sha256 of `~/.cargento/abstention-marks.json` as it was when scored. A later
  `--report` hashes the marks again and refuses PASS if they moved, because a mark written after
  seeing an output is agreement, not a mark.
- `marks`, the captain's answer key: one sixteen-character hash of `(harness, sid)` per case, and
  `judge` or `abstain` for each of the two constraints.
- `cases`, per case id: the harness, the marks, the outcome the producer landed in for each
  constraint, whether the case reached the model at all, and `asks_output`: whether the Expected
  Output question was put to the model. Only a work-evidence harness (Pi today) is asked it. On
  every other harness the collector fixed that mark to `abstain` and the producer answers
  `not verifiable` without asking, so the output column there is the ruling's answer and the
  report says so instead of counting it as the model abstaining. `counts.output_not_asked` is how
  many cases that covers.
- `counts`, `dec17`, `coverage` and `verdict`, which are what the report prints.
- `rubric`, per DEC-15 expectation case: the kind, the origin, whether it was admitted, and the two
  scored columns, judgement and extraction.

Nothing here names a session, a project, a title, a prompt or a model sentence. A test holds the
summary to that key list.

## What does not live here

The cases (`~/.cargento/abstention-cases.json`) name sessions and carry one user turn each. The
local results (`~/.cargento/abstention-results.json`) carry the producer's withheld reason and its
cutoff sentence. The rubric expectation file (`~/.cargento/abstention-rubric.json`) may carry
synthesised case bodies. All three stay on the machine that made them.

## How to argue with a result

A case id is `sha256("<harness>|<sid>")[:16]`. Whoever holds the cases file can resolve it; nobody
else can, which is the point. The outcome per constraint is one of `withheld:<reason>`, `unparsed`,
`abstained`, `judged:consistent` or `judged:departure`. `withheld` means the producer refused before
the model ran, so the case says nothing about the model, and it is counted for neither side.

The verdict is `failed` when a case marked should-abstain judged, `short` when no case failed but
fewer than one recorded case per DEC-15 kind reached the model on Claude or on Codex, `stale` when
the marks no longer hash to `marks_digest`, and `passed` only when none of those hold. The report
never prints one figure for the whole: false reassurance, false alarm, missed departure and
over-abstention are four counts, and citations hit, missed or extra are a fifth column beside them.

## The rubric expectation file, version 1

Kept beside the cases, never here. Its shape, so a case set can be written against it:

```json
{
  "v": 1,
  "cases": {
    "<case id>": {
      "kind": "supported-departure",
      "harness": "claude",
      "origin": "recorded",
      "expect": {
        "goal": {"result": "departure", "cites": ["<fact id>"]}
      }
    },
    "<synthesised id>": {
      "kind": "misleading-completion",
      "harness": "codex",
      "origin": "synthesised",
      "generated_by": "claude-code",
      "verified_by": "codex",
      "row": {"harness": "codex", "sid": "<sid>", "state": "idle", "ended_at": 1.0},
      "facts": [{"fact_id": "<fact id>", "type": "assistant_message", "summary": "..."}],
      "expect": {
        "goal": {"result": "unverifiable", "cites": []}
      }
    }
  }
}
```

`kind` is one of `supported-departure`, `legitimate-change`,
`matching-intent-incorrect-execution`, `misleading-completion` and `insufficient-evidence`.
`result` is one of `departure`, `consistent` and `unverifiable`, the producer's own three tokens. A
`recorded` entry names a case in the cases file by id and carries no body; a `synthesised` entry
carries its own `row` and `facts`, and is admitted only when `generated_by` and `verified_by` are
both present and differ. A synthesised entry verified by its own author is listed in the summary as
not admitted and scores nothing.

A synthesised `row` has to be one the producer will read. It goes through the same eligibility
rules as a live row: a `state` other than `idle` reads mid-flight, and an idle row reads finally
only when it carries an `ended_at` later than 1.0 (the yardstick's stamp) and long enough before
the run to have settled. An idle row with neither is `idle-unknown`, and the producer withholds it
before the model, so the case scores nothing. The first fixture written against this format did
exactly that.
