"""Generic incremental turn scanning and turn display data."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from . import io as runtime_io
from . import records, sessions

if TYPE_CHECKING:
    from .config import RuntimeConfig
    from .state import RuntimeState


def _apply_turn_record(
    config: RuntimeConfig,
    st: dict[str, Any],
    record: Any,
    harness: str,
) -> None:
    """Apply one chronological transcript record to incremental turn state."""
    ep = records.parse_ts(record.get("timestamp") or "")
    if not ep:
        return
    # A quiet stretch longer than the gap-reset window inside a turn means the
    # agent was not generating (permission wait, AskUserQuestion, sleep).
    # Bank the active segment and restart the clock at the post-gap event so
    # "elapsed" reflects work, not waiting.
    if st["turn_start"] and st["prev_ts"] and ep - st["prev_ts"] > config.turn_gap_reset_sec:
        if st["prev_ts"] > st["turn_start"]:
            st["durations"].append(st["prev_ts"] - st["turn_start"])
        st["turn_start"] = ep
        st["last_start"] = ep
    sig = records._turn_signal(record, harness)  # noqa: SLF001
    if sig:
        kind, override = sig
        if kind == "end":
            if st["turn_start"] and ep > st["turn_start"]:
                st["durations"].append(ep - st["turn_start"])
            st["turn_start"] = None
        else:
            if (
                kind == "prompt"
                and st["turn_start"]
                and st["prev_ts"]
                and st["prev_ts"] > st["turn_start"]
            ):
                st["durations"].append(st["prev_ts"] - st["turn_start"])
            start = records.norm_epoch(override) or ep
            st["turn_start"] = start
            st["last_start"] = start
    st["prev_ts"] = ep


def _latest_turn_context(
    config: RuntimeConfig,
    path: str,
    end_pos: int,
    harness: str,
) -> dict[str, Any]:
    """Find the nearest turn boundary before ``end_pos`` without loading the
    prefix into memory. Used when the file is larger than the forward-read
    budget so a long current turn is not lost."""
    context: dict[str, Any] = {"turn_start": None, "last_start": None, "prev_ts": None}
    if end_pos <= 0:
        return context
    active_decided = False
    later_ts: float | None = None
    for raw in runtime_io.reverse_lines(config, path, end_pos):
        if not raw.startswith(b"{"):
            continue
        try:
            decoded = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(decoded, dict):
            continue
        transcript_records = (
            reversed(records.gemini_records(decoded)) if harness == "gemini" else (decoded,)
        )
        for record in transcript_records:
            ep = records.parse_ts(record.get("timestamp") or "")
            if not ep:
                continue
            # Walking backward: `later_ts` is the timestamp of the record that
            # chronologically FOLLOWS this one. A quiet gap re-anchors the turn
            # at the post-gap record, same rule as the forward scanner.
            if later_ts is not None and later_ts - ep > config.turn_gap_reset_sec:
                if not active_decided:
                    context["turn_start"] = later_ts
                context["last_start"] = later_ts
                return context
            later_ts = ep
            if context["prev_ts"] is None:
                context["prev_ts"] = ep
            sig = records._turn_signal(record, harness)  # noqa: SLF001
            if not sig:
                continue
            kind, override = sig
            if not active_decided:
                active_decided = True
                if kind != "end":
                    context["turn_start"] = records.norm_epoch(override) or ep
            if kind != "end":
                context["last_start"] = records.norm_epoch(override) or ep
                return context
    return context


def scan_turns(
    config: RuntimeConfig,
    state: RuntimeState,
    path: str,
    harness: str,
) -> dict[str, Any] | None:
    """Whole-file turn tracker for JSONL harnesses. The transcript tail can
    be shorter than the current turn (long turns bury the prompt beyond the
    tail window), so turns are tracked incrementally: each call parses only
    bytes appended since the last call and carries state in ``turn_scan``.

    Serialized via the scanner lock — concurrent /api/data requests would
    otherwise double-advance pos and double-count durations."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    with state.scanner_lock:
        st = state.turn_scan.get(path)
        if st is None or st["pos"] > size:  # new, truncated, or rotated file
            if len(state.turn_scan) >= config.max_cache_entries:
                state.turn_scan.pop(next(iter(state.turn_scan)))
            st = {
                "pos": 0,
                "turn_start": None,
                "last_start": None,
                "durations": [],
                "prev_ts": None,
                "gemini_seen": {},
                "gemini_snapshot_count": 0,
                "gemini_snapshot_tail": None,
            }
            state.turn_scan[path] = st
        if size == st["pos"]:
            return st
        if size - st["pos"] > config.turn_scan_max_bytes:
            # Locate the active turn boundary in the skipped prefix with a
            # reverse mmap scan, then process the bounded tail forward.
            tail_start = size - config.turn_scan_max_bytes
            st.update(_latest_turn_context(config, path, tail_start, harness))
            st["pos"] = tail_start
        with open(path, "rb") as f:
            f.seek(st["pos"])
            data = f.read()
        end = data.rfind(b"\n")
        if end < 0:
            return st  # incomplete line, wait for more bytes
        st["pos"] += end + 1
        for raw in data[:end].split(b"\n"):
            if not raw.startswith(b"{"):
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            transcript_records = (
                records.incremental_gemini_records(d, st) if harness == "gemini" else (d,)
            )
            for record in transcript_records:
                if harness == "gemini":
                    fingerprint = records.record_fingerprint(record)
                    if fingerprint in st["gemini_seen"]:
                        continue
                    if len(st["gemini_seen"]) >= config.gemini_seen_entries:
                        st["gemini_seen"].pop(next(iter(st["gemini_seen"])))
                    st["gemini_seen"][fingerprint] = None
                _apply_turn_record(config, st, record, harness)
        st["durations"] = st["durations"][-50:]
        return st


def turns_from_events(events: list[tuple[float, bool]]) -> dict[str, Any]:
    """Turn state from chronologically sorted (epoch, is_user_prompt) pairs —
    used by DB-backed harnesses where messages come from SQL, not a file."""
    turn_start = prev = None
    durations = []
    for ep, is_user in events:
        if not ep:
            continue
        if is_user:
            if turn_start and prev and prev > turn_start:
                durations.append(prev - turn_start)
            turn_start = ep
        prev = ep
    return {"turn_start": turn_start, "durations": durations[-50:]}


def turn_progress(
    scan: dict[str, Any] | None,
    session_state: str,
    now: float,
    config: RuntimeConfig,
) -> dict[str, Any] | None:
    """Naive current-turn ETA: estimated total = median of this session's
    past turns that lasted at least as long as the current one has so far."""
    if session_state != "working" or not scan or not scan.get("turn_start"):
        return None
    elapsed = sessions.age(config, now, scan["turn_start"])
    if elapsed is None:
        return None  # turn start is implausibly ahead of the clock; no ETA
    history = scan.get("durations") or []
    cands = sorted(d for d in history if d >= elapsed)
    if cands:
        est_total = cands[len(cands) // 2]
        return {
            "elapsed_h": sessions.fmt_duration(elapsed),
            "eta_h": sessions.fmt_duration(est_total - elapsed),
            "pct": min(99, round(elapsed * 100 / est_total)) if est_total else 99,
            "long": max(est_total, elapsed) >= config.long_turn_warn_sec,
        }
    return {
        "elapsed_h": sessions.fmt_duration(elapsed),
        "eta_h": None,  # running longer than any recent turn
        "pct": 99 if history else None,
        "long": elapsed >= config.long_turn_warn_sec,
    }
