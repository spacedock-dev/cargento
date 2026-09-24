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
Code case has been read by that producer, and the accepted packet was reviewed against Codex
readings. The scorer can now drive either producer (`--producer claude` or `--producer codex`),
and format 5 below is the packet DRC-4666 qualifies Claude Code against. Writing a Claude Code
result opens nothing: the gate moves only in its own reviewed commit. Until then, Codex keeps
reading Claude Code sessions and the page says so before the press. The
[amendment](../design-reading-a-session.md#amended-2026-09-23-claude-code-is-built-and-gated) owns
that ruling.

## What lives here

`results.json` for the Codex producer and `claude-results.json` for Claude Code, once a scoring
run has been committed, written by `scripts/score_abstention.py --score --producer <name>`. One
file per producer, one run each. It holds:

- `producer`, `model` and `argv_digest`: which producer ran, the model id it passed, and the
  sha256 of the argv its exec builds, read without starting a process. A later change to a flag,
  the model or the effort moves the digest, so a result cannot be carried over to a producer that
  no longer runs that way.
- `destination`, `binary` and `cli_version`: where `reading_route.destination` says the call goes,
  the installed CLI it ran (its path with the home directory written `~`) and that CLI's
  `--version` line. A Claude Code result is written only when the destination is `Anthropic` and
  the CLI is the native installer's, a file under `~/.local/share/claude/versions` named for the
  version it reports. A stub on `PATH` or an `ANTHROPIC_BASE_URL` pointed elsewhere refuses the
  run before anything is written.
- `spend`, the calls charged to the spend ledger when the run finished and the cap it ran under.
- `marks_digest`, the sha256 of `~/.cargento/abstention-marks.json` as it was when scored. A later
  `--report` hashes the marks again and refuses PASS if they moved, because a mark written after
  seeing an output is agreement, not a mark.
- `inputs_digest`, on a historical replay: a hash of the cases and rubric as scored. A later
  report refuses PASS if either changed. The inputs themselves stay local.
- `marks`, the captain's answer key: one sixteen-character hash of `(harness, sid)` per case, and
  `judge` or `abstain` for each constraint: `goal` and `output` in the older formats, `goal` and
  `line_1` to `line_k` in format 5. Copied from the scored records as closed tokens, never from the
  marks file, which is hand-editable.
- `cases`, per case id: the harness, the marks, the outcome the producer landed in for each
  constraint, whether the case reached the model at all, and `asks_output`: whether the Expected
  Output question was put to the model. Only a case whose record shows work (a Pi work result,
  since the check never grants tool output) is asked it. On every other case the collector fixed
  that mark to `abstain` and the producer answers `not verifiable` without asking, so the output column there is the ruling's answer and the
  report says so instead of counting it as the model abstaining. `counts.output_not_asked` is how
  many cases that covers. In format 5 a Claude Code case's frozen checks are work evidence, so its
  lines are asked when the record holds a check or a written file.
- `basis`, per case and constraint, what a judged result rests on: `tool` only when it cites a check
  with a recorded result, `account` when it cites what the agent said or did (a written file shows
  the agent acted, not that anything checked it), `person`, `derived`, or empty
  where nothing was judged. A Goal `consistent` resting on the agent's account is never counted as
  tool-reported; `counts.goal_consistent_on_account` is how many there were.
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

## Case format 5: a per-case intent and frozen checks

Format 5 (`v: 5`) is what DRC-4666 scores the Claude Code producer against. It has no shared
yardstick. Each case carries every format 4 field, plus:

| Field | Meaning |
|---|---|
| `intent` | `goal` and `lines`, one to six `{text, source}` outcome lines, as a reader would save them. Each line is its own constraint, `line_1` onwards, marked and scored on its own. An optional `at` stamps when the intent counts as typed, and `window_start` opens the evidence window as a stored revision's would; without them the intent counts as typed at 1.0, before every session end. |
| `tool_output` | Claude Code only: `tails`, each check's redacted output tail by call id, and `changed_after`, the `[call id, check line]` pairs a later command may have changed. Both as a press read them at `captured_at`. |

Build a packet with `mark_abstention.py --freeze <spec>`. It spends nothing. The spec is a local
file listing, per case, the `harness`, `sid`, `project`, `captured_at`, the `row` lifecycle
(`state`, `finished_at`, `ended_at`), the `intent`, and for Claude Code optionally the
`transcript` path. The freeze reads the session's facts from the board and keeps only those dated at
or before `captured_at`. It never keeps a board check: those are computed over the whole transcript,
so a later run would reach back into the moment. It rebuilds the checks and the press reads from
the transcript as it stood at `captured_at`. It refuses a capture taken before a recorded turn
stop or end had settled.

A frozen case is `recorded` only when the machine's own records vouch for it. Otherwise it is
`synthetic`: it is marked and scored, never counts toward the coverage floor, and the rubric's word
for it does not change that. `unconfirmed` lists why, as closed tokens:

- `transcript-outside-projects`: the Claude Code transcript is not under `~/.claude/projects`.
- `transcript-other-session`: its records do not all name this session id.
- `lifecycle-unconfirmed`: the dashboard's stores did not observe the lifecycle the spec gives. A
  `working` row needs a history observation in `working` at `captured_at` itself. A turn stop needs
  an `idle` observation whose `last_activity` is the `finished_at`. An end needs the ends store's
  stamp. The freeze reads `cargento-history.json` and `cargento-ends.json` from `--store-home`,
  `~/.cargento` by default, never from the packet's own directory.

A Codex case is a recorded history `working` observation frozen at its last activity, because
Codex has no session-end hook and is never read at a turn stop.

The scorer repeats these checks at score time for every case the packet calls `recorded`, because
the packet is hand-editable: the transcript found for that sid under `~/.claude/projects`, its
session id, and the lifecycle in this machine's history and ends stores. A case that fails any of
them is scored as `synthetic` and never meets the floor, whatever the packet or the rubric says.

The scorer passes each Claude Code case's frozen checks to the producer as a press with a
tool-output grant would, and reads a Claude Code turn stop as the route does. It refuses to start
when the destination for those checks cannot be named. The marker shows the intent, each line with
its source and the frozen ledger, every check with its result words and its output tail, and asks
the goal and then each line. Where the record holds no check or work result, the lines are fixed
at `abstain` without asking.

Scoring refuses before its first call unless every case in the packet is marked, each on exactly
its own constraints, with `judge` or `abstain` and nothing else. The authorization says every case
is marked before any reading runs. A Claude Code result is written only from a format 5 packet.
`--producer codex` may report but not score, because no Codex spend is authorized for this
qualification.

### The spend ledger

Every model call is charged, before it runs, to one ledger at a fixed path,
`~/.cargento/drc-4666-spend.json`. It is shared by every producer and every packet directory, and
it never follows `CARGENTO_HOME`, so a fresh packet directory does not start the count again. Its
`~`, like every other path this check trusts (the installed CLI, `~/.claude/projects`, the
dashboard's stores), is the account's home from the password database, never `HOME`, and
`--score` refuses to run while `HOME` names another directory. It
holds case ids, times, statuses and two digests per call: the marks file's and the cases and
rubric's. It stops the run at 19 calls across every run, because the owner authorized twenty and
the browser walk after a pass is the twentieth. `--max-calls` can lower that and never raise it. A
case the cap stopped is withheld as `spend-cap`.

- The cap check and the charge happen under an exclusive lock, so concurrent runs cannot pass it.
- A missing ledger is an empty one. A ledger that cannot be read, or holds anything but this
  script's own shape, refuses every call and is left as it is.
- Once a call is charged, the key is frozen. `mark_abstention.py` refuses to write marks or
  `--reset`, and `--score` refuses a packet whose marks or cases hash differently from the calls
  already charged. A mark written after an output was seen is agreement, not a mark.
- The committed result records `ledger_chain`: the first charge id, the number of calls and a hash
  chain over their ids. A later `--score` refuses, and the marker stays frozen, while the ledger
  does not begin with that chain, so deleting or replacing the ledger does not unfreeze the key.
- `--report` flags a result as stale when the ledger holds a call charged under other digests, or
  no longer begins with the result's chain.
- `--resume` re-reads the local results and re-calls only the cases whose call failed
  (`withheld:model-failed`). It carries the other records over only when they hash to what the
  ledger recorded as the last run, so a hand-edited outcome is refused.

`--probe-argv` is the one way to watch what the CLI sends without spending: it calls the verified
CLI once with a fixed sentence, only when `ANTHROPIC_BASE_URL` points at a local stub, and writes no
result and charges nothing. It refuses any destination that is not this machine.

The owner's commands, in order. `CARGENTO_HOME` holds the packet; the ledger does not move with it:

```bash
export CARGENTO_HOME=~/.cargento/abstention-claude-<date>
python3 scripts/mark_abstention.py --freeze "$CARGENTO_HOME/freeze-spec.json"   # spends nothing
python3 scripts/score_abstention.py --report          # preflight, spends nothing
python3 scripts/mark_abstention.py                    # y/n/s/q per constraint, every case
python3 scripts/mark_abstention.py --report
# write the kind tags and one expectation per asked constraint into abstention-rubric.json now:
# changing the rubric after the first call changes the inputs digest and the ledger refuses it
python3 scripts/score_abstention.py --score --producer claude
python3 scripts/score_abstention.py --score --producer claude --resume   # only if a call failed
```

## How to argue with a result

A case id is `sha256("<harness>|<sid>")[:16]`. Whoever holds the cases file can resolve it; nobody
else can, which is the point. The outcome per constraint is one of `withheld:<reason>`, `unparsed`,
`abstained`, `judged:consistent` or `judged:departure`. `withheld` means the producer refused before
the model ran, so the case says nothing about the model, and it is counted for neither side.

The verdict is `failed` when a case marked should-abstain judged or the rubric records a false
reassurance (a mark of `abstain` on that line is not enough on its own), `blocked` when a rubric
entry left a required judgement unscored, `short` when no case failed but
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
`recorded` entry names a case in the cases file by id and carries no body, and against a format 5
case its `expect` is keyed `goal` and `line_1` onwards. Every asked constraint of a rubric case is
required: the goal, and each outcome line when the case's record shows work. A required constraint
with no expectation lands as `unscored:missing-expectation`, and an expectation under a key the
case does not have is counted as `unscored:unknown-constraint` without its key being copied. Any
`unscored:*` blocks a pass, and a case with one does not count toward coverage; a `synthesised` entry
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
