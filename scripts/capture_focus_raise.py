#!/usr/bin/env python3
"""Record whether a RAISE works, and from which responsible identity.

DRC-4382 measured which identifier FINDS a terminal. It never raised one, and
its own capture says so: the lookup counts a tab and never activates one. This
records the other half -- whether asking the operating system to bring that
window to the front actually moves it -- and specifically whether it works from
the shape Cargento ships as, which is a detached daemon.

The finding that drives the arm list, measured on this machine and reproducible
with `responsibility_get_pid_responsible_for_pid`: the running Cargento daemon
resolves to the Terminal window that LAUNCHED it, after a double fork, a
`setsid`, and three days re-parented to `launchd`. So macOS attributes its Apple
Events to Terminal. Every successful `osascript` call DRC-4382 made is therefore
that application automating itself while its launcher is alive, which is an
exemption rather than a grant. A2 is the arm that decides whether the exemption
survives the launcher, and A4 the one that decides whether anything works
without it.

Four modes:

    capture_focus_raise.py --dry-run
                                    print what every arm WOULD run and what it
                                    would record. Runs nothing. This is what an
                                    operator reads before authorising anything
    capture_focus_raise.py --arm a5 --allow-a5 --out FILE
                                    run one arm and append a line. The arm's own
                                    flag is required; without it the recorder
                                    refuses and writes nothing
    --verdict FILE                  derive the verdict from the arms in FILE.
                                    Appends it the first time; on a file that
                                    already carries one it COMPARES and says so
    --report FILE                   print the arms and the verdict

## Every arm is off by default, and the off switch is per arm

Nothing here runs because the recorder was invoked. An arm runs when its own
`--allow-<arm>` flag is passed, and `_execute` -- the single function in this
module that starts a process for an arm -- refuses otherwise. A2's
window-quitting step carries a second flag of its own, because it closes a
window an operator opened.

## What redaction is owed, given that the device is the value under test

The sibling recorder, `capture_terminal_identity.py`, reduces every reading to a
shape: `ttys006` becomes `ttys###`. That is right there and wrong here. The
question this file asks is whether a raise aimed at a PARTICULAR device moved a
PARTICULAR tab, and a masked device cannot answer it. So `shape()` and `mask()`
are deliberately not used on any reading this recorder takes, and the redaction
is rebuilt from the question rather than inherited:

Kept whole, because none of it identifies a person or their work: tty device
names, which are per-boot ordinals macOS hands out and RECYCLES; tmux pane and
window ids, which are ordinals on a socket this recorder mints itself; exit
statuses, counts, timings and booleans.

Refused, and each for a reason the sibling did not have to weigh:

- **Window titles.** A Terminal window's title is the running command and the
  working directory -- a repository name, a branch, a customer. No script here
  reads `name` or `custom title` of anything. The raise script reads `tty of
  tab` and nothing else, and the close script the same.
- **The frontmost application, unless it is one of the arms' own subjects.**
  This is the redaction the sibling never needed and the one a careless port
  would miss in both directions. `before` is whatever the operator happened to
  be looking at, which can be a password manager or a medical app. So a bundle
  identifier is admitted only if it is in `SUBJECT_BUNDLES`, a closed set of the
  applications the arms target, and everything else is written down as `other`.
  Movement is still detectable, because `changed` is computed on the RAW
  identifiers before either is redacted -- the sibling's rule for agreement
  between two readings, applied to a different pair.
- **Pathnames of every kind**: no cwd, no `pane_current_path`, no transcript
  path, and no tmux socket path, which names a user's temp directory. One argv
  does carry paths -- A2's launcher names the interpreter, this script and the
  capture file, all absolute and all under a home directory -- so `redact_argv`
  replaces any non-system, non-device path with `<path>/<basename>` on the way
  into the record and never on the way into the command. `/dev/ttys006` and
  `/usr/bin/osascript` both survive it: one is the value under test, the other
  names nobody.
- **Operator-supplied strings in an argv.** The socket label and the session
  name are MINTED by this recorder rather than taken from a flag, so there is no
  user string in a command line to redact and the recorded argv is verbatim.
- **The output of an arm's command.** `docs/plans/session-focus-security-scope.md`
  says a raise reads nothing back, so stdout and stderr of an arm command are
  discarded and only the exit status is kept. Whether the window moved is
  established by the recorder's own before-and-after probes instead, which is
  also the only way to establish it honestly: a command that claims success is
  not evidence that anything moved.

Names of ancestor processes go through the sibling's `walk`, which shapes them,
and the responsible process's name through `RESPONSIBLE_NAMES`, a closed set.
Neither is a device.

## The trap this refuses to fall into

An arm whose target was already frontmost proves nothing: "it moved" and "it was
already there" produce the same after-state. That is not left to whoever runs
the arm to notice. `resolve` establishes the before-state first, CHOOSES a
target that differs from it, and returns `satisfied=False` when it cannot find
one. `run_arm` runs no command at all unless the precondition is satisfied, so a
positive result that could not be distinguished from a no-op is unreachable
rather than merely flagged. An arm in that state records `inconclusive`.

## Exit codes mean something here

Unlike the sibling, nothing in this file is registered as a hook, so there is no
harness reading a 2 as a block. A refusal is loud: an arm invoked without its
flag exits non-zero and writes nothing.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The sibling this extends. Imported rather than copied, and the module boundary
# takes it cleanly: `ps_rows`, `walk`, `ancestry` and `role_of` are the ancestry
# walk, `_device_or_none` and `_bare` the controlling-terminal reads,
# `_dev_tty_open` and `_fd_tty` the `/dev/tty` probe, `_tmux` the ambient tmux
# read, and `tab_query`/`_terminal_tabs` the tab lookup a target has to pass
# before anything is aimed at it. `shape` and `mask` are the two this file must
# NOT use on a reading; see the module docstring.
import capture_terminal_identity as identity

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

FORMAT = 1
RECORD_ARM = "focus_raise"
RECORD_VERDICT = "focus_raise_verdict"
# One line of arrangement the records cannot carry, on the `_provenance`
# precedent the rest of `docs/captures/` sets.
RECORD_NOTE = "focus_raise_note"

BASE_KEYS: tuple[str, ...] = ("format", "record", "os", "at")

# A command that moves a window is fast or it has failed. The sibling's ten
# seconds is for `ps` under load; an `osascript` that has not answered in this
# long is waiting on a TCC prompt, which is an operator decision rather than a
# measurement.
COMMAND_TIMEOUT_SEC = 20
# How long the parent waits for the A2 daemon at each handshake. Generous
# because the operator has to close a window by hand in the middle of it.
HANDSHAKE_TIMEOUT_SEC = 120
HANDSHAKE_POLL_SEC = 0.25

# The applications an arm targets, and the only ones whose identity is written
# down. Everything else the operator happens to have in front is `other`.
SUBJECT_BUNDLES: dict[str, str] = {
    "com.apple.Terminal": "Terminal",
    "com.apple.finder": "Finder",
}
OTHER_APP = "other"

# `ps -o ucomm=` of a responsible process, admitted by name. The question this
# recorder exists to answer is whether the responsible process is Terminal, so
# the set has to be able to say Terminal, say what it was instead when it is one
# of the few things it can be, and say `other` rather than name an arbitrary
# program.
RESPONSIBLE_NAMES = frozenset(
    {"Terminal", "iTerm2", "launchd", "login", "tmux", "bash", "zsh", "sh", "osascript"}
)

# The socket and session this recorder mints for the tmux arms. Minted rather
# than taken from a flag: an operator's own socket label can be a project name,
# and a name in an argv is a name in the record.
TMUX_SOCKET = "cargento-raise"
TMUX_SESSION = "raise"

# A device in no family macOS hands out, for the negative control. `ttys` is the
# real family, so a control device has to be outside it or it may collide with a
# live tab -- which would turn the one arm that proves the instrument into the
# one arm that lies about it.
NO_MATCH_DEVICE = "ttyq999"
# A client tty with no attached client, for the tmux half of the same control.
NO_CLIENT_DEVICE = "ttyq998"

EXPECT_MOVE = "must_move"
EXPECT_HOLD = "must_not_move"
EXPECT_OBSERVE = "observes_only"

ISSUER_RECORDER = "recorder"
ISSUER_DISCLAIMED = "disclaimed_child"
ISSUER_DAEMON = "detached_daemon_past_its_launcher"

SOURCE_TERMINAL = "terminal_app"
SOURCE_TMUX = "tmux"
SOURCE_NONE = "none"

OUTCOME_NOT_AUTHORIZED = "not_authorized"
OUTCOME_INCONCLUSIVE = "inconclusive"
OUTCOME_OBSERVED = "observed"
OUTCOME_HELD_STILL = "held_still"
OUTCOME_CONTROL_FAILED = "control_failed"
OUTCOME_DID_NOT_MOVE = "did_not_move"
OUTCOME_MOVED_ELSEWHERE = "moved_elsewhere"
OUTCOME_MOVED_TO_TARGET = "moved_to_target"

# Why a precondition failed, from a closed set, so a reader can tell an arm that
# could not be set up from one that ran and found nothing.
WHY_OK = "satisfied"
WHY_NO_BEFORE = "before_state_could_not_be_established"
WHY_ALREADY_THERE = "the_target_was_already_the_current_state"
WHY_NO_DISTINCT_TARGET = "no_target_distinct_from_the_current_state"
WHY_AMBIGUOUS = "more_than_one_live_candidate_on_the_device"
WHY_NO_ARRANGEMENT = "the_arms_arrangement_is_not_set_up"

# Placeholders `--dry-run` prints where a run-time reading would go. They are
# placeholders rather than examples on purpose: the security contract requires a
# target be resolved at the moment of the raise and never cached, so there is no
# honest value to print here.
PLACEHOLDER: dict[str, str] = {
    "device": "<a Terminal tab device, resolved at raise time>",
    "client": "<the tmux client tty, resolved at raise time>",
    "pane": "<a tmux pane id, resolved at raise time>",
    "other_client": "<the second client's tty, resolved at raise time>",
    "no_match_device": NO_MATCH_DEVICE,
    "no_client_device": NO_CLIENT_DEVICE,
    "socket": TMUX_SOCKET,
    "session": TMUX_SESSION,
    "out": "<the capture file given to --out>",
    "handshake": "<a scratch handshake file this recorder mints>",
}


@dataclass(frozen=True)
class Arm:
    """One arm: what it runs, what it must prove, and what it may cost."""

    id: str
    what: str
    expectation: str
    issuer: str
    # Where the before-and-after "selected" reading comes from. An arm whose
    # subject is Terminal is read with an Apple Event; a tmux arm is read with
    # `tmux display-message`, which needs no permission at all.
    source: str
    target_app: str | None
    # The arrangement an operator has to have set up, in a closed vocabulary the
    # recorder can check rather than prose it cannot.
    # Which of the two mechanisms the arm exercises. Both, for an arm that
    # steers a multiplexer and then asks an emulator to come forward.
    mechanism: tuple[str, ...] = ()
    # Paths into the arm's own record that must be non-null for it to have
    # answered its question. Movement is not always the evidence: A2 moved a tab
    # and still answered nothing, because the fields saying WHO issued the raise
    # once the launcher was gone came back null, and those are the entire
    # difference between A2 and A1.
    requires_evidence: tuple[tuple[str, ...], ...] = ()
    needs: tuple[str, ...] = ()
    # A cost the arm leaves behind after it finishes. Named in the row because a
    # reader deciding whether to authorise it needs it before, not after.
    durable_side_effect: str | None = None
    note: str = ""


# What macOS is asked to do, which is not the same question as what moved.
# A socket raise never causes a responsible process to be consulted, so an arm
# that only steers tmux can say nothing about the Automation permission in
# either direction. Keeping the two apart is the whole reason this field exists.
MECHANISM_SOCKET = "socket_ipc"
MECHANISM_APPLE_EVENT = "apple_event"
MECHANISMS = (MECHANISM_SOCKET, MECHANISM_APPLE_EVENT)

NEED_TERMINAL_TABS = "two_or_more_terminal_tabs"
NEED_TMUX_SERVER = "a_tmux_server_on_this_recorders_own_socket"
NEED_TWO_CLIENTS = "two_clients_attached_to_one_session"

ARMS: tuple[Arm, ...] = (
    Arm(
        id="a8",
        mechanism=(MECHANISM_APPLE_EVENT, MECHANISM_SOCKET),
        what="negative control: a raise naming a device no live tab holds, and a "
        "tmux target whose client is not attached",
        expectation=EXPECT_HOLD,
        issuer=ISSUER_RECORDER,
        source=SOURCE_TERMINAL,
        target_app=None,
        needs=(NEED_TERMINAL_TABS, NEED_TMUX_SERVER),
        note="Runs first, so that a later success means something. Both halves are "
        "expected to fail loudly and move nothing; a control that moves a window "
        "invalidates every positive in the file.",
    ),
    Arm(
        id="a0",
        mechanism=(),
        what="baseline: `lsappinfo front` only, which is a LaunchServices read "
        "rather than an Apple Event",
        expectation=EXPECT_OBSERVE,
        issuer=ISSUER_RECORDER,
        source=SOURCE_NONE,
        target_app=None,
        note="No permission is involved, so this measures the instrument rather "
        "than the machine: if the frontmost reading is unavailable here, every "
        "before-and-after in the file is worthless.",
    ),
    Arm(
        id="a5",
        mechanism=(MECHANISM_SOCKET,),
        what="one `tmux switch-client` on this recorder's own socket",
        expectation=EXPECT_MOVE,
        issuer=ISSUER_RECORDER,
        source=SOURCE_TMUX,
        target_app=None,
        needs=(NEED_TMUX_SERVER,),
        note="No Apple Event, so no responsible identity is consulted by macOS. "
        "This is the arm that says whether a multiplexer can be steered from a "
        "process whose Apple Events would be refused.",
    ),
    Arm(
        id="a9",
        mechanism=(MECHANISM_SOCKET,),
        what="wrong-socket control: A5 with `-L` omitted, so the command reaches "
        "the default socket rather than the one holding the target",
        expectation=EXPECT_HOLD,
        issuer=ISSUER_RECORDER,
        source=SOURCE_TMUX,
        target_app=None,
        needs=(NEED_TMUX_SERVER,),
        note="A5 without its socket must fail rather than steer something else. "
        "The pane id is an ordinal, so `%1` exists on most servers and a command "
        "that silently found the wrong one would read as a success.",
    ),
    Arm(
        id="a7",
        mechanism=(MECHANISM_SOCKET,),
        what="ambiguity: two clients attached to one session, A5 naming one of them",
        expectation=EXPECT_MOVE,
        issuer=ISSUER_RECORDER,
        source=SOURCE_TMUX,
        target_app=None,
        needs=(NEED_TMUX_SERVER, NEED_TWO_CLIENTS),
        note="Records the other client's pane before and after as well, because "
        "the question is not only whether the named client moved but whether the "
        "one that was not named stayed put.",
    ),
    Arm(
        id="a1",
        mechanism=(MECHANISM_APPLE_EVENT,),
        what="same-app Apple Event: `osascript` telling Terminal to select a tab and activate",
        expectation=EXPECT_MOVE,
        issuer=ISSUER_RECORDER,
        source=SOURCE_TERMINAL,
        target_app="Terminal",
        needs=(NEED_TERMINAL_TABS,),
        durable_side_effect="a TCC AppleEvents grant for this recorder's "
        "responsible process, reversible with `tccutil reset AppleEvents`",
        note="Run from a shell in a Terminal window, this is Terminal automating "
        "itself, which macOS exempts. So a success here is the weakest positive "
        "in the file and A2 is what tells you whether it generalises.",
    ),
    Arm(
        id="a6",
        mechanism=(MECHANISM_SOCKET, MECHANISM_APPLE_EVENT),
        what="A5 then A1 on the client device: steer the multiplexer, then raise "
        "the window the client sits in",
        expectation=EXPECT_MOVE,
        issuer=ISSUER_RECORDER,
        source=SOURCE_TMUX,
        target_app="Terminal",
        needs=(NEED_TMUX_SERVER, NEED_TERMINAL_TABS),
        durable_side_effect="a TCC AppleEvents grant for this recorder's "
        "responsible process, reversible with `tccutil reset AppleEvents`",
        note="The composite a real focus would have to be, since a pane inside an "
        "unfocused window is not in front of anybody.",
    ),
    Arm(
        id="a2",
        mechanism=(MECHANISM_APPLE_EVENT,),
        requires_evidence=(
            ("responsible", "after_launcher_quit_name"),
            ("responsible", "after_launcher_quit_is_self"),
        ),
        what="launcher-quit: a daemon started from a throwaway Terminal window, "
        "that window quit, then a raise from the surviving daemon",
        expectation=EXPECT_MOVE,
        issuer=ISSUER_DAEMON,
        source=SOURCE_TERMINAL,
        target_app="Terminal",
        needs=(NEED_TERMINAL_TABS,),
        durable_side_effect="a TCC AppleEvents grant, and a Terminal window "
        "opened and then closed; the grant is reversible with "
        "`tccutil reset AppleEvents`",
        note="THE GATE ON THE WHOLE APPLE EVENT CASE. Cargento ships as a daemon "
        "whose launcher is long gone, and the responsible identity that made A1 "
        "work is the launcher's. The window-quitting step carries its own flag, "
        "`--allow-a2-quit-window`, because it closes a window an operator opened.",
    ),
    Arm(
        id="a4",
        mechanism=(MECHANISM_APPLE_EVENT,),
        what="alien responsible identity: the same raise issued by a child spawned "
        "with `responsibility_spawnattrs_setdisclaim`, so it is its own "
        "responsible process rather than Terminal's",
        expectation=EXPECT_MOVE,
        issuer=ISSUER_DISCLAIMED,
        source=SOURCE_TERMINAL,
        target_app="Terminal",
        needs=(NEED_TERMINAL_TABS,),
        durable_side_effect="a TCC AppleEvents grant for the disclaimed child, "
        "reversible with `tccutil reset AppleEvents`",
        note="A2 asks whether the exemption survives its launcher; this asks "
        "whether it was ever needed. A disclaimed child is measurably its own "
        "responsible process, which is the one variable this whole file turns on.",
    ),
    Arm(
        id="a3",
        mechanism=(MECHANISM_APPLE_EVENT,),
        what="cross-app: responsible to Terminal, target Finder",
        expectation=EXPECT_MOVE,
        issuer=ISSUER_RECORDER,
        source=SOURCE_NONE,
        target_app="Finder",
        durable_side_effect="a DURABLE TCC AppleEvents grant from this recorder's "
        "responsible process to Finder, reversible only with "
        "`tccutil reset AppleEvents`",
        note="Finder rather than iTerm2, which is not installed on this machine. "
        "Finder is not the daemon's responsible process, so it isolates the "
        "cross-app question, and activating it is trivial to undo. This arm writes "
        "a durable TCC grant.",
    ),
)

ARMS_BY_ID: dict[str, Arm] = {arm.id: arm for arm in ARMS}

ARM_KEYS = frozenset(
    {
        *BASE_KEYS,
        "arm",
        "mechanism",
        "what",
        "expectation",
        "issuer",
        "flag",
        "authorized",
        "precondition",
        "commands",
        "frontmost",
        "selected",
        "responsible",
        "issuer_terminal",
        "ancestry",
        "moved",
        "outcome",
        "durable_side_effect",
        "elapsed_ms",
    }
)
VERDICT_KEYS = frozenset(
    {
        *BASE_KEYS,
        "invocations",
        "arms",
        "per_arm",
        "controls_ran",
        "controls_held",
        "socket_raise",
        "apple_event_raise",
        "verdict",
    }
)
# What `resolve` writes, declared once. `--dry-run` prints this list as the
# promise of what an arm would record, and a test holds `resolve` to it: a
# dry-run advertising a field the recorder does not write is the same defect as
# an arm missing five keys, read from the other end.
PRECONDITION_KEYS: tuple[str, ...] = (
    "expectation",
    "needs",
    "before_state_established",
    "target_device",
    "target_pane",
    "target_client",
    "target_app",
    "target_was_already_the_current_state",
    "live_candidates_on_the_target_device",
    "candidates_on_the_target_device",
    "clients_attached",
    "why",
    "satisfied",
)
COMMAND_KEYS: tuple[str, ...] = (
    "argv",
    "purpose",
    "ran",
    "exit_status",
    "requires_flag",
    "output_discarded",
)


def base_of(record: dict[str, Any]) -> dict[str, Any]:
    """The fields a verdict inherits from the arms it was derived from.

    Not `identity.base_of`, which is otherwise the same function: its
    `BASE_KEYS` carry `harness` and `harness_version`, because every record it
    reads came out of a harness hook. Nothing here is a hook and no arm has a
    harness, so borrowing it raised `KeyError` on the one path an operator runs
    by hand.
    """
    return {key: record[key] for key in BASE_KEYS}


def flag_for(arm_id: str) -> str:
    """The one flag that lets an arm run. Never defaulted, never inferred."""
    return f"--allow-{arm_id}"


A2_QUIT_FLAG = "--allow-a2-quit-window"


class RefusedError(RuntimeError):
    """An arm command was reached without its flag. Nothing ran."""


# --------------------------------------------------------------------------
# The scripts. Every one of them reads `tty` and nothing else -- never `name`,
# never `custom title`, which are the command and the working directory.
# --------------------------------------------------------------------------

# A read: it selects nothing and activates nothing. The empty string on a
# window-less Terminal is deliberate, so the caller can tell "no before state"
# from "a before state that happens to be empty".
SELECTED_TERMINAL_TTY = """tell application "Terminal"
if (count of windows) is 0 then return ""
return tty of selected tab of front window
end tell"""

# Every device a Terminal tab sits on. There is no `lsappinfo` equivalent:
# LaunchServices knows applications, not tabs, so this one costs an Apple Event.
EVERY_TERMINAL_TAB_TTY = """set out to {}
tell application "Terminal"
repeat with w in windows
repeat with t in tabs of w
set end of out to tty of t
end repeat
end repeat
end tell
set text item delimiters to linefeed
return out as text"""


def raise_terminal_tab(device: str) -> str:
    """AppleScript that raises the one tab on a device, and DECLINES otherwise.

    The decline is not politeness. `docs/plans/session-focus-security-scope.md`
    makes a raise on a lookup returning no terminal or more than one live
    candidate a violation, and DRC-4382 measured why: macOS recycles the device,
    and three Terminal tabs matched one device with a single one of them busy,
    because finished tabs still held a device handed out again. So the script
    prefers the single BUSY candidate, falls back to a single candidate of any
    kind, and errors otherwise.

    It errors rather than reporting, because an error is an exit status and the
    contract discards output. Nothing here reads a window title.
    """
    quoted = identity._bare(device).replace('"', "")  # noqa: SLF001
    return "\n".join(
        (
            'tell application "Terminal"',
            "set hits to {}",
            "set live to {}",
            "repeat with w in windows",
            "repeat with t in tabs of w",
            f'if tty of t is "/dev/{quoted}" then',
            "set end of hits to {w, t}",
            "if busy of t then set end of live to {w, t}",
            "end if",
            "end repeat",
            "end repeat",
            "if (count of live) is 1 then",
            "set choice to item 1 of live",
            "else if (count of hits) is 1 then",
            "set choice to item 1 of hits",
            "else",
            'error "focus declined: ambiguous or absent" number 1',
            "end if",
            "set selected tab of (item 1 of choice) to (item 2 of choice)",
            "set index of (item 1 of choice) to 1",
            "activate",
            "end tell",
        )
    )


def selected_terminal_tty() -> str:
    """AppleScript reading the device of Terminal's selected tab, or nothing.

    A read: it selects nothing and activates nothing. It returns the empty
    string when Terminal has no windows, so the caller can tell "no before
    state" from "a before state that happens to be empty".
    """
    return SELECTED_TERMINAL_TTY


def activate_app(app: str) -> str:
    """AppleScript that brings one application forward. A3's whole command."""
    return f'tell application "{app}" to activate'


