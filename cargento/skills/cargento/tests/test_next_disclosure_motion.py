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

from .next_harness import NEXT_APP_JS, NEXT_STYLES, NextPageJsHarness, storage_prelude
from .test_next_analyze_flow import CONSENT_NEEDED
from .test_next_drift_panel import FIXTURE, PanelPage, routes

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

    def test_on_a_narrow_screen_the_sessions_caveat_opens_from_its_start_edge(self) -> None:
        """Verifier R-2, measured at 375px: under 620px the group header stacks into a column,
        so "What recent means" sits at the left (x=19), and a 343px body hung from its end edge
        ran from x=-169 to x=174, half of every line off the screen and out of scroll's reach.
        In the column the summary is always at the start, so the body hangs from that edge. The
        header's "Why" stays end-anchored: it ends a `flex-end` row at every width."""
        narrow = rule(
            ".next-operation-group>header>details.next-disclose--pop>.next-disclose-body",
            "@media(max-width:620px)",
        )
        self.assertIn("inset-inline-start:0", narrow)
        self.assertIn("inset-inline-end:auto", narrow)
        # The column rule this relies on, in the same step.
        self.assertIn(
            "flex-direction:column",
            rule(".next-operation-group>header", "@media(max-width:620px)"),
        )
        self.assertIn(
            "align-items:flex-start",
            rule(".next-operation-group>header", "@media(max-width:620px)"),
        )

    def test_what_is_sent_opens_as_a_popover_under_analyze_and_never_over_it(self) -> None:
        """Owner, 2026-10-02: "What is sent to <provider>" opens "in a popup just like the
        'Why' popup" at the top of the page. Same system: `next-disclose--pop`, one body
        wrapper taken out of flow, so opening it moves neither its summary nor Analyze. It
        hangs from its summary's start edge across the card's width, so it stays inside the
        viewport at every width the card does, and it opens downward from a summary drawn
        after Analyze, so it never covers that control."""
        html = self.page("codex", CONSENT_NEEDED)
        tag = details_tag(html, "reading-sent")
        self.assertIn("next-disclose--pop", tag)
        self.assertIn("next-cockpit-reading-sent", tag)
        start = html.index(tag)
        body = html[start : html.index("</details>", start)]
        self.assertRegex(body, r"</summary><div class=\"next-disclose-body\">[\s\S]*</div>$")
        items = re.findall(r"<li>([\s\S]*?)</li>", body)
        self.assertEqual(len(routes()["codex"]["disclosure_parts"]), len(items))
        ask = html.index('data-next-cockpit-action="reading-ask"')
        self.assertLess(ask, start)
        sent = f"{POP}.next-cockpit-reading-sent"
        self.assertIn("inline-size:100%", rule(sent))
        anchored = rule(f"{sent}>.next-disclose-body")
        for declaration in (
            "inset-inline-start:0",
            "inset-inline-end:0",
            "inline-size:auto",
            "max-inline-size:var(--measure)",
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, anchored)
        # Downward from the summary, as every popover body opens.
        self.assertIn("inset-block-start:calc(100% + 4px)", rule(f"{POP}>.next-disclose-body"))
        self.assertNotIn("inset-block-end", anchored)

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

    def test_focus_leaving_an_open_popover_closes_it(self) -> None:
        """Verifier R-1, measured at 1440x900: the header's open "Why" covers the Intent panel's
        "Saved" summary whole, and a keyboard reader who Tabs on from "Why" lands on it, hidden
        (WCAG 2.4.11). Focus leaving the popover for another control closes it, as a click outside
        does. Focus that goes nowhere, to another window or with a redraw that replaced the node,
        leaves it open, so a poll never shuts a body the reader is reading."""
        out = self.page(
            after="""
const summary = {tagName:"SUMMARY"};
const popover = {open:true, contains(node){ return node === summary; }};
summary.closest = selector =>
  selector === "details.next-disclose--pop[open]" && popover.open ? popover : null;
const saved = {tagName:"SUMMARY", closest(){ return null; }};
const seen = {};
__fire("focusout", {target:summary, relatedTarget:summary});
seen.inside = popover.open;
__fire("focusout", {target:summary, relatedTarget:null});
seen.nowhere = popover.open;
__fire("focusout", {target:summary, relatedTarget:saved});
seen.away = popover.open;
seen.view = nextRoute.view;
__els.app.innerHTML = JSON.stringify(seen);
""",
        )
        self.assertEqual(
            {"inside": True, "nowhere": True, "away": False, "view": "session"}, json.loads(out)
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


def top_level_selectors(selector_list: str) -> list[str]:
    """A selector list split at its own commas, never at the commas inside `:is(...)`."""
    parts, depth, start = [], 0, 0
    for index, char in enumerate(selector_list):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            parts.append(selector_list[start:index].strip())
            start = index + 1
    parts.append(selector_list[start:].strip())
    return parts


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
            rule(
                f"{VIEWS} {DISCLOSURES}:not(.next-disclose--pop)::details-content,"
                f"{POP}::details-content",
                f"{SUPPORTS} {REDUCED}",
            ),
        )
        self.assertIn(
            "transition:none",
            rule(f"{VIEWS} {DISCLOSURES}>summary::after", REDUCED),
        )
        # The marker turns rather than swapping glyphs.
        self.assertIn("rotate var(--disclose-dur)", rule(f"{VIEWS} {DISCLOSURES}>summary::after"))
        self.assertIn("list-style:none", rule(f"{VIEWS} {DISCLOSURES}>summary"))

    def test_a_reader_who_asks_for_less_motion_gets_none_on_every_eased_disclosure(self) -> None:
        """Measured in Chrome 156 with reduced motion emulated: the accordion still eased, because
        its base selector carries `:not(.next-disclose--pop)` and the reduced rule did not, so the
        base rule out-ranked `transition:none`. A presence check passed over that. So every rule
        that eases a disclosure needs a reduced-motion rule with the SAME selector, which can never
        lose on specificity, and nothing it sets may move."""
        reduced = {
            one: body
            for context, selector, body in rules()
            if REDUCED in context
            for one in top_level_selectors(selector)
        }
        eased = [
            (selector, body)
            for context, selector, body in rules()
            if REDUCED not in context
            and re.search(r"details|summary", selector)
            and re.search(r"(^|;)\s*transition\s*:(?!\s*none)", body)
        ]
        self.assertTrue(eased, "no eased disclosure rule was found")
        for selector, _body in eased:
            with self.subTest(selector=selector[:100]):
                self.assertIn(selector, reduced, "this eased rule has no reduced-motion twin")
                self.assertRegex(reduced[selector], r"(^|;)\s*transition\s*:\s*none")

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


