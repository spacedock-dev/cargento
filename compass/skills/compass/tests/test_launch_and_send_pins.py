"""What the Intent and drift journey launches, sends and writes, pinned by test.

[SECURITY.md](SECURITY.md#what-launches-and-what-sends) tables each outbound or launch path,
the switch that stops it and the test that fails when it leaks. These are the pins that table
named as missing, and each was run against a local break of the behaviour it guards before it
was kept (the break is recorded in the pull request that added them):

- the page and its stylesheet make no absolute request;
- a press under either spelling of the model refusal starts no process and opens no socket;
- the runtime writes nothing into a harness store, over a whole press-to-copy journey.

The fourth, that the live monitor starts no Claude reading model, extends
`test_live_estimate.ALiveEstimateStartsNoModelTest` where it already lived.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import dataclasses
import hashlib
import http.client
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import mock

from compass_runtime import annotations as annotation_store
from compass_runtime import (
    cli,
    http_api,
    observer,
    project_context,
    reading_policy,
    reading_route,
)
from compass_runtime import reading as runtime_reading
from compass_runtime import reading_jobs as runtime_reading_jobs
from compass_runtime import supervise as runtime_supervise
from compass_runtime.state import build_runtime_state
from compass_runtime.web import page as frontend_page

from .support import SERVER_PATH, make_config, make_server, serve_until_closed
from .test_claude_checks import SHORT
from .test_copied_corrections import COPIED, NOW, _App

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import TracebackType

WEB = Path(http_api.__file__).parent / "web"

# A scheme that opens a connection, in the three spellings a bundle can carry it: plain,
# JSON-escaped (`https:\/\/`) and protocol-relative in an attribute or `url()`.
ABSOLUTE = re.compile(
    rb"(?:https?|wss?):(?://|\\/\\/)"
    rb"|(?:src|href|action|poster|srcset)\s*=\s*[\"']?//"
    rb"|url\(\s*[\"']?//",
    re.IGNORECASE,
)
URL = re.compile(rb"(?:https?|wss?)://[^\s\"'<>)\\]+", re.IGNORECASE)

# The vendored terminal is served at `/assets/xterm.js` and `/assets/xterm.css` beside the
# page, from bytes pinned by `react.integrity.json`. It names four absolute URLs and none is
# ever requested: two are XML namespace identifiers handed to `createElementNS`, one sits in
# an error string about secure contexts, and two are provenance links in the stylesheet's
# licence comments. The set is closed rather than prefix-matched, so a vendored upgrade that
# adds a fifth fails here and is read before it ships.
XTERM_INERT_URLS = {
    "xterm.js": {
        b"http://www.w3.org/1999/xhtml",
        b"http://www.w3.org/2000/svg",
        b"https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts",
    },
    "xterm.css": {
        b"https://github.com/chjj/term.js",
        b"http://bellard.org/jslinux/",
    },
}


class ThePageMakesNoAbsoluteRequestTest(unittest.TestCase):
    """The built page and its stylesheet name no host, so loading them cannot reach one.

    The served CSP is `frame-ancestors 'none'` alone (`http_api`, the document headers), so
    nothing in the browser would stop an absolute URL a dependency bundled. This is the guard.
    """

    def test_the_served_page_carries_no_absolute_url(self) -> None:
        page = frontend_page.load_frontend_page()
        self.assertEqual([], [m.group(0) for m in ABSOLUTE.finditer(page)][:5])
        # A bare `http` would also match an English sentence, so the stricter pattern above is
        # the guard and this is only the readable half: no URL of any scheme at all today.
        self.assertEqual([], URL.findall(page)[:5])

    def test_the_stylesheet_the_font_rows_are_built_from_carries_none(self) -> None:
        sheet = (WEB / "styles.css").read_bytes()
        self.assertEqual([], [m.group(0) for m in ABSOLUTE.finditer(sheet)][:5])
        # Its `url()` values are placeholders the build replaces with embedded data.
        for value in re.findall(rb"url\(\s*[\"']?([^\"')]+)", sheet):
            self.assertRegex(value.decode(), r"^\{\{COMPASS_FONT_[A-Z0-9_]+\}\}$")

    def test_the_vendored_terminal_names_only_the_inert_urls_it_always_has(self) -> None:
        for name, allowed in XTERM_INERT_URLS.items():
            with self.subTest(asset=name):
                found = set(URL.findall((WEB / "vendor" / name).read_bytes()))
                self.assertEqual(allowed, found)

    def test_the_pattern_sees_each_spelling_it_exists_to_catch(self) -> None:
        for sample in (
            b'<script src="https://cdn.example/x.js"></script>',
            b'<link href="//cdn.example/x.css">',
            b'a{background:url("//cdn.example/x.png")}',
            b"fetch('https:\\/\\/api.example\\/x')",
            b"new WebSocket('wss://host.example/s')",
        ):
            with self.subTest(sample=sample):
                self.assertTrue(ABSOLUTE.search(sample))
        self.assertFalse(ABSOLUTE.search(b'<a href="#top">top</a> a/b // a comment'))


def _protected(path: Any, roots: tuple[str, ...]) -> bool:
    try:
        resolved = os.path.realpath(os.fspath(path))
    except (TypeError, ValueError):
        return False
    return any(resolved == root or resolved.startswith(root + os.sep) for root in roots)


# The calls that change a path without opening it for writing.
_PATH_MUTATORS = (
    (os, ("replace", "rename", "remove", "unlink", "rmdir", "mkdir", "makedirs")),
    (os, ("utime", "chmod", "truncate", "symlink", "link")),
    (shutil, ("rmtree", "copy", "copy2", "copyfile", "move")),
)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


class write_guard:  # noqa: N801 - used as a context manager
    """Record, without stopping, every write-shaped call aimed under `roots`.

    A request handler swallows what it raises, so a guard that raised could be answered with
    a 500 and leave the test green. This one records and lets the call through, which keeps
    the second check (the before-and-after snapshot) independent of it. Reads are not touched,
    and neither are calls on a file descriptor, whose path is unknown by then: `os.open` is
    watched instead, as is the `open` every `Path` method goes through.
    """

    def __init__(self, roots: tuple[Path, ...]) -> None:
        self.roots = tuple(os.path.realpath(root) for root in roots)
        self.seen: list[str] = []
        self._stack = contextlib.ExitStack()

    def __enter__(self) -> list[str]:
        self._stack.__enter__()
        for target in (builtins, io):
            self._stack.enter_context(mock.patch.object(target, "open", self._opening(target.open)))
        self._stack.enter_context(mock.patch.object(os, "open", self._os_opening(os.open)))
        for owner, names in _PATH_MUTATORS:
            for name in names:
                self._stack.enter_context(
                    mock.patch.object(
                        owner, name, self._watching(owner, getattr(owner, name), name)
                    )
                )
        return self.seen

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self._stack.__exit__(kind, error, trace)

    def _opening(self, real: Any) -> Any:
        def wrapper(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if set(mode) & set("wax+") and _protected(file, self.roots):
                self.seen.append(f"open({os.fspath(file)!r}, {mode!r})")
            return real(file, mode, *args, **kwargs)

        return wrapper

    def _os_opening(self, real: Any) -> Any:
        def wrapper(path: Any, flags: int, *args: Any, **kwargs: Any) -> Any:
            if flags & _WRITE_FLAGS and _protected(path, self.roots):
                self.seen.append(f"os.open({os.fspath(path)!r}, {flags:#x})")
            return real(path, flags, *args, **kwargs)

        return wrapper

    def _watching(self, owner: Any, real: Any, name: str) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if any(_protected(a, self.roots) for a in args if isinstance(a, (str, bytes, Path))):
                self.seen.append(f"{owner.__name__}.{name}{args!r}")
            return real(*args, **kwargs)

        return wrapper


def snapshot(*roots: Path) -> dict[str, tuple[Any, ...]]:
    """Every entry under `roots`: kind, size, modified time and content hash."""
    found: dict[str, tuple[Any, ...]] = {}
    for root in roots:
        for path in sorted([root, *root.rglob("*")]):
            info = path.lstat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
            found[str(path)] = (path.is_dir(), info.st_size, info.st_mtime_ns, digest)
    return found


@contextlib.contextmanager
def unix_connects() -> Iterator[list[Any]]:
    """Record every connection to a local-domain socket, and let it proceed.

    The one documented way into a session that is not the reader's own terminal is a request
    written to the socket a Claude Code session listens on (the hand-off request, not built).
    That socket is a Unix-domain one, and nothing else Compass does opens one, so a connection
    of that family during a journey is a send channel appearing.
    """
    seen: list[Any] = []
    real = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> Any:
        if self.family == getattr(socket, "AF_UNIX", None):
            seen.append(address)
        return real(self, address)

    with mock.patch.object(socket.socket, "connect", connect):
        yield seen


class _Journey(_App):
    """A real Claude Code transcript, served, and the calls the page makes over it."""

    @contextlib.contextmanager
    def serving(self) -> Iterator[int]:
        httpd = make_server(application=self.app())
        thread = serve_until_closed(httpd)
        try:
            yield httpd.server_port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    @staticmethod
    def call(port: int, method: str, path: str, payload: Any = None) -> tuple[int, dict[str, Any]]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            body = None if payload is None else json.dumps(payload).encode()
            conn.request(method, path, body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read()
        finally:
            conn.close()
        try:
            return response.status, json.loads(raw)
        except ValueError:
            return response.status, {}

    @staticmethod
    def settle() -> None:
        for thread in [
            t
            for t in threading.enumerate()
            if t.name.startswith(runtime_reading_jobs.THREAD_PREFIX)
        ]:
            thread.join(timeout=10)

    def press(self, **over: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "harness": "claude",
            "sid": SHORT,
            "press": True,
            "observer_model": 1,
            "provider": "claude",
            "model": observer.CLAUDE_READING_MODEL,
            "allow": True,
            "words_destination": "",
        }
        body.update(over)
        return body

    @contextlib.contextmanager
    def machine(self, installed: tuple[str, ...] = ("claude", "codex")) -> Iterator[None]:
        """Both CLIs on PATH, and no destination the real machine's settings could name."""
        # A fresh open runner: a `serve` run earlier in this worker closes the shared one.
        with (
            mock.patch.object(runtime_supervise, "_SHUTDOWN", threading.Event()),
            mock.patch.object(
                shutil,
                "which",
                lambda name: f"/usr/local/bin/{name}" if name in installed else None,
            ),
            mock.patch.object(reading_route, "destination", lambda *_a, **_k: ""),
        ):
            yield


