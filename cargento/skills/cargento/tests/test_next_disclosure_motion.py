"""The page's disclosures: two popovers that never move their summary, accordions that ease
open, and no animation replayed by a redraw (owner, 2026-10-02, asks 1 and 5).

The rule is [NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)'s 2026-10-02
amendment: a disclosure whose summary sits in a flex row beside other content is a popover,
and every other disclosure is an accordion. What survives a redraw is
[reader state](docs/design-reader-state.md#the-inventory)'s.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest

from .next_harness import NEXT_STYLES, storage_prelude
from .test_next_drift_panel import FIXTURE, PanelPage

VIEWS = (
    ':is([data-next-view-body="session"],[data-next-view-body="sessions"],'
    '[data-next-view-body="attention"],[data-next-view-body="project"])'
)
SWITCHER = f"{VIEWS} details.next-cockpit-scope-switcher"
DISCLOSURES = (
    "details:is(.next-cockpit-why,[data-next-cockpit-disclosure],"
    ".next-attention-coverage-details):not(.next-menu):not(.next-cockpit-scope-switcher)"
)
POP = f"{VIEWS} details.next-disclose--pop"
SUPPORTS = "@supports selector(::details-content)"
REDUCED = "@media (prefers-reduced-motion:reduce)"
SHEET = re.sub(r"/\*[\s\S]*?\*/", "", NEXT_STYLES)


def rules() -> list[tuple[str, str, str]]:
    """Every rule in the sheet as (enclosing at-rule prelude, selector, body)."""
    found: list[tuple[str, str, str]] = []

    def walk(text: str, context: str) -> None:
        index = 0
        while index < len(text):
            brace = text.find("{", index)
            if brace < 0:
                return
            prelude = text[index:brace].strip()
            depth, end = 1, brace + 1
            while depth and end < len(text):
                depth += {"{": 1, "}": -1}.get(text[end], 0)
                end += 1
            body = text[brace + 1 : end - 1]
            if prelude.startswith("@") and "{" in body:
                walk(body, f"{context} {prelude}".strip())
            else:
                found.append((context, prelude, body))
            index = end

    walk(SHEET, "")
    return found


def rule(selector: str, context: str = "") -> str:
    """The body of the one rule with exactly this selector inside exactly `context`."""
    bodies = [body for ctx, sel, body in rules() if sel == selector and ctx == context]
    if len(bodies) != 1:
        message = f"{len(bodies)} rules for {selector!r} in {context!r}"
        raise AssertionError(message)
    return bodies[0]


def details_tag(html: str, marker: str) -> str:
    """The `<details>` opening tag whose disclosure key ends with `marker`."""
    for match in re.finditer(r"<details\b[^>]*>", html):
        if f'\n{marker}"' in match.group(0) or f':{marker}"' in match.group(0):
            return match.group(0)
    message = f"no <details> for {marker}"
    raise AssertionError(message)


@unittest.skipUnless(shutil.which("node"), "node not available")
class OpenDisclosuresComeBackOpenInTheMarkupTest(PanelPage):
    def test_a_readers_open_caveat_comes_back_open_in_the_markup_so_the_redraw_does_not_animate(
        self,
    ) -> None:
        """A transition runs when `open` flips on a node already in the document, which is the
        reader's own toggle. Written into the markup it is the node's first state, so a poll that
        re-inserts an open disclosure draws it open with nothing to animate."""
        keys = {
            "reentry-why": "cargento\nclaude:focus-1\nreentry-why",
            "later-direction": "cargento\nclaude:focus-1\nlater-direction",
        }
        html = self.page(
            after="".join(
                f"nextCockpitDisclosureStates.set({json.dumps(key)}, true);\n"
                for key in keys.values()
            )
            + "renderNext();\n"
        )
        for name, key in keys.items():
            with self.subTest(disclosure=name):
                self.assertIn(f'data-next-cockpit-disclosure="{key}" open', html)
        # A disclosure the reader left shut stays shut in the markup.
        self.assertNotRegex(details_tag(html, "session-facts"), r"\sopen\b")


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheTwoPopoversNeverMoveTheirSummaryTest(PanelPage):
    def test_opening_why_under_the_header_does_not_move_it(self) -> None:
        html = self.page()
        tag = details_tag(html, "reentry-why")
        self.assertIn("next-disclose--pop", tag)
        start = html.index(tag)
        body = html[start : html.index("</details>", start)]
        # The body is one wrapper, so the CSS can take it out of flow as a unit.
        self.assertRegex(body, r"</summary><div class=\"next-disclose-body\">[\s\S]*</div>$")
        self.assertIn("next-departure-reentry-why", body)
        popover = rule(f"{POP}>.next-disclose-body")
        self.assertIn("position:absolute", popover)
        self.assertIn("inset-inline-end:0", popover)
        self.assertIn("flex:none", rule(POP))
        # The summary is its own width, so opening the popover cannot widen it.
        self.assertIn("inline-size:max-content", rule(f"{POP}>summary"))

    def test_the_sessions_group_caveat_opens_beside_its_title_without_moving_it(self) -> None:
        html = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "navigateNext({view:'sessions'});\nawait __settle();\n"
            "console.log(JSON.stringify(__els.app.innerHTML));",
            storage_prelude({}) + FIXTURE,
        )
        assert isinstance(html, str)
        tag = details_tag(html, "sessions-history-why")
        self.assertIn("next-disclose--pop", tag)
        start = html.index(tag)
        body = html[start : html.index("</details>", start)]
        self.assertIn('</summary><div class="next-disclose-body">', body)
        # The popover is the only kind on the list's header: the two header accordions above
        # the fleet stay in flow.
        self.assertNotIn("next-disclose--pop", details_tag(html, "sessions-board-why"))
        self.assertIn('[data-next-view-body="sessions"]', POP)

    def test_escape_closes_an_open_why_and_keeps_the_reader_on_the_session(self) -> None:
        out = self.page(
            after="""
