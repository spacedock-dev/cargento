# Session identity: project labels and display ids

How Cargento answers "which session am I looking at, and where is it running?" Both halves
were reported together in DRC-3962 and DRC-3963, because together they made distinct
sessions render as one.

The code is `cargento_runtime/sessions.py` (identity, shape, freshness, display ids) and
`cargento_runtime/aggregate.py` (dedup, ordering, the per-harness failure boundary). Collectors
produce rows; neither of those two files knows which harness a row came from, which is what keeps
identity one rule rather than ten. See
[`design-runtime-architecture.md`](design-runtime-architecture.md).

## The reported symptom

A user running three agents out of one worktree saw two of them. In their words:

> i have 2 codex and 1 claude started from subspace, but i am only seeing 1 codex and 1
> claude. also the project path is not normalized across harnesses.
> `git-spacedock-research-spacedock-subspace` vs `spacedock-subspace`

Two independent defects, and the second one hid the first.

## D-1: one project rule for every harness, `<parent>/<basename>`

Nine collectors each derived the project label their own way. Eight took the basename of a
working directory. Claude took its encoded `projects/` directory name with the home prefix
stripped, so one worktree read `subspace` on a Codex row and
`git-spacedock-research-spacedock-subspace` on a Claude row.

`project_from_cwd` is now the single rule. It returns the last two path segments, using the
host's own path module, and returns `(home)` for the home directory itself. Collectors apply
their own fallback when it returns empty.

Two segments rather than one because sibling worktrees are routinely all named the same
thing. `recce/cargento` and `agy-subagents/cargento` are different work; `cargento` twice is
a dashboard that lies. This matters more after the normalization, not less: making labels
agree across harnesses also makes them agree across directories that merely share a
basename.

A path under the home directory is labelled relative to it. Without that, `~/foo` reads
`<username>/foo`, which puts the account name in a UI column and disagrees with the
`project_label` fallback that strips exactly that prefix. The two derivations have to land
on the same string or the unification is only skin deep.

The comparison against home goes through `normcase`, which folds Windows case and separator
spelling and preserves length. `C:\Users\jared` and `C:/Users/jared` and `c:\users\JARED`
are one directory, and a store may record any of them.

### Rejected