class TheJourneyWritesNothingIntoAHarnessStoreTest(_Journey):
    """The invariant is read-only against harness stores, and nothing but absence held it.

    Two checks run over one journey, because each is blind where the other sees: a snapshot of
    the store before and after catches any write whatever made it, a subprocess included, and
    a write that restores what it changed; the guard names the call that did it. The journey is
    every route the Intent and drift page uses on a session: the board, the project context,
    the end-of-session observation, the typed goal, a press for a reading, Steer back's
    correction, the copy of it, a dismissal, and the Intent log.
    """

    def roots(self) -> tuple[Path, ...]:
        # The transcript store, and the directory the session ran in.
        return (self.root / "claude", self.root / "work")

    def walk(self, port: int) -> list[tuple[str, int]]:
        sid = f"claude:{SHORT}"
        steps = [
            ("GET", "/api/data?all=1", None),
            ("GET", f"/api/project-context?project=billing&session={sid}&prompts=1", None),
            ("GET", f"/api/observe?harness=claude&sid={SHORT}", None),
            (
                "POST",
                "/api/annotate",
                {
                    "harness": "claude",
                    "sid": SHORT,
                    "goal": "Ship the placeholder parser",
                    "lines": ["The parser tests pass"],
                },
            ),
            ("POST", "/api/reading", self.press()),
            ("POST", "/api/correction", {"harness": "claude", "sid": SHORT}),
            (
                "POST",
                "/api/correction/copied",
                {"harness": "claude", "sid": SHORT, "text": COPIED},
            ),
            ("POST", "/api/dismiss", {"harness": "claude", "sid": SHORT}),
            ("GET", "/api/annotations", None),
        ]
        answered = []
        for method, path, payload in steps:
            status, _ = self.call(port, method, path, payload)
            self.settle()
            answered.append((path.split("?")[0], status))
        return answered

    def fake_models(self) -> contextlib.ExitStack:
        class Model:
            def __init__(self, _config: Any, **_kw: Any) -> None:
                pass

            def __call__(self, _prompt: str, **_kw: Any) -> tuple[str, str]:
                return "{}", "ok"

            def available(self) -> bool:
                return True

            unavailable_reason = runtime_reading.WITHHELD_MODEL_UNAVAILABLE

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(runtime_reading, "ClaudeReadingModel", Model))
        stack.enter_context(mock.patch.object(runtime_reading, "CodexReadingModel", Model))
        return stack

    def test_a_press_to_copy_journey_leaves_every_harness_file_as_it_found_it(self) -> None:
        reading_policy.set_consent(self.config, True, now=NOW, provider="claude")
        before = snapshot(*self.roots())
        with (
            self.machine(),
            self.fake_models(),
            write_guard(self.roots()) as writes,
            unix_connects() as unix,
            self.serving() as port,
        ):
            answered = self.walk(port)
        # The journey really ran: a route that refused everything would leave the store alone
        # for the wrong reason.
        statuses = dict(answered)
        self.assertEqual(200, statuses["/api/data"])
        self.assertEqual(200, statuses["/api/annotate"])
        self.assertEqual(202, statuses["/api/reading"])
        self.assertEqual(200, statuses["/api/correction"])
        self.assertEqual(200, statuses["/api/correction/copied"])
        self.assertTrue(
            any(Path(self.config.state_dir).rglob("*")),
            "the journey wrote nothing under Compass's own home either",
        )
        self.assertEqual([], writes)
        self.assertEqual(before, snapshot(*self.roots()))
        self.assertEqual([], unix)

    @unittest.skipIf(sys.platform == "win32", "Unix-domain sockets are POSIX here")
    def test_the_recorder_sees_a_connection_to_a_local_domain_socket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s")
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(path)
                server.listen(1)
                with unix_connects() as seen, socket.socket(socket.AF_UNIX) as client:
                    client.connect(path)
        self.assertEqual([path], seen)

    def test_the_guard_and_the_snapshot_each_see_a_write_into_the_store(self) -> None:
        before = snapshot(*self.roots())
        with write_guard(self.roots()) as writes, self.path.open("a", encoding="utf-8") as handle:
            handle.write("{}\n")
        self.assertEqual(1, len(writes))
        self.assertNotEqual(before, snapshot(*self.roots()))
        # And a write that puts the bytes back is still named, which the snapshot alone cannot.
        original = self.path.read_bytes()
        with write_guard(self.roots()) as writes:
            self.path.write_bytes(original)
        self.assertEqual(1, len(writes))


