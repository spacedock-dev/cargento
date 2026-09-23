"""Who reads a session, and what a reader is told about it before they press.

DRC-4650. A Claude Code session is read by Claude Code once its own check is
qualified; until then Codex reads it, and the page says so before the press.
Every test here is about what a person is told or what spends their capacity,
and the route is the single place both are decided.
"""

from __future__ import annotations

import itertools
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

from cargento_runtime import aggregate, observer, reading_route, sessions
from cargento_runtime import annotations as annotation_store

from .support import make_runtime

HARNESSES = ("claude", "codex", "pi", "gemini")
STATES = ("usable", "missing", "unqualified")


def _resolver(installed: set[str]) -> Any:
    asked: list[str] = []

    def which(name: str) -> str | None:
        asked.append(name)
        return f"/usr/local/bin/{name}" if name in installed else None

    which.asked = asked  # type: ignore[attr-defined]
    return which


def _world(claude: str, codex: str) -> tuple[Any, Any]:
    """Patches for one machine: each provider usable, missing, or gated."""
    installed = {
        name for name, state in (("claude", claude), ("codex", codex)) if state != "missing"
    }
    gate = mock.patch.multiple(
        annotation_store,
        CLAUDE_ABSTENTION_CHECK=(
            annotation_store.ABSTENTION_CHECK_NOT_RUN
            if claude == "unqualified"
            else annotation_store.ABSTENTION_CHECK_PASSED
        ),
        ABSTENTION_CHECK=(
            annotation_store.ABSTENTION_CHECK_NOT_RUN
            if codex == "unqualified"
            else annotation_store.ABSTENTION_CHECK_ACCEPTED
        ),
    )
    return gate, _resolver(installed)


class TheClaudeCodeCheckIsBuiltAndNotYetOffered(unittest.TestCase):
    """Owner ruling 1: its own gate, recorded not-run, and Codex's does not open it."""

    def test_the_claude_code_check_is_recorded_as_not_run(self) -> None:
        self.assertEqual(
            annotation_store.ABSTENTION_CHECK_NOT_RUN, annotation_store.CLAUDE_ABSTENTION_CHECK
        )
        self.assertFalse(annotation_store.provider_enabled("claude"))

    def test_the_accepted_codex_review_does_not_qualify_claude_code(self) -> None:
        self.assertEqual(
            annotation_store.ABSTENTION_CHECK_ACCEPTED, annotation_store.ABSTENTION_CHECK
        )
        self.assertTrue(annotation_store.provider_enabled("codex"))
        self.assertFalse(annotation_store.provider_enabled("claude"))

    def test_each_gate_opens_only_its_own_provider(self) -> None:
        for check in (
            annotation_store.ABSTENTION_CHECK_PASSED,
            annotation_store.ABSTENTION_CHECK_ACCEPTED,
        ):
            with (
                self.subTest(check=check),
                mock.patch.multiple(
                    annotation_store,
                    CLAUDE_ABSTENTION_CHECK=check,
                    ABSTENTION_CHECK=annotation_store.ABSTENTION_CHECK_NOT_RUN,
                ),
            ):
                self.assertTrue(annotation_store.provider_enabled("claude"))
                self.assertFalse(annotation_store.provider_enabled("codex"))
                self.assertFalse(annotation_store.reading_enabled())
                self.assertTrue(annotation_store.any_reading_enabled())

    def test_no_other_name_is_a_provider(self) -> None:
        for name in ("", "gemini", "pi", "Claude", "openai"):
            with self.subTest(name=name):
                self.assertFalse(annotation_store.provider_enabled(name))

    def test_reading_enabled_still_means_the_codex_check(self) -> None:
        with mock.patch.object(
            annotation_store, "ABSTENTION_CHECK", annotation_store.ABSTENTION_CHECK_NOT_RUN
        ):
            self.assertFalse(annotation_store.reading_enabled())
            self.assertFalse(annotation_store.any_reading_enabled())