- **Splitting on both separators by hand.** Tempting, because a Windows path read on POSIX
  keeps its backslashes. `docs/design-cross-platform.md` already rejected the generic version
  of this helper and the same reasoning applies here: `\` is a legal POSIX filename
  character, so the split turns one directory named `my\proj` into two. Cargento only reads
  stores written on the machine it runs on, so `ntpath` on Windows and `posixpath` elsewhere
  are the correct semantics, and `windows` is injectable so one runner covers both.
- **Comparing against home with string equality.** Passes on POSIX and silently mislabels on
  Windows, where the same directory has several legal spellings.
- **Accepting a relative or unresolved cwd.** `..` and `relative/path` produced labels like
  `cargento/..`. Returning empty and letting the collector fall back to the harness name is
  the honest answer.

## D-2: read Claude's working directory from the transcript, not the directory name

Claude is the only harness whose store hands a collector no path. It encodes one into the
`projects/` directory name by replacing every separator with `-`, which is lossy:
`~/git/spacedock-research/spacedock/subspace` and a single directory literally named
`git-spacedock-research-spacedock-subspace` encode identically, so the basename cannot be
recovered by splitting.

The transcript records carry the real `cwd`, so `claude_session_cwd` reads it from the head
and the encoded name survives only as the fallback for a transcript too young to have
written one. That fallback stays whole rather than guessing at a split.

### Rejected

- **Splitting the encoded name on `-`.** Ambiguous by construction, per above. It would
  silently mangle any project whose directory name contains a hyphen, which is most of them.
- **Reverse-engineering the encoding from the home prefix.** Only recovers the prefix, which
  is the part already being stripped. The interesting segments stay ambiguous.
- **Leaving Claude on the encoded label and changing the other eight to match.** Would make
  every harness display a full path, which is what the report was complaining about.

## Antigravity multi-folder workspaces

Antigravity supports adding directories to an active workspace with `/add-dir`. Its CLI log
then writes the plural `workspaceDirs=[...]`, while `cache/last_conversations.json` still maps
the conversation to its primary workspace. Treating the whole log value as one cwd makes
`project_from_cwd` label the card from the last added directory.

The cache keeps only the most recent conversation id for a workspace. That id anchors the
primary path to the raw `workspaceDirs` context, and every conversation observed in that same
context inherits it. Metadata events are then replayed in log order, so logs still supply a
workspace for contexts missing from the cache and newer log-only values replace older ones.
Anchor discovery reads the bounded identity-bearing heads of older logs too: the cached
conversation can be quiet while a sibling in the same context remains active. Only logs inside
the requested activity window contribute sessions and prompts, so recovering an old anchor does
not put stale work back on the dashboard.

### Rejected

- **Using the whole `workspaceDirs` value as a cwd.** It combines several paths and labels the
  session from the final one.
- **Protecting only the cached conversation id.** Older sibling conversations share the same
  workspace context but no longer appear in the one-entry-per-workspace cache. They would keep
  the combined log value and split one project into two labels.
- **Filtering logs before discovering anchors.** The one cached conversation can fall outside the
  activity window before another terminal in the same workspace does. Filtering first loses the
  only unambiguous primary path even though the older log head is still safe to consult for
  identity.
- **Splitting the value on spaces.** Paths can contain spaces, and the log field carries no
  escaping that would make such a split reversible.
- **Always keeping the first log value.** Rotated logs are read oldest to newest. A session
  absent from the cache should retain the newest workspace the CLI reported.

## D-3: display ids widen per harness until unique

Session rows showed the first 8 characters of the session id. That is safe for Claude, whose
ids are random uuid4, and wrong for Codex, whose ids are UUIDv7: the leading 48 bits are a
millisecond timestamp, so agents launched together share leading hex by construction.

A fan-out in one directory therefore produced rows with the same harness badge, the same
project and the same displayed id. Four sessions reproduced locally as `019fa752` four times
over. That is the whole of the reported "sessions collapse together": nothing was ever
dropped, the rows were just indistinguishable. Fixing the project label alone would have
made it worse, since the project column started matching too.

`assign_display_ids` widens the shown prefix until it is unique, with a floor of 8, the way
git shortens a commit sha. `sid` stays whole; only the display string grows.

The group is `(harness, project)`, because that is exactly what the row prints beside the id,
so those are the rows a reader has to tell apart. Grouping by harness alone looks equivalent
and is not: four UUIDv7 agents started in the same millisecond need 16 to 18 characters to
separate, and every other Codex row would inherit that width for nothing. That is the same
objection this document raises against a fixed longer width, arriving by a different route.

### Rejected

- **A fixed longer width.** Trades one arbitrary number for another and still collides at
  enough concurrency, while making every row noisier for the common case that never needed it.
- **Showing the id tail instead of the head.** Works for UUIDv7 specifically and breaks the
  ordering intuition of every other harness. It also silently reintroduces the bug the day a
  harness adopts a random suffix scheme.
- **Deduplicating the rows.** They are not duplicates. `dedupe_sessions` was investigated
  first and correctly keys on the full `sid`; collapsing distinct sessions is the bug, not
  the fix.
- **Disambiguating with the session title.** Fan-out agents in one workflow are frequently
  dispatched with identical prompts, so the titles collide exactly when the ids do.

## D-4: the calm ledger orders rows on nothing that ticks

Calm mode gives each session one row in a table that repaints every five seconds. The first
version sorted each rank group by age, which is what the design source did. On the fixture that
looked right, because a fixture's ages are frozen. Against a live board it shuffled: two
generating sessions swapped places between refreshes, and the row a reader had their cursor on
moved out from under them.

Age itself is not the problem. Age is `generated - last_activity`, one clock shared by the whole
payload minus a per-session timestamp, so two idle rows hold their relative order forever. The
problem is a *working* row, whose last activity is always inside `WORKING_THRESHOLD_SEC` by
definition. Ordering those by age sorts them on which one wrote most recently, which is noise at
the resolution the column even prints.

So each row carries a `sortAge` that is its real age everywhere it means something and zero for a
working row, and the session id, which never changes, breaks every remaining tie. A row now moves
when its state changes and not otherwise. This is the same call `collect()` already makes
server-side when it sorts on `sid` rather than `last_activity`, arrived at independently on the
client, which is a reasonable sign it is the right one.

### Rejected

- **Bucketing age to whole minutes, then falling back to the id.** The first attempt at a fix, and
  it was worse than no fix. Ages advance together but cross their minute boundaries at different
  moments, so a row that ticked over fell behind its bucket-mates by id and then jumped back ahead
  a minute later. Measured on a 28-row board: one row crossing a boundary reordered 26 of them.
  Coarsening a key does not make a sort stable, it just makes the instability periodic.
- **Freezing the order and only re-sorting when the set of sessions changes.** Hides real state
  changes, which is the one thing the reader is watching for. A session going from working to
  needs-input has to move to the top immediately.
- **Sorting on the payload's own array order.** `collect()` does sort deterministically, but on
  `(state_rank, sid)`, which is not the order calm mode wants, and it reorders whenever any
  session's state changes. Depending on it would couple the two silently.

The row's `where` column follows D-3 to its conclusion. `project · session id` rarely fits in one
column of a dense table, and truncating the tail eats the id, which is the part D-3 widened
precisely so the row could be told apart. Only the project gives way; the id is never cut.

## What was ruled out along the way

Worth recording, because the issue as filed pointed at collection and the cause was
presentation:

- The Codex collector. Two rollout files, distinct ids, identical cwd, both fresh, produced
  two rows.
- `dedupe_sessions`. Keys on the full `sid`, not the display id.
- The frontend. Both the rate ring buffer and the notification map key on `harness + ":" +
  sid`, and no project-based grouping exists in the render path.

## Cursor

Cursor rows were hardcoded to the literal `cursor`, so every Cursor session in every
repository shared one label.

Its `meta` table is the only place a workspace path could live, but the payload is
undocumented and no Cursor store was available to read while this was written. The key
spellings `_CURSOR_CWD_KEYS` tries are therefore inferred from the VS Code lineage, not
observed, and the ranking is a guess at which is most trustworthy.

A shape check alone would not be safe under that uncertainty. In the same family
`workspace` routinely holds a `.code-workspace` *file*, and `workspaceStorage/<hash>` paths
are everywhere in chat storage; either passes an "is it an absolute path" test and yields a
confident wrong label, which is worse than no label. So a candidate is accepted only when it
resolves to a directory that exists on this machine. That makes the guess validate itself:
a wrong key almost never points at a real local directory, and when every key misses, the
row keeps the `cursor` fallback it had before. The `file://` spelling is accepted too, since
it is the canonical serialization in that family and rejecting it would make the whole read
a silent no-op indistinguishable from "Cursor records no workspace".

This is the one part of the change that is inference rather than observation. It is written
to fail closed, but a real store should be read before trusting the key list.
