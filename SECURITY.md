# Security policy

## Scope

Cargento ships three kinds of component that touch the network. The dashboard server
(`cargento/skills/cargento/server.py`, whose code is the `cargento_runtime` package beside it)
reads local coding-agent session stores (transcripts, task
files, SQLite databases) and serves them over HTTP. When the usage feature is on, the server also
makes the quota poll described in Usage quota reads (the quota fetcher); it carries no session
data. The observer model is the one path that can send session content off this machine. It is
off unless explicitly enabled and disclosure consent accompanies a focused refresh.
[Observer model calls](#observer-model-calls) states its bounds. The opt-in UI's Space fonts are
packaged into its page, so
loading either interface makes no request to a font provider. Four small forwarders ship beside it,
each wired into a harness's own configuration by the user or by the plugin: `notify_hook.py` POSTs
a Claude `Notification` payload to the dashboard, `event_hook.py` posts command-hook lifecycle
events for Claude and Codex, `agy_hook.py` posts Antigravity's hook events, and
`statusline_hook.py` posts Antigravity's status-line state. All four share one transport, so the
loopback check, the proxy suppression and the redirect refusal have a single implementation.

One of them could do harm if it were registered in the wrong place. Antigravity's `PreToolUse` hook
may return a `decision` that allows, denies or re-prompts a tool call, and there is no harmless
output at that position: an empty object there reads as a DENY, so a reporting hook would block the
user's work rather than pass it through. The safety property is that `agy_hook.py` is never
registered at `PreToolUse`. Where it is registered, after a tool call and after an invocation, it
prints exactly `{}` and nothing else on every path including every failure path, and a test asserts
that for malformed, empty and valid input alike. Irreversible actions below carries the same rule
for the hook that matches destructive shapes.

The third kind is one stdio MCP server, `mcp_server.py`, described under The ask lane below. It is
not a forwarder and shares none of the four's transport: a harness spawns it, it speaks JSON-RPC on
stdin and stdout, and it reaches the dashboard on loopback under the same three guards.

The posture rests on two invariants:

1. Localhost unless the operator says otherwise. The server binds `127.0.0.1`, and every forwarder
   and the MCP server refuse to reach anywhere but loopback, ignore proxy environment variables, and
   do not follow redirects. `--host` is the one way that first clause moves, it is an explicit
   argument nothing sets for you, and what it costs is under Known and accepted.
   Three kinds of outbound request are in scope, two implemented and one written down before it
   exists, and they are named apart rather than counted together because they are not the same
   exposure. The quota poll carries a vendor token out and quota numbers back, and no session
   content whatever. A harness invocation, described in Light harness usage below, can carry
   session-derived text: it is the one pathway by which the operator's own words may leave this
   machine. A nudge to an endpoint the operator supplies, described in Off-machine nudges below,
   would carry two counts and nothing that names a session. The observer model implements the
   second pathway behind explicit enablement and consent. Nudges remain unbuilt; these are the
   contracts the first feature to use each has to satisfy, `--no-harness-usage` and `--no-reach` included.
   Nothing else Cargento does reaches the network. One further pathway is written down and reaches
   no network on Cargento's own account: the hand-off request in Hand-off requests below writes one
   line to a socket on this machine, and what travels afterwards travels on the receiving session's
   own connection, which is why it is named here rather than counted above.
2. Read-only against harness stores. They are opened read-only and never written. Eight endpoints
   mutate, and six of them only in memory: `POST /api/notify` updates needs-input state, and
   `POST /api/usage` stores a quota figure a harness published to its own status-line command.
   `POST /api/events/<harness>` also mutates in memory only, behind the capability described under
   Known and accepted, and so do `POST /api/ask`, `POST /api/answer` and `POST /api/ask/withdraw`,
   which register a question a session asked, record the option the reader chose, and drop a question
   whose asker has stopped waiting for it, all three described under The ask lane. The long
   poll that delivers an answer, `GET /api/ask/<id>`, drops that question from memory once it has,
   which is the delivery completing rather than a change a caller asked for. Two write to disk.
   `POST /api/dismiss` writes the sessions you marked handled, and
   `POST /api/annotate` writes the goal and expected output you typed against a session. Both write
   Cargento's own state under `~/.cargento` and never a harness store, so the read-only rule above stands
   unchanged. What the first holds and how to clear it is in Dismissals; the second is one file,
   `cargento-annotations.json`, bounded by a session count and a revision count rather than by age,
   redacted on the way in like every other prompt-derived string, written owner-only through a temp
   file and a rename, and turned off entirely by `--no-annotations`. It is the only store holding
   prose you composed rather than anything a harness published. One forwarder writes too:
   `statusline_hook.py`'s deduplication memo under the same directory, which holds a normalized state
   name and a timestamp and nothing about the session's content.
   One `GET` reads wider than the rest, and is named here for that reason rather than for the
   count above. `GET /api/annotations` serves the prose you composed, for every session you have
   annotated, including sessions no longer on the board. That is a wider scope than `/api/data`
   ever had, which serves only what is live. It is same-origin only, refuses a cross-site
   navigation, answers 503 under `--no-annotations`, and reads the annotation store alone rather
   than session history, so words you withdrew with a clear are gone from it. It is not on the
   refresh loop: the words leave the server when the Intent log is opened, and the route's own
   docstring records that reasoning. The POST-route inventory in the test suite cannot see a `GET`,
   so this paragraph is the accounting for it.

   One `GET` writes as well, which is why it is named here rather than left to the count above.
   `GET /api/observe` is a trigger rather than a poll: it derives one session's goal, stage and open
   block and records the answer as a sidecar under `~/.cargento/observer/`, again Cargento's own
   state and never a harness store. Its two components are the harness key and the session id, and
   both must match `[A-Za-z0-9._-]{1,128}` before either reaches a path. `records.safe_text`
   bounds a string and strips control characters, and passes a separator straight through, so the
   grammar is what keeps the write inside that directory rather than the join. The file holds
   prompt-derived text, so it is written the way the state file and the dismissal store are: a temp
   file created owner-only and renamed into place, with a failed write reported as a failure rather
   than raised at the request. Published text records what that redaction covers. What the route
   reads is covered by Project reads below: the transcript, and the same two kinds of frontmatter a
   stage strip reads, under the same guards and the same `--no-spacedock` switch.
   The git probe runs inside a repository the user chose rather than a harness store. Git writes
   nothing there on the probe's behalf, and Cargento runs no program of its own; a filter driver the
   operator has configured globally, git-lfs being the common one, can still be invoked by a
   committed attribute and may then write where it likes, which the git-reads section below states
   in full. The focus command writes nothing
   anywhere, reads nothing back, and touches no harness store; `POST /api/focus`, the ninth POST
   route, is the one that mutates nothing at all. The server also keeps its own history
   of what it observed under `~/.cargento`, written as it observes rather than in answer to a
   request, and never a harness store, so the read-only rule stands unchanged.

Anything that weakens either invariant is a security bug: a bind reaching an address the operator did
not ask for, a request admitted that the bind's own Host gate should have refused, file reads outside
the documented store paths and the project-read contract below (however the path was derived),
writes to harness stores, running any program inside a user's repository other than the probe
described in Repository git reads (the end-of-session probe), running a program to reach a session's
terminal other than the focus command described in Reaching a session's terminal (the focus
command), or the hook client reaching a non-loopback destination. Those two exceptions are a
whitelist of two scoped clauses and not a general permission to execute: written generally the
sentence would make documented security bugs of three paths Cargento already ships, the native
notifier's `osascript`, `--daemon`'s respawn of the server, and the quota fetcher's Keychain read.

## Project reads (Spacedock stage strips)

One feature reads paths that are not under a store root. When a session declares itself a Spacedock
first officer, or in Pi's case is taken to be one because its transcript carries a boot envelope,
Cargento reads YAML frontmatter, and only frontmatter, from two kinds of file, so it can show where
each entity sits on its workflow's stage spine:

1. one workflow `README.md`, for the ordered stage list and which stages are initial or terminal;
2. the entity files in that workflow's entity-state directory, for each entity's current `status`.

That is the whole of it. No other project file is opened, and the only directory listed is the
entity-state directory itself, through one non-recursive `scandir`. Nothing is ever walked.

Neither path is guessed. The first officer's own `spacedock status --boot` output, already recorded
in its transcript, names the workflow directory and the entity-state directory as absolute paths.
Cargento uses those values and nothing else. Before any file is opened, all of the following must
hold, and a path failing any one is skipped silently:

- the directory value is absolute, contains no NUL, and encodes for this filesystem. A lone
  surrogate survives JSON decoding, and the checks below it raise `UnicodeEncodeError` rather
  than `OSError`, so an unencodable path would escape every handler here;
- the path is canonicalised with `realpath`, and the README must still resolve inside the workflow
  directory (`commonpath` containment), so a swapped entry cannot redirect the read;
- every file opened is a regular file and not a symlink. This is checked with `lstat`, opened with
  `O_NOFOLLOW` where the platform has it, and confirmed with an `fstat` `(st_dev, st_ino)` match
  against the `stat` the cache key was built from, so a parent-directory swap between the two cannot
  seed the cache from a different file. Windows has no `O_NOFOLLOW`, so there the guarantee rests on
  the `lstat` classification alone and a racing reparse-point swap could still be followed. That is
  the same unclosable class as the `FILE_SHARE_DELETE` window described in the skill body;
- the README frontmatter declares `commissioned-by: spacedock@`, which is Spacedock's own workflow
  discriminator.

The entity-state directory is deliberately not required to sit inside the workflow directory. A
`split-root` workflow legitimately keeps its state elsewhere, and that path carries the same
authority as the workflow path, having come from the same tool result. A per-file discriminator
stands in for containment instead: an entity file counts only if its name is a well-formed slug
(`^[a-z0-9][a-z0-9-]*[a-z0-9]$`, which also excludes `_archive/` and any report left beside the
state) and its `status` names a stage the README declared.

Hard caps: at most 64 KiB read from a README and 8 KiB from an entity file, 400 frontmatter lines
scanned, 32 stage names taken, 120 characters of the README's `title`, 96 entity files read per
workflow (newest first), 12 entities rendered per workflow, and 8 workflows per session. Both reads are cached on
`(realpath, st_mtime_ns, st_size)`, so an unchanged file costs one `stat` per refresh. Entity files
older than the dashboard's freshness window are not opened at all.

Only derived scalars reach `/api/data`: stage names (each validated against Spacedock's
`^[a-z0-9][a-z0-9-]*[a-z0-9]$` grammar), entity slugs, cycle markers, and the README frontmatter's
`title` scalar, shown as the workflow's goal line in the session view. That title is the one piece of
project-authored *text* on the surface, and it is there because a stage spine says where the work is
without saying what it is for; it is capped at 120 characters and passes through the same
control-character and bidi stripping every untrusted string does. No other file text, no frontmatter
body and no filesystem path is ever published, and the page HTML-escapes every value.
Pass `--no-spacedock` to switch the feature off. The read surface is then exactly the documented
store paths.

## Repository git reads (the end-of-session probe)

One feature runs a program inside a directory the user chose. Cargento already records each
session's working directory; when a session ends, the server runs one bounded git command there, so
the board can show that a session stopped with work still in the tree.

The probe is exactly this command, or there is no probe:

    git -c core.fsmonitor= -c core.hooksPath=/dev/null -c status.showUntrackedFiles=normal --no-optional-locks status --porcelain

`status.showUntrackedFiles=normal` keeps non-ignored untracked entries visible. Measured
2026-09-08: one untracked file was suppressed by `status.showUntrackedFiles=no` through local
config, `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_COUNT`. This key override closes all three routes;
other operator configuration, including ignore and filter rules, remains in effect. Clean means
no porcelain entries under these rules, not discovery of ignored content.

Two things about how it is spawned are part of the boundary rather than details of it.

**The executable is resolved, not looked up by the child.** `git` above is the name the contract
prints; what runs is an absolute path resolved once against a PATH the probe controls. Measured
2026-09-07: with the bare name, any empty or relative element ahead of the first element holding a
real `git` supplied the binary instead, and it resolved from the session's own directory, which is
the one directory whose contents must not be trusted to supply a program. The rule is order rather
than position: a leading `.`, a leading empty element, an interior empty element and an interior `.`
all hijacked, and trailing forms did not.

Every non-absolute PATH element is dropped, and the resolution refuses a relative answer as well.
Both ends, not either: the first version of this dropped a named pair, the empty element and `.`,
which reads like the whole property and was not. Measured 2026-09-07, a bare `relbin` survived that
filter, and then the two directories parted company: the resolver validated a `git` under the
dashboard's own working directory while the child resolved the same relative string against the
directory being probed, which is session-supplied. It published seven changed entries for a
directory that is not a repository at all. So the filter now drops anything a resolver would
resolve against a working directory, and the resolution returns nothing for an answer that is not
absolute even if it is ever handed a PATH from somewhere other than that filter. A PATH left with no
absolute element publishes no reading at all rather than falling back to the ambient one.

**The child's environment is scrubbed of `GIT_DIR` and `GIT_WORK_TREE`.** Either one points git at a
different repository entirely. Measured the same day: a probe of a clean repository published a
dirty reading belonging to another one, and a directory that is not a repository at all published it
too, so the check that the path is a directory does not help.

The mechanism is subprocess execution rather than a file open. That is what separates this feature from
every other read Cargento performs, and the three safety flags are load-bearing. The first two were measured
2026-08-28 at git 2.55.0 across four fresh repositories, one probe each, from an identical racy-clean
state; the third was measured 2026-09-07 at git 2.55.0 with git-lfs 3.8.0:

