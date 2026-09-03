# History store security scope (DRC-4330)

This is the security contract for the local session history store decided in DEC-6 (Linear
DRC-4234), written before the store exists so the implementation PR is held to a published standard.
SECURITY.md describes shipped behaviour only, so the section lives here until the code lands.

The history PR (DRC-4044) must do three things with this file: promote the section below into
SECURITY.md unchanged, apply the three intro amendments listed after it, and delete this file.

## The section, verbatim

The following lands in SECURITY.md between "Dismissals" and "The ask lane (`ask_operator`)", beside
the other file Cargento keeps under its own directory. It contains no relative links on purpose, so
it can move without rewriting.

---

## Local history (the session history store)

The board is rebuilt from the harness stores on every start, so a restart used to leave it with no
memory of sessions that already ran. Cargento keeps its own history of what it observed, on this
machine, so the board can open knowing what happened before it was last closed.

One rule fixes the rest: the store holds nothing the live snapshot does not already serve. What is
kept is session identity, states and the transitions between them, gate open and close, turn
boundaries and their timings, and tool names and counts.

What is never written to it:

- Prompt text, of any session, at any point, whatever field carries it. Not a row's title, which is
  derived from a prompt; not `last_prompt`; and not a session's state detail, which can carry a
  permission prompt's own text, an open question's, or a plan's first line, and which the bounded
  record of state disputes already omits for exactly that reason.
- Tool input, in whole or in part, including any substring of a command.
- Paths. Neither a session's working directory nor any path a tool touched.
- File contents, of any file.

The store may never widen that list: a field that is not already published on the live board is not
a field history may keep. The condition runs one way only — the board publishes prompt text and
project paths, and the never-list above bans both.

The store lives under Cargento's own directory, next to the dismissals file, and is written the way
that file and the state file are. It is opened owner-only with the mode in the `open` call, so it is
never briefly world-readable, and it is written through a temp file and a rename, so a reader
mid-write sees the old file or the new one. The mode is advisory, exactly as it is for the state
file and the dismissal store: Windows ignores it, and root reads it either way.

Retention is 14 days by default, with a size cap, and both are configurable. Eviction is by age
first, oldest observation dropped first, so a session that fell out of the window cannot be brought
back by raising the cap. The age window and the size cap bound the store together, and raising
either does not stop the other applying.

The store is on by default. A digest of what happened while the user was away exists only if the
history was being kept before they left, and Cargento already writes local state on the user's
behalf by default in the dismissals file and the observer sidecar. The trust cost of that default is
retention, and the bound above and the delete below are what answer it.

The off switch is `--no-history`. It mirrors `--no-git` at every one of that flag's sites, including
the branch that forwards flags to a respawned daemon, so a restart cannot re-enable a store the user
disabled. With the store off nothing is written and nothing is read back: the board opens with no
memory, exactly as it does today.

`--forget` deletes the store and exits. It is a one-shot command, in the family of `--stop` and
`--status` rather than the family of per-run switches, because what it does is not reversible by
running the next command without it. It removes the file whether or not the store is enabled, and it
adds no endpoint: nothing over the loopback port can delete history.

A store that cannot be read is discarded rather than repaired. Corrupt bytes, an unreadable file, a
version the running build does not understand: in every case the store is dropped, the board starts
empty, and the header reports the reset, so a silent loss of history is never mistaken for a machine
that did nothing.

Nothing in the store ever leaves the machine. It adds no outbound request, no forwarder and no
endpoint; the network posture described in Scope is unchanged by it.

A violation of any boundary in this section is a security bug: a field in the store that the live
board does not publish, prompt text or tool input or a path or file content reaching it by any route,
a write that is not owner-only or not through a temp file and a rename, an unbounded store or one
evicted by anything but age first, a store still written while the feature is off, a respawned daemon
that re-enables it, a history file reachable over the port, or any part of the store leaving the
machine.

---

## Intro amendments that ride with the promotion

Three sentences elsewhere in SECURITY.md stop being true the day the store ships, and only these
three change:

1. Process lifecycle opens "The server writes three files, all under `~/.cargento`" and enumerates
   them. The count rises to four and the enumeration gains the history store, described in Local
   history above. The next sentence in that paragraph, "One forwarder writes a fourth", becomes
   "a fifth", because it counts from the server's total: amending one sentence without the other
   leaves two files called the fourth. The store's filename is H1's to choose and this contract does not
   fix it.
2. Scope invariant 2, "Read-only against harness stores.", enumerates every writer with care: seven
   mutating endpoints, six of them in memory, one `POST` that writes disk, one forwarder, and one
   `GET` that writes a sidecar. The history store is a writer of a kind that enumeration does not
   reach, because it is written by the server continuously rather than on a request edge. The
   invariant gains one sentence at the end: the server also keeps its own history of what it
   observed under `~/.cargento`, written as it observes rather than in answer to a request, and
   never a harness store, so the read-only rule stands unchanged.
3. Dismissals opens "Marking a session handled writes one file, and it is the only thing Cargento
   writes on your behalf". The store is a second such file and a continuous one, so the clause
   claiming sole occupancy goes. The rest of that sentence, and everything after it about how the
   dismissals file is written, is correct as it stands and is not touched. This one is easy to miss
   because the false part is a subordinate clause rather than a heading or a count, and promoting
   the section without it leaves SECURITY.md contradicting itself two sections apart. The same claim
   is shipped in two more places, listed below, and this amendment is not done until they go too.

No count in Scope's network paragraph changes. The store adds no outbound request and no endpoint,
so invariant 1 is untouched, and `--forget` adds a command rather than a route.

## What else the build PR does with this file

- `HOW_TO_USE.md` gains the two user-facing entries: a `--no-history` row in the "Turn a feature off"
  table, and `--forget` documented with the one-shot commands rather than in that table, since every
  other row there is a reversible per-run switch and this one deletes a file. Neither flag parses
  today, so neither entry may land before this PR.
- `SKILL.md` gains a `--no-history` row in the flag table, and two things already in that file change
  with it. Its own "The server writes three files, all under `~/.cargento`" count rises to four with
  the store enumerated — the count only, because the sentence after it names the forwarder without an
  ordinal, unlike SECURITY.md's copy — and its `--no-dismiss` row drops the sole-occupancy claim
  amendment 3 removes.
- `--help` carries that sole-occupancy claim too: `--no-dismiss` calls the dismissals file the one file
  Cargento writes on the user's behalf, in `cli.py`, so H1 amends that string alongside the other two.
  Two docstrings repeat it as well; they are not user-facing and nothing here turns on them.
- The contract test lands here. `tests/test_documentation.py` binds the git probe's section to the
  code by asserting both that SECURITY.md says "The off switch is `--no-git`." and that the parser
  accepts `--no-git`. The history analogue is owed by this PR and could not be written before it:
  until `--no-history` parses, the assertion would be a grep over our own prose.
- `docs/promise-map.md` gains whatever the shipped capability earns, judged then rather than now. A
  promise enters that file only when a shipped capability backs it, so nothing may be written there
  ahead of the store.
- The section above is promoted unchanged and this file is deleted, both in that same PR. Leaving
  the file in place states the contract in two places and lets them drift.
- How the history is stored on disk, what the size cap's value is, and where the retention constant
  lives are implementation choices this contract does not make. It fixes what may be kept, how it is
  written, how long it survives, and how it is turned off and deleted.
