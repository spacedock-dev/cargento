"""A selected Claude model cannot silently weaken or change a reading."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import cli, config, lifecycle, observer, reading, reading_route

from .support import make_config


class ClaudeModelsHaveAnExplicitBaseline(unittest.TestCase):
    def test_the_default_request_is_sonnet_five_point_five(self) -> None:
        self.assertEqual("claude-sonnet-5-5", make_config().claude_reading_model)

    def test_explicit_baseline_and_higher_families_are_admitted(self) -> None:
        for value in (
            "claude-sonnet-5",
            "claude-sonnet-5-5",
            "claude-sonnet-6",
            "claude-opus-5",
            "claude-opus-5-5",
            "claude-sonnet-5-5-20261001",
        ):
            with self.subTest(value=value):
                self.assertEqual(value, config.validate_claude_reading_model(value))

    def test_unknown_aliases_lower_models_and_injected_flags_are_refused(self) -> None:
        for value in (
            "sonnet",
            "opus",
            "default",
            "latest",
            "claude-sonnet-4-9",
            "claude-haiku-5-5",
            "claude-haiku-6",
            "claude-opus-4-9",
            "claude-sonnet-5.5",
            "claude-sonnet-05",
            "claude-sonnet-5-0",
            "claude-sonnet-5 --tools Bash",
            "--model=claude-sonnet-5",
            "claude-sonnet-5\n--resume",
            "claude-sonnet-5-5-20260230",
            "",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                config.validate_claude_reading_model(value)

    def test_config_does_not_inherit_an_unreviewed_cli_default(self) -> None:
        built = config.build_runtime_config(
            environ={"HOME": "/synthetic", "ANTHROPIC_MODEL": "haiku"},
            platform_name="linux",
            os_name="posix",
            launcher_path=Path("server.py"),
            claude_reading_model="claude-sonnet-5",
        )
        self.assertEqual("claude-sonnet-5", built.claude_reading_model)
        with self.assertRaises(ValueError):
            config.build_runtime_config(
                environ={},
                platform_name="linux",
                os_name="posix",
                launcher_path=Path("server.py"),
                claude_reading_model="haiku",
            )


class ASelectedModelReachesTheBoundedCall(unittest.TestCase):
    def _call(self, selected: str, *, failure: bool = False) -> tuple[Any, list[Any]]:
        with tempfile.TemporaryDirectory() as home:
            cfg = dataclasses.replace(
                make_config(), state_dir=Path(home), claude_reading_model=selected
            )
            seen: list[Any] = []

            def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
                seen.append((argv, kwargs))
                kwargs["stdout"].write(b"{}")
                return subprocess.CompletedProcess(argv, int(failure))

            result = observer.claude_exec(
                cfg,
                "synthetic evidence",
                output_cap_bytes=64,
                runner=runner,
                binary_resolver=lambda _name: "/synthetic/bin/claude",
            )
            self.assertEqual([], list(Path(home).iterdir()))
            return result, seen

    def test_user_selected_baseline_is_the_only_model_argument(self) -> None:
        result, seen = self._call("claude-sonnet-5")
        self.assertEqual(("{}", "ok"), result)
        argv, kwargs = seen[0]
        self.assertEqual(1, argv.count("--model"))
        self.assertEqual("claude-sonnet-5", argv[argv.index("--model") + 1])
        self.assertEqual("", argv[argv.index("--tools") + 1])
        self.assertIn("--safe-mode", argv)
        self.assertIn("--restricted", argv)
        self.assertEqual(observer.OBSERVER_READING_TIMEOUT_SEC, kwargs["timeout"])

    def test_unavailable_selected_model_never_retries_on_the_baseline(self) -> None:
        result, seen = self._call("claude-sonnet-5-5", failure=True)
        self.assertEqual(("", "failed"), result)
        self.assertEqual(1, len(seen))
        self.assertEqual("claude-sonnet-5-5", seen[0][0][seen[0][0].index("--model") + 1])

    def test_invalid_selection_refuses_before_any_launch(self) -> None:
        for selected in ("claude-haiku-6", "sonnet", "claude-sonnet-5 --tools Bash"):
            with self.subTest(selected=selected):
                result, seen = self._call(selected)
                self.assertEqual(("", "unavailable"), result)
                self.assertEqual([], seen)

    def test_invalid_selection_is_not_an_available_reading_model(self) -> None:
        cfg = dataclasses.replace(make_config(), claude_reading_model="haiku")
        model = reading.ClaudeReadingModel(cfg, binary_resolver=lambda _name: "/synthetic/claude")
        self.assertFalse(model.available())

    def test_provenance_binds_selection_without_inventing_a_served_snapshot(self) -> None:
        cfg = dataclasses.replace(make_config(), claude_reading_model="claude-sonnet-5")
        old = observer.claude_reading_provenance(cfg)
        new = observer.claude_reading_provenance(
            dataclasses.replace(cfg, claude_reading_model="claude-sonnet-5-5")
        )
        self.assertEqual("claude-sonnet-5", old["selected_model"])
        self.assertIsNone(old["resolved_model"])
        self.assertEqual("high", old["effort"])
        self.assertEqual([5, 0, 1], old["admission_rank"])
        self.assertEqual([5, 5, 1], new["admission_rank"])
        self.assertNotEqual(old["envelope_digest"], new["envelope_digest"])


class ConfigurationAndDisclosureSelectTheSameModel(unittest.TestCase):
    def test_cli_selection_survives_daemon_respawn(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["--claude-reading-model", "claude-sonnet-5"])
        cfg, _state = cli.build_runtime(args, started=0.0)
        self.assertEqual("claude-sonnet-5", cfg.claude_reading_model)
        child = parser.parse_args(lifecycle.spawn_argv(cfg, args)[2:])
        child_cfg, _state = cli.build_runtime(child, started=0.0)
        self.assertEqual("claude-sonnet-5", child_cfg.claude_reading_model)

    def test_invalid_cli_selection_is_refused_without_echoing_untrusted_text(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stderr(out), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--claude-reading-model", "bad-secret-material"])
        self.assertNotIn("bad-secret-material", out.getvalue())

    def test_published_route_names_the_configured_model(self) -> None:
        cfg = dataclasses.replace(make_config(), claude_reading_model="claude-sonnet-5")
        route = reading_route.resolve(
            "claude",
            config=cfg,
            binary_resolver=lambda name: f"/synthetic/{name}",
        )
        self.assertEqual("claude", route["provider"])
        self.assertEqual("claude-sonnet-5", route["model"])
        all_routes = reading_route.resolve_all(
            ["claude", "codex"],
            config=cfg,
            binary_resolver=lambda name: f"/synthetic/{name}",
        )
        self.assertEqual("claude-sonnet-5", all_routes["claude"]["model"])
