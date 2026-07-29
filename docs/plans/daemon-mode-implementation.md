# Daemon Mode and UI Shutdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Cargento keep running after the session that started it exits, and give the user a way to stop it from the dashboard page.

**Architecture:** `server.py` grows a `--daemon` flag that detaches (double-fork on POSIX, detached re-spawn on Windows), a per-port state file under `~/.cargento/`, `--status`/`--stop` built on an HTTP health probe rather than signals, and two routes: `GET /api/health` and `POST /api/shutdown`. The page gets a two-click `stop` button in the header that POSTs the latter and then shows a terminal stopped panel. `--stop` and the button share the one shutdown path.

**Tech Stack:** Python 3.11+ stdlib only (`os`, `subprocess`, `http.client`, `select`, `threading`); the embedded page is plain JS in the `PAGE` string; tests are stdlib `unittest`, with page behavior executed under `node` via `PageJsHarness`.

The design and the reasoning behind each decision are in [`daemon-mode.md`](daemon-mode.md). Decision references below (D-1 … D-7) point there.

## Global Constraints

- Stdlib only, Python 3.11+. No dependencies, ever.
- All new code goes in `cargento/skills/cargento/server.py`; all new tests in `cargento/skills/cargento/tests/test_server.py`. No new modules — this plugin ships one server file.
- `ruff` runs with `select = ALL`. Every `noqa` needs an inline reason comment: `# noqa: S603 — fixed argv, no shell`. An *unnecessary* `noqa` fails `RUF100`, so add only what ruff actually demands.
- `mypy --strict` must pass, including on Windows, where `os.fork` and `os.setsid` do not exist. Never reference them at module import time except through `getattr(os, "fork", None)`.
- Line length 100. `E501` is ignored for `server.py` only (the embedded page), not for tests.
- Coverage `fail_under = 73` and only ratchets up. Never lower it.
- The server binds `127.0.0.1` only. Write `127.0.0.1`, never the `localhost` hostname, in any doc or string — `scripts/validate_plugins.py` rejects the `http://localhost` spelling of the dashboard URL outright, including in this plan.
- Never use `os.kill` for liveness (D-4): on Windows CPython routes it through `TerminateProcess`.
- Page state that a reader set must live in a module variable and be reapplied after each render — `#app` is rebuilt from scratch every 5 seconds.
- Escape every payload-derived string in the page through `esc()`.
- Commit with sign-off: `git commit -s`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `cargento/skills/cargento/server.py` | The whole server: CLI, HTTP handler, collectors, embedded page | Modified — new helpers grouped in one "process lifecycle" block placed immediately above `class Handler`, two handler routes, `main()` rewiring, page CSS + JS |
| `cargento/skills/cargento/tests/test_server.py` | Every test | Modified — new test methods, plus two additions to `PageJsHarness.PAGE_JS_STUBS` |
| `cargento/skills/cargento/SKILL.md` | The shipped product surface | Modified — Start, Stop, Options |
| `README.md`, `COMPATIBILITY.md`, `SECURITY.md`, `CONTRIBUTING.md` | Their owned subjects | Modified |
| `docs/design-daemon.md` | Durable rationale | Created |
| `docs/plans/daemon-mode.md`, `docs/plans/daemon-mode-implementation.md` | This plan and its spec | Deleted in the final task, once shipped |

New code goes in one contiguous block in `server.py` so the lifecycle logic can be read in one pass, rather than being scattered among the collectors. Put it directly above `class Handler` (currently line ~5723), after `collect_json`.

---

## Task 1: `GET /api/health`

Everything else polls this: the Windows readiness wait (D-2), `--status` and `--stop` (D-4, D-5). It answers without touching the filesystem, unlike `/api/data`, which scans every harness store on the machine.