def open_launcher_window(command: str) -> str:
    """AppleScript opening a NEW Terminal window running a command, and returning its device.

    `do script` with no `in` clause opens a window. The device is returned so
    the close step below can name the window without reading its title.
    """
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    return "\n".join(
        (
            'tell application "Terminal"',
            f'set madeTab to do script "{escaped}"',
            "return tty of madeTab",
            "end tell",
        )
    )


def close_window_on_device(device: str) -> str:
    """AppleScript closing the window holding a device, saving nothing.

    Iterated rather than filtered with `whose`: DRC-4382 measured that
    `every tab of every window whose tty is X` binds the filter to the WINDOW
    and then takes all of its tabs, which counted 2 for a device exactly one tab
    sits on. A close built on that shape would close the wrong window.
    """
    quoted = identity._bare(device).replace('"', "")  # noqa: SLF001
    return "\n".join(
        (
            'tell application "Terminal"',
            "repeat with w in windows",
            "repeat with t in tabs of w",
            f'if tty of t is "/dev/{quoted}" then',
            "close w saving no",
            "exit repeat",
            "end if",
            "end repeat",
            "end repeat",
            "end tell",
        )
    )


# --------------------------------------------------------------------------
# The readings. Every one is a keyword so a test can substitute it, which is
# the shape the sibling recorder takes and for the same reason: an arm that can
# only be exercised on a machine with a particular arrangement is an arm nobody
# checks.
# --------------------------------------------------------------------------


