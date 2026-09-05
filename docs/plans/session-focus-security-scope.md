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

The widening has to be **scoped to the repository clause it sits in**, and this is not a stylistic
preference. That sentence is about running a program *inside a user's repository*. Rewritten as a
general clause, of the shape "running any program other than the two named here", it would make
documented security bugs of three paths Cargento already ships: `notifications.py:148`, where the
native notifier runs `osascript`; `lifecycle.py:614`, where `--daemon` respawns the server; and
`quota.py:743` and `:789`, where the Keychain is read. So the exception is added to the repository
clause and the focus command is named as a separate bound, not folded into a permission to execute
generally.

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
the macOS cases do, by being run and recorded. iTerm2 is unmeasured for the plainest reason, that it
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
one live candidate, or any read or write inside the user's repository.