**Files:**
- Modify: `cargento/skills/cargento/server.py` (module constant near `HOME`; `Handler.do_GET` at ~5786)
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SERVER_STARTED: float` (module global, set by `main()`); route `GET /api/health` returning `{"ok": true, "pid": int, "port": int, "started": float}`.

- [ ] **Step 1: Write the failing tests**

Add to `class CargentoServerTest` in `test_server.py`:

```python
    def test_health_reports_identity_without_scanning_any_store(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            # The readiness wait and --status poll this in a loop. If it ever
            # reaches collect(), a liveness check costs a full multi-harness
            # filesystem scan.
            with mock.patch.object(dashboard, "collect") as collect:
                conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
                conn.request("GET", "/api/health")
                response = conn.getresponse()
                status = response.status
                payload = json.loads(response.read())
                conn.close()
            collect.assert_not_called()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(os.getpid(), payload["pid"])
        self.assertEqual(httpd.server_port, payload["port"])
        self.assertIsInstance(payload["started"], (int, float))

    def test_health_is_refused_from_a_non_local_host_header(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            conn.putrequest("GET", "/api/health", skip_host=True)
            conn.putheader("Host", "evil.example")
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest.test_health_reports_identity_without_scanning_any_store -v`
Expected: FAIL — the response is 404, so `json.loads` raises or `payload["ok"]` raises `KeyError`.

- [ ] **Step 3: Add the constant**

In `server.py`, immediately after the `STORE_ENV_VARS` line (~64):

```python
# Wall-clock start of the serving process, reported by /api/health so a caller
# can tell uptime without a second request. Set once by main().
SERVER_STARTED = 0.0
```

- [ ] **Step 4: Add the route**

In `Handler.do_GET`, insert a branch before the `elif url.path == "/":` line:

```python
        elif url.path == "/api/health":
            self._health()
```

And add this method to `Handler`, directly above `do_GET`:

```python
    def _health(self) -> None:
        """Liveness and identity, with no filesystem access.

        `/api/data` can answer "is a dashboard here?" only by scanning every
        harness store on the machine. The daemon readiness wait and --status ask
        that question in a loop, so they need an answer that costs nothing. The
        pid is part of it because "something is listening on the port" is not
        the same claim as "Cargento is running on the port".
        """
        self._send(
            json.dumps(
                {
                    "ok": True,
                    "pid": os.getpid(),
                    "port": getattr(self.server, "server_port", 0),
                    "started": SERVER_STARTED,
                }
            ).encode(),
            "application/json",
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k health -v`
Expected: PASS, 2 tests.

- [ ] **Step 6: Lint and typecheck**

Run: `ruff check . && ruff format --check . && mypy`
Expected: clean. If `ruff format` rewrites your block, accept its formatting.

- [ ] **Step 7: Commit**

```bash
git add cargento/skills/cargento/server.py cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): add GET /api/health for cheap liveness checks"
```

---

## Task 2: the per-port state file

D-3. One layout on every platform, `CARGENTO_HOME` authoritative when set, written by every instance that binds — daemon or foreground.

**Files:**
- Modify: `cargento/skills/cargento/server.py` (new lifecycle block above `class Handler`)
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: `SERVER_STARTED` (Task 1).
- Produces: `CARGENTO_HOME_ENV: str`, `DAEMON_READY_TIMEOUT_SEC: float`, `cargento_home() -> str`, `state_path(port: int) -> str`, `log_path(port: int) -> str`, `ensure_cargento_home() -> str`, `write_state(port: int) -> None`, `read_state(port: int) -> dict[str, Any] | None`, `remove_state(port: int) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
    def test_cargento_home_honours_the_override_and_defaults_under_home(self) -> None:
        with mock.patch.dict(os.environ, {"CARGENTO_HOME": "/tmp/elsewhere"}):
            self.assertEqual("/tmp/elsewhere", dashboard.cargento_home())
            self.assertEqual("/tmp/elsewhere", os.path.dirname(dashboard.state_path(4553)))
        environ = {k: v for k, v in os.environ.items() if k != "CARGENTO_HOME"}
        with mock.patch.dict(os.environ, environ, clear=True):
            self.assertEqual(
                os.path.join(dashboard.HOME, ".cargento"), dashboard.cargento_home()
            )

    def test_state_file_roundtrips_and_names_itself_per_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                dashboard.write_state(4553)
                dashboard.write_state(9999)
                self.assertTrue(os.path.exists(os.path.join(tmp, "cargento-4553.json")))
                state = dashboard.read_state(4553)
                assert state is not None
                self.assertEqual(os.getpid(), state["pid"])
                self.assertEqual(4553, state["port"])
                self.assertEqual(dashboard.log_path(4553), state["log"])
                self.assertEqual(sys.executable, state["python"])
                # Two instances on two ports do not overwrite each other.
                other = dashboard.read_state(9999)
                assert other is not None
                self.assertEqual(9999, other["port"])
                dashboard.remove_state(4553)
                self.assertIsNone(dashboard.read_state(4553))
                dashboard.remove_state(4553)  # removing twice is not an error

    def test_read_state_returns_none_for_absent_corrupt_and_non_object_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                self.assertIsNone(dashboard.read_state(4553))
                Path(dashboard.state_path(4553)).write_text("{not json", encoding="utf-8")
                self.assertIsNone(dashboard.read_state(4553))
                Path(dashboard.state_path(4553)).write_text("[1,2]", encoding="utf-8")
                self.assertIsNone(dashboard.read_state(4553))

    def test_write_state_reports_and_survives_an_unwritable_home(self) -> None:
        # A dashboard that cannot write its state file still serves; --status
        # just cannot see it. This must never be fatal.
        with tempfile.TemporaryDirectory() as tmp:
            blocker = os.path.join(tmp, "home")
            Path(blocker).write_text("not a directory", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CARGENTO_HOME": blocker}):
                with mock.patch.object(dashboard, "diag") as diag:
                    dashboard.write_state(4553)
                self.assertTrue(diag.called)
```

`tempfile`, `Path`, `sys` and `mock` are already imported in `test_server.py`; confirm rather than re-adding.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k state -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'cargento_home'`.

- [ ] **Step 3: Implement**

Open a new block in `server.py` directly above `class Handler`, starting with this comment, and put every later task's lifecycle helper in the same block:

```python
# ── process lifecycle: state file, health probe, detaching, stopping ────────
# Cargento is started by an agent and outlives the session that started it, so
# it needs the three things a supervised process gets for free: a way to be
# found, a way to be asked whether it is alive, and a way to be stopped. See
# docs/design-daemon.md.

CARGENTO_HOME_ENV = "CARGENTO_HOME"
DAEMON_READY_TIMEOUT_SEC = 10.0


def cargento_home() -> str:
    """Where the state file and the daemon log live.

    One layout on every platform. Platform-correct runtime directories
    (XDG_RUNTIME_DIR, %LOCALAPPDATA%) would be three code paths and three ways
    for --status to look somewhere the server never wrote. CARGENTO_HOME is
    authoritative when set, which is the rule the harness store variables in
    STORE_ENV_VARS already follow.
    """
    return os.environ.get(CARGENTO_HOME_ENV) or os.path.join(HOME, ".cargento")


def state_path(port: int) -> str:
    return os.path.join(cargento_home(), f"cargento-{port}.json")


def log_path(port: int) -> str:
    return os.path.join(cargento_home(), f"cargento-{port}.log")


def ensure_cargento_home() -> str:
    """Create the state directory, owner-only, and return it.

    0o700 because the log carries tracebacks with local paths in them. The mode
    is advisory: it does not apply to a directory that already exists, and
    Windows ignores it.
    """
    home = cargento_home()
    os.makedirs(home, mode=0o700, exist_ok=True)
    return home


def write_state(port: int) -> None:
    """Record this process as the instance serving `port`.

    Written by every instance that binds, daemon or foreground: --status and
    --stop are worth having either way, and a file that exists only sometimes
    is a file whose absence tells you nothing.

    Written through a temp file and os.replace so a reader mid-write sees the
    old file or the new one, never half of one.
    """
    payload = {
        "pid": os.getpid(),
        "port": port,
        "started": SERVER_STARTED,
        "log": log_path(port),
        "python": sys.executable,
    }
    target = state_path(port)
    tmp = f"{target}.{os.getpid()}.tmp"
    try:
        ensure_cargento_home()
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, target)
    except OSError as exc:
        diag(f"Cargento: could not write {target} ({exc}); --status will not see this instance")
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def read_state(port: int) -> dict[str, Any] | None:
    """The recorded state for `port`, or None if there is none to trust."""
    try:
        with open(state_path(port), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def remove_state(port: int) -> None:
    with contextlib.suppress(OSError):
        os.unlink(state_path(port))
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k state -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
ruff check . && ruff format --check . && mypy
git add cargento/skills/cargento/server.py cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): record a per-port state file under ~/.cargento"
```

---

## Task 3: the health probe and `--status`

D-4. The probe distinguishes three things a naive check collapses into one, and the pid in the response is what makes the third distinguishable.

**Files:**
- Modify: `cargento/skills/cargento/server.py` (lifecycle block; `import http.client` at the top; `main()` at ~6039)
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: `read_state`, `log_path` (Task 2); `GET /api/health` (Task 1).
- Produces: `probe_port(port: int, timeout: float = 1.0) -> tuple[str, dict[str, Any] | None]` returning kind `"cargento" | "foreign" | "closed"`; `instance_status(port: int) -> dict[str, Any]` with `state` in `"running" | "stale" | "foreign" | "absent"`; `render_status(status: dict[str, Any]) -> str`; CLI flag `--status`.

The spec's D-4 table covers the three cases where a state file exists. `"absent"` is the fourth: nothing listening and no state file. It is not an error.

- [ ] **Step 1: Write the failing tests**

```python
    def test_probe_port_classifies_cargento_foreign_and_closed(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_port
        try:
            kind, health = dashboard.probe_port(port, timeout=2)
            self.assertEqual("cargento", kind)
            assert health is not None
            self.assertEqual(os.getpid(), health["pid"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
        # Same port, now nothing listening.
        self.assertEqual(("closed", None), dashboard.probe_port(port, timeout=1))

    def test_probe_port_calls_a_non_cargento_listener_foreign(self) -> None:
        class Other(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"hi")

            def log_message(self, *args: object) -> None:
                pass

        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), Other)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            # 200 but not JSON: something else owns this port. Reporting it as
            # Cargento is how a stop command ends up aimed at an unrelated
            # process.
            self.assertEqual(("foreign", None), dashboard.probe_port(httpd.server_port, timeout=2))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_instance_status_covers_running_stale_foreign_and_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                health = {"ok": True, "pid": 4242, "port": 4553, "started": 1000.0}
                with mock.patch.object(dashboard, "probe_port", return_value=("cargento", health)):
                    running = dashboard.instance_status(4553)
                self.assertEqual("running", running["state"])
                self.assertEqual(4242, running["pid"])

                with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
                    self.assertEqual("absent", dashboard.instance_status(4553)["state"])
                    dashboard.write_state(4553)
                    stale = dashboard.instance_status(4553)
                self.assertEqual("stale", stale["state"])
                self.assertEqual(os.getpid(), stale["pid"])

                with mock.patch.object(dashboard, "probe_port", return_value=("foreign", None)):
                    self.assertEqual("foreign", dashboard.instance_status(4553)["state"])

    def test_render_status_names_the_state_and_never_suggests_a_kill(self) -> None:
        running = dashboard.render_status(
            {"state": "running", "port": 4553, "pid": 7, "started": 1000.0, "log": "/l"}
        )
        self.assertIn("running", running)
        self.assertIn("pid 7", running)
        self.assertIn("http://127.0.0.1:4553/", running)
        stale = dashboard.render_status({"state": "stale", "port": 4553, "pid": 7, "log": "/l"})
        self.assertIn("--stop", stale)
        foreign = dashboard.render_status({"state": "foreign", "port": 4553, "pid": None})
        self.assertIn("another process", foreign)
        self.assertIn("Nothing was stopped", foreign)
        self.assertIn("not running", dashboard.render_status({"state": "absent", "port": 4553}))

    def test_status_flag_exits_zero_only_when_running(self) -> None:
        for state, expected in (("running", 0), ("stale", 1), ("foreign", 1), ("absent", 1)):
            with mock.patch.object(
                dashboard, "instance_status", return_value={"state": state, "port": 4553, "pid": 1}
            ):
                with mock.patch.object(sys, "argv", ["server.py", "--status"]):
                    with mock.patch.object(dashboard, "diag"):
                        with self.assertRaises(SystemExit) as caught:
                            dashboard.main()
            self.assertEqual(expected, caught.exception.code, state)
```

The `Other` handler needs `import http.server` in the test module — check whether it is already imported and add it if not.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k "probe or instance_status or render_status or status_flag" -v`
Expected: FAIL with `AttributeError: ... has no attribute 'probe_port'`.

- [ ] **Step 3: Add the import**

In `server.py`, add to the stdlib import block (alphabetical, after `hashlib`):

```python
import http.client
```

`from http.server import ...` is already there; `import http.client` does not conflict with it.

- [ ] **Step 4: Implement the probe and status**

Append to the lifecycle block:

```python
def probe_port(port: int, timeout: float = 1.0) -> tuple[str, dict[str, Any] | None]:
    """What is listening on `port`: Cargento, something else, or nothing.

    Returns ("cargento", health) | ("foreign", None) | ("closed", None).

    The distinction is the entire point of this function. "Something is
    listening" reading as "Cargento is running" is how a stop command ends up
    aimed at an unrelated local server.
    """
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", "/api/health")
        response = conn.getresponse()
        body = response.read(4096)
        if response.status != 200:
            return ("foreign", None)
        data = json.loads(body)
    except (OSError, http.client.HTTPException):
        return ("closed", None)
    except ValueError:
        return ("foreign", None)  # answered 200 with something that is not JSON
    finally:
        conn.close()
    if not isinstance(data, dict) or not data.get("ok") or not isinstance(data.get("pid"), int):
        return ("foreign", None)
    return ("cargento", data)


def instance_status(port: int) -> dict[str, Any]:
    """Whether Cargento is on `port`, and what to say about it if not."""
    kind, health = probe_port(port)
    state = read_state(port)
    recorded_log = (state or {}).get("log") or log_path(port)
    if kind == "cargento" and health is not None:
        return {
            "state": "running",
            "port": port,
            "pid": health["pid"],
            "started": health.get("started"),
            "log": recorded_log,
        }
    if kind == "foreign":
        return {"state": "foreign", "port": port, "pid": (state or {}).get("pid")}
    return {
        "state": "stale" if state is not None else "absent",
        "port": port,
        "pid": (state or {}).get("pid"),
        "log": recorded_log,
    }


def render_status(status: dict[str, Any]) -> str:
    """One line describing an instance, for --status and --stop."""
    port = status["port"]
    state = status["state"]
    if state == "running":
        started = status.get("started")
        since = (
            datetime.fromtimestamp(started, tz=UTC).astimezone().strftime("%H:%M")
            if isinstance(started, int | float) and started
            else "unknown"
        )
        return (
            f"Cargento: running on port {port} (pid {status['pid']}, since {since}) "
            f"http://127.0.0.1:{port}/"
        )
    if state == "foreign":
        return (
            f"Cargento: port {port} is held by another process — what answered "
            f"/api/health is not Cargento. Nothing was stopped or removed."
        )
    if state == "stale":
        return (
            f"Cargento: not running on port {port}. A stale state file remains "
            f"(pid {status['pid']}); --stop removes it."
        )
    return f"Cargento: not running on port {port}."
```

- [ ] **Step 5: Wire `--status` into `main()`**

Add the flag after the existing `--no-spacedock` block in `main()`:

```python
    ap.add_argument(
        "--status",
        action="store_true",
        help="report whether a Cargento is running on --port, and exit",
    )
```

And handle it immediately after the `--diagnose` block, before the `sqlite_available()` check:

```python
    if args.status:
        status = instance_status(args.port)
        diag(render_status(status))
        raise SystemExit(0 if status["state"] == "running" else 1)
```

- [ ] **Step 6: Run to verify they pass**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k "probe or instance_status or render_status or status_flag" -v`
Expected: PASS, 5 tests.

- [ ] **Step 7: Lint, typecheck, commit**

```bash
ruff check . && ruff format --check . && mypy
git add cargento/skills/cargento/server.py cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): add --status backed by an HTTP health probe, never a signal"
```

---

## Task 4: `POST /api/shutdown`

D-6. The one shutdown path, shared by the page button and `--stop`.

**Files:**
- Modify: `cargento/skills/cargento/server.py` (`Handler.do_POST` at ~5799; `main()`)
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: `Handler._local_ok`, `Handler._send` (existing); `write_state`, `remove_state` (Task 2).
- Produces: route `POST /api/shutdown` returning `{"ok":true,"stopping":true}`; `main()` now writes the state file before serving and removes it in a `finally`.

- [ ] **Step 1: Write the failing tests**

```python
    def test_shutdown_endpoint_answers_before_it_stops_the_server(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            conn.request("POST", "/api/shutdown", body=b"", headers={"Content-Length": "0"})
            response = conn.getresponse()
            # Answering first is the requirement: socketserver.shutdown() waits
            # for the serve loop's current pass to finish, and that pass is this
            # handler. Called inline it deadlocks.
            self.assertEqual(200, response.status)
            self.assertEqual(b'{"ok":true,"stopping":true}', response.read())
            conn.close()
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "serve_forever did not return")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_shutdown_endpoint_refuses_a_cross_site_post(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            conn.request(
                "POST",
                "/api/shutdown",
                body=b"",
                headers={"Content-Length": "0", "Sec-Fetch-Site": "cross-site"},
            )
            response = conn.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            conn.close()
            # Still serving: a refused stop must not stop anything.
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            conn.request("GET", "/api/health")
            self.assertEqual(200, conn.getresponse().status)
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k shutdown_endpoint -v`
Expected: FAIL — the first gets 404 instead of 200.

- [ ] **Step 3: Route it**

In `Handler.do_POST`, replace the existing path check:

```python
        if urlparse(self.path).path != "/api/notify":
            self.send_error(404)
            return
```

with:

```python
        path = urlparse(self.path).path
        if path == "/api/shutdown":
            self._shutdown()
            return
        if path != "/api/notify":
            self.send_error(404)
            return
```

Add the method to `Handler`, next to `_health`:

```python
    def _shutdown(self) -> None:
        """Stop the server: the page's stop button and --stop both land here.

        Answer first, then stop. `socketserver.shutdown()` blocks until the
        serve loop finishes its current pass, and the current pass is this
        handler — calling it inline deadlocks the process it is trying to end,
        which is why the stop runs on a thread of its own.
        """
        self._send(b'{"ok":true,"stopping":true}', "application/json")
        with contextlib.suppress(OSError, ValueError):
            self.wfile.flush()
        threading.Thread(target=self.server.shutdown, daemon=True).start()
```

- [ ] **Step 4: Make `main()` write and clean up the state file**

Replace the last two lines of `main()`:

```python
    diag(f"Cargento: http://127.0.0.1:{args.port}/")
    server.serve_forever()
```

with:

```python
    diag(f"Cargento: http://127.0.0.1:{args.port}/")
    write_state(args.port)
    try:
        server.serve_forever()
    finally:
        remove_state(args.port)
        with contextlib.suppress(OSError):
            server.server_close()
```

Also set the start time. Immediately after `args = ap.parse_args()`, add:

```python
    global SERVER_STARTED  # noqa: PLW0603 — one process-wide start stamp
    SERVER_STARTED = time.time()
```

If ruff objects to two `global` statements in one function (`SPACEDOCK_ENABLED` already has one), merge them into a single `global SERVER_STARTED, SPACEDOCK_ENABLED` at the top of `main()` and keep the assignment where it is.

- [ ] **Step 5: Run to verify they pass**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k shutdown_endpoint -v`
Expected: PASS, 2 tests.

- [ ] **Step 6: Run the whole suite — this task changed a shared code path**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server -v 2>&1 | tail -5`
Expected: OK. `do_POST` is shared with `/api/notify`, so any regression there shows up here.

- [ ] **Step 7: Lint, typecheck, commit**

```bash
ruff check . && ruff format --check . && mypy
git add cargento/skills/cargento/server.py cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): add POST /api/shutdown and clean up state on exit"
```

---

## Task 5: `--stop`

D-5. Stops over HTTP, exactly as the button does. Exit codes: 0 when it stopped a running instance, cleaned a stale file, or found nothing (stopping is idempotent — scripts call it blindly); 1 when the port belongs to something else, which is the one case where it deliberately does nothing.

**Files:**
- Modify: `cargento/skills/cargento/server.py` (lifecycle block; `main()`)
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: `instance_status`, `render_status`, `remove_state`; `POST /api/shutdown` (Task 4).
- Produces: `stop_instance(port: int) -> tuple[str, int]` returning (message, exit code); CLI flag `--stop`.

- [ ] **Step 1: Write the failing tests**

```python
    def test_stop_instance_stops_a_running_server_over_http(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            message, code = dashboard.stop_instance(httpd.server_port)
            self.assertEqual(0, code, message)
            self.assertIn("stopped", message)
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_stop_instance_removes_a_stale_state_file_and_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                dashboard.write_state(4553)
                with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
                    message, code = dashboard.stop_instance(4553)
                self.assertEqual(0, code)
                self.assertIn("stale", message)
                self.assertIsNone(dashboard.read_state(4553))

    def test_stop_instance_refuses_to_touch_a_port_owned_by_something_else(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                dashboard.write_state(4553)
                with mock.patch.object(dashboard, "probe_port", return_value=("foreign", None)):
                    message, code = dashboard.stop_instance(4553)
                self.assertEqual(1, code)
                self.assertIn("another process", message)
                # The state file is evidence, not garbage: leave it alone.
                self.assertIsNotNone(dashboard.read_state(4553))

    def test_stop_instance_is_idempotent_when_nothing_is_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
                    message, code = dashboard.stop_instance(4553)
        self.assertEqual(0, code)
        self.assertIn("nothing running", message)

    def test_stop_flag_exits_with_the_code_stop_instance_returned(self) -> None:
        with mock.patch.object(dashboard, "stop_instance", return_value=("nope", 1)) as stop:
            with mock.patch.object(sys, "argv", ["server.py", "--port", "4553", "--stop"]):
                with mock.patch.object(dashboard, "diag") as diag:
                    with self.assertRaises(SystemExit) as caught:
                        dashboard.main()
        self.assertEqual(1, caught.exception.code)
        stop.assert_called_once_with(4553)
        diag.assert_called_once_with("nope")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k "stop_instance or stop_flag" -v`
Expected: FAIL with `AttributeError: ... has no attribute 'stop_instance'`.

- [ ] **Step 3: Implement**

Append to the lifecycle block:

```python
def stop_instance(port: int) -> tuple[str, int]:
    """Ask the instance on `port` to stop. Returns (message, exit code).

    Over HTTP, the same route the page's stop button uses — one implementation
    of stopping, and no per-platform signal semantics to reconcile. A server
    wedged badly enough not to serve cannot be stopped this way; SKILL.md keeps
    the platform kill commands for that.
    """
    status = instance_status(port)
    state = status["state"]
    if state == "running":
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("POST", "/api/shutdown", body=b"", headers={"Content-Length": "0"})
            response = conn.getresponse()
            response.read(1024)
            answered = response.status
        except (OSError, http.client.HTTPException) as exc:
            return (f"Cargento: could not stop port {port} — {type(exc).__name__}: {exc}", 1)
        finally:
            conn.close()
        if answered != 200:
            return (f"Cargento: the instance on port {port} refused to stop ({answered}).", 1)
        return (f"Cargento: stopped (pid {status['pid']}) on port {port}.", 0)
    if state == "stale":
        remove_state(port)
        return (f"Cargento: nothing running on port {port}; removed the stale state file.", 0)
    if state == "foreign":
        # The state file is evidence about a port we do not own. Leave it.
        return (render_status(status), 1)
    # Nothing there and nothing recorded. Stopping is idempotent on purpose:
    # a script that calls --stop unconditionally should not fail for it.
    return (f"Cargento: nothing running on port {port}.", 0)
```

- [ ] **Step 4: Wire `--stop` into `main()`**

Add the flag next to `--status`:

```python
    ap.add_argument(
        "--stop",
        action="store_true",
        help="stop the Cargento running on --port, and exit",
    )
```

Handle it immediately before the `--status` block:

```python
    if args.stop:
        message, code = stop_instance(args.port)
        diag(message)
        raise SystemExit(code)
```

- [ ] **Step 5: Run to verify they pass**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k "stop_instance or stop_flag" -v`
Expected: PASS, 5 tests.

- [ ] **Step 6: Lint, typecheck, commit**

```bash
ruff check . && ruff format --check . && mypy
git add cargento/skills/cargento/server.py cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): add --stop, which stops over HTTP rather than by signal"
```

---

## Task 6: detaching on POSIX

D-1. Bind first, then fork. The parent reports and exits; the daemon serves.

The parent has to be the process that prints the URL, because an agent's shell tool captures output only until the process it waited for exits — a line printed by the detached child after that is lost. So the daemon reports its pid back over a pipe, and the parent prints it. That also makes the report real: it means the daemon got as far as serving.

**Files:**
- Modify: `cargento/skills/cargento/server.py` (`import select`; lifecycle block; `main()`)
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: `ensure_cargento_home`, `log_path`, `write_state` (Task 2); `DAEMON_READY_TIMEOUT_SEC`.
- Produces: `_FORK`, `_SETSID` (module-level, possibly `None`); `fork_daemon(*, fork=None, setsid=None, exit_intermediate=None) -> tuple[str, int]` returning `("parent", read_fd)` or `("daemon", write_fd)`; `daemon_redirect_stdio(log_file: str) -> None`; `daemon_announce(write_fd: int) -> None`; `await_daemon(read_fd: int, port: int, log_file: str, timeout: float = DAEMON_READY_TIMEOUT_SEC) -> tuple[str, int]`; CLI flag `--daemon`.

- [ ] **Step 1: Write the failing tests**

```python
    def test_fork_daemon_returns_parent_role_without_touching_setsid(self) -> None:
        calls: list[str] = []

        def fake_fork() -> int:
            calls.append("fork")
            return 4242  # a pid: this process is the original

        def fake_setsid() -> int:
            calls.append("setsid")
            return 0

        role, fd = dashboard.fork_daemon(fork=fake_fork, setsid=fake_setsid)
        os.close(fd)
        self.assertEqual("parent", role)
        self.assertEqual(["fork"], calls)

    def test_fork_daemon_double_forks_and_sessions_the_daemon(self) -> None:
        calls: list[str] = []
        exited: list[int] = []

        def fake_fork() -> int:
            calls.append("fork")
            return 0  # child both times: this process becomes the daemon

        def fake_setsid() -> int:
            calls.append("setsid")
            return 0

        role, fd = dashboard.fork_daemon(
            fork=fake_fork, setsid=fake_setsid, exit_intermediate=exited.append
        )
        os.close(fd)
        self.assertEqual("daemon", role)
        # setsid between the two forks: the second fork is what guarantees the
        # daemon is not a session leader and can never acquire a terminal.
        self.assertEqual(["fork", "setsid", "fork"], calls)
        self.assertEqual([], exited)

    def test_fork_daemon_exits_the_intermediate_child(self) -> None:
        forks = iter([0, 9999])  # child, then parent-of-grandchild
        exited: list[int] = []
        role, fd = dashboard.fork_daemon(
            fork=lambda: next(forks),
            setsid=lambda: 0,
            exit_intermediate=exited.append,
        )
        os.close(fd)
        # The intermediate's only job was setsid. In production os._exit never
        # returns; the injected stub does, so the role is reported for the test.
        self.assertEqual([0], exited)
        self.assertEqual("daemon", role)

    def test_await_daemon_reports_the_pid_the_daemon_announced(self) -> None:
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, b"31337\n")
        finally:
            os.close(write_fd)
        message, code = dashboard.await_daemon(read_fd, 4553, "/tmp/c.log", timeout=2)
        self.assertEqual(0, code)
        self.assertIn("pid 31337", message)
        self.assertIn("http://127.0.0.1:4553/", message)
        self.assertIn("/tmp/c.log", message)

    def test_await_daemon_reports_failure_when_the_daemon_says_nothing(self) -> None:
        read_fd, write_fd = os.pipe()
        os.close(write_fd)  # daemon died before announcing
        message, code = dashboard.await_daemon(read_fd, 4553, "/tmp/c.log", timeout=1)
        self.assertEqual(1, code)
        self.assertIn("/tmp/c.log", message)

    def test_daemon_rejects_the_flags_it_cannot_combine_with(self) -> None:
        for other in ("--diagnose", "--stop", "--status"):
            with mock.patch.object(sys, "argv", ["server.py", "--daemon", other]):
                with self.assertRaises(SystemExit) as caught:
                    with contextlib.redirect_stderr(io.StringIO()):
                        dashboard.main()
            self.assertEqual(2, caught.exception.code, other)
```

`io` and `contextlib` must be imported in the test module — add them if absent. These tests run on Windows too: `os.pipe` exists there, and `fork_daemon` is driven entirely by injected hooks.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k "fork_daemon or await_daemon or cannot_combine" -v`
Expected: FAIL with `AttributeError: ... has no attribute 'fork_daemon'`.

- [ ] **Step 3: Add the import and the platform hooks**

Add `import select` to the stdlib import block (after `re`).

Then, at the top of the lifecycle block, just under `DAEMON_READY_TIMEOUT_SEC`:

```python
# Resolved through getattr, never referenced directly: `os.fork` and
# `os.setsid` do not exist on Windows, and a module-level `os.fork` reference
# would fail at import there — including under mypy, which checks both
# platforms.
_FORK: Callable[[], int] | None = getattr(os, "fork", None)
_SETSID: Callable[[], int] | None = getattr(os, "setsid", None)
```

`Callable` is already imported under `TYPE_CHECKING`, and `from __future__ import annotations` is in effect, so the annotation is a string at runtime.

- [ ] **Step 4: Implement the POSIX detach**

Append to the lifecycle block:

```python
def fork_daemon(
    *,
    fork: Callable[[], int] | None = None,
    setsid: Callable[[], int] | None = None,
    exit_intermediate: Callable[[int], None] | None = None,
) -> tuple[str, int]:
    """Split this process into a detached daemon and a reporting parent.

    Returns ("parent", read_fd) in the original process, which must report what
    the daemon says and then exit, and ("daemon", write_fd) in the detached
    process, which must serve.

    Why the parent reports rather than the daemon: an agent's shell tool stops
    capturing output when the process it waited for exits, so a line printed by
    the detached child afterwards is simply lost. The pipe also makes the
    report *true* — the parent says "running" because the daemon said so.

    Why two forks: the first detaches from the caller, setsid leaves the
    session and its controlling terminal, and the second means the daemon is
    not a session leader, so it can never reacquire one.

    The hooks exist so the call sequence can be asserted without a test suite
    that forks itself.
    """
    do_fork = fork or _FORK
    do_setsid = setsid or _SETSID
    do_exit = exit_intermediate or os._exit  # noqa: SLF001 — os._exit is the documented spelling
    if do_fork is None or do_setsid is None:  # pragma: no cover — POSIX-only path
        raise RuntimeError("--daemon needs fork/setsid; use the Windows re-spawn path")
    read_fd, write_fd = os.pipe()
    if do_fork() > 0:
        os.close(write_fd)
        return ("parent", read_fd)
    os.close(read_fd)
    do_setsid()
    if do_fork() > 0:
        do_exit(0)
    return ("daemon", write_fd)


def daemon_redirect_stdio(log_file: str) -> None:
    """Point stdio at the log, once there is nothing left to say on the terminal.

    dup2 rather than reassigning sys.stdout: writes from C and an uncaught
    traceback go to fd 1 and 2 directly, and those are exactly the output a
    detached failure leaves behind.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "rb") as devnull:
        os.dup2(devnull.fileno(), 0)
    with open(log_file, "ab", buffering=0) as handle:
        os.dup2(handle.fileno(), 1)
        os.dup2(handle.fileno(), 2)


def daemon_announce(write_fd: int) -> None:
    """Tell the waiting parent this process is serving, and how to name it."""
    with contextlib.suppress(OSError):
        os.write(write_fd, f"{os.getpid()}\n".encode())
    with contextlib.suppress(OSError):
        os.close(write_fd)


def await_daemon(
    read_fd: int, port: int, log_file: str, timeout: float = DAEMON_READY_TIMEOUT_SEC
) -> tuple[str, int]:
    """Wait for the forked daemon's pid. Returns (message, exit code)."""
    deadline = time.monotonic() + timeout
    seen = b""
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([read_fd], [], [], 0.1)
            if not ready:
                continue
            chunk = os.read(read_fd, 64)
            if not chunk:
                break  # the daemon closed the pipe without announcing: it died
            seen += chunk
            if b"\n" in seen:
                break
    except OSError:
        seen = b""
    finally:
        with contextlib.suppress(OSError):
            os.close(read_fd)
    pid = seen.strip().decode("ascii", "replace")
    if pid.isdigit():
        return (f"Cargento: http://127.0.0.1:{port}/ (pid {pid}, log {log_file})", 0)
    return (
        f"Cargento: started in the background, but it did not report ready "
        f"within {timeout:.0f}s — check {log_file}.",
        1,
    )
```

- [ ] **Step 5: Wire `--daemon` into `main()`**

Add the flag next to `--stop`:

```python
    ap.add_argument(
        "--daemon",
        action="store_true",
        help="detach and keep running after the session that started it exits",
    )
```

Immediately after `args = ap.parse_args()` and the `SERVER_STARTED` assignment, reject the combinations that cannot mean anything (D-5):

```python
    if args.daemon and (args.diagnose or args.stop or args.status):
        # Each of those three exits without serving, so --daemon cannot apply.
        # Accepting it silently would teach that it had been honored.
        ap.error("--daemon cannot be combined with --diagnose, --stop or --status")
```

Then change the bind-and-serve tail of `main()`. It currently reads:

```python
    try:
        server = LoopbackHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        diag(bind_error_message(exc, args.port))
        raise SystemExit(1) from exc
    diag(f"Cargento: http://127.0.0.1:{args.port}/")
    write_state(args.port)
    try:
        server.serve_forever()
    finally:
        remove_state(args.port)
        with contextlib.suppress(OSError):
            server.server_close()
```

Replace it with:

```python
    log_file = log_path(args.port)
    if args.daemon:
        ensure_cargento_home()
    # Bind before detaching. bind_error_message() exists so a busy port gets an
    # explanation rather than a traceback, and SKILL.md tells the agent to look
    # for an already-running dashboard when it sees one. Forking first would
    # send that message to a log file nobody has been told about yet, and
    # report success.
    try:
        server = LoopbackHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        diag(bind_error_message(exc, args.port))
        raise SystemExit(1) from exc
    announce_fd: int | None = None
    if args.daemon:
        role, fd = fork_daemon()
        if role == "parent":
            # The daemon holds its own dup of the listening socket; closing
            # this one keeps a dead daemon from leaving the port looking bound.
            with contextlib.suppress(OSError):
                server.server_close()
            message, code = await_daemon(fd, args.port, log_file)
            diag(message)
            raise SystemExit(code)
        announce_fd = fd
        daemon_redirect_stdio(log_file)
    diag(f"Cargento: http://127.0.0.1:{args.port}/")
    write_state(args.port)
    if announce_fd is not None:
        # After write_state, so --status works the instant the parent returns.
        daemon_announce(announce_fd)
    try:
        server.serve_forever()
    finally:
        remove_state(args.port)
        with contextlib.suppress(OSError):
            server.server_close()
```

- [ ] **Step 6: Run to verify they pass**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k "fork_daemon or await_daemon or cannot_combine" -v`
Expected: PASS, 6 tests.

- [ ] **Step 7: Lint, typecheck, commit**

```bash
ruff check . && ruff format --check . && mypy
git add cargento/skills/cargento/server.py cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): detach with --daemon on POSIX, binding before the fork"
```

If ruff reports the `# noqa: SLF001` on `os._exit` as unused (`RUF100`), delete the comment; if it demands a different code, use the one it names.