- Without `--no-optional-locks`, the probe writes `.git/index`. The write is git resolving a racy
  stat, not a per-invocation habit, and a repository a live session is editing is the normal case
  for it rather than a corner case.
- Without `-c core.fsmonitor=`, a `core.fsmonitor` script configured in the repository is executed
  under Cargento's identity. A repository can carry that setting in from wherever it was cloned.
- Without `-c core.hooksPath=/dev/null`, a filter driver installs its own hooks inside the
  repository. Hashing a tracked path whose committed attributes name a driver invokes it, and
  git-lfs then asks git where hooks belong and writes there: four files at mode 0755, named
  `post-checkout`, `post-commit`, `post-merge` and `pre-push`. `.git/index` was untouched in that arm,
  so neither other flag sees it, and this one closes it by answering with a path git cannot write.

Each flag disarms a hazard the others do not, so none may be dropped. There is no fallback to a
plain `git status`.

### The residual: a filter driver can still run, and can still write

The third flag suppresses the hook installation and neither the invocation nor what the driver does
once running. Two separate residuals, and the first is reachable by a clone.

**A committed attribute alone reaches the operator's own driver.** Measured 2026-09-07: a fresh
`git clone` of a repository whose only unusual artifact is a committed `.gitattributes` saying
`*.bin filter=lfs`, with `git config --local --get-regexp '^filter\.'` returning nothing at all,
ran `git-lfs filter-process` on one probe and gained
`.git/lfs/objects/d5/3e/d53eda7a…` inside the repository. The flag was present. The driver was
never carried by the clone: it comes from the global config that `git lfs install` writes, which
most machines with git-lfs already have. So this is clone-portable, and the write is driver-caused
rather than git writing on the probe's behalf.

**An arbitrary, attacker-chosen driver command needs `.git/config`.** A repository with
`*.x filter=pwn` committed and `filter.pwn.clean` set in its own `.git/config` had that command
executed by one probe, with the flag present. That half is not clone-portable, and there the
comparison with `core.fsmonitor` holds: both need the inspected repository's own config to name a
program. The comparison does **not** extend to the git-lfs case above, where committed content plus
a ubiquitous global install is the whole precondition. The two are kept apart here because blurring
them is what made the first version of this section wrong.

The trigger is a tracked path matching a filter attribute whose content git must hash, and **it does
not require a modified file.** A tree git itself reports clean invoked the driver on each of three
consecutive probes, because the racy-clean state that makes git hash the path is exactly what
`--no-optional-locks` declines to clear. So this recurs rather than happening once. What genuinely
reaches nothing is a repository with no matching tracked path: the attribute on its own, with
nothing it applies to, installed and ran nothing, measured.

No flag closes it, and this was looked for rather than assumed. `--attr-source` and
`GIT_ATTR_SOURCE` pointed at the empty tree do suppress the driver, and on a real git-lfs
repository they then report a merely-touched pointer file as modified, so the answer stops being
true. Clearing the driver with `-c filter.lfs.clean= -c filter.lfs.process=` makes git fail the
command outright, which publishes nothing. `diff-files`, `diff-index` and `ls-files -m` each invoke
the driver anyway, and the first two also call a touched LFS file modified. `status --porcelain`
has to hash the path to answer at all, and hashing is what runs the driver, so this is stated
rather than fixed.

`/dev/null` as a hooks path is measured on darwin. It names a location git can find no hook under on
any supported platform, and `tests/test_git_status.py` skips rather than passes where the mechanism
cannot be armed, so the Linux and Windows arms are unmeasured rather than verified.

### The residual: the reading is about the repository, not about the directory

`git status` discovers repository metadata by walking upward from the directory it runs in. The
probe passes the session's own working directory as cwd and passes nothing that bounds the walk.
With an ordinary `.git` directory and no working-tree redirection, it answers about the containing
repository. That walk has two outcomes, and only one of them is what a reader wants.

The common outcome is the right one, and it is why the feature is useful at all. A session working
in `repo/src/components` gets `repo`'s reading, which is the answer to whether that session left
work behind. Measured 2026-09-07 against this tree: a probe at a dirty repository's root and a probe
three levels inside it published an identical `dirty=True, changed=3`, while a directory with no
repository above it published `null`.

The wrong outcome is a `$HOME` that is itself a repository. A session working somewhere under such a
`$HOME`, in no project repository of its own, gets `$HOME`'s reading, and its row then reports a
dirty tree that has nothing to do with that session. Anyone who keeps dotfiles as a repository
checked out at `$HOME` can reach this. It is not reachable on the machine these measurements were
taken on, where `git -C "$HOME" rev-parse --show-toplevel` finds no repository at all, and that is a
fact about one machine rather than a property of the design.

Decided 2026-09-07, and recorded rather than fixed (DRC-4442). Three measurements settled it, and
the first is the one to read before proposing anything here:

- The confinement this was originally filed with does not work. `GIT_CEILING_DIRECTORIES` set to the
  probed directory changed nothing in either arm: the probe three levels inside the repository still
  published the parent's `dirty=True, changed=3`, identical to the same probe with no ceiling set.
  Only a ceiling at the probed directory's parent changes the outcome, and that publishes `null` for
  any session not sitting exactly at a repository root. So this is not a fix that was weighed and
  declined on cost. It was measured not to do the thing it was proposed to do.
- Confining the walk costs a reading people rely on. Of 48 recorded session directories still
  present on the machine measured, 30 sat at a repository root, 10 inside a repository below its
  root, and 8 in no repository at all. A parent ceiling would blank one in four of the
  repository-backed ones, and `null` means no reading available, so such a row could not even say why.
- The targeted alternative reopens DEC-3. Refusing only when the resolved repository root is `$HOME`
  keeps the subdirectory case and closes the dotfiles case, but learning that root needs a second git
  command, and this section's first bound is that the probe is exactly the one command above or there
  is no probe.

So the trade was a common correct reading against a hazard nobody here can currently reach, and the
ruling keeps the reading. What it costs a reader is written down rather than left to be discovered: a
git reading names a session's directory, but the repository git discovers may be an unrelated
ancestor such as `$HOME`.

**Local metadata can also select a different working tree (DRC-4492).** Git can read
`core.worktree` from the discovered `.git/config` and compare another directory's contents against
that repository's index. Measured 2026-09-08: a clean source pointing at a directory with nine
untracked entries returned `dirty=True, changed=9`; removing the setting restored clean/zero.
This is accepted local-config trust, distinct from inherited `GIT_WORK_TREE`, which the probe
scrubs. A `.git` file selects metadata elsewhere; it does not by itself establish that the remote
directory's contents were measured. In the gitfile control, changing files beside the target
metadata left the reading clean, while an untracked file beside the gitfile made it dirty. Metadata
selection and working-tree redirection are separate mechanisms. The probe retains its one-command
design and does not confine either one.

What is published, per session, is two fields and nothing else:

    {dirty: bool | None, changed: int | None}

Both fields are nullable, and `null` means no reading available: never attempted (including refused),
attempted without a usable result, or retired after resumed work. It makes no clean-tree inference.
The probe fires on `session_ended`, and most harnesses do not emit that event today, so most rows
carry `null`. `changed` counts porcelain entries rather than files: git collapses an untracked
directory into a single entry, so a new directory holding three files is one entry, not three.

What is never read:

- File contents, of any file, at any point.
- Diffs and blobs. Nothing asks what changed inside a file, only that something did.
- Branch and upstream state of any kind. The branch name, its tracking branch, and how far ahead or
  behind it sits are all outside this feature.

Porcelain output names paths. Those pathnames are matching hints and are never echoed to
`/api/data`, the same rule and the same wording this document applies to `cwd`.

The cadence is one-shot, on the `session_ended` edge. Never a poll, never on demand, and never on a
turn stop: the completion stamp written when a turn stops is a different edge, and probing there
would put one subprocess in the user's repository per turn for the life of the session.

The cadence is not a bound on how many probes run at once, and that took a second gate. One edge per
session at most once each still allowed 240 live probes per harness and 960 across the four event
sources, because the event budget refills for the whole of a probe's ten seconds, and each one is a
real `git status` in a real repository. So a session already being probed is refused a second probe,
and the process holds at most 32 in flight across every harness.

