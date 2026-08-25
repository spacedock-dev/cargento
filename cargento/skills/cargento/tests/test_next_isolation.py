from __future__ import annotations

import json
import shutil
import unittest
from typing import Any, ClassVar

from . import test_page_calm
from .next_harness import NextPageJsHarness
from .page_harness import PageJsHarness


def storage_prelude(seed: dict[str, str], *, location_hash: str = "") -> str:
    """Install observable browser storage before either bundle loads."""
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


@unittest.skipUnless(shutil.which("node"), "node not available")
class ExistingBundleIsolationTest(PageJsHarness):
    """Freeze the existing page against state owned by the next UI."""

    # This is the order-one firewall inherited by the rest of the milestone.
    # Later next-UI work adds behavior behind these names; it does not relax
    # this fixture to make that behavior pass.
    NEXT_STATE: ClassVar[dict[str, str]] = {
        "cargento.next.guardrails.recce": '["keep tests green"]',
        "cargento.next.leader": '{"id":"next-tab","ts":999000}',
        "cargento.next.revision": "next-revision",
    }

    def render_board(self, seed: dict[str, str]) -> Any:
        return self._run_page_js(
            test_page_calm.CalmModeTest.FIXTURE
            + """
render(board());
console.log(JSON.stringify({
  html: __els.app.innerHTML,
  nextReads: __storageReads.filter(k => k.startsWith("cargento.next.")),
  nextWrites: __storageWrites.filter(k => k.startsWith("cargento.next."))
}));
""",
            prelude=storage_prelude(seed),
        )

    def test_next_hash_grammar_cannot_activate_the_existing_session_view(self) -> None:
        out = self._run_page_js(
            """
console.log(JSON.stringify({
  mode: displayMode,
  hash: location.hash,
  wroteDisplayMode: __storageWrites.includes(DISPLAY_MODE_KEY)
}));
""",
            prelude=storage_prelude({}, location_hash="#n=session:claude:abc"),
        )

        self.assertEqual("regular", out["mode"])
        self.assertEqual("#n=session:claude:abc", out["hash"])
        self.assertFalse(out["wroteDisplayMode"])

    def test_next_storage_namespace_cannot_change_the_existing_render(self) -> None:
        baseline = self.render_board({})
        seeded = self.render_board(self.NEXT_STATE)

        self.assertEqual(baseline["html"], seeded["html"])
        self.assertEqual([], seeded["nextReads"])
        self.assertEqual([], seeded["nextWrites"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextBundleIsolationTest(NextPageJsHarness):
    """Keep the next UI out of the existing bundle's shared-origin lease."""

    def test_next_bundle_does_not_read_or_write_the_existing_leader_lease(self) -> None:
        lease = '{"id":"existing-tab","ts":999000}'
        out = self._run_page_js(
            """
console.log(JSON.stringify({
  leader: __store["cargento.leader"],
  readLeader: __storageReads.includes("cargento.leader"),
  wroteLeader: __storageWrites.includes("cargento.leader")
}));
""",
            prelude=storage_prelude({"cargento.leader": lease}),
        )

        self.assertEqual(lease, out["leader"])
        self.assertFalse(out["readLeader"])
        self.assertFalse(out["wroteLeader"])


if __name__ == "__main__":
    unittest.main()
