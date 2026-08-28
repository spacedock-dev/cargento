# Design: Spacedock stage cartography

The durable rationale behind how Cargento answers "where is each work item on its workflow?" for a
Spacedock first officer. It records the decisions and the alternatives that were tried and rejected.
The rejected ones are the expensive part, because without them they get re-attempted.

The security contract these reads operate under is owned by [`SECURITY.md`](../SECURITY.md), and the
user-facing behaviour is owned by the skill body. This file explains *why*, not *what*.

The parsers live in `cargento_runtime/spacedock.py`, which knows nothing about any harness. The
collectors call it, and each decides for itself whether a session is a first officer before asking
for strips: `collectors/claude.py` from the `agentSetting` in its transcript head,
`collectors/pi.py` from the boot envelope itself, per S-5. That boundary is what keeps
Spacedock cartography testable without a transcript, and it is why `spacedock.py` may import
`claude_data` for shared reads but never a collector. See
[`design-runtime-architecture.md`](design-runtime-architecture.md).

Each decision keeps a stable `S-N` anchor, and code comments may cite them by name. Grep the
identifier across `*.py`, `*.toml` and `*.md` before renumbering anything.

---

## The problem these decisions answer

A first officer is one session driving many entities through many workflows, dispatching one
ensign subagent per stage of work. The session card shows the subagent pills already, but a pill
name is not progress: `spacedock-ensign-drc-3832-review` says a worker exists, not that `drc-3832`
is four stages from done. Cargento is a passive reader. It never runs `spacedock`, never talks to
the first officer, and must derive the whole picture from files something else already wrote.

## S-1: Read state, not the boot snapshot, for where an entity is

The first officer's `spacedock status --boot` output lands in its transcript and carries a
`dispatchable` list of `{slug, current}`. It is tempting to treat that as the entity roster. It is
not one. It is a snapshot of what was ready to dispatch at the instant of boot.

The failure this caused was total, not partial. A first officer that boots against an empty queue
and takes work in later, via an intake mod, which is the *normal* operating mode for a long-lived
officer, reports `dispatchable: []`. Re-boots go on reporting `[]` because by then the entities are
claimed rather than dispatchable. Anchored on that list alone, the strip never rendered at all for
the sessions that most needed it: the ones that had been running for hours.

The entity-state directory is the authoritative, current answer. Boot names it absolutely
(`entity_dir`), one non-recursive `scandir` enumerates it, and each entity's own frontmatter
`status` names the stage it is parked on right now. `dispatchable` is kept as a third source behind
live workers and the state directory. It is still Spacedock's own statement about what is next to
move, which is worth showing for an entity resting on the initial stage.

## S-2: Never guess an entity slug from a worker name

A live worker is named `spacedock-ensign-<slug>-<cycle?>-<stage>-<cycle?>`, and it is the freshest
evidence available, naming an entity that is being worked *this second*. Recovering the slug by
stripping the stage and any cycle-shaped tokens from the right looks obvious and is wrong twice:

- Real slugs end in cycle-shaped tokens of their own. `…-pr-1506-r3` is one entity, not `…-pr-1506`
  on round 3.
- A guessed slug matches every workflow that declares the same stage. Two of this repository's own
  reference workflows declare `review`, so both `…-pr-1573-review` and `…-drc-3832-review` would
  attribute to both workflows, and each entity would render twice, once under a workflow it has
  nothing to do with.

So attribution is anchored. The slug must already be known from the state directory or the boot
snapshot, and candidates are matched longest-first so a slug that prefixes another cannot win. This
is why S-1 is load-bearing beyond its own display: without a roster there is no anchor, and the
live-worker evidence is unusable too.

## S-3: In flight means moving

A mature queue holds far more entities than it is running. One live state directory measured 31
entities, 29 of them parked on `intake`. Rendering all of them would push the two that were actually
moving off the end of a 12-row cap, leaving a strip that is technically complete and practically
useless.

So the state directory contributes only entities on a stage that is neither initial nor terminal,
which is why `spacedock.read_workflow` returns a `resting` set alongside the ordered stages. Live workers
and `dispatchable` entries bypass the filter. Both are positive evidence that a specific entity is
moving *now*, whatever stage it sits on.