class WhoReadsAClaudeCodeSessionOnThisBuild(unittest.TestCase):
    """Owner ruling 2, on the build as shipped: no gate patched."""

    def test_with_codex_installed_codex_reads_it_and_says_why_before_the_press(self) -> None:
        for installed in ({"codex"}, {"codex", "claude"}):
            with self.subTest(installed=sorted(installed)):
                route = reading_route.resolve("claude", binary_resolver=_resolver(installed))
                self.assertEqual("codex", route["provider"])
                self.assertTrue(route["fallback"])
                self.assertEqual(reading_route.REASON_FALLBACK_UNQUALIFIED, route["reason"])
                self.assertIn("Claude Code checks are built but not yet qualified", route["note"])
                self.assertIn("so Codex reads this session", route["note"])
                self.assertIn("OpenAI", route["disclosure"])
                self.assertIn("Codex capacity", route["disclosure"])
                self.assertIn("not yet qualified", route["disclosure"])
                self.assertNotIn("Anthropic", route["disclosure"])
                self.assertEqual(observer.OBSERVER_MODEL, route["model"])

    def test_the_gate_is_read_before_the_machine_is_so_claude_is_never_looked_up(self) -> None:
        which = _resolver({"claude", "codex"})
        reading_route.resolve("claude", binary_resolver=which)
        self.assertNotIn("claude", which.asked)

    def test_without_codex_not_yet_qualified_is_its_own_state_and_not_not_installed(self) -> None:
        gated = reading_route.resolve("claude", binary_resolver=_resolver({"claude"}))
        self.assertEqual("", gated["provider"])
        self.assertEqual("", gated["disclosure"])
        self.assertEqual(reading_route.REASON_UNQUALIFIED_OTHER_MISSING, gated["reason"])
        self.assertIn("Claude Code checks are built but not yet qualified", gated["note"])
        self.assertIn("Codex CLI was not found", gated["note"])
        self.assertNotIn("Claude Code CLI was not found", gated["note"])
        with mock.patch.object(
            annotation_store, "CLAUDE_ABSTENTION_CHECK", annotation_store.ABSTENTION_CHECK_PASSED
        ):
            bare = reading_route.resolve("claude", binary_resolver=_resolver(set()))
        self.assertEqual(reading_route.REASON_NOT_INSTALLED, bare["reason"])
        self.assertNotEqual(gated["note"], bare["note"])
        self.assertNotIn("qualified", bare["note"])

    def test_a_codex_session_is_read_by_codex(self) -> None:
        route = reading_route.resolve("codex", binary_resolver=_resolver({"codex", "claude"}))
        self.assertEqual(("codex", False), (route["provider"], route["fallback"]))
        self.assertEqual(reading_route.REASON_OWN_HARNESS, route["reason"])
        self.assertEqual("Codex reads this Codex session.", route["note"])

    def test_a_codex_session_without_codex_is_not_handed_to_a_gated_claude(self) -> None:
        route = reading_route.resolve("codex", binary_resolver=_resolver({"claude"}))
        self.assertEqual("", route["provider"])
        self.assertIn("Codex CLI was not found", route["note"])
        self.assertIn("Claude Code checks are built but not yet qualified", route["note"])

    def test_a_harness_with_no_producer_says_plainly_that_codex_reads_it(self) -> None:
        for harness in ("pi", "gemini", "opencode"):
            with self.subTest(harness=harness):
                route = reading_route.resolve(harness, binary_resolver=_resolver({"codex"}))
                self.assertEqual("codex", route["provider"])
                self.assertFalse(route["fallback"])
                self.assertEqual(reading_route.REASON_NO_OWN_PRODUCER, route["reason"])
                self.assertIn("no reading producer of its own", route["note"])
                self.assertIn("Codex reads this session", route["note"])

    def test_a_cli_found_only_by_a_relative_path_is_not_installed(self) -> None:
        for relative in ("codex", "./codex", "bin/codex"):
            with self.subTest(path=relative):
                route = reading_route.resolve(
                    "codex", binary_resolver=mock.Mock(return_value=relative)
                )
                self.assertEqual("", route["provider"])
                self.assertIn("Codex CLI was not found", route["note"])

    def test_resolving_a_route_never_starts_a_model(self) -> None:
        with mock.patch("subprocess.run", side_effect=AssertionError("a model started")) as run:
            for harness in HARNESSES:
                reading_route.resolve(harness, binary_resolver=_resolver({"codex", "claude"}))
        run.assert_not_called()