class TheSpacedockDiscoveryStartsNothingUnderItsSwitchTest(unittest.TestCase):
    """`--no-spacedock` stops `spacedock status --discover`, which no other test asked.

    The configuration test beside the flag only shows the switch reaching the frozen config.
    Here the runner is the seam, so what is asserted is the program that was not started.
    """

    def discover(self, *, enabled: bool) -> tuple[dict[str, Any], list[list[str]]]:
        started: list[list[str]] = []

        def runner(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
            started.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp) / "repository"
            (repository / ".git").mkdir(parents=True)
            config = make_config(spacedock_enabled=enabled)
            state = build_runtime_state(config, started=NOW)
            with mock.patch.dict(os.environ, {"SPACEDOCK_BIN": "/opt/bin/spacedock"}):
                result = project_context.discover_project_workflows(
                    config, state, str(repository), now=NOW, runner=runner
                )
        return result, started

    def test_the_switch_starts_no_program(self) -> None:
        result, started = self.discover(enabled=False)
        self.assertEqual([], started)
        self.assertEqual("unavailable", result["state"])

    def test_with_the_switch_on_the_same_call_does_start_it(self) -> None:
        _result, started = self.discover(enabled=True)
        self.assertEqual([["/opt/bin/spacedock", "status", "--discover"]], started)


