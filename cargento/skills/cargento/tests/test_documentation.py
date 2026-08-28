from __future__ import annotations

import json
import re
import unittest
from typing import TYPE_CHECKING, Any, ClassVar

from cargento_runtime import cli, git_status
from cargento_runtime import config as runtime_config
from cargento_runtime.web import page as frontend_page

from .support import (
    SERVER_PATH,
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

    def test_the_documented_unread_threshold_is_the_one_the_page_applies(self) -> None:
        # The gloss this replaced described a threshold nothing read any more.
        # SKILL.md states this one in minutes, so the two can only agree by
        # accident unless something compares them.
        match = re.search(r"const FINISHED_UNREAD_SEC = (\d+);", frontend_page.load_script())
        assert match is not None, "the unread threshold moved or was renamed"
        self.assertIn(f"for {int(match.group(1)) // 60} minutes", self.SKILL)

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
    def records(path: Path) -> list[dict[str, Any]]:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

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