const summary = {tagName:"SUMMARY", focused:false, focus(){ this.focused = true; },
  closest(){ return null; }};
const popover = {open:true, contains(node){ return node === summary; },
  querySelector(){ return summary; }};
__els.app.querySelectorAll = selector =>
  selector === "details.next-disclose--pop[open]" && popover.open ? [popover] : [];
let prevented = false;
__fire("keydown", {key:"Escape", target:summary, preventDefault(){ prevented = true; }});
__els.app.innerHTML = JSON.stringify({open:popover.open, focused:summary.focused, prevented,
  view:nextRoute.view});
""",
        )
        result = json.loads(out)
        self.assertEqual(
            {"open": False, "focused": True, "prevented": True, "view": "session"}, result
        )

    def test_a_click_outside_an_open_popover_closes_it(self) -> None:
        out = self.page(
            after="""
const inside = {closest(){ return null; }};
const outside = {closest(){ return null; }};
const popover = {open:true, contains(node){ return node === inside; }};
__els.app.querySelectorAll = selector =>
  selector === "details.next-disclose--pop[open]" && popover.open ? [popover] : [];
__fire("click", {target:inside, preventDefault(){}});
const afterInside = popover.open;
__fire("click", {target:outside, preventDefault(){}});
__els.app.innerHTML = JSON.stringify({afterInside, afterOutside:popover.open});
""",
        )
        self.assertEqual({"afterInside": True, "afterOutside": False}, json.loads(out))


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheProjectPageEasesItsDisclosuresTooTest(PanelPage):
    """Verifier F3 (2026-10-02): the owner asked that "each toggle dropdown" ease, and the
    project page, one click from every session crumb, still snapped its "Evidence" disclosures
    open behind the browser's triangle, and its menus with them."""

    def test_the_project_pages_evidence_disclosures_are_in_the_eased_scope(self) -> None:
        html = self._run_page_js(
            "await __settle();\nawait __settle();\n"
            "navigateNext({view:'project', project:'cargento', session:null});\n"
            "await __settle();\nconsole.log(JSON.stringify(__els.app.innerHTML));",
            storage_prelude({}) + FIXTURE,
        )
        assert isinstance(html, str)
        body = html[html.index('data-next-view-body="project"') :]
        evidence = re.findall(r"<details\b[^>]*>\s*<summary>Evidence · [^<]*</summary>", body)
        self.assertGreater(len(evidence), 0)
        for tag in evidence:
            with self.subTest(tag=tag[:60]):
                self.assertIn("data-next-cockpit-disclosure=", tag)
        self.assertIn('[data-next-view-body="project"]', VIEWS)

    def test_the_scope_switcher_and_the_more_menu_ease_and_reduced_motion_gets_none(self) -> None:
        switcher = rule(f"{SWITCHER}::details-content", SUPPORTS)
        self.assertIn("block-size:0", switcher)
        self.assertIn("block-size var(--disclose-dur) var(--disclose-ease)", switcher)
        self.assertIn("opacity var(--disclose-dur) var(--disclose-ease)", switcher)
        self.assertIn("block-size:auto", rule(f"{SWITCHER}[open]::details-content", SUPPORTS))
        menu = rule("details.next-menu::details-content", SUPPORTS)
        self.assertIn("opacity:0", menu)
        self.assertIn("opacity var(--disclose-pop-dur) var(--disclose-ease)", menu)
        self.assertIn("opacity:1", rule("details.next-menu[open]::details-content", SUPPORTS))
        self.assertIn(
            "transition:none",
            rule(
                f"details.next-menu::details-content,{SWITCHER}::details-content",
                f"{SUPPORTS} {REDUCED}",
            ),
        )