class APressUnderTheModelRefusalLaunchesNothingTest(_Journey):
    """`--no-harness-usage` is `--no-observer-model`: it stops model calls, and these are the calls.

    The refusal tests beside the route count invocations of a stubbed model, which cannot see
    a process or a connection the stub replaced. Here the real model classes run, and the two
    ways a model call can leave are patched to raise: starting a process (the CLIs) and
    opening a connection. A control with the gate open reaches the process patch, so a press
    that never gets that far for another reason cannot read as a pass.
    """

    # The provider that reads a Claude Code session is Claude Code when it is on PATH and Codex
    # when it is not, so each provider is pressed on a machine that has only it.
    PROVIDERS: ClassVar[dict[str, tuple[str, ...]]] = {
        "claude": ("claude", "codex"),
        "codex": ("codex",),
    }

    def setUp(self) -> None:
        super().setUp()
        # A press reads the words the reader saved, and answers `produced: false` without them
        # before it reaches a model, which would make every "nothing launched" below true.
        annotation_store.annotate(
            self.config, self.state, "claude", SHORT, goal="Ship the placeholder parser", now=10.0
        )

    def config_for(self, *flags: str) -> Any:
        """This fixture's config, carrying what the given flags make of the model switches."""
        parsed = cli.build_runtime(
            cli.build_parser().parse_args(list(flags)), started=NOW, launcher_path=self.root / "x"
        )[0]
        return dataclasses.replace(
            self.config,
            model_calls_disabled=parsed.model_calls_disabled,
            observer_model_enabled=parsed.observer_model_enabled,
            unasked_enabled=parsed.unasked_enabled,
        )

    @contextlib.contextmanager
    def tripwires(self, port: int) -> Iterator[tuple[mock.Mock, list[Any]]]:
        """Raise on any process start and on any connection but this test's own client's."""
        real_dial = socket.create_connection
        dialled: list[Any] = []

        def dial(address: Any, *args: Any, **kwargs: Any) -> Any:
            if address == ("127.0.0.1", port):
                return real_dial(address, *args, **kwargs)
            dialled.append(address)
            raise OSError("a socket")

        with (
            mock.patch.object(subprocess, "Popen", side_effect=OSError("a process")) as popen,
            mock.patch.object(socket, "create_connection", dial),
        ):
            yield popen, dialled

    def press_with(self, config: Any, provider: str) -> int:
        self.config = config
        self.state.config = config
        with (
            self.machine(self.PROVIDERS[provider]),
            self.serving() as port,
            self.tripwires(port) as (popen, dialled),
        ):
            status, _ = self.call(port, "POST", "/api/reading", self.press(provider=provider))
            self.settle()
        self.launched = popen.call_count
        self.dialled = dialled
        return status

    def test_the_model_refusal_starts_no_process_and_opens_no_connection(self) -> None:
        refusals = {
            "model_calls_disabled": dataclasses.replace(self.config, model_calls_disabled=True),
            "--no-harness-usage": self.config_for("--no-harness-usage"),
            "--no-observer-model": self.config_for("--no-observer-model"),
            # The refusal outranks both opt-ins, which once started Codex readings.
            "--no-harness-usage with both opt-ins": self.config_for(
                "--observer-model", "--unasked-readings", "--no-harness-usage"
            ),
        }
        for label, config in refusals.items():
            for provider in self.PROVIDERS:
                with self.subTest(refusal=label, provider=provider):
                    self.assertTrue(config.model_calls_disabled)
                    status = self.press_with(config, provider)
                    self.assertEqual(503, status)
                    self.assertEqual((0, []), (self.launched, self.dialled))

    def test_with_the_gate_open_the_same_press_does_reach_the_process_patch(self) -> None:
        reading_policy.set_consent(self.config, True, now=NOW, provider="claude")
        reading_policy.set_consent(self.config, True, now=NOW, provider="codex")
        for provider in self.PROVIDERS:
            with self.subTest(provider=provider):
                status = self.press_with(self.config, provider)
                self.assertEqual(202, status)
                self.assertGreaterEqual(self.launched, 1)


