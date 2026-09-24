from __future__ import annotations

import base64
import hashlib
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast
from unittest import mock

from cargento_runtime.web import page as frontend_page

from . import css_cascade
from .next_harness import NextPageJsHarness

if TYPE_CHECKING:
    from collections.abc import Callable


# --- The size guard's parser (DRC-4596) ---------------------------------------
#
# What it can see, and what it cannot. Every function below reads ONE rule at a
# time out of the stylesheet text. That is deliberate -- the alternative costed
# at triage, a selector-prefix scope plus a suffix allowlist, inspects 137 rules
# and fails 68, so the only route to green is a ~70-entry allowlist maintained
# by whoever is trying to get CI green. At that size the allowlist is the
# specification and the assertion measures nothing.
#
# The cost of reading one rule at a time is a blind spot that is structural, not
# a parser weakness, and it is stated here rather than implied away: where a
# sentence takes its size from one rule, its family from a second and its
# line-height from a third, no regex can join them. Two such sentences render
# today -- `.next-operation-fact--unknown strong` (163 strings at 12.5px) and
# `.next-cockpit-recovery small` (18 strings at 12.5px). Neither is in any
# census below, and neither is caught by any assertion here. THIS GUARD DOES NOT
# ESTABLISH A UNIVERSAL 15px FLOOR and must not be cited as one; DRC-4602 sizes
# the residual and only a computed style sees the composed class. A size guard
# that passed while sentences rendered below its claimed floor would be this
# milestone's own defect shipped as its remedy.
#
# Every function takes CSS TEXT rather than a path, so the mutant tests can feed
# a modified copy through the same code without touching the working tree -- no
# byte-pin oracle moves, and the falsifier is a committed test rather than a
# procedure someone promises they ran.

SENTENCE_FLOOR_REM = css_cascade.rem(15.0)
"""Written as a literal, never read from `--fs-sentence`.

Reading the floor out of the token makes every assertion below vacuous:
retuning `--fs-sentence` to 12px in a scratch copy took the sub-floor census
from 19 rules to 0 while the test stayed green.
"""

LABEL_FLOOR_REM = css_cascade.rem(13.0)
"""The v3 label step, which is also the smallest of the five type tokens.

v0.27.0 put this at 11px, where `--fs-label` and `--fs-machine` both sat. v3
deleted every sub-13px step, so the floor and the smallest token moved
together and the zero margin `test_the_root_type_tokens_hold_the_label_floor`
asserts is preserved rather than restored.
"""