---

## Task 7: detaching on Windows

D-2. No fork, so re-spawn and wait for the consequence of the child's bind.

**Files:**
- Modify: `cargento/skills/cargento/server.py` (lifecycle block; `main()`)
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: `probe_port` (Task 3), `log_path`, `ensure_cargento_home` (Task 2), `DAEMON_READY_TIMEOUT_SEC`.
- Produces: `forwarded_args(args: argparse.Namespace) -> list[str]`; `spawn_detached(args: argparse.Namespace, log_file: str) -> subprocess.Popen[bytes]`; `log_tail(log_file: str, limit: int = 2000) -> str`; `await_spawned(proc, port: int, log_file: str, timeout: float = DAEMON_READY_TIMEOUT_SEC) -> tuple[str, int]`.

All four are testable on any platform: `spawn_detached` through a mocked `Popen`, `await_spawned` through a stub process object.

- [ ] **Step 1: Write the failing tests**

```python
    def test_forwarded_args_carries_the_flags_the_child_needs_and_drops_daemon(self) -> None:
        args = argparse.Namespace(port=4553, window_hours=12.0, no_spacedock=True, daemon=True)
        forwarded = dashboard.forwarded_args(args)
        self.assertEqual(["--port", "4553", "--window-hours", "12.0", "--no-spacedock"], forwarded)
        # --daemon must not be forwarded: the child is an ordinary foreground
        # run that happens to own no console. Forwarding it would re-spawn
        # forever.
        self.assertNotIn("--daemon", forwarded)
        plain = dashboard.forwarded_args(
            argparse.Namespace(port=1, window_hours=24.0, no_spacedock=False, daemon=True)
        )
        self.assertEqual(["--port", "1", "--window-hours", "24.0"], plain)

    def test_spawn_detached_uses_a_fixed_argv_and_detaching_flags(self) -> None:
        args = argparse.Namespace(port=4553, window_hours=24.0, no_spacedock=False, daemon=True)
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "c.log")
            with mock.patch.object(dashboard.subprocess, "Popen") as popen:
                popen.return_value = mock.Mock(pid=321)
                dashboard.spawn_detached(args, log_file)
        argv = popen.call_args.args[0]
        self.assertEqual(sys.executable, argv[0])
        self.assertTrue(argv[1].endswith("server.py"))
        self.assertEqual(["--port", "4553", "--window-hours", "24.0"], argv[2:])
        self.assertEqual(dashboard.subprocess.DEVNULL, popen.call_args.kwargs["stdin"])
        self.assertTrue(popen.call_args.kwargs["close_fds"])
        # 0 on POSIX, where these creationflags do not exist; the call must
        # still be well-formed so the test runs everywhere.
        self.assertIsInstance(popen.call_args.kwargs["creationflags"], int)

    def test_await_spawned_reports_the_child_that_answered(self) -> None:
        health = {"ok": True, "pid": 777, "port": 4553, "started": 1.0}
        proc = mock.Mock(returncode=None)
        proc.poll.return_value = None
        with mock.patch.object(dashboard, "probe_port", return_value=("cargento", health)):
            message, code = dashboard.await_spawned(proc, 4553, "/tmp/c.log", timeout=2)
        self.assertEqual(0, code)
        self.assertIn("pid 777", message)
        self.assertIn("http://127.0.0.1:4553/", message)

    def test_await_spawned_surfaces_the_log_when_the_child_exits_at_once(self) -> None:
        # This is the case that keeps D-1's promise on Windows: the parent
        # cannot see the child's failed bind, so it shows the child's log.
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "c.log")
            Path(log_file).write_text(
                "Cargento: port 4553 is already in use.", encoding="utf-8"
            )
            proc = mock.Mock(returncode=1)
            proc.poll.return_value = 1
            with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
                message, code = dashboard.await_spawned(proc, 4553, log_file, timeout=2)
        self.assertEqual(1, code)
        self.assertIn("already in use", message)

    def test_await_spawned_gives_up_after_the_timeout(self) -> None:
        proc = mock.Mock(returncode=None)
        proc.poll.return_value = None
        with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
            message, code = dashboard.await_spawned(proc, 4553, "/tmp/c.log", timeout=0.3)
        self.assertEqual(1, code)
        self.assertIn("/tmp/c.log", message)

    def test_log_tail_reads_the_end_and_never_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "c.log")
            Path(log_file).write_bytes(b"x" * 3000 + b"LAST LINE")
            tail = dashboard.log_tail(log_file, limit=200)
            self.assertIn("LAST LINE", tail)
            self.assertLessEqual(len(tail), 200)
            self.assertIn("could not read", dashboard.log_tail(os.path.join(tmp, "nope.log")))
            Path(log_file).write_bytes(b"")
            self.assertIn("empty", dashboard.log_tail(log_file))
```

