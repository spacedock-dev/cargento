"""End-to-end tests for the POSIX Cargento installer."""

from __future__ import annotations

import http.client
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time
import unittest
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/build_release_assets.py"


@unittest.skipUnless(os.name == "posix", "the phase-one installer is POSIX-only")
class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="cargento-installer-")
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.assets = self.root / "assets"
        build = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--tag",
                "v1.2.3",
                "--output-dir",
                str(self.assets),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        self.installer = self.assets / "install.sh"
        self.home = self.root / "home"
        self.home.mkdir()
        self.data_root = self.home / "data/cargento"
        self.bin_dir = self.home / "bin"
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.claude_state = self.root / "claude-state.json"
        self.claude_log = self.root / "claude.log"
        self._make_tools()
        self.environment = {
            "HOME": str(self.home),
            "PATH": str(self.tools),
            "CARGENTO_DATA_ROOT": str(self.data_root),
            "CARGENTO_BIN_DIR": str(self.bin_dir),
            "CARGENTO_TEST_ASSET_DIR": str(self.assets),
            "FAKE_CLAUDE_STATE": str(self.claude_state),
            "FAKE_CLAUDE_LOG": str(self.claude_log),
        }

    def _write_executable(self, name: str, body: str) -> None:
        path = self.tools / name
        path.write_text(body)
        path.chmod(0o755)

    def _link_tool(self, name: str) -> None:
        target = shutil.which(name)
        if target is None:
            self.fail(f"test host must provide {name}")
        (self.tools / name).symlink_to(target)

    def _make_tools(self) -> None:
        for name in ("gzip", "tar", "mktemp", "mkdir", "rm", "ln", "mv", "chmod"):
            self._link_tool(name)
        hash_tool = "sha256sum" if shutil.which("sha256sum") else "shasum"
        self._link_tool(hash_tool)
        (self.tools / "python3").symlink_to(sys.executable)
        self._write_executable(
            "curl",
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import os
                import pathlib
                import shutil
                import sys

                output_index = sys.argv.index("-o")
                output = pathlib.Path(sys.argv[output_index + 1])
                source = pathlib.Path(os.environ["CARGENTO_TEST_ASSET_DIR"]) / sys.argv[output_index - 1].rsplit("/", 1)[-1]
                shutil.copyfile(source, output)
                """
            ),
        )
        self._write_executable(
            "claude",
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import json
                import os
                import pathlib
                import sys

                state_path = pathlib.Path(os.environ["FAKE_CLAUDE_STATE"])
                log_path = pathlib.Path(os.environ["FAKE_CLAUDE_LOG"])
                if state_path.exists():
                    state = json.loads(state_path.read_text())
                else:
                    state = {{"marketplaces": [], "plugins": []}}
                command = sys.argv[1:]
                with log_path.open("a") as log:
                    log.write(" ".join(command) + "\\n")
                if command == ["plugin", "marketplace", "list", "--json"]:
                    print(json.dumps(state["marketplaces"]))
                elif command == ["plugin", "list", "--json"]:
                    print(json.dumps(state["plugins"]))
                elif command == ["plugin", "marketplace", "add", "spacedock-dev/marketplace"]:
                    if any(item["name"] == "spacedock" for item in state["marketplaces"]):
                        raise SystemExit("duplicate marketplace add")
                    state["marketplaces"].append(
                        {{"name": "spacedock", "source": "github", "repo": "spacedock-dev/marketplace"}}
                    )
                elif command == ["plugin", "install", "--scope", "user", "cargento@spacedock"]:
                    marker = os.environ.get("FAKE_CLAUDE_FAIL_ONCE")
                    if marker and not pathlib.Path(marker).exists():
                        pathlib.Path(marker).touch()
                        raise SystemExit(7)
                    if any(
                        item["id"] == "cargento@spacedock" and item["scope"] == "user"
                        for item in state["plugins"]
                    ):
                        raise SystemExit("duplicate plugin install")
                    # Deliberately lags runtime 1.2.3. Marketplace selection is authoritative.
                    state["plugins"].append(
                        {{
                            "id": "cargento@spacedock",
                            "version": "0.4.2",
                            "scope": "user",
                            "enabled": True,
                        }}
                    )
                elif command == ["plugin", "enable", "--scope", "user", "cargento@spacedock"]:
                    plugin = next(
                        (
                            item
                            for item in state["plugins"]
                            if item["id"] == "cargento@spacedock" and item["scope"] == "user"
                        ),
                        None,
                    )
                    if plugin is None:
                        raise SystemExit("cannot enable absent plugin")
                    plugin["enabled"] = True
                else:
                    raise SystemExit("unexpected claude command: " + " ".join(command))
                state_path.write_text(json.dumps(state))
                """
            ),
        )

    def run_installer(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = self.environment.copy()
        if environment:
            env.update(environment)
        return subprocess.run(
            ["/bin/sh", str(self.installer), *arguments],
            cwd=self.root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_preflight_failure(
        self,
        result: subprocess.CompletedProcess[str],
        message: str,
    ) -> None:
        self.assertEqual(
            (
                result.returncode != 0,
                message in result.stderr,
                self.data_root.exists(),
                self.bin_dir.exists(),
                self.claude_state.exists(),
            ),
            (True, True, False, False, False),
        )

    def test_requires_exactly_the_supported_plugin_selector_before_mutation(self) -> None:
        for arguments in (
            (),
            ("--plugin",),
            ("--plugin", "codex"),
            ("--plugin", "claude", "--plugin", "claude"),
            ("--unknown",),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_installer(*arguments)
                self.assertEqual(
                    (
                        result.returncode,
                        "Usage: cargento-install --plugin claude" in result.stderr,
                        self.data_root.exists(),
                        self.bin_dir.exists(),
                        self.claude_state.exists(),
                    ),
                    (64, True, False, False, False),
                )

    def test_preflight_rejects_old_python_without_mutation(self) -> None:
        (self.tools / "python3").unlink()
        self._write_executable(
            "python3",
            f"#!{sys.executable}\nimport sys\nprint('3 10')\n",
        )
        old_python = self.run_installer("--plugin", "claude")
        self.assert_preflight_failure(old_python, "Python 3.11+")

    def test_preflight_rejects_missing_claude_without_mutation(self) -> None:
        (self.tools / "claude").unlink()
        missing_claude = self.run_installer("--plugin", "claude")
        self.assert_preflight_failure(missing_claude, "required command not found: claude")

    def test_preflight_rejects_missing_python_without_mutation(self) -> None:
        (self.tools / "python3").unlink()

        result = self.run_installer("--plugin", "claude")
        self.assert_preflight_failure(result, "required command not found: python3")

    def test_preflight_rejects_missing_download_tool_without_mutation(self) -> None:
        (self.tools / "curl").unlink()

        result = self.run_installer("--plugin", "claude")
        self.assert_preflight_failure(result, "required command not found: curl")

    def test_preflight_rejects_missing_gzip_without_mutation(self) -> None:
        (self.tools / "gzip").unlink()

        result = self.run_installer("--plugin", "claude")
        self.assert_preflight_failure(result, "required command not found: gzip")

    def test_preflight_rejects_missing_hash_tool_without_mutation(self) -> None:
        for name in ("sha256sum", "shasum"):
            (self.tools / name).unlink(missing_ok=True)

        result = self.run_installer("--plugin", "claude")
        self.assert_preflight_failure(result, "required SHA-256 tool not found")

    def test_corrupt_archive_cannot_change_owned_install_paths(self) -> None:
        archive = self.assets / "cargento-runtime-1.2.3.tar.gz"
        archive.write_bytes(archive.read_bytes() + b"x")

        result = self.run_installer("--plugin", "claude")
        self.assert_preflight_failure(result, "checksum verification failed")

    def test_rejects_wrong_archive_layout_before_activation(self) -> None:
        archive = self.assets / "cargento-runtime-1.2.3.tar.gz"
        payload = self.root / "wrong.txt"
        payload.write_text("wrong")
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(payload, arcname="wrong.txt")
        checksum = sha256(archive.read_bytes()).hexdigest()
        (self.assets / f"{archive.name}.sha256").write_text(f"{checksum}  {archive.name}\n")

        result = self.run_installer("--plugin", "claude")
        self.assert_preflight_failure(result, "unexpected runtime archive layout")

    def test_rejects_unsafe_archive_members_before_activation(self) -> None:
        cases = (
            ("traversal", "../escape", tarfile.REGTYPE, ""),
            ("symlink", "cargento/link", tarfile.SYMTYPE, "skills/cargento/server.py"),
            ("hardlink", "cargento/hard", tarfile.LNKTYPE, "cargento/skills/cargento/server.py"),
            ("fifo", "cargento/pipe", tarfile.FIFOTYPE, ""),
        )
        for label, name, member_type, linkname in cases:
            with self.subTest(label=label):
                archive = self.assets / "cargento-runtime-1.2.3.tar.gz"
                with tarfile.open(archive, "w:gz") as bundle:
                    root = tarfile.TarInfo("cargento")
                    root.type = tarfile.DIRTYPE
                    bundle.addfile(root)
                    for required in (
                        "cargento/skills/cargento/server.py",
                        "cargento/.claude-plugin/plugin.json",
                    ):
                        body = b"{}\n"
                        member = tarfile.TarInfo(required)
                        member.size = len(body)
                        bundle.addfile(member, io.BytesIO(body))
                    hostile = tarfile.TarInfo(name)
                    hostile.type = member_type
                    hostile.linkname = linkname
                    if member_type == tarfile.REGTYPE:
                        hostile.size = 0
                    bundle.addfile(hostile, io.BytesIO(b""))
                checksum = sha256(archive.read_bytes()).hexdigest()
                (self.assets / f"{archive.name}.sha256").write_text(f"{checksum}  {archive.name}\n")

                result = self.run_installer("--plugin", "claude")

                self.assertEqual(
                    (
                        result.returncode != 0,
                        "unexpected runtime archive layout" in result.stderr,
                        self.data_root.exists(),
                        self.bin_dir.exists(),
                        self.claude_state.exists(),
                        (self.root / "escape").exists(),
                    ),
                    (True, True, False, False, False, False),
                )

    def test_installs_cli_and_lagging_marketplace_plugin_idempotently(self) -> None:
        shell_profile = self.home / ".zshrc"
        shell_profile.write_text("# preserved\n")

        first = self.run_installer("--plugin", "claude")
        second = self.run_installer("--plugin", "claude")

        current = self.data_root / "current"
        launcher = self.bin_dir / "cargento"
        if launcher.exists():
            diagnose = subprocess.run(
                [str(launcher), "--diagnose", "--json"],
                env=self.environment,
                check=False,
                capture_output=True,
                text=True,
            )
            launcher_body = launcher.read_text()
        else:
            diagnose = subprocess.CompletedProcess([], 127, "", "launcher missing")
            launcher_body = ""
        state = (
            json.loads(self.claude_state.read_text())
            if self.claude_state.exists()
            else {"marketplaces": [], "plugins": []}
        )
        log = self.claude_log.read_text().splitlines() if self.claude_log.exists() else []
        self.assertEqual(
            (
                first.returncode,
                second.returncode,
                "CLI: verified" in first.stdout,
                "Plugin (claude): verified" in first.stdout,
                f'export PATH="{self.bin_dir}:$PATH"' in first.stdout,
                shell_profile.read_text(),
                current.is_symlink(),
                os.readlink(current) if current.is_symlink() else None,
                diagnose.returncode,
                ".claude/plugins/cache" in launcher_body,
                state["marketplaces"],
                state["plugins"],
                log.count("plugin marketplace add spacedock-dev/marketplace"),
                log.count("plugin install --scope user cargento@spacedock"),
            ),
            (
                0,
                0,
                True,
                True,
                True,
                "# preserved\n",
                True,
                "releases/1.2.3",
                0,
                False,
                [
                    {
                        "name": "spacedock",
                        "source": "github",
                        "repo": "spacedock-dev/marketplace",
                    }
                ],
                [
                    {
                        "id": "cargento@spacedock",
                        "version": "0.4.2",
                        "scope": "user",
                        "enabled": True,
                    }
                ],
                1,
                1,
            ),
            first.stderr or second.stderr or diagnose.stderr,
        )

    def test_installed_launcher_serves_until_sigint(self) -> None:
        install = self.run_installer("--plugin", "claude")
        launcher = self.bin_dir / "cargento"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        process = subprocess.Popen(
            [str(launcher), "--port", str(port)],
            env=self.environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def stop_process() -> None:
            if process.poll() is None:
                process.kill()

        self.addCleanup(stop_process)
        payload: dict[str, object] | None = None
        for _ in range(100):
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                connection.request("GET", "/api/data")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                break
            except OSError:
                time.sleep(0.05)
        process.send_signal(signal.SIGINT)
        process.wait(timeout=5)

        self.assertEqual(
            (
                install.returncode,
                isinstance(payload, dict),
                process.poll() is not None,
            ),
            (0, True, True),
            install.stderr,
        )

    def test_rejects_same_name_different_source_collision(self) -> None:
        self.claude_state.write_text(
            json.dumps(
                {
                    "marketplaces": [
                        {"name": "spacedock", "source": "github", "repo": "other/source"}
                    ],
                    "plugins": [],
                }
            )
        )

        result = self.run_installer("--plugin", "claude")

        self.assertEqual(
            (
                result.returncode != 0,
                "marketplace name collision" in result.stderr,
                "CLI: verified" in result.stdout,
                "Plugin (claude): failed" in result.stdout,
                "partial installation" in result.stderr,
            ),
            (True, True, True, True, True),
        )

    def test_enables_the_exact_plugin_identity_when_it_is_disabled(self) -> None:
        self.claude_state.write_text(
            json.dumps(
                {
                    "marketplaces": [
                        {
                            "name": "spacedock",
                            "source": "github",
                            "repo": "spacedock-dev/marketplace",
                        }
                    ],
                    "plugins": [
                        {
                            "id": "cargento@spacedock",
                            "version": "0.4.2",
                            "scope": "user",
                            "enabled": False,
                        }
                    ],
                }
            )
        )

        result = self.run_installer("--plugin", "claude")

        state = json.loads(self.claude_state.read_text()) if self.claude_state.exists() else {}
        plugins = state.get("plugins", [])
        self.assertEqual(
            (
                result.returncode,
                bool(plugins and plugins[0]["enabled"]),
                (
                    "plugin enable --scope user cargento@spacedock" in self.claude_log.read_text()
                    if self.claude_log.exists()
                    else False
                ),
            ),
            (0, True, True),
            result.stderr,
        )

    def test_installs_user_scope_when_only_project_scope_is_enabled(self) -> None:
        self.claude_state.write_text(
            json.dumps(
                {
                    "marketplaces": [
                        {
                            "name": "spacedock",
                            "source": "github",
                            "repo": "spacedock-dev/marketplace",
                        }
                    ],
                    "plugins": [
                        {
                            "id": "cargento@spacedock",
                            "version": "0.4.2",
                            "scope": "project",
                            "enabled": True,
                        }
                    ],
                }
            )
        )

        result = self.run_installer("--plugin", "claude")

        state = json.loads(self.claude_state.read_text()) if self.claude_state.exists() else {}
        user_plugins = [
            plugin
            for plugin in state.get("plugins", [])
            if plugin["id"] == "cargento@spacedock" and plugin["scope"] == "user"
        ]
        self.assertEqual(
            (
                result.returncode,
                len(user_plugins),
                bool(user_plugins and user_plugins[0]["enabled"]),
            ),
            (0, 1, True),
            result.stderr,
        )

    def test_upgrade_atomically_repoints_current_to_the_new_release(self) -> None:
        first = self.run_installer("--plugin", "claude")
        upgraded_assets = self.root / "upgraded-assets"
        build = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--tag",
                "v1.2.4",
                "--output-dir",
                str(upgraded_assets),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if build.returncode == 0:
            second = subprocess.run(
                ["/bin/sh", str(upgraded_assets / "install.sh"), "--plugin", "claude"],
                cwd=self.root,
                env={
                    **self.environment,
                    "CARGENTO_TEST_ASSET_DIR": str(upgraded_assets),
                },
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            second = subprocess.CompletedProcess([], 127, "", "asset build failed")
        current = self.data_root / "current"
        self.assertEqual(
            (
                first.returncode,
                build.returncode,
                second.returncode,
                os.readlink(current) if current.is_symlink() else None,
            ),
            (0, 0, 0, "releases/1.2.4"),
            first.stderr or build.stderr or second.stderr,
        )

    def test_partial_plugin_failure_keeps_cli_and_rerun_repairs_install(self) -> None:
        fail_marker = self.root / "fail-once"
        first = self.run_installer(
            "--plugin",
            "claude",
            environment={"FAKE_CLAUDE_FAIL_ONCE": str(fail_marker)},
        )

        launcher = self.bin_dir / "cargento"
        if launcher.exists():
            diagnose = subprocess.run(
                [str(launcher), "--diagnose", "--json"],
                env=self.environment,
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            diagnose = subprocess.CompletedProcess([], 127, "", "launcher missing")

        second = self.run_installer(
            "--plugin",
            "claude",
            environment={"FAKE_CLAUDE_FAIL_ONCE": str(fail_marker)},
        )
        recovery = (
            "curl -fsSL "
            '"https://github.com/spacedock-dev/cargento/releases/download/v1.2.3/install.sh" '
            "| sh -s -- --plugin claude"
        )
        self.assertEqual(
            (
                first.returncode != 0,
                "CLI: verified" in first.stdout,
                "Plugin (claude): failed" in first.stdout,
                "partial installation" in first.stderr,
                recovery in first.stderr,
                diagnose.returncode,
                second.returncode,
                "Plugin (claude): verified" in second.stdout,
            ),
            (True, True, True, True, True, 0, 0, True),
            first.stderr or diagnose.stderr or second.stderr,
        )
