"""Spacedock workflow cartography: parsing, attribution and the read policy.

Every read here is a project read rather than a store read, so the identity
checks, symlink refusal and byte bounds in this module are the security
boundary described in SECURITY.md.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat as stat_module
from typing import TYPE_CHECKING, Any

from cargento_runtime import sessions
from cargento_runtime import state as runtime_state

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.state import RuntimeState


# Spacedock drives work items ("entities") through an ordered list of named
# stages, with a "first officer" session dispatching "ensign" workers. Four
# facts make it visible to a passive reader, in decreasing order of authority:
#
# 1. The launcher starts the session with `--agent spacedock:first-officer`, so
#    the transcript's first records carry an ``agentSetting``. That alone proves
#    the session is Spacedock, and costs nothing: it is in the head bytes the
#    subagent classifier already reads.
# 2. The first officer runs `spacedock status --boot` at startup and the JSON
#    envelope lands in the transcript as a tool result, carrying the ABSOLUTE
#    workflow directory and the ABSOLUTE entity-state directory, so nothing has
#    to be discovered by scanning.
# 3. The ordered stage list, and which stages are initial or terminal, is the one
#    fact that envelope's `dispatchable` view omits, so it is read from the
#    workflow README's frontmatter. See SECURITY.md for the contract these reads
#    operate under.
# 4. The entity-state directory holds one file per entity, whose frontmatter
#    ``status`` is the stage it is parked on right now.
#
# Fact 4 exists because ``dispatchable`` is a snapshot of what was dispatchable
# AT BOOT, not the entity roster. A long-running first officer that boots an
# empty queue and intakes work later (the common case) reports
# `dispatchable: []` forever, so a strip anchored on it alone never renders.
#
# Every parser here is pure so the whole matrix is exercisable on any runner
# (design decision D-4 in docs/design-cross-platform.md).
SPACEDOCK_FO = "spacedock:first-officer"


SPACEDOCK_ENSIGN = "spacedock:ensign"


SD_STAGE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


SD_CYCLE_RE = re.compile(r"^(?:cycle|pass|round|c|v|p|r)\d+[a-z]?$|^(?:retry|rerun)$")


SD_COMMISSIONED_PREFIX = "spacedock@"


def frontmatter_lines(config: RuntimeConfig, text: str) -> list[str]:
    """The lines between a leading ``---`` fence and its closer, else [].

    Mirrors Spacedock's own fence finder: a leading BOM is stripped, truly
    empty leading lines are skipped, and the first content line must be exactly
    ``---``. CRLF is normalized so a ``---\\r`` fence still matches.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    start = None
    for index, raw in enumerate(lines):
        line = raw.removeprefix("﻿") if index == 0 else raw
        if line == "":
            continue
        if line.strip() != "---":
            return []
        start = index + 1
        break
    if start is None:
        return []
    out: list[str] = []
    for raw in lines[start:]:
        if raw.strip() == "---":
            return out
        if len(out) >= config.spacedock_max_frontmatter_lines:
            return []
        out.append(raw)
    return []  # unterminated frontmatter is not frontmatter


def scalar(lines: list[str], key: str) -> str:
    """A column-0 scalar from frontmatter lines, unquoted."""
    prefix = key + ":"
    for raw in lines:
        if raw.startswith(prefix):
            return raw[len(prefix) :].strip().strip("\"'")
    return ""


def truthy(value: str) -> bool:
    """YAML's true-ish scalars, quoted or bare. Anything else is false."""
    return value.strip().strip("\"'").lower() in {"true", "yes", "on"}