# A summary inside a view, as `closest` answers for it; anything else is outside the page's views.
FAKE_SUMMARY = """
const __summary = {tagName: "SUMMARY", closest: s => s === "summary" ? __summary
  : s === "[data-next-view-body]" ? {} : null};
"""
MOTION_PROBE = """
const __painted = [];
const __at = () => new Promise(r => setTimeout(r, 0));
nextPaintAfterMotion(() => __painted.push("before"));
__fire("click", {target: __summary});
nextPaintAfterMotion(() => __painted.push("held-1"));
nextPaintAfterMotion(() => __painted.push("held-2"));
const __right_after = __painted.slice();
await new Promise(r => setTimeout(r, 300));
console.log(JSON.stringify({right_after: __right_after, later: __painted}));
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class ABackgroundPaintWaitsOutTheReadersOwnToggleTest(NextPageJsHarness):
    """Measured in headless Chrome 156: the project-context paint lands about 100ms after each
    poll and replaced an easing accordion with one already open, so it snapped halfway, on every
    open that met a paint. A background paint now waits out the reader's own toggle."""

    def probe(self, setup: str = "") -> dict[str, list[str]]:
        out = self._run_page_js(
            "await __settle();\n" + FAKE_SUMMARY + setup + MOTION_PROBE,
            storage_prelude({}) + FIXTURE,
        )
        assert isinstance(out, dict)
        return out

    def test_a_paint_during_the_readers_toggle_lands_once_after_the_motion(self) -> None:
        out = self.probe()
        self.assertEqual(["before"], out["right_after"])
        # Coalesced: the newest paint draws the newest data, once.
        self.assertEqual(["before", "held-2"], out["later"])

    def test_a_reader_who_asks_for_less_motion_is_never_kept_waiting(self) -> None:
        out = self.probe(
            "window.matchMedia = q => ({matches: q.includes('prefers-reduced-motion')});\n"
        )
        self.assertEqual(["before", "held-1", "held-2"], out["right_after"])

    def test_a_click_outside_a_summary_holds_nothing(self) -> None:
        out = self.probe("__summary.closest = () => null;\n")
        self.assertEqual(["before", "held-1", "held-2"], out["right_after"])

    def test_the_poll_and_the_context_fetch_both_paint_through_the_hold(self) -> None:
        self.assertIn(
            "nextPaintAfterMotion(() => {\n    try{\n      renderNext(focus);", NEXT_APP_JS
        )
        context = NEXT_APP_JS[NEXT_APP_JS.index("function nextCockpitLoadContext") :][:1400]
        self.assertIn("nextPaintAfterMotion(() => renderNext())", context)


POPOVER_PROBE = """
const __scrolled = [];
const __body = {scrollIntoView: options => __scrolled.push(options)};
const __pop = {tagName: "DETAILS", open: false,
  classList: {contains: name => name === "next-disclose--pop"},
  contains: () => true, querySelector: s => s === ".next-disclose-body" ? __body : null};
const __sum = {tagName: "SUMMARY", parentElement: __pop, closest: s => s === "summary" ? __sum : null};
__fire("click", {target: __sum});
__pop.open = true;  // the browser's own toggle, which runs after the handlers
await new Promise(r => setTimeout(r, 20));
const __opened = __scrolled.slice();
__fire("click", {target: __sum});  // now open: this press shuts it
__pop.open = false;
await new Promise(r => setTimeout(r, 20));
console.log(JSON.stringify({opened: __opened, after_close: __scrolled.length}));
"""


@unittest.skipUnless(shutil.which("node"), "node not available")
class APopoverOpensWhollyOnTheScreenTest(NextPageJsHarness):
    """Measured at 1440x800: the "What is sent" body is 487px tall and ended 74px below the
    window. A scroll box inside it would lose its place on every poll, which the reader-state
    inventory forbids, so the page scrolls just far enough to show it, once, when the reader
    opens it."""

    def test_opening_a_popover_brings_its_whole_body_into_view_once(self) -> None:
        out = self._run_page_js(
            "await __settle();\n" + POPOVER_PROBE, storage_prelude({}) + FIXTURE
        )
        assert isinstance(out, dict)
        self.assertEqual(1, len(out["opened"]))
        self.assertEqual("nearest", out["opened"][0]["block"])
        self.assertEqual(1, out["after_close"], "closing must not scroll")
