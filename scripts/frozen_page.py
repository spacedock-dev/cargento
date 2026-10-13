"""The previous interface's script parts, kept for the paused Intent and drift study only.

The dashboard no longer ships or serves them. They live here, outside the plugin, because the
recorded study evaluates this text (`drift_replay.py` runs it through `drift_page.js`) and its
closure ledger binds the digest of `load_script()`: a changed byte would unfreeze the study
without a word. Nothing in `compass_runtime`, the plugin, the standalone binary or the built page
reads them. `compass/skills/compass/tests` cannot see this directory, so
`scripts/tests/test_frozen_page.py` pins every part and the concatenation.
"""

from __future__ import annotations

from pathlib import Path

FROZEN_DIR = Path(__file__).resolve().parent / "frozen-page"

# In the order the old page concatenated them into one scope.
APP_PARTS: tuple[str, ...] = (
    "next-boot.js",
    "next-observed.js",
    "next-attention.js",
    "next-notify.js",
    "next-cockpit-compat.js",
    "project.js",
    "next-chrome.js",
    "next-capacity.js",
    "next-sessions.js",
    "next-projects.js",
    "next-project.js",
    "next-intent.js",
    "next-activity.js",
    "next-session.js",
    "next-workstream.js",
    "next-delegation.js",
    "next-controls.js",
    "next-cockpit.js",
    "next-render.js",
    "next-live.js",
)


def load_script() -> str:
    """Return the previous interface's script parts, in order, as one text (study replay only)."""
    pieces = []
    for name in APP_PARTS:
        text = (FROZEN_DIR / name).read_text(encoding="utf-8")
        if not text.strip():
            msg = f"{name} is empty"
            raise RuntimeError(msg)
        pieces.append(text)
    return "".join(pieces)
