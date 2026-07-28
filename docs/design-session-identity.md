# Session identity: project labels and display ids

How Cargento answers "which session am I looking at, and where is it running?" Both halves
were reported together in DRC-3962 and DRC-3963, because together they made distinct
sessions render as one.

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

`project_from_cwd` is now the single rule. It returns the last two path segments, splitting
on both separators regardless of host, dropping a bare drive letter, and returning `(home)`
for the home directory itself. Collectors apply their own fallback when it returns empty.

Two segments rather than one because sibling worktrees are routinely all named the same
thing. `recce/cargento` and `agy-subagents/cargento` are different work; `cargento` twice is
a dashboard that lies. This matters more after the normalization, not less: making labels
agree across harnesses also makes them agree across directories that merely share a
basename.

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

## D-3: display ids widen per harness until unique

Session rows showed the first 8 characters of the session id. That is safe for Claude, whose
ids are random uuid4, and wrong for Codex, whose ids are UUIDv7: the leading 48 bits are a
millisecond timestamp, so agents launched together share leading hex by construction.

A fan-out in one directory therefore produced rows with the same harness badge, the same
project and the same displayed id. Four sessions reproduced locally as `019fa752` four times
over. That is the whole of the reported "sessions collapse together": nothing was ever
dropped, the rows were just indistinguishable. Fixing the project label alone would have
made it worse, since the project column started matching too.

`assign_display_ids` widens the shown prefix until it is unique within each harness, with a
floor of 8, the way git shortens a commit sha. Per harness, so one colliding Codex pair does
not churn every Claude row. `sid` stays whole; only the display string grows.

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
repository shared one label. Its store records a workspace path in the same undocumented
`meta` payload the session name comes from, so `_cursor_meta` now reads both and accepts a
value only when it looks like an absolute path. The harness name remains the fallback,
which is what every Cursor row showed before.