`argparse` must be imported in the test module — add it if absent.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k "forwarded_args or spawn_detached or await_spawned or log_tail" -v`
Expected: FAIL with `AttributeError: ... has no attribute 'forwarded_args'`.

- [ ] **Step 3: Implement**

Append to the lifecycle block:

```python
def forwarded_args(args: argparse.Namespace) -> list[str]:
    """The flags a re-spawned child needs — built from parsed values, not sys.argv.

    --daemon is deliberately absent: the child is an ordinary foreground run
    that happens to own no console, and forwarding the flag would re-spawn
    forever. Rebuilding from the namespace rather than filtering argv means a
    future flag has to be added here consciously.
    """
    forwarded = ["--port", str(args.port), "--window-hours", str(args.window_hours)]
    if args.no_spacedock:
        forwarded.append("--no-spacedock")
    return forwarded


def spawn_detached(args: argparse.Namespace, log_file: str) -> subprocess.Popen[bytes]:
    """Re-spawn this script with no console attached (Windows has no fork)."""
    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    with open(log_file, "ab", buffering=0) as handle:
        return subprocess.Popen(  # noqa: S603 — fixed argv from parsed flags, no shell
            [sys.executable, os.path.abspath(__file__), *forwarded_args(args)],
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=handle,
            creationflags=creationflags,
            close_fds=True,
        )


