"""A listed direction is reachable without moving an unchanged goal's window."""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import http.client
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from cargento_runtime import aggregate, http_api, project_context, records
from cargento_runtime import annotations as annotation_store
from cargento_runtime import io as runtime_io

from . import test_correction as correction_tests
from . import test_next_analysis_result as result_tests
from .support import make_runtime, make_server, serve_until_closed
from .test_claude_checks import SHORT
from .test_direction_adoption import FIRST_AT, LONG, NOW, _ClaudeSession, _row
from .test_next_intent_draft import TYPED, _DraftPage, visible_text


class AnUnchangedGoalKeepsItsWindow(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.config, self.state = make_runtime(state_home=home.name, state_dir=Path(home.name))
        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s1",
            goal="Ship retry",
            lines=["Pass checks"],
            now=1000.0,
            window_start=100.0,
        )

    def saved(self) -> Any:
        entry = annotation_store.find(annotation_store.load(self.config), "claude", "s1")
        assert entry is not None
        return entry["revisions"][-1]

    def test_a_lines_only_save_keeps_the_window(self) -> None:
        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s1",
            lines=["Pass all checks"],
            now=2000.0,
            window_start=1900.0,
            expected_revision=1,
        )
        self.assertEqual(100.0, self.saved()["window_start"])

    def test_repeating_the_goal_with_new_lines_keeps_the_window(self) -> None:
        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s1",
            goal="Ship retry",
            lines=["Pass all checks"],
            now=2000.0,
            window_start=1900.0,
            expected_revision=1,
        )
        self.assertEqual(100.0, self.saved()["window_start"])

    def test_add_keeps_the_same_typed_goals_window(self) -> None:
        outcome = annotation_store.add_direction(
            self.config,
            self.state,
            {"harness": "claude", "sid": "s1"},
            source_id="fact:0123456789abcdef",
            text="Every retry is bounded",
            entry_at=1500.0,
            expected_revision=1,
            now=2000.0,
            window_start=1900.0,
        )
        self.assertEqual("stored", outcome)
        self.assertEqual(100.0, self.saved()["window_start"])

    def test_new_goal_words_move_the_window(self) -> None:
        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s1",
            goal="Ship parser",
            now=2000.0,
            window_start=1900.0,
            expected_revision=1,
        )
        self.assertEqual(1900.0, self.saved()["window_start"])

    def test_clock_step_back_clamps_the_carried_window(self) -> None:
        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s1",
            lines=["Pass all checks"],
            now=90.0,
            window_start=80.0,
            expected_revision=1,
        )
        self.assertEqual(90.0, self.saved()["window_start"])


