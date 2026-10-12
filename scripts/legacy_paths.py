"""Temporary home selection and environment lookup for pre-Compass local names."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def environment_value(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name)
    # legacy-cargento: remove at 1.0.0
    if name not in environ:
        value = environ.get(name.replace("COMPASS_", "CARGENTO_", 1))
    return value


def default_home(home: str | None = None) -> str:
    home = os.path.expanduser("~") if home is None else home
    current = os.path.join(home, ".compass")
    # legacy-cargento: remove at 1.0.0
    if not os.path.lexists(current) and os.path.isdir(os.path.join(home, ".cargento")):
        return os.path.join(home, ".cargento")
    return current


def store_home() -> str:
    override = environment_value(os.environ, "COMPASS_HOME")
    return override if override and override.strip() else default_home()
