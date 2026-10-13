"""Home selection for the local store, shared by the operator scripts."""

from __future__ import annotations

import os


def default_home(home: str | None = None) -> str:
    return os.path.join(os.path.expanduser("~") if home is None else home, ".compass")


def store_home() -> str:
    override = os.environ.get("COMPASS_HOME")
    return override if override and override.strip() else default_home()
