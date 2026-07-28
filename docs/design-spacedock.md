# Design: Spacedock stage cartography

The durable rationale behind how Cargento answers "where is each work item on its workflow?" for a
Spacedock first officer. It records the decisions and the alternatives that were tried and rejected.
The rejected ones are the expensive part, because without them they get re-attempted.

The security contract these reads operate under is owned by [`SECURITY.md`](../SECURITY.md), and the
user-facing behaviour is owned by the skill body. This file explains *why*, not *what*.

Each decision keeps a stable `S-N` anchor, and code comments may cite them by name. Grep the
identifier across `*.py`, `*.toml` and `*.md` before renumbering anything.

---

## The problem these decisions answer

A first officer is one Claude session driving many entities through many workflows, dispatching one
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
which is why `sd_read_workflow` returns a `resting` set alongside the ordered stages. Live workers
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
