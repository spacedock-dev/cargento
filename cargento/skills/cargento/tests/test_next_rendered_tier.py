"""The sentence floor, asked of elements the emitters actually render.

`TheCompliantSetIsResolvedOnElementsNotOnRulesTest` in `test_next_page` asks
the same question of paths built out of the tier selectors themselves, which is
correct for the defect it was written for and blind to this one: a rule that
reaches a covered element through ancestors the tier selector never names can
take it below the floor, and the two rules never meet in a path derived from
either selector alone.

Measured on `58b1a81e`, which is what this module exists to stop:
`.next-steer>header p{font-size:var(--fs-label)}` takes `.next-steer-caveat`
from 0.9375rem to 0.8125rem, and the selector-derived sweep reports **zero**
below-floor selectors and **zero** skips. The mutation test below is that exact
mutant, put through this guard instead.

The paths come from `rendered_paths`, which executes the page's own JS and
parses what it writes into `#app`. See that module for why they are not
hypothesised from selectors and not hand-listed, and for the 8,873 false
positives that settled it.
"""

from __future__ import annotations

import shutil
import unittest
from typing import ClassVar, cast

from cargento_runtime.web import page as frontend_page

from . import css_cascade, rendered_paths
from .next_harness import NextPageJsHarness, storage_prelude
from .test_next_page import SENTENCE_FLOOR_REM, _tier_selectors

Shape = tuple[str, float]


