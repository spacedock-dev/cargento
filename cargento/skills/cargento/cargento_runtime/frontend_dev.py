"""Startup-only admission for an owned loopback development module server."""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import re
import secrets
import socket
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class DevelopmentFrontend:
    python_origin: str
    vite_origin: str
    vite_generation: str
    backend_generation: str
    vite_pid: int


@dataclass(frozen=True)
class DevManifest:
    frontend: DevelopmentFrontend
    scratch: Path
    nonce: str = field(repr=False)


class DevelopmentRuntime(Protocol):
    @property
    def home(self) -> str: ...
    @property
    def data_home(self) -> str: ...
    @property
    def state_dir(self) -> Path: ...

    @property
    def state_home(self) -> str: ...
    @property
    def store_roots(self) -> Mapping[str, tuple[str, ...]]: ...
    @property
    def host(self) -> str: ...
    @property
    def port(self) -> int: ...
    @property
    def model_calls_disabled(self) -> bool: ...
    @property
    def usage_fetch_enabled(self) -> bool: ...


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError("duplicate development manifest fields")
        result[key] = value
    return result


def _hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None


def _port(origin: Any) -> int:
    match = (
        re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})", origin)
        if isinstance(origin, str)
        else None
    )
    if (
        match is None
        or not 1 <= int(match[1]) <= 65535
        or origin != f"http://127.0.0.1:{int(match[1])}"
    ):
        raise RuntimeError("development origin must be a canonical literal loopback HTTP origin")
    return int(match[1])


def load_manifest(path: Path) -> DevManifest:
    try:
        with path.open("rb") as handle:
            raw = handle.read(2049)
        if len(raw) > 2048:
            raise RuntimeError("development manifest exceeds its read bound")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise RuntimeError("cannot read a valid development manifest") from exc
    keys = {
        "format",
        "python_origin",
        "vite_origin",
        "nonce",
        "vite_generation",
        "backend_generation",
        "vite_pid",
    }
    if (
        not isinstance(data, dict)
        or set(data) != keys
        or type(data["format"]) is not int
        or data["format"] != 1
    ):
        raise RuntimeError("invalid development manifest schema")
    python_port, vite_port = _port(data["python_origin"]), _port(data["vite_origin"])
    if python_port == vite_port or type(data["vite_pid"]) is not int or data["vite_pid"] <= 0:
        raise RuntimeError("invalid development listener identity")
    if not _hex(data["nonce"], 64) or not all(
        _hex(data[key], 32) for key in ("vite_generation", "backend_generation")
    ):
        raise RuntimeError("invalid development secret or generation")
    frontend = DevelopmentFrontend(
        data["python_origin"],
        data["vite_origin"],
        data["vite_generation"],
        data["backend_generation"],
        data["vite_pid"],
    )
    return DevManifest(frontend, path.resolve().parent, data["nonce"])


def validate_runtime(manifest: DevManifest, config: DevelopmentRuntime) -> None:
    if config.host != "127.0.0.1" or config.port != _port(manifest.frontend.python_origin):
        raise RuntimeError("development document does not match the React loopback bind")
    if not config.model_calls_disabled or config.usage_fetch_enabled:
        raise RuntimeError("development fixtures must disable models and vendor usage")
    roots = [config.home, config.data_home, str(config.state_dir), config.state_home]
    if not config.store_roots or any(not candidates for candidates in config.store_roots.values()):
        raise RuntimeError("development fixture collector roots are missing")
    roots.extend(
        candidate for candidates in config.store_roots.values() for candidate in candidates
    )
    if any(not Path(root).resolve().is_relative_to(manifest.scratch) for root in roots):
        raise RuntimeError("development fixture roots escape the owned scratch directory")


def signature(manifest: DevManifest, challenge: str) -> str:
    if not _hex(challenge, 64):
        raise RuntimeError("invalid development challenge")
    dev = manifest.frontend
    fields = (
        "cargento-vite-dev-v1",
        challenge,
        dev.python_origin,
        dev.vite_origin,
        dev.vite_generation,
        dev.backend_generation,
        str(dev.vite_pid),
    )
    return hmac.new(
        bytes.fromhex(manifest.nonce), "\n".join(fields).encode("ascii"), hashlib.sha256
    ).hexdigest()


