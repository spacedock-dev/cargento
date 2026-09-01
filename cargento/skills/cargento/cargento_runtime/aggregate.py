"""Harness registry, per-harness failure boundary, collection, and the application."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Protocol, TypeAlias

from . import dismissals, notifications, quota, records, sessions
from . import events as runtime_events
from . import io as runtime_io
from . import snapshot as runtime_snapshot

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .config import RuntimeConfig
    from .events import Overlay
    from .git_status import GitStatus
    from .sessions import Session
    from .state import RuntimeState


_STATE_RANK: Final = {"needs_input": 0, "working": 1, "idle": 2}


def row_order(session: Session) -> tuple[int, float, str]:
    """Where a row sits in the published payload: state, then wait, then id.

    Session id as the last tiebreaker (not last_activity) so rows don't reshuffle
    on every refresh while sessions are generating.

    The middle key is the gate queue: blocked rows arrive longest-blocked first,
    because session id is an arbitrary order to be stopped in and the gate that
    has held someone up longest is the one still costing something. It ranks on
    the timestamp rather than on the elapsed wait so that the order cannot churn
    as every row in it waits longer.

    `last_activity` stands in where a wait carries no `blocked_since`: only the
    Claude, Copilot and Cursor collectors and the event overlays set that field,
    and a harness without it must still take a place in the queue rather than
    sorting to the front on a zero.
    """
    wait = 0.0
    if session["state"] == "needs_input":
        wait = float(session.get("blocked_since") or session.get("last_activity") or 0)
    return (_STATE_RANK.get(session["state"], 3), wait, str(session["sid"]))


def _keep_wait_detail(session: Session, patch: Mapping[str, Any]) -> Mapping[str, Any]:
    """The patch, minus a `state_detail` that would blank a standing wait.

    No overlay constructor sets `detail`, so every needs-input patch carries
    None, and applying it erased whatever the collector had found. For a Claude
    row that is the open question itself, which is the one thing a person
    stopped at a gate wants to read.

    Narrow on purpose. It applies only when the row was already Needs input and
    stays Needs input, because the overlay is then agreeing about the state and
    disagreeing about nothing. Working and Idle must keep clearing the field, or
    a working detail such as `running Bash` follows the row into a wait, and a
    question that has been answered outlives the overlay that retired it.
    """
    if session.get("state") != "needs_input" or patch.get("state") != "needs_input":
        return patch
    if patch.get("state_detail") is not None or not session.get("state_detail"):
        return patch
    return {key: value for key, value in patch.items() if key != "state_detail"}


def _wait_popup_body(session: Session) -> str:
    """The popup body for a gated row: its project, and what it is waiting on.

    `notify.js` composes the same two fields with the same fallback, and the two
    must agree because either layer may be the one that delivers a given gate.
    The fallback is not decoration: no overlay constructor sets `detail`, so
    every needs-input patch from the event lane carries None, and that lane is
    the whole of how a Codex gate is detected. Composing here also means
    `maybe_popup`'s own default can never fire — an f-string is truthy — so the
    empty case has to be answered before the call.
    """
    return f"[{session.get('project')}] {session.get('state_detail') or 'needs your input'}"


def _subtract_dismissed(
    out_sessions: list[Session],
    cleared_marks: tuple[dismissals.Dismissal, ...],
) -> tuple[list[Session], int]:
    """The rows no standing dismissal covers, and how many it removed.

    Called after the overlays and before the display ids, and both halves
    matter. After, because `_apply_overlays` ends in `note_rows`, which expires
    any overlay whose key was not reported — subtract first and a dismissed
    session that comes back has lost its pending permission overlay. Before
    `assign_display_ids`, so the id widths describe the rows actually on screen.

    A count and not a filtered flag, because a dismissal silences an alert
    through `maybe_popup`'s own gate rather than by hiding the row from it (D-3
    in docs/design-dismissals.md).
    """
    kept = [
        session
        for session in out_sessions
        if not dismissals.holds(
            cleared_marks,
            str(session["harness"]),
            str(session["sid"]),
            float(session.get("last_activity") or 0.0),
        )
    ]
    return kept, len(out_sessions) - len(kept)


class OverlaySource(Protocol):
    """The narrow view of the coordinator that a collection needs.

    The first two run the traffic both ways. A collection reads the overlays for
    each row it produced, and then reports back which rows exist at all, which is
    how an overlay for a session no collection has yet seen resolves or expires.
    Stated as a Protocol so `aggregate` stays below `observation` and the
    dependency does not invert.

    `drop_counters` is neither: it is read only when a dispute is recorded, and
    it is here because an envelope that arrived and was dropped leaves no overlay
    to find. Without it a record cannot separate that from one never posted,
    which is two of the four readings in docs/design-needs-input.md (N-5).

    `finished_at` is separate from `overlays_for` because it deliberately
    outlives the ledger: `session_ended` retires a session's overlays, and a
    `claude -p` run that finished and exited is exactly the row the mark is for.
    """

    def overlays_for(self, harness: str, sid: str) -> list[Overlay]: ...

    def finished_at(self, harness: str, sid: str) -> float: ...

    def git_for(self, harness: str, sid: str) -> GitStatus | None: ...

    def note_rows(self, keys: set[tuple[str, str]]) -> None: ...

    def drop_counters(self) -> dict[str, int]: ...


Collection: TypeAlias = dict[str, Any]
Discoverer: TypeAlias = Callable[["RuntimeConfig", "RuntimeState"], bool]
Collector: TypeAlias = Callable[
    ["RuntimeConfig", "RuntimeState", float, float, bool],
    "list[Session]",
]
UsageProvider: TypeAlias = Callable[
    ["RuntimeConfig", "RuntimeState", float, float],
    "list[dict[str, Any]]",
]


@dataclass(frozen=True)
class HarnessSpec:
    """One supported harness: how to discover its store and how to read it.

    ``usage`` is the optional quota reader. Most harnesses have none: the
    survey behind DEC-1 found Codex alone writing quota to disk, and every
    other vendor keeping it behind an authenticated API. The field is where
    a quota source plugs in without widening the ``Collector`` contract.

    ``usage_is_fetch`` marks a provider whose numbers come from the network
    fetcher rather than from disk. Its presence on a discovered harness is
    what raises the payload's ``usage_fetch`` capability flag, and that flag
    is what wakes the page's first-run disclosure banner — a disk reader like
    Codex's must never raise it.

    ``reports_rate`` says whether this harness's collector can populate
    ``rate_per_min`` at all. Four of the ten cannot: OpenCode, Cursor and Droid
    read no token accounting, and Copilot's store carries only quota receipts.
    Those rows publish null, while a reporting harness sends 0 for a session
    that generated nothing in the window. Declaring the capability here keeps
    collector defaults numeric while the application can still make the wire
    value honest and consumers can rank a real zero.

    ``reports_needs_input`` is the same shape on the field where getting it
    wrong costs more. Six of the ten cannot observe a gate at all, and their
    silence is byte-identical to the silence of one that can when nothing is
    waiting: no row, no count, no band. So a quiet board cannot say whether
    nothing is waiting or nothing could have told you, and B2's own note is that
    a reader assumes the former because everything else here is harness-agnostic.
    A `reports_rate` false row renders a dash; this one has nothing to draw a
    dash on, which is why the disclosure has to be per harness rather than per
    row.

    It answers "can a gate on this harness reach the board", by ANY path -- not
    "can this collector detect one". The distinction is the whole of what the
    first review of this field caught: Codex reports a gate through the event
    overlay and has no collector detection at all, so a flag meaning the second
    thing labelled Codex blind on the same screen where a Codex gate was red.
    That is the inversion this field exists to prevent, shipped by the field
    itself. `tests/test_next_page.py` derives the expected set instead of listing it:
    every collector module is parsed for the state it actually writes, unioned
    with whatever `EVENTS_BY_HARNESS` maps `input_requested` for, because a
    hand-set bool beside a hand-written literal pinned the bug green. The same
    test holds the count in the sentence above to the registry, since nothing
    else does and it has been wrong twice.
    """

    key: str
    label: str
    discover: Discoverer
    collect: Collector
    reports_rate: bool = False
    reports_needs_input: bool = False
    usage: UsageProvider | None = None
    usage_is_fetch: bool = False


def default_harnesses(*, usage_fetch_enabled: bool = True) -> tuple[HarnessSpec, ...]:
    """Every supported harness, in display order.

    No collector notifies. Claude's did until DRC-4192, and this function took
    the popup notifier to bind that one row; the popup decision now belongs to
    `Application`, which is the only place that sees a row's final state, so
    ``Collector`` is one five-argument contract and every row is the collector
    module's own attribute.

    ``usage_fetch_enabled`` is ``--no-usage`` arriving at assembly: with the
    fetch off, no row that depends on the fetch keeps a usage provider, so
    nothing ever reads the fetch cache and the ``usage_fetch`` flag can never
    rise. That covers Claude and Cursor, which fetch, and Antigravity, whose
    quota is pushed rather than fetched but which the flag still drops because
    turning usage off means the whole section.
    """
    from .collectors import (  # noqa: PLC0415 — deferred to keep import order acyclic
        antigravity,
        claude,
        codex,
        copilot,
        cursor,
        droid,
        gemini,
        goose,
        opencode,
        pi,
    )

    return (
        HarnessSpec(
            "claude",
            "Claude",
            claude.discover,
            claude.collect,
            reports_rate=True,
            # Three paths, more than any other row: the bundled hook, an
            # actionable Notification POST, and a pending input tool in the
            # transcript. Codex, Copilot and Cursor have one apiece; the
            # remaining six are tracked per harness under B2.
            reports_needs_input=True,
            usage=claude.usage if usage_fetch_enabled else None,
            usage_is_fetch=True,
        ),
        HarnessSpec(
            "codex",
            "Codex",
            codex.discover,
            codex.collect,
            reports_rate=True,
            # Through the event overlay, not the collector: its bundled
            # `PermissionRequest` hook maps to `input_requested`. Measured on
            # 0.149.0 -- the hook fires with the prompt open, and a hook that
            # prints nothing lets that prompt reach the human.
            reports_needs_input=True,
            usage=codex.usage,
        ),
        HarnessSpec("pi", "Pi", pi.discover, pi.collect, reports_rate=True),
        # Gemini CLI was retired on 2026-06-18 and Antigravity replaced it.
        # They shared this row while both were Google's current surface; the
        # legacy row stays so a machine that ran Gemini CLI keeps its history.
        HarnessSpec("gemini", "Gemini", gemini.discover, gemini.collect, reports_rate=True),
        # Antigravity's quota arrives as a pushed status-line receipt rather
        # than a fetch, so `usage_is_fetch` stays False: there is no outbound
        # request to disclose, and the first-run banner must not appear for it.
        # `--no-usage` still drops the provider, because a user turning usage
        # off means the whole section, not just the network half.
        HarnessSpec(
            "antigravity",
            "Antigravity",
            antigravity.discover,
            antigravity.collect,
            reports_rate=True,
            usage=antigravity.usage if usage_fetch_enabled else None,
        ),
        # Copilot, OpenCode, Cursor and Droid leave `reports_rate` at False, and
        # it is a reading of their stores rather than a gap in their collectors:
        # OpenCode, Cursor and Droid record no token accounting, and Copilot's
        # store carries AI-Unit quota receipts and no per-message token counts.
        HarnessSpec(
            "copilot",
            "Copilot",
            copilot.discover,
            copilot.collect,
            # The third route, and neither of the other two: its own collector
            # reads the gate off the store. Copilot writes `permission.requested`
            # to `events.jsonl` when the dialog opens and `permission.completed`
            # only when the human answers, joined on `data.requestId`, so an
            # unanswered pair in the tail IS the standing prompt. No hook, no
            # adapter, nothing for the user to install.
            reports_needs_input=True,
            usage=copilot.usage,
        ),
        HarnessSpec("opencode", "OpenCode", opencode.discover, opencode.collect),
        # Cursor's allowance is money against a monthly billing cycle, fetched
        # from the RPC its own CLI calls, so this is a second `usage_is_fetch`
        # row: the disclosure banner must cover it exactly as it covers Claude.
        HarnessSpec(
            "cursor",
            "Cursor",
            cursor.discover,
            cursor.collect,
            # Copilot's route, on a different store: the collector reads it, no
            # hook and nothing to install. A standing tool-call gate leaves a
            # non-empty `pendingToolExecutionContracts` on the newest blob of the
            # chat's SQLite store, and the answer appends one with the map
            # emptied. The hook surface is a decided negative and stays one:
            # `beforeShellExecution` runs BEFORE the permission decision and
            # feeds into it, so a wait posted from there would paint every Cursor
            # row on its first command.
            reports_needs_input=True,
            usage=cursor.usage if usage_fetch_enabled else None,
            usage_is_fetch=True,
        ),
        HarnessSpec("goose", "Goose", goose.discover, goose.collect, reports_rate=True),
        HarnessSpec("droid", "Droid", droid.discover, droid.collect),
    )


# The published fields that never pass through `records.safe_text`, and the
# nested lists that hold more of them. A table rather than a block per field:
# four blocks are what let `state_detail` and `subagents[].name` be forgotten,
# and a line in a list is harder to leave out than a paragraph of loop.
#
# `state_detail` earns its place twice over. It is built by hand from the same
# transcript text — an in-progress task's `activeForm` is copied into it BEFORE
# the sweep runs — and it is read at ten render sites across six web files,
# including notification text, which can leave the page through the native
# notifier.
_RAW_ROW_TEXT: Final = ("title", "last_prompt", "state_detail")

# `(the row field holding a list of dicts, the keys inside each one)`.
#
# A task subject is the agent's wording rather than the operator's, so it is not
# prompt-derived in the sense DRC-4267 uses; it is here because a todo written
# from a prompt that held a key can quote it. A subagent name is operator text
# outright on four harnesses: opencode publishes the child session's own TITLE
# there, the same string this sweep redacts when that session is a parent row,
# and goose, codex and claude slice theirs out of the record with no `safe_text`
# in the way.
_RAW_NESTED_TEXT: Final = (
    ("tasks", ("subject", "activeForm")),
    ("subagents", ("name",)),
)


def _redact_in_place(holder: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        value = holder.get(key)
        if isinstance(value, str) and value:
            holder[key] = records.redact_secrets(value)


def _redact_published_text(rows: list[Session]) -> list[Session]:
    """Credential shapes out of the row fields that carry operator text.

    `records.safe_text` redacts on the way through and most published strings
    pass through it, but the fields swept here do not: the collectors build them
    out of the transcript by hand and bound them with a slice. Ten call sites
    would be ten chances for the eleventh harness to be forgotten, which is how
    `last_prompt` came to be published raw in the first place, so the sweep runs
    once over the assembled rows instead. A collector added later is covered
    without being asked.

    Adding a field to the tables above is cheap and leaving one out is not, so
    the bar is "could a collector ever put transcript text in it", not "does one
    today". `state_detail` and `subagents[].name` were both left out on that
    second reading and both were measured publishing a credential run unmarked.

    Placed before the overlays only because it can be: an overlay patches state,
    never a title (see `events`). It is before `_notify_waits` deliberately — a
    native popup is a screen exposure exactly as the card is.

    `redact_secrets` rather than `safe_text`, because these fields are published
    raw by design and this is not the change that starts scrubbing their control
    characters.

    It mutates, and returns the list it was handed so the caller can chain. The
    return value exists for that and nothing else.
    """
    for row in rows:
        _redact_in_place(row, _RAW_ROW_TEXT)
        instruction = row.get("instruction")
        if isinstance(instruction, dict):
            _redact_in_place(instruction, ("text",))
        for field, keys in _RAW_NESTED_TEXT:
            for item in row.get(field) or ():
                if isinstance(item, dict):
                    _redact_in_place(item, keys)
    return rows


def _hide_unmeasured_rates(rows: list[Session], harnesses: tuple[HarnessSpec, ...]) -> None:
    """Replace a rate-blind collector's numeric placeholder with wire-level unknown."""
    reporting = {spec.key for spec in harnesses if spec.reports_rate}
    for row in rows:
        if row["harness"] not in reporting:
            row["rate_per_min"] = None


