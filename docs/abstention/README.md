# The abstention check, committed half

What DEC-17's abstention check expected and what the producer did, and never the session text
either was drawn from. The ruling that fixes this split is restated in
[SECURITY.md](../../SECURITY.md#the-abstention-check); the reasoning behind the check is
[DEC-17](../design-reading-a-session.md#the-condition-on-enabling-not-on-building).

The captain accepted the twelve marked recorded cases as sufficient to enable reader-requested
readings on 2026-09-14. [acceptance.json](acceptance.json) records that decision and the bound
answer key. The runtime publishes `accepted`; no scoring verdict is implied. The
[amended ruling](../design-reading-a-session.md#amended-2026-09-14-the-captain-accepts-the-case-review)
owns enablement. The scoring format and verdicts below remain available for evaluating the producer.

That acceptance covers the Codex producer only. The Claude Code producer built by DRC-4650 has its
own gate, `annotations.CLAUDE_ABSTENTION_CHECK`, and it is recorded `not-run`. No recorded Claude
Code case has been read by that producer, the accepted packet was reviewed against Codex readings,
and the scorer here still drives `reading.CodexReadingModel`. Until a run under DRC-4666 qualifies
it, Codex keeps reading Claude Code sessions and the page says so before the press. The
[amendment](../design-reading-a-session.md#amended-2026-09-23-claude-code-is-built-and-gated) owns
that ruling.

## What lives here

`results.json`, once a scoring run has been committed, written by
`scripts/score_abstention.py --score`. One file, one run. It holds:

- `marks_digest`, the sha256 of `~/.cargento/abstention-marks.json` as it was when scored. A later
  `--report` hashes the marks again and refuses PASS if they moved, because a mark written after
  seeing an output is agreement, not a mark.
- `inputs_digest`, on a historical replay: a hash of the cases and rubric as scored. A later
  report refuses PASS if either changed. The inputs themselves stay local.
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
- `rubric`, per DEC-15 expectation case: the kind, the origin, whether it was admitted and, when it
  was not, a token saying why; whether a case with that id was scored at all; and the two scored
  columns, judgement and extraction.

Nothing here names a session, a project, a title, a prompt or a model sentence. A test asserts that
none of the local half's fields -- the session id, the project, the title, the opening ask, the
cutoff sentence, the model's detail -- appears in it, by name or by value.

## What does not live here

The cases (`~/.cargento/abstention-cases.json`) name sessions and carry one user turn each. The
local results (`~/.cargento/abstention-results.json`) carry the producer's withheld reason and its
cutoff sentence. The rubric expectation file (`~/.cargento/abstention-rubric.json`) may carry
synthesised case bodies. All three stay on the machine that made them.

## Historical replay, case format 4

Older case formats fetch the current row and facts from the live board at scoring time. That
cannot reproduce a historical case: the session may have disappeared, its lifecycle may have
changed, and its old facts may no longer be served. Format 4 reads a frozen packet offline.
`mark_abstention.py --build` still produces the older live format; a replay packet must be
prepared from recorded evidence before marking.

The local `abstention-cases.json` has `v: 4`, the `goal` and `output` yardstick strings, and a
`cases` list. Each case carries:

| Field | Meaning |
|---|---|
| `id`, `harness`, `sid` | The canonical session hash and its recorded identity. Replay admits Claude, Codex and Pi; duplicate IDs and hashes that do not match the identity are refused. |
| `origin` | `recorded`. Generated cases belong in the separate rubric file. |
| `captured_at` | A finite, positive Unix timestamp: the time being replayed. |
| `row_snapshot` | The row observed then, including its explicit `working`, `needs_input` or `idle` state and any observed `ended_at` or `finished_at`. Its identity must match the case. |
| `producer_facts` | The semantic facts available then, in the runtime fact format. Every fact must name that same session and carry a positive timestamp no later than `captured_at`. An empty list is valid and stays empty. |

The marking screen shows the frozen producer ledger, recorded lifecycle and both yardstick
strings before asking for a mark. Optional `title` and `asked_for` fields add review context;
legacy collector counts and output-question flags are not needed. Excerpts and later reviewer
context may live in the packet for review, but only `producer_facts` enters the producer.

Keep each packet in its own directory under `~/.cargento`, with the standard case and marks
filenames, and set `CARGENTO_HOME` to that directory for both scripts. Run the scorer's
`--report` first: it checks every snapshot and lists the recorded lifecycle without spending.
Then run the marking script interactively. It writes a `cases_digest` alongside the marks and
refuses to reuse an existing key if the packet changed. Finally, the scorer's `--score` uses those
bound marks. `--out` selects the summary path; local results stay beside the cases. The rubric
file can live there too, or be selected with `--rubric`.

Malformed snapshots stop the whole run before any model call or result write. There is no live
fallback, including when snapshots have the wrong format version. Replay passes `captured_at`
as the producer's clock, so a settling end does not become settled just because the check runs
later. An idle row without an observed session end remains withheld. Do not invent an end or
change a quiet row to working to make it qualify. The normal evidence and eligibility rules,
coverage floor still apply to scoring. Enablement follows the amended ruling linked above.

## How to argue with a result

A case id is `sha256("<harness>|<sid>")[:16]`. Whoever holds the cases file can resolve it; nobody
else can, which is the point. The outcome per constraint is one of `withheld:<reason>`, `unparsed`,
`abstained`, `judged:consistent` or `judged:departure`. `withheld` means the producer refused before
the model ran, so the case says nothing about the model, and it is counted for neither side.

The verdict is `failed` when a case marked should-abstain judged, `short` when no case failed but
fewer than one recorded case per DEC-15 kind reached the model on Claude or on Codex, `stale` when
the marks no longer hash to `marks_digest` or replay inputs no longer match `inputs_digest`, and
`passed` only when none of those hold. The report
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

Every one of those fields is hand-typed, and three of them are copied into this committed file, so
each is read against a closed set. A key that is not sixteen hex characters is dropped before
anything reads it, and the run prints how many. A `kind` outside the five, an `origin` spelt any
other way (`synthesized` and `Synthesised` included), or a synthesised `harness` outside `claude`,
`codex` and `pi` lands in the summary as not admitted with a reason token, and the value that
earned it is not written. A `recorded` entry's harness comes from the recorded case, never from the
entry: the coverage floor is what stands between an all-Claude corpus and PASS. An `expect` whose
`result` is not one of the three tokens is not scored either; that constraint is counted as
`unscored:bad-expectation` rather than read as an abstention expectation nobody wrote.

A synthesised `row` has to be one the producer will read. It goes through the same eligibility
rules as a live row: a `state` other than `idle` reads mid-flight, and an idle row reads finally
only when it carries an `ended_at` later than 1.0 (the yardstick's stamp) and long enough before
the run to have settled. An idle row with neither is `idle-unknown`, and the producer withholds it
before the model, so the case scores nothing. The first fixture written against this format did
exactly that.