def stage_entries(config: RuntimeConfig, lines: list[str]) -> list[dict[str, Any]]:
    """The ordered ``stages.states[]`` list, or [] if unrecognised.

    Each entry is ``{"name", "initial", "terminal"}``. An indentation-scoped
    scan, not a YAML evaluator: enter ``stages:``, then ``states:``, then take
    each ``- name:`` until the block dedents to a sibling key
    (``transitions:``), attributing the ``initial:``/``terminal:`` flags nested
    under an item to it. Document order is the stage order — Spacedock's own
    advancement indexes this list.

    Anything the scan cannot model yields [] so the dashboard renders no strip
    rather than a wrong one. That deliberately covers flow-style sequences,
    quoted keys, anchors and aliases.
    """
    entries: list[dict[str, Any]] = []
    names: set[str] = set()
    stages_indent: int | None = None
    states_indent: int | None = None
    item_indent: int | None = None
    for raw in lines:
        body = raw.strip()
        if not body or body.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if stages_indent is None:
            if body == "stages:":
                stages_indent = indent
            continue
        if states_indent is None:
            if indent <= stages_indent:
                return []  # left the stages block without finding states
            if body == "states:":
                states_indent = indent
            continue
        if indent <= states_indent and not body.startswith("- "):
            break  # dedented to a sibling of states:
        if body.startswith("- "):
            if item_indent is None:
                item_indent = indent
            if indent == item_indent and not body.startswith("- name:"):
                # A states entry this scanner cannot model (flow style
                # `- {name: x}`, a quoted key, an anchor). Skipping it would emit
                # a spine missing a stage the workflow really declares — a wrong
                # strip, the one outcome worse than no strip. Deeper `- ` items
                # are nested values (a stage's `decision.options`), not states.
                return []
        if not body.startswith("- name:") or indent != item_indent:
            # A flag nested under the item currently being built. Deeper `- `
            # items reach here too, but they cannot start with these keys.
            if entries and item_indent is not None and indent > item_indent:
                for flag in ("initial", "terminal"):
                    if body.startswith(flag + ":"):
                        entries[-1][flag] = truthy(body[len(flag) + 1 :])
            continue
        value = body[len("- name:") :].strip().strip("\"'")
        if not value or not SD_STAGE_RE.match(value) or value in names:
            return []
        if len(entries) >= config.spacedock_max_stages:
            return []
        names.add(value)
        entries.append({"name": value, "initial": False, "terminal": False})
    return entries


def stage_names(config: RuntimeConfig, lines: list[str]) -> list[str]:
    """The ordered stage names, or [] if the states block is unrecognised."""
    return [entry["name"] for entry in stage_entries(config, lines)]