def _read(argv: Sequence[str]) -> tuple[int, str]:
    """Run a READ and keep its output. Never used for an arm command."""
    try:
        done = subprocess.run(  # noqa: S603
            list(argv),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout.strip()


def read_frontmost() -> str | None:
    """The frontmost application's bundle identifier, RAW and unredacted.

    Raw because movement is computed on the raw pair and redaction applied to
    each end afterwards. `lsappinfo` is a LaunchServices query: no Apple Event,
    no TCC prompt, nothing moved.
    """
    code, asn = _read(["/usr/bin/lsappinfo", "front"])
    if code != 0 or not asn:
        return None
    code, line = _read(["/usr/bin/lsappinfo", "info", "-only", "bundleID", asn])
    if code != 0 or "=" not in line:
        return None
    # `"CFBundleIdentifier"="com.apple.Terminal"` -- the value, unquoted.
    return line.rsplit("=", 1)[-1].strip().strip('"') or None


def read_terminal_selected() -> str | None:
    code, out = _read(["/usr/bin/osascript", "-e", selected_terminal_tty()])
    if code != 0:
        return None
    return identity._device_or_none(out)  # noqa: SLF001


def read_tmux_selected(socket: str, client: str | None) -> str | None:
    if not client:
        return None
    code, out = _read(["tmux", "-L", socket, "display-message", "-p", "-t", client, "#{pane_id}"])
    return out or None if code == 0 else None


def read_tmux_clients(socket: str) -> list[dict[str, str]]:
    """Attached clients on this recorder's own socket, as tty and pane.

    Deliberately not `#{client_session}`: a session name is a name, and the only
    sessions this recorder targets are ones it minted itself.
    """
    code, out = _read(
        ["tmux", "-L", socket, "list-clients", "-F", "#{client_tty}\t#{client_activity}"]
    )
    if code != 0 or not out:
        return []
    found: list[dict[str, str]] = []
    for line in out.splitlines():
        tty = line.split("\t")[0].strip()
        device = identity._device_or_none(tty)  # noqa: SLF001
        if device:
            found.append({"tty": identity._bare(device)})  # noqa: SLF001
    return found


def read_tmux_panes(socket: str) -> list[str]:
    code, out = _read(["tmux", "-L", socket, "list-panes", "-a", "-F", "#{pane_id}"])
    if code != 0 or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def responsible_pid(pid: int) -> int | None:
    """The process macOS attributes this one's Apple Events to.

    The whole question. On this machine the running Cargento daemon answers
    Terminal, after a double fork, a `setsid` and three days re-parented to
    launchd -- which is why an `osascript` success from inside a Terminal window
    is an exemption rather than a grant.
    """
    try:
        lib = ctypes.CDLL(None, use_errno=True)
        fn = lib.responsibility_get_pid_responsible_for_pid
    except (AttributeError, OSError):
        return None
    fn.argtypes = [ctypes.c_int]
    fn.restype = ctypes.c_int
    answer = int(fn(int(pid)))
    return answer if answer > 0 else None


def process_name(pid: int | None) -> str | None:
    if pid is None:
        return None
    code, out = _read(["ps", "-o", "ucomm=", "-p", str(pid)])
    if code != 0 or not out:
        return None
    # A closed set, because an arbitrary `ucomm` is an arbitrary program name.
    return out if out in RESPONSIBLE_NAMES else OTHER_APP


@dataclass(frozen=True)
class Readers:
    """Every reading the recorder takes, in one bundle a test can replace."""

    frontmost: Callable[[], str | None] = read_frontmost
    terminal_selected: Callable[[], str | None] = read_terminal_selected
    tmux_selected: Callable[[str, str | None], str | None] = read_tmux_selected
    tmux_clients: Callable[[str], list[dict[str, str]]] = read_tmux_clients
    tmux_panes: Callable[[str], list[str]] = read_tmux_panes
    terminal_tabs: Callable[[str | None], dict[str, int] | None] = identity._terminal_tabs  # noqa: SLF001
    responsible: Callable[[int], int | None] = responsible_pid
    name_of: Callable[[int | None], str | None] = process_name


@dataclass
class Targets:
    """What one arm aims at, resolved at raise time and never cached."""

    device: str | None = None
    pane: str | None = None
    client: str | None = None
    other_client: str | None = None
    app: str | None = None
    candidates: int | None = None
    busy_candidates: int | None = None
    clients_attached: int = 0


@dataclass
class Snapshot:
    """The before or after state of the world, as raw readings."""

    frontmost: str | None = None
    selected: str | None = None
    other_client_pane: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def app_label(bundle: str | None) -> str | None:
    """A bundle identifier reduced to a name, or `other`.

    The redaction that is new here. `before` is whatever the operator was
    looking at, and that is theirs. Only the applications an arm targets are
    named; everything else is `other`. Movement survives this, because it is
    computed on the raw pair before either end is labelled.
    """
    if not bundle:
        return None
    return SUBJECT_BUNDLES.get(bundle, OTHER_APP)


def observe_state(arm: Arm, targets: Targets, readers: Readers, socket: str) -> Snapshot:
    """One reading of the world, for the arm's own subject."""
    selected: str | None = None
    if arm.source == SOURCE_TERMINAL:
        selected = readers.terminal_selected()
    elif arm.source == SOURCE_TMUX:
        selected = readers.tmux_selected(socket, targets.client)
    other = (
        readers.tmux_selected(socket, targets.other_client)
        if arm.source == SOURCE_TMUX and targets.other_client
        else None
    )
    return Snapshot(frontmost=readers.frontmost(), selected=selected, other_client_pane=other)


# --------------------------------------------------------------------------
# The precondition. This is where the already-frontmost trap is made
# unreachable rather than merely noticed.
# --------------------------------------------------------------------------


def _resolve_terminal_target(before: Snapshot, readers: Readers) -> tuple[Targets, str]:
    """A Terminal tab distinct from the selected one, or a reason there is none."""
    if before.selected is None:
        return Targets(), WHY_NO_BEFORE
    tabs = readers.terminal_tabs(before.selected)
    devices = _terminal_devices(readers)
    others = [d for d in devices if d != identity._bare(before.selected)]  # noqa: SLF001
    if not others:
        return Targets(), WHY_NO_DISTINCT_TARGET
    chosen = others[0]
    counts = readers.terminal_tabs(chosen) or {}
    candidates = counts.get("tabs")
    busy = counts.get("busy_tabs")
    if candidates is None:
        return Targets(), WHY_NO_BEFORE
    # The contract's ambiguity bound, applied before anything is aimed anywhere:
    # a device more than one LIVE tab sits on does not identify a window, and
    # macOS recycling the device is how that happens rather than a hypothetical.
    if (busy or 0) > 1:
        return Targets(device=chosen, candidates=candidates, busy_candidates=busy), WHY_AMBIGUOUS
    del tabs
    return (
        Targets(device=chosen, app="Terminal", candidates=candidates, busy_candidates=busy),
        WHY_OK,
    )


def _terminal_devices(readers: Readers) -> list[str]:
    """Every device a Terminal tab sits on, in a stable order.

    Read with one Apple Event that asks for `tty` and nothing else. There is no
    `lsappinfo` equivalent: LaunchServices knows applications, not tabs.
    """
    code, listed = _read(["/usr/bin/osascript", "-e", EVERY_TERMINAL_TAB_TTY])
    if code != 0:
        return []
    seen: list[str] = []
    for line in listed.splitlines():
        device = identity._device_or_none(line.strip())  # noqa: SLF001
        bare = identity._bare(device) if device else ""  # noqa: SLF001
        if bare and bare not in seen:
            seen.append(bare)
    del readers
    return seen


def _resolve_tmux_target(
    arm: Arm, before: Snapshot, readers: Readers, socket: str, targets: Targets
) -> tuple[Targets, str]:
    """A pane on this recorder's socket that the named client is not already on."""
    if not targets.client:
        return targets, WHY_NO_ARRANGEMENT
    if before.selected is None:
        return targets, WHY_NO_BEFORE
    panes = [pane for pane in readers.tmux_panes(socket) if pane != before.selected]
    if not panes:
        return targets, WHY_NO_DISTINCT_TARGET
    targets.pane = panes[0]
    if NEED_TWO_CLIENTS in arm.needs and targets.clients_attached < 2:
        return targets, WHY_NO_ARRANGEMENT
    return targets, WHY_OK


# One early return per way a target can fail to differ from the current state,
# which is the shape this function exists to have: a chain that falls through to
# a default is exactly how "it was already there" gets recorded as a success.
def _choose_target(  # noqa: PLR0911
    arm: Arm, before: Snapshot, targets: Targets, readers: Readers, socket: str
) -> tuple[Targets, str]:
    """Pick something to aim at that is NOT the current state, or say why not.

    This is where the already-frontmost trap dies. Every branch either returns a
    target that differs from the before-state or a reason, and the one caller
    starts no process on a reason.
    """
    if before.frontmost is None:
        return targets, WHY_NO_BEFORE
    if arm.expectation == EXPECT_OBSERVE:
        return targets, WHY_OK
    if arm.id in {"a8", "a9"}:
        # The controls aim at something that cannot be the current state by
        # construction, so the only precondition left is a readable before.
        targets.device = NO_MATCH_DEVICE
        targets.client = targets.client or NO_CLIENT_DEVICE
        targets.pane = _first_pane(readers, socket)
        return targets, WHY_OK if targets.pane else WHY_NO_ARRANGEMENT
    if arm.source == SOURCE_TMUX:
        targets, why = _resolve_tmux_target(arm, before, readers, socket, targets)
        if why == WHY_OK and arm.target_app == "Terminal":
            # A6 raises the window the client sits in, so its Terminal target is
            # the client's own device rather than a tab chosen for difference.
            targets.device = targets.client
        return targets, why
    if arm.target_app and arm.target_app != "Terminal":
        # An app target: the trap in its plainest form. Finder already in front
        # makes "it moved" and "it was already there" the same after-state.
        already = app_label(before.frontmost) == arm.target_app
        return targets, WHY_ALREADY_THERE if already else WHY_OK
    found, why = _resolve_terminal_target(before, readers)
    targets.device = found.device
    targets.candidates = found.candidates
    targets.busy_candidates = found.busy_candidates
    if why == WHY_OK and targets.device == identity._bare(before.selected or ""):  # noqa: SLF001
        return targets, WHY_ALREADY_THERE
    return targets, why


def resolve(
    arm: Arm, *, readers: Readers, socket: str = TMUX_SOCKET
) -> tuple[Targets, Snapshot, dict[str, Any]]:
    """The before-state, a target chosen to differ from it, and the verdict on both.

    An arm that cannot establish a before-state is not an arm, and an arm whose
    target is already the current state proves nothing. Both come back
    `satisfied=False`, and `run_arm` starts no process for either.
    """
    targets = Targets(app=arm.target_app)
    clients = readers.tmux_clients(socket) if arm.source == SOURCE_TMUX else []
    targets.clients_attached = len(clients)
    if clients:
        targets.client = clients[0]["tty"]
        if len(clients) > 1:
            targets.other_client = clients[1]["tty"]
    before = observe_state(arm, targets, readers, socket)
    targets, why = _choose_target(arm, before, targets, readers, socket)

    precondition = {
        "expectation": arm.expectation,
        "needs": list(arm.needs),
        "before_state_established": before.frontmost is not None
        and (arm.source == SOURCE_NONE or before.selected is not None),
        "target_device": targets.device,
        "target_pane": targets.pane,
        "target_client": targets.client,
        "target_app": targets.app,
        "target_was_already_the_current_state": why == WHY_ALREADY_THERE,
        "live_candidates_on_the_target_device": targets.busy_candidates,
        "candidates_on_the_target_device": targets.candidates,
        "clients_attached": targets.clients_attached,
        "why": why,
        "satisfied": why == WHY_OK,
    }
    return targets, before, precondition


def _first_pane(readers: Readers, socket: str) -> str | None:
    panes = readers.tmux_panes(socket)
    return panes[0] if panes else None


# --------------------------------------------------------------------------
# The plan. `--dry-run` prints exactly this and runs nothing.
# --------------------------------------------------------------------------


def plan(
    arm: Arm, targets: Targets, *, socket: str = TMUX_SOCKET, out: str = ""
) -> list[dict[str, Any]]:
    """Every command the arm would run, in order, as argv lists."""
    device = targets.device or PLACEHOLDER["device"]
    client = targets.client or PLACEHOLDER["client"]
    pane = targets.pane or PLACEHOLDER["pane"]
    steps: list[dict[str, Any]] = []
    if arm.id == "a8":
        steps = [
            {
                "purpose": "a Terminal raise naming a device no live tab holds",
                "argv": ["/usr/bin/osascript", "-e", raise_terminal_tab(NO_MATCH_DEVICE)],
            },
            {
                "purpose": "a tmux switch naming a client that is not attached",
                "argv": ["tmux", "-L", socket, "switch-client", "-c", NO_CLIENT_DEVICE, "-t", pane],
            },
        ]
    elif arm.id == "a0":
        steps = [
            {
                "purpose": "the LaunchServices frontmost read",
                "argv": ["/usr/bin/lsappinfo", "front"],
            }
        ]
    elif arm.id in {"a5", "a7"}:
        steps = [
            {
                "purpose": "steer the named client to the target pane",
                "argv": ["tmux", "-L", socket, "switch-client", "-c", client, "-t", pane],
            }
        ]
    elif arm.id == "a9":
        steps = [
            {
                "purpose": "A5 with `-L` omitted, so it reaches the default socket",
                "argv": ["tmux", "switch-client", "-c", client, "-t", pane],
            }
        ]
    elif arm.id == "a1":
        steps = [
            {
                "purpose": "raise the Terminal tab on the target device",
                "argv": ["/usr/bin/osascript", "-e", raise_terminal_tab(device)],
            }
        ]
    elif arm.id == "a6":
        steps = [
            {
                "purpose": "steer the named client to the target pane",
                "argv": ["tmux", "-L", socket, "switch-client", "-c", client, "-t", pane],
            },
            {
                "purpose": "raise the Terminal window the client sits in",
                "argv": ["/usr/bin/osascript", "-e", raise_terminal_tab(device)],
            },
        ]
    elif arm.id == "a4":
        steps = [
            {
                "purpose": "the same raise, issued by a child spawned with "
                "responsibility_spawnattrs_setdisclaim so it is its own "
                "responsible process",
                "argv": ["/usr/bin/osascript", "-e", raise_terminal_tab(device)],
                "spawned": "posix_spawn with disclaim",
            }
        ]
    elif arm.id == "a3":
        steps = [
            {
                "purpose": "activate Finder, which is not this process's responsible process",
                "argv": ["/usr/bin/osascript", "-e", activate_app("Finder")],
            }
        ]
    elif arm.id == "a2":
        steps = _plan_a2(device, out or PLACEHOLDER["out"])
    return steps


def _plan_a2(device: str, out: str) -> list[dict[str, Any]]:
    """A2's orchestration, with the window-quitting step named as its own gate."""
    handshake = PLACEHOLDER["handshake"]
    launcher = (
        f"{sys.executable} {os.path.abspath(__file__)} --a2-daemon "
        f"--a2-handshake {handshake} --a2-target {device} --out {out}"
    )
    return [
        {
            "purpose": "open a throwaway Terminal window running the daemon launcher",
            "argv": ["/usr/bin/osascript", "-e", open_launcher_window(launcher)],
        },
        {
            "purpose": "wait for the daemon to report its pid and its responsible process",
            "argv": [],
            "waits_for": handshake,
        },
        {
            "purpose": "QUIT the launcher window",
            "argv": ["/usr/bin/osascript", "-e", close_window_on_device("<the launcher's device>")],
            "requires_flag": A2_QUIT_FLAG,
        },
        {
            "purpose": "the daemon, now past its launcher, re-reads its responsible "
            "process and issues the raise",
            "argv": ["/usr/bin/osascript", "-e", raise_terminal_tab(device)],
            "issued_by": ISSUER_DAEMON,
        },
    ]


# --------------------------------------------------------------------------
# The one place an arm command runs.
# --------------------------------------------------------------------------


def _execute(argv: Sequence[str], *, allowed: bool) -> int:
    """Run one arm command and keep ONLY its exit status.

    The single gate. Every path that could move a window comes through here, and
    `allowed` is the arm's own flag rather than anything derived. Output is
    discarded because `docs/plans/session-focus-security-scope.md` says a raise
    reads nothing back -- and because a command claiming success is not evidence
    that a window moved. The before-and-after probes are.
    """
    if not allowed:
        raise RefusedError(argv[0] if argv else "an arm command")
    try:
        done = subprocess.run(  # noqa: S603
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=COMMAND_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124
    except (OSError, subprocess.SubprocessError):
        return 127
    return done.returncode


def _spawn_disclaimed(argv: Sequence[str], *, allowed: bool) -> tuple[int | None, int]:
    """Spawn a child that is its OWN responsible process, and say which pid it is.

    A4's whole mechanism. `posix_spawn` with `responsibility_spawnattrs_setdisclaim`
    is the documented way to break the responsibility inheritance that makes
    every Apple Event from this process tree look like Terminal's. Verified on
    this machine against a harmless target: an ordinary child answers the same
    responsible pid as its parent, a disclaimed child answers itself.

    The pid is returned so the caller can read the child's responsible process
    while it is still alive -- which is the reading A4 exists for, and which is
    unavailable once the child has exited.

    `allowed` is not decoration here, and the gap it closes was found by running
    the suite rather than by reading the code: this is a SECOND way to start a
    process, `_execute` never saw it, and `run_arm`'s injected executor could not
    intercept it. So the test suite spawned three real `osascript` raises while
    every spy in it reported nothing had run. They declined -- the target device
    held no tab -- but that was the arrangement's luck rather than the gate's
    doing, which is exactly the shape of thing this recorder exists to refuse.
    """
    if not allowed:
        raise RefusedError(argv[0] if argv else "a disclaimed spawn")
    lib = ctypes.CDLL(None, use_errno=True)
    lib.posix_spawnattr_init.argtypes = [ctypes.c_void_p]
    lib.posix_spawnattr_init.restype = ctypes.c_int
    lib.posix_spawnattr_destroy.argtypes = [ctypes.c_void_p]
    lib.posix_spawnattr_destroy.restype = ctypes.c_int
    lib.responsibility_spawnattrs_setdisclaim.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.responsibility_spawnattrs_setdisclaim.restype = ctypes.c_int
    lib.posix_spawn.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_char_p),
        ctypes.POINTER(ctypes.c_char_p),
    ]
    lib.posix_spawn.restype = ctypes.c_int

    attr = ctypes.c_void_p()
    if lib.posix_spawnattr_init(ctypes.byref(attr)) != 0:
        return None, 127
    try:
        if lib.responsibility_spawnattrs_setdisclaim(ctypes.byref(attr), 1) != 0:
            return None, 127
        words = (ctypes.c_char_p * (len(argv) + 1))()
        for index, word in enumerate(argv):
            words[index] = word.encode()
        words[len(argv)] = None
        envp = (ctypes.c_char_p * 1)()
        envp[0] = None
        pid = ctypes.c_int(0)
        code = lib.posix_spawn(
            ctypes.byref(pid), argv[0].encode(), None, ctypes.byref(attr), words, envp
        )
    finally:
        lib.posix_spawnattr_destroy(ctypes.byref(attr))
    if code != 0:
        return None, 127
    return pid.value, 0