class AListedDirectionReachesItsSource(_ClaudeSession):
    def test_a_source_disappearing_or_becoming_unreadable_is_refused(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        for failure in (FileNotFoundError, PermissionError):
            with (
                self.subTest(failure=failure.__name__),
                mock.patch.object(runtime_io, "read_prefix_bytes", side_effect=failure),
            ):
                self.assertEqual(
                    "",
                    project_context.direction_text(
                        self.config, self.state, "claude", SHORT, fact_id
                    ).text,
                )

    def test_a_direction_outside_the_tail_can_be_opened_whole(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        for _ in range(40):
            self.session.bash("pytest", "p" * 200)
        self.session.save(self.path)
        narrow = dataclasses.replace(self.config, tail_bytes=4096)
        self.assertEqual(
            LONG, project_context.direction_text(narrow, self.state, "claude", SHORT, fact_id).text
        )

    def test_the_goal_menu_resolves_a_history_message_without_words(self) -> None:
        fact = self.direction()
        fact.pop("reader_words", None)
        app = SimpleNamespace(config=self.config, state=self.state)
        context = {"semantic": {"facts": [fact]}}
        got = http_api._with_prompt_choices(
            app,
            context,
            [{"harness": "claude", "sid": SHORT, "project": "billing"}],
            ("claude", SHORT),
            "billing",
        )
        self.assertEqual(fact["fact_id"], got["prompt_choices"][0]["fact_id"])
        self.assertEqual(fact["at"], got["prompt_choices"][0]["at"])
        self.assertTrue(got["prompt_choices"][0]["text"].startswith("Use the placeholder lexer"))

    def test_a_child_identity_is_never_offered_as_the_parent_prompt(self) -> None:
        fact = self.direction()
        fact["source_session"] = {"harness": "claude", "sid": "other"}
        app = SimpleNamespace(config=self.config, state=self.state)
        got = http_api._with_prompt_choices(
            app,
            {"semantic": {"facts": [fact]}},
            [{"harness": "claude", "sid": SHORT, "project": "billing"}],
            ("claude", SHORT),
            "billing",
        )
        self.assertEqual([], got["prompt_choices"])

    def test_a_direction_beyond_the_source_budget_is_refused(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        with mock.patch.object(project_context, "SEMANTIC_BACKFILL_MAX_BYTES", 16):
            self.assertEqual(
                "",
                project_context.direction_text(
                    self.config, self.state, "claude", SHORT, fact_id
                ).text,
            )

    def test_a_file_changed_while_opening_a_direction_is_refused(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        original = runtime_io.read_prefix_bytes

        def moving(*args: Any, **kwargs: Any) -> bytes:
            value = original(*args, **kwargs)
            with self.path.open("a") as handle:
                handle.write("\n")
            return value

        with mock.patch.object(runtime_io, "read_prefix_bytes", moving):
            self.assertEqual(
                "",
                project_context.direction_text(
                    self.config, self.state, "claude", SHORT, fact_id
                ).text,
            )

    def test_ambiguous_raw_words_under_one_fact_id_are_refused(self) -> None:
        fact_id = str(self.direction()["fact_id"])
        altered = copy.deepcopy(self.session.rows[-1])
        altered["message"]["content"][0]["text"] = LONG + " Another ending."
        self.session.rows.append(altered)
        self.session.save(self.path)
        self.assertEqual(
            "",
            project_context.direction_text(self.config, self.state, "claude", SHORT, fact_id).text,
        )

    def test_a_menu_refuses_ambiguous_raw_words_before_they_are_folded(self) -> None:
        fact = self.direction()
        altered = copy.deepcopy(self.session.rows[-1])
        altered["message"]["content"][0]["text"] = LONG.replace("Use the", "Use   the", 1)
        self.session.rows.append(altered)
        self.session.save(self.path)
        app = SimpleNamespace(config=self.config, state=self.state)
        choices = http_api._prompt_facts(app, _row(), [fact])
        self.assertEqual([], annotation_store.prompt_choices(_row(), choices, 240))

    def test_goal_menu_masking_does_not_change_or_poison_analyze_words(self) -> None:
        self.session.prompt("Keep retry. AKIAIOSFODNN7\nEXAMPLE")
        self.session.save(self.path)
        before = project_context.transcript_user_facts(
            self.config, self.state, str(self.path), "claude", SHORT
        )
        menu = project_context.transcript_user_facts(
            self.config, self.state, str(self.path), "claude", SHORT, goal_choices=True
        )
        after = project_context.transcript_user_facts(
            self.config, self.state, str(self.path), "claude", SHORT
        )
        self.assertEqual(before, after)
        self.assertNotEqual(before[-1]["reader_words"], menu[-1]["reader_words"])
        self.assertNotIn(records.GOAL_SOURCE_CUT_FIELD, before[-1])
        self.assertNotIn(records.GOAL_SOURCE_CUT_FIELD, project_context.for_page(menu[-1]))

    def test_missing_raw_source_never_offers_folded_words_as_a_goal(self) -> None:
        self.session.prompt("Keep retry. AKIAIOSFODNN7\nEXAMPLE")
        self.session.save(self.path)
        fact = max(
            (item for item in self.facts() if item["type"] == "user_message"),
            key=lambda item: item["at"],
        )
        app = SimpleNamespace(config=self.config, state=self.state)
        with mock.patch.object(runtime_io, "read_prefix_bytes", side_effect=PermissionError):
            restored = http_api._prompt_facts(app, _row(), [fact])
            self.assertEqual([], annotation_store.prompt_choices(_row(), restored, 240))

    def test_a_command_cut_before_folding_stays_an_excerpt_in_every_choice(self) -> None:
        self.session.prompt(
            "<command-message>review</command-message>\n<command-name>/review</command-name>\n"
            "<command-args>Keep retry." + " " * 2100 + "later omitted</command-args>"
        )
        self.session.save(self.path)
        fact = max(
            (item for item in self.facts() if item["type"] == "user_message"),
            key=lambda item: item["at"],
        )
        app = SimpleNamespace(config=self.config, state=self.state)
        choices = annotation_store.prompt_choices(
            _row(), http_api._prompt_facts(app, _row(), [fact]), 240
        )
        raw = project_context.direction_text(
            self.config, self.state, "claude", SHORT, str(fact["fact_id"])
        )
        self.assertTrue(raw.cut)
        explicit = annotation_store.prompt_choice(
            str(fact["fact_id"]), float(fact["at"]), raw.text, 240, cut=raw.cut
        )
        self.assertEqual([explicit], choices)

    def test_an_ambiguity_after_the_fact_cap_still_refuses_an_earlier_choice(self) -> None:
        words = "Keep   retries bounded.\nUse the original boundary."
        self.session.prompt(words)
        self.session.save(self.path)
        fact = max(
            (item for item in self.facts() if item["type"] == "user_message"),
            key=lambda item: item["at"],
        )
        duplicate = copy.deepcopy(self.session.rows[-1])
        duplicate["message"]["content"][0]["text"] = words.replace("   ", " ").replace(
            "original boundary", "changed boundary"
        )
        for k in range(project_context.TRANSCRIPT_USER_FACTS_MAX):
            self.session.prompt(f"Use fixture {k} to check the boundary.")
        self.session.rows.append(duplicate)
        self.session.save(self.path)
        self.assertLess(self.path.stat().st_size, project_context.SEMANTIC_BACKFILL_MAX_BYTES)
        source = project_context.transcript_user_facts(
            self.config, self.state, str(self.path), "claude", SHORT, goal_choices=True
        )
        self.assertEqual(project_context.TRANSCRIPT_USER_FACTS_MAX, len(source))
        app = SimpleNamespace(config=self.config, state=self.state)
        choices = annotation_store.prompt_choices(
            _row(), http_api._prompt_facts(app, _row(), [fact]), 240
        )
        self.assertEqual([], choices)


class AReadingKeepsTheBaselineItRead(unittest.TestCase):
    def test_a_message_after_the_read_does_not_erase_a_departure(self) -> None:
        row = correction_tests.session_row(
            annotation_assessment=correction_tests.reading(
                goal=correction_tests.row_of(correction_tests.DEPARTED, ("write",))
            )
        )
        row["annotation_assessment"]["read_at"] = 120.0
        facts = (
            correction_tests.fact("write", 110, "agent_message"),
            correction_tests.fact("later", 130, "user_message"),
        )
        got = correction_tests.compose(row, facts)
        self.assertTrue(got["ok"], got)

    def test_a_message_before_the_read_still_demotes_the_departure(self) -> None:
        row = correction_tests.session_row(
            annotation_assessment=correction_tests.reading(
                goal=correction_tests.row_of(correction_tests.DEPARTED, ("write",))
            )
        )
        row["annotation_assessment"]["read_at"] = 120.0
        facts = (
            correction_tests.fact("write", 110, "agent_message"),
            correction_tests.fact("later", 115, "user_message"),
        )
        self.assertFalse(correction_tests.compose(row, facts)["ok"])

    def test_the_http_level_uses_the_read_time_for_later_directions(self) -> None:
        person = correction_tests.fact("new-person", 107, "user_message")
        person["source_session"] = {"harness": "claude", "sid": "focus-1"}
        facts = [*result_tests.NO_FAILURE, person]
        value = result_tests.assessment(
            {
                "goal": result_tests.criterion(result_tests.DEPARTS, "task-a"),
                "line_1": result_tests.criterion(result_tests.CONSISTENT, "c-pass"),
            },
            read_at=103,
        )
        entry: Any = {
            "assessment": value,
            "revisions": [{"n": 2, "lines": [{"text": "Pass checks", "source": "typed"}]}],
        }
        row = {
            "harness": "claude",
            "sid": "focus-1",
            "annotation_goal": "Ship retry",
            "annotation_goal_saved_at": 103,
        }
        context = {
            "semantic": {"facts": facts},
            "sources": {"work": {"tool_reports": [result_tests.scan_for(result_tests.NO_FAILURE)]}},
        }
        app = SimpleNamespace(clock=lambda: 150)
        got = http_api._analysis_levels(app, context, row, entry, 103)[0]["level"]
        expected = result_tests.server_level(value, result_tests.NO_FAILURE)
        self.assertEqual(expected, got)


class ThePageKeepsTheReadTime(result_tests._ResultPage):
    def test_after_read_direction_labels_staleness_without_erasing_departure(self) -> None:
        value = result_tests.assessment(
            result_tests.MIXED["criteria"], read_at=103, evidence_through=103
        )
        html = self.page(value, extra="__s.annotation_goal_saved_at = 103;")
        self.assertIn("Departs", " ".join(result_tests.rows_of(html)))
        self.assertIn("Read before your message", visible_text(html))

    def test_before_read_direction_still_withdraws_intent_departure(self) -> None:
        html = self.page(result_tests.MIXED, extra="__s.annotation_goal_saved_at = 103;")
        self.assertNotIn("Departs", " ".join(result_tests.rows_of(html)))


class TheQuestionLetsTheReaderChoose(_DraftPage):
    def test_add_selects_the_newest_and_offers_explicit_goal_adoption(self) -> None:
        html = self.html()
        self.assertIn("data-next-direction-select", html)
        self.assertIn('value="fo-a" selected', html)
        self.assertIn("Use this as my goal", visible_text(html))

    def test_the_line_box_asks_for_the_rule(self) -> None:
        html = self.html(
            'nextCockpitDirectionLines.set("claude:focus-1",{factId:"fo-a",text:"Keep checks",later:true});'
        )
        self.assertIn("Write the rule, not the moment", visible_text(html))

    def test_a_partial_visibility_cannot_claim_all_work_finished(self) -> None:
        got = self.drive(
            after='console.log(JSON.stringify(nextDelegatedWork({delegated_launches:2,delegated_unpaired:0,delegated_visibility:"partial",delegated_latest_launch_at:100,delegated_last_activity_at:110,delegated_quiet_since:null})));'
        )
        self.assertIn("cannot see", got["text"].lower())
        self.assertNotIn("finished", got["text"].lower())

    def test_a_measured_quiet_launch_is_risky_at_thirty_minutes(self) -> None:
        got = self.drive(
            after='console.log(JSON.stringify(nextDelegatedWork({delegated_launches:1,delegated_unpaired:1,delegated_visibility:"recorded",delegated_latest_launch_at:100,delegated_last_activity_at:110,delegated_quiet_since:110},1910)));'
        )
        self.assertTrue(got["risky"])
        self.assertIn("30", got["text"])

    def test_unknown_launches_are_not_measured_zero(self) -> None:
        got = self.drive(
            after='console.log(JSON.stringify(nextDelegatedWork({delegated_launches:null,delegated_unpaired:null,delegated_visibility:"not-recorded"},1910)));'
        )
        self.assertFalse(got["risky"])
        self.assertIn("not measured", got["text"].lower())


class TheServerVerifiesAnExplicitDirection(_ClaudeSession):
    def test_a_goal_choice_uses_the_same_safe_words_inside_and_outside_the_menu(self) -> None:
        samples = (
            "Keep   retry bounded.",
            "Keep retry. -pPLACEHOLDERpw9",
            "Keep retry. 'deploy:PLACEHOLDERpw9 two@db.example'",
            "Keep retry. AKIAIOSFODNN7\nEXAMPLE",
        )
        for words in samples:
            for newer in (0, 8):
                with self.subTest(words=words, newer=newer):
                    self.session.prompt(words)
                    self.session.save(self.path)
                    selected = max(
                        (fact for fact in self.facts() if fact["type"] == "user_message"),
                        key=lambda fact: fact["at"],
                    )
                    for k in range(newer):
                        self.session.prompt(f"Use fixture variant {k} after {selected['at']}.")
                    self.session.save(self.path)
                    entry = annotation_store.find(
                        annotation_store.load(self.config), "claude", SHORT
                    )
                    revision = entry["revisions"][-1]["n"] if entry else 0
                    with self.serving() as port:
                        opened = self.request(
                            port,
                            "/api/direction",
                            {"harness": "claude", "sid": SHORT, "fact_id": selected["fact_id"]},
                        )
                        choice = opened["goal_choice"]
                        expected = annotation_store.direction_review(
                            words, self.config.annotation_text_cap_chars
                        )[0]
                        self.assertEqual(expected, choice["text"])
                        menu = self.request(
                            port,
                            f"/api/project-context?project=billing&session=claude:{SHORT}&prompts=1",
                        )
                        for offered in menu["prompt_choices"]:
                            if offered["fact_id"] == selected["fact_id"]:
                                self.assertEqual(expected, offered["text"])
                        answer = self.request(
                            port,
                            "/api/annotate",
                            {
                                "harness": "claude",
                                "sid": SHORT,
                                "adopt": "chosen-prompt",
                                "prompt_fact": choice["fact_id"],
                                "expected_prompt": choice["text"],
                                "expected_prompt_at": choice["at"],
                                "expected_revision": revision,
                            },
                        )
                    self.assertEqual("stored", answer["outcome"])
                    saved = annotation_store.load(self.config)[0]["revisions"][-1]
                    self.assertEqual(expected, saved["goal"])

    @contextlib.contextmanager
    def serving(self) -> Any:
        spec = aggregate.HarnessSpec(
            key="claude",
            label="Claude",
            discover=lambda *_: True,
            collect=lambda *_a, **_k: [_row()],
        )
        app = aggregate.Application(
            self.config,
            self.state,
            (spec,),
            clock=lambda: NOW,
            diagnostic_sink=lambda _m: None,
            native_notifier=lambda _p: "",
            popup_notifier=lambda _t, _b: None,
        )
        server = make_server(application=app)
        thread = serve_until_closed(server)
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join(timeout=5)

    @staticmethod
    def request(port: int, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request(
                "POST" if body is not None else "GET",
                path,
                body=json.dumps(body).encode() if body is not None else None,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            assert response.status == 200
            parsed = json.loads(response.read())
            assert isinstance(parsed, dict)
            return parsed
        finally:
            connection.close()

    def test_an_explicit_listed_direction_outside_the_five_can_be_adopted(self) -> None:
        old = self.direction()
        for k in range(8):
            self.session.prompt(f"Use retry limit {k} for fixture {k}.")
        self.session.save(self.path)
        annotation_store.annotate(
            self.config, self.state, "claude", SHORT, goal="Ship retry", now=FIRST_AT + 1
        )
        with self.serving() as port:
            menu = self.request(
                port, f"/api/project-context?project=billing&session=claude:{SHORT}&prompts=1"
            )
            self.assertNotIn(old["fact_id"], [r["fact_id"] for r in menu["prompt_choices"]])
            opened = self.request(
                port,
                "/api/direction",
                {"harness": "claude", "sid": SHORT, "fact_id": old["fact_id"]},
            )
            choice = opened["goal_choice"]
            answer = self.request(
                port,
                "/api/annotate",
                {
                    "harness": "claude",
                    "sid": SHORT,
                    "adopt": "chosen-prompt",
                    "prompt_fact": choice["fact_id"],
                    "expected_prompt": choice["text"],
                    "expected_prompt_at": choice["at"],
                    "expected_revision": 1,
                },
            )
        self.assertEqual("stored", answer["outcome"])
        saved = annotation_store.load(self.config)[0]["revisions"][-1]
        self.assertEqual(choice["text"], saved["goal"])
        self.assertEqual(choice["at"], saved["window_start"])

    def test_unknown_fact_and_changed_expectation_adopt_nothing(self) -> None:
        old = self.direction()
        annotation_store.annotate(
            self.config, self.state, "claude", SHORT, goal="Ship retry", now=FIRST_AT + 1
        )
        with self.serving() as port:
            for fact_id, words in (("fact:unknown", LONG), (old["fact_id"], "Changed expectation")):
                answer = self.request(
                    port,
                    "/api/annotate",
                    {
                        "harness": "claude",
                        "sid": SHORT,
                        "adopt": "chosen-prompt",
                        "prompt_fact": fact_id,
                        "expected_prompt": words,
                        "expected_prompt_at": old["at"],
                        "expected_revision": 1,
                    },
                )
                self.assertEqual("refused", answer["outcome"])
        self.assertEqual(1, len(annotation_store.load(self.config)[0]["revisions"]))

    def test_polled_context_has_no_prompt_choices_until_the_menu_opens(self) -> None:
        with self.serving() as port:
            poll = self.request(
                port, f"/api/project-context?project=billing&session=claude:{SHORT}"
            )
            menu = self.request(
                port, f"/api/project-context?project=billing&session=claude:{SHORT}&prompts=1"
            )
        self.assertNotIn("prompt_choices", poll)
        self.assertGreater(len(menu["prompt_choices"]), 0)


class ChoosingADirectionDoesNotSaveIt(_DraftPage):
    def test_a_closed_pending_native_menu_is_not_reopened_by_its_reply(self) -> None:
        for close in (
            '__fire("focusout",{relatedTarget:null,target});',
            '__fire("keydown",{type:"keydown",key:"Escape",target,preventDefault(){}});',
        ):
            with self.subTest(close=close):
                got = self.drive(
                    after="""
let finish; let picker = 0;
__fetchImpl = async () => await new Promise(resolve => {finish = () => resolve({ok:true,json:async()=>({prompt_choices:[{fact_id:"menu",at:104,text:"Choose retry",cut:false}]})});});
const select = {tagName:"SELECT",dataset:{},isConnected:true,focus(){},showPicker(){picker++;},closest(selector){return selector === "[data-next-cockpit-prompt-select]" ? this : null;}};
const target = select;
nextIntentPromptMenuOpen({type:"pointerdown",target,preventDefault(){}});
await __settle();
"""
                    + close
                    + """
finish(); await __settle(); await __settle();
console.log(JSON.stringify({picker,menu:nextIntentPromptLists.get("claude:focus-1")}));
""",
                )
                self.assertFalse(got["menu"]["open"])
                self.assertEqual(0, got["picker"])

    def test_one_unpaired_launch_uses_singular_grammar(self) -> None:
        got = self.drive(
            after='console.log(JSON.stringify(nextDelegatedWork({delegated_launches:1,delegated_unpaired:1,delegated_visibility:"recorded"},1910)));'
        )
        self.assertIn("1 of this session's launches has no recorded completion", got["text"])

    def test_a_goal_typed_while_the_direction_opens_survives_the_reply(self) -> None:
        got = self.drive(
            self.CHOICE,
            """
const oldFetch = __fetchImpl; let finish;
__fetchImpl = async (url, init) => String(url) === "/api/direction" ? await new Promise(resolve => {
  finish = () => resolve({ok:true,json:async()=>({ok:true,goal_choice:{fact_id:"fo-a",at:104,text:"New retry goal",cut:false}})});
}) : oldFetch(url, init);
__press("direction-goal","fo-a"); await __settle();
__typeGoal("Typed while opening"); finish(); await __settle(); await __settle();
console.log(JSON.stringify({draft:nextCockpitHeldDrafts.get("held:claude:focus-1:goal"),chosen:nextIntentChosenPrompts.has("held:claude:focus-1:goal"),html:__els.app.innerHTML}));
""",
        )
        self.assertEqual("Typed while opening", got.get("draft"))
        self.assertFalse(got["chosen"])
        self.assertIn("Typed while opening", got["html"])

    def test_new_lines_or_a_saved_revision_refuse_a_pending_goal_choice(self) -> None:
        for change in (
            'nextCockpitHeldDrafts.set("held:claude:focus-1:lines",["New outcome line"]);',
            "__s.annotation_revision = 99;",
        ):
            with self.subTest(change=change):
                got = self.drive(
                    self.CHOICE,
                    """
let finish;
__fetchImpl = async () => await new Promise(resolve => {finish = () => resolve({ok:true,json:async()=>({ok:true,goal_choice:{fact_id:"fo-a",at:104,text:"New retry goal",cut:false}})});});
__press("direction-goal","fo-a"); await __settle();
"""
                    + change
                    + """
finish(); await __settle(); await __settle();
console.log(JSON.stringify({chosen:nextIntentChosenPrompts.has("held:claude:focus-1:goal"),lines:nextCockpitHeldDrafts.get("held:claude:focus-1:lines")}));
""",
                )
                self.assertFalse(got["chosen"])
                if "New outcome" in change:
                    self.assertEqual(["New outcome line"], got["lines"])

    def test_a_closed_menu_refreshes_on_null_blur_choice_and_escape(self) -> None:
        got = self.drive(
            after="""
let requests = 0;
__fetchImpl = async () => ({ok:true,json:async()=>({prompt_choices:[{fact_id:"menu-"+(++requests),at:104+requests,text:"Choice "+requests,cut:false}]})});
const select = {tagName:"SELECT",dataset:{},value:"menu-2",closest(selector){return selector === "[data-next-cockpit-prompt-select]" ? this : null;}};
await nextIntentLoadPromptChoices(__s);
__fire("focusout",{relatedTarget:null,target:select});
await nextIntentLoadPromptChoices(__s);
__fire("change",{target:select});
await nextIntentLoadPromptChoices(__s);
__fire("keydown",{type:"keydown",key:"Escape",target:select,preventDefault(){}});
await nextIntentLoadPromptChoices(__s);
console.log(JSON.stringify({requests,choices:nextIntentPromptChoices(__s)}));
"""
        )
        self.assertEqual(4, got["requests"])
        self.assertEqual("menu-4", got["choices"][0]["factId"])

    def test_closing_a_pending_menu_stays_closed_when_its_reply_arrives(self) -> None:
        got = self.drive(
            after="""
let finish; let requests = 0;
__fetchImpl = async () => {requests++; return await new Promise(resolve => {finish = () => resolve({ok:true,json:async()=>({prompt_choices:[{fact_id:"menu",at:104,text:"Choose retry",cut:false}]})});});};
const first = nextIntentLoadPromptChoices(__s);
await nextIntentLoadPromptChoices(__s);
__fire("focusout",{relatedTarget:null,target:{closest:()=>({})}});
finish(); await first;
console.log(JSON.stringify({requests,menu:nextIntentPromptLists.get("claude:focus-1")}));
"""
        )
        self.assertEqual(1, got["requests"])
        self.assertFalse(got["menu"]["open"])

    CHOICE = (
        TYPED
        + """
__s.annotation_line_1 = "Every retry is bounded";
__reply["/api/direction"] = () => ({status:200,body:{ok:true,text:"New retry goal",fits:true,clipped:false,
  goal_choice:{fact_id:"fo-a",at:104,text:"New retry goal",cut:false}}});
"""
    )

    def test_choose_only_opens_the_draft_and_asks_about_standing_lines(self) -> None:
        got = self.drive(
            self.CHOICE,
            '__press("direction-goal","fo-a");await __settle();await __settle();console.log(JSON.stringify({html:__els.app.innerHTML,posts:__posts}));',
        )
        self.assertEqual(["/api/direction"], [r["url"] for r in got["posts"]])
        self.assertIn("Keep your standing outcome lines", visible_text(got["html"]))
        self.assertIn("New retry goal", got["html"])

    def test_save_waits_for_the_keep_or_clear_answer(self) -> None:
        got = self.drive(
            self.CHOICE,
            '__press("direction-goal","fo-a");await __settle();__press("held-save","intent");await __settle();console.log(JSON.stringify(__posts));',
        )
        self.assertEqual(["/api/direction"], [r["url"] for r in got])

    def test_a_goal_choice_cannot_replace_an_unsaved_edit(self) -> None:
        got = self.drive(
            self.CHOICE,
            '__typeGoal("My edit");__press("direction-goal","fo-a");await __settle();console.log(JSON.stringify({html:__els.app.innerHTML,posts:__posts}));',
        )
        self.assertEqual([], got["posts"])
        self.assertIn("My edit", got["html"])

    def test_the_same_words_from_a_new_source_still_wait_for_adoption(self) -> None:
        got = self.drive(
            self.CHOICE
            + '__reply["/api/direction"] = () => ({status:200,body:{ok:true,goal_choice:{fact_id:"fo-a",at:104,text:__s.annotation_goal,cut:false}}});',
            '__press("direction-goal","fo-a");await __settle();console.log(JSON.stringify(nextIntentDraft(__s,nextCockpitAnnotation(__s))));',
        )
        self.assertEqual(104, got["at"])
        self.assertEqual("fo-a", got["factId"])

    def test_any_earlier_choice_changes_the_add_target(self) -> None:
        html = self.html('nextDirectionPicks.set("claude:focus-1","fo-b");')
        self.assertIn('data-next-cockpit-action="direction-add" data-arg="fo-b"', html)
        self.assertIn('value="fo-b" selected', html)

    def test_the_attention_model_counts_one_quiet_launch_without_drift(self) -> None:
        got = self.drive(
            after='console.log(JSON.stringify(nextAttentionModel({generated:1910,sessions:[{harness:"claude",sid:"s",project:"p",state:"idle",delegated_launches:1,delegated_unpaired:1,delegated_visibility:"unattributed",delegated_latest_launch_at:100,delegated_last_activity_at:110,delegated_quiet_since:110}]})));'
        )
        self.assertEqual(1, got["counts"]["risk"])
        self.assertEqual("quiet-launch", got["risk"][0]["primaryKind"])
        self.assertNotIn("drift", got["risk"][0]["signals"][0]["detail"]["text"].lower())

    def test_no_delegated_line_is_drawn_without_a_recorded_launch(self) -> None:
        self.assertNotIn("data-next-delegated-work", self.html())
        measured_zero = self.html(
            'Object.assign(__s,{delegated_launches:0,delegated_unpaired:0,delegated_visibility:"recorded"});'
        )
        self.assertNotIn("data-next-delegated-work", measured_zero)

    def test_a_recorded_launch_draws_the_count_and_its_visibility(self) -> None:
        html = self.html(
            'Object.assign(__s,{delegated_launches:2,delegated_unpaired:1,delegated_visibility:"unattributed",delegated_latest_launch_at:100,delegated_last_activity_at:105,delegated_quiet_since:null});'
        )
        self.assertIn("data-next-delegated-work", html)
        self.assertIn("2 recorded launches", visible_text(html))
        self.assertIn("cannot see all work", visible_text(html))

    def test_the_prompt_menu_fetches_once_per_open_without_a_save(self) -> None:
        got = self.drive(
            after="""
const oldFetch = __fetchImpl; let requests = [];
__fetchImpl = async (url, init) => {
  requests.push(String(url));
  if(String(url).includes("prompts=1")) return {ok:true,json:async()=>({prompt_choices:[{fact_id:"menu-1",at:104,text:"Choose retry goal",cut:false}]})};
  return oldFetch(url,init);
};
await nextIntentLoadPromptChoices(__s);
await nextIntentLoadPromptChoices(__s);
console.log(JSON.stringify({requests,posts:__posts,choices:nextIntentPromptChoices(__s)}));
"""
        )
        self.assertEqual(1, sum("prompts=1" in r for r in got["requests"]))
        self.assertEqual([], got["posts"])
        self.assertEqual("menu-1", got["choices"][0]["factId"])

    def test_quiet_time_needs_thirty_minutes_and_a_valid_recorded_clock(self) -> None:
        got = self.drive(
            after="""
const base = {delegated_launches:1,delegated_unpaired:1,delegated_visibility:"recorded",delegated_latest_launch_at:100,delegated_last_activity_at:110};
console.log(JSON.stringify([1799,1800,-1,null].map(age => nextDelegatedWork({...base,delegated_quiet_since:age == null ? null : 1910-age},1910).risky)));
"""
        )
        self.assertEqual([False, True, False, False], got)

    def test_loading_choices_keeps_the_open_native_select_in_place(self) -> None:
        got = self.drive(
            after="""
const select = {dataset:{nextFocus:"held:claude:focus-1:goal:prompt"},innerHTML:""};
const originalQuery = __els.app.querySelectorAll ? __els.app.querySelectorAll.bind(__els.app) : () => [];
__els.app.querySelectorAll = selector => selector === "[data-next-cockpit-prompt-select]" ? [select] : originalQuery(selector);
__fetchImpl = async () => ({ok:true,json:async()=>({prompt_choices:[{fact_id:"new-menu",at:104,text:"Choose retry goal",cut:false}]})});
const before = __els.app.innerHTML;
await nextIntentLoadPromptChoices(__s);
console.log(JSON.stringify({same:before === __els.app.innerHTML,options:select.innerHTML}));
"""
        )
        self.assertTrue(got["same"])
        self.assertIn("new-menu", got["options"])

    def test_a_saved_direction_goal_replaces_the_not_saved_announcement(self) -> None:
        got = self.drive(
            self.CHOICE,
            """
const said = []; const originalAnnounce = nextCockpitAnnounceCue;
__reply["/api/annotate"] = () => {Object.assign(__s,{annotation_goal:"New retry goal",annotation_goal_source:"chosen-prompt",annotation_goal_source_at:104,annotation_revision:3});return {status:200,body:{ok:true,persisted:true,outcome:"stored"}};};
nextCockpitAnnounceCue = (key,message,assertive) => {said.push(message);return originalAnnounce(key,message,assertive);};
__press("direction-goal","fo-a");await __settle();await __settle();
__press("direction-lines-keep");__press("held-save","intent");await __settle();await __settle();
console.log(JSON.stringify({said,posts:__posts}));
""",
        )
        self.assertEqual("/api/annotate", got["posts"][-1]["url"])
        self.assertEqual("Saved as a new revision.", [s for s in got["said"] if s][-1])

    def test_keyboard_open_focuses_before_loading_and_opens_the_picker(self) -> None:
        got = self.drive(
            after="""
const events = [];
const select = {isConnected:true,focus(){events.push("focus");},showPicker(){events.push("picker");}};
nextIntentLoadPromptChoices = async () => {events.push("load");nextIntentPromptLists.set("claude:focus-1",{open:true});};
nextIntentPromptMenuOpen({type:"keydown",key:"ArrowDown",preventDefault(){events.push("prevent");},target:{closest:()=>select}});
await __settle();
console.log(JSON.stringify(events));
"""
        )
        self.assertEqual(["prevent", "focus", "load", "picker"], got)