class Application:
    """One dashboard process's collection surface.

    Everything ambient is injected, so two applications can run in one
    interpreter without sharing configuration, caches, notifications or a clock.
    """

    def __init__(
        self,
        config: RuntimeConfig,
        state: RuntimeState,
        harnesses: tuple[HarnessSpec, ...],
        *,
        native_notifier: Callable[[str], str],
        popup_notifier: Callable[[str, str], None],
        diagnostic_sink: Callable[[str], None],
        clock: Callable[[], float] = time.time,
        overlays: OverlaySource | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.harnesses = harnesses
        self.native_notifier = native_notifier
        self.popup_notifier = popup_notifier
        self.diagnostic_sink = diagnostic_sink
        self.clock = clock
        # None until the coordinator is attached, and None forever under
        # --no-events. A collection with no overlay source is exactly the
        # scan-only behaviour that shipped before events existed, which is what
        # makes the rollback switch a one-line assembly change.
        self.overlays = overlays

    def harness_label(self, key: str) -> str:
        """The registry's display label for a harness key, or "" for anything else.

        "" and not the key, unlike the page's session-row fallback: a row's
        harness comes from a collector and is a registry key by construction,
        while an ask's is written by the agent that registered it and `unknown` is
        the shipped default for every client but Claude Code. Echoing the key back
        would title the common case "unknown is asking you".

        Resolved from `self.harnesses`, the same source the payload's `harnesses`
        array is built from, so a popup title and the board cannot disagree about
        what a harness is called.
        """
        return next((spec.label for spec in self.harnesses if spec.key == key), "")

    def collect(self, *, show_all: bool) -> Collection:
        config, state = self.config, self.state
        window_hours = config.window_hours
        now = self.clock()
        cleared_marks = dismissals.refresh(config, state)
        # Sampled before the harness loop for the reason Claude's collector used
        # to sample it before its transcript scan: a SessionEnd that commits
        # while this collection is in flight must invalidate the popup, and a
        # generation read at decision time would only be compared against itself.
        generations = notifications.hook_generations(state)
        out_sessions: list[Session] = []
        harnesses: list[dict[str, Any]] = []
        usage: list[dict[str, Any]] = []
        usage_supported = False
        usage_fetch_active = False
        for spec in self.harnesses:
            try:
                found = bool(spec.discover(config, state))
            except OSError:
                found = False
            harness: dict[str, Any] = {
                "key": spec.key,
                "label": spec.label,
                "discovered": found,
                # Whether a `rate_per_min` from this harness is a measurement at
                # all. Stated per harness because it is a property of the store;
                # the matching session field is null when the answer is no.
                "reports_rate": spec.reports_rate,
                # Whether this harness can report a gate at all, for the same
                # reason `reports_rate` is here: the page cannot derive it, and
                # the absence of a needs-input row is not evidence of quiet.
                "reports_needs_input": spec.reports_needs_input,
                "error": None,
            }
            harnesses.append(harness)
            if not found:
                continue
            try:
                out_sessions.extend(spec.collect(config, state, now, window_hours, show_all))
            except Exception as e:  # noqa: BLE001 — one broken harness must not take down the rest
                harness["error"] = f"{type(e).__name__}: {e}"
                runtime_io.diag(
                    f"[{spec.key}] collector error: {harness['error']}",
                    self.diagnostic_sink,
                )
            if spec.usage is None:
                continue
            # The `usage` key exists exactly when a discovered harness can
            # publish quota; the page keeps its band hidden otherwise. A
            # failed quota read is a diagnostic, never a harness error — the
            # session rows above already collected, and a broken tile must
            # not repaint the whole strip red.
            usage_supported = True
            usage_fetch_active = usage_fetch_active or spec.usage_is_fetch
            try:
                usage.extend(spec.usage(config, state, now, window_hours))
            except Exception as e:  # noqa: BLE001 — same boundary as the collector above
                runtime_io.diag(
                    f"[{spec.key}] usage error: {type(e).__name__}: {e}",
                    self.diagnostic_sink,
                )

        out_sessions = _redact_published_text(sessions.dedupe_sessions(out_sessions))
        _hide_unmeasured_rates(out_sessions, self.harnesses)
        self._mark_unreachable_by_events(out_sessions)
        # Between dedupe and the sort, deliberately. Dedupe keys on
        # (harness, sid), which no overlay changes, and the sort ranks on `state`,
        # which an overlay does change: patching after the sort would leave a row
        # ranked by the state it no longer claims. The summary below is counted
        # from the patched rows for the same reason.
        self._apply_overlays(out_sessions, now=now)
        # After the overlays, which is load-bearing: a wait only an event knows
        # about is a wait, and reading the collector's state is what left the
        # overlay lane silent on every harness.
        #
        # Before the subtraction only by convention. `maybe_popup` consults the
        # dismissal store itself and returns before its own bookkeeping, so a
        # dismissed row records nothing under either ordering and nothing
        # observable changes if these two lines swap — measured, not assumed.
        # The order is kept because it is the one that stays correct if the gate
        # ever stops consulting the store.
        self._notify_waits(out_sessions, generations)
        out_sessions, cleared = _subtract_dismissed(out_sessions, cleared_marks)
        sessions.assign_display_ids(config, out_sessions)
        out_sessions.sort(key=row_order)
        active_sessions = [x for x in out_sessions if x["active"]]
        total_tasks = sum(x["total"] for x in out_sessions)
        total_done = sum(x["done"] for x in out_sessions)
        collection: Collection = {
            "generated": now,
            "window_hours": window_hours,
            # The trailing window every `rate_per_min` below is averaged over.
            # Published so a consumer can name the window it is ranking on
            # instead of hardcoding a figure that would go on reading "10 min"
            # the day this configuration changed it.
            "rate_window_sec": config.rate_window_sec,
            "show_all": show_all,
            # How many rows this payload dropped because the reader marked them
            # handled. A count and not a flag on the rows: the tab title, the
            # gate queue and calm's idle clip all derive from `sessions`, and a
            # per-row flag is a thing each of them would have to remember.
            "cleared": cleared,
            # Which layer owns needs-input popups. Empty means the page should
            # raise its own; a backend name means the server already did.
            "native_notify": self.native_notifier(config.platform_name),
            "harnesses": harnesses,
            "summary": {
                "needs_input": sum(1 for x in active_sessions if x["state"] == "needs_input"),
                "working": sum(1 for x in active_sessions if x["state"] == "working"),
                "rate_per_min": sum(
                    x["rate_per_min"] for x in active_sessions if x["rate_per_min"] is not None
                ),
                "active_sessions": len(active_sessions),
                "open_tasks": sum(x["open"] for x in out_sessions),
                "progress_pct": round(total_done * 100 / total_tasks) if total_tasks else 0,
                "total_tasks": total_tasks,
                "total_done": total_done,
            },
            "sessions": out_sessions,
        }
        if config.dismissals_enabled:
            # The capability flag, keyed the way `usage_fetch` is: present exactly
            # when the store is live, so `--no-dismiss` leaves the page with no
            # control to offer rather than one that answers 503.
            collection["dismiss"] = True
        # Folded in rather than branched on here: `collect` sits on ruff's
        # complexity and statement caps, and an inline `if` puts it over both.
        collection.update(self._ask_cards(now))
        if usage_supported:
            # Present even when empty: the page distinguishes "no quota data
            # yet" (key with no entries) from "nothing here publishes quota"
            # (no key), and only the former draws the band.
            collection["usage"] = sorted(usage, key=lambda u: str(u.get("harness", "")))
        if usage_fetch_active:
            # The fetcher's capability flag: present exactly when a discovered
            # harness's quota comes from the network fetcher. The page's
            # first-run disclosure banner keys on it, so it must never rise for
            # a disk-read provider or with the fetch disabled.
            collection["usage_fetch"] = True
        return collection

    def _ask_cards(self, now: float) -> dict[str, Any]:
        """The ask capability flag and its cards, or nothing at all.

        Keyed the way `dismiss` is, and for the same reason: absent means the
        page draws no control, so `--no-ask` leaves a reader with nothing to
        click rather than a button whose click answers 503.

        `pending` sweeps as it reads, and it returns only unresolved asks, so an
        answered card can never reappear on the board between the click and the
        poller collecting it. The sweep is no longer the only one: `register`
        sweeps too, because a collection is not guaranteed to happen and a
        registration is. What the coordinator does guarantee is that an
        outstanding ask forces collections while it lasts, which is what renders
        the card here with no browser tab open.
        """
        config, state = self.config, self.state
        if not config.ask_enabled:
            return {}
        return {
            "ask": True,
            "asks": [
                {
                    "id": ask.id,
                    "harness": ask.harness,
                    "session_id": ask.session_id,
                    "project": ask.project,
                    "question": ask.question,
                    "options": list(ask.options),
                    "age_sec": round(now - ask.created),
                }
                for ask in state.asks.pending(
                    now=now,
                    deadline=config.ask_deadline_sec,
                    retention=config.ask_retention_sec,
                )
            ],
        }

    def _notify_waits(self, out_sessions: list[Session], generations: dict[str, int]) -> None:
        """Raise the native popup for every row that has just started waiting.

        Here rather than in a collector, and that is the amendment DRC-4192
        made to R-5 in docs/design-runtime-architecture.md. The one-layer rule —
        the server notifies where `native_notifier` names a backend, the browser
        where it does not — rested on the server firing for whatever the browser
        stood down for. It fired for Claude alone, because `maybe_popup` had one
        caller and it was Claude's collector, so on macOS a Codex row at a real
        gate alerted nobody at all. This is also the only place that sees a row's
        FINAL state: `_apply_overlays` runs after every collector has returned,
        so a wait reported by a hook POST and nothing else was silent even on
        Claude.

        The label comes from `self.harnesses`, the same source the payload's
        `harnesses` array is built from, so a popup and the board cannot disagree
        about what a harness is called. `harness_label` answers "" for anything
        the registry does not carry, and a row's harness is a registry key by
        construction; the key is echoed rather than a blank subject shipped, as
        the page's own session-row fallback does.

        Inactive rows are skipped, which is what `show_all` collections rest on:
        `--all` widens what is drawn, never what alerts.
        """
        for session in out_sessions:
            if not session.get("active"):
                continue
            harness, sid = str(session["harness"]), str(session["sid"])
            state = str(session.get("state") or "")
            notifications.maybe_popup(
                self.config,
                self.state,
                notifications.PopupSubject(
                    harness=harness,
                    label=self.harness_label(harness) or harness,
                    prefix=sid,
                    # The whole-subtree reading, the same field the dismissal
                    # subtraction below compares, so the popup gate and the row
                    # cannot lapse at different moments.
                    activity=float(session.get("last_activity") or 0.0),
                ),
                state,
                _wait_popup_body(session) if state == "needs_input" else None,
                expect_generation=generations.get(sid, 0),
                popup_notifier=self.popup_notifier,
            )

    def _mark_unreachable_by_events(self, out_sessions: list[Session]) -> None:
        """Disclose the rows no event can ever reach, before any overlay lands.

        Six of the ten harnesses have no entry in the event vocabulary, so
        `events.parse` refuses their envelopes outright and their rows are read
        off disk and nothing else. Their idle rows therefore cannot say whether a
        turn ended, and without this an unmarked row would mean either "did not
        finish" or "cannot be seen from here" — the same collapse the retired
        `stale` gloss was admitting to (DRC-4035 D4).

        A property of the harness, not of this process, so it is stated whether or
        not a coordinator is attached. Written before `_apply_overlays` on
        purpose: an adapter harness's own overlay owns this field, and the two
        must not be able to disagree about one row.
        """
        for session in out_sessions:
            if str(session["harness"]) not in runtime_events.IDENTITY_NORMALIZERS:
                session["acquisition"] = runtime_events.ACQUISITION_SCAN

    def _apply_overlays(self, out_sessions: list[Session], *, now: float) -> None:
        """Patch collected rows from the live overlay ledger, if one is attached.

        The row list is walked, not the ledger: an overlay can only ever reach a
        session a collector produced, so there is no path here by which one
        creates or removes a row. `note_rows` then reports the full key set back,
        which is what lets an unmatched overlay wait or expire rather than
        silently doing nothing forever.
        """
        source = self.overlays
        if source is None:
            return
        for session in out_sessions:
            harness, sid = str(session["harness"]), str(session["sid"])
            overlays = source.overlays_for(harness, sid)
            finished_at = source.finished_at(harness, sid)
            git = source.git_for(harness, sid)
            if overlays or finished_at or git is not None:
                patch = runtime_events.reduce_overlays(
                    overlays,
                    now=now,
                    # The row's own reading of when the session last wrote,
                    # which is the only evidence that outlives a wait no hook
                    # ever closes. Collectors that do not report it send 0,
                    # and the wait then stands.
                    own_activity=float(session.get("own_activity") or 0.0),
                    # The whole-tree reading, subagents included, which is
                    # what retires a stop no `turn_started` ever follows. A
                    # parked parent with a running child is working, so idle
                    # cannot key on `own_activity` the way a wait does.
                    session_activity=float(session.get("last_activity") or 0.0),
                    activity_grace_sec=self.config.overlay_wait_activity_grace_sec,
                    # Reduced rather than written straight onto the row, so the
                    # mark passes the same activity guard the idle overlay does
                    # even though it outlives the ledger that overlay lives in.
                    finished_at=finished_at,
                    # Reduced rather than written onto the row for the reason the
                    # mark above is: a reading taken at a session end must still
                    # lose to any overlay saying the session is alive again.
                    git=None if git is None else (git.dirty, git.changed),
                )
                self._note_dispute(session, patch, overlays, now=now)
                runtime_events.apply_patch(session, _keep_wait_detail(session, patch))
            else:
                # No ledger for this row means nothing can be disagreeing with it.
                self._clear_dispute(harness, sid)
        collected = {(str(s["harness"]), str(s["sid"])) for s in out_sessions}
        source.note_rows(collected)
        # A session that vanishes mid-dispute reaches neither branch above, so
        # its episode would be held open forever, pinning a record the ring has
        # already evicted.
        with self.state.dispute_lock:
            for key in [k for k in self.state.dispute_episodes if k not in collected]:
                del self.state.dispute_episodes[key]

    def _note_dispute(
        self,
        session: Session,
        patch: Mapping[str, Any],
        overlays: list[Overlay],
        *,
        now: float,
    ) -> None:
        """Record an overlay overruling a collector that had found a wait.

        Only that direction. A collector Idle row an overlay promotes to Working
        is the ordinary path and says nothing, so counting it would bury the case
        this exists to find. See docs/design-needs-input.md (N-6).

        One record per episode, not per collection. A disagreement stands until
        something changes it, and collections run at the memo floor, so recording
        each one made `dispute_total` count polls and let a single 90-second
        episode fill the ring on its own. An episode keeps its shape while the
        two states and the newest arrival sequence hold; anything else is a new
        fault and gets its own record.

        Records rather than decides: the patch is applied either way. Which side
        is right is not knowable here, and DRC-4095 and DRC-4097 are the same
        disagreement resolved the other way round.
        """
        key = (str(session["harness"]), str(session["sid"]))
        patched = patch.get("state")
        if session.get("state") != "needs_input" or patched not in {"working", "idle"}:
            self._clear_dispute(*key)
            return
        # Subagent overlays are excluded from the shape deliberately. They patch
        # no state, so a child starting or stopping changes the disagreement not
        # at all, but each is remembered under its own slot with a fresh
        # sequence. Counting them split one standing wait into a record per child
        # transition, on fan-outs, which DRC-4121 established are the sessions
        # most likely to be holding a prompt in the first place.
        shape = (
            "needs_input",
            str(patched),
            max(
                (o.arrival_seq for o in overlays if o.kind != runtime_events.OVERLAY_SUBAGENT),
                default=-1,
            ),
        )
        # Read before the lock, not inside it: `drop_counters` takes the
        # coordinator's lock, and nesting one under the other would make an
        # ordering load-bearing that nothing else in the file relies on.
        counters = self.overlays.drop_counters() if self.overlays else {}
        with self.state.dispute_lock:
            open_episode = self.state.dispute_episodes.get(key)
            if open_episode is not None and open_episode[0] == shape:
                record = open_episode[1]
                record["last_seen_at"] = now
                record["repeats"] = int(record["repeats"]) + 1
                return
            record = {
                "at": now,
                "last_seen_at": now,
                "repeats": 0,
                "harness": key[0],
                "sid": key[1],
                "collector_state": "needs_input",
                "overlay_state": patched,
                "own_activity": float(session.get("own_activity") or 0.0),
                "last_activity": float(session.get("last_activity") or 0.0),
                # The guard's own constant, so a record stays readable against a
                # build whose constant has since moved.
                "activity_grace_sec": self.config.overlay_wait_activity_grace_sec,
                "overlays": runtime_events.overlay_rows(overlays, now=now),
                # Reading 3 against reading 4 in N-5, an envelope dropped versus
                # never posted, is a counter comparison. The live counters are
                # cumulative, so a record read tomorrow can only bracket itself
                # against its neighbours if it carries its own copy.
                "drop_counters": counters,
            }
            self.state.dispute_total += 1
            self.state.disputes.append(record)
            self.state.dispute_episodes[key] = (shape, record)

    def _clear_dispute(self, harness: str, sid: str) -> None:
        """Close a session's open episode, so the next one is a new record."""
        with self.state.dispute_lock:
            self.state.dispute_episodes.pop((harness, sid), None)

    def request_usage_fetch(self) -> bool:
        """Maybe start a background quota fetch; the gates live in `quota`.

        Called only from `/api/data` handling for requests that carry the
        page's consent — never from `collect`, which `--diagnose` also runs
        and which must stay free of network side effects.
        """
        return quota.request_fetch(
            self.config,
            self.state,
            clock=self.clock,
            diagnostic_sink=self.diagnostic_sink,
        )

    @property
    def snapshot(self) -> runtime_snapshot.Snapshot:
        """The runtime's published responses. Owned by state, not by this object."""
        return self.state.snapshot

    def collect_json(self, *, show_all: bool) -> tuple[runtime_snapshot.Revision, bytes]:
        """The published response for one variant, collecting only if stale.

        Two locks, deliberately. `collect_memo_lock` is still held across
        collection, so ThreadingHTTPServer callers share one filesystem and
        SQLite scan rather than stampeding a cold entry. The snapshot's own lock
        is taken only to read or write the published tuple, so a slow reader can
        never block a collection and a collection can never block a reader.

        The freshness floor is `collect_memo_sec`, unchanged from the memo this
        replaced, so the worst-case staleness a `curl` or headless caller sees is
        exactly what it was before.
        """
        key: runtime_snapshot.SnapshotKey = (self.config.window_hours, show_all)
        published = self._fresh_snapshot(key)
        if published is not None:
            return published
        with self.state.collect_memo_lock:
            # Re-check under the lock: another thread may have collected while
            # this one waited, which is the whole point of holding it.
            published = self._fresh_snapshot(key)
            if published is not None:
                return published
            body = json.dumps(self.collect(show_all=show_all)).encode()
            revision = self.snapshot.publish(key, body, now=self.clock())
            # Only a freshly minted revision is worth announcing. A warm reuse
            # returns above without reaching this line, so a connected client is
            # never woken for a state it already has.
            self.state.streams.publish(revision)
            return revision, body

    def _fresh_snapshot(
        self, key: runtime_snapshot.SnapshotKey
    ) -> tuple[runtime_snapshot.Revision, bytes] | None:
        """The published entry for `key` if it is inside the floor, else None."""
        age = self.snapshot.age(key, now=self.clock())
        if age is None or age >= self.config.collect_memo_sec:
            return None
        return self.snapshot.current(key)