def _shape(path: list[css_cascade.Node]) -> str:
    """One element's path, as the ancestor chain a reader could go and look at."""
    parts = []
    for node in path:
        classes = sorted(str(name) for name in cast("set[str]", node["classes"]))
        parts.append(f"{node['tag']}.{'.'.join(classes)}" if classes else str(node["tag"]))
    return "/".join(parts)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TheFloorHoldsOnElementsTheEmittersRenderTest(NextPageJsHarness):
    """DRC-4614: paths derived from the render, so ancestor-reaching rules are seen.

    This guard is only as wide as what the fixture renders, and that is a
    property of the instrument rather than a claim about the stylesheet.
    `test_the_render_covers_the_surfaces_this_guard_speaks_for` is what stops
    the coverage collapsing silently: a renamed route drops to the default view
    rather than erroring, and the element count is what notices.
    """

    paths: ClassVar[list[list[css_cascade.Node]]]
    css: ClassVar[str]
    tiers: ClassVar[dict[str, float]]
    per_route: ClassVar[dict[str, int]]

    # Elements the render resolves below the floor on the tree as it stands.
    # This is an inventory of known exceptions rather than a tolerance: the
    # assertion is set equality, so a new one reds and a fixed one reds too.
    #
    # Empty, and it has now been emptied twice by the mechanism working. It held
    # one entry for DRC-4602 and five for DRC-4632, and in both cases the fix
    # could not land without removing the excuse, because set equality reds on a
    # stale exception exactly as it reds on a new violation. That is the whole
    # argument for pinning a set rather than tolerating a count.
    #
    # Kept as an empty frozenset rather than deleted so the next element to fall
    # below the floor reds against something that exists, with somewhere obvious
    # to record why if it is deliberate.
    KNOWN_BELOW_FLOOR: ClassVar[frozenset[Shape]] = frozenset()

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        cls.tiers = _tier_selectors(cls.css)
        cls.paths = []
        cls.per_route = {}

    def setUp(self) -> None:
        super().setUp()
        if not type(self).paths:
            type(self).paths, type(self).per_route = self._harvest()

    def _harvest(self) -> tuple[list[list[css_cascade.Node]], dict[str, int]]:
        collected: list[list[css_cascade.Node]] = []
        per_route: dict[str, int] = {}
        for route in rendered_paths.FIXTURE_ROUTES:
            html = self._run_page_js(
                rendered_paths.render_script(route),
                prelude=storage_prelude({}, location_hash=route),
            )
            found = rendered_paths.paths_in(html)
            per_route[route] = len(found)
            collected.extend(found)
        return collected, per_route

    def _below_floor(self, css: str) -> set[Shape]:
        """Rendered elements a tier rule covers, that resolve below the floor."""
        tokens, rules = css_cascade.load_text(css)
        found: set[Shape] = set()
        for path in self.paths:
            if not any(css_cascade.matches(path, selector) for selector in self.tiers):
                continue
            size = css_cascade.resolve(path, tokens, rules)
            if size is not None and size < SENTENCE_FLOOR_REM:
                found.add((_shape(path), size))
        return found

    def _covered(self) -> int:
        return sum(
            1
            for path in self.paths
            if any(css_cascade.matches(path, selector) for selector in self.tiers)
        )

    def test_the_render_covers_the_surfaces_this_guard_speaks_for(self) -> None:
        """A guard over an empty render passes in silence, so count first.

        **This guard does not speak for the whole stylesheet, and the numbers
        say how far it does reach.** Measured on `58b1a81e`: ten routes render
        939 elements, 134 of them covered by some tier selector, and those 134
        are reached by **32 of the sheet's 107 tier selectors**. The other 75
        style surfaces this fixture never renders -- an empty state, a harness
        with no sessions, the legacy project view -- and the guard is silent
        about them rather than clearing them.

        So this is a floor on the rendered population, not a census. The
        selector-derived sweep in `test_next_page` still runs over all 107 and
        the two are complementary: that one is wide and blind to ancestors,
        this one is narrow and sees them.

        The thresholds are deliberately well under today's figures. They catch
        a render that collapsed, not one that drifted by a row.
        """
        self.assertGreater(len(self.paths), 500, f"the render collapsed: {self.per_route}")
        self.assertGreater(self._covered(), 80, "almost nothing is tier-covered")
        # How many DISTINCT tier selectors the render reaches. Without this a
        # fixture could keep its element count while rendering one surface over
        # and over, and the coverage above would not notice.
        reached = sum(
            1
            for selector in self.tiers
            if any(css_cascade.matches(path, selector) for path in self.paths)
        )
        self.assertGreater(
            reached, 25, f"the render reaches only {reached} of {len(self.tiers)} tier selectors"
        )
        # The cockpit is the half the four top-level routes do not reach, and
        # it is where the steer block lives. Measured: without it this guard
        # had nothing to say about the mutation DRC-4614 names.
        steer = [
            path
            for path in self.paths
            if any("next-steer" in cast("set[str]", n["classes"]) for n in path)
        ]
        self.assertTrue(steer, f"no cockpit steer block rendered: {self.per_route}")

    def test_every_rendered_tier_element_resolves_at_or_above_the_floor(self) -> None:
        self.assertEqual(
            self.KNOWN_BELOW_FLOOR,
            self._below_floor(self.css),
            "the set of rendered elements below the sentence floor moved",
        )

    def test_no_rendered_absence_outranks_the_value_it_replaces(self) -> None:
        """DRC-4607, asked of every slot the render produces rather than two by name.

        A value and its absence are picked by a ternary and never co-exist, so
        each branch is resolved on its own copy of the same path. That is the
        method `AnAbsenceNeverOutranksTheValueItReplacesTest` established; what
        is new here is the population, which comes from the render instead of
        from a list of pairs somebody remembered to add to.

        Measured on `58b1a81e`: nine slots, **zero inverted** -- seven resolve
        equal and two resolve with the absence smaller. DRC-4607 reports the
        recovery briefing pair as inverted at 11.5px against 12.5px; on the v3
        rem scale it is 0.8125rem against 0.8125rem and the issue is stale
        rather than wrong, its figures having been taken at `84d27a53`.

        This is a floor on the rendered population, as everything in this module
        is: a slot no fixture renders is not checked here.
        """
        tokens, rules = css_cascade.load_text(self.css)
        inverted: list[tuple[str, float, float]] = []
        slots = 0
        for path in self.paths:
            leaf = cast("set[str]", path[-1]["classes"])
            for variant in sorted(leaf):
                if not variant.endswith(("--known", "--absent")):
                    continue
                stem, _, _kind = variant.rpartition("--")
                twin_classes = (leaf - {variant}) | {
                    f"{stem}--absent" if variant.endswith("--known") else f"{stem}--known"
                }
                twin = [*path[:-1], {**path[-1], "classes": twin_classes}]
                here = css_cascade.resolve(path, tokens, rules)
                there = css_cascade.resolve(twin, tokens, rules)
                if here is None or there is None:
                    continue
                slots += 1
                known, absent = (here, there) if variant.endswith("--known") else (there, here)
                if absent > known:
                    inverted.append((_shape(path), known, absent))
        self.assertGreater(slots, 4, "no value/absence slot rendered, so nothing was compared")
        self.assertEqual([], inverted, "an absence resolves larger than the value it replaces")

    def test_the_guard_sees_a_rule_that_reaches_an_element_through_unnamed_ancestors(
        self,
    ) -> None:
        """DRC-4614 AC-1, as a mutation rather than as an assertion about a number.

        `.next-steer-caveat` renders as a `p` inside `.next-steer > header`, so
        `.next-steer>header p` at (0,1,2) outranks it at (0,1,0) -- but only on
        the real path. A path built from either selector alone carries one of
        the two and never both, which is why the selector-derived sweep in
        `test_next_page` stays green on this exact mutant.
        """
        mutant = self.css.replace(
            ".next-steer-caveat{",
            ".next-steer>header p{font-size:var(--fs-label)}\n.next-steer-caveat{",
            1,
        )
        self.assertNotEqual(self.css, mutant, "the mutant did not apply; its anchor moved")
        caught = self._below_floor(mutant) - self.KNOWN_BELOW_FLOOR
        self.assertTrue(
            any(shape.endswith("p.next-steer-caveat") for shape, _size in caught),
            f"the mutant was not caught; below-floor set was {caught}",
        )
        # And the ancestors are really what did it: the same declaration on a
        # selector that names the element directly is caught by the older guard
        # too, so catching THAT would prove nothing about this blind spot.
        self.assertNotIn(
            ".next-steer>header p",
            self.css,
            "the sheet now declares the mutant's own selector; pick another shape",
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class ControlsResolveToOneRecipeTest(NextPageJsHarness):
    """DRC-4604's other half: check what a control computes, not what it declares.

    DRC-4590's criterion read "no control rule declares its own radius or
    resting border" and its verifier grepped for exactly those two
    declarations. That passed while the primitive it established was not
    uniform in the property a reader actually sees: one of the seven rules it
    collapsed overrode the tier back down, and a check of two declarations
    cannot see a third drifting.

    So this resolves the control's SIZE through the cascade, on the paths the
    emitters render, and holds every `.next-action` to the tier the primitive
    promises. The declaration-level guards stay where they are; this is the
    half they structurally cannot cover.
    """

    paths: ClassVar[list[list[css_cascade.Node]]]
    css: ClassVar[str]
    per_route: ClassVar[dict[str, int]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        cls.paths = []
        cls.per_route = {}

    def setUp(self) -> None:
        super().setUp()
        if not type(self).paths:
            collected: list[list[css_cascade.Node]] = []
            per_route: dict[str, int] = {}
            for route in rendered_paths.FIXTURE_ROUTES:
                html = self._run_page_js(
                    rendered_paths.render_script(route),
                    prelude=storage_prelude({}, location_hash=route),
                )
                found = rendered_paths.paths_in(html)
                per_route[route] = len(found)
                collected.extend(found)
            type(self).paths, type(self).per_route = collected, per_route

    def _actions(self) -> list[list[css_cascade.Node]]:
        return [
            path for path in self.paths if "next-action" in cast("set[str]", path[-1]["classes"])
        ]

    def test_the_two_controls_that_share_the_waiting_strip_resolve_to_one_size(self) -> None:
        """DRC-4632. RAISE and COPY touch each other, so they may not disagree.

        `.next-rail-wait-controls` renders `nextSessionRaiseControl` immediately
        followed by the copy control (`next-cockpit.js:3042`,
        `next-delegation.js:209`). RAISE is exempt from the primitive on purpose:
        it carries `--amber` at rest as a state signal and keeps its own brighter
        focus ring, which DRC-4590 recorded and `test_next_chrome` pins. That
        exemption is about colour and boundary, not about type.

        So raising the copy control on its own would have relocated this issue
        rather than closed it: two adjacent controls, two tiers apart, which is
        the same defect one strip along. Only `font-size` moves on RAISE; every
        other declaration that makes it distinct stays where it is.

        Asserted on the resolved size of both paths rather than on either rule,
        because the copy control reaches its size through three rules and the
        point is what a reader sees when the two sit side by side.
        """
        tokens, rules = css_cascade.load_text(self.css)
        strip: list[css_cascade.Node] = [
            {"tag": "div", "classes": {"next-rail-wait-controls"}, "attrs": set()}
        ]
        sizes = {
            name: css_cascade.resolve(
                [*strip, {"tag": "button", "classes": classes, "attrs": {"type"}}], tokens, rules
            )
            for name, classes in (
                ("raise", {"next-session-raise", "next-attention-raise"}),
                ("copy", {"next-action", "next-session-copy"}),
            )
        }
        self.assertEqual({"raise": SENTENCE_FLOOR_REM, "copy": SENTENCE_FLOOR_REM}, sizes)

    def test_the_strip_guard_reds_when_only_one_of_the_pair_is_raised(self) -> None:
        """Mutation: the half-fix DRC-4632 was originally filed as.

        Putting `--fs-label` back on `.next-session-raise` alone is exactly the
        state the issue body proposed before the strip was noticed. It leaves
        every `.next-action` at the tier, so the guard above it stays green, and
        this one has to be what catches it.
        """
        tokens, rules = css_cascade.load_text(
            self.css + "\n.next-session-raise{font-size:var(--fs-label)}\n"
        )
        strip: list[css_cascade.Node] = [
            {"tag": "div", "classes": {"next-rail-wait-controls"}, "attrs": set()}
        ]
        sizes = [
            css_cascade.resolve(
                [*strip, {"tag": "button", "classes": classes, "attrs": {"type"}}], tokens, rules
            )
            for classes in (
                {"next-session-raise", "next-attention-raise"},
                {"next-action", "next-session-copy"},
            )
        ]
        self.assertNotEqual(sizes[0], sizes[1], "the mutant did not split the pair")

    def test_every_rendered_control_resolves_to_the_tier_the_primitive_promises(self) -> None:
        """`.next-action` declares `--fs-body`; nothing may quietly pull it back.

        Measured on the tree this landed against: the fixture renders controls
        carrying the class, and every one resolves at the sentence tier. A rule
        that overrides a control's size downward -- which is what DRC-4604
        reports of `.next-session-copy` at 11.5px, and what DRC-4590's
        two-declaration verifier could not see -- reds here.

        **It reported clean for a while and was not.** This criterion is the one
        DRC-4604 added because "the verifier must resolve what a control actually
        computes", and it resolved through a resolver that never evaluated a
        pseudo-class: `:where(#app) button:not([class])` matched every classed
        button at (0,2,1) and handed back the tier it declares rather than the
        one the control renders at. DRC-4630 fixed the resolver and the very
        control DRC-4604 named came out below the tier, on five paths that were
        one control and one declaration. DRC-4632 raised it, so this asserts the
        empty set again rather than an excused one.
        """
        tokens, rules = css_cascade.load_text(self.css)
        actions = self._actions()
        self.assertGreater(len(actions), 0, f"no control rendered: {self.per_route}")
        below = {
            _shape(path): size
            for path in actions
            if (size := css_cascade.resolve(path, tokens, rules)) is not None
            and size < SENTENCE_FLOOR_REM
        }
        self.assertEqual({}, below, "these controls resolve below the tier `.next-action` promises")

    def test_the_guard_reds_when_a_control_is_pulled_back_below_the_tier(self) -> None:
        """Mutation, because a guard over an empty set passes in silence.

        The mutant is a single class at (0,1,0), which is what a regression
        actually looks like. It used to carry an `#app` prefix, and that was a
        workaround rather than a choice: `css_cascade` parsed
        `:where(#app) button:not([class])` and then ignored the pseudo-class, so
        the phantom sat at (0,2,1) on every classed button and a single-class
        mutant lost to it. DRC-4630 removed the phantom and the prefix with it.
        """
        tokens, rules = css_cascade.load_text(
            self.css + "\n.next-action{font-size:var(--fs-label)}\n"
        )
        pulled = [
            path
            for path in self._actions()
            if (size := css_cascade.resolve(path, tokens, rules)) is not None
            and size < SENTENCE_FLOOR_REM
        ]
        self.assertTrue(pulled, "the mutant did not pull any control below the tier")