## S-4: Old state is history, not work

A first officer discovers every workflow in the project, not only the ones it is driving. Workflows
retired months ago still have entities frozen mid-pipeline, and by S-3 those look exactly like work
in flight. A card for a session working two PRs would list a dozen entities last touched in a
different quarter.

Entity files are therefore bounded by the same freshness window every collector applies to a
session, and it is checked against the `stat` before the file is opened, so stale state costs no
read. The window arrives as an argument rather than being read from a clock inside the parser, per
D-4 in [`design-cross-platform.md`](design-cross-platform.md).

## S-5: On Pi, the boot envelope is its own classifier

Claude answers "is this a first officer?" before reading anything: the `agentSetting` sits in the
transcript head, one cached lookup, and a session with nothing to do with Spacedock opens no project
file. Pi writes no equivalent. Nothing in a Pi transcript announces the role.

So the Pi collector uses the boot envelope for both jobs. Finding one proves the session is a first
officer, and the same payload carries the paths. Only a first officer runs `spacedock status --boot`,
so presence is good evidence, and it needs no new source.

It costs two things, both accepted rather than overlooked. Every Pi session pays a bounded transcript
scan on refresh, where Claude pays a cached lookup and stops; each pass is capped at
`spacedock_boot_scan_bytes` and progress is cached per path (S-7), so a settled transcript costs
one `stat`.
And classification now depends on tool output rather than a launch-time declaration, which is a
weaker signal: tool output is whatever a tool printed. The guards that matter sit downstream and are
unchanged, so a crafted envelope still has to survive path canonicalisation, the symlink and
identity checks, and the `commissioned-by: spacedock@` discriminator before anything is published.

Rejected: inventing a Pi-side marker, which needs Spacedock to write something Pi does not write
today and strands every existing session. Rejected: hoisting classification above the collectors,
which buys nothing while each harness answers the question from a different field, and moves
harness knowledge into a module whose whole point is not having any.

## S-6: The boot envelope has a third provenance shape, and it is Codex's

The provenance rule is that boot output counts only when it arrives as *command output*, because
scanning the raw line would let anything a person pasted nominate an absolute path for Cargento to
open. `spacedock.tool_result_text` is where that rule is applied, and it read two shapes: Claude's
`type: "tool_result"` content blocks and Pi's `toolResult` role message.

Codex writes neither. A Codex rollout record has no `message` key at all, and the tool echo lives
under `payload`. The consequence was quiet and total: 0 of 458 local rollouts yielded a boot
envelope, so `observer.resolve_workflow` found no workflow and every Codex session running one
published an empty stage. Nothing failed, and nothing said so.

Two payload spellings carry it, and each carries `output` in two value shapes. All four were
counted on the local rollout store rather than read off an API description, which is the evidence
standard `docs/captures/README.md` sets for an adapter gate:

| payload type | `output` is a string | `output` is a list of `{type, text}` blocks |
|---|---|---|
| `function_call_output` | 15,730 records | 897 records |
| `custom_tool_call_output` | 2,956 records | 18,477 records |

Of the 23 rollouts naming a `definition_dir` anywhere, 22 carry one on one of those two payload
types and 14 carry an envelope the reader actually parses: 9 on `function_call_output`, 6 on
`custom_tool_call_output`, one file carrying both. That is 50 records, 43 of them on
`function_call_output`. Ten of the 14 files have one inside the `spacedock_boot_scan_bytes` head
window, which is what takes the count of Codex sessions with a resolvable workflow from 0 to 10.

The wider figure, 18 files and 12 of them on `function_call_output`, counts something else and is
recorded here so nobody re-derives it and thinks the reader regressed: it counts a file whose
`definition_dir` record carries a `{"command"` candidate object in its tool output, parsed or not.
Four of those 18 hold a candidate the envelope reader rejects.

Nothing else under `payload` is read. A `function_call`'s own `arguments` field carries the same
JSON on the way in, and it is the model's request rather than the command's output, so accepting it
would give a model's proposal the authority of a tool result. That is the same distinction the Pi
role gate makes, and it is why the branch tests the payload type rather than looking for
`definition_dir` anywhere under the record.

