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
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import aggregate, cli, lifecycle
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

    def test_cli_freezes_explicit_selection_and_windows_respawn_carries_it(self) -> None:
        parser = cli.build_parser()
        default = parser.parse_args([])
        self.assertEqual("legacy", default.frontend)
        selected = parser.parse_args(["--frontend", "react", "--daemon"])
        config, _ = cli.build_runtime(selected, started=1)
        self.assertEqual("react", config.frontend)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.frontend = "legacy"  # type: ignore[misc]  # exercise frozen-field refusal
        argv = lifecycle.spawn_argv(config, selected)
        self.assertEqual("react", argv[argv.index("--frontend") + 1])
        self.assertNotIn("--daemon", argv)
        config, _ = cli.build_runtime(default, started=1)
        self.assertNotIn("--frontend", lifecycle.spawn_argv(config, default))

    def test_bad_selected_artifact_fails_before_server_or_daemon_setup(self) -> None:
        (self.root / "react.html").unlink()
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(1, cli.main(["--frontend", "react", "--no-events", "--daemon"]))
        self.assertIn("cannot load frontend assets", stderr.getvalue())

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
