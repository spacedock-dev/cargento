# The focus command's security contract, ahead of B5's code

This is the scope section for reaching a session's terminal, written before the code that needs it,
the way the quota fetcher's, the ask lane's, the git probe's and the history store's contracts were.
DRC-4017 (B5) promotes it into `SECURITY.md` unchanged and deletes this file, and the deep dive
beside it, in the same commit.

## This document is the ruling

Every other capability that runs a program or reaches outside Cargento's own process has a decision
issue behind it as well as a contract. This one deliberately does not, and that is the operator's
call taken on 2026-09-05. Approving this document is the ruling, so the ruling has to be stated here
rather than left for a reader to look for and not find.

What is granted: Cargento may ask the operating system to bring a window to the front, on the
operator's own action, using a bounded command named in this document. Nothing wider. It is not a
grant to run programs generally, and no other feature may cite this section as cover.

What is not reopened: DEC-2 refused a general write path into terminals and named B5 as the route to
the same friction without a write power. That refusal stands, and the "nothing is typed" bound below
is where it becomes checkable rather than a sentence in a closed decision.

## Amendment to Scope, applied when this is promoted

Scope's violation sentence today makes "running any program inside a user's repository other than
the probe described in Repository git reads" a security bug. The focus command sets no working
directory, so it falls outside that sentence on a technicality rather than on a boundary anyone
reasoned about. DRC-4274 warned about exactly that move, of a promoted section landing under a
clause that does not cover it, so the sentence is widened rather than evaded: it names a whitelist
of two, the git probe and the focus command, and stays a whitelist rather than becoming a general
permission to execute.

Invariant 2's paragraph gains one sentence: the focus command writes nothing anywhere, reads nothing
back, and touches no harness store.

## Reaching a session's terminal (the focus command)

One feature asks the operating system to put a window in front of the operator. Cargento already
knows where each session runs; when the reader clicks through to a session that is waiting on them,
the server runs one bounded command that raises that session's terminal, so the hunt across tabs
ends in one move.

### What runs, exactly

The command is a literal argv per named case, or there is no focus. A session matching no named case
is not focused, and the reader is told that rather than shown a control that does nothing.

The argv is constant except for one field, the target identifier, and that field is substituted into
a fixed position rather than concatenated. No shell, no interpolation, and nothing from a request
body reaches any position. Every command runs with stdin closed, under a timeout, with its output
discarded. A failure is reported to the reader as a focus that did not happen, and never retried.

No working directory is set. The command does not run inside the user's repository, which is what
keeps Scope's repository-execution sentence meaningful rather than sidestepped.

### The named cases, and why the list is this short

Two arrangements are candidates today, because DRC-4382 measured identification for exactly two: a
session in a bare macOS Terminal.app tab, and a session in a tmux pane. The identifier differs by
harness even within one arrangement. A Codex hook keeps the controlling terminal and reads it
directly; a Claude hook does not, because its stdin is the payload pipe, so the device has to be
read one level up off the harness process. In a pane neither works and tmux's own client device is
what finds the window.

Neither arrangement is a named case yet, and this is the part most easily read too generously.
**DRC-4382 measured which identifier finds a terminal. It did not raise one.** The capture says so in
its own words: the lookup counts a tab and never activates one. So a raise command becomes a named
case only once it has been run and recorded, one case per platform, per multiplexer and per harness
where they differ, the way Usage quota reads requires a vendor's endpoint to be named before it
ships. A section listing commands nobody has run would repeat the failure of documenting bounds the
code will not accept.

Linux and Windows are unmeasured, and the capture records them that way. Earlier desk research
suggested Wayland may not permit a background process to raise a window at all, and that Windows
Terminal has no documented way to focus a tab. That is research rather than measurement and this
document does not rely on it: both are simply not named cases, and either becomes one the same way
the macOS cases do, by being run and recorded. iTerm2 is unmeasured for the plainest reason, that it
is not installed on the machine that took the capture.

### The target, and what makes it safe to pass