class TheLaunchAndSendTableNamesRealTestsTest(unittest.TestCase):
    """The table in SECURITY.md cites tests by name, so a rename cannot leave it citing nothing.

    Three things are held: every cited `module.Class.method` resolves, every switch that stops
    a launch or a send appears, and every runtime module that starts a program or makes a
    request is accounted for by a row. The last is the one that finds a path nobody tabled.
    """

    HEADING = "## What launches and what sends\n"
    TESTS = Path(__file__).parent
    RUNTIME = Path(http_api.__file__).parent
    CITATION = re.compile(r"`(test_[a-z0-9_]+(?:\.[A-Za-z0-9_]+){1,2})`")
    # Every switch or environment variable that closes a launch or a send.
    SWITCHES = (
        "--no-usage",
        "--no-reach",
        "--no-observer-model",
        "--no-harness-usage",
        "--no-git",
        "--no-focus",
        "--no-spacedock",
        "--no-ask",
        "--no-events",
        "--quiet-hours",
        "--allow-tool-output",
        "COMPASS_ALLOW_TOOL_OUTPUT=1",
        "--interaction-origin-session",
        "--daemon",
    )
    # Runtime module -> text of the row that accounts for what it starts or requests.
    LAUNCHERS: ClassVar[dict[str, str]] = {
        "quota": "Vendor quota poll",
        "reach": "Reach nudge",
        "supervise": "A press for a reading",
        "git_status": "The git probe",
        "observation": "The focus command",
        "focus": "The focus command",
        "notifications": "A native notification",
        "lifecycle": "The daemon",
        "project_context": "The Spacedock workflow discovery",
        "interaction_prototype": "The optional read-only terminal",
    }
    WATCHED = frozenset(
        {
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.check_output",
            "subprocess.call",
            "urllib.request.urlopen",
            "urllib.request.build_opener",
            "socket.create_connection",
            "os.system",
            "os.execv",
            "os.execvp",
        }
    )

    @classmethod
    def section(cls) -> str:
        text = (SERVER_PATH.parents[3] / "SECURITY.md").read_text(encoding="utf-8")
        start = text.index(cls.HEADING) + len(cls.HEADING)
        return text[start : text.index("\n## ", start)]

    def test_every_cited_test_exists(self) -> None:
        cited = sorted(set(self.CITATION.findall(self.section())))
        self.assertGreaterEqual(len(cited), 20, "the pattern found almost nothing to check")
        missing = []
        for name in cited:
            module, _, rest = name.partition(".")
            path = self.TESTS / f"{module}.py"
            owner, _, method = rest.partition(".")
            if not path.exists():
                missing.append(name)
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
            found = classes.get(owner)
            if found is None or (
                method
                and method not in {n.name for n in found.body if isinstance(n, ast.FunctionDef)}
            ):
                missing.append(name)
        self.assertEqual([], missing)

    def test_every_switch_that_closes_a_path_is_in_the_table(self) -> None:
        section = self.section()
        self.assertEqual([], [switch for switch in self.SWITCHES if f"`{switch}" not in section])
        # The launch grant is cited by the class that holds its paths, as the ruling names it.
        self.assertIn("ALaunchTimeToolOutputGrantTest", section)

    def test_every_runtime_module_that_launches_or_requests_has_a_row(self) -> None:
        found: dict[str, set[str]] = {}
        for path in [*self.RUNTIME.glob("*.py"), *self.RUNTIME.glob("collectors/*.py")]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            used = {
                ast.unparse(node)
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and ast.unparse(node) in self.WATCHED
            }
            if used:
                found[path.stem] = used
        self.assertEqual(
            sorted(self.LAUNCHERS),
            sorted(found),
            "a module started a program or made a request without a row in the table, or "
            "a row's module stopped doing so",
        )
        section = self.section()
        self.assertEqual(
            [], [row for row in set(self.LAUNCHERS.values()) if f"| {row}" not in section]
        )


if __name__ == "__main__":
    unittest.main()