# Absolute paths that name no person: a binary in a system or package-manager
# location. Anything else beginning with a slash is somebody's home, somebody's
# repository, or somebody's temp directory, and none of those belong in a record.
SYSTEM_PREFIXES: tuple[str, ...] = ("/usr/bin/", "/bin/", "/sbin/", "/usr/sbin/", "/opt/homebrew/")
# The one exception, and it is the value under test: a device node.
DEVICE_PREFIX = "/dev/"
# Matched anywhere in a word rather than at its start. A2's launcher argv is one
# word -- a whole AppleScript -- and the interpreter path inside it is preceded
# by an escaped quote, so a leading-character test walked straight past it and
# wrote a home directory into a record under a green suite.
_ABSOLUTE_PATH = re.compile(r"/(?:[A-Za-z0-9._~+-]+/)*[A-Za-z0-9._~+-]+")


def _names_nobody(path: str) -> bool:
    # `== "/dev"` as well as the prefix: `/dev/<the launcher's device>` stops the
    # match at `/dev`, and without this that becomes `<path>/dev`.
    return path == DEVICE_PREFIX.rstrip("/") or path.startswith((DEVICE_PREFIX, *SYSTEM_PREFIXES))


def redact_argv(argv: Sequence[str]) -> list[str]:
    """An argv as it is RECORDED: verbatim, minus any pathname that names a user.

    Applied to the record and never to what runs, so the command is exact and
    the evidence file is not. A2 is why this exists at all -- its launcher argv
    carries the interpreter, this script and the capture file, all of them
    absolute and all of them under a home directory. Nothing else in the file
    goes near a path.

    `/dev/ttys006` survives, because a device is the value the whole capture is
    about, and so does `/usr/bin/osascript`, because a reader checking which
    binary ran needs it and a system path names nobody.
    """
    return [
        _ABSOLUTE_PATH.sub(
            lambda found: (
                found.group(0)
                if _names_nobody(found.group(0))
                else "<path>/" + os.path.basename(found.group(0))
            ),
            word,
        )
        for word in argv
    ]