Rejected: also reading `event_msg`/`item_completed`. It looked like a third path, because 3 further
rollouts mention a `definition_dir` there and nowhere else. They turn out to be `CommandExecution`
items, which record the shell invocation together with its captured stdout, and 0 of the 4 such
records carry a boot envelope at all. The mention is the command line, not its output. So the shape
would add a maintenance surface and no session.

## S-7: Read the envelope as a rendering, and walk the window to find it

S-6 settled *where* the envelope may come from. Two later measurements showed that both remaining
assumptions, about *what it looks like* and *where in the file it sits*, were wrong. Each was
independently fatal. The strip published nothing at all while a workflow was plainly running, and
said so as "A workflow exists, but nothing is fresh enough to show", which reads like a freshness
problem and is not one.

It arrives rendered, not raw. The reader looked for the literal `{"command"` of a JSON object. The
first officer's own skill tells it to run `status --boot --identify --json` and to "consume JSON,
not the human table", but nothing tells it to *echo* that JSON, and both real first-officer sessions
measured here piped it through a formatter. What reached the transcript was an indented key/value
rendering, and the object never appeared. Across 120 transcripts over 21 days the JSON branch
matched exactly one file, and that one was this repository's own test fixtures catted into a tool
result. The feature had never once fired on a real session.

So the fields are read line by line rather than decoded, which survives any rendering that keeps
`key: value`. The trust model is unchanged, deliberately. A rendered path is gated on a top-level
`command: boot` exactly as the JSON branch is gated on `envelope["command"] == "boot"`; only
column-0 keys are read, so a nested decoy cannot nominate one; and every downstream guard still
stands between an extracted path and anything published, meaning the `_usable_dir` shape check,
canonicalisation, the symlink and identity checks, and `commissioned-by: spacedock@`.

It is also not in the head. The scan read the first `spacedock_boot_scan_bytes` on the reasoning
that boot output is written once at session start, so the read could be amortised on `(path, size)`.
A first officer greets and discovers before it boots: the two sessions measured booted at 69% and
73% of the way through their transcripts, at bytes 803,503 and 821,199 of files near 1.1 MB. Claude
Code writes single records up to 109 KB, so a head window is small in lines even when it is large in
bytes.

Raising the cap was rejected. It only moves the guess, and it is the expensive direction: the cache
key is `min(size, cap)`, so a live transcript below the cap misses on every write and re-reads the
whole file under the collection lock. Instead the window walks. Each pass reads at most
`spacedock_boot_scan_bytes` of not-yet-scanned bytes and remembers how far it reached, which keeps
the per-refresh cost the head scan had while covering the file eventually. A pass stops on a line
boundary, so an envelope straddling the edge is read whole on the next one, and a record longer than
the whole window is stepped over rather than stalled on. The cost is latency, not coverage: an
envelope two windows in appears on the second refresh rather than the first.

## Rejected alternatives worth keeping rejected

Run `spacedock status` ourselves. It would answer every question above directly and correctly. It
also turns a passive reader into something that executes a project binary found on the host, on a
5-second timer, for every session on the dashboard. The entire read surface is deliberately "files
other things already wrote". This would be the only exception, and it would be the one with
arbitrary side effects.

Watch for later `status` envelopes instead of adding a state read. Cheaper in principle, since it
adds no new read surface, and it fails in practice. The transcripts examined contained `boot`
envelopes and nothing else: a first officer's routine status checks are not emitted as JSON, so
there is no fresher envelope to find. Widening the 512 KiB head scan to the whole transcript would
have made the collection pass quadratic in transcript size for no additional data.

Require the entity directory to sit inside the workflow directory. This is the natural containment
check, and it would silently re-create the original bug for any `split-root` workflow, which
legitimately stores state elsewhere. Containment is replaced by a per-file discriminator: the
filename must be a well-formed slug and the frontmatter `status` must name a stage that workflow
declared. Both paths come from the same tool result and carry the same authority, so the guard
belongs on what is read, not on where it sits.

Parse the entity file for more than `status`. Titles, verdicts, scores and PR numbers are all
sitting right there in the frontmatter, and each one is project content that would then flow to
`/api/data`. Only the stage is needed to place an entity on a spine, so only the stage is taken.