def _bounded_response(
    response: http.client.HTTPResponse, transport: socket.socket, deadline: float
) -> bytes:
    raw = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("development ownership challenge timed out")
        transport.settimeout(remaining)
        part = response.read1(2049 - len(raw))
        raw.extend(part)
        if len(raw) > 2048:
            raise RuntimeError("development ownership response exceeds its read bound")
        if not part or response.isclosed():
            return bytes(raw)


def _interrupt_socket(owned_socket: socket.socket | None, expired: threading.Event) -> None:
    expired.set()
    if owned_socket is not None:
        # Idle socket timeouts do not bound HTTP's internal header/chunk
        # parsing when a listener continuously sends partial lines.
        with suppress(OSError):
            owned_socket.shutdown(socket.SHUT_RDWR)


def _probe(manifest: DevManifest) -> None:
    dev = manifest.frontend
    challenge = secrets.token_hex(32)
    deadline = time.monotonic() + 2
    connection = http.client.HTTPConnection("127.0.0.1", _port(dev.vite_origin), timeout=2)
    transport: socket.socket | None = None
    response: http.client.HTTPResponse | None = None
    expired = threading.Event()

    watchdog = threading.Timer(
        max(0, deadline - time.monotonic()),
        lambda: _interrupt_socket(transport or connection.sock, expired),
    )
    watchdog.daemon = True
    watchdog.start()
    try:
        connection.request(
            "GET",
            "/__cargento_dev_handshake",
            headers={
                "x-cargento-dev-challenge": challenge,
                "x-cargento-dev-generation": dev.backend_generation,
            },
        )
        transport = connection.sock
        if transport is None:
            raise RuntimeError("development ownership connection failed")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("development ownership challenge timed out")
        transport.settimeout(remaining)
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("development listener refused its ownership challenge")
        raw = _bounded_response(response, transport, deadline)
        if expired.is_set() or time.monotonic() >= deadline:
            raise RuntimeError("development ownership challenge timed out")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    except (OSError, http.client.HTTPException, UnicodeError, ValueError, RecursionError) as exc:
        raise RuntimeError("development ownership challenge failed") from exc
    finally:
        watchdog.cancel()
        if response is not None:
            response.close()
        connection.close()
        watchdog.join()
    expected = {
        "format": 1,
        "vite_generation": dev.vite_generation,
        "backend_generation": dev.backend_generation,
        "vite_pid": dev.vite_pid,
    }
    if (
        not isinstance(data, dict)
        or set(data) != {*expected, "signature"}
        or any(
            type(data[key]) is not type(value) or data[key] != value
            for key, value in expected.items()
        )
    ):
        raise RuntimeError("development listener identity does not match its ticket")
    if not _hex(data["signature"], 64) or not hmac.compare_digest(
        data["signature"], signature(manifest, challenge)
    ):
        raise RuntimeError("development listener did not prove ownership")


def admit(path: Path, config: DevelopmentRuntime) -> DevelopmentFrontend:
    manifest = load_manifest(path)
    validate_runtime(manifest, config)
    _probe(manifest)
    return manifest.frontend


def load_page(dev: DevelopmentFrontend) -> bytes:
    """A Python-owned document with fixed admitted module URLs and no secret."""
    origin = dev.vite_origin
    return (
        '<!doctype html><html lang="en"><head><meta charset="UTF-8">'
        "<title>Cargento development</title>"
        f'<meta name="cargento-dev-generation" content="{dev.backend_generation}">'
        f'<link rel="stylesheet" crossorigin="anonymous" href="{origin}/__cargento_dev_fonts.css">'
        '</head><body><div id="root"></div><script type="module">'
        f'import RefreshRuntime from "{origin}/@react-refresh";'
        "RefreshRuntime.injectIntoGlobalHook(window);"
        "window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;"
        "window.__vite_plugin_react_preamble_installed__=true;"
        f'</script><script type="module" src="{origin}/@vite/client"></script>'
        f'<script type="module" src="{origin}/src/main.tsx"></script></body></html>\n'
    ).encode()
