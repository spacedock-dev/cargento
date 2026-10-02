from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import reading_route
from cargento_runtime.web import page as frontend_page

from .page_harness import PageJsHarness

NEXT_WEB_DIR = frontend_page.WEB_DIR
NEXT_APP_JS = frontend_page.load_script()
NEXT_STYLES = (NEXT_WEB_DIR / "styles.css").read_text(encoding="utf-8")
NEXT_PAGE_TEXT = (
    (NEXT_WEB_DIR / "index.html")
    .read_text(encoding="utf-8")
    .replace("{{CARGENTO_STYLES}}", NEXT_STYLES)
    .replace("{{CARGENTO_APP}}", NEXT_APP_JS)
)


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

    def __enter__(self) -> _Pins:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def named_machine() -> Any:
    """Every unpinned `destination` call reads a machine that names the vendor.

    A route's `To:` item says what `destination` names (verifier ui4 C1), so a
    test that resolves a route without its own `environ` and `root` would say
    what this runner's environment and OS say: nothing on Windows, a host
    under a developer's `ANTHROPIC_BASE_URL`. This pins Linux, no endpoint
    variable and an empty root wherever the caller left them unset.
    """
    real = reading_route.destination

    def named(
        provider: str,
        *,
        environ: Any = None,
        root: Path | None = None,
        system: str | None = None,
    ) -> str:
        return real(
            provider,
            environ={} if environ is None else environ,
            root=Path("/nonexistent-cargento-root") if root is None else root,
            system="Linux" if system is None else system,
        )

    return _Pins(
        mock.patch.object(reading_route, "destination", named),
        mock.patch.object(reading_route, "_account", _named_account),
    )


def published_routes(*harnesses: str, installed: tuple[str, ...] = ("codex",)) -> str:
    """The server's own `reading_routes` for these harnesses, as a JS literal.

    Resolved by `reading_route` on a machine with `installed` on PATH and the
    shipped gates, so a fixture carries the sentence a reader would see rather
    than one written for the test.
    """
    # No endpoint setting and a platform whose settings the resolver reads, so
    # neither this machine's environment nor its OS (Windows names nothing)
    # decides what a page fixture says about where tool output goes.
    with named_platform():
        routes = reading_route.resolve_all(
            harnesses,
            binary_resolver=lambda name: f"/usr/local/bin/{name}" if name in installed else None,
            environ={},
            root=Path("/nonexistent-cargento-root"),
        )
    return json.dumps(routes)


def storage_prelude(seed: dict[str, str], *, location_hash: str = "") -> str:
    """Install observable browser storage before the dashboard bundle loads."""
    return f"""
let __store = {json.dumps(seed)};
let __storageReads = [];
let __storageWrites = [];
const localStorage = {{
  getItem(k){{
    __storageReads.push(k);
    return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null;
  }},
  setItem(k, v){{
    __storageWrites.push(k);
    __store[k] = String(v);
  }},
  removeItem(k){{
    __storageWrites.push(k);
    delete __store[k];
  }}
}};
const navigator = {{}};
location.hash = {json.dumps(location_hash)};
"""


class NextPageJsHarness(PageJsHarness):
    """Run the independently assembled next-UI script under the shared DOM stubs."""

    APP_JS = NEXT_APP_JS