class EveryDisclosureEasesOpenAndShutTest(unittest.TestCase):
    def test_every_disclosure_eases_open_and_shut_and_reduced_motion_gets_none(self) -> None:
        accordion = rule(
            f"{VIEWS} {DISCLOSURES}:not(.next-disclose--pop)::details-content", SUPPORTS
        )
        self.assertIn("block-size var(--disclose-dur) var(--disclose-ease)", accordion)
        self.assertIn("opacity var(--disclose-dur) var(--disclose-ease)", accordion)
        self.assertRegex(NEXT_STYLES, r":root\{[^}]*--disclose-ease:ease-in-out")
        self.assertRegex(NEXT_STYLES, r":root\{[^}]*--disclose-dur:200ms")
        self.assertRegex(NEXT_STYLES, r":root\{[^}]*--disclose-pop-dur:160ms")
        self.assertIn("opacity:0", accordion)
        self.assertIn(
            "block-size:auto",
            rule(
                f"{VIEWS} {DISCLOSURES}:not(.next-disclose--pop)[open]::details-content", SUPPORTS
            ),
        )
        # Both reduced-motion rules exist and are separate, because a selector list holding an
        # unsupported pseudo-element would invalidate the marker's rule with it.
        self.assertIn(
            "transition:none",
            rule(f"{VIEWS} {DISCLOSURES}::details-content", f"{SUPPORTS} {REDUCED}"),
        )
        self.assertIn(
            "transition:none",
            rule(f"{VIEWS} {DISCLOSURES}>summary::after", REDUCED),
        )
        # The marker turns rather than swapping glyphs.
        self.assertIn("rotate var(--disclose-dur)", rule(f"{VIEWS} {DISCLOSURES}>summary::after"))
        self.assertIn("list-style:none", rule(f"{VIEWS} {DISCLOSURES}>summary"))

    def test_nothing_replays_on_a_redraw(self) -> None:
        """`@starting-style` and keyframes on an open disclosure both run again every time a poll
        re-inserts the node, so neither may be used for a disclosure."""
        self.assertNotIn("@starting-style", SHEET)
        for _context, selector, body in rules():
            if re.search(r"details|\[open\]|summary", selector):
                with self.subTest(selector=selector[:80]):
                    self.assertNotRegex(body, r"(^|;)\s*animation(-name)?\s*:")

    def test_the_more_menu_opens_below_its_button(self) -> None:
        self.assertIn("top:calc(100% + 4px)", rule(".next-menu-items"))
        self.assertNotIn("top:26px", rule(".next-menu-items"))


if __name__ == "__main__":
    unittest.main()