def tool_result_text(record: dict[str, Any]) -> list[str]:
    """The text of every ``tool_result`` block in one transcript record.

    Provenance matters: boot output is *command output*, so it counts only when
    it arrives in a tool result. Scanning the raw line would let ordinary
    conversation text — anything a user pasted or a model echoed — nominate an
    absolute path for Cargento to open.
    """
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        text = block.get("content")
        if isinstance(text, str):
            out.append(text)
        elif isinstance(text, list):
            out.extend(
                part["text"]
                for part in text
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
    return out


def boot_records(config: RuntimeConfig, data: bytes) -> list[dict[str, Any]]:
    """Every ``spacedock status --boot`` envelope in a transcript head.

    Decoded line by line as the JSONL it is, so the JSON decoder does the
    unescaping and each envelope is located inside already-plain text. An
    earlier version scanned the escaped bytes with a hand-rolled brace balancer,
    which both mis-sliced a path containing a brace and rescanned to the end of
    the blob for every unbalanced marker — quadratic, under the collection lock.
    """
    out: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for line in data.split(b"\n"):
        if b"definition_dir" not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        for text in tool_result_text(record):
            position = 0
            for _ in range(config.spacedock_max_boot_candidates):
                begin = text.find('{"command"', position)
                if begin < 0:
                    break
                try:
                    envelope, position = decoder.raw_decode(text, begin)
                except ValueError:
                    # raw_decode fails at the first bad byte, so stepping past a
                    # bad candidate cannot degrade into a whole-blob rescan.
                    position = begin + 1
                    continue
                if isinstance(envelope, dict) and envelope.get("command") == "boot":
                    out.append(envelope)
                    if len(out) >= config.spacedock_max_boot_records:
                        return out
    return out


def workflow_dirs(config: RuntimeConfig, envelopes: list[dict[str, Any]]) -> list[str]:
    """Distinct absolute workflow directories named by boot envelopes.

    Order is first-seen so the display order matches the boot order. Only
    absolute paths are kept: a relative value cannot be resolved without
    guessing a base, and guessing is what the read contract forbids.
    """
    out: list[str] = []
    for record in envelopes:
        value = record.get("definition_dir")
        if not isinstance(value, str) or not value:
            continue
        if not os.path.isabs(value) or "\x00" in value:
            continue
        if value not in out:
            out.append(value)
        if len(out) >= config.spacedock_max_workflows:
            break
    return out


def boot_entities(envelopes: list[dict[str, Any]], workflow_dir: str) -> dict[str, str]:
    """``{slug: current_stage}`` for one workflow, newest envelope winning.

    A first officer boots once per workflow and may re-boot; later envelopes
    carry fresher stages, so they overwrite earlier ones.
    """
    out: dict[str, str] = {}
    for record in envelopes:
        if record.get("definition_dir") != workflow_dir:
            continue
        items = record.get("dispatchable")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            current = item.get("current")
            if isinstance(slug, str) and slug and isinstance(current, str) and current:
                out[slug] = current
    return out


def boot_entity_dir(envelopes: list[dict[str, Any]], workflow_dir: str) -> str:
    """The absolute entity-state directory one workflow's boot output names.

    Same provenance and same authority as ``definition_dir``: the session's own
    command output, in a tool result. The newest envelope wins, and the value is
    kept only if it is absolute — a relative path cannot be resolved without
    guessing a base, and guessing is what the read contract forbids. A
    ``split-root`` workflow legitimately stores state outside its definition
    directory, so containment is NOT required here; the discriminator is applied
    per file instead (see :func:`read_entities`).
    """
    out = ""
    for record in envelopes:
        if record.get("definition_dir") != workflow_dir:
            continue
        value = record.get("entity_dir")
        if isinstance(value, str) and value and os.path.isabs(value) and "\x00" not in value:
            out = value
    return out


def transcript_boot(config: RuntimeConfig, state: RuntimeState, path: str) -> list[dict[str, Any]]:
    """Boot envelopes from a transcript's head, cached per (path, size).

    Boot output is written once at session start and never rewritten, so the
    scan is amortised: keying on size lets a still-growing session pick the
    envelope up on a later refresh without rescanning an unchanged prefix.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    key = (path, min(size, config.spacedock_boot_scan_bytes))
    with state.cache_lock:
        cached = state.spacedock_boot_cache.get(key)
    if cached is not None:
        return cached
    envelope_records: list[dict[str, Any]] = []
    try:
        with open(path, "rb") as handle:
            blob = handle.read(config.spacedock_boot_scan_bytes)
        if b"definition_dir" in blob:
            envelope_records = boot_records(config, blob)
    except OSError:
        return []
    with state.cache_lock:
        runtime_state.bounded_put(
            state.spacedock_boot_cache, key, envelope_records, limit=config.max_cache_entries
        )
    return envelope_records


def open_regular(path: str) -> int | None:
    """Open ``path`` read-only, refusing symlinks and non-regular files.

    ``O_NOFOLLOW`` is absent on Windows, so there the refusal rests on the
    ``lstat`` classification alone and a racing reparse-point swap could still
    be followed — the same unclosable class as the FILE_SHARE_DELETE window
    documented in SKILL.md.
    """
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        if stat_module.S_ISLNK(os.lstat(path).st_mode):
            return None
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        if not stat_module.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            return None
    except OSError:
        os.close(descriptor)
        return None
    return descriptor


class SdMismatchError(Exception):
    """The opened file is not the one that was stat'd. Distinct from an empty
    read, which is merely a file with no frontmatter."""


def read_frontmatter(
    config: RuntimeConfig, path: str, limit: int, expect: os.stat_result
) -> list[str]:
    """The frontmatter lines of a regular, non-symlink file, or [].

    At most ``limit`` bytes are read, and the descriptor must describe the same
    file ``expect`` does. O_NOFOLLOW guards only the final path component, so a
    parent-directory swap between the stat and the open would otherwise seed a
    cache from a different file under a trusted key — that raises
    :class:`SdMismatchError` so the caller can decline to cache. Only the frontmatter
    lines leave this function; the body is never returned.
    """
    descriptor = open_regular(path)
    if descriptor is None:
        return []
    try:
        opened = os.fstat(descriptor)
        same_file = (opened.st_dev, opened.st_ino) == (expect.st_dev, expect.st_ino)
    except OSError:
        same_file = False
    if not same_file:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        raise SdMismatchError(path)
    raw = b""
    try:
        handle = os.fdopen(descriptor, "rb")
    except OSError:
        # os.fdopen does not close the descriptor when it fails to wrap it,
        # and this runs on every refresh — leaking here exhausts the table.
        with contextlib.suppress(OSError):
            os.close(descriptor)
    else:
        with handle, contextlib.suppress(OSError):
            raw = handle.read(limit)
    return frontmatter_lines(config, raw.decode("utf-8", "replace"))


def read_workflow(
    config: RuntimeConfig, state: RuntimeState, workflow_dir: str
) -> dict[str, Any] | None:
    """The stage taxonomy of one workflow directory, or None.

    ``workflow_dir`` is an absolute path the session itself recorded in its boot
    output; it is canonicalised, its README must be a regular non-symlink file,
    at most ``config.spacedock_readme_bytes`` are read, and the result counts only if the
    frontmatter declares ``commissioned-by: spacedock@`` — Spacedock's own
    workflow discriminator. No other file in the workflow directory is read and
    no directory is walked; the entity-state directory the boot output names
    separately is read by :func:`read_entities`. Only derived scalars leave
    this function; no file text does.

    ``resting`` is the subset of stages an entity is not moving through: the
    initial stage it is queued on and the terminal stages it has finished at.
    """
    try:
        root = os.path.realpath(workflow_dir)
        readme = os.path.join(root, "README.md")
        info = os.stat(readme)
    except OSError:
        return None
    # Containment: the README must resolve inside the directory it was found in,
    # so a symlinked or swapped entry cannot redirect the read elsewhere.
    try:
        resolved = os.path.realpath(readme)
        if os.path.commonpath((root, resolved)) != root:
            return None
    except (OSError, ValueError):
        return None
    key = (root, info.st_mtime_ns, info.st_size)
    with state.cache_lock:
        if key in state.spacedock_workflow_cache:
            return state.spacedock_workflow_cache[key]
    result: dict[str, Any] | None = None
    try:
        lines = read_frontmatter(config, readme, config.spacedock_readme_bytes, info)
    except SdMismatchError:
        return None
    if scalar(lines, "commissioned-by").startswith(SD_COMMISSIONED_PREFIX):
        entries = stage_entries(config, lines)
        if entries:
            result = {
                "name": os.path.basename(root) or root,
                "stages": [entry["name"] for entry in entries],
                "resting": [
                    entry["name"] for entry in entries if entry["initial"] or entry["terminal"]
                ],
            }
    with state.cache_lock:
        runtime_state.bounded_put(
            state.spacedock_workflow_cache, key, result, limit=config.max_cache_entries
        )
    return result


def entity_stage(
    config: RuntimeConfig, state: RuntimeState, path: str, info: os.stat_result
) -> str:
    """The ``status`` scalar in one entity file's frontmatter, or "".

    Cached on ``(path, st_mtime_ns, st_size)``, so a state directory in which
    only one entity is moving costs one read per refresh and a stat per file.
    """
    key = (path, info.st_mtime_ns, info.st_size)
    with state.cache_lock:
        cached = state.spacedock_entity_cache.get(key)
    if cached is not None:
        return cached
    try:
        lines = read_frontmatter(config, path, config.spacedock_entity_bytes, info)
    except SdMismatchError:
        return ""
    stage = scalar(lines, "status")
    with state.cache_lock:
        runtime_state.bounded_put(
            state.spacedock_entity_cache, key, stage, limit=config.max_cache_entries
        )
    return stage


def entity_files(config: RuntimeConfig, entity_dir: str) -> list[tuple[str, str, os.stat_result]]:
    """``(slug, path, stat)`` for a state directory's entity files, newest first.

    Spacedock writes an entity as either ``<slug>.md`` or ``<slug>/index.md``
    (the folder form, for entities that accumulate per-stage artifacts). One
    ``scandir`` of the directory the boot output named; nothing below it is
    walked, and ``_archive/`` — where Spacedock retires finished entities — is
    skipped along with every other name that is not a well-formed slug.

    Newest-first because the cap that follows is a budget: a mature queue holds
    far more entities than it is running, and the ones being written are the
    ones in flight.

    Every candidate is `lstat`ed for real rather than taking the stat
    ``scandir`` already cached. On Windows that cached result reports
    ``st_ino`` and ``st_dev`` as zero, which can never match the ``fstat`` of an
    open descriptor — so the identity check in :func:`read_frontmatter`
    would refuse every entity file and the strip would come back empty on that
    platform alone. A silent per-platform false negative is exactly the failure
    mode D-4 in ``docs/design-cross-platform.md`` exists to keep out.
    """
    try:
        with os.scandir(os.path.realpath(entity_dir)) as entries:
            found = list(entries)
    except OSError:
        return []
    out: list[tuple[str, str, os.stat_result]] = []
    for entry in found:
        name = entry.name
        slug = name.removesuffix(".md")
        # Spacedock's slug grammar is its stage grammar: lowercase kebab. That
        # rejects `_archive`, `README.md` and the report files operators leave
        # beside the state without a second pass over the listing.
        if not SD_STAGE_RE.match(slug):
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                path = os.path.join(entry.path, "index.md")
            elif name.endswith(".md"):
                path = entry.path
            else:
                continue
            info = os.lstat(path)
        except OSError:
            continue  # entity written or retired between the listing and the stat
        if not stat_module.S_ISREG(info.st_mode):
            continue  # a symlinked entity file is refused, not followed
        out.append((slug, path, info))
    out.sort(key=lambda item: -item[2].st_mtime_ns)
    return out[: config.spacedock_max_entity_files]


def read_entities(
    config: RuntimeConfig,
    state: RuntimeState,
    entity_dir: str,
    stages: list[str],
    now: float,
    window_sec: float,
) -> list[tuple[str, str]]:
    """``[(slug, stage)]`` for one workflow's recent entity state, newest first.

    The authoritative, current answer to "where is each entity", against which
    the boot envelope's ``dispatchable`` snapshot is only a stale hint. An entity
    counts only when:

    - its state file was written within ``window_sec`` — the same freshness
      window every collector applies to a session. A first officer discovers
      every workflow in the project, and a workflow retired months ago still has
      entities frozen mid-pipeline; those are history, not work in flight.
    - its frontmatter ``status`` names a stage this workflow declares — the
      per-file discriminator that stands in for the containment check
      :func:`read_workflow` performs, since a ``split-root`` workflow may
      legitimately keep its state outside the definition directory.
    """
    declared = set(stages)
    out: list[tuple[str, str]] = []
    for slug, path, info in entity_files(config, entity_dir):
        if not sessions.is_fresh(config, now, info.st_mtime, window_sec):
            continue
        stage = entity_stage(config, state, path, info)
        if stage in declared:
            out.append((slug, stage))
    return out


def attribute_worker(name: str, slugs: list[str], stages: list[str]) -> tuple[str, str, str] | None:
    """``(slug, stage, cycle)`` for a worker, anchored on a *known* slug.

    Guessing the slug by stripping cycle-shaped tokens is wrong twice over: real
    entity slugs end in cycle-shaped tokens of their own (`…-pr-1506-r3` is one
    entity, not `…-pr-1506` on round 3), and a guessed slug matches every other
    workflow that declares the same stage. So the slug comes from this
    workflow's own boot snapshot, longest first so a slug that prefixes another
    cannot win.
    """
    body = name.removeprefix("spacedock-ensign-")
    if body == name:
        return None
    for slug in sorted(slugs, key=len, reverse=True):
        remainder = body.removeprefix(slug + "-")
        if remainder == body:
            continue
        tokens = remainder.split("-")
        for stage in sorted(stages, key=len, reverse=True):
            stage_tokens = stage.split("-")
            for offset in range(len(tokens) - len(stage_tokens), -1, -1):
                if tokens[offset : offset + len(stage_tokens)] != stage_tokens:
                    continue
                rest = tokens[:offset] + tokens[offset + len(stage_tokens) :]
                if any(not SD_CYCLE_RE.match(token) for token in rest):
                    continue
                return (slug, stage, "-".join(rest))
    return None


def session_workflows(
    config: RuntimeConfig,
    state: RuntimeState,
    boot: list[dict[str, Any]],
    worker_names: list[str],
    now: float,
    window_sec: float,
) -> list[dict[str, Any]]:
    """Render-ready workflow strips for one session.

    An entity earns a strip when it is *in flight*: named by a live worker, or
    parked on a stage it is moving through, or listed as dispatchable at boot.
    Three sources in decreasing order of freshness — live workers first and
    marked, then the entity state directory, then the boot snapshot — deduped by
    slug so the freshest answer for an entity wins.

    Entities resting on the initial or a terminal stage are left out of the
    middle source. A mature queue is mostly those: reporting thirty entities
    parked on ``intake`` would push the handful that are actually moving off the
    end of the strip. They still appear if boot called them dispatchable, which
    is Spacedock's own statement that they are next to move.
    """
    out: list[dict[str, Any]] = []
    for workflow_dir in workflow_dirs(config, boot):
        info = read_workflow(config, state, workflow_dir)
        if info is None:
            continue
        stages: list[str] = info["stages"]
        resting: set[str] = set(info["resting"])
        booted = boot_entities(boot, workflow_dir)
        entity_dir = boot_entity_dir(boot, workflow_dir)
        roster = (
            read_entities(config, state, entity_dir, stages, now, window_sec) if entity_dir else []
        )
        # Live worker names carry a stage but not a slug boundary, so the slug
        # has to come from a roster. The state directory is what makes that
        # roster non-empty for a first officer that booted an empty queue.
        slugs = list({slug for slug, _ in roster} | set(booted))
        entities: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in worker_names:
            attributed = attribute_worker(name, slugs, stages)
            if attributed is None:
                continue
            slug, stage, cycle = attributed
            if slug in seen:
                continue
            seen.add(slug)
            entities.append({"slug": slug, "stage": stage, "cycle": cycle, "live": True})
        for slug, stage in roster:
            if slug in seen or stage in resting:
                continue
            seen.add(slug)
            entities.append({"slug": slug, "stage": stage, "cycle": "", "live": False})
        for slug, stage in booted.items():
            if slug in seen or stage not in stages:
                continue
            seen.add(slug)
            entities.append({"slug": slug, "stage": stage, "cycle": "", "live": False})
        if not entities:
            continue
        out.append(
            {
                "workflow": info["name"],
                "stages": stages,
                "entities": entities[: config.spacedock_max_entities],
            }
        )
    return out