# --------------------------------------------------------------------------
# Running one arm.
# --------------------------------------------------------------------------


def _moved(before: Snapshot, after: Snapshot) -> bool | None:
    """Whether anything changed, computed on the RAW readings.

    Before redaction, for the reason the sibling computes its agreement on raw
    devices: two applications that both redact to `other` would compare equal
    and a real move would read as a no-op.
    """
    pairs = [
        (before.frontmost, after.frontmost),
        (before.selected, after.selected),
    ]
    known = [(left, right) for left, right in pairs if left is not None or right is not None]
    if not known:
        return None
    return any(left != right for left, right in known)


def _reached(arm: Arm, targets: Targets, after: Snapshot) -> bool | None:
    hits: list[bool] = []
    if arm.target_app:
        hits.append(app_label(after.frontmost) == arm.target_app)
    if targets.pane and arm.source == SOURCE_TMUX:
        hits.append(after.selected == targets.pane)
    if targets.device and arm.source == SOURCE_TERMINAL:
        hits.append(
            after.selected is not None
            and identity._bare(after.selected) == identity._bare(targets.device)  # noqa: SLF001
        )
    if not hits:
        return None
    return all(hits)


def _unanswered(record: dict[str, Any]) -> str | None:
    """Why the arm answered nothing, or `None` if it did answer.

    Three ways an arm can fail to ask its question, kept together because they
    are one idea. The third is the one that was missing: a step behind its own
    flag is the step that MAKES the arm the question it is. A2's is quitting the
    window that launched the daemon, and without it the raise runs with the
    launcher alive, which is the case three other arms already cover. Skipping
    it and still reporting a positive is a verdict composed over evidence the
    arm did not gather, and it read `moved_to_target` for an arm that answered
    nothing at all.
    """
    if not record["authorized"]:
        return OUTCOME_NOT_AUTHORIZED
    if not record["precondition"]["satisfied"]:
        return OUTCOME_INCONCLUSIVE
    if any(step.get("requires_flag") and not step["ran"] for step in record["commands"]):
        return OUTCOME_INCONCLUSIVE
    for path in ARMS_BY_ID[str(record["arm"])].requires_evidence:
        cursor: Any = record
        for key in path:
            cursor = cursor.get(key) if isinstance(cursor, dict) else None
        if cursor is None:
            return OUTCOME_INCONCLUSIVE
    return None


