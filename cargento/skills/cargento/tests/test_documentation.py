from __future__ import annotations

import contextlib
import io
import json
import os
import re
import unittest
from typing import TYPE_CHECKING, Any, ClassVar

from cargento_runtime import cli, git_status, history
from cargento_runtime import config as runtime_config

from .support import (
    SERVER_PATH,
    make_config,
)

if TYPE_CHECKING:
    from pathlib import Path


class DocumentationMatchesCodeTest(unittest.TestCase):
    """Reviewers found documentation describing behaviour the code no longer
    had, twice. These assert the claims against the implementation."""

    SKILL = (SERVER_PATH.parent / "SKILL.md").read_text(encoding="utf-8")

    def posix_roots(self) -> dict[str, list[str]]:
        roots: dict[str, list[str]] = runtime_config.resolve_store_roots(
            platform_name="darwin", environ={}, home="/HOME"
        )
        return roots

    def test_documented_store_paths_are_the_ones_searched(self) -> None:
        # Every "~/..." path in the data-source list must be a real default.
        # ".claude/settings" (the user's own hook config) and ".cargento" (Cargento's
        # own state and log directory) are not harness stores, so the store-root
        # assertion below does not apply to them.
        excluded_prefixes = (".claude/settings", ".cargento")
        documented = {
            "~/" + match
            for match in re.findall(r"`~/([\w./*<>-]+?)[`/]", self.SKILL)
            if not match.startswith(excluded_prefixes)
        }
        searched = {
            root.replace("/HOME", "~") for roots in self.posix_roots().values() for root in roots
        }
        for path in sorted(documented):
            with self.subTest(documented=path):
                self.assertTrue(
                    any(
                        root.startswith(path.rstrip("/")) or path.startswith(root)
                        for root in searched
                    ),
                    f"SKILL.md documents {path} but nothing searches it: {sorted(searched)}",
                )

    def test_documented_env_overrides_are_the_ones_honoured(self) -> None:
        documented = {
            name
            for name in (
                "CLAUDE_CONFIG_DIR",
                "CODEX_HOME",
                "GEMINI_CLI_HOME",
                "COPILOT_HOME",
                "PI_CODING_AGENT_DIR",
                "PI_CODING_AGENT_SESSION_DIR",
            )
            if f"`{name}`" in self.SKILL
        }
        self.assertEqual(set(runtime_config.STORE_ENV_VARS), documented)
        # And each one actually redirects its store.
        for name, key, expected in (
            ("CLAUDE_CONFIG_DIR", "claude.projects", "/opt/x/projects"),
            ("CODEX_HOME", "codex.sessions", "/opt/x/sessions"),
            ("GEMINI_CLI_HOME", "gemini.tmp", "/opt/x/.gemini/tmp"),
            ("COPILOT_HOME", "copilot.root", "/opt/x"),
            ("PI_CODING_AGENT_DIR", "pi.sessions", "/opt/x/sessions"),
            ("PI_CODING_AGENT_SESSION_DIR", "pi.sessions", "/opt/x"),
        ):
            with self.subTest(env=name):
                roots = runtime_config.resolve_store_roots(
                    platform_name="linux", environ={name: "/opt/x"}, home="/HOME"
                )
                self.assertEqual([expected], roots[key])

    def test_the_documented_python_floor_matches_the_tooling(self) -> None:
        self.assertIn("Python 3.11+", self.SKILL)
        pyproject = (SERVER_PATH.parents[3] / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('python_version = "3.11"', pyproject)
        self.assertIn('target-version = "py311"', pyproject)

    def test_documented_urls_use_the_address_the_server_binds(self) -> None:
        # The listener is IPv4-only, so "localhost" can resolve to ::1 and fail.
        self.assertNotIn("http://localhost:4553", self.SKILL)
        self.assertIn("http://127.0.0.1:4553", self.SKILL)


class DocumentedCaptureFiguresTest(unittest.TestCase):
    """Prose that cites a capture file must still agree with the file.

    Four claims had drifted from the captures they name: a session count that
    was never five, a vocabulary comment saying every member was seen firing,
    and an "unobserved" its own paragraph refuted. A count stated in prose is
    checkable against the file it came from, so these check it.
    """

    ROOT = SERVER_PATH.parents[3]
    CAPTURES = ROOT / "docs" / "captures"
    NUMBERS: ClassVar[dict[int, str]] = {
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
    }

    @staticmethod
    def _every_pair(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        """A JSON object with every pair kept, duplicates included.

        `json.loads` keeps the LAST value for a duplicate key and the discarded
        one never becomes a node in the walk, so a record carrying
        `{"record": "…", "record": "<a label>"}` passed the vocabulary check
        with the label sitting in the committed bytes. Verified as a defeat
        before this existed. The displaced value is parked under a slot named
        after the key it lost, which no vocabulary classifies, so a duplicate
        key fails the walk instead of hiding inside it. Last-wins is preserved
        for every other assertion, which reads these records as plain dicts.
        """
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                out[f"{key} <duplicate {len(out)}>"] = out[key]
            out[key] = value
        return out

    @classmethod
    def records(cls, path: Path) -> list[dict[str, Any]]:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [
            json.loads(line, object_pairs_hook=cls._every_pair) for line in lines if line.strip()
        ]

    @staticmethod
    def unwrapped(relative: str) -> str:
        source = DocumentedCaptureFiguresTest.ROOT / relative
        return " ".join(source.read_text(encoding="utf-8").split())

    def test_the_documented_gemini_session_count_is_the_one_in_the_capture(self) -> None:
        # The hooks capture is the only Gemini file carrying a session marker,
        # so it is the only one that can settle the count the adapters cite.
        sessions = {
            record["session"]
            for record in self.records(self.CAPTURES / "gemini" / "hooks-0.53.1-macos.jsonl")
        }
        claim = f"Measured from {self.NUMBERS[len(sessions)]} real 0.53.1 sessions"
        for relative in (
            "cargento/skills/cargento/event_hook.py",
            "cargento-gemini/hooks/event_hook.py",
        ):
            with self.subTest(source=relative):
                self.assertIn(claim, self.unwrapped(relative))

    def test_the_gemini_identity_capture_cannot_count_its_own_sessions(self) -> None:
        # `events.py` said five sessions. The file holds five verdict records
        # and no session marker at all, so it cannot say how many sessions
        # wrote them; the comment states the record count instead.
        records = self.records(self.CAPTURES / "gemini" / "identity-0.53.1-macos.jsonl")
        self.assertTrue(all("session" not in record for record in records))
        self.assertTrue(
            all(
                record["id_verdicts"]["session_id"]["equals_store_line1_sessionId"]
                for record in records
            )
        )
        claim = f"in {self.NUMBERS[len(records)]} recorded verdicts"
        self.assertIn(claim, self.unwrapped("cargento/skills/cargento/cargento_runtime/events.py"))

    def test_an_unfired_gemini_event_is_named_beside_the_vocabulary(self) -> None:
        # The allowlist is the documented vocabulary, which is wider than the
        # measured one. A member that never fired has to be called out where
        # the set is declared, or the comment claims evidence it does not have.
        fired = {
            record["event"]
            for record in self.records(self.CAPTURES / "gemini" / "hooks-0.53.1-macos.jsonl")
        }
        source = (self.ROOT / "scripts" / "validate_plugins.py").read_text(encoding="utf-8")
        entry = source.split('/hooks/hooks.json": (\n        "gemini",', 1)[1]
        comment, names = entry.split("frozenset(", 1)
        declared = set(re.findall(r'"(\w+)"', names.split("}", 1)[0]))
        self.assertIn("SessionStart", declared)
        for name in sorted(declared - fired):
            with self.subTest(never_fired=name):
                self.assertIn(name, comment)

    # Globs rather than filenames. Both recorders are versioned in their own
    # names, so a re-record at a new harness build or a second drive lands
    # beside the file it supersedes -- and a hardcoded tuple then walks the old
    # one and nothing else, which is the same "read one of two files" defeat
    # this oracle was rewritten to close.
    REGISTRY_GLOB = "claude/team-registry-*.jsonl"
    DRIVE_GLOB = "claude/teammate-board-drive-*.jsonl"
    # Both DRC-4344 stores hold operator text, so the shapes-never-values rule
    # is checked over every file either recorder has written.
    TEAMMATE_CAPTURE_GLOBS: ClassVar[tuple[str, ...]] = (REGISTRY_GLOB, DRIVE_GLOB)

    # A POSITIVE vocabulary, and it has to be one. The first version of this
    # check bounded strings at 64 characters, which was defeatable six ways: it
    # walked values and never keys, it exempted two containers, and the bound sat
    # ABOVE the text it guarded, since the labels these files must not carry are
    # `agentName` values and workflow identifiers and the harness caps its own
    # names at 64. A structural rule fails for the same reason -- a workflow
    # identifier is shaped exactly like a field name. So every string in these
    # files, key or value, at any depth, must be a member of one of the sets
    # below or match one of the patterns. A string nobody has classified fails,
    # which is the only form of this check that a label cannot walk through.
    _SCHEMA_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            # The keys the two recorders write.
            "format",
            "harness",
            "os",
            "at",
            "record",
            "claude_version",
            "registry",
            "registry_mtime_age_days",
            "top_level_keys",
            "member_fields",
            "member_count",
            "members",
            "backendType",
            "isActive",
            "isActive_present",
            "joinedAt_type",
            "older_registry_fields",
            "newer_registry_fields",
            "added",
            "removed",
            "added_fields_the_runtime_reads",
            "added_fields_deliberately_unread",
            "layout",
            "session",
            "record_types_in_order",
            "first_timestamped_record_index",
            "header_fields",
            "files",
            "first_timestamped_record_index_per_file",
            "reads_at_index_zero",
            "verdict",
            "arm",
            "lead",
            "element_key_sets",
            "element_keys_uniform",
            "published_total",
            "published_with_a_measured_start",
            "published_with_a_null_start",
            "direct_children",
            "grandchildren",
            "grandchildren_active",
            "distinct_parents_named",
            "active_true",
            "active_false",
            "active_null",
            "state",
            "state_detail_shape",
            "state_detail_subagent_count",
            "chrome_running_subagents",
            "chrome_published_subagents",
            "registered_members",
            "before_published",
            "before_with_a_measured_start",
            "before_grandchildren_reachable",
            "after_published",
            "after_with_a_measured_start",
            "after_grandchildren_reachable",
            "after_distinct_parents_named",
            "grandchildren_active_while_running",
            "grandchildren_present_after_they_stopped",
            "grandchildren_active_after_they_stopped",
            "state_detail_counts_grandchildren",
            "ac4_state_fields_moved_old_vs_new",
            "ac4_sessions_compared",
            "state_detail_counts_only_direct_children",
            "a_quiet_teammate_reads_inactive_while_its_own_worker_runs",
            "state_may_lag_a_demoted_child_by_seconds",
        }
    )
    _HARNESS_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            # Field names read out of the harness's own stores. A new harness build
            # that adds one fails this check until somebody classifies it, which is
            # the behaviour an evidence file wants.
            "agentId",
            "agentName",
            "agentSetting",
            "agentType",
            "apiBlockIndex",
            "attributionAgent",
            "attributionPlugin",
            "attributionSkill",
            "color",
            "createdAt",
            "cwd",
            "effort",
            "entrypoint",
            "gitBranch",
            "isSidechain",
            "isSnapshotUpdate",
            "joinedAt",
            "leadAgentId",
            "leadSessionId",
            "leafUuid",
            "members",
            "message",
            "messageId",
            "model",
            "name",
            "parentUuid",
            "permissionMode",
            "planModeRequired",
            "prompt",
            "requestId",
            "sessionId",
            "session_id",
            "snapshot",
            "sourceToolAssistantUUID",
            "started_at",
            "subscriptions",
            "teamName",
            "timestamp",
            "tmuxPaneId",
            "toolUseResult",
            "type",
            "userType",
            "uuid",
            "version",
            "active",
            "parent",
        }
    )
    _HARNESS_TOKENS: ClassVar[frozenset[str]] = frozenset(
        {
            # Closed vocabularies the harness or the recorder picks from, never text
            # a person wrote. Same class as `tool` and `notification_type` in the
            # captures README.
            "agent-setting",
            "mode",
            "permission-mode",
            "user",
            "assistant",
            "attachment",
            "atis",
            "atis-latch",
            "last-prompt",
            "file-history-snapshot",
            "in-process",
            "tmux",
            "claude",
            "darwin",
            "working",
            "team_registry_shape",
            "registry_field_drift",
            "transcript_header_shape",
            "first_timestamp_index_verdict",
            "board_drive_arm",
            "board_drive_verdict",
            "top_level",
            "legacy_subagents",
            "positive",
            "negative",
            "control_before",
        }
    )
    _RECORDER_SENTENCES: ClassVar[frozenset[str]] = frozenset(
        {
            # Composed by the recorder from a measurement, not copied from a store.
            "a one-line read finds the start stamp",
            "a one-line read misses the start stamp",
            "running N subagents",
        }
    )
    _PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"^(?:null|bool|int|float|string|list|object|unknown)$"),  # type names
        re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),  # ISO stamp
        re.compile(r"^[0-9a-f]{8}$"),  # an 8-char session prefix, the README's allowance
        re.compile(r"^[0-9a-f]{12}$"),  # a salted digest
        re.compile(r"^\d+\.\d+\.\d+$"),  # a harness version
        re.compile(r"^agent-[0-9a-f]{2}$"),  # a legacy subagent filename prefix
    )
    FORBIDDEN: ClassVar[frozenset[str]] = frozenset({"prompt", "message"})

    @classmethod
    def strings(cls, node: Any, trail: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
        """Every string in the record, KEYS INCLUDED.

        Walking values alone was the hole: a key is a string a recorder chose to
        write and is exactly as capable of carrying a label as a value is.
        """
        if isinstance(node, dict):
            out: list[tuple[tuple[str, ...], str]] = []
            for key, value in node.items():
                out.append(((*trail, "<key>"), str(key)))
                out += cls.strings(value, (*trail, str(key)))
            return out
        if isinstance(node, list):
            return [pair for value in node for pair in cls.strings(value, trail)]
        return [(trail, node)] if isinstance(node, str) else []

    @classmethod
    def classified(cls, text: str) -> bool:
        if (
            text in cls._SCHEMA_KEYS
            or text in cls._HARNESS_FIELDS
            or text in cls._HARNESS_TOKENS
            or text in cls._RECORDER_SENTENCES
        ):
            return True
        return any(pattern.match(text) for pattern in cls._PATTERNS)

    def matching(self, pattern: str) -> list[Path]:
        found = sorted(self.CAPTURES.glob(pattern))
        self.assertTrue(found, f"{pattern} must match at least one capture")
        return found

    def registry_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self.matching(self.REGISTRY_GLOB):
            found = self.records(path)
            self.assertTrue(found, f"{path.name} must not be empty")
            records += found
        return records

    def teammate_capture_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for pattern in self.TEAMMATE_CAPTURE_GLOBS:
            for path in self.matching(pattern):
                found = self.records(path)
                self.assertTrue(found, f"{path.name} must not be empty")
                records += found
        return records

    def test_every_string_in_a_teammate_capture_is_classified(self) -> None:
        # The whole privacy rule for these two files, in one assertion over both.
        # Falsified by: any string a recorder puts in either file that nobody has
        # classified -- an `agentName`, a workflow identifier, a description, a
        # path. A label cannot pass this the way it passed a length bound.
        unclassified = sorted(
            {
                text
                for record in self.teammate_capture_records()
                for _trail, text in self.strings(record)
                if not self.classified(text)
            }
        )
        self.assertEqual([], unclassified, "unclassified strings in a capture file")

    def test_a_teammate_captures_field_shapes_hold_only_type_names(self) -> None:
        # A field map may say what type a field holds and never what it held.
        # Falsified by: a shape map whose value is content rather than a type.
        types = {"null", "bool", "int", "float", "string", "list", "object", "unknown"}
        for record in self.teammate_capture_records():
            for name in ("member_fields", "header_fields"):
                for field, declared in (record.get(name) or {}).items():
                    self.assertLessEqual(
                        set(declared), types, f"{name}[{field}] must hold type names"
                    )

    def test_a_teammate_capture_names_a_forbidden_field_without_reading_it(self) -> None:
        # `prompt` and `message` may be named and never valued. Named `prompt`
        # must be, or the capture does not evidence the field the runtime refuses
        # to read.
        # Falsified by: a key called `prompt` holding a string, or dropping it
        # from the drift record.
        shape_maps = ("member_fields", "header_fields")
        name_lists = (
            "added",
            "removed",
            "top_level_keys",
            "older_registry_fields",
            "newer_registry_fields",
            "added_fields_the_runtime_reads",
            "added_fields_deliberately_unread",
        )
        for record in self.teammate_capture_records():
            for trail, value in self.strings(record):
                declared = bool(trail) and (trail[0] in shape_maps or trail[-1] in name_lists)
                if declared or (trail and trail[-1] == "<key>"):
                    continue
                self.assertNotIn(
                    trail[-1] if trail else "",
                    self.FORBIDDEN,
                    f"{'.'.join(trail)} records that field's value",
                )
                self.assertNotIn(value.strip().lower(), self.FORBIDDEN, f"{'.'.join(trail)}")
        drift = [r for r in self.registry_records() if r["record"] == "registry_field_drift"]
        self.assertTrue(drift, "the capture must record the registry's field drift")
        for record in drift:
            self.assertIn("prompt", record["added"])
            self.assertIn("prompt", record["added_fields_deliberately_unread"])
            self.assertNotIn("prompt", record["added_fields_the_runtime_reads"])

    def test_the_team_registry_capture_settles_the_start_stamp_index(self) -> None:
        # DRC-4344's first gap in one figure, and it must come from the file
        # rather than the code: a top-level transcript's first timestamped record
        # is not record 0, and a legacy subagent's is.
        # Falsified by: a capture whose two layouts agree, which would mean the
        # asymmetry the fix rests on was never measured.
        verdicts = {
            record["layout"]: record
            for record in self.registry_records()
            if record["record"] == "first_timestamp_index_verdict"
        }
        self.assertEqual({"top_level", "legacy_subagents"}, set(verdicts))
        top, legacy = verdicts["top_level"], verdicts["legacy_subagents"]
        self.assertEqual(0, top["reads_at_index_zero"], "no top-level file stamps record 0")
        self.assertEqual(
            legacy["files"], legacy["reads_at_index_zero"], "every legacy file stamps record 0"
        )
        self.assertNotEqual(top["verdict"], legacy["verdict"])

    def test_the_capture_files_table_is_one_block(self) -> None:
        # Two rows were left stranded below the prose that follows the table,
        # and every capture PR adds its row by copying the one above it, so a
        # split table hands the next author a broken precedent.
        lines = (self.CAPTURES / "README.md").read_text(encoding="utf-8").splitlines()
        rows = [number for number, line in enumerate(lines) if line.startswith("| `")]
        self.assertEqual(list(range(rows[0], rows[0] + len(rows))), rows)

    def test_a_post_turn_idle_push_carries_an_id_in_the_antigravity_capture(self) -> None:
        # `statusline_hook.py` called this unobserved. One of its two arms ended
        # on exactly such a push: `idle`, after `working`, carrying an id. The
        # prose states the id's width and that it named a real db, so the filter
        # reads those two verdict fields rather than the dict's truthiness -- a
        # re-recorded capture carrying `{"len": 12, "matches_a_db_stem": false}`
        # would otherwise leave this green while the sentence went false.
        arms: dict[str, list[dict[str, Any]]] = {}
        for record in self.records(self.CAPTURES / "antigravity" / "statusline-macos.jsonl"):
            arms.setdefault(record["capture"], []).append(record)
        ended_idle_with_id = []
        for arm, pushes in arms.items():
            verdict = pushes[-1]["id_verdicts"]["conversation_id"] or {}
            if (
                pushes[-1]["agent_state"] == "idle"
                and verdict.get("len") == 36
                and verdict.get("matches_a_db_stem")
                and any(push["agent_state"] == "working" for push in pushes[:-1])
            ):
                ended_idle_with_id.append(arm)
        self.assertEqual(2, len(arms))
        claim = f"{self.NUMBERS[len(ended_idle_with_id)].capitalize()} of the two arms"
        # Both the shipped adapter and the durable design record state this. A
        # correction that lands in one leaves the repository contradicting
        # itself, which is the drift DRC-4193 exists to close.
        for relative in (
            "cargento/skills/cargento/statusline_hook.py",
            "docs/plans/event-driven-session-observation.md",
        ):
            with self.subTest(source=relative):
                self.assertIn(claim, self.unwrapped(relative))


class GitProbeContractDocumentationTest(unittest.TestCase):
    """SECURITY.md's git-probe section is a contract, so the code must still meet it.

    The section was written and reviewed on its own cycle before this code existed
    (DRC-4274, promoted here from `docs/plans/git-probe-security-scope.md` and that
    file deleted in the same commit). Prose and code can only agree by accident
    unless something compares them, and this is the comparison.
    """

    ROOT = SERVER_PATH.parents[3]
    SECURITY = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    # Whitespace-collapsed, so a reflow that changes no words does not fail these.
    # The command assertion below deliberately reads the raw text instead.
    FLAT = re.sub(r"\s+", " ", SECURITY)

    def test_the_documented_command_is_the_argv_the_probe_builds(self) -> None:
        # The contract prints the command as an indented code block. If either side
        # gains or loses a flag, this fails — which is the point, because both
        # flags are independently load-bearing and neither may be dropped quietly.
        self.assertIn(
            "    " + " ".join(git_status.GIT_STATUS_ARGV) + "\n",
            self.SECURITY,
        )

    def test_the_contract_section_survived_the_promotion(self) -> None:
        self.assertIn("## Repository git reads (the end-of-session probe)", self.SECURITY)
        # The two intro amendments that had to ride with it. Without the first the
        # section is filed under a Scope clause enumerating file reads, harness-store
        # writes and non-loopback traffic — none of which is subprocess execution.
        self.assertIn(
            "running any program inside a user's repository other than the probe described in "
            "Repository git reads (the end-of-session probe),",
            self.FLAT,
        )
        self.assertIn(
            "The git probe runs inside a repository the user chose rather than a harness store, "
            "and it neither writes there nor executes anything the repository supplies.",
            self.FLAT,
        )

    def test_the_plan_document_died_with_its_promotion(self) -> None:
        # Leaving it in place states the contract in two places and lets them drift.
        self.assertFalse((self.ROOT / "docs" / "plans" / "git-probe-security-scope.md").exists())

    def test_the_documented_off_switch_is_the_flag_the_parser_accepts(self) -> None:
        self.assertIn("The off switch is `--no-git`.", self.FLAT)
        args = cli.build_parser().parse_args(["--no-git"])
        self.assertTrue(args.no_git)

    def test_the_contract_says_entries_rather_than_files(self) -> None:
        # `changed` counts porcelain entries; git collapses an untracked directory
        # into one. Rendering it as a file count is a wrong number under a true name.
        self.assertIn("counts porcelain entries rather than files", self.FLAT)


class HistoryStoreContractDocumentationTest(unittest.TestCase):
    """SECURITY.md's history section is a contract, so the code must still meet it.

    The direct analogue of `GitProbeContractDocumentationTest` above, and owed by
    the merged contract: the section was written and reviewed on its own cycle
    before this code existed (DRC-4330, promoted here from
    `docs/plans/history-store-security-scope.md` and that file deleted in the
    same commit). Prose and code can only agree by accident unless something
    compares them, and this is the comparison.
    """

    ROOT = SERVER_PATH.parents[3]
    SECURITY = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    # Whitespace-collapsed, so a reflow that changes no words does not fail these.
    FLAT = re.sub(r"\s+", " ", SECURITY)

    def test_the_contract_section_survived_the_promotion(self) -> None:
        self.assertIn("## Local history (the session history store)", self.SECURITY)

    def test_the_plan_document_died_with_its_promotion(self) -> None:
        # Leaving it in place states the contract in two places and lets them drift.
        self.assertFalse(
            (self.ROOT / "docs" / "plans" / "history-store-security-scope.md").exists()
        )

    def test_the_documented_off_switch_is_the_flag_the_parser_accepts(self) -> None:
        # The prose half is bound to a parser call, so it is not a grep over our
        # own words: until `--no-history` parses, this assertion would be one.
        self.assertIn("The off switch is `--no-history`.", self.FLAT)
        args = cli.build_parser().parse_args(["--no-history"])
        self.assertTrue(args.no_history)

    def test_the_documented_deletion_command_is_the_flag_the_parser_accepts(self) -> None:
        self.assertIn("`--forget` deletes the store and exits.", self.FLAT)
        args = cli.build_parser().parse_args(["--forget"])
        self.assertTrue(args.forget)

    def test_the_store_lives_where_the_contract_says_it_does(self) -> None:
        # "under Cargento's own directory, next to the dismissals file" — bound to
        # the path the code builds rather than asserted about our own prose.
        config = make_config(state_home="/tmp/cargento-contract")
        self.assertEqual(
            os.path.join("/tmp/cargento-contract", "cargento-history.json"),
            history.store_path(config),
        )
        self.assertIn("next to the dismissals file", self.FLAT)

    def test_the_retention_default_the_contract_names_is_the_configured_one(self) -> None:
        # "Retention is 14 days by default" — a figure in prose that no test
        # bound would drift from the constant the day either changed.
        self.assertIn("Retention is 14 days by default", self.FLAT)
        self.assertEqual(14 * 24 * 60 * 60, make_config().history_retention_sec)

    def test_the_bounds_the_contract_calls_configurable_are_flags(self) -> None:
        # The captain's ND-1 ruling of 2026-09-03. The sentence was inherited
        # verbatim from the plan doc and `build_runtime_config` accepted neither
        # figure, so it was prose about a build that could not do it. Bound to
        # the parser the way the off switch above is, rather than grepped: until
        # both flags parse, this assertion would be one about our own words.
        self.assertIn(
            "Retention is 14 days by default, with a size cap, and both are configurable.",
            self.FLAT,
        )
        args = cli.build_parser().parse_args(["--history-days", "3", "--history-max-bytes", "4096"])
        self.assertEqual(3.0, args.history_days)
        self.assertEqual(4_096, args.history_max_bytes)

    def test_the_kept_list_names_the_project_label_the_store_actually_keeps(self) -> None:
        # D4, the captain's ruling of 2026-09-03: the label was in an explicit
        # gap in the contract and the store needs it as the grouping key, so the
        # promotion put it in the kept-list. Bound to the record, so the prose
        # and the field set cannot drift apart.
        self.assertIn("the derived two-segment project label", self.FLAT)
        self.assertIn("project", history.OBSERVATION_FIELDS)

    @staticmethod
    def bullets(source: str, header: str) -> list[str]:
        """The bullet lines of the list directly under `header`.

        Scoped rather than grepped over the whole document, and that is the
        whole point of it. Every carrier name and every ban clause also occurs
        in this section's surrounding prose, so an `assertIn` over SECURITY.md
        is satisfied whatever these two lists actually say: `last_prompt` sits
        in the rationale paragraph, `state_detail` and the instruction line
        under Published text, `title` throughout. Matching the file instead of
        the list is the difference between binding a list and mentioning it.

        A moved or reworded header raises rather than widening back to the file,
        because the quiet failure here is an assertion that still passes while
        measuring nothing.
        """
        _, found, rest = source.partition(header)
        if not found:
            raise AssertionError(f"the block header moved: {header!r}")
        return [line for line in rest.split("\n\n", 1)[0].splitlines() if line.startswith("- ")]

    def test_the_absolute_bans_took_no_exception_and_still_have_none(self) -> None:
        # DEC-13 relaxed one of the four never-items and deliberately left the
        # other three alone. The count is pinned with them: a clause moved out
        # of this block and into the allowlist paragraph would still satisfy a
        # substring match on the file, which is exactly the relocation this is
        # here to refuse.
        bans = self.bullets(self.SECURITY, "with no exception available:\n\n")
        self.assertEqual(3, len(bans))
        block = " ".join(bans)
        for clause in (
            "Tool input, in whole or in part",
            "Paths.",
            "File contents, of any file",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, block)

    def test_the_contract_names_every_field_the_allowlist_admits(self) -> None:
        # DEC-13, the captain's ruling of 2026-09-04: the outright prompt-text
        # ban became a per-field allowlist. This is the direction that stops the
        # store from keeping something the contract never named.
        self.assertIn("Prompt-derived text is avoided by default and allowlisted", self.FLAT)
        entries = " ".join(self.bullets(self.SECURITY, "The allowlist, one line per field:\n\n"))
        for field in history.PROMPT_TEXT_ALLOWLIST:
            with self.subTest(field=field):
                self.assertIn(field, entries)
                # And the contract cannot name a field the store does not write:
                # an allowlist entry with no record behind it reads as an
                # exposure that exists when it does not.
                self.assertIn(field, history.OBSERVATION_FIELDS)

    def test_no_prompt_carrier_reaches_the_store_without_an_allowlist_entry(self) -> None:
        # The direction with teeth, and the one that replaces the old literal
        # quote. The ban used to be a sentence; it is now a comparison, so a
        # field added to the record without an allowlist entry fails here rather
        # than passing because nobody re-read the prose.
        for carrier in history.PROMPT_DERIVED_CARRIERS:
            if carrier in history.PROMPT_TEXT_ALLOWLIST:
                continue
            with self.subTest(field=carrier):
                self.assertNotIn(carrier, history.OBSERVATION_FIELDS)

    def test_the_allowlist_is_empty_and_the_contract_says_so(self) -> None:
        # The two have to agree about emptiness as well as about contents,
        # because "nothing yet" is the claim a reader of this contract acts on.
        self.assertEqual((), history.PROMPT_TEXT_ALLOWLIST)
        entries = self.bullets(self.SECURITY, "The allowlist, one line per field:\n\n")
        self.assertEqual(1, len(entries))
        self.assertIn("Nothing yet. No feature has earned an entry", entries[0])


class LightHarnessUsageContractDocumentationTest(unittest.TestCase):
    """DEC-14's section is a contract for a pathway nothing uses yet.

    The other contract sections here bind prose to shipped code. This one has no
    shipped code to bind to, which is exactly the state that produced the ND-1
    defect: a section inherited from a plan, describing bounds the build could
    not honour, passing because nothing compared the two. So what is bound here
    is the emptiness. The section must keep saying the pathway is unused, and the
    parser must keep having no flag to switch it off, and the day either changes
    the other has to change with it.
    """

    ROOT = SERVER_PATH.parents[3]
    SECURITY = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    FLAT = re.sub(r"\s+", " ", SECURITY)

    def test_the_section_exists_under_a_heading_other_documents_can_anchor(self) -> None:
        self.assertIn("## Light harness usage (asking a harness a bounded question)", self.SECURITY)

    def test_the_pathway_is_documented_as_unused_and_the_parser_agrees(self) -> None:
        # The load-bearing assertion. `--no-harness-usage` is the off switch the
        # section promises the first feature will ship; until then the section
        # says so and the parser has no such flag, so whoever adds the flag is
        # failed here until they amend the section. The reverse does not hold and
        # is not claimed: nothing in this suite can see a feature that uses the
        # pathway while shipping no flag, so that half is held by review.
        self.assertIn("No shipped feature uses this pathway today", self.FLAT)
        self.assertIn("That flag does not exist yet", self.FLAT)
        # argparse prints its usage to stderr before exiting, and that banner in
        # a passing run reads like a failure to anyone watching the suite.
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--no-harness-usage"])

    def test_the_invariant_names_the_second_outbound_kind_apart(self) -> None:
        # Invariant 1 used to call the quota poll "the single outbound
        # exception". A harness invocation carries session-derived text where the
        # poll carries none, so the amendment names them apart rather than
        # widening the one exception to cover both. A reader who only skims the
        # invariants has to see that distinction there.
        self.assertNotIn("The quota poll is the single outbound exception", self.FLAT)
        self.assertIn("no session content whatever", self.FLAT)
        self.assertIn(
            "the one pathway by which the operator's own words may leave this machine", self.FLAT
        )

    def test_the_consent_is_opt_in_where_the_quota_fetch_is_opt_out(self) -> None:
        # The asymmetry is the point: reading a number is not spending capacity,
        # and the section has to say which one it is.
        self.assertIn("Opt-in, and off until answered", self.FLAT)
        self.assertIn("spends their capacity rather than reading a number", self.FLAT)

    def test_the_pathway_adds_no_credential_and_no_endpoint(self) -> None:
        # The quota section owns the endpoint list and the token rules, and this
        # pathway must not quietly extend either. It invokes the operator's own
        # signed-in harness instead.
        self.assertIn("never a Cargento credential", self.FLAT)
        self.assertIn("adds no endpoint to the list in Usage quota reads", self.FLAT)