class WhoReadsASessionOnceClaudeCodeIsQualified(unittest.TestCase):
    """DEC-21 item 4, reached by patching the gate open: own harness first."""

    def test_a_claude_code_session_is_read_by_claude_code_and_the_page_names_anthropic(
        self,
    ) -> None:
        gate, which = _world("usable", "usable")
        with gate:
            route = reading_route.resolve("claude", binary_resolver=which)
        self.assertEqual(("claude", False), (route["provider"], route["fallback"]))
        self.assertEqual("Claude Code", route["label"])
        self.assertEqual(observer.CLAUDE_READING_MODEL, route["model"])
        self.assertIn("Anthropic", route["disclosure"])
        self.assertIn("Claude Code capacity", route["disclosure"])
        self.assertNotIn("OpenAI", route["disclosure"])
        self.assertNotIn("Codex", route["disclosure"])

    def test_a_missing_claude_code_falls_back_to_codex_and_says_it_was_missing(self) -> None:
        gate, which = _world("missing", "usable")
        with gate:
            route = reading_route.resolve("claude", binary_resolver=which)
        self.assertEqual(("codex", True), (route["provider"], route["fallback"]))
        self.assertEqual(reading_route.REASON_FALLBACK_MISSING, route["reason"])
        self.assertIn("Claude Code CLI was not found", route["note"])
        self.assertIn("OpenAI", route["disclosure"])

    def test_a_codex_session_without_codex_falls_back_to_a_qualified_claude_code(self) -> None:
        gate, which = _world("usable", "missing")
        with gate:
            route = reading_route.resolve("codex", binary_resolver=which)
        self.assertEqual(("claude", True), (route["provider"], route["fallback"]))
        self.assertIn("Codex CLI was not found", route["note"])
        self.assertIn("Anthropic", route["disclosure"])


class EveryMachineGetsExactlyOneTrueAnswer(unittest.TestCase):
    """The whole table: every harness, every install state, every gate."""

    def _all(self) -> list[tuple[str, str, str, dict[str, Any]]]:
        rows = []
        for harness, claude, codex in itertools.product(HARNESSES, STATES, STATES):
            gate, which = _world(claude, codex)
            with gate:
                rows.append(
                    (
                        harness,
                        claude,
                        codex,
                        dict(reading_route.resolve(harness, binary_resolver=which)),
                    )
                )
        return rows

    def test_own_harness_first_then_the_other_then_nothing(self) -> None:
        for harness, claude, codex, route in self._all():
            with self.subTest(harness=harness, claude=claude, codex=codex):
                state = {"claude": claude, "codex": codex}
                preferred = "claude" if harness == "claude" else "codex"
                other = "codex" if preferred == "claude" else "claude"
                if state[preferred] == "usable":
                    expected = preferred
                elif state[other] == "usable":
                    expected = other
                else:
                    expected = ""
                self.assertEqual(expected, route["provider"])
                self.assertEqual(bool(expected) and expected != preferred, route["fallback"])
                self.assertIn(route["reason"], reading_route.REASONS)
                self.assertTrue(route["note"])
                self.assertEqual(harness, route["harness"])

    def test_every_disclosure_names_its_receiver_and_never_the_other_vendor(self) -> None:
        for harness, claude, codex, route in self._all():
            with self.subTest(harness=harness, claude=claude, codex=codex):
                if not route["provider"]:
                    self.assertEqual("", route["disclosure"])
                    self.assertEqual("", route["model"])
                    continue
                vendor = reading_route.VENDORS[route["provider"]]
                elsewhere = ({"OpenAI", "Anthropic"} - {vendor}).pop()
                self.assertIn(vendor, route["disclosure"])
                self.assertNotIn(elsewhere, route["disclosure"])
                self.assertIn(f"your {route['label']} capacity", route["disclosure"])
                self.assertTrue(route["disclosure"].startswith(route["note"]))
                self.assertIn("never a verification", route["disclosure"])

    def test_no_two_states_with_no_reader_share_a_sentence(self) -> None:
        seen: dict[str, tuple[str, str, str]] = {}
        for harness, claude, codex, route in self._all():
            if route["provider"] or harness == "gemini":
                continue
            key = route["note"]
            with self.subTest(harness=harness, claude=claude, codex=codex):
                self.assertNotIn(key, seen, f"shared with {seen.get(key)}")
            seen[key] = (harness, claude, codex)
        self.assertGreaterEqual(len(seen), 8)