def outcome_of(record: dict[str, Any]) -> str:
    """The arm's own answer, DERIVED from what it recorded."""
    unanswered = _unanswered(record)
    if unanswered:
        return unanswered
    moved = record["moved"]
    if record["expectation"] == EXPECT_OBSERVE:
        return OUTCOME_OBSERVED
    if record["expectation"] == EXPECT_HOLD:
        return OUTCOME_HELD_STILL if moved is False else OUTCOME_CONTROL_FAILED
    if moved is not True:
        return OUTCOME_DID_NOT_MOVE
    reached = (
        record["frontmost"]["after_is_the_target"] or record["selected"]["after_is_the_target"]
    )
    return OUTCOME_MOVED_TO_TARGET if reached else OUTCOME_MOVED_ELSEWHERE


def _issuer_terminal() -> dict[str, Any]:
    """The recorder's own controlling terminal, kept whole. The value under test."""
    rows = identity.ps_rows(os.getpid())
    raw = str(rows[0]["tty"]) if rows else None
    device = identity._device_or_none(raw)  # noqa: SLF001
    return {
        "tty": identity._bare(device) if device else None,  # noqa: SLF001
        "dev_tty_open": identity._dev_tty_open(),  # noqa: SLF001
        "fd0": identity._fd_tty(0),  # noqa: SLF001
        "in_a_tmux_pane": bool(identity._tmux("#{pane_id}")),  # noqa: SLF001
    }


def _ancestry_of(pid: int) -> dict[str, Any]:
    """The issuer's ppid chain, through the sibling's walk and its masking.

    The one place a record carries a SHAPED device, and the difference is the
    question rather than an oversight. `selected` and `target_device` are the
    values under test and stay whole; the chain is context about which processes
    the issuer sits under, and `ttys###` answers that as well as `ttys006` does.
    Leaving the chain whole would widen the file's exposure for nothing.

    `harness=""` on purpose: nothing here is a harness, and an unknown key gives
    `walk` an empty executable set, so no ancestor is mislabelled.
    """
    return identity.ancestry(identity.walk(identity.ps_rows(pid), harness=""))


