from __future__ import annotations

import dataclasses
import hashlib
import http.client
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import aggregate, cli, lifecycle
from cargento_runtime import config as runtime_config
from cargento_runtime.web import page

from .support import make_runtime


class ReactFrontendTest(unittest.TestCase):
    HTML = b'<!doctype html><html><head><title>React</title></head><body><div id="root"></div></body></html>\n'

    def setUp(self) -> None:
        self.assertTrue(
            callable(getattr(page, "load_frontend_page", None)),
            "selected artifact loader is missing",
        )
        self.temp = tempfile.TemporaryDirectory(prefix="cargento-react-page-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(page, "WEB_DIR", self.root).start()
        # `build_id` is cached for the life of a process, and React is the default now, so
        # any earlier test that built an application has already cached the real page's id.
        page.build_id.cache_clear()
        self.addCleanup(page.build_id.cache_clear)
        self.write_package(self.HTML)

    def write_package(self, html: bytes) -> None:
        licenses = b"Controlled test license\n"
        self.metadata: dict[str, Any] = {
            "format": 1,
            "frontend": "react",
            "document": {
                "file": "react.html",
                "bytes": len(html),
                "sha256": hashlib.sha256(html).hexdigest(),
            },
            "licenses": {
                "file": "react-licenses.txt",
                "bytes": len(licenses),
                "sha256": hashlib.sha256(licenses).hexdigest(),
            },
            "provenance": {"sources": [], "fonts": [], "packages": []},
        }
        (self.root / "react.html").write_bytes(html)
        (self.root / "react-licenses.txt").write_bytes(licenses)
        self.write_metadata()

    def write_metadata(self) -> None:
        (self.root / "react.integrity.json").write_text(
            json.dumps(self.metadata) + "\n", encoding="utf-8"
        )

    def test_selected_page_and_focus_injection_preserve_pre_capability_identity(self) -> None:
        loaded = page.load_frontend_page("react")
        self.assertEqual(self.HTML, loaded)
        injected = cli.inject_focus_capability(loaded, "abcdef")
        self.assertEqual(1, injected.count(b'name="cargento-focus"'))
        self.assertEqual(1, injected.count(b"</head>"))
        self.assertEqual(
            self.HTML, injected.replace(b'<meta name="cargento-focus" content="abcdef">', b"")
        )
        self.assertEqual(
            "react-" + hashlib.sha256(self.HTML).hexdigest()[:16], page.build_id("react")
        )

    def test_missing_or_corrupt_required_files_refuse_without_fallback(self) -> None:
        for name in ("react.html", "react.integrity.json", "react-licenses.txt"):
            with self.subTest(name=name):
                self.write_package(self.HTML)
                (self.root / name).unlink()
                with self.assertRaises((OSError, RuntimeError)):
                    page.load_frontend_page("react")
                self.write_package(self.HTML)
                (self.root / name).write_bytes(b"corrupt")
                with self.assertRaises((OSError, RuntimeError)):
                    page.load_frontend_page("react")

    def test_rehashed_ambiguous_head_or_existing_capability_refuses(self) -> None:
        for html in (
            self.HTML.replace(b"</head>", b"</head></head>"),
            self.HTML.replace(b"</head>", b"</HEAD>"),
            self.HTML.replace(b"</head>", b'<meta name="cargento-focus" content="dead"></head>'),
            self.HTML.replace(b"\n", b"\r\n"),
            self.HTML + b"\xff",
        ):
            with self.subTest(html=html):
                self.write_package(html)
                with self.assertRaises(RuntimeError):
                    page.load_frontend_page("react")

    def test_head_literal_in_comment_script_or_data_cannot_impersonate_real_head_end(self) -> None:
        for literal in (
            b"<!-- </head> -->",
            b'<script>const literal="</head>";</script>',
            b"<script src=\"data:text/javascript,console.log('</head>')\"></script>",
        ):
            with self.subTest(literal=literal):
                html = self.HTML.replace(b"</head>", literal + b"</HEAD>")
                self.write_package(html)
                with self.assertRaises(RuntimeError):
                    page.load_frontend_page("react")

    def test_unicode_multiline_prefix_keeps_actual_head_injection_position(self) -> None:
        html = self.HTML.replace(b"<html>", "\n<!-- Ω🙂 -->\n<html>\n".encode())
        self.write_package(html)
        loaded = page.load_frontend_page("react")
        self.assertEqual(html, loaded)
        meta = b'<meta name="cargento-focus" content="abcdef">'
        self.assertEqual(
            html.replace(b"</head>", meta + b"</head>"),
            cli.inject_focus_capability(loaded, "abcdef"),
        )

    def test_wrong_schema_typed_size_and_path_cannot_redirect_loader(self) -> None:
        for key, value in (
            ("bytes", True),
            ("bytes", len(self.HTML) + 1),
            ("file", "../index.html"),
            ("sha256", "0" * 64),
        ):
            with self.subTest(key=key, value=value):
                self.write_package(self.HTML)
                self.metadata["document"][key] = value
                self.write_metadata()
                with self.assertRaises(RuntimeError):
                    page.load_frontend_page("react")
        self.write_package(self.HTML)
        self.metadata["unexpected"] = "not accepted"
        self.write_metadata()
        with self.assertRaises(RuntimeError):
            page.load_frontend_page("react")

    def test_react_is_the_default_and_the_choice_is_frozen_per_process(self) -> None:
        parser = cli.build_parser()
        default = parser.parse_args([])
        self.assertEqual("react", default.frontend)
        self.assertEqual("react", runtime_config.DEFAULT_FRONTEND)
        config, _ = cli.build_runtime(default, started=1)
        self.assertEqual("react", config.frontend)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.frontend = "legacy"  # type: ignore[misc]  # exercise frozen-field refusal
        # A programmatic caller that names no renderer gets the same one as the CLI, so
        # the default is stated once rather than once per entry point.
        self.assertEqual("react", make_runtime()[0].frontend)

    def test_no_loader_defaults_a_renderer_so_a_fallback_cannot_pick_the_old_one(self) -> None:
        import inspect  # noqa: PLC0415

        for function in (page.load_frontend_page, page.build_id, cli.load_frontend_page):
            with self.subTest(function=function.__qualname__):
                parameter = inspect.signature(function).parameters["mode"]
                self.assertIs(inspect.Parameter.empty, parameter.default)
                with self.assertRaises(TypeError):
                    function()  # type: ignore[call-arg]  # the missing mode is the subject

    def test_legacy_is_the_explicit_process_level_rollback(self) -> None:
        parser = cli.build_parser()
        selected = parser.parse_args(["--frontend", "legacy"])
        config, _ = cli.build_runtime(selected, started=1)
        self.assertEqual("legacy", config.frontend)
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            parser.parse_args(["--frontend", "next"])
        with self.assertRaises(ValueError):
            runtime_config.build_runtime_config(
                environ={"HOME": "/nonexistent-cargento-test"},
                platform_name="linux",
                os_name="posix",
                launcher_path=Path("server.py"),
                frontend="next",
            )

    def test_the_detached_child_inherits_the_selection_whichever_way_it_went(self) -> None:
        # Always forwarded, including the default: a respawn that relied on the child's
        # own default would change renderer the day the default moves again.
        parser = cli.build_parser()
        for chosen in ("react", "legacy"):
            with self.subTest(chosen=chosen):
                selected = parser.parse_args(["--frontend", chosen, "--daemon"])
                config, _ = cli.build_runtime(selected, started=1)
                argv = lifecycle.spawn_argv(config, selected)
                self.assertEqual(chosen, argv[argv.index("--frontend") + 1])
                self.assertEqual(1, argv.count("--frontend"))
                self.assertNotIn("--daemon", argv)
        omitted = parser.parse_args(["--daemon"])
        config, _ = cli.build_runtime(omitted, started=1)
        argv = lifecycle.spawn_argv(config, omitted)
        self.assertEqual("react", argv[argv.index("--frontend") + 1])
        child = parser.parse_args(argv[2:])
        self.assertEqual("react", child.frontend)

    def test_no_environment_variable_or_stored_setting_selects_the_renderer(self) -> None:
        config, _ = cli.build_runtime(cli.build_parser().parse_args([]), started=1)
        for name in ("CARGENTO_FRONTEND", "CARGENTO_RENDERER", "FRONTEND"):
            with self.subTest(name=name), mock.patch.dict(os.environ, {name: "legacy"}):
                again, _ = cli.build_runtime(cli.build_parser().parse_args([]), started=1)
                self.assertEqual(config.frontend, again.frontend)

    def test_development_frontend_needs_react_so_the_rollback_refuses_it(self) -> None:
        parser = cli.build_parser()
        manifest = ["--frontend-dev-manifest", "ticket.json"]
        # React is now the default, so the flag alone satisfies the renderer half of the check.
        cli.validate_frontend_args(parser, parser.parse_args(manifest))
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            cli.validate_frontend_args(
                parser, parser.parse_args(["--frontend", "legacy", *manifest])
            )

    def test_bad_selected_artifact_fails_before_server_or_daemon_setup(self) -> None:
        (self.root / "react.html").unlink()
        for argv in (["--frontend", "react"], []):
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(1, cli.main([*argv, "--no-events", "--daemon"]))
                self.assertIn("cannot load frontend assets", stderr.getvalue())

    def test_a_broken_default_build_says_how_to_roll_back_and_never_falls_back(self) -> None:
        (self.root / "react.html").unlink()
        legacy_loads: list[str] = []
        real = page.load_frontend_page

        def spy(mode: str = "legacy") -> bytes:
            legacy_loads.append(mode)
            return real(mode)

        stderr = io.StringIO()
        with mock.patch.object(page, "load_frontend_page", spy), redirect_stderr(stderr):
            self.assertEqual(1, cli.main(["--no-events"]))
        self.assertEqual(["react"], legacy_loads)
        self.assertIn("--frontend legacy", stderr.getvalue())

    def test_a_broken_legacy_build_does_not_offer_itself_as_the_rollback(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(page, "WEB_DIR", self.root),
            redirect_stderr(stderr),
        ):
            self.assertEqual(1, cli.main(["--frontend", "legacy", "--no-events"]))
        self.assertIn("cannot load frontend assets", stderr.getvalue())
        self.assertNotIn("--frontend legacy", stderr.getvalue())

    def test_duplicate_metadata_keys_and_bad_provenance_refuse(self) -> None:
        self.metadata["provenance"]["sources"] = [
            {"file": "../private-session", "sha256": "0" * 64}
        ]
        self.write_metadata()
        with self.assertRaises(RuntimeError):
            page.load_frontend_page("react")
        self.write_package(self.HTML)
        encoded = json.dumps(self.metadata).replace('"format": 1', '"format": 1, "format": 1')
        (self.root / "react.integrity.json").write_text(encoded, encoding="utf-8")
        with self.assertRaises(RuntimeError):
            page.load_frontend_page("react")

    def test_optional_terminal_inventory_checks_fixed_local_assets(self) -> None:
        (self.root / "vendor").mkdir()
        terminal = {}
        for kind, name in (("javascript", "xterm.js"), ("stylesheet", "xterm.css")):
            payload = b"synthetic asset\n"
            (self.root / "vendor" / name).write_bytes(payload)
            terminal[kind] = {
                "file": "vendor/" + name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        self.metadata["optionalTerminal"] = terminal
        self.write_metadata()
        self.assertEqual(self.HTML, page.load_frontend_page("react"))
        (self.root / "vendor/xterm.js").write_bytes(b"corrupt")
        with self.assertRaises(RuntimeError):
            page.load_frontend_page("react")

    def test_two_applications_publish_own_mode_and_loaded_page_identity(self) -> None:
        applications = []
        for mode, html in (("legacy", b"legacy fixed bytes"), ("react", self.HTML)):
            config, state = make_runtime(
                frontend=mode,
                usage_fetch_enabled=False,
                history_enabled=False,
                annotations_enabled=False,
            )
            applications.append(
                aggregate.Application(
                    config,
                    state,
                    (),
                    native_notifier=lambda _: "",
                    popup_notifier=lambda *_: None,
                    diagnostic_sink=lambda _: None,
                    frontend_page_bytes=html,
                )
            )
        for app, mode, html in zip(
            applications, ("legacy", "react"), (b"legacy fixed bytes", self.HTML), strict=True
        ):
            result = app.collect(show_all=False)
            self.assertEqual(mode, result["frontend"])
            prefix = "react-" if mode == "react" else ""
            self.assertEqual(prefix + hashlib.sha256(html).hexdigest()[:16], result["build"])


class LegacyAssetGuardTest(unittest.TestCase):
    """The rollback has no integrity metadata, so an emptied part must not serve a page.

    Measured on a scratch plugin: emptying `next-cockpit.js` served HTTP 200 with a
    908,989 byte page and no message, while a deleted part refused. Full integrity for
    the legacy assets is deferred to its retirement; this only closes the silent case.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cargento-legacy-guard-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(
            page.WEB_DIR,
            self.root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("react*", "vendor", "__pycache__"),
        )
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(page, "WEB_DIR", self.root).start()

    def test_the_untouched_copy_still_assembles(self) -> None:
        self.assertTrue(page.load_frontend_page("legacy"))

    def test_an_empty_or_blank_script_part_refuses_by_name(self) -> None:
        for name in page.APP_PARTS:
            for blank in ("", " \n\t\n"):
                with self.subTest(part=name, blank=blank):
                    original = (self.root / name).read_bytes()
                    (self.root / name).write_text(blank, encoding="utf-8")
                    try:
                        with self.assertRaisesRegex(RuntimeError, f"{name} is empty"):
                            page.load_frontend_page("legacy")
                    finally:
                        (self.root / name).write_bytes(original)

    def test_the_launcher_refuses_loudly_and_does_not_serve_the_react_page_instead(self) -> None:
        (self.root / "next-cockpit.js").write_text("", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(1, cli.main(["--frontend", "legacy", "--no-events"]))
        self.assertIn("cannot load frontend assets", stderr.getvalue())
        self.assertIn("next-cockpit.js is empty", stderr.getvalue())


class InstalledFrontendTest(unittest.TestCase):
    @staticmethod
    def child_environment(root: Path) -> dict[str, str]:
        env = {
            "PATH": str(root / "no-node"),
            "HOME": str(root / "home"),
            "USERPROFILE": str(root / "home"),
            "CARGENTO_HOME": str(root / "state"),
            "PYTHONNOUSERSITE": "1",
        }
        if os.name == "nt":
            env.update(
                {
                    key: value
                    for key, value in os.environ.items()
                    if key.upper() in {"SYSTEMROOT", "WINDIR"}
                }
            )
        return env

    def test_windows_loader_environment_survives_without_host_data_or_executables(self) -> None:
        helper = Path(__file__).resolve().parents[4] / "frontend/test/installed_backend.py"
        spec = importlib.util.spec_from_file_location("installed_backend_environment", helper)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            callable(getattr(module, "isolated_environment", None)),
            "OS loader environment isolation is missing",
        )
        scratch = Path("/owned-fixture")
        hostile = {
            "SystemRoot": "C:\\Windows",
            "windir": "C:\\Windows",
            "HOME": "/real-user",
            "USERPROFILE": "/real-user",
            "PATH": "/real-node-bin",
            "APPDATA": "/real-agent-data",
            "LOCALAPPDATA": "/real-agent-data",
            "CODEX_HOME": "/real-codex",
            "CLAUDE_CONFIG_DIR": "/real-claude",
            "PI_CODING_AGENT_DIR": "/real-pi",
            "XDG_DATA_HOME": "/real-data",
            "OPENAI_API_KEY": "synthetic-secret",
            "NODE_AUTH_TOKEN": "synthetic-secret",
        }
        expected = {
            "HOME": str(scratch),
            "USERPROFILE": str(scratch),
            "CARGENTO_HOME": str(scratch / "state"),
            "PATH": str(scratch / "no-executables"),
            "SYSTEMROOT": "C:\\Windows",
            "WINDIR": "C:\\Windows",
        }
        self.assertEqual(expected, module.isolated_environment(scratch, hostile, os_name="nt"))
        self.assertEqual(
            {k: v for k, v in expected.items() if k not in {"SYSTEMROOT", "WINDIR"}},
            module.isolated_environment(scratch, hostile, os_name="posix"),
        )

    @staticmethod
    def close_owned_process(proc: subprocess.Popen[str]) -> None:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()

    def assert_terminal_fixture(
        self, conn: http.client.HTTPConnection, ready: dict[str, Any], plugin: Path
    ) -> None:
        self.assertIn(":console", ready["terminal_fragment"])
        conn.request(
            "GET",
            "/api/interaction/origin?harness=codex&sid=disposable-tmux-origin%3A1",
        )
        response = conn.getresponse()
        origin = json.loads(response.read())
        self.assertEqual("registered", origin["state"])
        self.assertEqual("not-exposed", origin["keyboard_input"])
        for asset in ("xterm.js", "xterm.css"):
            conn.request(
                "GET",
                "/assets/" + asset,
                headers={"Sec-Fetch-Site": "same-origin"},
            )
            response = conn.getresponse()
            self.assertEqual(200, response.status)
            self.assertEqual(
                (plugin / "skills/cargento/cargento_runtime/web/vendor" / asset).read_bytes(),
                response.read(),
            )
            conn.request(
                "GET",
                "/assets/" + asset,
                headers={"Sec-Fetch-Site": "cross-site"},
            )
            response = conn.getresponse()
            self.assertEqual(403, response.status)
            response.read()

    def test_selected_corruption_fails_before_bind_and_recovery_ignores_assets(self) -> None:
        repo = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory(prefix="cargento-installed-corrupt-") as temporary:
            root = Path(temporary)
            plugin = root / "plugin"
            shutil.copytree(
                repo / "cargento", plugin, ignore=shutil.ignore_patterns("tests", "__pycache__")
            )
            env = self.child_environment(root)
            launcher = plugin / "skills/cargento/server.py"
            web = plugin / "skills/cargento/cargento_runtime/web"
            # Hold the candidate port ourselves: a startup that reaches bind
            # would report a port collision instead of the selected asset error.
            with socket.socket() as held:
                held.bind(("127.0.0.1", 0))
                port = str(held.getsockname()[1])
                for name in ("react.html", "react.integrity.json", "react-licenses.txt"):
                    original = (web / name).read_bytes()
                    for mutation in (None, b"corrupt"):
                        with self.subTest(name=name, mutation=mutation):
                            if mutation is None:
                                (web / name).unlink()
                            else:
                                (web / name).write_bytes(mutation)
                            result = subprocess.run(
                                [
                                    sys.executable,
                                    str(launcher),
                                    "--frontend",
                                    "react",
                                    "--daemon",
                                    "--port",
                                    port,
                                ],
                                capture_output=True,
                                text=True,
                                env=env,
                                timeout=10,
                                check=False,
                            )
                            self.assertEqual(1, result.returncode)
                            self.assertIn("cannot load frontend assets", result.stderr)
                            self.assertFalse((root / "state").exists())
                            (web / name).write_bytes(original)
            (web / "react.html").unlink()
            for option in ("--help", "--status", "--stop"):
                result = subprocess.run(
                    [sys.executable, str(launcher), "--frontend", "react", "--port", port, option],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=10,
                    check=False,
                )
                self.assertIn(result.returncode, (0, 1))
                self.assertNotIn("cannot load frontend assets", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_the_installed_launcher_serves_react_by_default_and_legacy_on_request(self) -> None:
        # The real launcher, not the fixture helper: this is what a reader types. Node is
        # absent from PATH and the home is empty, so the page can only come from the
        # installed copy's own files and no real store is read.
        repo = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory(prefix="cargento-installed-default-") as temporary:
            root = Path(temporary)
            plugin = root / "plugin"
            shutil.copytree(
                repo / "cargento", plugin, ignore=shutil.ignore_patterns("tests", "__pycache__")
            )
            env = self.child_environment(root)
            launcher = plugin / "skills/cargento/server.py"
            react_page = (plugin / "skills/cargento/cargento_runtime/web/react.html").read_bytes()
            quiet = ("--no-usage", "--no-git", "--no-focus", "--no-reach", "--no-history")
            for label, flags, detach, expected in (
                ("default", (), False, "react"),
                ("rollback", ("--frontend", "legacy"), False, "legacy"),
                ("default detached", (), True, "react"),
                ("rollback detached", ("--frontend", "legacy"), True, "legacy"),
            ):
                with self.subTest(label=label):
                    port = self.free_port()
                    argv = [
                        sys.executable,
                        str(launcher),
                        "--port",
                        str(port),
                        *quiet,
                        *flags,
                    ]
                    stop = [sys.executable, str(launcher), "--port", str(port), "--stop"]
                    proc: subprocess.Popen[str] | None = None
                    try:
                        if detach:
                            started = subprocess.run(
                                [*argv, "--daemon"],
                                capture_output=True,
                                text=True,
                                env=env,
                                timeout=60,
                                check=False,
                            )
                            self.assertEqual(0, started.returncode, started.stdout + started.stderr)
                        else:
                            proc = subprocess.Popen(
                                argv,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=env,
                                text=True,
                            )
                        body, payload = self.fetch_page_and_data(port, proc)
                        self.assertEqual(expected, payload["frontend"])
                        self.assertEqual(expected == "react", body == react_page)
                        prefix = "react-" if expected == "react" else ""
                        self.assertEqual(
                            prefix + hashlib.sha256(body).hexdigest()[:16], payload["build"]
                        )
                    finally:
                        subprocess.run(
                            stop,
                            capture_output=True,
                            env=env,
                            timeout=30,
                            check=False,
                        )
                        if proc is not None:
                            self.close_owned_process(proc)

    def test_a_running_dashboard_keeps_its_renderer_and_a_second_start_says_so(self) -> None:
        # A daemon started under the old default keeps serving the legacy page after an
        # upgrade, and the rollback flag does nothing on a port that already runs React.
        # Neither may be silent, and neither may send the reader to the wrong page.
        repo = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory(prefix="cargento-installed-occupied-") as temporary:
            root = Path(temporary)
            plugin = root / "plugin"
            shutil.copytree(
                repo / "cargento", plugin, ignore=shutil.ignore_patterns("tests", "__pycache__")
            )
            env = self.child_environment(root)
            launcher = str(plugin / "skills/cargento/server.py")
            quiet = ("--no-usage", "--no-git", "--no-focus", "--no-reach", "--no-history")
            for running, asked in (("legacy", "react"), ("react", "legacy")):
                with self.subTest(running=running, asked=asked):
                    port = self.free_port()
                    base = [sys.executable, launcher, "--port", str(port), *quiet]

                    def run(
                        *extra: str, base: list[str] = base
                    ) -> subprocess.CompletedProcess[str]:
                        return subprocess.run(
                            [*base, *extra],
                            capture_output=True,
                            text=True,
                            env=env,
                            timeout=60,
                            check=False,
                        )

                    try:
                        started = run("--frontend", running, "--daemon")
                        self.assertEqual(0, started.returncode, started.stdout + started.stderr)
                        status = run("--status")
                        self.assertEqual(0, status.returncode, status.stdout + status.stderr)
                        self.assertIn(f"frontend {running}", status.stdout)
                        for detach in (("--daemon",), ()):
                            refused = run("--frontend", asked, *detach)
                            text = refused.stdout + refused.stderr
                            self.assertEqual(1, refused.returncode, text)
                            self.assertIn(running, text)
                            self.assertIn("--stop", text)
                            self.assertIn("start again with the flag you want", text)
                            self.assertNotIn("use it", text)
                        # Same renderer as the occupant: using it is the right answer.
                        same = run("--frontend", running)
                        self.assertEqual(1, same.returncode)
                        self.assertIn("use it", same.stdout + same.stderr)
                    finally:
                        run("--stop")

    @staticmethod
    def free_port() -> int:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    @staticmethod
    def fetch_page_and_data(
        port: int, proc: subprocess.Popen[str] | None
    ) -> tuple[bytes, dict[str, Any]]:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if proc is not None and proc.poll() is not None:
                assert proc.stderr is not None
                raise AssertionError(f"launcher exited early: {proc.stderr.read()}")
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                try:
                    conn.request("GET", "/")
                    body = conn.getresponse().read()
                    conn.request("GET", "/api/data")
                    payload = json.loads(conn.getresponse().read())
                finally:
                    conn.close()
            except (OSError, ValueError):
                time.sleep(0.1)
                continue
            return body, payload
        raise AssertionError(f"nothing answered on port {port}")

    def test_installed_copy_serves_both_modes_without_node_and_cleans_up_on_eof(self) -> None:
        repo = Path(__file__).resolve().parents[4]
        helper = repo / "frontend/test/installed_backend.py"
        self.assertTrue(helper.is_file(), "installed-copy backend helper is missing")
        with tempfile.TemporaryDirectory(prefix="cargento-installed-react-") as temporary:
            root = Path(temporary)
            plugin = root / "plugin"
            shutil.copytree(
                repo / "cargento", plugin, ignore=shutil.ignore_patterns("tests", "__pycache__")
            )
            env = self.child_environment(root)
            for mode in ("legacy", "react"):
                with self.subTest(mode=mode):
                    focus_args = (
                        ["--focus-token", "abcdef"] if mode == "react" else ["--terminal-fixture"]
                    )
                    proc = subprocess.Popen(
                        [
                            sys.executable,
                            str(helper),
                            "--plugin-root",
                            str(plugin),
                            "--frontend",
                            mode,
                            "--port",
                            "0",
                            *focus_args,
                        ],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env,
                        text=True,
                    )
                    try:
                        assert proc.stdout is not None
                        ready_line = proc.stdout.readline()
                        if not ready_line:
                            assert proc.stderr is not None
                            self.fail(proc.stderr.read())
                        self.assertTrue(
                            ready_line, "installed helper did not accept the smoke contract"
                        )
                        ready = json.loads(ready_line)
                        self.assertTrue(ready["ready"])
                        self.assertEqual(mode, ready["frontend"])
                        self.assertTrue(Path(ready["runtime"]).is_relative_to(plugin.resolve()))
                        conn = http.client.HTTPConnection("127.0.0.1", ready["port"], timeout=5)
                        conn.request("GET", "/")
                        response = conn.getresponse()
                        body = response.read()
                        if mode == "react":
                            self.assertEqual(
                                1, body.count(b'<meta name="cargento-focus" content="abcdef">')
                            )
                        self.assertEqual(200, response.status)
                        conn.request(
                            "GET", "/?frontend=" + ("legacy" if mode == "react" else "react")
                        )
                        response = conn.getresponse()
                        self.assertEqual(body, response.read())
                        conn.request("GET", "/api/data")
                        response = conn.getresponse()
                        payload = json.loads(response.read())
                        if mode == "legacy":
                            self.assert_terminal_fixture(conn, ready, plugin)
                        conn.close()
                        self.assertEqual(mode, payload["frontend"])
                        prefix = "react-" if mode == "react" else ""
                        self.assertEqual(
                            prefix
                            + hashlib.sha256(
                                body.replace(b'<meta name="cargento-focus" content="abcdef">', b"")
                            ).hexdigest()[:16],
                            payload["build"],
                        )
                        assert proc.stdin is not None
                        proc.stdin.close()
                        proc.wait(timeout=10)
                        self.assertEqual(0, proc.returncode)
                    finally:
                        self.close_owned_process(proc)


if __name__ == "__main__":
    unittest.main()