def _css_body(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _type_tokens(css: str) -> dict[str, float]:
    """The `--fs-*` table from the single `:root` block."""
    roots = re.findall(r"(?:\A|\n):root\{([^}]*)\}", _css_body(css), re.DOTALL)
    if len(roots) != 1:
        raise AssertionError(f"expected exactly one :root block, found {len(roots)}")
    return {
        name: float(value)
        for name, value in re.findall(r"--(fs-[a-z0-9-]+):([0-9.]+)rem", roots[0])
    }


def _rules(css: str) -> list[tuple[str, str]]:
    """Every rule as (selector text, declarations), `:root` and at-rules dropped."""
    out: list[tuple[str, str]] = []
    for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", _css_body(css)):
        selector = block.group(1).strip()
        if not selector or selector.startswith(("@", ":root")):
            continue
        out.append((selector, block.group(2)))
    return out


def _declared_size(decls: str, tokens: dict[str, float]) -> float | None:
    """The size a rule declares, resolving `var(--fs-*)` against `:root` first.

    Without the indirection every rule in scope declares a token name rather
    than a number, so a literal scan passes all of them and measures nothing.
    """
    token = re.search(r"font-size:\s*var\(--(fs-[a-z0-9-]+)\)", decls) or re.search(
        r"font:[^;]*?var\(--(fs-[a-z0-9-]+)\)", decls
    )
    if token:
        return tokens.get(token.group(1))
    # The lookbehind keeps `font:10.5px/1.5` from matching the weight slot; the
    # same defect in an earlier draft resolved that shorthand to 0.5px.
    literal = re.search(r"font-size:\s*([0-9.]+)rem", decls) or re.search(
        r"font:[^;{}]*?(?<![0-9.])([0-9.]+)rem", decls
    )
    return float(literal.group(1)) if literal else None


def _declared_line_height(decls: str) -> float | None:
    """A rule's own prose line-height, from the longhand or the `font:` slash slot.

    The shorthand alternative is load-bearing: the sentence rules in this sheet
    are written `font:500 var(--fs-sentence)/1.55 var(--sans)`, and a pattern
    that only accepted a px literal before the slash saw 25 sentence rules where
    there are 68.
    """
    longhand = re.search(r"line-height:\s*([0-9.]+)", decls)
    if longhand:
        return float(longhand.group(1))
    shorthand = re.search(r"font:[^;{}]*?(?:[0-9.]+rem|var\(--fs-[a-z0-9-]+\))/([0-9.]+)", decls)
    return float(shorthand.group(1)) if shorthand else None


def _is_mono(decls: str) -> bool:
    return "var(--mono)" in decls or "monospace" in decls


def _sentence_census(css: str) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """Split every sentence-tier rule into (at or above the floor, below it).

    Membership is the test `docs/design-next-ui.md` states under "Type scale":
    a rule is on the sentence tier when it sets its text in sans and declares
    its own prose line-height. Derived from what the rule declares, so it cannot
    become the structurally-present default AGENTS.md warns about, and it needs
    no allowlist.
    """
    tokens = _type_tokens(css)
    above: list[tuple[str, float]] = []
    below: list[tuple[str, float]] = []
    for selector, decls in _rules(css):
        if _is_mono(decls):
            continue
        height = _declared_line_height(decls)
        if height is None or height < 1.3:
            continue
        size = _declared_size(decls, tokens)
        if size is None:
            continue
        (above if size >= SENTENCE_FLOOR_REM else below).append((selector, size))
    return above, below


def _sub_label_floor_literals(css: str) -> set[tuple[str, float]]:
    """Every px literal below the label floor, written outside `:root`."""
    found: set[tuple[str, float]] = set()
    for selector, decls in _rules(css):
        sizes = [float(value) for value in re.findall(r"font-size:\s*([0-9.]+)rem", decls)]
        sizes += [
            float(value) for value in re.findall(r"font:[^;{}]*?(?<![0-9.])([0-9.]+)rem", decls)
        ]
        found.update((selector, size) for size in sizes if size < LABEL_FLOOR_REM)
    return found


def _absence_rules(css: str) -> list[tuple[str, str]]:
    """Rules whose selector names an absence, by the sheet's own convention.

    Derived from the convention -- an `-absent` class-name segment, or the
    withheld attribute -- rather than from a list of the spellings someone
    happened to think of. The list this replaces held three markers,
    `--absent`, `[data-next-withheld]` and `-clause-absent`, and matched 8 of
    the 14 rules that carry one. `.next-capacity-absent`,
    `.next-session-absent`, `.next-cockpit-held-absent` and
    `.next-cockpit-work-absent` spell the marker with a single hyphen, so the
    guard could not see them, and all four spelled their ink `var(--ink3)`
    directly rather than through `--ink-absence`: repointing the register
    would have left them behind with this test green. That is the
    enumerated-verifier defect this milestone has now shipped five times, and
    the point of deriving is that the next absence emitter arrives inside the
    guard instead of beside it.

    `\\b` at the end, so a hypothetical `-absentee` cannot match. The grouped
    selectors this found were split rather than repointed whole:
    `.next-capacity-slack` is a figure (`~N% spare at reset`) and
    `.next-cockpit-work-dropped` is a bound on rows that DID render, so
    neither belongs on the absence register even though each shared a rule
    with something that does.
    """
    return [
        (sel, decls)
        for sel, decls in _rules(css)
        if re.search(r"-absent\b", sel) or "[data-next-withheld]" in sel
    ]


def _tier_selectors(css: str) -> dict[str, float]:
    """Each INDIVIDUAL selector its own rule puts on the sentence tier.

    Grouped selectors are split, which is the whole point: the census reads a
    rule's declaration, and a grouped rule declares for several elements at
    once. `.next-guardrail-copy small` was declared at 15px inside one group
    and at 12.5px by the next rule -- both (0,1,1), later wins -- so the
    per-rule reading called an element compliant while it rendered below the
    floor. Neither selector STRING appears twice, so no string comparison can
    see it; only resolving the element can.
    """
    tokens = _type_tokens(css)
    found: dict[str, float] = {}
    for selector, decls in _rules(css):
        if _is_mono(decls):
            continue
        height = _declared_line_height(decls)
        size = _declared_size(decls, tokens)
        if height is None or height < 1.3 or size is None or size < SENTENCE_FLOOR_REM:
            continue
        for raw in selector.split(","):
            part = raw.strip()
            if part:
                found[part] = size
    return found


class TheCompliantSetIsResolvedOnElementsNotOnRulesTest(unittest.TestCase):
    """DRC-4596 AC-6, which asks what an element RENDERS at.

    Every other guard in this module reads what a rule DECLARES. That is a fact
    about the rule, and the two part company the moment a second rule at equal
    specificity names the same element: the later one wins and the element
    renders at a size its own tier rule never mentions. Measured here, and
    independently with `getComputedStyle` in headless Chrome, which is the
    method the criterion itself names.

    **This is the direction `docs/design-next-ui.md` said was safe.** That file
    said a per-rule census "will understate the set". It can also OVERSTATE it,
    by reading a rule as compliant when a later equal-specificity rule takes the
    element below the floor. The sentence is corrected there with the mechanism
    named, because "understate" and "overstate" have different causes and only
    one of them was written down.
    """

    tokens: ClassVar[dict[str, float]]
    rules: ClassVar[list[tuple[str, str, int]]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tokens, cls.rules = css_cascade.load(frontend_page.WEB_DIR / "styles.css")

    # Selectors some rule declares at or above the floor and another declares
    # below it. Straddling is legal -- in all eight of these the COMPLIANT rule
    # is the one that wins -- but it is the precondition for the defect, so the
    # set is pinned and a ninth has to be looked at rather than discovered by a
    # reader. `.next-guardrail-copy small` was the ninth: it straddled with the
    # sub-floor rule winning, and it is gone from this list because the sheet no
    # longer declares a size it immediately overrides.
    STRADDLING: ClassVar[frozenset[str]] = frozenset(
        {
            ".next-capacity-pct",
            ".next-cockpit-decision-summary",
            ".next-cockpit-memos label>small",
            ".next-cockpit-now-state small",
            # v3 added this one: the recovery cell declares strong and small at
            # the sentence tier together and then pulls small back to the label
            # tier on the next line. Reviewed, and it is the intended shape -- a
            # small there is a caption, and 13px is where a caption belongs.
            ".next-cockpit-recovery small",
            ".next-cockpit-recovery>div",
            # And this one, which straddles only across a media query: the tab
            # sizes down at the narrow breakpoint. A tab is a control rather
            # than a sentence, so neither side is a floor violation.
            ".next-cockpit-tabs button",
            ".next-cockpit-viewing-session",
            ".next-project-workflow-definition>small",
        }
    )

    @staticmethod
    def _straddling(css: str) -> set[str]:
        tokens = _type_tokens(css)
        sides: dict[str, set[bool]] = {}
        for selector, decls in _rules(css):
            size = _declared_size(decls, tokens)
            if size is None:
                continue
            for part in selector.split(","):
                cleaned = part.strip()
                if cleaned:
                    sides.setdefault(cleaned, set()).add(size >= SENTENCE_FLOOR_REM)
        return {part for part, seen in sides.items() if len(seen) == 2}

    @staticmethod
    def _below_floor(
        css: str, tokens: dict[str, float], rules: list[tuple[str, str, int]]
    ) -> tuple[dict[str, float], int]:
        """Tier selectors whose ELEMENT resolves below the floor, and the skips.

        The skip count comes back rather than being swallowed. A selector form
        the resolver cannot express is silently not checked, and today there
        are none -- 77 swept, 77 resolved, 0 skipped -- so nothing hides behind
        it. The count is what turns "resolved clean" into "resolved clean, over
        everything".

        **It is a tripwire rather than a live guard, and that is measured.**
        Putting a sibling combinator on a tier selector does not produce a
        skip: `css_cascade.resolve` calls `matches` over every RULE and lets
        `UnsupportedSelectorError` out, so the sweep raises before this branch
        is reached. `_steps` is shared by both, so any selector `path_for`
        refuses, `matches` refuses too. The branch becomes reachable only if
        the resolver is later changed to skip rules it cannot express -- which
        is exactly the change that would open the hole -- and the assertion is
        here to red on that day rather than to catch anything today.
        """
        found: dict[str, float] = {}
        skipped = 0
        for selector in _tier_selectors(css):
            try:
                path = css_cascade.path_for(selector)
            except css_cascade.UnsupportedSelectorError:
                skipped += 1
                continue
            size = css_cascade.resolve(path, tokens, rules)
            if size is not None and size < SENTENCE_FLOOR_REM:
                found[selector] = size
        return found, skipped

    def test_every_sentence_tier_element_resolves_at_or_above_the_floor(self) -> None:
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        # A sweep that resolved nothing would pass the check below in silence.
        self.assertGreater(len(_tier_selectors(css)), 40, "the tier sweep found almost nothing")
        below, skipped = self._below_floor(css, self.tokens, self.rules)
        self.assertEqual(
            {},
            below,
            "a rule declares these on the sentence tier and a later rule renders "
            "them below the floor",
        )
        self.assertEqual(0, skipped, f"{skipped} tier selectors were skipped unresolved")

    def test_the_guard_reds_on_a_later_equal_specificity_rule_below_the_floor(self) -> None:
        """Mutation: re-create the defect exactly, and run the GUARD on it.

        Asserting that the resolver returns 12.5 would only prove the resolver
        works. What has to be true is that the check above FAILS, so the mutant
        is put through the same function the real sheet goes through.

        `.next-steer-caveat` declares `--fs-body` and a later rule at the
        same (0,1,0) takes it to `--fs-label`, which is the shape
        `.next-guardrail-copy small` shipped in.

        The mutant used `--fs-xs` until v3 deleted that token. An undeclared
        token makes `_declared_size` return None, so the mutant stopped
        producing a violation and the guard asserted nothing while still
        passing. The token has to be one the sheet actually declares, or this
        test proves only that a typo is invisible.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        mutant = css + "\n.next-steer-caveat{font-size:var(--fs-label);line-height:1.5}\n"
        self.assertNotEqual(css, mutant)
        tokens, rules = css_cascade.load_text(mutant)
        self.assertEqual(
            {".next-steer-caveat": css_cascade.rem(13.0)},
            self._below_floor(mutant, tokens, rules)[0],
        )
        # And the clean sheet is not incidentally failing for some other reason.
        self.assertEqual({}, self._below_floor(css, self.tokens, self.rules)[0])

    def test_the_set_of_selectors_declared_on_both_sides_is_pinned(self) -> None:
        """The precondition, pinned as a census.

        Every one of these resolves to its compliant rule today, so none is a
        defect; what makes the set worth holding is that the shipped defect was
        a member of it. A grouped-rule edit that adds a ninth gets reviewed
        instead of being found by a reader.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        self.assertEqual(self.STRADDLING, self._straddling(css))
        self.assertNotIn(".next-guardrail-copy small", self._straddling(css))

    def test_the_straddle_census_would_have_seen_the_shipped_defect(self) -> None:
        """Mutation: put the overridden declaration back.

        This is the pre-fix sheet, and it proves the census is aimed at the
        thing that actually shipped rather than at a shape resembling it.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        mutant = css.replace(
            ".next-guardrail-copy strong,.next-guardrail-copy small"
            "{display:block;overflow-wrap:anywhere;font-weight:500}\n"
            ".next-guardrail-copy strong{font-size:var(--fs-body);line-height:1.55}",
            ".next-guardrail-copy strong,.next-guardrail-copy small"
            "{display:block;overflow-wrap:anywhere;font-size:var(--fs-body);"
            "font-weight:500;line-height:1.55}",
        )
        # assertNotEqual is doing real work here: the two strings are quoted
        # from the sheet, so a rename like --fs-sentence to --fs-body silently
        # makes the replace a no-op and the mutation vacuous. It went that way
        # once, in v3.
        self.assertNotEqual(css, mutant)
        self.assertIn(".next-guardrail-copy small", self._straddling(mutant))
        tokens, rules = css_cascade.load_text(mutant)
        self.assertEqual(
            {".next-guardrail-copy small": css_cascade.rem(13.0)},
            self._below_floor(mutant, tokens, rules)[0],
        )


_ROOT_NODE: css_cascade.Node = {"tag": "div", "classes": set(), "attrs": set()}


class APseudoClassIsEvaluatedOrRefusedTest(unittest.TestCase):
    """DRC-4630. The resolver parsed pseudo-classes and then ignored them.

    `_SIMPLE` absorbed `:not([class])` into the compound, `_node_matches`
    compared tag, classes and attributes only, and the condition was never
    asked -- so the pseudo-class always matched AND carried specificity while
    doing it. Both halves of a wrong answer: the rule reached elements the
    browser excludes, at a weight that beat the rule that really wins.

    It was found from the outside, which is the part worth keeping. DRC-4604's
    control guard needed a mutant that pulls a control below its tier, the
    natural single-class mutant would not red, and the reason turned out to be
    the instrument rather than the mutant.
    """

    tokens: ClassVar[dict[str, float]]
    rules: ClassVar[list[tuple[str, str, int]]]
    css: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        cls.tokens, cls.rules = css_cascade.load_text(cls.css)

    # The floor the sheet declares for a button nobody has classed, and the
    # selector that produced the defect. Quoted from `styles.css` rather than
    # written out, so a rewrite of that rule fails the assertions below loudly
    # instead of leaving them testing a selector the sheet no longer has.
    BARE_BUTTON_FLOOR: ClassVar[str] = ":where(#app) button:not([class])"

    def test_the_sheet_still_carries_the_selector_these_assertions_are_about(self) -> None:
        self.assertIn(self.BARE_BUTTON_FLOOR + "{", self.css)

    def test_a_negation_does_not_match_the_element_it_excludes(self) -> None:
        """AC-1. A classed button is not a button without a class."""
        classed: list[css_cascade.Node] = [
            {"tag": "div", "classes": set(), "attrs": set()},
            {"tag": "button", "classes": {"next-action", "next-notify-button"}, "attrs": {"type"}},
        ]
        self.assertIsNone(css_cascade.matches(classed, self.BARE_BUTTON_FLOOR))

    def test_the_negation_still_matches_the_element_it_is_for(self) -> None:
        """The other half, because "matches nothing" would also pass the above.

        The specificity is asserted as well as the match. It used to come back
        (0,2,1): the `#app` inside `:where()` counted as a pseudo-class rather
        than as nothing, and `:not([class])` counted a second time. `:where()`
        adds nothing by definition and `:not()` takes its argument's weight, so
        an attribute and a tag is the whole of it.
        """
        bare: list[css_cascade.Node] = [
            {"tag": "div", "classes": set(), "attrs": set()},
            {"tag": "button", "classes": set(), "attrs": {"type"}},
        ]
        self.assertEqual((0, 1, 1), css_cascade.matches(bare, self.BARE_BUTTON_FLOOR))

    def test_special_casing_the_one_selector_would_not_satisfy_this(self) -> None:
        """AC-1's falsifier, asked of pseudo-classes the sheet does not use.

        Matching `:not([class])` by string leaves every other pseudo-class
        matching unconditionally, so the check is a form the sheet has never
        carried: a state the node is not in, and a negation of a class.
        """
        node: list[css_cascade.Node] = [
            {"tag": "button", "classes": {"next-action"}, "attrs": set()}
        ]
        self.assertIsNone(css_cascade.matches(node, "button:hover"))
        self.assertIsNone(css_cascade.matches(node, ".next-action:not(.next-action)"))
        self.assertIsNone(css_cascade.matches(node, "button:first-child"))
        # And a state the node IS in resolves, so the above is not "nothing
        # matches any more".
        hovered: list[css_cascade.Node] = [
            {"tag": "button", "classes": {"next-action"}, "attrs": set(), "states": {"hover"}}
        ]
        self.assertEqual((0, 2, 0), css_cascade.matches(hovered, ".next-action:hover"))

    def test_every_pseudo_class_the_sheet_uses_is_one_the_resolver_evaluates(self) -> None:
        """AC-2. The enumeration, taken from the sheet rather than remembered."""
        used = {
            match.group(1)
            for selector, _body, _order in self.rules
            for match in re.finditer(r"(?<!:):([\w-]+)", selector)
        }
        handled = (
            css_cascade._STATE_PSEUDO
            | css_cascade._STRUCTURAL_PSEUDO
            | css_cascade._PSEUDO_ELEMENTS
            | {"is", "where", "not", "nth-child"}
        )
        self.assertEqual(set(), used - handled, "the sheet uses a pseudo-class nothing evaluates")
        # The sweep is aimed at something: an empty `used` would pass the line
        # above while asserting nothing at all.
        self.assertGreater(len(used), 8, f"the pseudo-class sweep found only {sorted(used)}")

    def test_a_pseudo_class_the_resolver_does_not_know_is_refused(self) -> None:
        """AC-2's falsifier: the remainder raises rather than being skipped.

        `:has()` is the realistic next arrival and the sheet has none. It is
        refused the way a sibling combinator is, and for the reason
        `UnsupportedSelectorError` already gives -- a rule that leaves the
        cascade in silence produces plausible numbers.
        """
        node: list[css_cascade.Node] = [
            {"tag": "button", "classes": {"next-action"}, "attrs": set()}
        ]
        for selector in (
            ".next-action:has(span)",
            ".next-action:nth-of-type(2)",
            "button:lang(en)",
        ):
            with (
                self.subTest(selector=selector),
                self.assertRaises(css_cascade.UnsupportedSelectorError),
            ):
                css_cascade.matches(node, selector)

    def test_a_selector_list_inside_a_functional_pseudo_class_survives_parsing(self) -> None:
        """The sheet's one `:is()` was being cut in half at its own comma.

        `load_text` split every rule's selector on `,`, which turned
        `:is(a, input):focus-visible` into `:is(a` and `input):focus-visible` --
        two strings that are not selectors. `:nth-child(-n+4)` went the same way
        one layer down, where the `+` read as a sibling combinator and the whole
        rule was refused.
        """
        selectors = [selector for selector, _body, _order in self.rules]
        self.assertIn(".next-project-detail-rail :is(a,button,input):focus-visible", selectors)
        self.assertIn(".next-cockpit-recovery>div:nth-child(-n+4)", selectors)
        focused: list[css_cascade.Node] = [
            {"tag": "div", "classes": {"next-project-detail-rail"}, "attrs": set()},
            {"tag": "input", "classes": set(), "attrs": set(), "states": {"focus-visible"}},
        ]
        self.assertIsNotNone(
            css_cascade.matches(
                focused, ".next-project-detail-rail :is(a,button,input):focus-visible"
            )
        )

    def test_no_rule_in_the_sheet_is_refused_for_a_reason_other_than_a_sibling(self) -> None:
        """AC-2 over the whole sheet, so a new selector form cannot land quietly.

        Sibling combinators are the one refusal this module has always made and
        still makes; every other rule has to resolve. Measured on the tree this
        landed against: 1110 rules, 18 refused, all 18 carrying `+` or `~`.
        """
        refused = []
        for selector, _body, _order in self.rules:
            try:
                css_cascade.matches([_ROOT_NODE], selector)
            except css_cascade.UnsupportedSelectorError:
                refused.append(selector)
        self.assertEqual([], [one for one in refused if "+" not in one and "~" not in one])
        self.assertGreater(len(refused), 10, "the sibling refusals stopped happening")


class NextPageAssetContractTest(unittest.TestCase):
    @staticmethod
    def _loader() -> Callable[[], bytes]:
        loader = getattr(frontend_page, "load_page", None)
        if loader is None:
            raise AssertionError("page.py does not expose load_page")
        return cast("Callable[[], bytes]", loader)

    @staticmethod
    def _fake_font_styles() -> str:
        return "".join(
            f'@font-face{{src:url("{slot}")}}\n' for _name, slot in frontend_page.FONT_ASSETS
        )

    @staticmethod
    def _write_bundle(web: Path, template: str) -> None:
        (web / "index.html").write_text(template, encoding="utf-8")
        (web / "styles.css").write_text(
            NextPageAssetContractTest._fake_font_styles() + ".next{color:red}\n",
            encoding="utf-8",
        )
        for name, _slot in frontend_page.FONT_ASSETS:
            asset = web / name
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_text("d09GMg==\n", encoding="ascii")
        # One marker per part, derived from APP_PARTS rather than listed. The
        # hand-written list this replaces went stale the moment a part was added,
        # and the failure named a byte count rather than the missing file. Order
        # and membership are pinned against literals in the two oracle tests
        # below; this fixture only has to make the loader resolvable.
        for name in frontend_page.APP_PARTS:
            (web / name).write_text(f"/*{name}*/\n", encoding="utf-8")

    def test_load_page_resolves_the_patched_web_dir_at_call_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            self._write_bundle(
                web,
                "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
            )
            with mock.patch.object(frontend_page, "WEB_DIR", web):
                actual = self._loader()()

        embedded_styles = self._fake_font_styles()
        for _name, slot in frontend_page.FONT_ASSETS:
            embedded_styles = embedded_styles.replace(
                slot,
                "data:font/woff2;base64,d09GMg==",
            )
        self.assertEqual(
            (f"<style>{embedded_styles}.next{{color:red}}\n</style>").encode()
            + b"<script>"
            + "".join(f"/*{name}*/\n" for name in frontend_page.APP_PARTS).encode()
            + b"</script>",
            actual,
        )

    def test_the_next_template_has_exactly_one_of_each_slot(self) -> None:
        cases = (
            ("{{CARGENTO_APP}}", "index.html must contain one CARGENTO_STYLES slot"),
            ("{{CARGENTO_STYLES}}", "index.html must contain one CARGENTO_APP slot"),
            (
                "{{CARGENTO_STYLES}}{{CARGENTO_STYLES}}{{CARGENTO_APP}}",
                "index.html must contain one CARGENTO_STYLES slot",
            ),
            (
                "{{CARGENTO_STYLES}}{{CARGENTO_APP}}{{CARGENTO_APP}}",
                "index.html must contain one CARGENTO_APP slot",
            ),
        )
        for template, message in cases:
            with self.subTest(template=template), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                self._write_bundle(web, template)
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(RuntimeError, f"^{re.escape(message)}$"),
                ):
                    self._loader()()

    def test_the_next_stylesheet_requires_exactly_one_slot_per_font(self) -> None:
        name, slot = frontend_page.FONT_ASSETS[0]
        cases = (
            ("", f"styles.css must contain one {slot} slot"),
            (slot * 2, f"styles.css must contain one {slot} slot"),
        )
        for replacement, message in cases:
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                self._write_bundle(
                    web,
                    "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
                )
                stylesheet = web / "styles.css"
                stylesheet.write_text(
                    stylesheet.read_text(encoding="utf-8").replace(slot, replacement),
                    encoding="utf-8",
                )
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(RuntimeError, f"^{re.escape(message)}$"),
                ):
                    frontend_page.load_styles()

        self.assertTrue(name.endswith(".woff2.b64"))

    def test_the_next_stylesheet_rejects_invalid_font_payloads(self) -> None:
        name, _slot = frontend_page.FONT_ASSETS[0]
        for payload in ("not base64!", "T1RUTw=="):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                self._write_bundle(
                    web,
                    "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
                )
                (web / name).write_text(payload, encoding="ascii")
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(
                        RuntimeError,
                        rf"^font asset {re.escape(name)} must be base64 WOFF2$",
                    ),
                ):
                    frontend_page.load_styles()

    def test_a_missing_next_font_stays_inside_the_next_loader_boundary(self) -> None:
        name, _slot = frontend_page.FONT_ASSETS[0]
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            self._write_bundle(
                web,
                "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
            )
            (web / name).unlink()
            with (
                mock.patch.object(frontend_page, "WEB_DIR", web),
                self.assertRaises(FileNotFoundError),
            ):
                frontend_page.load_page()

    def test_every_next_part_exists_and_is_named(self) -> None:
        web = frontend_page.WEB_DIR
        self.assertEqual(
            (
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
            ),
            frontend_page.APP_PARTS,
        )
        actual = {path.name for path in web.glob("*.js")}
        self.assertEqual(set(frontend_page.APP_PARTS), actual)
        for name in frontend_page.APP_PARTS:
            with self.subTest(part=name):
                self.assertGreater((web / name).stat().st_size, 0)

    def test_the_next_page_embeds_the_design_fonts_from_pinned_local_assets(self) -> None:
        expected_fonts = {
            "fonts/space-grotesk-v22-vietnamese.woff2.b64": (
                6_772,
                "d699664b145bfeeccc66a4cce7fa55e14eb63efd7ec6b0b2ec52e25dd98f3917",
            ),
            "fonts/space-grotesk-v22-latin-ext.woff2.b64": (
                18_924,
                "054c266fbb441ee059365dba0885d206f67ca05b375de869b88e02ebfccc9b9d",
            ),
            "fonts/space-grotesk-v22-latin.woff2.b64": (
                22_320,
                "a0d054c4af557de20afd6ca59f47ab353bcaec49c63ff04b6c9d39d0f8910557",
            ),
            "fonts/ibm-plex-mono-v20-regular-vietnamese.woff2.b64": (
                4_000,
                "0a8b854cc18641bd1b8222afa7ec82a75e59bc6501f777744ec87db1b6cd7a2c",
            ),
            "fonts/ibm-plex-mono-v20-regular-latin-ext.woff2.b64": (
                8_860,
                "f1050dc5317b43434c0aeda599d4624c774ffc162e87a8cf204b949b6a85816d",
            ),
            "fonts/ibm-plex-mono-v20-regular-latin.woff2.b64": (
                10_052,
                "c36f509c0a8f9f85f29cb44bc8701d8a9e0b14c499e77a884f789ead7093a7ac",
            ),
            "fonts/ibm-plex-mono-v20-medium-vietnamese.woff2.b64": (
                4_036,
                "b2529fba93fd07a50ffb8fc3d103eb04b0c298d4f6564d2833c44fde286de7e4",
            ),
            "fonts/ibm-plex-mono-v20-medium-latin-ext.woff2.b64": (
                8_848,
                "77f03e26f981c582bdba3a7abed4baa2d3149211c01366bb3ab3ba7622ec4ae5",
            ),
            "fonts/ibm-plex-mono-v20-medium-latin.woff2.b64": (
                10_060,
                "a76f53ca6612e7b3828eec2311098675b7f9849ae4169a8bcef6302aec02a6c0",
            ),
            "fonts/ibm-plex-mono-v20-semibold-vietnamese.woff2.b64": (
                4_116,
                "69744cabbccc9faf77516ce9b744361e1e6be7f8081400006035a153797d2965",
            ),
            "fonts/ibm-plex-mono-v20-semibold-latin-ext.woff2.b64": (
                8_960,
                "1b6b18fd0fd240bc6d5850f4df621484722d4b5d3650ebdd1e3a8bbd81c75854",
            ),
            "fonts/ibm-plex-mono-v20-semibold-latin.woff2.b64": (
                10_120,
                "ad4580d8cb4b5f627c2d18457656732f7f7b070f7837fbc380e08054157e6f6c",
            ),
            "fonts/ibm-plex-mono-v20-italic-vietnamese.woff2.b64": (
                4_416,
                "fe88a1e1a9cdb5b50308f09aaf573987f4ba2177bc6faa5feeb82a47df277bbb",
            ),
            "fonts/ibm-plex-mono-v20-italic-latin-ext.woff2.b64": (
                9_788,
                "c590f625acd1a18021f23486445b03b8435879b406db1003d3fdd7804e9319fb",
            ),
            "fonts/ibm-plex-mono-v20-italic-latin.woff2.b64": (
                11_568,
                "2665f5fbbb334780fa135c7f1dc6e2459061a2d6d44c32b7c1fdbc34cde65ede",
            ),
        }
        vietnamese_range = (
            "U+0102-0103,U+0110-0111,U+0128-0129,U+0168-0169,U+01A0-01A1,"
            "U+01AF-01B0,U+0300-0301,U+0303-0304,U+0308-0309,U+0323,U+0329,"
            "U+1EA0-1EF9,U+20AB"
        )
        latin_ext_range = (
            "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,"
            "U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,"
            "U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"
        )
        latin_range = (
            "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
            "U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,"
            "U+2212,U+2215,U+FEFF,U+FFFD"
        )
        expected_faces = {
            "fonts/space-grotesk-v22-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_GROTESK_V22_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/space-grotesk-v22-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_GROTESK_V22_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/space-grotesk-v22-latin.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_GROTESK_V22_LATIN}}",
                latin_range,
            ),
            "fonts/ibm-plex-mono-v20-regular-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_REGULAR_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/ibm-plex-mono-v20-regular-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_REGULAR_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/ibm-plex-mono-v20-regular-latin.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_REGULAR_LATIN}}",
                latin_range,
            ),
            "fonts/ibm-plex-mono-v20-medium-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_MEDIUM_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/ibm-plex-mono-v20-medium-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_MEDIUM_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/ibm-plex-mono-v20-medium-latin.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_MEDIUM_LATIN}}",
                latin_range,
            ),
            "fonts/ibm-plex-mono-v20-semibold-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_SEMIBOLD_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/ibm-plex-mono-v20-semibold-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_SEMIBOLD_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/ibm-plex-mono-v20-semibold-latin.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_SEMIBOLD_LATIN}}",
                latin_range,
            ),
            "fonts/ibm-plex-mono-v20-italic-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_ITALIC_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/ibm-plex-mono-v20-italic-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_ITALIC_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/ibm-plex-mono-v20-italic-latin.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_ITALIC_LATIN}}",
                latin_range,
            ),
        }
        self.assertEqual(
            tuple((name, marker) for name, (marker, _range) in expected_faces.items()),
            frontend_page.FONT_ASSETS,
        )
        for name, (size, digest) in expected_fonts.items():
            with self.subTest(font=name):
                encoded = "".join(
                    frontend_page.asset_path(name).read_text(encoding="ascii").splitlines()
                )
                payload = base64.b64decode(encoded, validate=True)
                self.assertEqual(b"wOF2", payload[:4])
                self.assertEqual(size, len(payload))
                self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

        styles = frontend_page.asset_path("styles.css").read_text(encoding="utf-8")
        raw_faces = [line for line in styles.splitlines() if line.startswith("@font-face{")]
        for name, (marker, unicode_range) in expected_faces.items():
            with self.subTest(face=name):
                matches = [face for face in raw_faces if marker in face]
                self.assertEqual(1, len(matches))
                self.assertIn(f"unicode-range:{unicode_range}", matches[0])

        assembled = frontend_page.load_page().decode()
        self.assertNotIn("fonts.googleapis.com", assembled)
        self.assertNotIn("fonts.gstatic.com", assembled)
        self.assertNotIn("{{CARGENTO_FONT_", assembled)
        self.assertEqual(15, assembled.count("data:font/woff2;base64,"))
        assembled_faces = re.findall(r"@font-face\{([^}]*)\}", assembled)
        grotesk = [face for face in assembled_faces if "font-family:'Space Grotesk'" in face]
        mono = [face for face in assembled_faces if "font-family:'IBM Plex Mono'" in face]
        self.assertEqual(3, len(grotesk))
        self.assertTrue(all("font-weight:400 700" in face for face in grotesk))
        self.assertEqual(12, len(mono))
        # The pair, not the weight. IBM Plex Mono ships a 400 italic beside the
        # 400 upright, so counting `font-weight:400` alone reports six where
        # three of them are a different face, and an italic lost to the upright
        # subsetting would still leave that count right.
        cuts: dict[tuple[str, str], int] = {}
        for face in mono:
            style = re.search(r"font-style:([^;]+);", face)
            weight = re.search(r"font-weight:([^;]+);", face)
            self.assertIsNotNone(style)
            self.assertIsNotNone(weight)
            cut = (style.group(1) if style else "", weight.group(1) if weight else "")
            cuts[cut] = cuts.get(cut, 0) + 1
        self.assertEqual(
            {
                ("normal", "400"): 3,
                ("normal", "500"): 3,
                ("normal", "600"): 3,
                ("italic", "400"): 3,
            },
            cuts,
        )

        expected_notices = {
            "fonts/SpaceGrotesk-OFL.txt": (
                4_402,
                "c6dec685825f73b18c20926fddc65e8315642e12986f15db0699170940a09efc",
            ),
            "fonts/IBMPlexMono-OFL.txt": (
                4_363,
                "37784b44044a4ffd9256702b7c0982c37e5c8887ba90c6dca0479aea93dc898d",
            ),
        }
        for name, (size, digest) in expected_notices.items():
            with self.subTest(notice=name):
                notice = frontend_page.asset_path(name).read_bytes()
                self.assertEqual(size, len(notice))
                self.assertEqual(digest, hashlib.sha256(notice).hexdigest())
        sources = frontend_page.asset_path("fonts/SOURCES.txt").read_text(encoding="utf-8")
        self.assertIn("Space Grotesk v22", sources)
        self.assertIn("IBM Plex Mono v20", sources)
        for _size, digest in expected_fonts.values():
            self.assertIn(digest, sources)
        # The family name survives in SOURCES.txt as provenance -- the Space Grotesk
        # subsets came from a combined request that also carried Space Mono -- so the
        # retirement is asserted on the shipped filenames, which are what is gone.
        self.assertNotIn("space-mono-v17", sources)
        self.assertFalse((frontend_page.WEB_DIR / "fonts" / "SpaceMono-OFL.txt").exists())
        self.assertEqual([], sorted(frontend_page.WEB_DIR.glob("fonts/space-mono-*")))
        self.assertNotIn("SPACE_MONO", styles)

    def test_the_retired_preview_asset_directory_is_absent(self) -> None:
        self.assertFalse((frontend_page.WEB_DIR / "next").exists())

    def test_the_optional_terminal_uses_the_verified_local_vendor_assets(self) -> None:
        assets = {
            "vendor/xterm.js": (
                488_663,
                "14903579ff54664cd72f8e8699e6961a6272c21863ec1c3b118cdc8af5d4a972",
            ),
            "vendor/xterm.css": (
                7_112,
                "854a7c0fb70e8b1a083c16797ab827299fb18744f5ad34f227b48337e33293c6",
            ),
            "vendor/xterm-LICENSE.txt": (
                1_261,
                "b569f629d00f2626a8100df2a1798210535621e42164dfd426a6fe5aac7b0ccd",
            ),
            "vendor/SOURCES.txt": (
                534,
                "426b3d3a2288c8f88c9b960b5089294aa35c7e77a84969650633669b884e2e45",
            ),
        }
        for name, (size, digest) in assets.items():
            with self.subTest(asset=name):
                data = frontend_page.asset_path(name).read_bytes()
                self.assertEqual(size, len(data))
                self.assertEqual(digest, hashlib.sha256(data).hexdigest())

    def test_every_css_variable_the_canonical_page_uses_is_declared(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        page = frontend_page.load_page().decode()
        declared = set(re.findall(r"(--[\w-]+)\s*:", styles))
        used = set(re.findall(r"var\((--[\w-]+)", page))
        self.assertEqual(set(), used - declared, "page uses CSS variables nothing declares")

    def test_the_need_you_button_keeps_visible_keyboard_focus(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        button = re.search(r"\.next-gate\{([^}]*)\}", styles)
        focus = re.search(r"\.next-gate:focus-visible\{([^}]*)\}", styles)

        self.assertIsNotNone(button)
        self.assertIsNotNone(focus)
        button_rules = dict(re.findall(r"([\w-]+):([^;]+)", button.group(1) if button else ""))
        focus_rules = dict(re.findall(r"([\w-]+):([^;]+)", focus.group(1) if focus else ""))
        self.assertEqual("none", button_rules.get("appearance"))
        self.assertEqual("inherit", button_rules.get("font"))
        self.assertEqual("pointer", button_rules.get("cursor"))
        self.assertEqual("2px solid var(--ink)", focus_rules.get("outline"))
        self.assertEqual("3px", focus_rules.get("outline-offset"))

    def test_the_next_palette_is_dark_only(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        roots = re.findall(r"(?:\A|\n):root\{([^}]*)\}", styles, re.DOTALL)
        self.assertEqual(1, len(roots))
        self.assertNotIn("prefers-color-scheme", styles)
        # Reconciliation removed the temporary prototype palette (RC-5).
        for retired in ("--warn", "--alert", "--accent-ink", "--warnink"):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, styles)
        expected = {
            # surfaces
            "--sunk": "#0f0f0a",
            "--bg": "#14140f",
            "--panel": "#24231b",
            "--raise": "#323025",
            # boundaries
            "--line": "#74725f",
            "--line-hi": "#8a8874",
            "--rule": "#35342a",
            # ink
            "--ink": "#f6f3ea",
            "--ink2": "#cdc7b4",
            "--ink3": "#a39c88",
            # tones
            "--accent": "#cfe884",
            "--accent-dim": "#93a757",
            "--amber": "#f0b95e",
            "--clay": "#e4886a",
        }
        tokens = dict(re.findall(r"(--[\w-]+):([^;]+);", roots[0]))
        # The map is the whole palette, not a sample of it. Read back every
        # :root token whose value IS a hex literal and require the two sets to
        # match, so a fifteenth colour fails here instead of arriving unmeasured
        # and unreachable by the contrast loop below. Composed values --
        # `--e-card`'s shadow, `--hatch`'s gradient, the `color-mix` selection
        # pair -- carry a colour without being one, and stay out by construction.
        literal = {
            name: value.strip()
            for name, value in tokens.items()
            if re.fullmatch(r"#[0-9a-f]{6}", value.strip())
        }
        self.assertEqual(expected, literal)

        # The four --ink-* roles survive v3 as indirection, never as a colour of
        # their own: the tier moves in one line because nothing repeats a hex.
        for role, target in (
            ("--ink-label", "var(--ink2)"),
            ("--ink-value", "var(--ink)"),
            ("--ink-absence", "var(--ink2)"),
            ("--ink-caption", "var(--ink2)"),
        ):
            with self.subTest(role=role):
                self.assertEqual(target, (tokens.get(role) or "").strip())

        # Retired by v3 alongside the prototype palette above.
        for gone in ("--line2", "--radius-control", "--control-bd"):
            with self.subTest(retired=gone):
                self.assertNotIn(gone, tokens)

        def luminance(value: str) -> float:
            channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [
                channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def contrast(first: str, second: str) -> float:
            high, low = sorted((luminance(first), luminance(second)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        for surface in ("--sunk", "--bg", "--panel", "--raise"):
            for ink in (
                "--ink",
                "--ink2",
                "--ink3",
                "--accent",
                "--accent-dim",
                "--amber",
                "--clay",
            ):
                with self.subTest(surface=surface, ink=ink):
                    self.assertGreater(contrast(tokens[ink], tokens[surface]), 4.5)

        # SC 1.4.11. --line bounds a control and must clear 3:1 on the surfaces a
        # control sits on; --raise is the one it cannot, which is the whole reason
        # --line-hi exists. --rule divides rows and bounds nothing, so it is out
        # of scope and is asserted to stay out by never being asked to clear it.
        for surface in ("--sunk", "--bg", "--panel"):
            with self.subTest(boundary="--line", surface=surface):
                self.assertGreater(contrast(tokens["--line"], tokens[surface]), 3.0)
        self.assertGreater(contrast(tokens["--line-hi"], tokens["--raise"]), 3.0)
        self.assertGreater(contrast(tokens["--ink"], tokens["--bg"]), 3.0)

    # --- DRC-4596: the size guard, and the three mutants that falsify it ------

    SUB_LABEL_FLOOR_REGISTRY: ClassVar[set[tuple[float, str]]] = set()
    """The px literals below the 13px label floor, recorded rather than raised.

    Empty against the v3 sheet, which is this registry at its strongest rather
    than a reason to delete it. v3 spells every size as a token, so the six
    literals v0.27.0 recorded -- 10px on `.next-rail-capacity-caption` and
    10.5px on the capacity scope, the capacity window, the delegation metrics,
    the operation harness and the project-change stamp -- went with the steps
    they named. The assertion is an equality over a DERIVED sweep, so a seventh
    literal arriving below the floor, or any of the six coming back, reds on the
    run that lands it. An empty expected set is only vacuous if the sweep cannot
    produce a non-empty one, and `test_a_retuned_label_token_is_caught` is the
    committed proof that it can.
    """

    SENTENCE_TIER_RULES: ClassVar[set[str]] = {
        # Every rule this census resolves at or above the floor. A set rather
        # than a count, so one rule leaving the tier while another joins cannot
        # pass unnoticed.
        # `.next-cockpit-stale-read` joined with DRC-4613: a sans sentence with
        # a prose line-height is on this tier by the sheet's own membership test.
        ".next-action",
        ".next-activity-question",
        ".next-attention-brief p",
        ".next-attention-caveats p",
        ".next-attention-heading p,.next-attention-section-heading p",
        ".next-attention-open p",
        ".next-attention-part",
        ".next-attention-risk-assignment",
        ".next-attention-risk-detail",
        ".next-attention-risk-identity h3",
        ".next-attention-risk-observation p",
        ".next-capacity-prospect",
        ".next-capacity-prospect small",
        ".next-cockpit-authority>small",
        ".next-cockpit-conflict-cue",
        ".next-cockpit-conflict-open",
        ".next-cockpit-conflict-text",
        ".next-cockpit-conflict-why,.next-cockpit-conflict-settled",
        ".next-cockpit-content",
        ".next-cockpit-content .next-cockpit-evidence-missing",
        ".next-cockpit-content .next-course-evidence",
        ".next-cockpit-count-label",
        ".next-cockpit-decision-summary,.next-cockpit-viewing-session,\n.next-cockpit-now-state small,.next-project-workflow-definition>small,\n.next-cockpit-system-details ul,.next-cockpit-memos label>small",
        ".next-cockpit-define",
        ".next-cockpit-departures-kept",
        ".next-cockpit-empty,.next-cockpit-evidence-missing",
        ".next-cockpit-held-absent",
        ".next-cockpit-held-field textarea",
        ".next-cockpit-held-lede",
        ".next-cockpit-held-reentry",
        ".next-cockpit-held-reentry-text",
        ".next-cockpit-held-revision",
        ".next-cockpit-landed-note",
        ".next-cockpit-landed-value",
        ".next-cockpit-lede",
        ".next-cockpit-reading-clause,.next-session-departure-clause",
        ".next-cockpit-reading-clause-absent",
        ".next-cockpit-reading-limit",
        ".next-cockpit-reading-result,.next-cockpit-reading-detail,.next-session-departure-reading",
        ".next-cockpit-reading-stale,.next-session-departure-stale",
        ".next-cockpit-reading-why",
        ".next-cockpit-recovery .next-project-goal-text",
        ".next-cockpit-recovery .next-project-goal-text.next-project-value--absent,\n.next-cockpit-recovery .next-project-goal-gap",
        ".next-cockpit-recovery details>summary,.next-course-evidence>summary,\n.next-cockpit-plan-details>summary,.next-cockpit-console-status>summary,\n.next-cockpit-console-setup>summary",
        ".next-cockpit-recovery>div",
        ".next-cockpit-scope-switcher>summary",
        ".next-cockpit-stale-read",
        ".next-cockpit-why>summary",
        ".next-cockpit-work-absent,.next-cockpit-work-limit",
        ".next-cockpit-work-derived",
        ".next-cockpit-work-dropped",
        ".next-cockpit-work-result",
        ".next-cockpit-work-checks",
        ".next-cockpit-work-mix",
        ".next-cockpit-work-summary",
        ".next-course-episode p,.next-course-episode ul,.next-course-direction p",
        ".next-delegation-caption",
        ".next-guardrail-copy strong",
        ".next-guardrail-empty",
        ".next-instruction-text",
        ".next-intent-note",
        ".next-intent-revision,.next-intent-why",
        ".next-intent-words",
        ".next-operation-assignment",
        ".next-operation-collision",
        ".next-operation-fact em",
        ".next-operation-group>header p",
        ".next-operation-identity strong,.next-operation-fact strong",
        ".next-operation-outcome",
        ".next-operation-unread,.next-operation-scan-only",
        ".next-operations-fleet small",
        ".next-operations-header p",
        ".next-project-collision,.next-project-detail-collision",
        ".next-project-detail-rail .next-rail-reason",
        ".next-project-ending-outcome",
        ".next-project-goal-gap",
        ".next-project-goal-text",
        ".next-projects-empty",
        ".next-projects-note",
        ".next-rail-question",
        ".next-rail-wait-heading a",
        ".next-session-ask-question",
        ".next-session-current>strong,.next-session-command-facts strong,.next-session-command-context",
        ".next-session-delivery-count",
        ".next-session-delivery-lane",
        ".next-session-delivery-note",
        ".next-session-delivery-why",
        ".next-session-departure-next",
        ".next-session-departures-count",
        ".next-session-departures-why",
        ".next-departure-reentry-why",
        ".next-operation-goal-link",
        ".next-session-detail-instruction",
        ".next-session-facts dd",
        ".next-session-health",
        ".next-session-held-link",
        ".next-session-source-coverage p",
        ".next-stalled",
        ".next-steer input,.next-guardrail-add-input input",
        ".next-steer-caveat",
        ".next-usage-consent",
        ".next-usage-consent p.next-usage-consent-note",
        ".pc-entry-details",
        ".pc-history-band>summary,.pc-trail-history>summary,.pc-entry-suppressed>summary,.pc-event-evidence>summary",
        ".pc-semantic-timeline,.pc-terminal",
        ".pc-terminal-screen",
        ".pc-trail-result",
        ".pc-trail-top .pc-lane-title",
    }

    SUB_SENTENCE_FLOOR_INVENTORY: ClassVar[set[tuple[float, str]]] = {
        (0.8125, ".next-cockpit-recovery .next-project-value--absent"),
        (0.8125, ".next-delegation-withheld small"),
        (0.8125, ".next-guardrail-copy small"),
        (0.8125, ".pc-substrate-empty,.pc-substrate-reason,.pc-terminal-identity p"),
        (0.8125, ".pc-substrate-steps"),
        (0.8125, ".pc-trail-quiet,.pc-trail-history,.pc-event-evidence"),
        (0.8125, ".pc-trail-top span"),
    }
    """The sentence-tier rules still below the floor, which DRC-4602 sizes.

    An exact set, so a rule LEAVING the sentence tier for a lower one reds here
    just as a new sub-floor rule does.

    Recomputed against v3, where every entry reads 13.0px and nothing else. The
    v0.27.0 inventory held 36 rules spread over five steps between 12.5px and
    14.5px; v3 deleted every one of those steps, so a rule that was not raised
    to `--fs-body` landed on `--fs-label` and the residual is now one figure
    wide. Nineteen of the 36 were raised onto the tier outright.

    The nine rules here that appear in neither v0.27.0 census did not fall --
    they arrived. Each was mono at 12.5px or 11px in v0.27.0, which kept it out
    of a census that skips mono, and v3 set it in sans at 13px. They enter this
    inventory having got LARGER, which is the one reading of a growing registry
    that is not a regression, and it is why the check below this one compares
    the v0.27.0 above-set against this below-set: that intersection is empty, so
    no rule crossed the floor downwards.
    """

    def test_the_root_type_tokens_hold_the_label_floor(self) -> None:
        tokens = _type_tokens((frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8"))
        # Five steps, not v0.27.0's twenty-one. A count and not only a floor,
        # because the defect this half guards against is a REINSTATED step: a
        # sixteenth token sitting between two of these reds here even when it
        # sits above the floor and so passes every other assertion in the class.
        self.assertEqual(5, len(tokens))
        below = {name: size for name, size in tokens.items() if size < LABEL_FLOOR_REM}
        self.assertEqual({}, below)
        # Zero margin is the useful state: --fs-label sits ON the floor, so any
        # new sub-13px step reds immediately.
        self.assertEqual(LABEL_FLOOR_REM, min(tokens.values()))
        # `--fs-sentence` was renamed to `--fs-body` at the same 15px. The name
        # this reads is the one the sentence rules spell, so a rename that left
        # the rules behind would red rather than resolve to the old step.
        self.assertEqual(SENTENCE_FLOOR_REM, tokens["fs-body"])

    def test_a_retuned_label_token_is_caught(self) -> None:
        """Mutation: `--fs-label:13px` -> `12.5px`, applied to an in-process copy.

        The tree is never touched, so no byte-pin oracle moves and this is a
        committed check rather than a procedure someone promises they ran.

        `assertNotEqual` on the substitution is the load-bearing line, not
        ceremony: the v0.27.0 spelling of this mutant was `--fs-label:11px`,
        which matches nothing in the v3 sheet, and a mutation that substitutes
        nothing proves nothing while still reporting a pass on the half below.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        self.assertEqual({}, {n: s for n, s in _type_tokens(css).items() if s < LABEL_FLOOR_REM})
        mutant = css.replace("--fs-label:0.8125rem", "--fs-label:0.78125rem", 1)
        self.assertNotEqual(css, mutant)
        self.assertEqual(
            {"fs-label": css_cascade.rem(12.5)},
            {n: s for n, s in _type_tokens(mutant).items() if s < LABEL_FLOOR_REM},
        )

    def test_sub_label_floor_literals_are_exactly_the_registry(self) -> None:
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        found = {(size, selector) for selector, size in _sub_label_floor_literals(css)}
        self.assertEqual(self.SUB_LABEL_FLOOR_REGISTRY, found)

    def test_sentence_tier_rules_resolve_at_or_above_the_floor(self) -> None:
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        above, below = _sentence_census(css)
        # Recomputed against the v3 sheet: 83 rules above the floor over 82
        # distinct selectors, and 24 below. v0.27.0 read 61 and 36. Both halves
        # of that move are raises -- 19 sub-floor rules went up to 15px, and 9
        # rules that were mono below 13px are now 13px sans, which puts them in
        # the sub-floor census for the first time at a size LARGER than they had.
        # Nothing crossed downwards: the v0.27.0 above-set and this below-set do
        # not intersect, which is the check that separates a retune from a
        # regression and the reason this is a rewrite rather than a stylesheet fix.
        #
        # A SET **and** a length, and each catches what the other cannot.
        #
        # The set is what a compensating swap needs: one rule leaving the tier
        # while another joins at 15px keeps the length where it was, and the
        # v0.27.0 integration was exactly that swap -- DRC-4589 moved
        # `.next-cockpit-authority>span` off the tier and `>small` on to it, so
        # a length check alone would have been green on the change that defeats
        # it.
        #
        # The length is what a DUPLICATE needs, and this half went unexplained,
        # which made it the one a reader would delete as redundant. The duplicate
        # is still `.next-cockpit-scope-switcher>summary`, declared once at the
        # default viewport and again in the `@media(max-width:1279px)` block;
        # removing that copy takes the length 83 -> 82 and leaves the set the
        # same size at 82, because a set cannot count a selector twice. Re-run
        # on the v3 sheet with the substitution proved before the verdict was
        # read: neither half is decorative, and the length is the only guard
        # this module has against duplicate drift.
        # 105 rules over 104 distinct selectors, against 84 over 83 before
        # DRC-4602 and 102 over 101 after it. Every one of the 19 DRC-4602 moved
        # was a RAISE -- the joining set was 19 and the leaving set empty, which
        # is the check that separates a retune from a regression -- and DRC-4631
        # then added three, of which `.next-instruction-text` is worth its
        # own line: it carries the words a person typed, and the membership test
        # could not reach it because it had no rule of its own to be selected
        # by. It took one until a live board showed it rendering at 13px.
        #
        # The one duplicate is unchanged, so the rule count still exceeds the
        # selector count by exactly one. DRC-4642 then added one:
        # `.next-departure-reentry-why`, the limit sentence beside a departure.
        # DRC-4637 adds the goal link at the body floor; no selector moved down.
        # DRC-4676 adds two at the body floor: a check's result line and the
        # sentence that counts the checks from the whole scan.
        self.assertEqual(109, len(above))
        self.assertEqual(self.SENTENCE_TIER_RULES, {selector for selector, _size in above})
        self.assertEqual(
            self.SUB_SENTENCE_FLOOR_INVENTORY, {(size, selector) for selector, size in below}
        )

    def test_a_sentence_rule_edited_below_the_floor_is_caught(self) -> None:
        """Mutation: one `font:` shorthand's `var(--fs-body)` -> `var(--fs-label)`.

        The shorthand form is the one that matters. Every sentence rule in this
        sheet is written `font:500 var(--fs-body)/1.55 var(--sans)`, so a parser
        that only read the `font-size` longhand would pass this mutant.

        Both halves of the substitution were repointed, and each for its own
        reason. `--fs-sentence` was renamed to `--fs-body` at the same 15px, so
        the pattern matched nothing. `--fs-xs` was DELETED, so the replacement
        would have named an undefined token: `_declared_size` returns `None` for
        one of those and the rule leaves the census entirely, which moves the
        above-count and the below-count in the same direction and makes the two
        assertions below disagree about a mutant that never landed a size at all.
        `--fs-label` is the only surviving step beneath the floor.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        mutant = css.replace(
            "font:500 var(--fs-body)/1.55 var(--sans)",
            "font:500 var(--fs-label)/1.55 var(--sans)",
            1,
        )
        self.assertNotEqual(css, mutant)
        clean_above, clean_below = _sentence_census(css)
        mutant_above, mutant_below = _sentence_census(mutant)
        self.assertEqual(len(clean_above) - 1, len(mutant_above))
        self.assertEqual(len(clean_below) + 1, len(mutant_below))

    def test_a_retuned_sentence_token_cannot_silence_the_census(self) -> None:
        """Why SENTENCE_FLOOR_REM is a literal and not read from the token.

        Retuning `--fs-body` to 12px would take the sub-floor inventory to 0
        against a token-derived floor, because every rule on the tier would then
        sit at the floor by definition. Against the literal the inventory grows
        instead -- measured on the v3 sheet, every rule the census resolves above
        the floor joins the ones already below it -- which is what a reader would
        want to hear.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        mutant = css.replace("--fs-body:0.9375rem", "--fs-body:0.75rem", 1)
        self.assertNotEqual(css, mutant)
        _, clean_below = _sentence_census(css)
        _, mutant_below = _sentence_census(mutant)
        self.assertGreater(len(mutant_below), len(clean_below))

    def test_the_steer_caveat_never_outranks_the_field_it_warns_about(self) -> None:
        """DRC-4595's raise, checked as a pair rather than as a floor.

        The caveat and the field are two branches of one control that a reader
        meets together, so the caveat alone proves nothing: raised on its own it
        would draw the warning larger than the words it warns about, the same
        ordering defect as an absence outranking its value. Both sides are read
        here, and equality is the assertion. Drop the field back to
        `var(--fs-label)` and this reds on the comparison, not on a literal.
        (v0.27.0 named `--fs-xs` in that sentence; v3 deleted the step, and the
        13px label token is what a regression would reach for now.)

        The label above them stays on the label tier on purpose -- `STEER ·
        LOCAL ONLY` is a caption, and DRC-4587's ruling is that a value is never
        drawn smaller than the caption beside it, not that the two match.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        tokens = _type_tokens(css)
        sizes = {
            selector: _declared_size(decls, tokens)
            for selector, decls in _rules(css)
            if selector in (".next-steer-caveat", ".next-steer-label", ".next-action")
            or selector == ".next-steer input,.next-guardrail-add-input input"
        }
        caveat = sizes[".next-steer-caveat"]
        field = sizes[".next-steer input,.next-guardrail-add-input input"]
        assert caveat is not None and field is not None
        self.assertEqual(field, caveat)
        self.assertEqual(SENTENCE_FLOOR_REM, caveat)
        # The submit sits in the same row as the field; DRC-4590's primitive
        # carries it, so this reds if the promoted control forks a local rule.
        self.assertEqual(field, sizes[".next-action"])
        self.assertEqual(LABEL_FLOOR_REM, sizes[".next-steer-label"])

    def test_absence_rules_stay_sans_and_never_outrank_their_value(self) -> None:
        """DRC-4589's ruling, as far as one rule at a time can carry it.

        The ruling is that an absence is a SANS SENTENCE sharing `--ink3` with
        labels, separated by family and case rather than by ink. The family half
        is checkable per rule, over every rule the derived sweep finds.

        The size half is not, quite. `.next-project-value--absent` declares
        13px, which is CORRECT, because no context that rule reaches resolves
        its paired value BELOW 13px. Re-resolved through `css_cascade` against
        the v3 sheet, absence/value: session line 13.0/inherited, project scope
        13.0/13.0, activity title 13.0/inherited, cockpit recovery 13.0/15.0,
        and the goal-text slot 15.0/15.0 where the absence shares the value's
        own rule. Raising the absence alone would make a stated absence render
        larger than the fact it replaces, which is the defect this milestone has
        already shipped four times.

        So the size clause is bound to the pair rather than to a floor: the
        exception holds only while `.next-project-value--known` declares no size
        of its own. Give the value a size and this reds, which is exactly when
        the pair must be re-measured.

        The census below is a census and not a pairing claim. Four of its seven
        rows are the pairs `AnAbsenceNeverOutranksTheValueItReplacesTest`
        resolves; the other three -- capacity, Held to's own absence paragraph,
        and the observed record's -- are absence PARAGRAPHS that replace a
        collection rather than a value, so there is no second selector to draw
        them against. DRC-4602 owns that wider class. What this assertion holds
        is that the set and the count are both what was measured, so a rule
        arriving below the floor cannot do it quietly.

        v3 moved every one of the seven sub-floor sizes from 12.5px to 13px --
        the deleted `--fs-xs` step onto the surviving `--fs-label` one. Seven
        rules, the same seven selectors: nothing joined the sub-floor set and
        nothing left it, so the count below is unchanged and only the figure
        moved.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        tokens = _type_tokens(css)
        absences = _absence_rules(css)
        self.assertEqual(14, len(absences))
        for selector, decls in absences:
            with self.subTest(selector=selector):
                self.assertFalse(_is_mono(decls))
        sized = {
            selector: size
            for selector, decls in absences
            if (size := _declared_size(decls, tokens)) is not None
        }
        below = {sel: size for sel, size in sized.items() if size < SENTENCE_FLOOR_REM}
        # TWO rules sit below the floor, against seven before DRC-4602, which
        # raised the other five to the sentence tier along with the rest of the
        # sub-floor census. Both survivors are deliberate and neither has a
        # paired value that outranks it:
        #
        #   `.next-project-value--absent` is the base rule, and the exception is
        #   bound to the pair rather than to a floor: `.next-project-value--known`
        #   declares no size at all, so raising the absence alone would make a
        #   stated absence render larger than the fact it replaces. The
        #   assertion below that `--known` stays unsized is what keeps that
        #   reasoning honest -- give the value a size and this reds, which is
        #   exactly when the pair must be re-measured.
        #
        #   `.next-capacity-absent` is an absence PARAGRAPH replacing a
        #   collection, so there is no second selector to draw it against.
        #
        #   `.next-cockpit-recovery .next-project-value--absent` was RAISED by
        #   DRC-4602 and put back the same day. DRC-4614's rendered-path guard
        #   caught what the raise did: in `.next-cockpit-waiting` the --known
        #   branch inherits 13px, so the raised absence resolved 15px against a
        #   13px value -- an inversion created by the fix for the floor. The
        #   goal-text slot inside the same briefing IS raised, by its own more
        #   specific rule, because there both branches move together.
        #
        # The recovery pair moved together: its value and its absence both
        # resolve to 15px now, measured on the element path the application
        # builds, which is what cleared the one entry DRC-4614's rendered-path
        # guard was carrying.
        self.assertEqual(
            {
                ".next-project-value--absent": css_cascade.rem(13.0),
                ".next-capacity-absent": css_cascade.rem(13.0),
                ".next-cockpit-recovery .next-project-value--absent": css_cascade.rem(13.0),
            },
            below,
        )
        known = [
            decls for selector, decls in _rules(css) if selector == ".next-project-value--known"
        ]
        self.assertEqual(1, len(known))
        self.assertIsNone(_declared_size(known[0], tokens))

    def test_every_absence_rule_that_colours_itself_colours_through_the_register(self) -> None:
        """The half of DRC-4589's ruling a repoint would otherwise break.

        `--ink-absence` exists so the absence role can move without touching
        every rule that plays it. Four rules spelled `var(--ink3)` instead, and
        the marker list that preceded the derived sweep could not see any of
        them: a repoint of the register would have moved seven absence rules
        and left four behind, in an ink now reserved for labels, with this
        module green.

        The set AND the count, because neither implies the other. A rule that
        declares no colour at all inherits one, and there are four of those --
        asserting only the declared set would let a fifth rule lose its colour
        silently.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        declared: list[str] = []
        silent = 0
        for _selector, decls in _absence_rules(css):
            colour = re.search(r"(?:^|;)\s*color:\s*([^;]+)", decls)
            if colour is None:
                silent += 1
                continue
            declared.append(colour.group(1).strip())
        self.assertEqual({"var(--ink-absence)"}, set(declared))
        self.assertEqual(10, len(declared))
        self.assertEqual(4, silent)

    def test_a_mono_absence_is_caught(self) -> None:
        """Mutation: the reading clause's `var(--sans)` -> `var(--mono)`.

        Family is how an absence is told from a value here: v0.27.0 kept both
        on `--ink3` and v3 puts both on `--ink2`, so in neither sheet does ink
        separate them. An absence that took mono would read as a string a source
        published.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        # The shorthand as this lineage spells it, repointed onto the token the
        # rule actually carries. It has now been wrong twice for the same
        # reason: the branch this test came from read
        # `font:500 var(--fs-sentence)/1.55` against a pre-squash tree, #361
        # left the rule on `--fs-xs`, and v3 deleted `--fs-xs` for
        # `--fs-label`. A mutation string that matches nothing is a mutation
        # test that proves nothing, which is what `assertNotEqual` below is for.
        #
        # **Third time, 2026-09-22.** DRC-4602 raised this rule to `--fs-body`
        # with the rest of the sub-floor census, and the `--fs-label` spelling
        # stopped matching. The `assertNotEqual` caught it, which is the whole
        # reason it is there -- but three breakages from the same cause is the
        # signal that the string is the fragile part. It is pinned to the rule's
        # own text on purpose, because a mutant built by substitution would
        # mutate whatever the rule happens to say and could no longer be read as
        # a specific claim about a sans absence turning mono.
        mutant = css.replace(
            ".next-cockpit-reading-clause-absent{font:var(--fs-body)/1.5 var(--sans)",
            ".next-cockpit-reading-clause-absent{font:var(--fs-body)/1.5 var(--mono)",
            1,
        )
        self.assertNotEqual(css, mutant)
        self.assertEqual(0, sum(1 for _, decls in _absence_rules(css) if _is_mono(decls)))
        self.assertEqual(1, sum(1 for _, decls in _absence_rules(mutant) if _is_mono(decls)))

    def test_every_rule_colouring_a_withheld_element_keeps_the_absence_ink(self) -> None:
        """DRC-4589's ink ruling, stated as the property rather than as a count.

        The criterion was drafted as "exactly one rule colours
        `[data-next-withheld]`", on the reading that the second such rule's
        `color:var(--ink3)` was redundant with the first. Measured, it is not:
        `.next-cockpit-scope-tree small` sets `color:var(--ink2)` at (0,1,1) and
        beats the bare `[data-next-withheld]` at (0,1,0), so the (0,2,1) rule is
        the only thing holding those withheld smalls on `--ink3`. Dropping it
        would turn them ink2 and break the ruling it was meant to serve. The
        falsifiable property underneath is asserted instead.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        coloured = [
            (selector, decls)
            for selector, decls in _rules(css)
            if "[data-next-withheld]" in selector and "color:" in decls
        ]
        self.assertEqual(2, len(coloured))
        for selector, decls in coloured:
            with self.subTest(selector=selector):
                # The register rather than the literal, since DRC-4589 made it
                # the single place the ruling can be re-read from.
                self.assertEqual(["var(--ink-absence)"], re.findall(r"color:\s*([^;]+)", decls))

    def test_reduced_motion_keeps_the_static_live_cue_without_animation(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        live_rule = re.search(r"\.next-live \.next-status-dot\{([^}]*)\}", styles)
        reduced = re.search(
            r"@media\(prefers-reduced-motion:reduce\)\{\s*"
            r"([^{}]+)\{([^}]*)\}",
            styles,
        )

        self.assertIsNotNone(live_rule)
        self.assertIsNotNone(reduced)
        self.assertIn("color:var(--ink)", live_rule.group(1) if live_rule else "")
        self.assertIn("animation:next-live-pulse", live_rule.group(1) if live_rule else "")
        self.assertIn(".next-live .next-status-dot", reduced.group(1) if reduced else "")
        self.assertIn("animation:none", reduced.group(2) if reduced else "")

    def test_activity_subagent_names_can_shrink_inside_the_card(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        pill = re.search(r"\.next-activity-subagent\{([^}]*)\}", styles)
        name = re.search(r"\.next-activity-subagent-name\{([^}]*)\}", styles)

        self.assertIsNotNone(pill)
        self.assertIsNotNone(name)
        self.assertIn("min-width:0", pill.group(1) if pill else "")
        self.assertIn("max-width:100%", pill.group(1) if pill else "")
        self.assertIn("min-width:0", name.group(1) if name else "")
        self.assertIn("overflow-wrap:anywhere", name.group(1) if name else "")

    def test_operator_text_breaks_an_unbreakable_token(self) -> None:
        # The instruction line quotes what the operator typed, and 50 of 1,789
        # published lines carry a single token over 80 characters (longest 113) —
        # pasted URLs, which `shorten_paths` leaves whole on purpose because the
        # repo and issue number in them are the informative part. Under
        # `max-width:760px` the detail padding drops to 0, so one such token
        # gives the whole page a horizontal scrollbar. Every comparable surface
        # in this stylesheet already guards it.
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        for selector in (
            r"\.next-operation-identity,\.next-operation-fact",
            r"\.next-session-detail-instruction",
        ):
            with self.subTest(selector=selector):
                rule = re.search(selector + r"\{([^}]*)\}", styles)
                self.assertIsNotNone(rule)
                self.assertIn("overflow-wrap:anywhere", rule.group(1) if rule else "")

    def test_session_detail_tone_rails_use_the_fixed_palette(self) -> None:
        # Keyed on the observation tone, not the raw harness state: the rule carries
        # what was observed, which is what the palette encodes. The state-keyed
        # predecessor could not express `bad`, so a session that ended dirty wore the
        # same rail as one still working.
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        for tone, color in (
            ("want", "var(--amber)"),
            ("bad", "var(--clay)"),
            ("ok", "var(--accent)"),
        ):
            with self.subTest(tone=tone):
                rule = re.search(
                    rf'\.next-session-detail\[data-tone="{tone}"\] '
                    r"\.next-session-current\{([^}]*)\}",
                    styles,
                )
                self.assertIsNotNone(rule)
                self.assertIn(f"border-left-color:{color}", rule.group(1) if rule else "")
        # Unknown never gets colour, so it must have no override at all rather than a
        # muted one. Absence of the rule is the assertion.
        self.assertIsNone(
            re.search(
                r'\.next-session-detail\[data-tone="unknown"\] \.next-session-current\{',
                styles,
            ),
        )

    def test_project_scope_tree_is_left_at_wide_width_and_stacks_when_narrow(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        styles = styles.split("/* ===== COCKPIT ===== */", 1)[1].split(
            "/* ===== SUBSTRATE ===== */", 1
        )[0]
        wide = re.search(r"\.next-cockpit-shell\{([^}]*)\}", styles)
        narrow = re.search(
            r"@media\(max-width:1279px\)\{[\s\S]*?"
            r"\.next-cockpit-shell\{([^}]*)\}",
            styles,
        )

        self.assertIsNotNone(wide)
        self.assertIn("grid-template-columns:264px minmax(0,1fr)", wide.group(1) if wide else "")
        self.assertIsNotNone(narrow)
        self.assertIn("grid-template-columns:1fr", narrow.group(1) if narrow else "")
        self.assertNotIn("overflow-x:auto", wide.group(1) if wide else "")

        wide_switcher = re.search(r"\.next-cockpit-scope-switcher\{([^}]*)\}", styles)
        narrow_tree = re.search(
            r"@media\(max-width:1279px\)\{[\s\S]*?\.next-cockpit-scope-tree\{([^}]*)\}",
            styles,
        )
        narrow_switcher = re.search(
            r"@media\(max-width:1279px\)\{[\s\S]*?\.next-cockpit-scope-switcher\{([^}]*)\}",
            styles,
        )
        self.assertIsNotNone(wide_switcher)
        self.assertIn("display:none", wide_switcher.group(1) if wide_switcher else "")
        self.assertIsNotNone(narrow_tree)
        self.assertIn("display:none", narrow_tree.group(1) if narrow_tree else "")
        self.assertIsNotNone(narrow_switcher)
        self.assertIn("display:block", narrow_switcher.group(1) if narrow_switcher else "")

        project_cue = re.search(r"\.next-scope-cue--project\{([^}]*)\}", styles)
        session_cue = re.search(r"\.next-scope-cue--session\{([^}]*)\}", styles)
        square = re.search(r"\.next-scope-marker--square\{([^}]*)\}", styles)
        round_marker = re.search(r"\.next-scope-marker--round\{([^}]*)\}", styles)
        branch = re.search(r"\.next-scope-cue--session:before\{([^}]*)\}", styles)
        self.assertIsNotNone(project_cue)
        self.assertIn("border-left:2px solid", project_cue.group(1) if project_cue else "")
        self.assertIsNotNone(session_cue)
        self.assertIn("padding-left:18px", session_cue.group(1) if session_cue else "")
        self.assertIsNotNone(square)
        self.assertIn("border-radius:0", square.group(1) if square else "")
        self.assertIsNotNone(round_marker)
        self.assertIn("border-radius:50%", round_marker.group(1) if round_marker else "")
        self.assertIsNotNone(branch)
        self.assertIn("border-top:1px solid", branch.group(1) if branch else "")
        tree = re.search(r"\.next-cockpit-scope-tree\{([^}]*)\}", styles)
        self.assertIsNotNone(tree)
        self.assertNotIn("overflow-x:auto", tree.group(1) if tree else "")

        now_wide = re.search(
            r'\.next-cockpit-panel\[data-next-cockpit-panel="now"\]\{([^}]*)\}', styles
        )
        now_narrow = re.search(
            r"@media\(max-width:760px\)\{[\s\S]*?"
            r'\.next-cockpit-panel\[data-next-cockpit-panel="now"\]\{([^}]*)\}',
            styles,
        )
        self.assertIsNotNone(now_wide)
        self.assertIn(
            "grid-template-columns:repeat(2,minmax(0,1fr))",
            now_wide.group(1) if now_wide else "",
        )
        self.assertIsNotNone(now_narrow)
        self.assertIn("grid-template-columns:1fr", now_narrow.group(1) if now_narrow else "")

    def test_the_rail_card_puts_the_title_above_its_meta_in_two_registers(self) -> None:
        """DRC-4597 AC-1 and AC-4. The title is the card's value and the meta is
        the caption beneath it; a withheld title swaps the ink and never the
        size.

        v0.27.0 set the title in mono and the withheld swap changed family as
        well as ink. v3 sets the title in sans, and the withheld rule
        (`.next-cockpit-scope-tree [data-next-withheld]`) now declares
        `font-family:var(--sans)` and `color:var(--ink-absence)` and no size at
        all -- so family is no longer the separator and the clause above says
        only what the sheet still does. What the criterion is actually about
        survives intact: the two halves are two registers, and the caption never
        outgrows the value it captions.
        """
        styles = frontend_page.asset_path("styles.css").read_text(encoding="utf-8")
        title = re.search(r"\.next-cockpit-scope-title\{([^}]*)\}", styles)
        meta = re.search(r"\.next-cockpit-scope-meta\{([^}]*)\}", styles)
        self.assertIsNotNone(title)
        self.assertIsNotNone(meta)
        title_body = title.group(1) if title else ""
        meta_body = meta.group(1) if meta else ""
        self.assertIn("font:var(--fs-body) var(--sans)", title_body)
        self.assertIn("color:var(--ink)", title_body)
        # One clipped line. `white-space:normal` from the rail's own reset is
        # the rule this has to beat, and the reset no longer selects a bare
        # `span` inside the link, so nothing overrides it at equal specificity.
        self.assertIn("text-overflow:ellipsis", title_body)
        self.assertIn("white-space:nowrap", title_body)
        self.assertIn("font:var(--fs-label) var(--mono)", meta_body)
        # `--ink3` in v0.27.0. v3 retired it from the reading inks -- it is now
        # only the text of an inert control -- so a caption left on it would be
        # the one piece of prose on the board painted in the disabled ink. The
        # register separation is what the criterion wants and it is asserted as
        # a difference below, not as two spellings that happen to differ today.
        self.assertIn("color:var(--ink2)", meta_body)
        self.assertNotIn("color:var(--ink);", meta_body)
        # Resolved, not just named. The two assertions above pin which TOKEN
        # each half uses; they cannot see a `:root` that redefines one of those
        # tokens so the caption outgrows the value it sits under. Measured by
        # DRC-4592 on the v0.27.0 pair: a `--fs-2xs` raised above `--fs-sm`
        # passes every other check in this file, and the same hole is open on
        # `--fs-label` against `--fs-body`. This is the numeric half of the pair
        # that `AnAbsenceNeverOutranksTheValueItReplacesTest` used to carry
        # before that class narrowed to sentence-tier absences, which the rail
        # card is not.
        tokens = {
            name: float(value)
            for name, value in re.findall(r"--(fs-[a-z0-9-]+):([0-9.]+)rem", styles)
        }
        self.assertGreaterEqual(
            tokens["fs-body"],
            tokens["fs-label"],
            "the rail card's meta outgrew the title it captions",
        )
        self.assertNotIn(
            ".next-cockpit-scope-tree span,", styles, "a bare span reset would unclip the title"
        )
        self.assertNotIn(".next-cockpit-scope-name{", styles)
        mark = re.search(r"\.next-cockpit-scope-mark:before\{([^}]*)\}", styles)
        self.assertIsNotNone(mark)
        self.assertIn("border-top:1px solid", mark.group(1) if mark else "")

    def test_the_tab_cue_never_renders_an_absence_larger_than_its_figure(self) -> None:
        """DRC-4592 AC-4 and AC-5. Both branches of the cue's state ternary
        resolve here; the pair is never on screen at one moment, so only the
        stylesheet can be asked whether they agree.
        """
        styles = frontend_page.asset_path("styles.css").read_text(encoding="utf-8")
        sizes = {}
        for selector in (
            ".next-cockpit-tab-cue",
            ".next-cockpit-tab-cue--pending",
            ".next-cockpit-tab-cue--unobserved",
            # The fourth branch of the same ternary. It was missing from this
            # loop while the rule existed in v0.27.0 too, so the state a reader
            # meets when the cue cannot be computed at all was the one state
            # nothing held to the others' size.
            ".next-cockpit-tab-cue--unavailable",
        ):
            block = re.search(re.escape(selector) + r"\{([^}]*)\}", styles)
            self.assertIsNotNone(block, f"{selector} declares no rule of its own")
            body = block.group(1) if block else ""
            token = re.search(r"font:(?:\d+ )?var\(--(fs-[a-z0-9-]+)\)", body)
            self.assertIsNotNone(token, f"{selector} declares no size, so it inherits one")
            sizes[selector] = token.group(1) if token else ""
        self.assertEqual(1, len(set(sizes.values())), f"the cue states disagree on size: {sizes}")
        lede = re.search(r"\.next-cockpit-lede\{([^}]*)\}", styles)
        self.assertIsNotNone(lede)
        self.assertIn("font:var(--fs-body)/1.55 var(--sans)", lede.group(1) if lede else "")
        self.assertIn("color:var(--ink2)", lede.group(1) if lede else "")
        define = re.search(r"\.next-cockpit-define\{([^}]*)\}", styles)
        self.assertIsNotNone(define)
        # 500 weight, matching `.next-cockpit-reading-why`: a definition sits in
        # the same register as the caveats it stands beside, not a fourth one.
        self.assertIn("font:500 var(--fs-body)/1.55 var(--sans)", define.group(1) if define else "")

    def test_four_cockpit_tabs_fit_the_smallest_phone_without_pills(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        phone_tabs = re.search(
            r"@media\(max-width:420px\)\{[\s\S]*?\.next-cockpit-tabs\{([^}]*)\}",
            styles,
        )
        phone_buttons = re.search(
            r"@media\(max-width:420px\)\{[\s\S]*?\.next-cockpit-tabs button\{([^}]*)\}",
            styles,
        )

        self.assertIsNotNone(phone_tabs)
        self.assertIn(
            "grid-template-columns:repeat(4,minmax(0,1fr))",
            phone_tabs.group(1) if phone_tabs else "",
        )
        self.assertNotIn("overflow-x:auto", phone_tabs.group(1) if phone_tabs else "")
        self.assertIsNotNone(phone_buttons)
        self.assertIn("min-width:0", phone_buttons.group(1) if phone_buttons else "")
        self.assertNotIn("border-radius", phone_buttons.group(1) if phone_buttons else "")

    def test_load_page_preserves_its_byte_oracles(self) -> None:
        # Per-part first, deliberately. Every part feeds the assembled page, so a
        # one-part edit fails the assembled oracle too. Naming the part that moved
        # is the more useful failure of the two.
        expected_parts = {
            "next-boot.js": (
                31_382,
                "bd9516f3a1795413cc8fd43c729d5c0d4ffe5ec105a85eefb6003daf7281e3cb",
            ),
            "next-observed.js": (
                32_982,
                "d83b752fb8929e95b75b8426d772f99b1c4428051a12d131ef4158e288f1d80c",
            ),
            "next-attention.js": (
                56_558,
                "cf7eb26d4135f352efe4cd7256e46f26514ba9b8e19422ac32fc840ac9b4e71a",
            ),
            "next-notify.js": (
                11_104,
                "2fdc43bbb9382ce92fe972d628b6bf11e0342f35bfa43e9965133c3315b39ad1",
            ),
            "next-cockpit-compat.js": (
                599,
                "ebc70801be79cd5805a85a281dd0566a08a97bab72d0356ae923d20f60310db4",
            ),
            "project.js": (
                112_662,
                "81e7f6490f9d6c2e128549aff8bb54c2f6bebaec15b03bfebe3e057b4ef8f587",
            ),
            "next-chrome.js": (
                41_434,
                "7af1dd2cfe9b3e3274de234fbb19e4c918a7b7eb12fe9580a5468b15527c6557",
            ),
            "next-capacity.js": (
                32_261,
                "986a0b0d74771bbb9f1d9df520dbb6c91d5916685fe365a64eff61c29acab7cc",
            ),
            "next-sessions.js": (
                27_289,
                "2c8f1e1f80b1f2a88b4cfee335a39f4078e5bd3169ed29e3a21ea473ce70c5a1",
            ),
            "next-projects.js": (
                5_829,
                "0324f6aebe951a37bde0f710c73c77f1007d26159a5b33e453b54711b4263348",
            ),
            "next-project.js": (
                20_930,
                "ecdbe1f2c556bfa4b918ebfff1d5a535c539ce6660c0c51b719e7b4ac6bcf40d",
            ),
            "next-intent.js": (
                21_732,
                "5e3ed558080982391079c7a2ea197b8d9e4446ec09ec4592415ab4b6003b1d03",
            ),
            "next-activity.js": (
                6_467,
                "f44d5da254b7a6be30b05a4c03bfd83050608b0d9da35910c3e640a742c0e2cc",
            ),
            "next-session.js": (
                39_699,
                "aeee9bce3426b321164d78e7dcac919787446ae8142021bac313e49b93d12b1f",
            ),
            "next-workstream.js": (
                18_659,
                "9680ee01d19296e87cf9b35230a51a7e98ddc764c5bfb80f0e18e7723ece8a04",
            ),
            "next-delegation.js": (
                12_735,
                "aa8e8ab3a5531e28ee08f555f901fd29d873aecd4bdd0e498199036efe16dfc2",
            ),
            "next-controls.js": (
                18_846,
                "7d3250df229af732ebb668171e4cb284f0c1e00e4b0241710d1e5f0ac2a76777",
            ),
            "next-cockpit.js": (
                264_564,
                "9ce4dad23380f9a0e0839a0118c5c800a657961a7493ae433431955a09e8d348",
            ),
            "next-render.js": (
                12_231,
                "aaa3804c38530dcde476e2306801e3849ff9cea3d6b16a3891abe215c6f98abb",
            ),
            "next-live.js": (
                3_340,
                "755ae1c40ffeef20f6c5bfddeafbc798e62ac7e9d2ba9365b92d7ba032905e96",
            ),
        }
        self.assertEqual(tuple(expected_parts), frontend_page.APP_PARTS)
        for name, (size, digest) in expected_parts.items():
            with self.subTest(part=name):
                data = frontend_page.asset_path(name).read_bytes()
                self.assertEqual(size, len(data))
                self.assertEqual(digest, hashlib.sha256(data).hexdigest())

        styles = frontend_page.asset_path("styles.css").read_bytes()
        self.assertEqual(142_557, len(styles))
        self.assertEqual(
            "1c638b426fd8199f20b3e3b7908c752cb5ef0fa90dafae2feb4efabce69ef5be",
            hashlib.sha256(styles).hexdigest(),
        )

        assembled = frontend_page.load_page()
        self.assertEqual(1_104_174, len(assembled))
        self.assertEqual(
            "cf7c01a503bf2496c7d50fb71d93a06bc8634869de948ace54501c32c70ec0f6",
            hashlib.sha256(assembled).hexdigest(),
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class OneDepartureRowTreatmentTest(unittest.TestCase):
    """DRC-4514. The design's own note: reuse this row, do not invent a second.

    The review section puts two collections under one heading, and until this
    was pinned the two rows in it rendered in four different sizes each -- 10px
    against 12.5px for the constraint, 12.5px against 11.5px for the clause,
    13.5px against 12.5px for the model's sentence, 10px against 11.5px for the
    evidence line. The third treatment's band is 13 to 13.5px, so the sentence
    at 12.5px was outside it as well as different from its neighbour.

    Asserted as shared SELECTORS rather than as matching values, because two
    declaration lists that happen to agree today are the state this drifted out
    of. One rule cannot disagree with itself.
    """

    def test_one_string_in_the_bundle_states_the_superseded_fact(self) -> None:
        """DRC-4563. Two wordings of one fact is the divergence the log refuses.

        The reading block and the departure row differ only in their subject
        word, so the characters after it are owned once, in the boot part,
        beside the other two sentences more than one surface states. A second
        literal copy anywhere in the bundle is what this counts. It counts
        characters, so a copy broken over a line join would not be seen; what
        it is for is the ordinary way a second wording arrives, which is
        someone typing the sentence again beside the row that wanted it.
        """
        tail = "is current, so it does not describe what you are asking for now."
        counts = {
            name: frontend_page.asset_path(name).read_bytes().decode().count(tail)
            for name in frontend_page.APP_PARTS
        }

        self.assertEqual(1, counts["next-boot.js"], f"the boot part owns it: {counts}")
        self.assertEqual(1, sum(counts.values()), f"and owns it alone: {counts}")

    def test_the_two_departure_rows_are_declared_by_one_rule_each(self) -> None:
        styles = frontend_page.asset_path("styles.css").read_bytes().decode()
        rules: dict[str, list[str]] = {}
        for chunk in styles.split("}"):
            head, _, body = chunk.rpartition("{")
            if head:
                rules.setdefault(head.strip().splitlines()[-1].strip(), []).append(body)

        for cockpit, session in (
            (".next-cockpit-departure", ".next-session-departure"),
            (".next-cockpit-reading-name", ".next-session-departure-name"),
            (".next-cockpit-reading-clause", ".next-session-departure-clause"),
            (".next-cockpit-reading-detail", ".next-session-departure-reading"),
            (".next-cockpit-reading-evidence", ".next-session-departure-base"),
            (".next-cockpit-reading-stale", ".next-session-departure-stale"),
        ):
            with self.subTest(pair=session):
                shared = [
                    head
                    for head in rules
                    if cockpit in head.split(",") and session in head.split(",")
                ]
                self.assertEqual(
                    1,
                    len(shared),
                    f"{session} must share exactly one declaration list with {cockpit}",
                )


class NextPageBehaviorTest(NextPageJsHarness):
    def test_the_next_bundle_reads_query_values(self) -> None:
        out = self._run_page_js(
            'console.log(JSON.stringify({view: qs("view"), missing: qs("missing")}));',
            'location.search = "?view=project";\n',
        )

        self.assertEqual({"view": "project", "missing": None}, out)

    def test_esc_escapes_all_five_characters(self) -> None:
        out = self._run_page_js(
            "console.log(JSON.stringify(esc(`<img src=x onerror='1' data-note=\"&\">`)));"
        )

        self.assertEqual(
            "&lt;img src=x onerror=&#39;1&#39; data-note=&quot;&amp;&quot;&gt;",
            out,
        )

    def test_payload_clock_durations_use_compact_second_through_day_tiers(self) -> None:
        out = self._run_page_js(
            """
nextData = {generated: 10000};
const values = [null, NaN, Infinity, -1, 0, 59.9, 60, 3599, 3600, 7740,
  86400, 90 * 86400 + 3 * 3600];
console.log(JSON.stringify({
  formatted: values.map(nextFormatDuration),
  since: [null, "bad", 10010, 9700].map(nextDurationSince)
}));
"""
        )

        self.assertEqual(
            [
                None,
                None,
                None,
                None,
                "0s",
                "59s",
                "1m",
                "59m",
                "1h 0m",
                "2h 9m",
                "1d 0h",
                "90d 3h",
            ],
            out["formatted"],
        )
        self.assertEqual([None, None, "0s", "5m"], out["since"])

    def test_the_default_bundle_opens_on_sessions_with_the_primary_navigation(self) -> None:
        out = self._run_page_js(
            "console.log(JSON.stringify(__els.app.innerHTML));",
            '__els.app = {innerHTML: ""};\n',
        )

        # All three top-level routes, because this assertion pinned the literal
        # two-link nav and was one of the two places that held Attention off the
        # header while the router, the title and the `a` shortcut all knew it
        # (DRC-4421). Kept as a literal rather than loosened: it is the mounted
        # bundle's own markup, and the order is part of what a reader learns.
        # Sessions is the landing view (DEC-20), so it is the one marked; the
        # links keep their learned order and Projects stays one click away.
        self.assertIn(
            '<nav aria-label="Primary"><a href="#n=projects">Projects</a>'
            '<a href="#n=sessions" aria-current="page">Sessions</a>'
            '<a href="#n=attention">Attention</a>'
            '<a href="#n=intent">Intent log</a></nav>',
            out,
        )
        self.assertNotIn('class="next-breadcrumb" aria-label="Breadcrumb"', out)
        self.assertNotIn("overview", out)


class TheBoardHasOneControlPrimitiveTest(unittest.TestCase):
    """DRC-4590. The stylesheet had no way to say "this one": no shared control
    class and no radius token, so every control was its own recipe and the whole
    range was spent on the secondary tier.

    The sweep that produced this issue found 24 resting control rules over six
    corner treatments. Seven collapse here; the remaining five are filed as
    their own issue and the exempt ones are named with reasons in the sheet, so
    AC-1 and AC-2 are accepted on these enumerated verifiers rather than on a
    universal reading neither could satisfy.
    """

    # The seven the primitive absorbs. Enumerated rather than discovered,
    # because "every control rule" is the claim this issue cannot make.
    COLLAPSED = (
        ".next-notify-button",
        ".next-stalled button",
        ".next-session-copy",
        ".next-steer button",
        ".next-guardrail-add",
        ".next-usage-switch button",
        ".next-cockpit-reading button",
    )

    def setUp(self) -> None:
        raw = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        # Comments out first. They carry commas and selector-shaped text, and
        # a selector head read straight out of the source picks up whatever
        # comment precedes the rule -- which matches nothing and reads as a
        # missing rule rather than as a broken parser.
        self.styles = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)

    def rule(self, selector: str) -> str:
        """The body of the rule whose selector list contains `selector` exactly.

        Matched on the whole comma-separated head, so `.next-steer button` does
        not silently answer with `.next-steer button:hover`.
        """
        for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.styles):
            heads = [head.strip() for head in block.group(1).split(",")]
            if selector in heads:
                return block.group(2)
        return ""

    def test_one_token_and_one_class_own_the_resting_box(self) -> None:
        """AC-1."""
        root = re.findall(r"(?:\A|\n):root\{([^}]*)\}", self.styles, re.DOTALL)
        # `--radius-control` in v0.27.0, `--r-control` in v3's four-step radius
        # scale. The token was renamed, not dropped, so the criterion is intact
        # and only its spelling moved.
        self.assertTrue(any("--r-control:" in block for block in root))
        # Exactly one rule owns `.next-action` on its own, so the primitive has
        # a single definition rather than a definition per caller.
        owners = [
            block.group(1).strip()
            for block in re.finditer(r"([^{}]+)\{[^{}]*\}", self.styles)
            if block.group(1).strip() == ".next-action"
        ]
        self.assertEqual(1, len(owners))
        body = self.rule(".next-action")
        self.assertIn("border-radius:var(--r-control)", body)

    def test_no_collapsed_rule_keeps_its_own_recipe(self) -> None:
        """AC-1's falsifier: the collapse done by adding the class to a
        selector group, leaving the duplicated declarations in place. That
        reads as passing in a grep for the class name and changes nothing."""
        for selector in self.COLLAPSED:
            with self.subTest(selector=selector):
                body = self.rule(selector)
                self.assertNotEqual("", body, f"{selector} has no rule to check")
                self.assertNotIn("border-radius:", body)
                self.assertNotRegex(body, r"(?:^|;)border:1px")

    def test_a_disabled_control_survives_greyscale(self) -> None:
        """AC-3. Ink alone cannot carry this, in either sheet, and the reason
        inverted between them. In v0.27.0 `--ink3` WAS the resting prose colour,
        so a disabled control drawn one step down vanished with colour removed.
        v3 retired `--ink3` from the reading inks and spends it here, which
        removes that particular collision and leaves the underlying point: a
        tone is not a state, and greyscale keeps only shape.

        So this reads the two things that survive the colour being taken away --
        the dashed boundary and the hatched fill -- rather than the ink. The
        hatch is new in v3 and is asserted rather than ignored: it is now the
        louder of the two carriers, and a v4 that drops it would leave a single
        1px dash doing all the work with this test still green.
        """
        body = self.rule('.next-action[aria-disabled="true"]')
        # The shorthand, because that is how v3 writes it; v0.27.0 used the
        # `border-style` longhand. Anchored so `border-style:dashed` on some
        # other edge cannot answer for the box, and the width is read too --
        # `border:0 dashed` is dashed and invisible.
        self.assertRegex(body, r"(?:^|;)border:1px dashed ")
        self.assertIn("background:var(--hatch)", body)
        self.assertIn("cursor:not-allowed", body)
        # The stalled control is waiting, not refusing, and says so with its
        # own cursor. Collapsing the two loses a distinction a reader acts on.
        stalled = self.rule(".next-stalled button:disabled")
        self.assertIn("cursor:wait", stalled)
        # And it does not inherit the refusal's border either. Dashed is the
        # register for a control refusing a press; this one is waiting for a
        # retry it makes itself, so it states `solid` rather than letting the
        # primitive say the wrong thing about the state. Without this the
        # cursor and the border disagree about what the control is doing.
        self.assertIn("border-style:solid", stalled)
        self.assertGreater(
            self.styles.index(".next-stalled button:disabled"),
            self.styles.index('.next-action[aria-disabled="true"]'),
            "the stalled override must come after the primitive to win at equal specificity",
        )

    def test_the_tripwire_control_gets_the_box_its_hit_area_already_had(self) -> None:
        """AC-4. It was given the shared outlined recipe and stripped of it on
        the next line, so it read as a line of prose inside a 44px target: what
        a reader can see and what they can hit did not agree."""
        body = self.rule(".next-guardrail-add")
        self.assertNotEqual("", body)
        self.assertNotRegex(body, r"(?:^|;)border:0")
        self.assertNotRegex(body, r"(?:^|;)padding:0")
        # The 44px band is inherited rather than redeclared, from the one rule
        # that owns it for every control on the board.
        self.assertIn("min-block-size:44px", self.rule("#app a"))

    def test_the_irreversible_control_is_heavier_than_the_reversible_one(self) -> None:
        """AC-5. `clear` drops one unsaved box and `discard everything` deletes
        every revision, and the two carried the same five declarations."""
        discard = self.rule(".next-cockpit-held-discard button")
        armed = self.rule(".next-cockpit-held-discard button[aria-describedby]")
        self.assertNotEqual("", armed)
        # Width, not hue. The comment above these rules already rules colour
        # out here: `--clay` reads as an observation about the session, and
        # this is a control.
        self.assertRegex(armed, r"border-width:\d")
        block = self.styles[self.styles.index(".next-cockpit-held-discard") :][:800]
        for hue in ("--clay", "--amber", "--accent"):
            with self.subTest(hue=hue):
                self.assertNotIn(hue, block)
        # And the per-field `clear` stays bare text, which is what makes the
        # weight difference read at all. Boxing both removes the contrast this
        # criterion exists for.
        self.assertRegex(self.rule(".next-cockpit-held-field button"), r"(?:^|;)border:0")
        # The discard control takes its box from the primitive, so its own
        # rule no longer contradicts it with a borderless recipe.
        self.assertNotRegex(discard, r"(?:^|;)border:0")
        self.assertNotIn("border-radius:", discard)

    def test_the_dead_tab_strip_class_is_gone_and_its_neighbours_are_not(self) -> None:
        """AC-6. `.next-tabs` has zero references in every `.js`, `.py` and
        `.html` in the repository, but it survives in two shared selector
        groups carrying live classes -- so a line range deletes live rules."""
        self.assertEqual([], re.findall(r"\.next-tabs[^-\w]", self.styles))
        # The four live classes still resolve what they shared with it.
        self.assertIn("display:flex", self.rule(".next-header"))
        self.assertIn("display:flex", self.rule(".next-tabs-row"))
        self.assertIn("display:flex", self.rule(".next-header-right"))
        self.assertRegex(self.rule(".next-crumb"), r"(?:^|;)border:0")
        self.assertRegex(self.rule(".next-menu button"), r"(?:^|;)border:0")


class InkRoleRegistersAreDeclaredOnceAndSpelledNowhereElseTest(unittest.TestCase):
    """DRC-4589 AC-1, AC-3 and AC-6.

    One ink carried label, value, absence and caption. Twenty-one cockpit and
    session label rules each spelled `var(--ink3)` in their own declaration
    block, so moving the label tier meant editing twenty-one rules by hand and
    hoping none of them was a value.

    The registers are what make the next move one line. Nothing here asserts a
    colour changed, because none did: `--ink-label` and `--ink-absence` both
    resolve to `--ink3` under the captain's ruling of 2026-09-17, and
    `--ink-value` to `--ink`. What is asserted is that the indirection exists,
    that no rule bypasses it, and that the four registers live in the one
    `:root` the asset test admits.
    """

    REGISTERS = ("--ink-label", "--ink-value", "--ink-absence", "--ink-caption")

    def setUp(self) -> None:
        raw = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        self.styles = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)

    def test_the_four_registers_are_declared_in_the_one_root_block(self) -> None:
        roots = re.findall(r"(?:\A|\n):root\{([^}]*)\}", self.styles, re.DOTALL)
        self.assertEqual(1, len(roots), "a second :root fails the asset test's palette assertion")
        for register in self.REGISTERS:
            with self.subTest(register=register):
                self.assertIn(f"{register}:var(--ink", roots[0])

    def test_no_label_rule_spells_an_ink_token_in_its_own_block(self) -> None:
        """AC-1's oracle, which returned 21 on the tree this branch forked from
        and must return 0. It reads whole declaration blocks, so a rule that
        sets the label size and its own `--ink3` in one block is what fails it.
        """
        offenders = [
            line
            for line in self.styles.splitlines()
            if re.match(r"\.next-(cockpit|session)[^{]*\{[^}]*var\(--fs-label\)", line)
            and "var(--ink3)" in line
        ]
        self.assertEqual([], offenders)

    def test_every_rule_colouring_a_withheld_value_uses_the_absence_register(self) -> None:
        """AC-3 restated as the property rather than as a count.

        It was drafted as "exactly one rule colours `[data-next-withheld]`", on
        the reading that the scope-rail override's colour merely restated the
        base rule, and the captain ruled the override keeps only its family
        swap. DRC-4597 then moved the attribute off a `<small>` and onto
        `span.next-cockpit-scope-title`, which declares `color:var(--ink)` at
        the same (0,1,0) specificity and later in the sheet. On that tree the
        override is the only thing holding a withheld title on the absence
        register, and stripping it rendered an absent title in FULL ink,
        identical to a published one -- the inversion this milestone exists to
        remove. A count could not see that; the register can, and
        `WithheldTitleKeepsTheAbsenceInkTest` resolves the pair through the
        cascade.
        """
        colouring = [
            line
            for line in self.styles.splitlines()
            if re.search(r"data-next-withheld[^{]*\{[^}]*color:", line)
        ]
        self.assertNotEqual([], colouring)
        for line in colouring:
            with self.subTest(rule=line[:60]):
                self.assertIn("var(--ink-absence)", line)
                self.assertNotIn("var(--ink3)", line)

    def test_every_absent_variant_resolves_through_the_absence_register(self) -> None:
        """No `--absent` or `-clause-absent` rule may set an ink token directly:
        the register is the single place the ruling can be re-read from.
        """
        for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.styles):
            head, body = block.group(1).strip(), block.group(2)
            if "--absent" not in head and "-clause-absent" not in head:
                continue
            if "color:" not in body:
                continue
            with self.subTest(selector=head):
                self.assertIn("var(--ink-absence)", body)
                self.assertNotIn("var(--ink3)", body)


if __name__ == "__main__":
    unittest.main()


class TheDesignDocsLoadBearingClaimsAreBoundTest(unittest.TestCase):
    """DRC-4606: claims `docs/design-next-ui.md` makes that nothing checked.

    That issue listed six, in the reviewer's own order of risk, and two of them
    were already spoken for. Of the remaining four, the tracking census had the
    worst record: it had been wrong in production once, was corrected in prose,
    then *expanded* in prose, and **zero tests mentioned `letter-spacing` at
    all** -- the one occurrence in the suite was inside a comment.

    It had drifted again by the time this ran, and the proof is that the drift
    was one day old and mine: DRC-4613 added `.next-cockpit-tab-cue-stale` at
    `.06em`, the label register's only exception, and nothing reddened. That is
    the whole argument for binding a property rather than proof-reading a
    paragraph.

    The rejected alternative is a lint that greps the prose for stale figures.
    Measured across four sweeps of this document, a single retracted count
    survived as digits, then number-words, then a comparison, then a hedge. A
    search built from enumerated forms is never finished. These bind the
    property; the prose is then free to describe it.
    """

    # Every tracking the sheet uses, and what each one is for. A SET, because a
    # count passes a swap where one value leaves and another arrives.
    #
    # Three registers and an opt-out, which is the structure the prose
    # describes: labels are uppercase mono at `.07em`, display type is tightened
    # negatively at the two head/value steps, and a rule that must not inherit
    # tracking says so explicitly.
    TRACKINGS: ClassVar[frozenset[str]] = frozenset({".07em", "-.02em", "-.015em", "0", "normal"})

    @staticmethod
    def _sheet() -> str:
        return (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")

    @classmethod
    def _declarations(cls, css: str) -> list[tuple[str, str]]:
        """(selector, tracking) for every rule that declares one."""
        found = []
        for selector, body in _rules(css):
            match = re.search(r"letter-spacing:\s*([^;}]+)", body)
            if match:
                found.append((selector.strip(), match.group(1).strip()))
        return found

    def test_the_trackings_the_sheet_uses_are_exactly_the_recorded_set(self) -> None:
        used = {tracking for _selector, tracking in self._declarations(self._sheet())}
        self.assertEqual(self.TRACKINGS, used, "the set of trackings in the sheet moved")

    def test_the_label_register_tracks_uniformly(self) -> None:
        """The property the census was really about, and the one that drifted.

        A label rule is mono at the label step. Every one of them tracks at
        `.07em`; the negative values belong to display type at the head and
        value steps, and they are excluded by the recipe rather than by name.

        This is what `.06em` would have reddened, and did not, because nothing
        asserted it until now.
        """
        odd = {
            selector: tracking
            for selector, tracking in self._declarations(self._sheet())
            if tracking.startswith(".") and tracking != ".07em"
        }
        self.assertEqual({}, odd, "a label-register rule tracks at something other than .07em")

    def test_a_label_rule_that_drifts_off_the_register_is_caught(self) -> None:
        """Mutation: re-create yesterday's defect and watch this red."""
        mutant = self._sheet().replace("letter-spacing:.07em", "letter-spacing:.06em", 1)
        self.assertNotEqual(self._sheet(), mutant, "the mutant did not apply")
        odd = {
            selector: tracking
            for selector, tracking in self._declarations(mutant)
            if tracking.startswith(".") and tracking != ".07em"
        }
        self.assertEqual(1, len(odd), "a drifted label tracking went unnoticed")

    def test_the_measure_token_is_the_width_the_document_states(self) -> None:
        """`--measure` is named as 540px and about 72 characters; nothing held it.

        The character figure is not asserted, deliberately: it depends on the
        face and cannot be derived from the sheet. The width can, and it is the
        number the document actually commits to.
        """
        match = re.search(r"--measure:\s*([0-9.]+)rem", self._sheet())
        self.assertIsNotNone(match, "--measure is no longer declared in rem")
        assert match is not None
        self.assertEqual(540.0, float(match.group(1)) * css_cascade.ROOT_PX)

    def test_the_label_step_is_bound_by_name_and_not_only_as_the_minimum(self) -> None:
        """`--fs-label` at 13px, asserted as itself.

        `test_the_root_type_tokens_hold_the_label_floor` already holds the
        minimum of the scale, which is a different claim: it stays true if
        `--fs-label` moves and some other token takes the floor. The document
        names this token, so this names it too.
        """
        tokens = _type_tokens(self._sheet())
        self.assertIn("fs-label", tokens)
        self.assertEqual(css_cascade.rem(13.0), tokens["fs-label"])
