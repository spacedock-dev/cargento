# What Cargento promises

Run as many coding agents as you like. Cargento tells you which ones need you, which ones are
fine, and when it is safe to walk away. One local screen, every harness you use, and nothing
leaves your machine that you cannot switch off.

This file is the user-facing half of the roadmap. It says what Cargento answers today, what backs
each answer, and where each answer stops. The internal half, the scored candidate signals and the
build order, lives on the [Visibility 2x2 board](visibility-2x2/README.md), whose journey view
carries the same five promises in a **Promise** row. The wording is the same in both places on
purpose: one of them faces users and the other faces the build queue, and they should never say
different things. The same rather than byte-identical, and the exception is exactly one character:
each sentence here continues from the promise lead-in and so opens lowercase, while the board
renders it standing alone after a promise label and so opens with a capital. `scripts/validate_plugins.py`
holds those two copies to each other on that rule. The Linear project overview carries a third copy
that no check can reach, so that one is read by hand.

It is written for someone who runs several coding agents at once and cannot see most of them.
Nine or ten terminal tabs, three of them waiting on a question nobody noticed, one burning the
week's quota on the wrong branch.

## How a new user gets there

Four steps, and only the first two are required.

1. Install the plugin. For Claude Code that is `claude plugin marketplace add spacedock-dev/marketplace`
   followed by `claude plugin install cargento@spacedock`. Codex, Antigravity and Gemini CLI each
   have a one-line equivalent in the [README](../README.md). There is nothing to install alongside
   it: the server is Python 3.11 or newer and stdlib only, and it runs standalone with no harness
   plugin at all.
2. Say "open cargento". A local dashboard opens at `http://127.0.0.1:4553`, and it maps every
   harness it finds on the machine regardless of which one launched it. No account, no cloud
   service, no repository token. The server binds IPv4 loopback and nothing else.
3. Read the first screen. Session operations leads with the sessions that are active now, above the
   ones that are only recent history, and gives each active session the same four columns: where it
   is, what it is doing now, what it does next, and whether it is blocked. Since 0.20 that is the
   default view rather than an opt-in one.
4. Optionally connect two things, both one-time and both documented in
   [HOW_TO_USE.md](../HOW_TO_USE.md): the lifecycle hooks that let a blocked session raise a
   desktop notification, and the status-line hook that gives Antigravity its working state and
   forwards its quota.

The moment worth waiting for is step 3, and it is not the layout. It is the first time the board
shows you a second agent that has been blocked on you for eleven minutes while you were watching
the first one. No single harness can tell you that, because no single harness can see the others.

## The five questions of a day

The columns below are the narrative spine of the user journey, in the order a day actually hits
them. Each one gets one promise, the shipped capability that backs it, and the limit that keeps
the promise honest.

### P1. Which of my agents are running?

**We promise:** every session on this machine, across ten harnesses, on one screen, with what is
active now kept apart from what is only recent history.

Backed by the ten-harness collector set (Claude Code, Codex, Pi, Gemini CLI, Antigravity CLI,
GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, Factory Droid), a one-line description of what
each session is, the projects view that groups sessions by the repository they are working in, and
the active-versus-recent split that shipped with the session operations board in 0.19.

Where it stops: a row counts as active only when its harness published evidence that it is. A
recent observation cannot prove that a harness is still open, so history keeps identity and scope
and makes no claim about live state. A harness with no local session data shows as discovered but
disabled rather than silently missing.

### P2. What is it doing, and when should I come back?

**We promise:** for each live session, what it is doing now, what it plans next, how far into the
current turn it is, and an estimate of when that turn ends. It tells you when that changes instead
of making you poll.

Backed by the current-turn elapsed and ETA estimate with its progress bar, the warning that fires
when a request runs or is projected to run past fifteen minutes, a pill per subagent carrying its
measured elapsed, its own model and its own liveness, with a teammate that has finished or gone
quiet still listed rather than dropped, session detail that leads with current activity, the recent token output rate, the model each
session is running on, and desktop notifications on a state change.

