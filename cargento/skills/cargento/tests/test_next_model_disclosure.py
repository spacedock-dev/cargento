"""The selected Claude model reaches the real assembled page before consent."""

from __future__ import annotations

import dataclasses
import re
import shutil
import unittest
from unittest import mock

from cargento_runtime import annotations, reading_route

from . import test_next_analyze_flow as flow
from . import test_next_drift_panel as panel
from .support import make_config
from .visible_text import visible_text


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePageDisclosesItsSelectedClaudeModel(panel.PanelPage):
    def test_own_and_fallback_routes_name_the_selection_before_allow(self) -> None:
        for model in ("claude-sonnet-5-5", "claude-sonnet-5", "claude-opus-6"):
            for harness in ("claude", "codex"):
                with (
                    self.subTest(model=model, harness=harness),
                    mock.patch.object(
                        annotations, "provider_enabled", lambda name: name == "claude"
                    ),
                ):
                    routed = reading_route.resolve_all(
                        (harness,),
                        binary_resolver=lambda name: (
                            "/usr/local/bin/claude" if name == "claude" else None
                        ),
                        environ={},
                        config=dataclasses.replace(make_config(), claude_reading_model=model),
                    )
                    html = self.page(
                        harness,
                        flow.CONSENT_NEEDED,
                        routed=dict(routed),
                        after=flow.FIRST_PRESS + flow.SHOW_POSTS,
                    )
                    card = flow.CARD.search(panel.drift_of(html))
                    self.assertIsNotNone(card)
                    assert card is not None
                    items = re.findall(r"<li>([\s\S]*?)</li>", card.group(0))
                    self.assertIn(f"using {model}", visible_text(" ".join(items)))
                    self.assertIn('<i data-posts="0"></i>', html)
