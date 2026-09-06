"""Raise the terminal a session is running in: one socket case, or no focus.

`SECURITY.md`'s "Reaching a session's terminal (the focus command)" is the
contract this module implements, and its bounds are the operator's ruling of
2026-09-05 as amended rather than this module's preferences. A leaf: it imports
no runtime module and holds no state, so the coordinator can call it from a
handler thread without ordering concerns, exactly as `git_status` is called.

## Why there is one case and not three

DRC-4382 measured which identifier finds a terminal and never raised one; the
capture says so in its own words, that the lookup counts a tab and never
activates one. DRC-4385 then measured a raise, and only over a UNIX socket, where
macOS consults no responsible process at all. The Apple Event arm that decides
the shipping case — a daemon whose launching terminal has been quit — is
inconclusive: its two responsible-identity fields never reached the record. The
contract gates every Apple Event case behind that arm, so this module names none,
and a socket raise changes what a tmux client displays without bringing a GUI
window forward.

## Why the target is half stored and half resolved

The stored half is the socket and the pane, which a hook gathered from its own
environment and posted through an authenticated event. The volatile half — the
tmux session that pane belongs to, and the device of the client attached to it —
is asked for at the raise and never cached, because a client device demonstrably
moves inside one session: detach and reattach from another tab and it is a
different device, while both readings still mask to `ttys###`.

## What the lookups read, and what is never read back

The two lookup commands' standard output is read, held to a grammar, used to
build the next argv, and dropped. Nothing from them is stored, published or
logged: no pane content, no window title and no pathname enters Cargento's state,
and the raise command's own output is discarded unread. The published answer is a
single boolean, minted by the caller from this function's return value.

## Three declines, and the third is not about the target

Zero attached clients means nobody is watching. More than one live candidate is
ambiguous, and picking one would be the misdirected raise DRC-4382 measured from
the other direction. More than one attached client is refused even when the
target is correct and unambiguous, because `switch-client` resolves the pane to
its window and moves the tmux *session's* current window, which every attached
client displays — measured in DRC-4385's both positive arms and reproduced
outside them. That decline is about who else is watching rather than about
whether the target was found.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable

# The contract's per-field grammars, copied from the document rather than
# invented here. Each refuses a leading dash in its own FIRST character class
# rather than in a sentence beside it, which is the whole lesson of DRC-4381:
# that issue shipped `^[A-Za-z0-9._-]{1,64}$`, whose class holds a dash with
# nothing anchoring position 0, and review reproduced a poisoned value turning a
# copied command into one that disables a harness's permission checks.
TMUX_PANE_RE: Final = re.compile(r"^%[0-9]{1,9}$")
# A NAME, passed as `-L`, and never a path. A session on a custom `-S /path`
# socket yields no target at all, which is an honest decline rather than a
# command that cannot work.
TMUX_SOCKET_RE: Final = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$")
# tmux hands this back rather than a request supplying it, and it still reaches
# an argv position, so it still passes a grammar: a session named `-C` would
# otherwise arrive as a flag. Not in the contract's table, which enumerates the
# fields derived from a session's identity; this one is derived from the first
# lookup and is bounded here for the reason the table's own sentence gives.
TMUX_SESSION_RE: Final = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$")
# The literal `/dev/` prefix is anchored rather than allowing a path and
# resolving it afterwards, so traversal is refused by the shape: no member of the
# class after the prefix is a separator, and a leading dot is refused, which is
# what excludes `/dev/..`.
CLIENT_TTY_RE: Final = re.compile(r"^/dev/[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")

# Slot sentinels. A NUL is in no grammar above, so a legal value can never be
# mistaken for a slot, and a template that lost a substitution would ship a NUL
# argument rather than silently running with a sentinel that looks like a word.
_SOCKET: Final = "\x00socket"
_PANE: Final = "\x00pane"
_SESSION: Final = "\x00session"
_CLIENT: Final = "\x00client"

# Tuples rather than lists, for `GIT_STATUS_ARGV`'s reason: a caller cannot
# append to the argv it was handed, which is the cheapest way a second flag
# reaches a bounded command.
SESSION_NAME_ARGV: Final[tuple[str, ...]] = (
    "tmux",
    "-L",
    _SOCKET,
    "display-message",
    "-p",
    "-t",
    _PANE,
    "#{session_name}",
)
LIST_CLIENTS_ARGV: Final[tuple[str, ...]] = (
    "tmux",
    "-L",
    _SOCKET,
    "list-clients",
    "-t",
    _SESSION,
    "-F",
    "#{client_tty}",
)
SWITCH_CLIENT_ARGV: Final[tuple[str, ...]] = (
    "tmux",
    "-L",
    _SOCKET,
    "switch-client",
    "-c",
    _CLIENT,
    "-t",
    _PANE,
)

# One reading is all a lookup may produce. Bounded so a tmux answering with
# megabytes cannot be held in memory while its first line is taken.
_OUTPUT_CAP: Final = 8_192


@dataclass(frozen=True)
class Target:
    """The durable half of one session's terminal identity.

    Frozen, and never published: `SECURITY.md` forbids echoing a target, so the
    only thing a row carries is a boolean saying one exists.
    """

    socket: str
    pane: str


def valid(target: Target) -> bool:
    """Whether both stored fields still pass their own grammar."""
    return bool(
        TMUX_SOCKET_RE.match(target.socket) is not None
        and TMUX_PANE_RE.match(target.pane) is not None
    )


def target_from(socket: str | None, pane: str | None) -> Target | None:
    """One target, or None. The only constructor anything upstream should use."""
    if not socket or not pane:
        return None
    candidate = Target(socket=socket, pane=pane)
    return candidate if valid(candidate) else None


def fill(template: tuple[str, ...], **values: str) -> tuple[str, ...]:
    """Substitute each slot into its fixed position. Never concatenation.

    Every field lands in the index its template gave it, so two targets differing
    in one field produce argvs differing at exactly one index — which is the
    property `tests/test_focus.py` asserts, because a constant template proves
    nothing about the call built from it.
    """
    slots = {
        _SOCKET: values.get("socket"),
        _PANE: values.get("pane"),
        _SESSION: values.get("session"),
        _CLIENT: values.get("client"),
    }
    return tuple(part if slots.get(part) is None else str(slots[part]) for part in template)


def _run(
    argv: tuple[str, ...],
    *,
    timeout_sec: float,
    runner: Callable[..., Any],
) -> Any | None:
    """One bounded command, or None having produced nothing.

    No `cwd`: the command does not run inside the user's repository, which is what
    keeps Scope's repository-execution sentence meaningful rather than sidestepped.
    `stdin` is closed rather than inherited for `git_status.probe`'s reason — a
    command that can block on a read is a command that burns its whole timeout.
    """
    try:
        return runner(
            argv,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout_sec,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        # OSError covers tmux absent from PATH; SubprocessError covers the
        # timeout. Caught as one because every one of them means the same thing
        # to the reader: the focus did not happen. Never retried.
        return None


def _lines(result: Any) -> list[str]:
    """The command's readings, bounded and stripped. Nothing else looks at output."""
    if getattr(result, "returncode", 1) != 0:
        return []
    raw = getattr(result, "stdout", b"")
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    if not isinstance(raw, (bytes, bytearray)):
        return []
    text = bytes(raw)[:_OUTPUT_CAP].decode("utf-8", "replace")
    return [line.strip() for line in text.splitlines() if line.strip()]


