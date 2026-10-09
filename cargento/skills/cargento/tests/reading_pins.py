"""Pins that let a reading-route test run the same on every runner.

`reading_route.destination` names where tool output goes from the machine's OS, home and
endpoint settings, and on Windows it names nothing by design. These stand a Linux machine
that names the vendor in its place.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any, Self
from unittest import mock

from cargento_runtime import reading_route

_REAL_DESTINATION = reading_route.destination


def named_platform() -> Any:
    """Pin the OS the destination resolver reads to one where it can name one.

    On Windows the resolver never names a destination, by design, so a test
    that means "a machine where the destination can be named" pins Linux and
    runs the same on every runner.
    """
    return _Pins(
        mock.patch.object(platform, "system", return_value="Linux"),
        mock.patch.object(reading_route, "_account", _named_account),
    )


def _named_account(environ: Any) -> tuple[str, str]:
    """A home and a user wherever the environment leaves them out.

    The resolver falls back to the password file, and Windows has none, so an
    unpinned account named nothing on windows-latest and every route there
    said "wherever your settings send it".
    """
    return (
        environ.get("HOME") or "/home/cargento-test",
        environ.get("USER") or "cargento-test",
    )


class _Pins:
    """Several patchers that start and stop together, as a context or by hand."""

    def __init__(self, *patchers: Any) -> None:
        self._patchers = patchers

    def start(self) -> None:
        for patcher in self._patchers:
            patcher.start()

    def stop(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def named_machine(environ: dict[str, str] | None = None) -> Any:
    """Every unpinned `destination` call reads a machine that names the vendor.

    A route's `To:` item says what `destination` names (verifier ui4 C1), so a
    test that resolves a route without its own `environ` and `root` would say
    what this runner's environment and OS say: nothing on Windows, a host
    under a developer's `ANTHROPIC_BASE_URL`. This pins Linux, no endpoint
    variable and an empty root wherever the caller left them unset. `environ`
    is the daemon's environment in their place, for a test of a machine whose
    endpoint setting moved.
    """
    # The resolver as shipped, not whatever a stub entered earlier has put in
    # its place: a socket test's model stub pins a constant destination.
    real = _REAL_DESTINATION
    pinned = {} if environ is None else dict(environ)

    def named(
        provider: str,
        *,
        environ: Any = None,
        root: Path | None = None,
        system: str | None = None,
    ) -> str:
        return real(
            provider,
            environ=pinned if environ is None else environ,
            root=Path("/nonexistent-cargento-root") if root is None else root,
            system="Linux" if system is None else system,
        )

    return _Pins(
        mock.patch.object(reading_route, "destination", named),
        mock.patch.object(reading_route, "_account", _named_account),
    )