class ThePagePublishesARoutePerHarnessNotOneDisclosure(unittest.TestCase):
    """The page renders the route for THAT session's harness, so the payload
    carries one per harness on the board and no board-wide sentence."""

    def _collection(self, harnesses: tuple[str, ...], installed: set[str]) -> dict[str, Any]:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        config, state = make_runtime(
            state_home=home, state_dir=Path(home), annotations_enabled=True
        )

        def spec(harness: str) -> Any:
            def collect(*_args: Any) -> list[dict[str, Any]]:
                row = sessions.base_session(harness, "s1", "proj")
                row.update({"state": "working", "active": True, "last_activity": 1_700_000_000.0})
                return [row]

            return aggregate.HarnessSpec(
                key=harness, label=harness.title(), discover=lambda *_: True, collect=collect
            )

        application = aggregate.Application(
            config,
            state,
            tuple(spec(h) for h in harnesses),
            native_notifier=lambda _p: "",
            popup_notifier=lambda _t, _b: None,
            diagnostic_sink=lambda _m: None,
            clock=lambda: 1_700_000_100.0,
        )
        with mock.patch.object(shutil, "which", _resolver(installed)):
            _revision, body = application.collect_json(show_all=False)
        return dict(json.loads(body))

    def test_a_claude_row_and_a_pi_row_each_name_their_actual_receiver(self) -> None:
        data = self._collection(("claude", "pi"), {"codex", "claude"})
        self.assertNotIn("reading_disclosure", data)
        routes = data["reading_routes"]
        self.assertEqual({"claude", "pi"}, set(routes))
        self.assertEqual("codex", routes["claude"]["provider"])
        self.assertIn(
            "Claude Code checks are built but not yet qualified", routes["claude"]["disclosure"]
        )
        self.assertIn("OpenAI", routes["claude"]["disclosure"])
        self.assertIn("no reading producer of its own", routes["pi"]["disclosure"])

    def test_with_claude_code_open_the_claude_row_names_anthropic(self) -> None:
        with mock.patch.object(
            annotation_store, "CLAUDE_ABSTENTION_CHECK", annotation_store.ABSTENTION_CHECK_PASSED
        ):
            data = self._collection(("claude", "codex"), {"codex", "claude"})
        routes = data["reading_routes"]
        self.assertEqual("claude", routes["claude"]["provider"])
        self.assertIn("Anthropic", routes["claude"]["disclosure"])
        self.assertNotIn("OpenAI", routes["claude"]["disclosure"])
        self.assertEqual("codex", routes["codex"]["provider"])
        self.assertIn("OpenAI", routes["codex"]["disclosure"])

    def test_the_published_permission_says_which_providers_are_allowed(self) -> None:
        data = self._collection(("claude",), {"codex"})
        self.assertEqual({"codex": False, "claude": False}, data["reading"]["providers"])

    def test_one_collection_looks_each_cli_up_at_most_once(self) -> None:
        which = _resolver({"codex"})
        with mock.patch.object(
            annotation_store, "CLAUDE_ABSTENTION_CHECK", annotation_store.ABSTENTION_CHECK_PASSED
        ):
            reading_route.resolve_all(("claude", "codex", "pi", "gemini"), binary_resolver=which)
        self.assertEqual(sorted(set(which.asked)), sorted(which.asked))


class TheBuildGateThePageReadsIsEitherProvider(unittest.TestCase):
    """`reading_check` is the page's build-wide gate. With Codex closed and
    Claude Code qualified, a published `not-run` would refuse a route the
    server offers, so the page is told the check that opens one."""

    def test_the_published_check_is_codexs_while_codex_is_open(self) -> None:
        data = ThePagePublishesARoutePerHarnessNotOneDisclosure._collection(
            cast("Any", self), ("claude",), {"codex"}
        )
        self.assertEqual(annotation_store.ABSTENTION_CHECK, data["reading_check"])

    def test_a_qualified_claude_code_opens_the_page_when_codex_is_closed(self) -> None:
        with mock.patch.multiple(
            annotation_store,
            ABSTENTION_CHECK=annotation_store.ABSTENTION_CHECK_NOT_RUN,
            CLAUDE_ABSTENTION_CHECK=annotation_store.ABSTENTION_CHECK_PASSED,
        ):
            data = ThePagePublishesARoutePerHarnessNotOneDisclosure._collection(
                cast("Any", self), ("claude",), {"claude"}
            )
        self.assertEqual(annotation_store.ABSTENTION_CHECK_PASSED, data["reading_check"])
        self.assertEqual("claude", data["reading_routes"]["claude"]["provider"])

    def test_with_both_closed_the_page_is_told_not_run(self) -> None:
        with mock.patch.object(
            annotation_store, "ABSTENTION_CHECK", annotation_store.ABSTENTION_CHECK_NOT_RUN
        ):
            data = ThePagePublishesARoutePerHarnessNotOneDisclosure._collection(
                cast("Any", self), ("claude",), {"claude", "codex"}
            )
        self.assertEqual(annotation_store.ABSTENTION_CHECK_NOT_RUN, data["reading_check"])


class TheSentencesReadAsSentences(unittest.TestCase):
    def test_no_reason_chains_three_clauses_with_and(self) -> None:
        for harness, claude, codex in itertools.product(HARNESSES, STATES, STATES):
            gate, which = _world(claude, codex)
            with gate:
                note = reading_route.resolve(harness, binary_resolver=which)["note"]
            with self.subTest(harness=harness, claude=claude, codex=codex):
                self.assertLessEqual(note.count(", and "), 1, note)


if __name__ == "__main__":
    unittest.main()