The two gates cost different things, and only one of them costs a stale reading. A session refused
because its own probe is already running keeps the reading that probe produces, which can be up to
ten seconds old and stays until another session end arrives. A session refused by the ceiling
publishes no reading at all: no first probe ran for it, and releasing a slot re-dispatches nothing.
There is no automatic recovery without another eligible end event. Measured with the ceiling set
to 2 and four distinct ends: after every in-flight probe drained and collection ran, the two probed
sessions read `dirty=True, changed=5`, both refused ones read null, and the dispatch count stayed
at 2. Redelivering `session_ended` for a refused key in the same process dispatched a third probe
and supplied its reading. The decision to retain refusal is recorded in
[N-9's rejected list](docs/design-needs-input.md#n-9-idle-was-two-situations-and-only-an-event-can-separate-them).

The off switch is `--no-git`. The probe is on by default and that flag turns it off. It mirrors
`--no-spacedock` at every one of that flag's sites, including the branch that forwards flags to a
respawned daemon, so a restart cannot re-enable a probe the user disabled. With the probe off no
git command runs at all, and both fields stay `null`.

A violation of any boundary in this section is a security bug: a git command other than the one
above, any of its fixed options dropped, a read of file contents or diffs or branch state, a pathname
reaching a response, a probe on any edge but session end, a probe while the feature is off, an
executable taken from anywhere but the resolved absolute path, a reading published about any
repository but the one git discovers from the directory it names, subject to the metadata and
working-tree selection described above, or any write inside the user's repository
that Cargento's own argv could have prevented.

Two of those clauses are narrower than they read, and both narrowings are the residuals above rather
than relaxations. A filter driver the inspected repository configured for itself may write where it
likes, and no argv Cargento can pass stops it; what the argv must prevent, and now does, is git
writing on the probe's behalf. And the reading clause says repository rather than directory on
purpose: git's discovery normally selects the containing repository, which is the correct answer
for a session in a subdirectory and the wrong one for a session under a `$HOME` that is a repository.
That selection also trusts local metadata: a gitfile can select external metadata, and
`core.worktree` can redirect the contents compared against the discovered index. The boundary does
not promise that those contents lie beneath the session directory or the discovered metadata.

## Reaching a session's terminal (the focus command)

One feature asks the operating system to put a window in front of the operator. Cargento already
knows where each session runs; when the reader clicks through to a session that is waiting on them,
the server runs one bounded command that raises that session's terminal, so the hunt across tabs
ends in one move.

### What runs, exactly

The command is a literal argv per named case, or there is no focus. A session matching no named case
is not focused, and the reader is told that rather than shown a control that does nothing.

Each argv is constant except for its target fields, and every one of those is substituted into a
fixed position rather than concatenated. No shell, no interpolation, and nothing from a request body
reaches any position. The tmux case carries three such fields, not one, and the grammars section
below states each one separately. Every command runs with stdin closed and under a timeout. A
failure is reported to the reader as a focus that did not happen, and never retried.

No working directory is set. The command does not run inside the user's repository, which is what
keeps Scope's repository-execution sentence meaningful rather than sidestepped.

### The named cases, and why the list is this short

Two arrangements are candidates today, because DRC-4382 measured identification for exactly two: a
session in a bare macOS Terminal.app tab, and a session in a tmux pane. The identifier differs by
harness even within one arrangement. A Codex hook keeps the controlling terminal and reads it
directly; a Claude hook does not, because its stdin is the payload pipe, so the device has to be
read one level up off the harness process. In a pane neither works and tmux's own client device is
what finds the window.

**One arrangement is now a named case and the other is not, and the difference is what was run.**
DRC-4385 ran the socket raise and recorded it: `switch-client` on a named socket moved the client it
was told to, with a negative control that held still recorded first. So the tmux socket case is
named, and it is what ships. The Apple Event case is not. DRC-4387 ran its arms and the one that
decides it, a daemon whose launching window has been quit, came back inconclusive: it moved a tab
but its two responsible-identity fields were null, so the record cannot say who issued the raise.
Until that is answered no Apple Event case may be named, and the paragraph below is why the bar is
set there.

This is the part most easily read too generously.
**DRC-4382 measured which identifier finds a terminal. It did not raise one.** The capture says so in
its own words: the lookup counts a tab and never activates one. So a raise command becomes a named
case only once it has been run and recorded, one case per platform, per multiplexer and per harness
where they differ, the way Usage quota reads requires a vendor's endpoint to be named before it
ships. A section listing commands nobody has run would repeat the failure of documenting bounds the
code will not accept.

**A tmux raise is two commands in two mechanisms, and the section admits that rather than hiding it.**
Selecting the pane is socket IPC to the tmux server; bringing the window that hosts the client to
the front is an Apple Event to the emulator. They fail independently, and the first is worth shipping
without the second: a selected pane in a client the operator then switches to by hand is the whole
value on a machine where the terminal is already visible. What the section forbids is reporting the
second as done when only the first ran.

**The two mechanisms carry very different permission costs, and the difference is measured.** The
socket path needs no operating-system permission at all. The Apple Event path is checked against the
Automation privacy permission, which macOS attributes to the *responsible* process rather than the
caller. Measured on the running daemon: after a double fork, a `setsid`, and three days re-parented
to `launchd`, its responsible process is still the Terminal window that launched it. So the sixteen
successful `osascript` calls recorded in DRC-4382 are that application automating itself while its
launcher is alive, which is an exemption rather than a grant.

The launcher outliving the daemon is not the shipping case; the daemon exists to outlive it. What
happens then is unmeasured, and the failure it risks is silent: an unbundled, ad-hoc-signed
interpreter carries no usage description, so a refused Apple Event returns an error the operator
never sees and cannot grant from the Automation pane. **No Apple Event case may be named until that
arm has been run**, and the socket case is not blocked behind it.

Linux and Windows are unmeasured, and the capture records them that way. Earlier desk research
suggested Wayland may not permit a background process to raise a window at all, and that Windows
Terminal has no documented way to focus a tab. That is research rather than measurement and this
document does not rely on it: both are simply not named cases, and either becomes one the same way
the macOS cases do, by being run and recorded.

**Not a named case means no target is recorded there, and that is enforced where the target is
stored rather than left to the raise to discover.** The device grammar below anchors `/dev/` and
admits no separator after it, so it refuses `/dev/pts/N`, which is the client device of every
terminal emulator, every ssh session and every mux-inside-mux client on Linux and the BSDs. A run
that recorded targets there would publish a focusable control for the ordinary Linux case and spend
two subprocesses answering false every time it was clicked, which is precisely what "A session
matching no named case is not focused, and the reader is told that rather than shown a control that
does nothing" forbids. So recording is gated on the platform the case was measured on, and
`focusable` is false on every other one. iTerm2 is unmeasured for the plainest reason, that it
is not installed on the machine that took the capture.

### The target, and what makes it safe to pass

The target is a **record shaped by its named case, not a single string**, and each field carries its
own grammar. The first draft of this document required every target to match
`^[A-Za-z0-9._-]{1,128}$`, the grammar `GET /api/observe` applies to a harness key and a session id.
That was wrong in a way that mattered: a tmux pane id is `%3`, and `%` is not in that class. The one
case needing no operating-system permission could not have shipped under it, and re-adding the `%`
in the argv builder is exactly the concatenation the previous section forbids.

So the grammars are per field, and each is as narrow as its field allows:

| Field | Grammar | Refused examples |
| -- | -- | -- |
| tmux pane id | `^%[0-9]{1,9}$` | `%3; rm -rf`, `-%3`, `%`, `%3 %4` |
| tmux socket name | `^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$`, passed as `-L`, a name and never a path | `-L`, `../x`, `/tmp/s`, `.hidden`, an empty string |
| controlling terminal device | `^/dev/[A-Za-z0-9][A-Za-z0-9._-]{0,119}$` | `--dangerously-skip-permissions`, `; rm -rf ~`, `../../etc/passwd`, `/dev/..` |
| tmux server pid | `^[0-9]{1,10}$`, compared and never passed as an argument | `-84321`, `84321;x`, `84321,0`, an empty string |

Every field is substituted into a fixed argv position and never concatenated, and a field failing
its grammar is not a raise.

**Each grammar refuses a leading dash in its own first character class rather than in a sentence
beside it, and that wording is the whole lesson of DRC-4381.** That issue shipped
`^[A-Za-z0-9._-]{1,64}$`, whose class contains a dash with nothing anchoring position 0, and review
reproduced a poisoned transcript filename turning a copied command into one that disables a
harness's permission checks. The first draft of this table repeated the same shape twice, and it was
caught only by running the patterns against the values the table claimed they refused. A raise puts
that class of value in an argv position rather than on a clipboard, so a prose promise that the
grammar does not keep is worse here than nowhere.

The device grammar anchors the literal `/dev/` prefix rather than allowing a path and checking it
afterwards, so traversal is refused by the shape rather than by a later resolve: no member of the
class after the prefix is a separator, and a leading dot is refused, which is what excludes
`/dev/..`.

Where a platform path builds a script rather than an argv, the field passes through the same
escaping the native notifier applies, and its grammar still runs first. **That is an escaping
precedent and not a permission one, and the difference decides what may be claimed.**
`notifications.notify_mac` runs `display notification`, a StandardAdditions command with no
`tell application` block, so it is never checked against the Automation privacy permission. A macOS
focus case would be the **first** Automation-checked call in this codebase, not the second, and
nothing about the notifier working says a raise will.

The record is derived from a session Cargento observed, and reaches the runtime through an
authenticated event rather than through the focus request. That is the honest statement, and it is
narrower than the first draft's "never taken from a request body": on the only measured path the
identity arrives in a hook POST to `/api/events/<harness>`, which is a request body, from a process
Cargento does not control. What bounds it is the capability on that route, which holds a forger to
the same operating-system user. The focus request itself names a session and never a target.

### The lookup is done at raise time, and an ambiguous answer is not a raise

Two measured facts make this a bound rather than an implementation note.

The device is not known to hold still. DRC-4382's verdict field is named `identifier_shape_held_still`
and claims exactly that: two devices mask to the same shape, so the capture establishes that the
readings agree and deliberately leaves unmade the claim that the device itself stayed put. The case
where it demonstrably moves is tmux, where detaching and reattaching from another tab moves the
client device inside one session. So a target is resolved at the moment of the raise and never
cached across a session's life.

A device does not identify one window. macOS recycles the device, and the capture caught it: in one
arm three Terminal tabs matched a single device with one of them busy, because finished tabs still
held a device macOS had handed out again. A lookup returning more than one live candidate is
ambiguous, and an ambiguous lookup does not raise. Picking one would be the same failure as the
naive readings below, arrived at from the other direction.

A session with more than one attached client is refused. This is the third decline rule and the one
no lookup prevents: a target can be correctly resolved, unambiguous, and the only live candidate,
and raising it still takes the view away from every other client attached to that session. On a real
machine that is another person, or another agent. The rule is therefore about who else is watching
rather than about whether the target was found, which is why it sits beside the ambiguity bound and
not inside it.

Refusing is the operator's ruling of 2026-09-06, taken over the alternative of raising anyway and
disclosing it on the control. The reasoning recorded with it: a reader often cannot know who else is
attached, and a disclosure they clicked past is not consent from the person whose view moved. The
cost is that the shared-session case is not served at all, and the section says so rather than
leaving a reader to discover it.

**The rule is decided on one command and enforced by the next, and the gap between them is named
rather than narrowed.** `list-clients` answers, the count is decided, and `switch-client` is spawned
about six milliseconds later: measured at a 6.1 ms median and a 7.4 ms maximum over ten runs, that
being server-side client spawn rather than the 0.05 ms of Python between them. A client attaching
inside that window is raised anyway. tmux offers no conditional switch, and closing the gap would
mean a fourth command (a server-side `if-shell -F '#{session_attached}'`), which the "a command
other than one of the named cases" clause forbids outright. So the bound is stated the way the
`core.fsmonitor` hazard and the Apple Event arm each are, and the violation clause below measures
what the lookup reported rather than a state of the world this feature cannot hold still. The worst
outcome in that window is another attached client's view moving; nothing is escalated, disclosed or
written.

### What is never done

Nothing is typed into a terminal. No keystroke, no text, no newline, by any path. The ask lane's
direction invariant is unchanged by this feature, and any implementation reaching for `send-keys`
contradicts it outright.

No harness store is written. No file inside the user's repository is read or written. No native
permission prompt is answered, and no agent session's state is altered: the conversation is
untouched, no turn is started or stopped, and nothing is typed.

**What a socket raise does change is the multiplexer session, and an earlier draft of this document
denied it.** It read "the window moves, the session does not", which is false of the only mechanism
this feature ships. `tmux switch-client` resolves the pane to its window and moves the tmux
session's current window; every client attached to that session displays the change. DRC-4385
measured it in both positive arms, and reproduced it outside them by steering one client and
watching the other follow. The sentence is corrected rather than softened, because the bound below
rests on the mechanism being described accurately.

The raise reads nothing back: its standard output is discarded unread, so no pane content, no window
title and no pathname enters Cargento.

**The two lookups that precede it do read, and saying so is the point.** The shared-session rule and
the ambiguity rule cannot be enforced without asking tmux which session a pane belongs to and which
clients are attached to it, so a section forbidding all reading would forbid its own bounds. What
those two commands return is bounded, held to the same grammars as any other field before it reaches
an argv position, used only to build the next command, and then dropped: none of it is stored,
published, logged or echoed to the reader. An earlier draft of this section said output was discarded
rather than parsed without qualification, which was false of the mechanism the same document
mandates.

### What the named case runs

The tmux socket case is three commands on the socket the session reported, in this order, or there is
no focus:

    tmux -L <socket> display-message -p -t <pane> '#{pid} #{session_name}'
    tmux -L <socket> list-clients -t <session> -F '#{client_tty}'
    tmux -L <socket> switch-client -c <client tty> -t <pane>

The first names the session and the server, and an earlier draft claimed less carefully that it
"proves the pane still exists". It proves that *a* pane with that id exists in whatever server holds
that socket name now, which is not the same pane. **A pane id is an ordinal on one tmux server, not
a name.** Kill the server, start another on the same socket name, and `%3` is somebody else's pane
in somebody else's session: reproduced on tmux 3.7c, where the second generation re-issued `%0`
upward and a raise on the stale target moved an attached client onto an unrelated window and
reported success. That is the misdirected raise Known and accepted names, arrived at without any
lookup failing. So the pid the server reports is compared against the pid that reported the pane,
and a mismatch is a decline. It costs no extra command, and it is also what makes a socket name that
resolves on a *different* server of the same user (the hook and the daemon need not share a
`TMUX_TMPDIR`) a decline rather than a raise on that server's pane.

The second is what the two decline rules are decided on: no client attached is nobody to raise for,
and more than one is the shared session this document refuses. **It is counted by lines, not by
values.** `list-clients` prints one line per attached client, and a control-mode client (a
`tmux -C attach`, which is what another agent driving the same session looks like) reports an empty
`#{client_tty}`. A reader that dropped empty lines would count two attached clients as one and raise,
which is the shared-session case this document refuses outright. A client the device grammar cannot
name is then a separate decline, decided after the count, so such a client is refused rather than
invisible. Only the third moves anything.

### What the command can still cause

This section does not claim the command executes nothing but itself, and the reason is recorded
rather than assumed. The git probe's contract used to carry the stronger claim, that it "neither
writes there nor executes anything the repository supplies", and DEC-11 retracted it because a
reproduction falsified both halves: hashing a tracked path whose committed attributes named a filter
driver installed four hooks inside the repository and ran the driver, through a path the probe's two
flags were never written against. A third flag now closes the write; the invocation is stated as a
residual, because no flag closes it. The general lesson is the one this feature most needs. A
bounded command can still cause a program to run through a path its bounds never contemplated.

So the honest statement is narrower. A multiplexer and a window manager are programs the operator
configured, and what they do when asked to raise a window is theirs. That is the same trust already
extended by running them, and it is the `core.fsmonitor` hazard in smaller form. Naming it is what
keeps this section from inheriting an optimism that has already been shown to be wrong once.

### Who may trigger it

The operator's own action, and nothing else. The route is a POST carrying a per-run capability, so a
document navigation cannot take this path and a local process without the token cannot either.

**The capability is minted for this feature and delivered to the page, and saying so is the point.**
The first draft said the route carries "the per-run capability `POST /api/events/<harness>` uses",
and that was unsatisfiable by the caller the same sentence names: nothing under
`cargento_runtime/web/` knows about tokens, the page makes two `fetch` calls and one `EventSource`
with no header among them, and the per-run tokens live only in the state file at mode `0600`. It was
also the wrong token. The per-harness capabilities are derived per harness, so the token that would
focus a Claude session is byte-identical to the one `POST /api/events/claude` accepts, which is the
power to forge that harness's lifecycle state. Handing the browser that token to raise a window
would be a strictly worse trade than the raise is worth.

So focus gets **its own consumer key**, and it is delivered by injecting it into the served document
where the page bytes are handed to the server rather than by baking it into an asset. That seam
matters: the frontend's assembled bytes are pinned by digest in two test files, and a token in an
asset would make them non-deterministic. Injecting after assembly leaves those pins untouched.

Both halves of that matter and neither is decoration. A GET would repeat a gap this repository has
already been bitten by: an attacker page that gets the browser to open a Cargento URL in a tab reads
nothing back, and the "a cross-origin document cannot be read" reasoning does not cover the side
effect. On the quota fetch that side effect was a credential read. Here it would be a window
appearing on the operator's desk.

**What the capability separates, stated exactly, because the first draft claimed more than it
buys.** Loopback is not a per-user boundary, and the token rides in the served document: any other
account on the machine can `GET /` and lift it, so against that account this route stands where
`/api/dismiss` does. What the capability actually separates is a page from a document navigation and
from a local process that never fetched the board. The absence of per-user isolation is a documented
exposure of the whole server rather than something this feature introduces or repairs, and Known and
accepted below says so in the same words.

A rate ceiling and an in-flight gate, so a repeated or looped request cannot repeat the raise. The
route's check order is deliberately **not** the one `POST /api/events/<harness>` uses, and the
difference is the security property rather than an inconsistency. That route answers an unsupported
harness with a 404 before consulting the capability, because a harness name is public. **A session id
is not.** So here the capability is checked first, then the ceiling, and the session is looked up
last: to a caller without the token a live session and one that never existed are byte-identical
403s, and the route is not an oracle for which sessions the board holds. The focus route emits no
404 on any path: an unsupported session is the same 200 `{"focused": false}` as any other
unfocusable one, and the feature being off is a 503 rather than a 404 because it is a run-wide fact
that leaks nothing about any session, where a 404 would read as a build too old to have the route.

The ceiling is claimed after the body is read rather than before it. The body read is blocking and
carries no socket timeout, so claiming a process-wide one-slot gate ahead of it let a peer that sent
a length and then nothing hold focus shut for as long as it kept the socket open. Nothing in the
body distinguishes one session from another, so reading it first adds no oracle, and the gate still
precedes the raise, which is what "cannot repeat the raise" asks for.

### What is published, and what is written to disk

The response is a single boolean saying whether a focus happened: true only when the raise command
itself exited zero, and false alike for a raise that was attempted and failed and for one that was
never attempted at all, so a declined lookup and an unknown session are indistinguishable from a
failed command. No target identifier, no pathname and no window title is echoed. Nothing is written to disk by this feature, and nothing
leaves the machine.

### The off switch

`--no-focus`, and one other flag turns it off as a side effect. The capability comes from the
observation coordinator, which does not exist under `--no-events`, so that flag disables focus too.
A reader of this line would not otherwise have that fact, and a feature with an undocumented second
off switch is one nobody can reason about.

The flag disables the feature for a run, and it mirrors `--no-git` at every one of that flag's sites, including the branch that forwards flags to a respawned daemon, so a restart cannot
re-enable a focus command the operator disabled. With the feature off no command runs at all and the
control does not render.

### Known and accepted

A row's attribution is unverified, as the ask lane's already is. A forged registration cannot make a
window appear, because the target comes from a collector rather than from a request, but a reader
who clicks is trusting a row Cargento measured rather than one a session proved.

Raising a window is the first thing Cargento does that it cannot undo and that is visible outside
Cargento. A raise that lands on the wrong window puts a keyboard in front of a session the operator
did not mean to reach. DRC-4382 measured how that happens: for a session with no controlling
terminal at all, both obvious readings report a terminal, and it belongs to somebody else. So a
lookup that cannot identify a terminal must decline rather than fall back, and "the first ancestor
with a tty" and "an emulator variable is set" are both named here as refused readings.

### Violation

A violation of any boundary in this section is a security bug: a command other than one of the named
cases, a field reaching an argv position without passing its own grammar, any field beginning with a
dash, a target field concatenated into an argument rather than substituted into a fixed position,
an Apple Event case named before its arm has been run, a raise reported as done when only the
socket half of it ran, a keystroke sent into any terminal by any path, output read back or published, a working
directory set on the command, a focus triggered by anything but an authorized operator action, a
focus while the feature is off, a respawned daemon that re-enables it, a target resolved once and
reused rather than resolved at the raise, a raise on a lookup that returned no terminal or more than
one live candidate, a raise on a lookup that reported more than one attached client, or any read or write inside the user's repository.

## Usage quota reads (the quota fetcher)

The quota feature sends credentials but no session content. When the usage feature is on, the server polls each
supported vendor's usage endpoint so the dashboard can show quota windows: how much of the 5-hour
and weekly limits is used and when they reset, or for a vendor that meters spend rather than
requests, how much of the monthly billing period's allowance is used and when the cycle ends.

What is sent: the vendor's own OAuth access token, read from where the harness keeps it (the macOS
Keychain, or the harness's credential file on other platforms), carried in the request's
authorization header. Nothing else. No transcript content, no prompts, no paths, no project names,
no machine identifiers. What comes back is quota numbers: window utilization, reset times, and
per-limit entries. Session data never appears in either direction.

The endpoints, named exactly:

1. Anthropic (Claude Code, and any harness signed in with the same Claude subscription):
   `GET https://api.anthropic.com/api/oauth/usage` with the `anthropic-beta: oauth-2025-04-20`
   header.
2. Cursor: `POST https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage` with an
   empty JSON body and two headers, the bearer authorization and `Content-Type: application/json`.
   This is the RPC the Cursor CLI itself calls for its own `/usage` command, against the backend the
   CLI's config records. The credential is the session token in the macOS Keychain under the service
   name `cursor-access-token`. Read this next part before trusting the name: Cursor stores the
   identical value under `cursor-refresh-token`, so unlike Claude's quota-scoped token this one can
   also mint new sessions. Cargento sends it as a bearer token and never exchanges it, and the
   never-refreshed rule below is what keeps that true. macOS only, because that is the only platform
   where the token's location has been verified; elsewhere Cursor is absent from the band rather than
   read from a guessed path.
3. Codex: no endpoint. Codex writes rate-limit snapshots into its own session files, and Cargento
   reads them from disk like every other store.
4. Copilot: no endpoint. Copilot records its own per-request AI Unit consumption in a local session
   store, and Cargento reads that from disk. Its remaining entitlement is not published locally and
   is not fetched.

No other vendor is polled. A new vendor's endpoint must be named here before it ships. These
endpoints are not documented for third-party use: a vendor can change, break, or block them at any
time, and a failed poll means an empty tile, never a retry storm.

Token handling is read-only, one way, and never expands:

- The token is never refreshed. Refreshing from outside the harness can race the harness for its
  own session. A token the harness would refresh by itself, or one a vendor refuses, switches that
  vendor's usage display off and says which of the two happened; the remedy always belongs to the
  harness. This rule is what bounds the Cursor credential noted above: a value that could mint
  sessions is only ever presented as a bearer token, so the extra capability is never exercised.
- The token is never written to disk, never logged, and never served. `/api/data` and every other
  loopback endpoint must not carry it, in any form.
- Reading the token adds no write access anywhere. Harness stores stay read-only.

Consent and the off switch: the feature is disclosed before it acts, and it does not act until the
disclosure is answered. The first time the dashboard opens with the feature available, a banner explains the token read and
the request above, and carries the switch that turns the feature off. The setting can be changed
later from that same switch, which sits in the capacity strip beneath the fleet counts, and
`--no-usage` disables the feature for a run regardless of the stored setting. With the feature off, Cargento's network surface is exactly the
three loopback-bound kinds of component described above, and nothing is fetched.

**Answered, not assumed, and that is a change of 2026-09-04.** The mechanism is the `usage=1`
parameter: the server fires the fetch for no request that omits it, and the page adds it only while
the stored answer is `granted`. So an unanswered disclosure reads no credential and makes no
request, and neither does a declined one, and an unrecognisable stored value counts as unanswered.
The server enforces its own half rather than trusting the page: it ignores the parameter on a
document navigation, so a cross-site link that opens `/api/data?usage=1` in a tab is served the
body and arms nothing. That check is what makes the sentence above a property of the system and
not only of the page's URL builder.
This paragraph previously described the banner as shipped when the page had no banner, no configure
control and no stored setting at all: the next-UI promotion had dropped them, the page consequently
sent the parameter never, and nothing failed because nothing bound this paragraph to the page. The
promise was true only because the feature never acted. DRC-4376 restored the surface and DRC-4352
made the page ask, in that order. `test_next_capacity.py` binds the builder and the mount, and
`test_quota.NoFetchWithoutConsentTest` binds the server's refusal, so neither half can go missing
again without a red test.

Polling posture: responses are cached, and at most one request per vendor is made every five
minutes. No polling happens while no dashboard page is connected. `--diagnose` never triggers a
fetch; its output stays a report of local paths only.

A violation of any boundary in this section is a security bug: a request carrying anything beyond
the token, a token reaching a log or a loopback response, a refresh attempt, an unlisted endpoint,
or a fetch with the feature off.

Not every harness needs that request. One publishes its own quota to a user-configured command:
Antigravity pipes a state payload, including a `quota` object, to whatever its status-line setting
names, and a user who points that at `POST /api/usage` gets the same display with no credential
read and no outbound request at all. That payload also carries an account email and a transcript
path, so the receipt is never stored or served as it arrived: only the derived window percentages
and reset times are kept, built into a fresh record field by field. `--no-usage` stops this too: the
quota fields are dropped before storage, so nothing is retained and nothing reaches the band, and
the request still succeeds so a status line never sees an error. The dashboard's own switch is
narrower, and deliberately so. It governs the outbound fetch and the display, which is all it can
govern for a harness that publishes its quota locally: with it off, a pushed receipt is still kept
and still served on the loopback port, exactly as a disk-read tile (Codex, Copilot) is. Withdrawing
retention for a run is what `--no-usage` is for.

## Light harness usage (asking a harness a bounded question)

Cargento was built to sit outside harness usage: it watched, and it spent nothing. DEC-14 changed
that on 2026-09-04, because several of the answers the dashboard most wants to give cannot be
derived from a transcript by rule (whether a quiet session died or finished, what happened while
the operator was away, what a session's actual goal is rather than its opening instruction), and
each of those shipped withholding its answer instead. Cargento may now ask a harness a bounded
question and consume a little of the operator's own capacity doing it.

The observer model is the first implementation of this pathway. Its entry below names what it
sends, what it asks, and what it caps. Future harness callers need their own entry.

What makes this different from every other boundary in this document: it is the only one that sends
the operator's own words off this machine. The quota poll carries a token and numbers. A harness
invocation carries session-derived text, which is why invariant 1 names it separately rather than
widening the quota exception to cover it, and why the consent below is opt-in where `--no-usage` is
opt-out.

The bounds, all of which hold together:

- Opt-in, and off until answered. The feature does nothing until the operator turns it on. It
  is disclosed the way the quota fetch is disclosed, and for a stronger reason: this one spends
  their capacity rather than reading a number. A run with the setting unanswered makes no
  invocation.
- The observer uses the quota disclosure pattern: the browser supplies consent on the focused
  refresh request, and a document navigation never authorizes a call. Quota consent alone is not
  consent to send transcripts. This request parameter is not per-user authentication; a local
  process can imitate it once the operator has enabled the model for this run. The startup flag
  and the per-session in-flight gate bound that exposure. This prototype follows the cockpit's
  consent ruling; it does not implement the earlier proposed per-run event capability for this
  route.
- The operator's own harness, never a Cargento credential. Cargento invokes the harness the
  operator has already installed and signed in, non-interactively. It holds no API key, reads no
  new secret, and adds no endpoint to the list in Usage quota reads. Nothing about token handling
  changes, because there is no new token. A future feature that wanted to call a vendor API
  directly would be a different decision needing its own endpoint entry there.
- Redacted before it leaves, and bounded after. What is sent is prompt-derived text, so it goes
  through `records.redact_secrets` first and the bound second, the same order and for the same
  reason Published text gives. A key pasted into a prompt must not be handed to a subprocess any
  more than it may be published to the page.
- One bounded question. The generated prompt has a byte cap and the subprocess has a timeout.
  Codex is invoked ephemerally with user configuration and rules ignored, in a read-only sandbox.
  Explicit CLI overrides disable shell execution, hooks, plugins, apps, subagents, browser and
  computer tools, image generation, web search, and automatic project/skill instructions.
  These flags are not a proof of an empty tool set across Codex versions. The installed CLI and
  its provider remain a trust boundary; live tool suppression and provider retention are not
  verified by the dashboard's tests.
- Visible spend. Model metadata records whether a call ran or was refused. Provider token usage
  is not measured by this prototype; it must not present a zero cost as if it had measured one.
- Off switch. `--no-observer-model` disables calls for a run regardless of consent and overrides
  `--observer-model`. `--no-harness-usage` is an alias for that rollback. Both default to disabled
  without the opt-in flag. Windows daemon respawn currently omits the opt-in flag, so the model
  remains disabled there.

A violation of any of those is a security bug: an invocation with the setting off or unanswered, an
invocation carrying unredacted text, a credential read that this section does not name, tool access
beyond the documented CLI boundary, or an unbounded or untimed call.

What is accepted rather than solved: the invoked harness is another program with its own logging and
its own retention, and what it does with a prompt is outside Cargento's control. That is the same
trust the operator already extends to that harness by running it, but it is a real transfer and it is
stated here rather than implied.

### Observer model calls

`observer.CodexGoalModel` sends a generated prompt to the installed Codex CLI, which uses its
own authentication to reach OpenAI. This is the one path that can send session content off the
machine. It is off unless `--observer-model` was supplied. `--no-observer-model` always wins.

A focused `/api/project-context` refresh can summarize the focused session and up to three active
children whose assignment is unavailable. Merely opening a panel does not call the model. The
server also requires `observer_model=1` on that refresh, following the quota consent pattern;
the page must send it only after presenting the observer disclosure and storing its answer.
Only loopback peers can authorize a model call, and cross-origin Fetch Metadata is refused.
The response publishes the disclosure and byte cap. The backend does not treat `usage=1` as
observer consent. Console presents that disclosure for an exact session and stores the answer separately from
quota consent. Allowing summaries sends no request: each call requires the reader to choose
Summarize this session. Passive refreshes never carry model consent. Storage failure retains
the answer only for the current tab, using the same fallback as quota consent.

Transcript message content is redacted before extraction can clip credential shapes. The complete
generated prompt, including workflow stage, then goes through `records.redact_secrets` again
before UTF-8 clipping to **16,384 bytes (16 KiB)**. This caps the prompt Cargento hands to Codex,
not the CLI's added protocol or system instructions. Redaction recognizes credential shapes;
it does not remove arbitrary private prose. One call per session may be in flight, including
concurrent HTTP refreshes; the slot is released on failure. Each invocation has a **60-second**
timeout and returns at most `observer_goal_cap_chars * 4` bytes for a 200-character goal line.
A failed call falls back to local analysis. No raw model stdout or stderr is served or logged.

An absent or relative `shutil.which("codex")` result is refused. An absolute installed executable
is still trusted code; replacing it as the owning user is outside this boundary.

### Cockpit dispatch and terminal reads

Dispatch markdown is read from `XDG_RUNTIME_DIR/spacedock-dispatch` when available, with the
legacy `/tmp/spacedock-dispatch` path retained for existing producers. The legacy location is in
a shared temporary namespace where another local user can plant matching filenames; a filename
match alone establishes neither ownership nor safe contents. Both use the same checks:
`O_NOFOLLOW`, an anchored directory descriptor, realpath containment, regular files owned by the
current uid, and refusal of group- or world-writable files. Files larger than **65,536 bytes** are
refused, including growth during the bounded read. The directory must also belong to the current
uid. Platforms without the POSIX no-follow and ownership checks refuse this source. The 32 MiB
semantic backfill limit applies to transcripts, not dispatch artifacts: a dispatch is a short
Markdown file, and a transcript-sized allowance would let a planted artifact force a large read.

`SPACEDOCK_BIN`, when set, must be absolute; otherwise discovery resolves `spacedock` and also
requires an absolute result. Accepting a relative override or resolution could execute a planted
program when the working directory is on `PATH`. The child gets only `PATH` (the OS default),
`HOME` and `LANG`, a fixed argv without a shell, and a two-second timeout. Discovery output over 64 KiB is rejected after
capture; that is a parsing cap, not a streaming bound on subprocess output allocation.

The terminal registration file is created with mode **0600**. Its reader checks that exact mode,
uid, regular-file type and a **16 KiB** limit on the opened descriptor, refusing symlinks.
This capability trust check is POSIX-only; platforms without `O_NOFOLLOW` or `getuid`, including
native Windows, refuse terminal registration and report why. Shutdown uses a separate bounded
regular-file read of `server_generation` solely to decide whether to remove its own file. That
cleanup read does not require ownership or mode checks and never consumes a token, port or lease;
it preserves files with a different generation, nonregular files and files over the byte cap. The tmux
adapter attaches with `-r`; it exposes no pane-input method, HTTP input/control requests refuse,
and any client WebSocket frame closes the connection. Control lines and queued output each have
a **64 KiB** byte cap; overlong frames disconnect instead of growing the buffer. The snapshot
retains at most 12,000 characters. These bounds supplement the 512-frame limit.

The optional xterm JavaScript and CSS are vendored and served at `/assets/xterm.js` and
`/assets/xterm.css`. Only loopback peers with the ordinary origin checks can receive them, and
both return 404 unless the interaction feature is enabled. Serving an asset starts no terminal.

## Off-machine nudges (reaching the operator away from the desk)

Every signal Cargento sends today needs somebody in front of the machine: the macOS popup, the
browser notification in a tab that is open, the board itself. DEC-4 ruled on 2026-09-02 that
Cargento may reach further, in one shape and no other. The operator supplies one endpoint, and
Cargento posts a count to it.

This is the section to read before building that, and it grants nothing on its own. No shipped
feature posts to an endpoint the operator supplies; H2 (DRC-4034) is the first one that would.
Until it lands, the outbound surface is the quota poll and the explicitly enabled observer model.

Why this needs its own section rather than an entry under Usage quota reads: that section's
endpoint list is closed, and every entry on it is a vendor Cargento chose and verified. Here the
endpoint is one the operator pastes in, so the list cannot be closed and there is no vendor to
vouch for. What bounds the exposure is the payload rather than the destination, which is the
opposite way round from the quota poll and is why the two are not one rule.

The bounds, all of which hold together:

- Off until a URL exists. There is no default endpoint and no provider Cargento picked. With no URL
  configured nothing is posted, which is the shipped state today. DEC-4 refused a first-class push
  through a provider Cargento chooses, so an endpoint the operator already uses, ntfy, Pushover or
  a Slack webhook being the common ones, is the whole mechanism.
- One destination, and it is the operator's. Cargento posts to that URL and nowhere else, follows
  no redirect, and ignores proxy environment variables. Those last two are the rules the four
  forwarders and the MCP server already hold to; the loopback check beside them is the one rule
  that cannot carry over, since the whole point here is a destination that is not this machine. So
  a redirect cannot move the destination after the operator chose it, and that is what replaces the
  loopback guard rather than sitting beside it.
- Counts and states, never a session. The payload carries how many sessions need a human and how
  many finished and were never read. It carries no session name, no project, no title, no path, no
  prompt text and no request text. A person who gets a nudge opens the dashboard to find out which
  session it was, and the count is the whole message.
- Two counts, not three, and the missing one is deliberate. DEC-4's own wording offered a third,
  how many sessions went quiet, and what is missing is not the elapsed reading but the threshold.
  `last_activity` is published on every row and the board renders an idle duration from it, so
  `now - last_activity` is a reading the runtime already takes. What nothing decides is when quiet
  becomes worth a nudge: `config.py` holds no such threshold, and `events.py`'s `stale` is a
  different fact, a finish stamp contradicted by later activity rather than a session that went
  quiet. A third count would therefore have to name its own threshold, and naming one is a product
  decision this section is not the place to make. If DEC-4's third count is wanted, that threshold
  is the work, and it is smaller than it looks.
- Throttled, and a change is what triggers it. At most one post per configured interval, with a
  change in the counts as the trigger rather than a timer, so a board that is not changing sends
  nothing and a flapping one cannot turn into a stream.
- The URL is a credential. A webhook URL is a bearer token wearing a path: whoever holds it can
  post to the operator's own phone. It is never logged, never echoed, never served on the loopback
  port, and never printed by `--diagnose`, which is the handling Usage quota reads gives a vendor
  token. Redaction has to cover the whole URL and not only a query string, because these providers
  put the secret in the path.
- Off switch. The feature ships `--no-reach` with it: a flag that disables the pathway for a run
  regardless of the stored setting, mirroring `--no-usage` and `--no-history` at every one of their
  sites, including the branch that forwards flags to a respawned daemon, so a restart cannot
  re-enable what the operator disabled. That flag does not exist yet, and this document does not
  claim it does. Nothing posts, so there is nothing to switch off. A test holds those two statements
  together: it asserts this section still says nothing posts and that the parser still has no such
  flag, so whoever adds the flag is failed here until they amend this section too.

A violation of any of those is a security bug: a post with no URL configured, a post to any
destination but the configured one, a redirect followed, a payload carrying any field beyond the
counts named above, the URL reaching a log line, a `--diagnose` line or a loopback response, or a
post rate above the configured interval.

What is accepted rather than solved: the endpoint is a third party, and what it does with a count
is outside Cargento's control. That is the same trust the operator extends to that provider by
using it, and it is a real transfer. A count is a small thing to leak and it is not nothing. How
many sessions on this machine need a human, and when, says that the operator is working and roughly
how hard, to anyone who can read the notification stream. That is stated here rather than implied.

## Process lifecycle: written paths, and `/api/shutdown`

The server writes five files, all under `~/.cargento` (relocatable with `CARGENTO_HOME`,
authoritative when nonblank): `cargento-<port>.json`, recording the running instance (`pid`, `port`,
`started`, `log`, `python`); `cargento-<port>.log`, where a detached (`--daemon`) instance's
output goes; `cargento-dismissals.json`, the sessions the reader marked handled, described in
Dismissals below; `observer/<harness>_<sid>.json`, the sidecar `GET /api/observe` records when a
reader opens that panel for a session, named in invariant 2 above; and `cargento-history.json`, the
history of what this server observed, described in Local history above. One forwarder writes a
sixth, in the same directory and named in invariant 2 above:
`statusline_hook.py` keeps `statusline-<harness>-<session>.json` per conversation, holding a
normalized state name and a timestamp, so a status line that fires many times a turn posts once. The directory is created `0o700` because the log can carry local paths: uncaught
tracebacks land there, not just Python-level prints. Nothing ever removes or rotates the log: a
`--stop` (or a killed process) deletes the state file but leaves the log behind, since it is the
record of a detached run, so `~/.cargento` accumulates one log file per port indefinitely.

`POST /api/shutdown` stops the server and is gated by the same `_local_ok()` checks (`Host`,
`Origin`, `Sec-Fetch-Site`) that already protect `/api/notify`. It adds no new exposure of
consequence: any local process that can reach the port could already read every session on the
machine through `/api/data`, and can now also stop the server. That is a smaller capability inside
the same trust boundary described above, not a new one.

`GET /api/overlays` reads the event overlay ledger and is a diagnostic, described in
[`docs/design-needs-input.md`](docs/design-needs-input.md#n-5-two-different-faults-produce-the-same-row-so-the-ledger-is-now-readable).
It carries no session content: an overlay is a harness name, the collector key for the session, a
state kind, three timestamps, and a subagent id the hook supplied, capped at ingress. The collector
key is Claude's eight-character transcript prefix and the whole session UUID for Codex, Antigravity
and Gemini CLI, and `/api/data` already publishes both, along with titles and prompts this route
never sees. It applies the strict same-origin check rather than the relaxed one `/api/data` uses for
navigations, and answers 503 when the process runs without a coordinator.

The same route serves the bounded record of state disputes, where an event overruled a session the
dashboard had read as waiting. A record holds the same fields plus the two activity timestamps the
reducer compared, and no more: the row's title and its state detail are deliberately absent, because
a state detail can carry a permission prompt's own text, an open question's, or a plan's first line.

## Dismissals

Marking a session handled writes one file:
`~/.cargento/cargento-dismissals.json`, opened `0600` with the mode in the `open` call so it is never
briefly world-readable, written through a temp file and `os.replace` so a reader mid-write sees the
old file or the new one.

It holds a harness key, a session id, and two timestamps per entry. Nothing else: no title, no
prompt, no project path, no state detail. Nothing sends it anywhere either. The one route that reads
it out is `GET /api/cleared`, on the loopback port, and what that serves back to the page is strictly
less than `/api/data` already does. It applies the strict same-origin check rather than the relaxed
one `/api/data` uses for navigations, and answers 503 under `--no-dismiss`.

Two properties bound what a forged `POST /api/dismiss` can do. The body carries no timestamp: the
watermark that decides how long a mark holds is the server's own clock at the moment it lands, so
there is no value a caller can send that hides a row past that session's next write. And the file is
capped at 256 entries, oldest mark evicted first, so nothing can grow it without limit. A corrupt,
truncated or over-cap file degrades to "no dismissals", with every row visible, rather than
raising, and one malformed entry is dropped on its own without discarding the rest.

To clear it, delete the file, or use the page's `handled` chip to restore individual sessions.
`--no-dismiss` leaves it unread and unwritten for a run.

Two exposures come with the feature and are accepted rather than solved. The first is that clearing a
session suppresses its desktop popup as well as its row, including a session still waiting on an
answer, which is what the control is for when the gate was answered somewhere else. It is also the
most a forged `POST /api/dismiss` can achieve: one session's alert stays silent until that session
writes again, and its standing question is still on the board the moment the row is restored. The
second is that two dashboards on one machine share the one file. Each picks up the other's marks on
its next collection, but two marks landing in the same instant resolve last-writer-wins on the whole
file, and the losing mark is lost.
[`docs/design-dismissals.md`](docs/design-dismissals.md) records why that race is stated rather than
solved.

## Local history (the session history store)

The board is rebuilt from the harness stores on every start, so a restart used to leave it with no
memory of sessions that already ran. Cargento keeps its own history of what it observed, on this
machine, so the board can open knowing what happened before it was last closed.

One rule fixes the rest: the store holds nothing the live snapshot does not already serve. What is
kept is session identity, states and the transitions between them, gate open and close, turn
boundaries and their timings, tool names and counts, and the derived two-segment project label the
board groups by: it is published on every row, it is capped at the last two segments rather than
being a path, and both panels that read the history group by it, so the history cannot be seeded
without it. Never a raw working directory.

What is never written to it, under any circumstances and with no exception available:

- Tool input, in whole or in part, including any substring of a command.
- Paths. Neither a session's working directory nor any path a tool touched.
- File contents, of any file.

**Prompt-derived text is avoided by default and allowlisted per field when a feature needs it.**
Until 2026-09-04 this was a fourth outright prohibition, and DEC-13 replaced it with the allowlist
below. What did not change is that the store keeps no prompt-derived text nobody named: a carrier
absent from the allowlist is banned exactly as firmly as tool input is, and the allowlist is a list
of decisions rather than a category.

The reason the ban became an allowlist is that it was stricter than the product around it and the
asymmetry was doing no work. The dashboard already publishes prompt text. Published text below owns
the enumeration, and the carriers that reach the page raw are these nine: `title`, `last_prompt`, `state_detail`,
`project_key`, `project_name`, `tasks[].subject`, `tasks[].activeForm`, `subagents[].name` and
`subagents[].parent`. More reaches the page through `records.safe_text`, including the observer's
derived goal and Codex's `title`, which is a prompt because Codex writes no generated title. And
`GET /api/observe` already writes prompt-derived text to disk as a sidecar under
`~/.cargento/observer/`, redacted on the way in and written owner-only. Prompt
text on disk in Cargento's own state was therefore already a shipped pattern with a review behind
it, and the history store was the one place holding a harder line than the surface it records.

A field carrying prompt-derived text may be kept only when every one of these holds:

1. it is named in the allowlist below, on its own line, with the feature that needs it;
2. it is already published on the live board, so the one rule above, that the store holds nothing the
   live snapshot does not already serve, still holds unchanged;
3. it has passed `records.redact_secrets`, through `safe_text` or `redact_clip`, **before** it is
   bounded and never after, the order Published text requires and for the reason given there;
4. it is bounded to a cap this section states;
5. it lives inside the retention window, the size cap, `--no-history` and `--forget` described
   below, with no separate lifetime of its own;
6. its admission bumps `history.SCHEMA_VERSION` and appends the old value to
   `history.READABLE_VERSIONS`, so an upgrade reads the records already on disk instead of
   discarding them. Every admission is additive, because each field is re-validated on its own
   and a record written before a field existed is a record with that field absent. The store
   used to compare the version for equality, which meant the bump that came with the first
   admission would have wiped fourteen days of history on upgrade with no signal but a reset
   reason nobody reads. A version outside that tuple is still refused, which is the case the
   header exists to report.

The allowlist, one line per field:

- `annotation_goal`, for the outcome baseline DEC-15b admits. What the reader typed one session
  should achieve, at most 240 characters as the annotation store bounds it and at most 256 as this
  store does. Published on every row, redacted by `records.safe_text` inside
  `annotations.annotate` before either bound is applied, and kept so the words a reading was read
  against reopen after a restart and after the live row leaves the board.
- `annotation_output`, the same field's other half: what the reader typed the session should
  produce. Same bound, same redaction, same reason.

The revision number beside them, `annotation_revision`, is in the record and not on this list. It
is an integer the board derives, not text anybody typed.

Reserved and deliberately not admitted, because nothing produces one and this store may not hold
what the live snapshot does not already serve: `assessment_at`, `assessment_cutoff`,
`assessment_revision_read`, `assessment_goal_result` and `assessment_output_result`. The names are
recorded so the admission that adds them does not re-argue the naming, and each still needs its own
line here.

A test binds this list to `history.PROMPT_TEXT_ALLOWLIST` and to the record's own field set: an
entry with no record behind it fails, and none of the carriers named in
`history.PROMPT_DERIVED_CARRIERS` may enter the record without an entry here. That tuple is a
hand-kept list of names, so a carrier it does not yet name is held out by this section and by
review rather than by the test. Adding a prompt-derived field to the record means adding its name
there in the same change.

The store may never widen the set of fields it keeps otherwise: a field that is not already
published on the live board is not a field history may keep. That condition used to run one way
only, because the board published prompt text while the never-list banned it outright; with the
allowlist the exception is gone and the condition runs both ways for an allowlisted field. The
derived two-segment project label is kept by the kept-list above while the never-list still bans
the paths it is derived from.

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
behalf by default in the dismissals file, and writes the observer sidecar on demand when a reader
opens that panel for a session. The trust cost of that default is retention, and the bounds above
and the delete below are what answer it.

The off switch is `--no-history`. It mirrors `--no-git` at every one of that flag's sites, including
the branch that forwards flags to a respawned daemon, so a restart cannot re-enable a store the user
disabled. With the store off nothing is written and nothing is read back: the board opens with no
memory, exactly as it does today.

`--forget` deletes the store and exits. It is a one-shot command, in the family of `--stop` and
`--status` rather than the family of per-run switches, because what it does is not reversible by
running the next command without it. It removes the file whether or not the store is enabled, and it
adds no endpoint: nothing over the loopback port can delete history. It is refused while a dashboard
answers on the port it names, and says to `--stop` that instance first: a running server holds its
own copy of the history in memory and would write the deleted records back on the next transition,
which is the one way a delete could report success and not have happened. A dashboard on some other
port is out of that probe's reach, so the recording lane also drops its copy when the file it read
has gone.

A store that cannot be read is discarded rather than repaired. Corrupt bytes, an unreadable file, a
version the running build does not understand: in every case the store is dropped, the board starts
empty, and the header reports the reset, so a silent loss of history is never mistaken for a machine
that did nothing.

Nothing in the store ever leaves the machine. It adds no outbound request, no forwarder and no
endpoint; the network posture described in Scope is unchanged by it.

A violation of any boundary in this section is a security bug: a field in the store that the live
board does not publish, prompt-derived text in a field the allowlist above does not name, tool input
or a path or file content reaching it by any route,
a write that is not owner-only or not through a temp file and a rename, an unbounded store or one
evicted by anything but age first, a store still written while the feature is off, a respawned daemon
that re-enables it, a history file reachable over the port, or any part of the store leaving the
machine.

## Irreversible actions (hook-side destructive-shape matching)

The board can say a tool call failed. It cannot say the call deleted a branch. C6 (DRC-4025) would
report the handful of shapes a person wants told about after the fact, and the design that makes it
safe puts the matching in the hook rather than in the server. The hook already holds the payload its
own harness handed it; it decides whether that payload matches one of a named set of shapes and
posts an identifier for the shape it matched, with the tool's name. The command does not travel.

This is the section to read before building that, and it grants nothing on its own. No shipped
adapter matches a command shape, and the event envelope has no field that could carry the answer.
Coverage is Claude Code and Codex with the hooks installed, which is the scope DEC-5 set. That is a
limit rather than a phase, and it has to be read the way the session-end marks are read: an absent
report means no match was observed, never that a session ran nothing irreversible.

### What Cargento reads of a tool call today, exactly

The rule here is an allowlist rather than a prohibition, for the reason DEC-13 gave the history
store: a flat "never" the code already breaks is a contract narrower than the system, and a reader
who finds the counter-example stops believing the rest of the document. So the honest form is a list
of named reads. Of an observed session's tool calls, the runtime parses the input at exactly the
places below and nowhere else, and each reduces what it read to a bounded summary at parse time
rather than keeping anything raw. One further read exists and is governed elsewhere: the ask lane's
own `ask_operator` tool parses the arguments of the call a session makes to Cargento, which is a
tool Cargento owns rather than one it observed, and The ask lane states its bounds:

- `claude_data.input_summary` reads two fields of two Claude tools. `ExitPlanMode` carries `plan`,
  and what is kept is its first usable line, which is the plan's own title in practice.
  `AskUserQuestion` carries `questions`, and what is kept is each item's `question`. Both go through
  `records.safe_text` and are bounded at `config.input_summary_cap_chars`, 160 characters. The pair
  of tool names is `claude_data.INPUT_TOOLS`, and a tool absent from it has its input read by
  nothing.
- `transcripts.codex_plan` reads Codex's `update_plan` payload, in both shapes Codex writes: the
  `arguments` of a `function_call` and the `input` of a `custom_tool_call`. What is kept is the plan
  steps and their statuses, bounded at `transcripts.CODEX_PLAN_MAX_STEPS` steps, 64, with each
  step's text through `records.safe_text` and bounded at `transcripts.CODEX_PLAN_STEP_CAP_CHARS`,
  160 characters. Codex caps its own plan well below both, and the record is untrusted input, so the
  bound is against a malformed one rather than against ordinary use.

The operator-cockpit prototype also reads dispatch evidence:

- `collectors.codex._child_assignment` reads `spawn_agent` and `followup_task` arguments from
  the bounded transcript tail, matching a child task or target before summarizing its message.
- `project_context._tool_call_events` and `project_context._tool_support` read Pi `bash` and
  `subagent` arguments for dispatch events, assignment summaries, and counts.
- `project_context.codex_dispatch_events` reads `spawn_agent` arguments to join a task name to
  a readable dispatch artifact. Its backward scan is capped at 32 MiB by default; project event
  output is capped at 100 rows and semantic lines at 112 characters.

These are evidence reads, not command execution. In total, seven expressions in `cargento_runtime`
reach an input payload. The counts and module names are checked by `test_documentation`.
The prototype has no additional switch that disables just these dispatch reads.

A shape match would be a different kind of read from either of those. It happens in the hook, inside
the operator's own harness process, against a payload that process already has, and what it keeps is
a verdict rather than a summary. It changes nothing about what the server or the collectors read from
a transcript, and it adds no store, no path and no subprocess.

### The bounds a shape match has to hold to

- The hook decides and the server never sees the command. What is posted is an identifier for a
  shape from the named set, the tool name, and a timestamp, which is the shape DEC-5 allowed. The
  command, its arguments and its output stay in the harness's process and are not put on a socket,
  and neither is any substring of them, any path or any file's content.
- The set of shapes is written into this document before it ships, one line each, the way the quota
  endpoints are. A shape is a decision rather than something an operator configures: a
  user-supplied pattern would be a small language running against their own commands, and the
  result of running it would go on the wire.
- The match cannot delay or block the call. It is time-bounded and fails open, so a shape the
  matcher cannot decide in its budget is no report rather than a held tool call.
- Report after, never before. This reports what happened, so it hangs off the after-the-fact event
  rather than the gate in front of it, and a matcher may never be registered at a hook position
  whose output gates a tool call. Antigravity is why that is a rule and not a preference. Its
  `PreToolUse` output decides the call, and an empty object there is a deny rather than an
  abstention, measured on 1.1.19: `{"decision": "allow"}` permits and exactly `{}` refuses. So
  there is no harmless output at that position, `agy_hook.py` prints `{}` on every path including
  every failure path, and the safety property is that the hook is never registered there rather than
  that its output is safe. A matcher inherits that rule unchanged.
- Off switch. The feature ships `--no-irreversible` with it, mirroring `--no-events` at every one of
  that flag's sites, including the branch that forwards flags to a respawned daemon. That flag does
  not exist yet, and this document does not claim it does. Nothing matches a shape, so there is
  nothing to switch off, and a test asserts both halves: this section still says no adapter matches,
  and the parser still has no such flag.

### The envelope has to widen, and one dropped thing has to come back

Known and accepted describes the event envelope as an allowlist at both ends, and its sentence says
the prompt, the tool name, the tool input and the tool output are dropped in the hook and never put
on a socket. Every word of that is true today and stays true until this feature lands. Then two
things change, and this is where they are settled rather than discovered: the envelope gains a
shape identifier, and the tool name stops being dropped. DEC-14 amended invariant 1 the same way
during its own groundwork pass, which is why amending is the established answer here rather than a
novel one.

The tool name is the one of those four that can come back, and the reason is not that it is the
shortest. The board already publishes it: a failing tool's name reaches the page through the loop
signal and is rendered on both the session and the attention surfaces. So the envelope was dropping
a value the snapshot serves anyway, for want of a use rather than for secrecy, and a hook that posts
it tells the server nothing the server could not already say. The prompt, the tool input and the
tool output are the three that stay dropped, and they are the three where that reasoning does not
hold.

Three places carry the envelope's width and they move together in one commit. This document's own
sentence spells it as a word, `config.py`'s stated reason for `event_body_cap_bytes` spells it as a
word too because the cap is justified by that width, and `events.ALLOWED_FIELDS` is the set itself.
`test_documentation.EventEnvelopeEnumerationTest` reads both prose copies against
`len(events.ALLOWED_FIELDS)`, so a field added without the words moving is a red test rather than a
document that has quietly drifted.

### Whether a shape identifier may enter the history store

This turns on one thing, and the thing is already written down. Local history bans tool input "under
any circumstances and with no exception available", and it bans any substring of a command with it.
A shape identifier is neither: it is a fixed label from the set this document names, and it carries
no part of what was typed. So the ban does not reach it, and the second of that section's rules
decides the question instead. A field the live board does not publish is not a field history may
keep. If C6 publishes the identifier on the row, the identifier becomes admissible and needs its own
line in that section's kept-list in the same change. If C6 renders it only in a panel the board does
not publish, history may not keep it, and C6's cross-session list cannot be built out of the store.
Either way the answer is settled here rather than discovered during the build.

A violation of any boundary in this section is a security bug: a command, an argument or a tool
output reaching a socket, an input read the allowlist above does not name, an operator-configurable
pattern, a hook that returns anything but its harness's no-opinion answer, an envelope field this
document has not named, or a shape identifier in the history store with no published field behind
it.

## The ask lane (`ask_operator`)

Cargento ships one MCP tool. A session that wants a human decision calls `ask_operator`, and the
question appears in the dashboard for the reader to answer. This is the only path by which anything
a reader does in Cargento reaches a running session, and it exists because the session asked. One
other direction is written down and unbuilt: Hand-off requests (one verb into a session) below is
Cargento starting the exchange rather than a reader, it carries one fixed verb and nothing a reader
typed, and no shipped feature uses it.

What it is, precisely. Cargento ships a stdio MCP server beside the dashboard. It is not one of the
four forwarders and shares none of their transport. A harness spawns it, it speaks JSON-RPC on stdin
and stdout, and it holds the agent's tool call open while the question is outstanding. It registers
the question with the dashboard over loopback and polls for the answer.

The direction is the invariant for everything shipped. Cargento reaches into no session today, and
the one written-down exception is the hand-off request below, which DEC-2 allowed as a single verb
into a session that consents and which nothing ships. It weakens no other sentence in this section.
A session can only ever be
waiting because it asked to be, and a session that never calls the tool is untouched by all of this.
Nothing is typed into a terminal, no harness store is written, and the tool cannot answer a native
permission prompt. That last point is not a limitation to be lifted later: answering a harness's own
gate is refused, and the four probes DEC-2 filed are research rather than a roadmap.

What the reader's click can and cannot say. The question's options are recorded when the question is
registered. An answer names the question and an option by index, and the MCP server returns its own
copy of that option to the agent. An answer cannot introduce text. The strongest thing a forged
answer can do is select the wrong one of the options the asking agent itself wrote, and it cannot put
new content into that agent's context.

What is bounded. The question text and the option list are bounded when they arrive, and rendered as
text and never as markup. The number of questions outstanding at once is capped, and the honest
answer past the cap is a refusal the server turns into a decline rather than an error. A question
that is never answered expires and declines. The question is also delivered as a notification: on macOS by the server,
through the same truncation and AppleScript escaping the needs-input popup uses, and elsewhere by the page, which
passes the text to the browser's own notification API and applies neither (it is not building a
shell command, and the text is already bounded at the ingress); the notification is a pointer rather than a decision surface, and an option can
only ever be chosen back in the page.

Failure is always a decline, never a hang. If the dashboard is not running, if no reader answers, if
the deadline passes, or if the process is stopped while a question is outstanding, the tool returns a
decline and the agent proceeds as it judges best. A stopped dashboard releases every outstanding
question before it exits. A tool call that gives up for any of those reasons also withdraws its own
question on the way out, so a card nobody is waiting on leaves the board instead of staying clickable
until its deadline. A click on a question whose asker has gone is accepted and discarded either way,
which is why the withdrawal matters to the reader rather than to the agent.

The standing permission this needs, and what granting it means. At default settings every harness
gates the first call to this tool in the user's own terminal, before the call reaches Cargento. The
feature is therefore useless until the user grants the tool once, which on Claude Code writes
`permissions.allow: ["mcp__plugin_cargento_cargento__ask_operator"]` into that project's
`.claude/settings.local.json`. Granting it means that project's sessions may pause themselves on a
Cargento question without asking again. It is scoped to that directory, it is the user's to revoke by
deleting the line, and Cargento never writes it.

Answering is a real decision. Every other click in the dashboard changes what you see. This one
changes what an agent does next, with your credentials, in your repository. The exposure that follows
is recorded under Known and accepted rather than solved here, because loopback is not a per-user
boundary.

## Hand-off requests (one verb into a session)

The ask lane runs one way. A session asks, a reader answers, and Cargento starts nothing. DEC-2
ruled on 2026-09-02 that Cargento may also start the exchange, in one shape and no other: when a
quota window is about to close on a session that is mid-task, Cargento may send that session one
request for a hand-off summary, so the operator gets the state of the work written down instead of
writing it from memory before the cutoff. E7 (DRC-4040) is the feature. This is the boundary it has
to respect, and it is written before the code exists for the same reason the quota, git-probe,
history and light-harness boundaries were.

This section grants nothing on its own. No shipped feature sends anything into a session, and the
ask lane's direction claim is amended for this section and for nothing else.

### One verb, and what makes it one

What may be sent is a request for a hand-off summary. Not a prompt the reader composed, not a line
off the board, not a retry of the operator's last instruction: one fixed request Cargento authored,
in plain text, whose content does not vary with what the reader typed or with what the session
holds. That is what keeps this out of the general write path into terminals that DEC-2 refused as a
standing answer, and it is the same property the ask lane relies on in the other direction, where an
answer can only ever select one of the options the asking agent itself wrote. A reader cannot
introduce text through either.

The verb is also not a permission answer. DEC-2 confirmed the refusal of native-gate answering
rather than lifting it, so nothing here reaches a harness's own prompt, and the ask lane's sentence
on that stands unchanged.

### The session's own consent, and what is documented rather than measured

The receiving side decides whether to accept, and the mechanism is the harness's rather than
Cargento's. What follows is read off Claude Code's own documentation and has not been measured on a
machine here, which is stated plainly because this repository's standing lesson is that desk
research got the field, the unit or the rendering wrong five times out of five. Four facts are
documented, not measured:

- that the inbound setting, `crossSessionInbound`, has values that refuse an inbound message or hold
  it for the session to accept;
- that a held message lapses after a `dialogExpiry` of five minutes;
- that a delivered message counts toward usage the way a prompt the operator types does;
- that the socket lives in a per-user directory under the system temporary directory, of the shape
  `/tmp/cc-socks-<uid>`.

The build that lands E7 measures all four first, records the capture under `docs/captures/` the way
every other harness vocabulary here was earned, and replaces this list with the measurement. Until
then no sentence in this section rests on any of them being exactly right. What the section does
assert is the rule Cargento sets for itself: a session that refuses inbound messages is not reached,
and a request that lapses unread is a request that was not delivered.

Cargento sends no authentication line, on any platform. The socket protocol documents one, and the
reason to leave it unused is not convenience. Verifying that a session is Cargento's own child is
one permission class. Presenting a credential that would reach any session on the machine is
another, and sending the line asserts the second. So the verb reaches a session that already accepts
inbound messages, and it reaches nothing else.

### The token, and the path that contains it

The per-session token is never logged, never echoed, never served on the loopback port, and never
printed by `--diagnose`. Neither is any path that contains it. That second half is not a flourish:
the token is documented as part of the socket's filename rather than as a separate field, so a
redaction covering the value while printing a directory listing, an error message or the path itself
leaks the whole thing. Both the value and its containing path get the handling Usage quota reads
gives a vendor token. Published text records what redaction covers today, and a path-shaped secret
is the case it does not yet name, so E7's change adds it there in the same commit.

### The read this adds, and why `config.py` has to name it

Finding a session's socket means reading a path that is no harness store and lies under no root
`config.resolve_store_roots` returns. That function documents three Claude roots today,
`claude.projects`, `claude.tasks` and `claude.teams`, and no fourth. Scope makes a read outside the
documented store paths a security bug "however the path was derived", so this read is a security bug
until its location is documented there. Naming it belongs to E7's change rather than to this
section: the commit that opens the socket adds the directory to the documented roots, and a reviewer
who finds the open without the entry has found the bug this paragraph predicts.

### How this relates to Light harness usage, and to the outbound count

They are two pathways and not one, which is why invariant 1 names them apart. Light harness usage
starts a fresh harness process and hands it text Cargento composed out of a session, so the
operator's own words leave the machine on a request Cargento made. A hand-off request writes one
line to a socket on this machine, to a session the operator already started and is already paying
for. Cargento makes no network request for it, and the fixed verb carries nothing derived from any
session.

What leaves the machine afterwards is what that session sends next, on its own connection and its
own credentials, exactly as everything else that session does leaves. So this pathway adds nothing
to invariant 1's count of outbound requests, and the invariant names it anyway: a reader counting
network exposures who found no mention of a verb that causes a vendor round trip would be right to
distrust the count.

It does spend the operator's capacity, and Light harness usage's rule about that holds here without
being restated. A feature that consumes capacity states what it consumed.

### Failure is a decline, never a hang

An absent socket, a stale token, a session that never answers, an inbound setting that refuses, a
message that lapses: each one ends as the board reporting that the hand-off was not delivered. None
of them holds a request open, blocks a shutdown, or leaves a session parked. This is the ask lane's
rule in the other direction and it is there for the same reason: neither end of this exchange may be
able to wedge the other.

Cargento does not retry. A verb that resent itself when a session did not answer would spend the
operator's remaining window on delivery attempts at the exact moment the window is the thing running
out.

### The off switch

The feature ships `--no-handoff` with it: a flag that disables the pathway for a run regardless of
the stored setting, mirroring `--no-ask` and `--no-history` at every one of their sites, including
the branch that forwards flags to a respawned daemon, so a restart cannot re-enable what the
operator disabled. That flag does not exist yet, and this document does not claim it does. No
feature sends the verb, so there is nothing to switch off. A test holds those two statements
together: it asserts this section still says nothing is sent and that the parser still has no such
flag, so whoever adds the flag is failed here until they amend this section too.

### Violation, and what is accepted rather than solved

A violation of any boundary in this section is a security bug: text sent into a session that is not
the one fixed verb, a verb sent to a session that refuses inbound messages, an authentication line
presented, the token or its containing path reaching a log, a `--diagnose` line or a loopback
response, a retry, a socket read from a location the store roots do not document, or a request that
blocks rather than declines.

What is accepted rather than solved: as far as the harness's own documentation goes, the socket
directory is per-user, so other accounts are held out only as well as that documented shape holds,
and E7's capture is what settles it rather than this paragraph. What is certain either way is that
the directory does nothing about other processes of the same account. Anything running as the
operator can send the same verb to the same session without going through Cargento at all. That stays inside the
trust boundary for the reason Known and accepted gives for the rest of this document, since such a
process can read the operator's secret material directly, and it is the same limit the ask lane
already accepts on loopback.

## Operator-cockpit prototype

The `proto/operator-cockpit` branch adds project context and an optional read-only terminal.
`GET /api/project-context` reads bounded transcript and workflow evidence, stores semantic history
under the configured state directory, and can invoke the installed Codex CLI for a derived goal.
This is separate from quota fetching and from the session-history switch. The prototype retains
its own semantic-history store; `--forget` continues to delete only the session-history store.

That store carries session text in both directions, and this document did not say so until the
annotation work re-counted which files hold what a person typed. A fact's `summary` is bounded at
240 characters and holds the operator's own directive where the fact is a steer or an observer goal;
a result fact's `detail` holds up to 4096 characters of the assistant's final answer. So the file is
a carrier of typed words as well as generated ones, in the same content class as the observer
sidecar's goal line, and the redaction paragraph below is what stands between it and a credential.

Semantic history redacts recognized credential shapes before publication and persistence.
Loading an older store also redacts nested values and, if any changed, immediately replaces
the file atomically with an owner-only copy under the history lock. A read may be the only
activity after an upgrade, so waiting for a later history update would retain known secrets
unnecessarily. If replacement fails, the read still publishes redacted values, logs a warning
without their contents, and retries the repair on the next load. Original bytes can remain
until the filesystem permits replacement; this does not erase filesystem snapshots or backups.

The terminal is off unless both `--interaction-origin-session` and
`--interaction-origin-registration-file` are supplied. When enabled, ten POST operations under
`/api/interaction/` join the ordinary routes: `register`, `renew`, `probe-unregistered`,
`probe-spoofed`, `control`, `input`, `expire`, `disconnect`, `reconnect`, and `reset`.
Registration requires the session-side registration token; renewal requires the lease token.
The probe and lifecycle controls have the normal loopback/origin checks, with no additional
capability. `control` and `input` always refuse. Normal serving returns 404 for this prefix.

`interaction_prototype.py` joins `focus.py` as a module allowed to invoke tmux. It validates the
registered pane identity before capturing output and attaches a read-only control-mode client.
The WebSocket at `/api/interaction/stream` carries output only; receiving a client frame ends the
connection. Its upgrade response carries the same framing header as ordinary responses. Terminal
output is a separate exposure from the redacted session summaries: a person or local process that
can read the registered terminal can see its captured text.

## Published text (credential redaction)

A harness transcript records what the operator typed, verbatim, so if a key was ever pasted into a
prompt the store holds it. The dashboard reads those stores and publishes prompt text. Named as
fields rather than glossed, because a prose alias is a name no test can check, the carriers that reach the page raw are these nine: `title`, `last_prompt`, `state_detail`,
`project_key`, `project_name`, `tasks[].subject`, `tasks[].activeForm`, `subagents[].name` and
`subagents[].parent`. Those are the two tables in
`aggregate`, and the instruction line's own `text` passes the same sweep beside them. It is a list
of carriers rather than a list of every published string that could hold what the operator typed:
more prompt text reaches the page through `records.safe_text` on the way, including the observer's
derived goal, the ask question and its options, and a Codex `title`, which is a prompt because Codex
writes no generated title. Some of what those carriers hold came from a tool call's input rather
than from a prompt directly: a Claude plan's first line, an `AskUserQuestion` question, and a Codex
plan's steps, each under the bounds Irreversible actions states. A sweep of the local Claude store
on the machine this was built on found seven distinct live Anthropic credentials in ordinary prompt
history. Loopback is no help against it: the dashboard is what someone opens to show a colleague
what their agents are doing, so the exposure is the screen and the screenshot.

Credential-shaped runs are replaced before publication, in place, by a visible marker that keeps the
prefix naming the kind: `sk-ant-…REDACTED`, `AKIA…REDACTED`, `ghp_…REDACTED`. The words around it
survive, because those are the instruction and the reason the line is on the card. The marker is
visible deliberately. Someone who sees it learns their prompt history holds a live key, which is the
only route by which it gets rotated.

The list of shapes is measured against the local corpus and lives in one place,
`records.redact_secrets`. It is applied at three. Inside `records.safe_text`, which nearly every
published string already passes through, including the ask question and its options, Codex's title
and the observer's goal. At the slice, through `records.redact_clip`, for the strings the other nine
collectors build out of their own store by hand: `title` and `last_prompt`. And over the assembled rows
in `aggregate`, a backstop under both that also reaches `state_detail`, the instruction line, task
subjects and a subagent name. An ask answer needs no cover, being an index into options the asking
agent wrote rather than text. The measurement, the false-positive rate and the rejected alternatives
are in [`docs/design-credential-redaction.md`](docs/design-credential-redaction.md).

The order matters as much as the coverage. Redaction runs before the bound, never after, because a
key cut at a 140-character cap is still a hundred usable characters of key and a shape whose tail has
fallen off no longer matches. A slice that ran first is what published a URL credential cut short of
its `@`.

The card, the browser notification body and the native popup are pixels, and a screenshot is what
each of them risks. Two of the things carrying this text are files. The first is the observer
sidecar under `~/.cargento/observer/`, one JSON file per session holding the derived goal, which is
the operator's own words. Since goal provenance landed it holds two such lines rather than one: the published
`goal` and the pre-model `deterministic_goal` the model arm would otherwise have overwritten. They
are the same class of text and carry the same risk, so the count changes and nothing else does.
Both are redacted on the way in like everything else, and the file is
written owner-only through a temp file and a rename, so a reader mid-write sees the old file or the
new one and neither is ever briefly world-readable. The mode is advisory and Windows ignores it, the
same caveat the state file and the dismissal store carry.

The second is the prototype's semantic-history store, `~/.cargento/semantic-work-history.json`. It
holds the operator's own directive as well as the assistant's answer, it is redacted on the way in
and again on every read, and it is written owner-only through a temp file and a rename like the
sidecar above. The Operator-cockpit prototype section has its fields and its deletion behaviour,
including that `--forget` does not reach it.

This reduces the exposure and does not close it, and both directions of error are real. A shape list
covers the formats it was measured against, so a credential in a format nobody has seen goes through
unmarked. A control character struck through the middle of a key defeats the match on the whole key,
and what follows is worse than nothing being published: the substitution that scrubs the character
turns it into a space, so the head in front of it still matches and redacts while the tail behind it
publishes beside the marker, 75 characters of key on a probe. A run longer than any key its format
issues is cut at the cap, and the characters past the cap publish. And the AWS secret access key is
matched only when one of three spellings of its key name sits in front of the value, because a bare
40-character base64 run cannot be told apart from a hash or a diff.

In the other direction a genuine instruction line can be altered: 20 of 22,120 real prompts in the
local corpus, 18 on Claude and 2 on Codex. That rate was re-measured when the filter was widened to
cover a key with a character in front of it, a URL credential clipped short of its `@`, capped
bodies, Linear keys and the cued AWS secret, and it did not move on any of them. Nothing here changes
the rule outside the software, which is not to paste a credential into a prompt, and to rotate one
that was.

## Known and accepted

`--host` hands that same access to a network. `--host 0.0.0.0` is the operator
saying the machine's network may read the board, and there is no second gate behind it: everything
the paragraph below grants another account on the machine, a non-default bind grants anything that
can reach the port. Reading `/api/data` is the whole board: every session's titles, prompts and
project paths. Writing is the ten POST routes enabled without terminal registration, `/api/shutdown` and `/api/answer` among them, so a
reachable dashboard can be killed, and a question a session is waiting on can be answered by
somebody other than you. There is nothing to authenticate with on eight of them, for the reason the
ask-lane paragraph below gives: the page is served as fixed bytes with no per-run secret in them.
Two carry a capability and they are not worth the same. `POST /api/events/<harness>` takes a per-run
token published only in the state file at mode `0600` and never served to the page, so a client
holding only the board cannot post events at all; that boundary survives a non-default bind intact,
and Event ingress below is where it is stated. `POST /api/focus`'s capability buys less: the token is
injected into the served document, so anything that can load the board under a non-default bind can
also ask for a raise, and `/api/data` names which rows would answer it. What that second gate
actually separates is a page from a document navigation and from a local process that never fetched
the board, which is the exposure the focus section states.

What the non-default bind does *not* spend is the rebinding defense. The Host and Origin gate widens
to addresses and never to names. Under `0.0.0.0`, that means any address a client could arrive on.
A page on `http://evil.example:4553` whose DNS points at the machine is refused in both modes, and
the `Sec-Fetch-Site` cross-site check runs unchanged. The gate tells a name from an address; it
cannot tell one remote client from another. So the honest scope is: use `--host` on a network you
would hand the transcripts to, and reach a dashboard over `ssh -L` otherwise.

Loopback is not a per-user boundary. Any other account on the same machine can `GET /api/data` and
read every session's titles and prompts, or forge a `POST /api/notify`. The Host, `Sec-Fetch` and
Origin checks defeat browser-based DNS rebinding, but they do not defeat a local process. This
matters more on a shared Linux host than on a personal laptop. Please report a *bypass* of the checks
that do exist. The absence of per-user isolation is documented here rather than treated as a new
finding.

A browser will not frame the board, and the header that stops it is narrower than it looks. Every
response the server composes carries `Content-Security-Policy: frame-ancestors 'none'`, with the
three exceptions named below, because the request gate does not close framing on its own: every port
on this machine is the same site, so a page served from another local port frames the board under a
`same-site` label that never reaches the cross-site check, and a frame navigation carries no `Origin`
for the check below it. That is worth closing because the served document holds the focus capability,
so a framed board is one lured click from raising a terminal, and `/api/data` names which rows would
answer. The attack it stops is blind: the framer cannot read the frame, since a fetch from another
local port carries an `Origin` and is refused, and no `Access-Control-Allow-Origin` is ever sent, so
the framer must guess that a question is outstanding and where its control landed.

What the header does not buy is the local-process exposure above. A local process the attacker
controls can open a socket to the port carrying no `Origin` and no `Sec-Fetch` headers at all, pass
every check, and answer or raise directly. `frame-ancestors` is not a defense against that attacker
and does not narrow what this section already accepts. The one case it does defend is a loopback page
whose process the attacker does not control: a stored cross-site scripting flaw, or an
HTML-rendering endpoint, in some other local development server the operator already runs. It is
delivered as a header rather than in the document because CSP ignores `frame-ancestors` in a
`<meta http-equiv>`, and it is the only directive in that policy because `frame-ancestors` has no
fallback to `default-src`, so it restricts framing and nothing else. Three responses are outside it,
deliberately, and none of them is a page: `/api/stream` writes its own headers and an event stream
has nothing to click; a `send_error` body is the standard library's error template, which carries no
control and no capability; and the `204` a poll of `/api/ask/<id>` returns while no answer has
arrived carries no body at all, so a frame navigated to it renders nothing. The stream and that poll
are both reachable from a frame on the same terms the board is, because each route takes the plain
local check.

Having nothing to click is not the whole question for those two, because both hold a socket open,
and that half was measured on 2026-09-07 in Chrome. Eight frames pointed at `/api/stream` from a
page on another loopback port took **six** sockets, not eight: a browser caps concurrent HTTP/1.1
connections per origin at six, so the eight-slot stream budget was never drained and a seventh
client still received a 200. `stream_max_clients` sitting above the browser's six is why, and the
reason it was chosen that way is recorded beside it in `config`. What the six frames did drain was
Chrome's own connection pool for that origin, and the board then would not load at all in the same
browser: the navigation sat pending and committed the instant the frames were removed. So the
resource a framed long-lived route can deny is the browser's, not this server's, and the server
cannot arbitrate it.

Both routes therefore refuse a frame navigation outright, on `Sec-Fetch-Dest`, which the same
measurement confirmed a framed request carries: `iframe`, alongside `Sec-Fetch-Site: same-site` and
no `Origin` at all, which is how such a request passed the checks above. That buys one thing, which
is that the request is refused before it can hold a socket rather than holding one for as long as
the framer likes. It is worth exactly what `frame-ancestors` is worth and no more, and for the same
reason stated above: a local process the attacker controls sends no `Sec-Fetch` headers at all. A
`curl` caller sends none either and is unaffected, since the refusal fires only on a header a
browser sets.

Event ingress is the exception, and it is narrow. `POST /api/events/<harness>` requires a per-run
capability, because a general lifecycle overlay is more powerful than the side state `/api/notify`
sets: a forged `session_ended` can suppress a permission alert, and a looped `turn_started` can mask
a blocked session. The server generates one secret per process, derives one token per harness from
it, and publishes only the derived tokens in the state file, opened `0600` with the mode in the
`open` call so the token is never briefly world-readable. A token from one adapter cannot post as
another harness, and a token recovered from an old state file is useless against the next run. The
comparison is constant-time.

What that does **not** buy: the file mode is advisory, exactly as the state directory's `0700` is.
It does not apply to a directory that already exists, Windows ignores it, and root reads it either
way. Any process running as the same user can read the token and post events, and that stays inside
the trust boundary for the same reason the rest of this section does, since such a process can read
the user's secret material directly. An overlay may also only ever patch a row a collector produced;
it can never create or delete one, and it can only write these nine fields: `state`,
`state_detail`, `active`, `blocked_since`, `acquisition`, `finished_at` (the stamp of the turn's last
observed stop), `ended_at` (the stamp of the session id's own end), and `dirty` with `changed` (the
end-of-session git reading). `--no-events` turns the whole path off for a run.

The event envelope is allowlisted at both ends. Each adapter builds the twelve permitted fields one at
a time from the native payload, so the prompt, the tool name, the tool input and the tool output are
dropped in the hook and never put on a socket; the server then validates independently, because a
hook's output is untrusted regardless of who wrote it. Codex's payloads carry `prompt`, `tool_input`,
`tool_response` and `last_assistant_message`, and Antigravity's carry the account email and the
transcript path; none of those reach a socket. `statusline_hook.py` also shapes `/api/usage` down to
the `quota` block alone, which is what this document asks for a paragraph below rather than sending
the whole status-line document and relying on the server to discard it. `cwd` and `transcript_path` are
matching hints and are never echoed to `/api/data`. Every clause above holds today. One
written-down feature would change two of them, and Irreversible actions above is where that is
settled rather than left to break this sentence: it would add a shape identifier, and it would stop
the tool name being dropped, on the reasoning that section gives. The prompt, the tool input and the
tool output would stay dropped. The count in this paragraph, the same count in `config.py`'s stated
reason for `event_body_cap_bytes`, and `events.ALLOWED_FIELDS` itself move in one commit or
`test_documentation.EventEnvelopeEnumerationTest` goes red.

One published field is derived from a transcript filename, and the sentence above is the one it has
to be read against. `resume_id` carries the session id a harness's own CLI takes to re-enter that
session, so the board can hand a reader the command rather than the hunt. It is the transcript's
stem and never its path: no directory, no home, nothing a filesystem could be walked from, and the
first eight characters of that same stem are already published as Claude's `sid`. `cwd` is not read
for it and would not help if it were. Two harnesses fill it, Claude Code and Codex, and the other
eight publish `null`, which is what stops the page offering a command nobody has verified.

The value is checked against `^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$` before it is published and again in
the page before a command is built from it, and that grammar is the guard rather than any quoting:
this is the one string on the board that becomes a shell command in the reader's own terminal, and it
is read off a filename in a store the harness owns. Two shapes are refused, and quoting would have
covered only the first. A token a shell would split, or one carrying a separator, substitution or
newline, is dropped and the row shows no control. So is a token starting with `-`: a shell reads that
as one word, but the CLI reads it as a flag. `claude --resume` takes an optional value and therefore
never consumes a `-`-leading token, and both harnesses ship a valueless flag that turns their
permission checks off, so a transcript named `--dangerously-skip-permissions.jsonl` would otherwise
reach the clipboard as a permission bypass with the session id dropped. Publishing a value that fails
that grammar, or building a command from one, is a security bug.

The ask lane inherits the loopback exposure above, and it is the first place where that exposure
reaches beyond what a reader sees. Any local process that can reach the port can answer a question a
session is waiting on. Two things keep this narrow rather than solved. An answer selects an option by
index from a list the asking agent wrote, so a forgery cannot introduce text into an agent's context,
only choose badly among choices the agent already offered. And a session is only ever waiting because
it asked, so there is no question to answer unless an agent raised one. A per-reader
authentication would be the real fix, and it is not available: the dashboard page is served as fixed
bytes with no per-run secret in it, and a local process could read such a secret anyway.

A question's attribution is unverified, and this is the second half of that exposure. `harness`,
`session_id` and `project` are taken from the registration body and bounded, and nothing checks that
the named session exists or that the caller is it, so any local process that can reach the port can
put a card on the board that reads as coming from a specific session in a specific repository. Two
things bound the damage. The card is its own band and touches no collector-measured session state, so
a forged attribution cannot alter a row, a state, a count or a dismissal
([`docs/design-ask-lane.md`](docs/design-ask-lane.md#a-4-an-outstanding-question-is-its-own-band-not-a-row-in-sessions)
records why the band is separate); and answering the card still
only selects among options its own registrant wrote, so the forger gains nothing from being answered.
What a forgery does buy is plausibility, at the one place in the dashboard where a reader makes a
decision, which is why it is named here rather than left implicit in the loopback paragraph above. That
plausibility now reaches a reader with no tab open, because the question also raises a notification. The
title renders the display label of the harness key the registration claimed, and neither the key nor the
claim is verified. A registration that inherits or forges the harness environment variable titles the
banner with that harness. What the registry lookup does buy is that the title is a name the registry
carries or nothing at all, so a 120-character agent-authored string cannot reach it, and an
unattributable question is announced as "An agent" rather than under a borrowed name.
Verifying it would need a per-session secret that the sessions do not have and that the loopback
boundary could not keep.

`--diagnose` output is sensitive. It prints the home directory, the interpreter path, the *values* of
the store relocation variables, every candidate store path, and per-path read errors. A recorded
store error may include a store or prompt excerpt, even when SQLite raised it. The shared formatter
keeps the exception type plus at most 1,024 Unicode characters of its message, including
`... [truncated]` when clipped; clipping does not redact sensitive content. Nothing is transmitted,
but redact it before pasting it into a public issue.

## Reporting a vulnerability

Please do not open a public issue for security problems. Instead:

- Use [GitHub private vulnerability reporting](https://github.com/spacedock-dev/cargento/security/advisories/new), or
- Email dev@reccehq.com with a description and reproduction steps.

You can expect an acknowledgment within a few days. Please allow time for a fix to land and release before public disclosure.

## Supported versions

Only the latest released version of the plugin receives security fixes.