Where it stops: Cargento reads a tool call's name and whether it failed, and reads what it
contained only at the few places
[SECURITY.md](../SECURITY.md#irreversible-actions-hook-side-destructive-shape-matching) names, each
reduced to a short summary as it is read. A plan title and a question are the two that reach the
board. DEC-5 lifted that boundary in part on 2026-09-02 rather than confirming it, and SECURITY.md
is where the current line is drawn.
An ETA is an estimate, and it says so.

### P3. Is anything waiting on me?

**We promise:** one queue of everything blocked on you, with what it is waiting for and how long it
has waited. A session can also ask you a question directly and wait for your answer.

Backed by the merged gate queue with a keyboard pass over it, the wait reason surfaced without
opening the session, the standing wait duration, a control on the row that copies the command which
puts you back in the waiting session, a second one that raises that session's terminal where
Cargento can reach it, and the ask lane: a session calls one tool, the question lands
on the dashboard, the answer goes back, and the session continues. An arriving
question raises a notification rather than sitting there unseen.

Where it stops: four of the ten harnesses can report a gate at all, and they are Claude Code,
Codex, Copilot and Cursor. The other six have no gate detection, so the board names that coverage
gap rather than letting a quiet row read as an all clear. What each of the four can say also
differs: Claude names the gate, Codex says one is open without naming it, Copilot says whether a
command or a URL is being asked about, Cursor says only that a permission request is standing and
for how long. The re-entry command is narrower again: two of the ten, Claude Code and Codex,
publish a session id their own CLI takes, so a row from the other eight offers no command rather
than a guessed one. Raising the terminal is narrower still, and on most rows it is not offered at
all: the session has to be running under tmux, to have started while this server has been up, and
to have exactly one terminal attached, or Cargento declines rather than guessing which window you
meant. A raise moves what that terminal displays and does not bring its window to the front of your
desk. Where no raise is offered the queue says how far the feature reached rather than repeating
the absence on every row, and the copy control is what remains. Cargento does not answer a prompt
for you. The one shape it is allowed is the session asking and Cargento
answering
([DEC-2](https://linear.app/recce/issue/DRC-4054/dec-2-decision-let-cargento-act-not-just-observe)).

### P4. Will I hit the wall before the work finishes?

**We promise:** your quota in one place across vendors, with each window's budget shown against its
own clock, so you can see whether there is room before you start rather than partway through.

Backed by the capacity strip, which reads five harnesses by three different routes. Claude and
Cursor are fetched from the vendor with the harness credential once you have answered the
disclosure, Codex and Copilot are read from files they already write to disk, and Antigravity
forwards its own figures through a status-line receipt. Each window shows how much of its allowance
is spent against how much of its time is gone, the pace that comparison implies, when the budget
runs out at that pace, and when the window resets. Beneath it, what the remaining budget buys in
minutes at both paces Cargento has measured, and how long sessions have actually worked in the
project that consumed the most measured working time on this machine. On top of that sit
per-model sub-limits.

Where it stops: what a vendor exposes is what you get. Claude, Codex and Antigravity publish
five-hour and weekly windows, Cursor publishes its monthly billing cycle, and Copilot contributes
per-session AI Units with no percentage because its entitlement is not stored locally. Cursor
fetching is macOS only, and Cursor's cycle has no published start, so its row shows a level and no
clock. There is no per-session cost figure anywhere on the board, and no ranking of which session is
burning fastest right now: every rate the board publishes is a mean over one ten-minute window, and
it names that window rather than claiming an immediacy the arithmetic does not have.
Credential-backed fetching happens only once the disclosure is answered, `--no-usage` refuses it for
a run, and the token is never written, logged, or served. Quota that is expired, rejected, missing,
or stale is withheld rather than rendered as zero.

**Cargento never tells you that you are going to overrun.** It puts the budget's end time beside
the window's reset time and leaves the comparison to you, including on the day they are ninety
seconds apart. There is deliberately no single safe-to-start light and no likelihood: every quota
producer signals failure as an empty list, so a composed verdict reads green exactly when Cargento
can see nothing.

### P5. Did anything die quietly?

**We promise:** nothing finishes invisibly. Work that finished and was never read is flagged, and a
session that ends leaving uncommitted changes says so.

Backed by the finished-and-unread flag, the mark that separates a turn that stopped from a session
still waiting on a reply that never came, the mark that a session is over so it stops reading as one
waiting at its prompt, a way to mark a session handled so it leaves the board, and the
end-of-session git probe that shipped in 0.19.

Where it stops: both of those marks reach only the harnesses whose adapter maps the event that
carries them. An absent mark means no end was observed, never that a session is alive, so it covers
the harnesses with no adapter, a session that predates this server process, and a run under
`--no-events` alike. The session-end mark also lapses one row window after the row it belongs to.
A quiet session is published as idle with nothing elapsed behind it: there is no duration threshold,
so going quiet is a state here and not a reading. The git probe runs one bounded command as a
session ends and publishes two numbers, whether the tree is dirty and how many porcelain entries
changed. Cargento runs no program of its own there, though a repository can carry a committed
attribute that makes git invoke a filter driver you already have installed, git-lfs being the common
one, and that driver may then write inside the repository. It is a residual
[SECURITY.md](../SECURITY.md#the-residual-a-filter-driver-can-still-run-and-can-still-write) states
in full. It never publishes a pathname, and `--no-git` turns it off entirely.
Telling a session that died from one that finished is not shipped yet.

## What we do not promise yet

Three of these are the interesting ones, because each is one decision or one release away rather
than a research project.

Walking away from the desk is the promise this map most wants to make and cannot yet. It needs a
session that is genuinely wedged to be told apart from one that is merely quiet, and it needs
Cargento to reach you somewhere other than a browser tab you are not looking at. The first half
reaches Claude only: the turn's failure total and the turn where nothing succeeded are published,
and the other nine harnesses record tool failure in no shape this can read. The second half is a
build rather than a call now. DEC-4 ruled on 2026-09-02 that Cargento may post a count to an
endpoint you supply, and [SECURITY.md](../SECURITY.md) writes that boundary down before the code
lands.

Gate coverage on the remaining six harnesses is a per-harness measurement job, not a design
question. Today the board is honest about the gap, which is the right behaviour and not the same as
covering it.

Telling a session that died from one that finished is scoped and unstarted.

Everything else, including where each of these sits in the build order and what it is waiting on,
is on the [Cargento: Visibility 2x2 Roadmap](https://linear.app/recce/project/cargento-visibility-2x2-roadmap-c43e013de860/overview)
project in Linear. Its description leads with this same map, and each milestone leads with the user
value it is there to deliver.

## Keeping this file honest

Four rules, and the first one is the whole point.

A promise enters this file only when a shipped capability backs it, and that capability is named in
the same section. Nothing on the roadmap is written here in the future tense.

A cancelled item never becomes a promise. Two were cancelled for exactly the reason a promise would
have been wrong: a composed safe-to-start light that reads green when the data is missing, and a
come-back-later time whose measured lead over simply looking was one minute sixteen seconds.

The limits are part of the promise, not a disclaimer under it. The reason a reader believes the
first four paragraphs of a section is that the fifth one tells them where it ends.

Before and after screenshots are the design record, not the promise. They explain how the interface
got here to people who followed the process, and they belong in
[the session operations board walkthrough](future-ui-exploration/presentations/future-ui-session-operations-board/README.md)
and [the Next UI design record](design-next-ui.md).

## How work links to a promise

Every unit of roadmap work names the promise it serves and how it touches it. The link is two
labels on the Linear issue and a two-sentence **User value** section at the top of its body: who
notices this and when in their day, then the promise ID and the move. The
[burndown workflow](roadmap-burndown/README.md) requires the section at triage and reads the labels
at selection.

| ID | Question | Linear label | Board column |
|---|---|---|---|
| P1 | Which of my agents are running? | `journey:open-sessions` | `open` |
| P2 | What is it doing, and when should I come back? | `journey:mid-flight` | `mid` |
| P3 | Is anything waiting on me? | `journey:stopped-at-gate` | `gate` |
| P4 | Will I hit the wall before the work finishes? | `journey:usage` | `usage` |
| P5 | Did anything die quietly? | `journey:end-of-sessions` | `end` |

The five labels and the five columns predate the IDs. Nothing was renamed to make this table.

The move says how the work touches its promise.

| Move | Meaning | May change this file |
|---|---|---|
| `keep` | Without this, the board says something untrue about the promise. Most defects land here, because the limits are part of the promise. | No |
| `sharpen` | The promise is kept and this makes it more precise, or covers one more harness. | No |
| `extend` | A new clause on an existing promise. | Yes, that promise |
| `new` | Territory no promise covers. Today that is only the Move up a level milestone. | Yes, a new promise |
| `none` | No user-visible effect. The issue says why, and the Linear project overview counts these so the share stays visible. | No |

A decision issue names the promise its ruling unblocks or forecloses, and takes the move of the
work it gates.

Only `extend` and `new` may change what this file says. A `keep` or `sharpen` merge changes no
wording here, and a burndown that closes one says so in its report.