def log_tail(log_file: str, limit: int = 2000) -> str:
    """The end of the daemon log — the only account of a failure the parent
    could not watch happen."""
    try:
        with open(log_file, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            data = handle.read()
    except OSError:
        return f"(could not read {log_file})"
    return data.decode("utf-8", "replace").strip() or f"({log_file} is empty)"


def await_spawned(
    proc: subprocess.Popen[bytes],
    port: int,
    log_file: str,
    timeout: float = DAEMON_READY_TIMEOUT_SEC,
) -> tuple[str, int]:
    """Wait for the re-spawned child to answer. Returns (message, exit code).

    Windows cannot report the child's bind() to the parent, so the parent
    observes the consequence instead. That is what keeps the POSIX promise that
    a busy port explains itself on the terminal rather than only in a log.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        kind, health = probe_port(port, timeout=0.5)
        if kind == "cargento" and health is not None:
            return (f"Cargento: http://127.0.0.1:{port}/ (pid {health['pid']}, log {log_file})", 0)
        if proc.poll() is not None:
            return (
                f"Cargento: the background server exited immediately "
                f"(code {proc.returncode}). Its output was:\n{log_tail(log_file)}",
                1,
            )
        time.sleep(0.2)
    return (
        f"Cargento: started in the background, but nothing answered on port "
        f"{port} within {timeout:.0f}s — check {log_file}.",
        1,
    )
```

- [ ] **Step 4: Wire it into `main()`**

The Windows path must run *before* the bind, so the parent never holds the port. Insert this immediately before the `log_file = log_path(args.port)` line added in Task 6 — no, place it directly after that line and before the bind:

```python
    log_file = log_path(args.port)
    if args.daemon:
        ensure_cargento_home()
    if args.daemon and os.name == "nt":
        # No fork on Windows: re-spawn, then wait to be sure (D-2). Returns
        # before binding, so the parent never holds the port it handed over.
        message, code = await_spawned(spawn_detached(args, log_file), args.port, log_file)
        diag(message)
        raise SystemExit(code)
```

Then guard the POSIX branch so it cannot run on Windows. Change the Task 6 line `if args.daemon:` (the `role, fd = fork_daemon()` one) to:

```python
    if args.daemon and os.name != "nt":
```

- [ ] **Step 5: Run to verify they pass**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.CargentoServerTest -k "forwarded_args or spawn_detached or await_spawned or log_tail" -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Lint, typecheck, commit**

```bash
ruff check . && ruff format --check . && mypy
git add cargento/skills/cargento/server.py cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): detach on Windows by re-spawning and waiting for readiness"
```

---

## Task 8: the end-to-end lifecycle test

One test, no platform skip. The CLI contract is identical on both paths, so whichever detach path the runner has is the one it exercises — and CI runs Ubuntu, macOS and Windows.

**Files:**
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: the `--daemon`, `--status`, `--stop` CLI from Tasks 3, 5, 6, 7.
- Produces: nothing.

- [ ] **Step 1: Write the test**

Add a new test class at the end of `test_server.py`:

```python
class DaemonLifecycleTest(unittest.TestCase):
    """The real thing: detach, outlive the caller, answer --status, stop.

    Everything else in this file tests a piece. This tests the promise.
    """

    SERVER = str(Path(dashboard.__file__).resolve())

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        return port

    def _run(self, *flags: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.SERVER, *flags],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_daemon_outlives_its_caller_and_stops_on_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "CARGENTO_HOME": tmp}
            port = self._free_port()
            flags = ("--port", str(port))
            try:
                start = self._run(*flags, "--daemon", env=env)
                self.assertEqual(0, start.returncode, start.stdout + start.stderr)
                # The starting process has exited by now. Everything below runs
                # against a server whose parent is gone.
                self.assertIn(f"http://127.0.0.1:{port}/", start.stdout)
                self.assertIn("pid ", start.stdout)

                kind, health = dashboard.probe_port(port, timeout=10)
                self.assertEqual("cargento", kind, start.stdout)
                assert health is not None
                self.assertNotEqual(os.getpid(), health["pid"])

                state = json.loads(
                    Path(tmp, f"cargento-{port}.json").read_text(encoding="utf-8")
                )
                self.assertEqual(health["pid"], state["pid"])

                status = self._run(*flags, "--status", env=env)
                self.assertEqual(0, status.returncode, status.stdout + status.stderr)
                self.assertIn("running", status.stdout)

                stopped = self._run(*flags, "--stop", env=env)
                self.assertEqual(0, stopped.returncode, stopped.stdout + stopped.stderr)
                self.assertIn("stopped", stopped.stdout)

                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if dashboard.probe_port(port, timeout=1)[0] == "closed":
                        break
                    time.sleep(0.2)
                self.assertEqual("closed", dashboard.probe_port(port, timeout=1)[0])
                self.assertFalse(Path(tmp, f"cargento-{port}.json").exists())

                after = self._run(*flags, "--status", env=env)
                self.assertEqual(1, after.returncode)
                self.assertIn("not running", after.stdout)
            finally:
                # Never leave a detached server behind, however this test ended.
                self._run(*flags, "--stop", env=env)

    def test_a_busy_port_still_explains_itself_under_daemon(self) -> None:
        """D-1's promise: binding happens before detaching, so this message
        reaches the terminal that asked for it and not just a log file."""
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_port
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = self._run(
                    "--port", str(port), "--daemon", env={**os.environ, "CARGENTO_HOME": tmp}
                )
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn(f"port {port}", result.stdout + result.stderr)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
```

`socket` must be imported in the test module — add it if absent.

The `_free_port` helper has an inherent race: the port is free when checked, and something else could take it before the daemon binds. In practice the window is microseconds and the fallback is a clear bind error, not a hang.

- [ ] **Step 2: Run it**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server.DaemonLifecycleTest -v`
Expected: PASS, 2 tests. This one really forks and really binds, so expect a few seconds.

- [ ] **Step 3: Confirm no server was left behind**

Run: `python3 cargento/skills/cargento/server.py --status --port 4553`
Expected: reports on your own dashboard if you have one running on 4553, and nothing about the test's ports. Then check that no stray process is listening on a random high port from the test run — the `finally` should have handled it.

- [ ] **Step 4: Lint, typecheck, commit**

```bash
ruff check . && ruff format --check . && mypy
git add cargento/skills/cargento/tests/test_server.py
git commit -s -m "test(skill): cover the real daemon lifecycle end to end"
```

---

## Task 9: the stop button on the page

D-7. Arms before it fires; the stopped page is not the stalled page.

**Files:**
- Modify: `cargento/skills/cargento/server.py` (CSS near `.modebtn` at ~4478; JS: `modeBar` ~5061, `calmAction` ~5233, the click listener ~5255, the keydown listener ~5260, `refresh` ~5663, the `setInterval` line ~5695)
- Modify: `cargento/skills/cargento/tests/test_server.py` (`PageJsHarness.PAGE_JS_STUBS`)
- Test: `cargento/skills/cargento/tests/test_server.py`

**Interfaces:**
- Consumes: `POST /api/shutdown` (Task 4); existing page functions `esc()`, `render()`, `lastData`, `modeBar()`, `calmAction()`.
- Produces: page globals `stopArmed`, `stopError`, `serverStopped`, `refreshTimer`; functions `stopControl()`, `disarmStop()`, `requestStop()`, `renderStopped()`; `data-calm="stop"` as a click action.

- [ ] **Step 1: Extend the test stubs**

Two additions to `PageJsHarness.PAGE_JS_STUBS` in `test_server.py`. Replace the existing fetch line:

```javascript
const fetch = () => new Promise(() => {});
```

with:

```javascript
// Records what the page requested and lets a test choose the reply. The old
// never-settling stub is the default, so existing tests behave identically.
let __fetchCalls = [];
let __fetchImpl = () => new Promise(() => {});
const fetch = (...args) => { __fetchCalls.push(args); return __fetchImpl(...args); };
const clearInterval = () => {};
```

`fetch` stays `const` — tests swap `__fetchImpl`, never `fetch` itself. `clearInterval` is needed because the page now cancels its own polling.

- [ ] **Step 2: Write the failing page tests**

Add to the calm-mode page test class (the one with `FIXTURE` and `run_calm`):

```python
    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_stop_button_arms_then_posts_and_shows_the_stopped_panel(self) -> None:
        checks = """
const out = {};
render(board());
out.shown = __els.app.innerHTML.includes('data-calm="stop"');
out.armedBefore = __els.app.innerHTML.includes("sure?");

// First click only arms it: the page cannot undo a stop.
__fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
out.armedAfter = __els.app.innerHTML.includes("sure?");
out.postedYet = __fetchCalls.filter(c => c[0] === "/api/shutdown").length;

// A refresh must not disarm it — #app is rebuilt every 5s and the button
// would flicker under the reader's cursor.
render(board());
out.survivesRender = __els.app.innerHTML.includes("sure?");

__fetchImpl = () => Promise.resolve({ok: true});
__fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
await __settle(); await __settle();
const posted = __fetchCalls.filter(c => c[0] === "/api/shutdown");
out.posted = posted.length;
out.method = posted.length ? posted[0][1].method : null;
out.stoppedPanel = __els.app.innerHTML.includes("Cargento stopped");
out.buttonGone = __els.app.innerHTML.includes('data-calm="stop"');
out.title = document.title;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["shown"])
        self.assertFalse(out["armedBefore"])
        self.assertTrue(out["armedAfter"])
        self.assertEqual(0, out["postedYet"])
        self.assertTrue(out["survivesRender"])
        self.assertEqual(1, out["posted"])
        self.assertEqual("POST", out["method"])
        self.assertTrue(out["stoppedPanel"])
        self.assertFalse(out["buttonGone"])
        self.assertIn("stopped", out["title"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_stop_disarms_on_escape_and_on_a_click_elsewhere(self) -> None:
        checks = """
const out = {};
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
const clickAway = () => __fire("click", {target: {closest: () => null}});

render(board());
clickStop();
out.armed = __els.app.innerHTML.includes("sure?");
__fire("keydown", {key: "Escape", preventDefault(){}, target: {tagName: "DIV"}});
out.afterEsc = __els.app.innerHTML.includes("sure?");

clickStop();
out.armedAgain = __els.app.innerHTML.includes("sure?");
clickAway();
out.afterClickAway = __els.app.innerHTML.includes("sure?");
out.nothingPosted = __fetchCalls.filter(c => c[0] === "/api/shutdown").length;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["armed"])
        self.assertFalse(out["afterEsc"])
        self.assertTrue(out["armedAgain"])
        self.assertFalse(out["afterClickAway"])
        self.assertEqual(0, out["nothingPosted"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_failed_stop_reports_inline_and_leaves_the_page_live(self) -> None:
        checks = """
const out = {};
render(board());
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop();
__fetchImpl = () => Promise.resolve({ok: false, status: 403});
clickStop();
await __settle(); await __settle();
// The server is still running, so the page must not claim otherwise.
out.stoppedPanel = __els.app.innerHTML.includes("Cargento stopped");
out.error = __els.app.innerHTML.includes("stop failed");
out.rows = rows();
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertFalse(out["stoppedPanel"])
        self.assertTrue(out["error"])
        self.assertEqual(3, out["rows"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_late_refresh_does_not_repaint_over_the_stopped_panel(self) -> None:
        checks = """
const out = {};
render(board());
serverStopped = true;
renderStopped();
await refresh();          // an in-flight poll settling after the stop
out.stillStopped = __els.app.innerHTML.includes("Cargento stopped");
out.noFetch = __fetchCalls.filter(c => String(c[0]).startsWith("/api/data")).length;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stillStopped"])
        self.assertEqual(0, out["noFetch"])
```

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server -k stop_button -v`
Expected: FAIL — `out["shown"]` is False, since nothing renders `data-calm="stop"` yet.

- [ ] **Step 4: Add the CSS**

In `PAGE`, immediately after the `.modebtn:focus-visible` rule (~4478):

```css
  .stopbtn{font-family:var(--mono);font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:5px 12px;border:1px solid var(--line);border-radius:9px;cursor:pointer;color:var(--ink3);background:var(--bg);transition:color .12s,background .12s,border-color .12s}
  .stopbtn:hover{color:var(--ink2)}
  .stopbtn.armed{color:var(--alert);border-color:color-mix(in oklab,var(--alert) 45%,transparent);background:color-mix(in oklab,var(--alert) 12%,transparent)}
  .stopbtn:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in oklab,var(--accent) 45%,transparent)}
  .stopnote{font-family:var(--mono);font-size:10.5px;color:var(--alert);margin-left:6px}
  .stopped{margin:72px auto;max-width:440px;display:flex;flex-direction:column;gap:10px;text-align:center;font-family:var(--mono)}
  .stopped-h{font-size:15px;font-weight:700;color:var(--ink)}
  .stopped-p{font-size:12px;color:var(--ink3);line-height:1.65}
```

- [ ] **Step 5: Add the JS**

Insert directly above `function modeBar(){`:

```javascript
/* ── stopping the server from the page ─────────────────────────────────────
   Two clicks, because the page cannot undo a stop and the header is a place
   people click. `stopArmed` is a module variable for the documented reason:
   #app is rebuilt every five seconds, so state that is not reapplied after
   the swap is state the refresh eats — and a button that disarmed itself on
   the next poll would flicker under the reader's cursor. */
let stopArmed = false;
let stopError = "";
let serverStopped = false;

function stopControl(){
  if(serverStopped) return "";
  const note = stopError ? `<span class="stopnote">${esc(stopError)}</span>` : "";
  return `<button type="button" class="stopbtn${stopArmed ? " armed" : ""}"` +
    ` data-calm="stop" aria-pressed="${stopArmed}"` +
    ` title="Stop the Cargento server. Two clicks — this cannot be undone from the page.">` +
    (stopArmed ? "stop — sure?" : "stop") + `</button>` + note;
}

function disarmStop(){
  if(!stopArmed && !stopError) return false;
  stopArmed = false; stopError = "";
  return true;
}

async function requestStop(){
  stopArmed = false;
  try{
    const r = await fetch("/api/shutdown", {method: "POST"});
    if(!r.ok) throw new Error("status " + r.status);
  }catch(e){
    /* Still running, so the page must not claim otherwise. */
    stopError = "stop failed";
    if(lastData) render(lastData);
    return;
  }
  serverStopped = true;
  renderStopped();
}

function renderStopped(){
  /* Not the "stalled" banner: nothing is retrying, nothing is coming back,
     and the reader is the one who ended it. */
  if(refreshTimer !== null){ clearInterval(refreshTimer); refreshTimer = null; }
  document.title = "Cargento — stopped";
  const app = document.getElementById("app");
  if(!app) return;
  app.className = "wrap";
  app.innerHTML = `<div class="stopped"><div class="stopped-h">Cargento stopped.</div>` +
    `<div class="stopped-p">The server is no longer running, so this page will not ` +
    `update. Ask your agent to open Cargento again to restart it.</div></div>`;
}
```

- [ ] **Step 6: Put the button in the header**

`modeBar()` is called by both display modes (calm at ~5578, regular at ~5651), so one edit covers both. Change its return to append the control after the segmented switch — `.modebar` is `justify-content:flex-end`, so it lands rightmost:

```javascript
  return `<div class="modebar"><span class="modebar-k">display</span>` +
    `<div class="modeseg" role="group" aria-label="display mode">` +
    btn("regular") + btn("calm") + `</div>` + stopControl() + `</div>`;
```

- [ ] **Step 7: Wire the click, the click-away, and escape**

In `calmAction`, immediately after the `mode` line:

```javascript
  if(act === "stop"){
    if(!stopArmed){ stopArmed = true; stopError = ""; if(lastData) render(lastData); return; }
    requestStop();
    return;
  }
```

In the document click listener, replace `if(!el) return;` with:

```javascript
  if(!el){
    /* A click anywhere else is an answer: not that one. */
    if(disarmStop() && lastData) render(lastData);
    return;
  }
```

In the keydown listener, immediately after the `c` handler and *before* the `if(displayMode !== "calm" || !lastData) return;` guard, so it works in both modes:

```javascript
  if(k === "Escape" && (stopArmed || stopError)){
    stop(); disarmStop(); if(lastData) render(lastData); return;
  }
```

- [ ] **Step 8: Stop the polling loop cleanly**

At the top of `async function refresh(){`, add:

```javascript
  if(serverStopped) return;   /* an in-flight poll must not repaint the panel */
```

And replace the last line of the script:

```javascript
setInterval(refresh, 5000);
```

with:

```javascript
let refreshTimer = setInterval(refresh, 5000);
```

`refreshTimer` is referenced by `renderStopped()`, which is defined earlier in the file — that is fine, since it is only *called* after the assignment runs. Do not move the `let` above `renderStopped`; `refresh()` is called on the line before, and hoisting the timer would change when the first poll fires.

- [ ] **Step 9: Run the page tests**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server -k "stop_button or stop_disarms or failed_stop or late_refresh" -v`
Expected: PASS, 4 tests.

- [ ] **Step 10: Run every page test — the stubs changed for all of them**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_server -v 2>&1 | tail -5`
Expected: OK. The `fetch` stub is shared by every page test, so a mistake there shows up broadly.

- [ ] **Step 11: Lint the embedded assets**

Run: `python3 scripts/lint_embedded.py`
Expected: clean. This is the linter for the HTML/CSS/JS inside `PAGE`; add `--allow-missing-node` only if node is genuinely unavailable.

- [ ] **Step 12: Lint, typecheck, commit**

```bash
ruff check . && ruff format --check . && mypy
git add cargento/skills/cargento/server.py cargento/skills/cargento/tests/test_server.py
git commit -s -m "feat(skill): add a two-click stop button to the dashboard header"
```

---

## Task 10: documentation, and the pre-PR gate

**Files:**
- Modify: `cargento/skills/cargento/SKILL.md`, `README.md`, `COMPATIBILITY.md`, `SECURITY.md`, `CONTRIBUTING.md`
- Create: `docs/design-daemon.md`
- Delete: `docs/plans/daemon-mode.md`, `docs/plans/daemon-mode-implementation.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code depends on.

- [ ] **Step 1: Rewrite the SKILL.md Start section**

Replace the three per-shell code blocks and the surrounding prose (lines ~52–85, from `## Start` through the busy-port paragraph) with:

```markdown
## Start

Stdlib-only, Python 3.11+, no dependencies. Resolve `server.py` relative to this `SKILL.md` in the
installed plugin and start it detached, so it keeps running after this session ends:

```bash
python3 "<skill-dir>/server.py" --port 4553 --daemon
```

One line on every platform and in every shell — `--daemon` does the detaching itself, so no
backgrounding operator is involved. It prints the URL, the pid and the log path, and returns.
On native Windows `python3` is not a reliable spelling; use `python` (or `py -3`). Whichever
interpreter starts the server, reuse it for the commands below.

Drop `--daemon` to run it in the foreground instead, which is the easier shape for debugging: log
output goes to your terminal rather than to the log file.

Then open the UI:

```bash
python3 -m webbrowser -t http://127.0.0.1:4553/
```

Use `127.0.0.1`, not `localhost`: the server listens on IPv4 only, and on some systems `localhost`
resolves to `::1` first.

Tell the user the URL, that the page auto-refreshes every 5 seconds, that it keeps running until
stopped, and that popups require the server to be running. Completed-task ages/estimates degrade
where the filesystem exposes no birthtime (Linux, and Windows before Python 3.12).

If the port is busy the server explains that instead of dumping a traceback, and exits non-zero —
under `--daemon` too. Check whether a dashboard is already there before killing anything:

```bash
python3 "<skill-dir>/server.py" --port 4553 --status
```

`--status` reports one of three things, and never guesses: running (with pid and uptime), not
running, or that the port belongs to some other process — in which case it changes nothing.

Cargento writes two files, both under `~/.cargento` (relocatable with `CARGENTO_HOME`):
`cargento-<port>.json`, which records the running instance, and `cargento-<port>.log`, where a
detached server's output goes.
```

- [ ] **Step 2: Rewrite the SKILL.md Stop section**

Replace the whole `## Stop` section (~148–166) with:

```markdown
## Stop

```bash
python3 "<skill-dir>/server.py" --port 4553 --stop
```

Or click `stop` in the dashboard header — two clicks, since the page cannot undo it. Both do the
same thing: `POST /api/shutdown`. `--stop` also clears a state file left behind by a server that
was killed, and exits non-zero without touching anything if the port turns out to belong to another
process.

**Last resort**, for a server wedged badly enough that it no longer answers HTTP. Match only
*listening* sockets — without that filter these also match connected clients, including the
browser's own network process:

```bash
# macOS, Linux, WSL (lsof is absent on many minimal images — fuser is the fallback)
lsof -ti tcp:4553 -sTCP:LISTEN | xargs kill
fuser -k 4553/tcp
```
```powershell
# Windows PowerShell
Get-NetTCPConnection -LocalPort 4553 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```
```bat
:: Windows cmd, typed at the prompt — inside a .bat file write %%a for %a.
for /f "tokens=5" %a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":4553"') do taskkill /PID %a /F
```

Substitute the port the server was actually started on. The cmd form matches any port whose digits
contain the string (`:4553` also matches `:45530`), so prefer the PowerShell form on Windows.
```

- [ ] **Step 3: Add the SKILL.md Options rows**

In the Options table, after the `--port N` row (whose "check whether a dashboard is already there"
advice should now point at `--status` rather than `curl`):

```markdown
| `--daemon` | Detach and keep running after the starting session exits. Prints the URL, pid and log path. |
| `--stop` | Stop the instance on `--port`, over `/api/shutdown` — the same path the UI's `stop` button uses. |
| `--status` | Report whether Cargento is on `--port`: running, not running, or the port belongs to another process. Exits 0 only when running. |
| `/api/health` | Liveness and identity (pid, port, uptime). Scans nothing, unlike `/api/data`. |
| `POST /api/shutdown` | Stop the server. Loopback-only, with the same origin checks as `/api/notify`. |
```

- [ ] **Step 4: Document the button in Display modes**

Add to the end of the `## Display modes` intro paragraph:

```markdown
A `stop` button sits beside the switch in both modes: the first click arms it, the second stops the
server, and `esc` or a click elsewhere disarms it. After it fires the page stops polling and says
Cargento was stopped, rather than showing the "stalled" banner that means the server went away on
its own.
```

- [ ] **Step 5: Update the other owned docs**

- `README.md` — find any line that starts the server (grep for `server.py`) and add `--daemon`; mention that it keeps running until stopped and can be stopped from the UI or with `--stop`.
- `COMPATIBILITY.md` — a subsection saying `--daemon` double-forks on POSIX and re-spawns detached on Windows; both bind (or verify a bind) before reporting success, so a busy port fails loudly on every platform; the state file and log live under `~/.cargento`, one layout everywhere, `CARGENTO_HOME` authoritative.
- `SECURITY.md` — the two files Cargento writes and why (`0o700`; the log can carry local paths from tracebacks), and the `/api/shutdown` exposure: any local process that can reach the port could already read every session on the machine through `/api/data`, and can now also stop the server — a smaller capability inside the same trust boundary, gated by the same `Host`/`Origin`/`Sec-Fetch-Site` checks.
- `CONTRIBUTING.md` — three bullets in "Design constraints for `server.py`": bind the listener before forking, so a failed bind is still reported to the terminal that asked; never use `os.kill`, including `os.kill(pid, 0)` for liveness, because CPython implements it on Windows through `TerminateProcess` — probe `/api/health` instead; stopping goes over HTTP so the CLI and the page share one path, and `socketserver.shutdown()` must never be called from a handler thread.

- [ ] **Step 6: Write `docs/design-daemon.md`**

Fold the durable content out of `docs/plans/daemon-mode.md`: the seven decisions with their
rationale, and the Rejected section. Leave out the task breakdown, the exit criteria and the
verification checklist — those belong to the work, not to the design. Link it from
`CONTRIBUTING.md` alongside `design-cross-platform.md`, and add it to the docs table in `AGENTS.md`
if the table lists design docs individually rather than as `docs/design-*.md`.

- [ ] **Step 7: Delete the plan docs**

```bash
git rm docs/plans/daemon-mode.md docs/plans/daemon-mode-implementation.md
```

`AGENTS.md` is explicit: delete a plan once its work ships. Any link to them from another doc must
be repointed at `docs/design-daemon.md` first, or `validate_plugins.py` fails on the dangling link.

- [ ] **Step 8: Verify the macOS notification path by hand**

This is the one thing the plan refuses to assume (see the spec's "Verification, not assumption"),
because delivering popups with no browser tab open is the main reason daemon mode is worth having.
On macOS, with no dashboard tab open:

```bash
python3 cargento/skills/cargento/server.py --port 4553 --daemon
echo '{"session_id":"deadbeef","message":"daemon notification check","notification_type":"permission_request"}' \
  | python3 cargento/skills/cargento/notify_hook.py
```

Expected: a macOS notification appears. If it does not, `osascript` cannot reach the user's Aqua
session from a detached session leader, and that is a finding worth writing into
`docs/design-daemon.md` and `COMPATIBILITY.md` rather than papering over. Then:

```bash
python3 cargento/skills/cargento/server.py --port 4553 --stop
```

- [ ] **Step 9: Run the full pre-PR gate**

From `AGENTS.md`, the canonical suite:

```bash
python3 -m pip install -r requirements-validation.txt -r requirements-dev.txt
ruff check .
ruff format --check .
mypy
python3 scripts/lint_embedded.py
python3 scripts/validate_plugins.py
python3 scripts/bump_version.py --current
git diff "$(git merge-base origin/main HEAD)"..HEAD \
  -- '*plugin.json' '*marketplace.json' '*gemini-extension.json' | grep -E '^[+-].*"version"'
coverage run -m unittest cargento.skills.cargento.tests.test_server \
  scripts.tests.test_validate_plugins scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded
coverage report
```

Expected: everything passes; the `git diff | grep` prints nothing (version fields are owned by the
Release workflow and must not move in a PR); `coverage report` meets `fail_under = 73`. If coverage
dropped, add tests — never lower the threshold.

Then, if the CLIs are installed:

```bash
claude plugin validate ./cargento --strict
agy plugin validate ./cargento
```

- [ ] **Step 10: Reconcile docs, then commit and open the PR**

Run `/sync-docs` in your agent — it is a skill, not a shell command — and let it commit any doc
updates onto this branch. It also holds the human-facing prose to the documented voice standard.

```bash
git add -A
git commit -s -m "docs: document daemon mode, --stop/--status, and the UI stop button"
git push -u origin HEAD && gh pr create
```

---

## Self-Review

**Spec coverage.** D-1 → Task 6. D-2 → Task 7. D-3 → Task 2. D-4 → Task 3. D-5 → Task 5 (plus the argparse rejection in Task 6, Step 5). D-6 → Tasks 1 and 4. D-7 → Task 9. Surface table → Tasks 3, 5, 6 (flags) and 1, 4 (routes). Exit codes → Task 3 Step 1 and Task 5 Step 1. Documentation section → Task 10. Tests section → every task, with the end-to-end in Task 8. Verification → Task 10 Step 8. Rejected alternatives → carried into `docs/design-daemon.md` in Task 10 Step 6. Exit criteria → Task 8 (survives its caller, `--status` states, busy port), Task 9 (button and stopped page), Task 10 (macOS notification, full gate).

**Two gaps the spec left, closed here rather than silently:** `instance_status` has a fourth state, `"absent"` (nothing listening, no state file), which D-4's three-row table did not cover because it assumed a state file exists. And `--stop` with nothing running exits 0, not 1 — stopping is idempotent so a script can call it unconditionally, which the spec's exit-code paragraph did not address.

**Type and name consistency.** `probe_port` returns `tuple[str, dict[str, Any] | None]` and every caller (`instance_status`, `await_spawned`, the end-to-end test) unpacks two values and checks `kind == "cargento"` before using `health`. `instance_status` always returns a dict with `state` and `port`; `render_status` reads `pid`, `started` and `log` defensively via `.get` where a state may not carry them. `stop_instance` and `await_daemon` and `await_spawned` all return `(message, code)` in that order, and every `main()` call site does `message, code = …; diag(message); raise SystemExit(code)`. `fork_daemon` returns `("parent", read_fd)` / `("daemon", write_fd)` and `main()` branches on the string. Page side: `stopArmed`, `stopError`, `serverStopped`, `refreshTimer`, `stopControl`, `disarmStop`, `requestStop`, `renderStopped` are spelled identically in the implementation steps and in the tests, and the click action is `data-calm="stop"` in `stopControl`, `calmAction` and all four page tests.

**One ordering hazard, called out where it bites:** Task 7 Step 4 must place the Windows branch *before* the bind, and must add the `and os.name != "nt"` guard to the POSIX branch Task 6 introduced. Getting either wrong means the parent holds the port it is handing to the child.
