"""The annotation store: what the reader typed a session should achieve.

DRC-4508. These tests are the acceptance criteria the issue can actually hold
this store to. The two it cannot are named in the module docstring of
`annotations` and in the pull request, not silently skipped here.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import aggregate, cli, project_context
from cargento_runtime import annotations as annotation_store
from cargento_runtime import observer as runtime_observer
from cargento_runtime.config import RuntimeConfig, build_runtime_config
from cargento_runtime.state import build_runtime_state

from .support import make_runtime


class AnnotationStoreTest(unittest.TestCase):
    NOW = 1_800_000_000.0

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.harness_store = self.root / "harness-own-store"
        self.harness_store.mkdir()
        self.config = self._config()
        self.state = build_runtime_state(self.config, started=self.NOW)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _config(self, **overrides: Any) -> RuntimeConfig:
        return build_runtime_config(
            environ={"HOME": str(self.root), "CARGENTO_HOME": str(self.root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
            store_root_overrides={"pi.sessions": str(self.harness_store)},
            **overrides,
        )

    # --- what the reader typed comes back ---------------------------------

    def test_an_annotation_survives_a_restart_and_writes_only_to_our_own_store(self) -> None:
        """Given a typed goal, when the process restarts, it is still there.

        The write-destination half of the same criterion: a harness's own store
        is a place Cargento reads and never writes, so the assertion is that the
        fixture's harness root is untouched rather than that ours was written.
        """
        before = sorted(os.listdir(self.harness_store))

        annotation_store.annotate(
            self.config, self.state, "pi", "sess-1", goal="Ship the cockpit", now=self.NOW
        )

        # A second state object is this process restarted: nothing cached.
        restarted = build_runtime_state(self.config, started=self.NOW + 10)
        entry = annotation_store.find(
            annotation_store.active(self.config, restarted), "pi", "sess-1"
        )

        assert entry is not None
        self.assertEqual("Ship the cockpit", entry["revisions"][-1]["goal"])
        self.assertEqual(before, sorted(os.listdir(self.harness_store)))
        self.assertTrue(annotation_store.store_path(self.config).startswith(str(self.root)))

    def test_a_typed_line_break_is_stored_as_one_space(self) -> None:
        """The product call, recorded where it binds: these fields are one line.

        DRC-4533 asked whether they are single-line or multi-line. Single, and
        the reason is not layout. Relaxing the control-character strip for these
        two fields would reopen a closed credential hole: the scrub is what
        stops a pasted PEM body surviving, which `test_records` holds shut. So
        the store keeps collapsing, and the box collapses too, so the reader
        watches it happen rather than finding it afterwards.
        """
        annotation_store.annotate(
            self.config,
            self.state,
            "pi",
            "sess-1",
            goal="ship it\n\nand the doc",
            output="a PR\tgreen CI",
            now=self.NOW,
        )

        entry = annotation_store.find(
            annotation_store.active(self.config, self.state), "pi", "sess-1"
        )
        assert entry is not None
        revision = entry["revisions"][-1]
        self.assertEqual("ship it and the doc", revision["goal"])
        self.assertEqual("a PR green CI", revision["output"])
        for field in ("goal", "output"):
            with self.subTest(field=field):
                self.assertNotIn("\n", revision[field])
                self.assertNotIn("\t", revision[field])

    def test_activity_after_the_annotation_does_not_erase_it(self) -> None:
        """The deliberate difference from `dismissals`, which lapses on activity.

        A dismissal says "I have handled this", so later movement makes the row
        news again. An annotation says "this is what I asked for", which later
        movement does not answer. There is no watermark to compare against, and
        this test is what stops one being added by analogy.
        """
        annotation_store.annotate(
            self.config, self.state, "pi", "sess-1", goal="Ship the cockpit", now=self.NOW
        )
        entries = annotation_store.active(self.config, self.state)

        # Asserted on the PUBLISHED ROW, far past any plausible watermark,
        # because that is where a lapse would be observable. A predicate in the
        # store used to stand here and took an activity argument it ignored, so
        # adding the lapse to the binding left this test green; it is deleted
        # and this is what replaces it.
        rows: list[dict[str, object]] = [
            {
                "harness": "pi",
                "sid": "sess-1",
                "state": "working",
                "last_activity": self.NOW + 1_000_000,
            }
        ]
        aggregate._attach_annotations(rows, entries)

        self.assertEqual("Ship the cockpit", rows[0]["annotation_goal"])
        self.assertEqual("", rows[0]["annotation_goal_why"])

    # --- revisions ---------------------------------------------------------

    def test_each_save_appends_a_numbered_revision_and_mutates_none(self) -> None:
        """An assessment names the revision it read, so a revision is immutable.

        Editing in place would silently re-point every assessment that cited
        revision 1 at text it never saw.
        """
        annotation_store.annotate(self.config, self.state, "pi", "s", goal="First", now=self.NOW)
        annotation_store.annotate(
            self.config, self.state, "pi", "s", goal="Second", now=self.NOW + 5
        )

        entry = annotation_store.find(annotation_store.active(self.config, self.state), "pi", "s")
        assert entry is not None
        revisions = entry["revisions"]
        self.assertEqual([1, 2], [rev["n"] for rev in revisions])
        self.assertEqual("First", revisions[0]["goal"])
        self.assertEqual("Second", revisions[1]["goal"])
        self.assertEqual(self.NOW, revisions[0]["at"])

    def test_the_two_fields_are_optional_and_independent(self) -> None:
        """Either alone is a real annotation, and the absent one says why."""
        annotation_store.annotate(
            self.config, self.state, "pi", "goal-only", goal="G", now=self.NOW
        )
        annotation_store.annotate(
            self.config, self.state, "pi", "out-only", output="O", now=self.NOW
        )

        entries = annotation_store.active(self.config, self.state)
        goal_only = annotation_store.published(annotation_store.find(entries, "pi", "goal-only"))
        out_only = annotation_store.published(annotation_store.find(entries, "pi", "out-only"))

        self.assertEqual("G", goal_only["goal"])
        self.assertEqual("", goal_only["output"])
        self.assertTrue(goal_only["output_why"])
        self.assertEqual("O", out_only["output"])
        self.assertTrue(out_only["goal_why"])

        # A session nobody annotated is an absence with a reason, never a blank
        # and never a placeholder.
        absent = annotation_store.published(None)
        self.assertEqual("", absent["goal"])
        self.assertTrue(absent["goal_why"])
        self.assertEqual(0, absent["revision_count"])

    def test_saving_one_field_does_not_destroy_the_other(self) -> None:
        """An omitted field is unchanged; an empty one is cleared.

        Collapsing the two would make a client that posts only the goal wipe the
        expected output beside it, which is the opposite of the independence
        these two fields are documented to have.
        """
        annotation_store.annotate(
            self.config, self.state, "pi", "s", goal="G1", output="O1", now=self.NOW
        )
        # Only the goal is sent. The expected output is not mentioned.
        annotation_store.annotate(self.config, self.state, "pi", "s", goal="G2", now=self.NOW + 1)
        entry = annotation_store.find(annotation_store.active(self.config, self.state), "pi", "s")
        assert entry is not None
        self.assertEqual(
            ("G2", "O1"), (entry["revisions"][-1]["goal"], entry["revisions"][-1]["output"])
        )

        # An explicit empty string is a clear of that one field.
        annotation_store.annotate(self.config, self.state, "pi", "s", output="", now=self.NOW + 2)
        entry = annotation_store.find(annotation_store.active(self.config, self.state), "pi", "s")
        assert entry is not None
        self.assertEqual(
            ("G2", ""), (entry["revisions"][-1]["goal"], entry["revisions"][-1]["output"])
        )

    def test_an_unannotated_session_publishes_no_zero_revision_and_no_epoch(self) -> None:
        """`revision: 0` and `at: 0.0` are the zeros the first rule forbids.

        A render printing the annotation timestamp would show 1 January 1970 for
        every session nobody annotated.
        """
        absent = annotation_store.published(None)
        self.assertIsNone(absent["revision"])
        self.assertIsNone(absent["at"])

    def test_a_prefix_binding_says_so_and_an_exact_one_stays_quiet(self) -> None:
        """The hazard DRC-4508 named, reported rather than claimed away.

        `collectors/claude.py` passes the transcript stem's first eight
        characters to `base_session`, so a Claude row's sid IS the display
        prefix and the full stem is published beside it as `resume_id`.
        """
        rows: list[Any] = [
            {
                "harness": "claude",
                "sid": "77aa41c2",
                "resume_id": "77aa41c2-aaaa-4aaa",
                "state": "x",
            },
            {"harness": "pi", "sid": "full-identity", "resume_id": None, "state": "x"},
        ]
        aggregate._attach_annotations(rows, ())
        self.assertTrue(rows[0]["annotation_binding_why"], "a truncated identity said nothing")
        self.assertEqual("", rows[1]["annotation_binding_why"])

    def test_a_display_length_identity_says_so_even_with_no_resume_id(self) -> None:
        """DRC-4533, second item. The length proxy missed the case the Claude
        collector documents.

        A Claude row that reached the loop from the task store alone has no
        transcript and therefore no `resume_id`, which that collector records as
        the None case. Its sid is still the eight-character prefix, so the row
        claimed an exact binding it never had.
        """
        rows: list[Any] = [
            {"harness": "claude", "session": "77aa41c2", "sid": "77aa41c2", "resume_id": None},
        ]
        aggregate._attach_annotations(rows, ())
        self.assertTrue(
            rows[0]["annotation_binding_why"],
            "a display-length identity with no resume id claimed exact binding",
        )

    def test_a_saved_revision_that_repeats_the_last_one_is_not_appended(self) -> None:
        """Re-saving unchanged text is not a new request, so it is not a revision.

        Otherwise a reader who opens the field and closes it burns a revision
        number that an assessment will later cite as a change of intent.
        """
        annotation_store.annotate(self.config, self.state, "pi", "s", goal="Same", now=self.NOW)
        annotation_store.annotate(self.config, self.state, "pi", "s", goal="Same", now=self.NOW + 5)

        entry = annotation_store.find(annotation_store.active(self.config, self.state), "pi", "s")
        assert entry is not None
        self.assertEqual(1, len(entry["revisions"]))

    # --- untrusted input ---------------------------------------------------

    def test_a_credential_is_redacted_before_the_text_is_bounded(self) -> None:
        """Order matters, and `records.redact_clip` records why.

        Bounding first can cut a key's tail off, leaving a head that no longer
        matches the shape list and is published intact.
        """
        secret = "AKIA" + "Q" * 16
        cap = self.config.annotation_text_cap_chars
        # Straddling the cap on purpose. A short fixture never reaches the clip,
        # so clip-then-redact and redact-then-clip are indistinguishable and the
        # test proves nothing about the order it is named for. Here the tail
        # falls outside the bound, so clipping first would leave a head the
        # shape list no longer matches and publish it intact.
        annotation_store.annotate(
            self.config, self.state, "pi", "s", goal="x" * (cap - 10) + " " + secret, now=self.NOW
        )
        entry = annotation_store.find(annotation_store.active(self.config, self.state), "pi", "s")
        assert entry is not None
        stored = entry["revisions"][-1]["goal"]
        self.assertNotIn(secret, stored)
        self.assertNotIn(secret[:12], stored, "a clipped head of the key survived")

    def test_text_is_clipped_to_the_configured_bound(self) -> None:
        annotation_store.annotate(
            self.config, self.state, "pi", "s", goal="x" * 5_000, now=self.NOW
        )
        entry = annotation_store.find(annotation_store.active(self.config, self.state), "pi", "s")
        assert entry is not None
        self.assertLessEqual(
            len(entry["revisions"][-1]["goal"]), self.config.annotation_text_cap_chars
        )

    def test_binding_uses_the_full_session_id_not_a_display_prefix(self) -> None:
        """Two Claude sessions sharing an eight-character prefix are two rows.

        `sessions.py` publishes both `session` (the prefix) and `sid` (the full
        id) on every row, so exact binding needs no new identity work. Keying on
        the prefix would let one session's words appear under another's name.
        """
        first = "77aa41c2" + "-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        second = "77aa41c2" + "-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        annotation_store.annotate(
            self.config, self.state, "claude", first, goal="Mine", now=self.NOW
        )

        entries = annotation_store.active(self.config, self.state)
        self.assertIsNotNone(annotation_store.find(entries, "claude", first))
        self.assertIsNone(annotation_store.find(entries, "claude", second))
        self.assertIsNone(annotation_store.find(entries, "claude", "77aa41c2"))

    # --- degradation -------------------------------------------------------

    def test_a_corrupt_store_reads_as_empty_and_one_bad_entry_costs_one_entry(self) -> None:
        path = annotation_store.store_path(self.config)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text("{ not json", encoding="utf-8")
        self.assertEqual((), annotation_store.load(self.config))

        Path(path).write_text(
            json.dumps(
                {
                    "v": 1,
                    "entries": [
                        {"harness": "pi", "sid": "good", "revisions": [{"n": 1, "goal": "kept"}]},
                        "not a record",
                        {"sid": "no harness", "revisions": []},
                    ],
                }
            ),
            encoding="utf-8",
        )
        kept = annotation_store.load(self.config)
        self.assertEqual(1, len(kept))
        self.assertEqual("good", kept[0]["sid"])

    def test_the_off_switch_reads_empty_and_writes_nothing(self) -> None:
        off = self._config(annotations_enabled=False)
        state = build_runtime_state(off, started=self.NOW)
        self.assertFalse(annotation_store.annotate(off, state, "pi", "s", goal="G", now=self.NOW))
        self.assertEqual((), annotation_store.load(off))
        self.assertFalse(os.path.exists(annotation_store.store_path(off)))

    def test_clearing_removes_the_session_and_leaves_the_others(self) -> None:
        annotation_store.annotate(self.config, self.state, "pi", "keep", goal="K", now=self.NOW)
        annotation_store.annotate(self.config, self.state, "pi", "drop", goal="D", now=self.NOW)
        annotation_store.clear(self.config, self.state, "pi", "drop")

        entries = annotation_store.active(self.config, self.state)
        self.assertIsNotNone(annotation_store.find(entries, "pi", "keep"))
        self.assertIsNone(annotation_store.find(entries, "pi", "drop"))

    def test_the_store_is_bounded_by_sessions_and_by_revisions(self) -> None:
        """Two count bounds and no time-to-live, for `dismissals._bounded`'s reason.

        A TTL would delete what the reader asked for while the session it
        describes is still on the board.
        """
        limit = self.config.annotation_max_sessions
        for index in range(limit + 3):
            annotation_store.annotate(
                self.config, self.state, "pi", f"s{index}", goal="G", now=self.NOW + index
            )
        self.assertEqual(limit, len(annotation_store.load(self.config)))
        # The oldest gave way, the newest is present.
        self.assertIsNone(annotation_store.find(annotation_store.load(self.config), "pi", "s0"))

        # Newer than every session above, or the session bound evicts this one
        # between saves and its numbering restarts. The two bounds are
        # independent and a fixture that lets them interact tests neither.
        revision_limit = self.config.annotation_max_revisions
        for index in range(revision_limit + 3):
            annotation_store.annotate(
                self.config,
                self.state,
                "pi",
                "many",
                goal=f"G{index}",
                now=self.NOW + 9_000 + index,
            )
        entry = annotation_store.find(annotation_store.load(self.config), "pi", "many")
        assert entry is not None
        self.assertEqual(revision_limit, len(entry["revisions"]))
        # Numbering keeps counting, so a dropped revision reads as dropped
        # rather than as one that never existed.
        self.assertEqual(revision_limit + 3, entry["revisions"][-1]["n"])


class AnUnwritableStoreIsReportedRatherThanSwallowedTest(unittest.TestCase):
    """DRC-4533: `save()`'s failure arm and the `persisted:false` it feeds.

    Both were untested. The diagnostic sentence was corrected on this branch
    from "next restart" to "next collection" and was then defended by nothing,
    which is the shape of a claim that quietly goes stale.

    What the arm has to get right is narrow and easy to get wrong: the write
    fails, the words stay in this process, the caller is told, and the next
    collection reloads from disk and drops them. The page's cue says exactly
    that, so if this arm changes, that sentence becomes a lie.
    """

    NOW = 1_800_000_000.0

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # A FILE where the state home has to be a directory. `os.makedirs` then
        # raises FileExistsError, which is an OSError, on a real filesystem
        # rather than through a patched-out `open`: the arm under test is the
        # one a full disk or a read-only home reaches, and a mock of the write
        # would not prove `os.replace` and the temp-file cleanup are inside it.
        self.blocked = self.root / "state"
        self.blocked.write_text("not a directory", encoding="utf-8")
        self.config = build_runtime_config(
            environ={"HOME": str(self.root), "CARGENTO_HOME": str(self.blocked)},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
        )
        self.state = build_runtime_state(self.config, started=self.NOW)
        self.said: list[str] = []

    def test_the_write_fails_loudly(self) -> None:
        landed = annotation_store.save(self.config, (), diagnostic_sink=self.said.append)

        self.assertFalse(landed)
        self.assertTrue(
            any("could not write the annotation store" in line for line in self.said),
            self.said,
        )
        # The sentence names the collection, not a restart. A reader who is told
        # the wrong horizon plans around the wrong one.
        self.assertTrue(any("gone at the next collection" in line for line in self.said), self.said)

    def test_a_write_that_fails_after_the_temp_file_exists_cleans_it_up(self) -> None:
        """The cleanup arm, which needs a failure LATER than the first one.

        Written as its own case because the obvious fixture cannot reach it: an
        unwritable home fails at `makedirs`, before `os.open` has made anything
        to clean up, so a leftover assertion there passes with the cleanup
        deleted. Measured: that mutation survived. Here the home is real and the
        TARGET is a directory, so the temp file is written and `os.replace` is
        what fails.
        """
        home = self.root / "writable"
        home.mkdir()
        config = build_runtime_config(
            environ={"HOME": str(self.root), "CARGENTO_HOME": str(home)},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
        )
        # A directory exactly where the store file goes.
        pathlib.Path(annotation_store.store_path(config)).mkdir(parents=True)

        landed = annotation_store.save(config, (), diagnostic_sink=self.said.append)

        self.assertFalse(landed)
        strays = [name for name in os.listdir(home) if ".tmp" in name]
        self.assertEqual([], strays, "the partial write was left behind")

    def test_annotate_reports_the_failure_while_this_process_keeps_the_words(self) -> None:
        landed = annotation_store.annotate(
            self.config,
            self.state,
            "pi",
            "sess-1",
            goal="Ship the cockpit",
            now=self.NOW,
            diagnostic_sink=self.said.append,
        )

        # False, and that is what the endpoint publishes as `persisted`.
        self.assertFalse(landed)
        # And yet the revision IS in this process: `annotate` sets
        # `state.annotations` before it writes, inside the lock. That is the
        # whole reason the page may not treat a false here as a lost save
        # without also saying the words are about to go.
        held = annotation_store.find(
            annotation_store.active(self.config, self.state), "pi", "sess-1"
        )
        assert held is not None
        self.assertEqual("Ship the cockpit", held["revisions"][-1]["goal"])

    def test_the_next_collection_is_what_actually_takes_the_words(self) -> None:
        annotation_store.annotate(
            self.config,
            self.state,
            "pi",
            "sess-1",
            goal="Ship the cockpit",
            now=self.NOW,
            diagnostic_sink=self.said.append,
        )

        # `aggregate` calls this on every collection. It reloads from disk, and
        # disk never got the write, so the words go here rather than at a
        # restart. The page's `unpersisted` cue is written against this fact.
        annotation_store.refresh(self.config, self.state)

        gone = annotation_store.find(
            annotation_store.active(self.config, self.state), "pi", "sess-1"
        )
        self.assertIsNone(gone)


class TheSaveReadsTheAnswerTheEndpointSendsTest(unittest.TestCase):
    """The two halves of one save, held to the same key.

    Measured: the page checked `saved.annotated`, which `/api/annotate` has
    never sent. Every save would have landed on disk and shown the reader a
    refusal with their words still in the box, and the test that covered it
    stubbed the response itself, so it agreed with the page rather than with
    the server. Two independent statements, compared here.
    """

    HANDLER = (Path(__file__).resolve().parents[1] / "cargento_runtime" / "http_api.py").read_text(
        encoding="utf-8"
    )
    PAGE = (
        Path(__file__).resolve().parents[1] / "cargento_runtime" / "web" / "next-cockpit.js"
    ).read_text(encoding="utf-8")

    def test_the_page_reads_a_key_the_handler_writes(self) -> None:
        body = self.HANDLER[self.HANDLER.index("    def _annotate(") :]
        body = body[: body.index("\n    def ", 1)]
        sent = set(re.findall(r'^\s+"([a-z_]+)": ', body, re.MULTILINE))
        self.assertIn("ok", sent)
        save = self.PAGE[self.PAGE.index("async function nextCockpitHeldSave(") :]
        save = save[: save.index("\nfunction ")]
        read = set(re.findall(r"\bsaved\.([a-z_]+)\b", save))
        self.assertTrue(read, "the save reads nothing off the answer")
        self.assertEqual(set(), read - sent, "the page reads a key the endpoint never sends")


class AnnotationWiringTest(unittest.TestCase):
    """The two wirings a copy-paste breaks silently.

    Both off-switch tests elsewhere construct the config directly, and the
    documentation oracle only greps `cli.py` for the flag string, so neither
    would notice `annotations_enabled=not args.no_dismiss`.
    """

    NOW = 1_800_000_000.0

    def test_the_flag_reaches_the_config(self) -> None:
        """Through `build_runtime`, not through argparse.

        An earlier version of this test asserted only that the parser sets
        `args.no_annotations`, which argparse guarantees. The arbiter proved it
        hollow by mutating line 381 to `annotations_enabled=not args.no_dismiss`
        and watching the whole suite stay green. It reads the config now.
        """
        parser = cli.build_parser()
        off, _state = cli.build_runtime(parser.parse_args(["--no-annotations"]), started=self.NOW)
        self.assertFalse(off.annotations_enabled)
        # And not by accident of another flag: the plausible copy-paste is
        # `not args.no_dismiss`, so pin that the two switches are independent.
        self.assertTrue(off.dismissals_enabled)
        on, _state2 = cli.build_runtime(parser.parse_args([]), started=self.NOW)
        self.assertTrue(on.annotations_enabled)
        dismiss_off, _s3 = cli.build_runtime(parser.parse_args(["--no-dismiss"]), started=self.NOW)
        self.assertTrue(dismiss_off.annotations_enabled)

    def test_the_capability_is_published_only_when_the_store_is_live(self) -> None:
        """The flag's help text says the page offers no field to type them in,
        which needs the page to be told."""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        on_config, on_state = make_runtime(state_home=home, state_dir=Path(home))
        self.assertIs(
            True,
            cli.build_application(on_config, on_state, clock=lambda: 0.0)
            .collect(show_all=True)
            .get("annotate"),
        )
        off_config, off_state = make_runtime(
            state_home=home, state_dir=Path(home), annotations_enabled=False
        )
        self.assertIsNone(
            cli.build_application(off_config, off_state, clock=lambda: 0.0)
            .collect(show_all=True)
            .get("annotate")
        )


class AnnotationOnTheRowTest(unittest.TestCase):
    """The store reaching the published payload.

    `AnnotationStoreTest` covers the store. This covers the one thing every
    surface downstream depends on: that a session row carries what the reader
    typed, and that a row with nothing typed carries the absence and its reason
    rather than no key at all. A missing key renders as `undefined`, which is
    the blank the shared contract's first rule forbids.
    """

    def test_a_row_carries_what_was_typed_and_an_unannotated_row_says_why(self) -> None:
        rows: list[Any] = [
            {"harness": "pi", "sid": "typed", "state": "working"},
            {"harness": "pi", "sid": "untouched", "state": "working"},
        ]
        entries: Any = (
            {
                "harness": "pi",
                "sid": "typed",
                "revisions": ({"n": 2, "at": 5.0, "goal": "Ship it", "output": ""},),
            },
        )
        aggregate._attach_annotations(rows, entries)

        self.assertEqual("Ship it", rows[0]["annotation_goal"])
        self.assertEqual(2, rows[0]["annotation_revision"])
        self.assertEqual("", rows[0]["annotation_goal_why"])
        # The expected output was never typed, so it names its absence.
        self.assertTrue(rows[0]["annotation_output_why"])

        # Present, not absent: the key exists so the render has something to ask.
        self.assertEqual("", rows[1]["annotation_goal"])
        self.assertTrue(rows[1]["annotation_goal_why"])
        self.assertEqual(0, rows[1]["annotation_revision_count"])

    def test_binding_on_the_row_is_the_full_sid_not_the_display_prefix(self) -> None:
        """`sessions.py` publishes both. Keying on `session` would let one
        session's words appear under another's name."""
        rows: list[Any] = [
            {"harness": "claude", "session": "77aa41c2", "sid": "77aa41c2-aaaa", "state": "x"}
        ]
        entries: Any = (
            {
                "harness": "claude",
                "sid": "77aa41c2-bbbb",
                "revisions": ({"n": 1, "at": 1.0, "goal": "Not yours", "output": ""},),
            },
        )
        aggregate._attach_annotations(rows, entries)
        self.assertEqual("", rows[0]["annotation_goal"])
        self.assertTrue(rows[0]["annotation_goal_why"])


class ProvenanceReachesTheDurableRecordTest(unittest.TestCase):
    """DRC-4533, first item. The record must not say a model wrote a line a
    transcript wrote.

    `goal_source` was added so the two can be told apart. The writer that
    persists an observer goal into semantic work history did not read it, and
    stamped every one of them as model-derived including the deterministic ones
    that are the default.
    """

    def test_a_deterministic_goal_is_not_recorded_as_model_derived(self) -> None:
        rows = [
            {
                "harness": "pi",
                "sid": "a",
                "observed_at": 10.0,
                "goal": "From the transcript",
                "goal_source": "deterministic",
                "source": "observer",
            },
            {
                "harness": "pi",
                "sid": "b",
                "observed_at": 11.0,
                "goal": "Reworded",
                "goal_source": "model",
                "source": "observer",
            },
            {
                "harness": "pi",
                "sid": "c",
                "observed_at": 12.0,
                "goal": "Older sidecar",
                "source": "observer",
            },
        ]
        facts = project_context._semantic_observer_facts(rows)
        claims = [f["actor_claim"] for f in facts]
        self.assertEqual(3, len(claims))
        self.assertNotIn("model", claims[0], "a transcript line recorded as model-derived")
        self.assertIn("model", claims[1])
        # A sidecar predating the field claims neither, rather than defaulting
        # to the one that is wrong more often.
        self.assertNotIn("model", claims[2])
        self.assertNotEqual(claims[0], claims[2], "unknown provenance read as deterministic")


class CachedSidecarIsUntrustedTest(unittest.TestCase):
    """DRC-4533, third item. The cached branch republishes fields nothing checks.

    Any local process can rewrite a sidecar. `goal` is type-checked and
    `goal_source` is checked against a frozen set; the four beside them are not.
    """

    def test_a_rewritten_sidecar_cannot_publish_a_non_string_or_an_unbounded_goal(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        config = build_runtime_config(
            environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=root / "server.py",
        )
        state = build_runtime_state(config, started=1.0)
        transcript = root / "t.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")

        runtime_observer.write_sidecar(
            config,
            "pi",
            "hostile",
            {
                "goal": "ok",
                "observed_at": 10.0,
                "transcript": "sig",
                "deterministic_goal": {"k": "AKIAQQQQQQQQQQQQQQQQ"},
                "stage": ["not", "a", "string"],
                "block": {"nested": True},
                "reason": 12345,
            },
        )
        out = project_context._observe_session(
            config, state, str(transcript), ("pi", "hostile"), now=20.0, refresh=False
        )
        assert out is not None
        for field in ("deterministic_goal", "stage", "block", "reason"):
            self.assertNotIsInstance(out[field], (dict, list), f"{field} published a container")

        # And a plausible but enormous string is bounded like every other
        # published goal line.
        runtime_observer.write_sidecar(
            config,
            "pi",
            "hostile",
            {
                "goal": "ok",
                "observed_at": 11.0,
                "transcript": "sig",
                "deterministic_goal": "x" * 5_000,
            },
        )
        out2 = project_context._observe_session(
            config, state, str(transcript), ("pi", "hostile"), now=20.0, refresh=False
        )
        assert out2 is not None
        self.assertLessEqual(len(out2["deterministic_goal"]), config.observer_goal_cap_chars + 1)


if __name__ == "__main__":
    unittest.main()