def run_arm(
    arm: Arm,
    *,
    allowed: bool,
    readers: Readers | None = None,
    execute: Callable[[Sequence[str], bool], int] | None = None,
    # The disclaimed spawn is a SECOND way to start a process, so it needs a
    # second seam. Without one the injected executor above reported that nothing
    # had run while A4 spawned a real raise past it.
    spawn: Callable[[Sequence[str], bool], tuple[int | None, int]] | None = None,
    socket: str = TMUX_SOCKET,
    out: str = "",
    at: str = "",
    # Flags beyond the arm's own `--allow-<id>`. Empty by default, so a step
    # behind a second flag stays unreachable unless a caller names it.
    extra_flags: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """One arm, run or refused, as a record.

    Nothing starts a process before `precondition["satisfied"]` is true, which
    is what makes the already-frontmost trap unreachable rather than reported.
    """
    started = time.perf_counter()
    readers = readers or Readers()
    runner = execute or (lambda argv, ok: _execute(argv, allowed=ok))
    spawner = spawn or (lambda argv, ok: _spawn_disclaimed(argv, allowed=ok))
    targets, before, precondition = resolve(arm, readers=readers, socket=socket)

    issuer_pid = os.getpid()
    # Read once. Two reads of the same question can disagree, and a record
    # whose name and `is_self` came from different readings describes no process.
    issuer_responsible = readers.responsible(issuer_pid)
    responsible = {
        "issuer_is_this_recorder": arm.issuer == ISSUER_RECORDER,
        "issuer_kind": arm.issuer,
        "name": readers.name_of(issuer_responsible),
        "is_self": issuer_responsible == issuer_pid,
        "after_launcher_quit_name": None,
        "after_launcher_quit_is_self": None,
    }

    commands: list[dict[str, Any]] = []
    ran = allowed and precondition["satisfied"]
    if ran:
        for step in plan(arm, targets, socket=socket, out=out):
            if not step["argv"]:
                continue
            if step.get("requires_flag") and step["requires_flag"] not in extra_flags:
                # The window-quitting step, gated on its own flag because it
                # closes something an operator opened. Passing that flag is the
                # only way it runs.
                commands.append(
                    {
                        "argv": redact_argv(step["argv"]),
                        "purpose": step["purpose"],
                        "ran": False,
                        "exit_status": None,
                        "requires_flag": step["requires_flag"],
                        "output_discarded": True,
                    }
                )
                continue
            spawned = step.get("spawned")
            if spawned:
                child, code = spawner(step["argv"], True)
                if child is not None:
                    # Read while the child is alive: once it has exited there is
                    # no responsible process to ask about, and this reading is
                    # the entire point of the arm.
                    child_responsible = readers.responsible(child)
                    responsible["name"] = readers.name_of(child_responsible)
                    responsible["is_self"] = child_responsible == child
                    # The child's own status, not `posix_spawn`'s: a spawn
                    # succeeds long before the raise it started has an answer.
                    code = _reap(child)
            else:
                code = runner(list(step["argv"]), True)
            commands.append(
                {
                    "argv": redact_argv(step["argv"]),
                    "purpose": step["purpose"],
                    "ran": True,
                    "exit_status": code,
                    "requires_flag": None,
                    "output_discarded": True,
                }
            )
    else:
        commands = [
            {
                "argv": redact_argv(step["argv"]),
                "purpose": step["purpose"],
                "ran": False,
                "exit_status": None,
                "requires_flag": step.get("requires_flag"),
                "output_discarded": True,
            }
            for step in plan(arm, targets, socket=socket, out=out)
        ]

    after = observe_state(arm, targets, readers, socket) if ran else Snapshot()
    record: dict[str, Any] = {
        "format": FORMAT,
        "record": RECORD_ARM,
        "os": platform.system().lower(),
        "at": at or identity.stamp(),
        "arm": arm.id,
        "what": arm.what,
        "expectation": arm.expectation,
        "issuer": arm.issuer,
        "flag": flag_for(arm.id),
        "authorized": allowed,
        "mechanism": list(arm.mechanism),
        "precondition": precondition,
        "commands": commands,
        "frontmost": {
            "before": app_label(before.frontmost),
            "after": app_label(after.frontmost) if ran else None,
            "changed": (before.frontmost != after.frontmost) if ran else None,
            "after_is_the_target": (
                app_label(after.frontmost) == arm.target_app if ran and arm.target_app else None
            ),
        },
        "selected": {
            "source": arm.source,
            "before": before.selected,
            "after": after.selected if ran else None,
            "changed": (before.selected != after.selected) if ran else None,
            "after_is_the_target": _reached(arm, targets, after) if ran else None,
            "other_client_before": before.other_client_pane,
            "other_client_after": after.other_client_pane if ran else None,
            "other_client_changed": (
                before.other_client_pane != after.other_client_pane if ran else None
            ),
        },
        "responsible": responsible,
        "issuer_terminal": _issuer_terminal(),
        "ancestry": _ancestry_of(issuer_pid),
        "moved": _moved(before, after) if ran else None,
        "durable_side_effect": arm.durable_side_effect,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "outcome": "",
    }
    record["outcome"] = outcome_of(record)
    return record


def _reap(pid: int) -> int:
    """Wait for a spawned child and return ITS exit status, as a shell would."""
    try:
        _, status = os.waitpid(pid, 0)
    except (ChildProcessError, OSError):
        return 127
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return 128 + os.WTERMSIG(status) if os.WIFSIGNALED(status) else 127


# --------------------------------------------------------------------------
# The verdict, derived from the arm records rather than declared.
# --------------------------------------------------------------------------

VERDICT_NO_ARM_RAN = "no_arm_ran"
VERDICT_CONTROLS_FAILED = "controls_failed"
VERDICT_NO_RAISE_WORKS = "no_raise_works"
VERDICT_ONLY_EXEMPT = "only_the_exempt_responsible_identity_raises"
VERDICT_ALIEN_WORKS = "a_raise_works_from_an_alien_responsible_identity"
# An arm that never ran contributes this rather than a negative, per mechanism.
UNMEASURED = "unmeasured"


def verdict(arms: list[dict[str, Any]], *, base: dict[str, Any]) -> dict[str, Any]:
    """The verdict, computed from the arms committed beside it.

    Two properties this refuses to fudge. An arm that never ran contributes
    `null` rather than a negative, because "it did not move" and "nobody asked
    it to" are different answers and a composed verdict fails toward a confident
    green. And a file whose negative controls moved something is reported as
    `controls_failed` whatever its positives say: an instrument that moves a
    window when told to aim at nothing cannot vouch for the arms that were aimed
    at something.
    """
    per_arm: dict[str, Any] = {}
    for name in sorted({str(record["arm"]) for record in arms}):
        rows = [record for record in arms if record["arm"] == name]
        did_not_run = {OUTCOME_NOT_AUTHORIZED, OUTCOME_INCONCLUSIVE}
        ran = [row for row in rows if row["outcome"] not in did_not_run]
        moved = [row["moved"] for row in ran if row["moved"] is not None]
        per_arm[name] = {
            "invocations": len(rows),
            "expectation": rows[0]["expectation"],
            "issuer": rows[0]["issuer"],
            "ran": len(ran),
            "outcomes": sorted({str(row["outcome"]) for row in rows}),
            "why_not": sorted(
                {
                    str(row["precondition"]["why"])
                    for row in rows
                    if not row["precondition"]["satisfied"]
                }
            ),
            "moved": (any(moved) if moved else None),
            "reached_the_target": (
                any(
                    bool(row["frontmost"]["after_is_the_target"])
                    or bool(row["selected"]["after_is_the_target"])
                    for row in ran
                )
                if ran
                else None
            ),
            "exit_statuses": sorted(
                {
                    int(command["exit_status"])
                    for row in rows
                    for command in row["commands"]
                    if command["exit_status"] is not None
                }
            ),
            "responsible_names": sorted(
                {str(row["responsible"]["name"]) for row in rows if row["responsible"]["name"]}
            ),
            "responsible_is_self": sorted({bool(row["responsible"]["is_self"]) for row in rows}),
            "durable_side_effect": rows[0]["durable_side_effect"],
            "mechanism": rows[0].get("mechanism", []),
        }

    controls = [
        summary
        for summary in per_arm.values()
        if summary["expectation"] == EXPECT_HOLD and summary["ran"]
    ]
    controls_held = all(summary["moved"] is False for summary in controls) if controls else None

    positives = [
        (name, summary)
        for name, summary in per_arm.items()
        if summary["expectation"] == EXPECT_MOVE and summary["ran"] and summary["moved"]
    ]
    alien = [
        name
        for name, summary in positives
        if summary["issuer"] != ISSUER_RECORDER or summary["responsible_is_self"] == [True]
    ]

    # Two findings, not one. A socket raise steers a multiplexer over a UNIX
    # socket and macOS consults no responsible process for it, so such an arm
    # is silent about the Automation permission rather than reassuring about
    # it. Composing them into a single string is how the first version of this
    # function read five tmux arms and answered a question about TCC.
    def _ran_mechanism(name: str) -> list[tuple[str, dict[str, Any]]]:
        return [
            (arm_name, summary)
            for arm_name, summary in per_arm.items()
            if summary["ran"] and name in summary["mechanism"]
        ]

    def _finding(name: str) -> str:
        exercised = _ran_mechanism(name)
        # Only a must-move arm can answer this. A control that held still says
        # nothing about whether a raise works, because nobody asked it to move,
        # and a file of controls alone is unmeasured rather than negative. This
        # is the per-arm null rule applied to the mechanism, and it is the level
        # it was first missed on: a run whose pty clients failed to attach left
        # both socket must-move arms at `ran: 0`, and an earlier draft read the
        # two surviving controls as `does_not_work`.
        asked = [
            (arm_name, summary)
            for arm_name, summary in exercised
            if summary["expectation"] == EXPECT_MOVE
        ]
        if not asked:
            return UNMEASURED
        moved = [(arm_name, summary) for arm_name, summary in asked if summary["moved"]]
        if not moved:
            return "does_not_work"
        if name == MECHANISM_SOCKET:
            return "works"
        if any(arm_name in dict(alien_by_name) for arm_name, _ in moved):
            return "works_from_an_alien_responsible_identity"
        return "only_from_the_exempt_responsible_identity"

    alien_by_name = [(name, per_arm[name]) for name in alien]
    socket_raise = _finding(MECHANISM_SOCKET)
    apple_event_raise = _finding(MECHANISM_APPLE_EVENT)

    if not any(summary["ran"] for summary in per_arm.values()):
        answer = VERDICT_NO_ARM_RAN
    elif controls_held is False:
        answer = VERDICT_CONTROLS_FAILED
    else:
        answer = f"socket_raise={socket_raise} apple_event_raise={apple_event_raise}"
    return {
        **base,
        "record": RECORD_VERDICT,
        "invocations": len(arms),
        "arms": sorted(per_arm),
        "per_arm": per_arm,
        "controls_ran": len(controls),
        "controls_held": controls_held,
        "socket_raise": socket_raise,
        "apple_event_raise": apple_event_raise,
        "verdict": answer,
    }


# --------------------------------------------------------------------------
# A2's daemon half.
# --------------------------------------------------------------------------


def a2_daemon(handshake: str, target: str, out: str) -> None:
    """Double-fork past the launcher window, then raise once it is gone.

    Two readings of `responsibility_get_pid_responsible_for_pid` bracket the
    quit, because the whole arm is the difference between them. On this machine
    the first is Terminal even after the fork; whether the second still is, is
    the finding.
    """
    if os.fork() > 0:
        return
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    readers = Readers()
    pid = os.getpid()
    started = readers.responsible(pid)
    _write_json(handshake + ".ready", {"pid": pid, "responsible_name": readers.name_of(started)})
    deadline = time.time() + HANDSHAKE_TIMEOUT_SEC
    while time.time() < deadline and not os.path.exists(handshake + ".quit"):
        time.sleep(HANDSHAKE_POLL_SEC)
    after = readers.responsible(pid)
    before_state = readers.terminal_selected()
    code = _execute(["/usr/bin/osascript", "-e", raise_terminal_tab(target)], allowed=True)
    after_state = readers.terminal_selected()
    _write_json(
        handshake + ".done",
        {
            "responsible_before_quit_name": readers.name_of(started),
            "responsible_after_quit_name": readers.name_of(after),
            "responsible_after_quit_is_self": after == pid,
            "exit_status": code,
            "selected_before": before_state,
            "selected_after": after_state,
        },
    )
    del out
    os._exit(0)


def _write_json(path: str, payload: dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
    except OSError:
        return


# --------------------------------------------------------------------------
# Output.
# --------------------------------------------------------------------------


def dry_run(arms: Iterable[Arm] = ARMS) -> list[str]:
    """Exactly what each arm would run and what it would record. Runs nothing.

    Targets print as placeholders rather than as values, and that is the honest
    rendering: the security contract requires a target be resolved at the moment
    of the raise and never cached, so there is nothing to print until then.
    """
    lines: list[str] = [
        "capture_focus_raise --dry-run: NOTHING BELOW RUNS.",
        "",
        "Every arm is off until its own flag is passed. `_execute` is the single",
        "function in this module that starts an arm's process and it refuses",
        "without that flag. A2's window-quitting step carries a second flag.",
        "",
        "What every arm records, whether it runs or not:",
        "  " + ", ".join(sorted(ARM_KEYS)),
        "",
        "  precondition:  " + ", ".join(PRECONDITION_KEYS),
        "  commands[]:    argv, purpose, ran, exit_status, requires_flag, output_discarded",
        "  frontmost:     before, after, changed, after_is_the_target",
        "  selected:      source, before, after, changed, after_is_the_target,",
        "                 other_client_before, other_client_after, other_client_changed",
        "  responsible:   issuer_is_this_recorder, issuer_kind, name, is_self,",
        "                 after_launcher_quit_name, after_launcher_quit_is_self",
        "  issuer_terminal: tty, dev_tty_open, fd0, in_a_tmux_pane",
        "",
        "An arm whose target is already the current state runs NOTHING and records",
        "`inconclusive`: `resolve` picks a target that differs from the before-state",
        "and reports `satisfied=false` when it cannot, and `run_arm` starts no",
        "process unless that is true.",
        "",
    ]
    for arm in arms:
        lines += [
            f"=== {arm.id}  [{arm.expectation}]  issued by {arm.issuer}",
            f"    {arm.what}",
            f"    flag          {flag_for(arm.id)}   (NOT PASSED)",
            f"    selected read {arm.source}",
            f"    target app    {arm.target_app or '-'}",
            f"    needs         {', '.join(arm.needs) or '-'}",
            f"    leaves behind {arm.durable_side_effect or '-'}",
            f"    note          {arm.note}",
            "    would run:",
        ]
        steps = plan(arm, Targets(), out=PLACEHOLDER["out"])
        if not steps:
            lines.append("      (nothing)")
        for index, step in enumerate(steps, start=1):
            gate = f"  [needs {step['requires_flag']}]" if step.get("requires_flag") else ""
            spawn = f"  [{step['spawned']}]" if step.get("spawned") else ""
            wait = f"  [waits for {step['waits_for']}]" if step.get("waits_for") else ""
            lines.append(f"      {index}. {step['purpose']}{gate}{spawn}{wait}")
            lines.append(f"         {json.dumps(step['argv'])}")
        lines.append("")
    return lines


def report(records: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for record in records:
        if record["record"] == RECORD_NOTE:
            lines.append(f"{record['record']} {record['note']}")
        elif record["record"] == RECORD_ARM:
            lines += [
                (
                    f"{record['arm']} {record['outcome']} "
                    f"authorized={record['authorized']} moved={record['moved']} "
                    f"why={record['precondition']['why']}"
                ),
                # The evidence the outcome is derived from, beside the label.
                # `--report` printing a label and hiding its numbers is how a
                # reader was left unable to check the sibling's derivation.
                "  " + json.dumps(record["frontmost"], sort_keys=True),
                "  " + json.dumps(record["selected"], sort_keys=True),
                "  " + json.dumps(record["responsible"], sort_keys=True),
                "  "
                + json.dumps(
                    [
                        {"argv": c["argv"][:2], "ran": c["ran"], "exit_status": c["exit_status"]}
                        for c in record["commands"]
                    ],
                    sort_keys=True,
                ),
            ]
        else:
            lines.append(record["record"])
            lines.append(json.dumps(record["per_arm"], indent=2, sort_keys=True))
            lines.append(f"controls_held={record['controls_held']} verdict={record['verdict']}")
    return lines


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="record whether a raise works")
    parser.add_argument("--arm", default="", choices=("", *sorted(ARMS_BY_ID)))
    parser.add_argument("--out", default="")
    parser.add_argument("--socket", default=TMUX_SOCKET, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verdict", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--note", default="")
    for arm in ARMS:
        parser.add_argument(
            flag_for(arm.id),
            dest=f"allow_{arm.id}",
            action="store_true",
            help=f"authorize {arm.id}; without it {arm.id} runs nothing",
        )
    parser.add_argument(A2_QUIT_FLAG, dest="allow_a2_quit_window", action="store_true")
    parser.add_argument("--a2-daemon", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--a2-handshake", default="", help=argparse.SUPPRESS)
    parser.add_argument("--a2-target", default="", help=argparse.SUPPRESS)
    return parser


def authorized(arm_id: str, args: argparse.Namespace) -> bool:
    """Whether this arm's own flag was passed. The only thing that lets it run."""
    return bool(getattr(args, f"allow_{arm_id}", False))


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0911, PLR0912
    args = build_parser().parse_args(argv)

    if args.a2_daemon:
        a2_daemon(args.a2_handshake, args.a2_target, args.out)
        return 0
    if args.dry_run:
        for line in dry_run():
            print(line)
        return 0
    if args.report:
        for line in report(identity.read_records(args.report)):
            print(line)
        return 0
    if args.verdict:
        records = identity.read_records(args.verdict)
        arms = [record for record in records if record["record"] == RECORD_ARM]
        if not arms:
            print("no arms to derive a verdict from", file=sys.stderr)
            return 1
        derived = verdict(arms, base=base_of(arms[0]))
        committed = [record for record in records if record["record"] == RECORD_VERDICT]
        if committed:
            # Re-running over a committed file is how a reader checks the
            # derivation, and appending blindly is how the sibling turned that
            # check into a second verdict line and a red suite.
            if committed == [derived]:
                print(f"verdict reproduced from {len(arms)} arms in {args.verdict}")
                return 0
            print(f"verdict DIFFERS from the record in {args.verdict}", file=sys.stderr)
            return 1
        identity.append(args.verdict, derived)
        print(f"appended the verdict to {args.verdict}")
        return 0
    if args.note:
        if not args.out:
            print("--note needs --out", file=sys.stderr)
            return 2
        identity.append(
            args.out,
            {
                "format": FORMAT,
                "record": RECORD_NOTE,
                "os": platform.system().lower(),
                "at": identity.stamp(),
                "note": args.note,
            },
        )
        return 0
    if not args.arm:
        print("--arm is required (or --dry-run, --verdict, --report)", file=sys.stderr)
        return 2
    if not args.out:
        print("--out is required when capturing", file=sys.stderr)
        return 2
    arm = ARMS_BY_ID[args.arm]
    if not authorized(arm.id, args):
        # Loud, and nothing is written. This recorder is not a hook, so there is
        # no harness reading a non-zero code as a block.
        print(
            f"{arm.id} was not authorized: pass {flag_for(arm.id)} to run it. Nothing ran.",
            file=sys.stderr,
        )
        return 3
    extra = frozenset({A2_QUIT_FLAG}) if args.allow_a2_quit_window else frozenset()
    identity.append(
        args.out,
        run_arm(arm, allowed=True, socket=args.socket, out=args.out, extra_flags=extra),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