def raise_terminal(
    target: Target,
    *,
    timeout_sec: float,
    runner: Callable[..., Any] = subprocess.run,
) -> bool:
    """Raise this session's pane for the one client watching it, or decline.

    Returns whether a raise was attempted and succeeded. False covers every
    decline and every failure alike, because the published answer is one boolean
    and a reason would be an affordance the contract does not grant.
    """
    if not valid(target):
        return False
    named = _lines(
        _run(
            fill(SESSION_NAME_ARGV, socket=target.socket, pane=target.pane),
            timeout_sec=timeout_sec,
            runner=runner,
        )
    )
    # This also proves the pane still exists: tmux exits non-zero for a pane it
    # cannot resolve, so no separate existence check is needed and none is run.
    if len(named) != 1 or TMUX_SESSION_RE.match(named[0]) is None:
        return False
    clients = _lines(
        _run(
            fill(LIST_CLIENTS_ARGV, socket=target.socket, session=named[0]),
            timeout_sec=timeout_sec,
            runner=runner,
        )
    )
    # Zero: nobody is watching, so there is nothing to raise. More than one: the
    # shared-session decline — raising takes the view from every other client
    # attached, which on a real machine is another person or another agent.
    if len(clients) != 1 or CLIENT_TTY_RE.match(clients[0]) is None:
        return False
    result = _run(
        fill(SWITCH_CLIENT_ARGV, socket=target.socket, client=clients[0], pane=target.pane),
        timeout_sec=timeout_sec,
        runner=runner,
    )
    return getattr(result, "returncode", 1) == 0
