#!/usr/bin/env python3
"""Record what terminal identity a hook can see, as shape only.

B5 (DRC-4017) wants one click in the dashboard to raise the terminal a waiting
session is sitting in. Nothing Cargento collects today can locate one:
`events.py`'s `ALLOWED_FIELDS` is nine fields with no pid, no tty and no terminal
identity, and no collector reads one. But a hook runs as a CHILD of the harness
process, so it can see things the store never records. This measures exactly
what, on the two harnesses that matter for that button.

Three modes, with the harness named first on the record path exactly as
`capture_hook.py` takes it:

    capture_terminal_identity.py claude --arm tmux --out FILE
                                    read a hook payload on stdin, append a line
    --verdict FILE                  derive the verdict from the arms in FILE.
                                    Appends it the first time; on a file that
                                    already carries one it COMPARES and says so,
                                    which is how a reader checks the derivation
    --report FILE                   print the arms and the verdict

## What it records, and what it refuses to

Shapes, presence, depths, roles, and one vendor vocabulary word. A tty device
names one terminal on one machine, so `ttys006` is written down as `ttys###`.
Every hex character of a value that contains a digit ANYWHERE is masked, and so
is any run of four or more characters that is nothing but hex. Both rules are
needed and the second was learned the hard way: a UUID splits on its hyphens, so
a group with no digit in it -- `FAEB` -- was written down verbatim, and four
characters of a real session id reached a committed capture.

The one value kept whole is `TERM_PROGRAM`. It is a vendor vocabulary word the
emulator picks from rather than text anyone wrote, which is the class
`docs/captures/README.md` already admits for `tool` and `notification_type`, and
it is the field that says which emulator a raise would have to talk to.

An ancestor is recorded by its accounting name (`ps -o ucomm=`) and a role from a
closed set. Never by `ps -o comm=`, which is a PATH truncated to sixteen
characters and whose basename can be a username; the path is read to decide the
role and is then dropped. Never by its arguments, which are a command line.

No prompt, no cwd, no transcript path, no session id past the eight characters
the collectors key on, no tmux socket path -- that one names a user's temp
directory.

## Why the control matters more than the positives

A harness started in its own session has no controlling terminal, but its ppid
chain still climbs into whatever launched it. A reader that took the first
ancestor with a tty would get a terminal belonging to somebody else and report it
confidently. So the record carries `harness_tty` and
`first_ancestor_with_a_tty_depth` as separate fields, and the verdict is computed
per arm across an arm that should answer differently.

## Why it cannot disturb a session, or the machine it runs on

The record path exits 0 whatever happens, including on a mistyped flag: argparse
exits 2 there, 2 is a harness's BLOCKING code for a hook, and a recorder that
blocks the session it is measuring is worse than one that records nothing. Only
`--verdict` and `--report`, which are run by hand rather than by a harness,
return a code that means something. It appends a single line, imports nothing
outside the standard library, and makes NO network call of any kind -- there is a
running dashboard on the machine this was measured on, and a recorder that posted
to it would contaminate the thing being measured. `scripts/tests/` holds it to
that.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

FORMAT = 1
RECORD_ARM = "terminal_identity"
RECORD_VERDICT = "terminal_identity_verdict"
# One line of arrangement the records themselves cannot carry, on the
# `_provenance` precedent the rest of `docs/captures/` already sets.
RECORD_NOTE = "terminal_identity_note"

# Long enough for the vocabulary words emulators actually use, short enough that
# nothing else fits. `capture_hook.py` bounds its tool name for the same reason.
MAX_TOKEN_CHARS = 40
# The chain from a hook to launchd is five or six links. Twelve leaves room for a
# wrapper without letting a cycle run forever.
MAX_DEPTH = 12
# A run of nothing but hex is an identifier even with no digit in it. Four,
# because every group of a UUID is at least four hex characters, and a shorter
# all-hex run is likelier to be a name than an id -- `bash` and `tmux` are not
# all-hex at any length, but a three-letter word can be.
MIN_HEX_RUN = 4
PS_TIMEOUT_SEC = 10

EMULATOR_VARS: tuple[str, ...] = (
    "TERM_PROGRAM",
    "TERM_SESSION_ID",
    "ITERM_SESSION_ID",
    "WT_SESSION",
    "WINDOWID",
    "KITTY_WINDOW_ID",
    "WEZTERM_PANE",
    "VSCODE_INJECTION",
)
MULTIPLEXER_VARS: tuple[str, ...] = ("TMUX", "TMUX_PANE")

# Executable basenames, matched against `ps -o comm=` and never recorded. The
# harness entry is keyed by the argument this script is given, for the reason
# `capture_hook.py` takes one: two harnesses send the same field names.
HARNESS_EXECUTABLES: dict[str, frozenset[str]] = {
    "claude": frozenset({"claude", "node", "bun"}),
    "codex": frozenset({"codex", "codex-exec", "codex-responses-api-proxy"}),
}
MULTIPLEXER_EXECUTABLES = frozenset({"tmux", "screen", "zellij"})
SHELL_EXECUTABLES = frozenset({"bash", "zsh", "sh", "fish", "dash", "ksh", "tcsh", "csh"})
# Matched against `ps -o ucomm=`, because a GUI application's `comm` is a bundle
# path and sixteen characters do not reach the executable inside it.
EMULATOR_NAMES = frozenset(
    {
        "Terminal",
        "iTerm2",
        "kitty",
        "wezterm-gui",
        "alacritty",
        "ghostty",
        "WarpTerminal",
        "Hyper",
        "Code",
        "Electron",
    }
)

SESSION_KEYS = ("session_id", "sessionId")
EVENT_KEYS = ("hook_event_name", "hookEventName", "event", "eventName")
# Never read, under any spelling. Listed so the refusal is auditable rather than
# implied by the absence of code, exactly as `capture_hook.py` lists its own.
NEVER_RECORD = ("prompt", "message", "cwd", "transcript_path", "transcriptPath", "tool_input")

BASE_KEYS: tuple[str, ...] = ("format", "record", "harness", "harness_version", "os", "at")
ARM_KEYS = frozenset(
    {
        "format",
        "record",
        "harness",
        "harness_version",
        "os",
        "at",
        "arm",
        "mode",
        "session",
        "event",
        "hook_ms",
        "tty",
        "ancestry",
        "multiplexer",
        "emulator",
        "emulator_lookup",
    }
)
VERDICT_KEYS = frozenset({*BASE_KEYS, "invocations", "arms", "per_arm", "verdict"})
# Every field name either record writes below the top level. The oracle over the
# committed files walks keys as well as values, so the schema has to be declared
# somewhere a reader can check it against the code.
RECORD_FIELD_NAMES = frozenset(
    {
        *ARM_KEYS,
        *VERDICT_KEYS,
        "present",
        "shape",
        "vars",
        "TERM_PROGRAM_value",
        "hook_fd0",
        "hook_fd1",
        "hook_fd2",
        "hook_dev_tty_open",
        "hook_ps_tty",
        "harness_tty",
        "harness_tty_agrees_with_hook_ps_tty",
        "harness_tty_agrees_with_hook_fd0_tty",
        "chain",
        "depth",
        "name",
        "role",
        "chain_length",
        "reached_harness",
        "depth_to_harness",
        "reached_multiplexer",
        "depth_to_multiplexer",
        "reached_emulator",
        "depth_to_emulator",
        "first_ancestor_with_a_tty_depth",
        "a_terminal_is_reachable_past_the_harness",
        "tmux_client_tty",
        "tmux_pane_tty",
        "pane_tty_is_the_client_tty",
        "method",
        "tabs_matching_harness_tty",
        "tabs_matching_tmux_client_tty",
        "busy_tabs_matching_harness_tty",
        "busy_tabs_matching_tmux_client_tty",
        "sessions",
        "modes",
        "identifier_shape_held_still",
        "locates_a_terminal_by",
        "harness_tty_present",
        "hook_ps_tty_present",
        "tmux_client_tty_present",
        "tmux_pane_present",
        "term_program_present",
        "emulator_in_the_ancestry",
        "stability_sessions_with_two_or_more_invocations",
        "note",
        *EMULATOR_VARS,
        *MULTIPLEXER_VARS,
    }
)

# The identifiers a raise could be built on. Each one is read out of an arm
# record by this path, and the verdict says, per arm, whether its SHAPE held
# still. Not whether the device did: four of the five paths below point at a
# field `shape()` has already masked, and two `ttysNNN` devices share one shape,
# so a comparison made here cannot tell them apart. See `verdict()`.
IDENTIFIERS: dict[str, tuple[str, ...]] = {
    "hook_ps_tty": ("tty", "hook_ps_tty"),
    "harness_tty": ("tty", "harness_tty"),
    "TMUX_PANE": ("multiplexer", "TMUX_PANE", "shape"),
    "tmux_client_tty": ("multiplexer", "tmux_client_tty"),
    "TERM_PROGRAM": ("emulator", "TERM_PROGRAM_value"),
}

_RUN = re.compile(r"[0-9A-Za-z]+")
_HEXISH = re.compile(r"[0-9a-fA-F]")
_HEX_RUN = re.compile(r"[0-9a-fA-F]+")
# `ps` writes `??` for a process with no controlling terminal on macOS and `?` on
# Linux. Both are truthy, which is how one reached an AppleScript query.
_NO_DEVICE = frozenset({"", "?", "??"})


def _device_or_none(reading: str | None) -> str | None:
    """A `ps` tty reading, or None for the spellings that mean no device.

    The lookup took `??` straight through and asked Terminal.app about
    `/dev/??`, which answers 0 rather than failing -- an artifact 0 sitting in
    the same field of the same file as a measured one, with nothing to tell them
    apart. `shape()` cannot stand in for this: it masks digits, and the lookup
    needs the device.
    """
    if reading is None:
        return None
    return None if reading.strip() in _NO_DEVICE else reading


def shape(text: str | None) -> str | None:
    """A reading reduced to its shape: `/dev/ttys006` becomes `ttys###`.

    Two rules, and the second exists because the first leaked. Every hex
    character of a value that contains a digit ANYWHERE is masked, not just of
    the run the digit sits in: `_RUN` splits a UUID on its hyphens, so
    `7A3B9C1D-FAEB-...` made `FAEB` a run with no digit of its own and wrote four
    characters of a real `TERM_SESSION_ID` into a committed capture. And a run of
    nothing but hex is an identifier even when the value carries no digit at all,
    so one of `MIN_HEX_RUN` characters or more is masked on its own account. A
    run holding a non-hex character is a name and survives.
    """
    if not text:
        return None
    value = text.strip()
    if _device_or_none(value) is None:
        return None
    value = value.removeprefix("/dev/")
    digit_anywhere = any(char.isdigit() for char in value)

    def mask(match: re.Match[str]) -> str:
        run = match.group(0)
        all_hex = len(run) >= MIN_HEX_RUN and _HEX_RUN.fullmatch(run) is not None
        if not digit_anywhere and not all_hex:
            return run
        return "".join("#" if _HEXISH.fullmatch(char) else char for char in run)

    return _RUN.sub(mask, value)[:MAX_TOKEN_CHARS]


def presence(environ: dict[str, str], name: str) -> dict[str, Any]:
    value = environ.get(name)
    if not value:
        return {"present": False, "shape": None}
    # `TMUX` is a socket path, a server pid and a session index. The path names a
    # user's temp directory, so this one is recorded as presence alone.
    if name == "TMUX":
        return {"present": True, "shape": None}
    return {"present": True, "shape": shape(value)}


def environment(environ: dict[str, str]) -> dict[str, Any]:
    """The multiplexer and emulator variables, as presence and shape."""
    term_program = environ.get("TERM_PROGRAM") or None
    return {
        "multiplexer": {name: presence(environ, name) for name in MULTIPLEXER_VARS},
        "emulator": {
            "vars": {name: presence(environ, name) for name in EMULATOR_VARS},
            # The one value kept whole: a vendor vocabulary word, bounded.
            "TERM_PROGRAM_value": term_program[:MAX_TOKEN_CHARS] if term_program else None,
        },
    }


# Role by executable, in precedence order. A multiplexer is checked before an
# emulator because a pane's chain carries both names at different depths, and a
# shell after both because `login` execs one.
_ROLES: tuple[tuple[str, frozenset[str]], ...] = (
    ("multiplexer", MULTIPLEXER_EXECUTABLES),
    ("emulator", EMULATOR_NAMES),
    ("shell", SHELL_EXECUTABLES),
    ("login", frozenset({"login"})),
    ("init", frozenset({"launchd", "init", "systemd"})),
)


def role_of(comm: str, ucomm: str, harness: str, *, depth: int) -> str:
    """An ancestor's role, from a closed set, decided on the executable.

    The path is read here and dropped: `ps -o comm=` is truncated to sixteen
    characters, so its basename can be the head of a home directory rather than a
    program. `ucomm` is not enough on its own -- this harness reports its own
    VERSION there -- and it is what a GUI application has instead of a reachable
    executable name, so both are consulted and neither is recorded raw.
    """
    if depth == 0:
        return "recorder"
    executable = os.path.basename(comm.strip())
    name = ucomm.strip()
    candidates = {executable, name, executable.lstrip("-"), name.lstrip("-")}
    if executable in HARNESS_EXECUTABLES.get(harness, frozenset()):
        return "harness"
    for role, members in _ROLES:
        if candidates & members:
            return role
    return "other"


def walk(processes: list[dict[str, Any]], *, harness: str) -> list[dict[str, Any]]:
    """The ppid chain from the hook process upward, as names, roles and shapes.

    `processes` is a list of `ps` readings, one per process. It is passed in
    rather than read here so the walk is testable against a chain that cannot be
    built on a machine -- the launcher-inherited terminal, above all.
    """
    by_pid = {int(row["pid"]): row for row in processes}
    chain: list[dict[str, Any]] = []
    seen: set[int] = set()
    pid = int(processes[0]["pid"]) if processes else 0
    for depth in range(MAX_DEPTH):
        row = by_pid.get(pid)
        if row is None or pid in seen:
            break
        seen.add(pid)
        chain.append(
            {
                "depth": depth,
                "name": shape(str(row.get("ucomm", ""))) or "other",
                "role": role_of(
                    str(row.get("comm", "")), str(row.get("ucomm", "")), harness, depth=depth
                ),
                "tty": shape(str(row.get("tty", ""))),
            }
        )
        parent = int(row.get("ppid", 0))
        if parent <= 0:
            break
        pid = parent
    return chain


def _first(chain: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    return next((entry for entry in chain if entry["role"] == role), None)


def ancestry(chain: list[dict[str, Any]]) -> dict[str, Any]:
    """What the chain reached, and at what depth."""
    harness = _first(chain, "harness")
    multiplexer = _first(chain, "multiplexer")
    emulator = _first(chain, "emulator")
    with_tty = next((entry for entry in chain if entry["tty"]), None)
    harness_depth = harness["depth"] if harness else None
    return {
        "chain": chain,
        "chain_length": len(chain),
        "reached_harness": harness is not None,
        "depth_to_harness": harness_depth,
        # The terminal of the harness ITSELF, which is not the same question as
        # the first terminal in the chain. See the flag at the bottom.
        "harness_tty": harness["tty"] if harness else None,
        "reached_multiplexer": multiplexer is not None,
        "depth_to_multiplexer": multiplexer["depth"] if multiplexer else None,
        "reached_emulator": emulator is not None,
        "depth_to_emulator": emulator["depth"] if emulator else None,
        "first_ancestor_with_a_tty_depth": with_tty["depth"] if with_tty else None,
        # The trap the control arm exists to show: a terminal found ABOVE the
        # harness belongs to whatever launched it, not to this session.
        "a_terminal_is_reachable_past_the_harness": bool(
            with_tty is not None
            and harness is not None
            and harness["tty"] is None
            and with_tty["depth"] > harness["depth"]
        ),
    }


def observe(
    *,
    payload: dict[str, Any],
    harness: str,
    arm: str,
    environ: dict[str, str],
    processes: list[dict[str, Any]],
    probe: dict[str, Any],
    elapsed_ms: float,
    harness_version: str,
    at: str,
    mode: str = "print",
    os_name: str = "",
) -> dict[str, Any]:
    """One capture line: what identity was visible, never what it was."""
    session = ""
    for key in SESSION_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate:
            session = candidate[:8]
            break
    event = ""
    for key in EVENT_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate:
            event = candidate[:MAX_TOKEN_CHARS]
            break
    chain = walk(processes, harness=harness)
    found = ancestry(chain)
    # The raw reading, kept only long enough to compare: `processes` is ordered
    # by depth, which is how `walk` builds the chain out of it.
    harness_depth = found["depth_to_harness"]
    harness_tty_raw = (
        str(processes[harness_depth].get("tty", ""))
        if harness_depth is not None and harness_depth < len(processes)
        else None
    )
    # Compared on the RAW readings. Two `ttysNNN` devices share a shape, so
    # agreement computed after masking would be true by construction.
    ps_tty_raw = probe.get("ps_tty")
    fd0_raw = (probe.get("fd_tty") or {}).get("0")

    def agrees(left: str | None, right: str | None) -> bool | None:
        if not shape(left) or not shape(right):
            return None
        return shape(left) is not None and _bare(left) == _bare(right)

    seen = environment(environ)
    pane_tty_raw = probe.get("tmux_pane_tty")
    client_tty_raw = probe.get("tmux_client_tty")
    multiplexer = dict(seen["multiplexer"])
    multiplexer["tmux_client_tty"] = shape(client_tty_raw)
    multiplexer["tmux_pane_tty"] = shape(pane_tty_raw)
    multiplexer["pane_tty_is_the_client_tty"] = agrees(pane_tty_raw, client_tty_raw)
    return {
        "format": FORMAT,
        "record": RECORD_ARM,
        "harness": harness,
        "harness_version": harness_version,
        "os": os_name or platform.system().lower(),
        "at": at,
        "arm": arm,
        "mode": mode,
        "session": session,
        "event": event,
        "hook_ms": round(elapsed_ms, 1),
        "tty": {
            "hook_fd0": shape((probe.get("fd_tty") or {}).get("0")),
            "hook_fd1": shape((probe.get("fd_tty") or {}).get("1")),
            "hook_fd2": shape((probe.get("fd_tty") or {}).get("2")),
            "hook_dev_tty_open": bool(probe.get("dev_tty_open")),
            "hook_ps_tty": shape(ps_tty_raw),
            "harness_tty": shape(harness_tty_raw),
            "harness_tty_agrees_with_hook_ps_tty": agrees(harness_tty_raw, ps_tty_raw),
            "harness_tty_agrees_with_hook_fd0_tty": agrees(harness_tty_raw, fd0_raw),
        },
        "ancestry": found,
        "multiplexer": multiplexer,
        "emulator": seen["emulator"],
        "emulator_lookup": probe.get("emulator_lookup")
        or lookup(harness_tty=None, client_tty=None),
    }


def _bare(device: str | None) -> str:
    return (device or "").strip().removeprefix("/dev/")


def base_of(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in BASE_KEYS}


def _dig(record: dict[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = record
    for step in path:
        if not isinstance(node, dict):
            return None
        node = node.get(step)
    return node


def _highest(rows: list[dict[str, Any]], field: str) -> int | None:
    """The largest count any invocation of an arm measured, or None if none did.

    The largest rather than the last: the lookup is a live reading and a tab
    busy at one invocation can be idle at the next, but a tab that was there
    was there.
    """
    seen = [_dig(row, ("emulator_lookup", field)) for row in rows]
    measured = [value for value in seen if isinstance(value, int)]
    return max(measured) if measured else None


def verdict(arms: list[dict[str, Any]], *, base: dict[str, Any]) -> dict[str, Any]:
    """The verdict, derived from the arm records rather than declared.

    Everything below comes out of the arms committed beside it. Re-running
    `--verdict` over a committed file COMPARES rather than appending, so the
    reproduction can be checked by hand without writing to the evidence.

    One property this deliberately does NOT claim: that a device held still. The
    identifiers are read after `shape()` has masked them, every `ttysNNN` device
    serializes to the same `ttys###`, and nothing in an arm record distinguishes
    two devices in one family once it is written. So a tmux client that moved
    from one tab to another inside a session -- a detach and a reattach, which
    `tmux_client_tty` is exactly the identifier to notice -- is invisible here.
    The field is named `identifier_shape_held_still` for what it measures, and
    `docs/captures/README.md` says the shapes agreed rather than that the device
    did. Carrying a salted digest instead was considered and rejected: a hook is
    a fresh process per invocation, so the salt would have to be written beside
    the digest or handed in undisclosed arrangement, and a salt in the file makes
    the digest reversible in milliseconds against a device space of a few hundred.
    """
    per_arm: dict[str, Any] = {}
    for name in sorted({str(record["arm"]) for record in arms}):
        rows = [record for record in arms if record["arm"] == name]
        sessions: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            sessions.setdefault(str(row.get("session") or ""), []).append(row)
        repeated = {sid: rows_ for sid, rows_ in sessions.items() if len(rows_) > 1}
        held: dict[str, bool | None] = {}
        for identifier, path in IDENTIFIERS.items():
            # An identifier absent from every reading compares equal to itself, so
            # a plain equality check would report the most useless field in the
            # file as the most reliable one. `null` is not `true`, and neither is
            # a single reading: one invocation cannot establish stability either.
            #
            # The presence check ranges over the SAME rows the comparison does,
            # not over every row of the arm. A session that never saw the
            # identifier contributes a one-element set of nulls and would read as
            # agreement -- and a sighting in a single-invocation session would
            # vouch for it. `docs/captures/README.md` names a detached pane as
            # unmeasured, so that is the next capture rather than a hypothetical.
            measured = {
                sid: rows_
                for sid, rows_ in repeated.items()
                if any(_dig(row, path) for row in rows_)
            }
            if not measured:
                held[identifier] = None
                continue
            held[identifier] = all(
                len({json.dumps(_dig(row, path)) for row in rows_}) == 1
                for rows_ in measured.values()
            )
        has_pane = any(_dig(row, ("multiplexer", "TMUX_PANE", "present")) for row in rows)
        # Taken from the lookup the arms already carry, not from whether an
        # identifier is present. In a pane the harness HAS a tty and ZERO
        # Terminal tabs sit on it, so a label read off presence named `tty` as a
        # locator on exactly the evidence that refutes it -- and an arm with a
        # live client tty but no tty of its own would have read `none`. The busy
        # count rather than the total, because macOS recycles the device and a
        # finished tab keeps the string.
        busy_harness = _highest(rows, "busy_tabs_matching_harness_tty")
        busy_client = _highest(rows, "busy_tabs_matching_tmux_client_tty")
        routes = []
        if busy_harness:
            routes.append("tty")
        if busy_client:
            routes.append("tmux_client_tty")
        if routes and has_pane:
            routes.append("tmux_pane")
        locates = "+".join(routes) if routes else "none"
        per_arm[name] = {
            "invocations": len(rows),
            "sessions": len(sessions),
            "modes": sorted({str(row.get("mode") or "") for row in rows}),
            "stability_sessions_with_two_or_more_invocations": len(repeated),
            "harness_tty_present": any(_dig(row, ("tty", "harness_tty")) for row in rows),
            "hook_ps_tty_present": any(_dig(row, ("tty", "hook_ps_tty")) for row in rows),
            # The identifier that actually finds the window in a pane had no
            # presence column beside the three that do not.
            "tmux_client_tty_present": any(
                _dig(row, ("multiplexer", "tmux_client_tty")) for row in rows
            ),
            "tmux_pane_present": has_pane,
            "term_program_present": any(
                _dig(row, ("emulator", "TERM_PROGRAM_value")) for row in rows
            ),
            "emulator_in_the_ancestry": any(
                _dig(row, ("ancestry", "reached_emulator")) for row in rows
            ),
            "identifier_shape_held_still": held,
            # The counts this is derived from are deliberately not copied up
            # beside it: the control arm's is an artifact 0 from a query against
            # a device that did not exist, and a summary is the last place to
            # repeat one. `--report` prints each arm's own `emulator_lookup`.
            "locates_a_terminal_by": locates,
            # Carried up from the arms because it is the control's whole finding:
            # "no terminal" understates what a naive reader would do here.
            "a_terminal_is_reachable_past_the_harness": any(
                _dig(row, ("ancestry", "a_terminal_is_reachable_past_the_harness")) for row in rows
            ),
        }
    positive = sorted(a for a, found in per_arm.items() if found["locates_a_terminal_by"] != "none")
    return {
        **base,
        "record": RECORD_VERDICT,
        "invocations": len(arms),
        "arms": sorted(per_arm),
        "per_arm": per_arm,
        # A one-word answer to B5's question, from a closed set, so a reader does
        # not have to infer it from the table above.
        "verdict": "a_terminal_is_locatable" if positive else "no_terminal_is_locatable",
    }


def ps_rows(pid: int) -> list[dict[str, Any]]:
    """The ppid chain as `ps` readings, oldest call first, hook process at index 0."""
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for _ in range(MAX_DEPTH):
        if pid <= 0 or pid in seen:
            break
        seen.add(pid)
        try:
            done = subprocess.run(  # noqa: S603
                # Resolved on PATH by design: this asks the machine about itself.
                ["ps", "-o", "ppid=,ucomm=,comm=,tty=", "-p", str(pid)],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=PS_TIMEOUT_SEC,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            break
        line = done.stdout.strip()
        if not line:
            break
        parts = line.split()
        if len(parts) < 4:
            break
        ppid, ucomm, comm, tty = parts[0], parts[1], parts[-2], parts[-1]
        rows.append({"pid": pid, "ppid": int(ppid), "ucomm": ucomm, "comm": comm, "tty": tty})
        pid = int(ppid)
    return rows


def _fd_tty(fd: int) -> str | None:
    try:
        return os.ttyname(fd)
    # `os.ttyname` does not exist on Windows, and its absence is an absent
    # reading rather than a fault. Without `AttributeError` here the whole
    # recorder died before writing anything and still exited 0.
    except (AttributeError, OSError, ValueError):
        return None


def _dev_tty_open() -> bool:
    try:
        handle = os.open("/dev/tty", os.O_RDONLY)
    except OSError:
        return False
    os.close(handle)
    return True


def _tmux(fmt: str) -> str | None:
    if not os.environ.get("TMUX"):
        return None
    try:
        done = subprocess.run(  # noqa: S603
            ["tmux", "display-message", "-p", fmt],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def tab_query(device: str) -> str:
    """The AppleScript that counts open Terminal.app tabs sitting on a device.

    Returns two numbers: how many tabs carry the device, and how many of those
    are busy. Three things here were measured rather than reasoned about, and
    each had already produced a wrong number.

    The `/dev/` prefix is not decoration: Terminal.app reports `tty` as the full
    device path, and the same query against the bare name answers 0 rather than
    failing, which is a clean and wrong negative. The count is taken per TAB: the
    shorter `every tab of every window whose tty is X` binds the filter to the
    window and then counts every tab in it, which answered 2 for a device exactly
    one tab sits on. And the busy count is separate because macOS RECYCLES the
    device -- two finished tabs on this machine both still reported
    `/dev/ttys004` while a live session held it, so a total alone says a tty
    names one window when it names three.
    """
    quoted = _bare(device).replace('"', "")
    return "\n".join(
        (
            'tell application "Terminal"',
            "set n to 0",
            "set b to 0",
            "repeat with w in windows",
            "repeat with t in tabs of w",
            f'if tty of t is "/dev/{quoted}" then',
            "set n to n + 1",
            "if busy of t then set b to b + 1",
            "end if",
            "end repeat",
            "end repeat",
            'return (n as text) & "," & (b as text)',
            "end tell",
        )
    )


def _terminal_tabs(device: str | None) -> dict[str, int] | None:
    """Tabs on that device, total and busy, or None if the question is unaskable."""
    asked = _device_or_none(device)
    if asked is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603
            ["osascript", "-e", tab_query(asked)],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    parts = done.stdout.strip().split(",")
    if done.returncode != 0 or len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return {"tabs": int(parts[0]), "busy_tabs": int(parts[1])}


def lookup(
    *,
    harness_tty: str | None,
    client_tty: str | None,
    count: Callable[[str | None], dict[str, int] | None] = _terminal_tabs,
) -> dict[str, Any]:
    """Whether either candidate device names a window that could be raised.

    Two devices rather than one, because in a pane the harness's tty is a pty
    tmux made and no Terminal tab sits on it. Asking only that one would report a
    flat negative for an arm where the multiplexer's own client tty still finds
    the window. Read-only, and it is the difference between holding a string and
    holding a handle: an identifier nothing can look up would not build B5.
    """
    # `_device_or_none` rather than truthiness: `ps` writes `??` for a process
    # with no controlling terminal, `??` is truthy, and one went straight into an
    # AppleScript query against `/dev/??` -- which Terminal.app answers 0 rather
    # than refusing. That put an artifact 0 in the control arm's tab counts, in
    # the same field of the same corpus as the tmux arms' measured 0.
    harness = count(harness_tty) if _device_or_none(harness_tty) else None
    client = count(client_tty) if _device_or_none(client_tty) else None
    return {
        "method": "terminal_app_applescript_tty",
        "tabs_matching_harness_tty": harness["tabs"] if harness else None,
        "busy_tabs_matching_harness_tty": harness["busy_tabs"] if harness else None,
        "tabs_matching_tmux_client_tty": client["tabs"] if client else None,
        "busy_tabs_matching_tmux_client_tty": client["busy_tabs"] if client else None,
    }


def harness_version(harness: str) -> str:
    try:
        done = subprocess.run(  # noqa: S603
            # Resolved on PATH: the recorder asks the harness which build it is.
            [harness, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    found = re.search(r"\d+\.\d+\.\d+", done.stdout)
    return found.group(0) if found else ""


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append(path: str, record: dict[str, Any]) -> None:
    try:
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        # Unwritable: give up silently, exactly as `notify_hook.py` does. A hook
        # that fails is felt by the human in the session.
        pass


def read_records(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def capture(argv: argparse.Namespace) -> None:
    started = time.perf_counter()
    raw = ""
    try:
        raw = sys.stdin.read(1_000_000)
    except (OSError, ValueError):
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    for banned in NEVER_RECORD:
        payload.pop(banned, None)
    processes = ps_rows(os.getpid())
    harness_row = next(
        (
            row
            for index, row in enumerate(processes)
            if role_of(str(row["comm"]), str(row["ucomm"]), argv.harness, depth=index) == "harness"
        ),
        None,
    )
    probe = {
        "fd_tty": {str(fd): _fd_tty(fd) for fd in (0, 1, 2)},
        "ps_tty": next((str(row["tty"]) for row in processes[:1]), None),
        "dev_tty_open": _dev_tty_open(),
        "tmux_client_tty": _tmux("#{client_tty}"),
        "tmux_pane_tty": _tmux("#{pane_tty}"),
        "emulator_lookup": lookup(
            harness_tty=str(harness_row["tty"]) if harness_row else None,
            client_tty=_tmux("#{client_tty}"),
        ),
    }
    record = observe(
        payload=payload,
        harness=argv.harness,
        arm=argv.arm,
        environ=dict(os.environ),
        processes=processes,
        probe=probe,
        elapsed_ms=(time.perf_counter() - started) * 1000,
        harness_version=argv.harness_version or harness_version(argv.harness),
        at=stamp(),
        mode=argv.mode,
    )
    append(argv.out, record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("harness", nargs="?", default="claude", choices=sorted(HARNESS_EXECUTABLES))
    parser.add_argument("--arm", default="")
    parser.add_argument("--mode", default="print", choices=("print", "interactive"))
    parser.add_argument("--out", default="")
    parser.add_argument("--harness-version", default="")
    parser.add_argument("--verdict", default="", help="derive the verdict from a capture file")
    parser.add_argument("--report", default="", help="print a capture file")
    args = parser.parse_args(argv)

    if args.report:
        for record in read_records(args.report):
            if record["record"] == RECORD_NOTE:
                print(record["record"], record["note"])
            elif record["record"] == RECORD_ARM:
                # `emulator_lookup` beside `tty`, because this is the documented
                # reading path and the label the verdict prints is derived from
                # these numbers. Printing the label and hiding them is how a
                # reader was left unable to check it.
                print(
                    record["arm"],
                    record["event"],
                    json.dumps(record["tty"], sort_keys=True),
                    json.dumps(record["emulator_lookup"], sort_keys=True),
                )
            else:
                print(record["record"], json.dumps(record["per_arm"], indent=2, sort_keys=True))
        return 0
    if args.verdict:
        records = read_records(args.verdict)
        arms = [record for record in records if record["record"] == RECORD_ARM]
        if not arms:
            print("no arms to derive a verdict from", file=sys.stderr)
            return 0
        derived = verdict(arms, base=base_of(arms[0]))
        committed = [record for record in records if record["record"] == RECORD_VERDICT]
        if committed:
            # Re-running this over a committed file is how a reader checks the
            # derivation by hand, and appending blindly turned that into a
            # second verdict line and a red suite. `capture_team_registry.py`
            # refuses its own re-run for the same reason: by hand is exactly
            # when it happens.
            if committed == [derived]:
                print(f"verdict reproduced from {len(arms)} arms in {args.verdict}")
                return 0
            print(f"verdict DIFFERS from the record in {args.verdict}", file=sys.stderr)
            return 1
        append(args.verdict, derived)
        print(f"appended the verdict to {args.verdict}")
        return 0
    if not args.out or not args.arm:
        parser.error("--out and --arm are required when capturing")
    capture(args)
    return 0


# Run by hand rather than by a harness, so their exit code is an answer and is
# passed through. Everything else is the record path.
BY_HAND = frozenset({"--verdict", "--report", "--help", "-h"})


def exit_code(argv: list[str] | None = None) -> int:
    """`main()`'s code, with the record path unable to block the session it measures."""
    given = sys.argv[1:] if argv is None else argv
    by_hand = any(arg.split("=", 1)[0] in BY_HAND for arg in given)
    try:
        return main(argv)
    except SystemExit as chosen:
        # argparse exits 2 on a mistyped flag, an unknown `--mode`, or a missing
        # `--arm`, and 2 is a harness's BLOCKING code for a hook. `SystemExit`
        # derives from `BaseException`, so the handler below never saw it and the
        # 2 reached the harness. A recorder that blocks a session is worse than
        # one that records nothing.
        if by_hand and isinstance(chosen.code, int):
            return chosen.code
        return 0
    except Exception:
        # A hook that raises is felt by the human in the session, so the record
        # path swallows everything. Not by hand, though: an unreadable file is
        # the operator's likeliest mistake and a silent 0 would hide it.
        if by_hand:
            raise
        return 0


if __name__ == "__main__":
    sys.exit(exit_code())