The target identifier must match `^[A-Za-z0-9._-]{1,128}$` before it reaches an argv position, which
is the grammar `GET /api/observe` already applies to a harness key and a session id, and for the
same reason: the grammar is what bounds the value, not the command that receives it. A target
beginning with a dash is refused, so no value can be read as a flag. That refusal is not
theoretical. DRC-4381 shipped a grammar admitting a leading dash, and review reproduced a poisoned
transcript filename turning a copied command into one that disables a harness's permission checks. A
raise puts the same class of value in an argv position rather than on a clipboard.

Where a platform path builds a script rather than an argv, the identifier passes through the same
escaping the native notifier applies, and the grammar still runs first. That path deserves naming:
`notifications.notify_mac` is already an `osascript` caller and has no bounds section of its own, so
a macOS focus case would be the second caller and the first whose script text is derived from a
store Cargento does not control.

The identifier is derived from a session Cargento observed. It is never taken from a request body.

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

### What is never done

Nothing is typed into a terminal. No keystroke, no text, no newline, by any path. The ask lane's
direction invariant is unchanged by this feature, and any implementation reaching for `send-keys`
contradicts it outright.

No harness store is written. No file inside the user's repository is read or written. No native
permission prompt is answered and no session's state is altered: the window moves, the session does
not.

Nothing is read back. Standard output is discarded rather than parsed, so no pane content, no window
title and no pathname enters Cargento.

### What the command can still cause

This section does not claim the command executes nothing but itself, and the reason is recorded
rather than assumed. The git probe's contract carries the stronger claim, that it "neither writes
there nor executes anything the repository supplies", and DEC-11 exists because a reproduction
falsified it: a repository declaring an LFS filter attribute caused a hook to be installed, through
a path the probe's two flags were never written against. The general lesson is the one this feature
most needs. A bounded command can still cause a program to run through a path its bounds never
contemplated.

So the honest statement is narrower. A multiplexer and a window manager are programs the operator
configured, and what they do when asked to raise a window is theirs. That is the same trust already
extended by running them, and it is the `core.fsmonitor` hazard in smaller form. Naming it is what
keeps this section from inheriting an optimism that has already been shown to be wrong once.

### Who may trigger it

The operator's own action, and nothing else. The route is a POST carrying the per-run capability
`POST /api/events/<harness>` uses, so a document navigation cannot take this path and a local
process without the token cannot either.

Both halves of that matter and neither is decoration. A GET would repeat a gap this repository has
already been bitten by: an attacker page that gets the browser to open a Cargento URL in a tab reads
nothing back, and the "a cross-origin document cannot be read" reasoning does not cover the side
effect. On the quota fetch that side effect was a credential read. Here it would be a window
appearing on the operator's desk. And loopback is not a per-user boundary, so any other account on
the machine can reach the port; the capability is what separates a focus route from `/api/dismiss`,
whose worst outcome is a hidden row.

A rate ceiling and an in-flight gate, so a repeated or looped request cannot repeat the raise. The
route's checks run in the order `POST /api/events/<harness>` establishes, and for its stated reason:
an unsupported case is a 404 before the capability is consulted, so the route cannot be used as an
authentication oracle.

### What is published, and what is written to disk

The response is a single boolean saying whether a focus was attempted. No target identifier, no
pathname and no window title is echoed. Nothing is written to disk by this feature, and nothing
leaves the machine.

### The off switch

`--no-focus`. The flag disables the feature for a run, and it mirrors `--no-git` at every one of that
flag's sites, including the branch that forwards flags to a respawned daemon, so a restart cannot
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
cases, a target reaching an argv position without passing the grammar, a target beginning with a
dash, a keystroke sent into any terminal by any path, output read back or published, a working
directory set on the command, a focus triggered by anything but an authorized operator action, a
focus while the feature is off, a respawned daemon that re-enables it, a target resolved once and
reused rather than resolved at the raise, a raise on a lookup that returned no terminal or more than
one live candidate, or any read or write inside the user's repository.
