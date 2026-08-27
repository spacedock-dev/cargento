"""The repo-wide ISO-8601 rule: an offset-less stamp means UTC.

The rule only has teeth on a machine whose local time is not UTC: where it is,
a naive-means-local bug and a naive-means-UTC fix produce identical numbers, so
an assertion cannot tell them apart. That is why the original defect survived in
`parse_ts` and `quota._epoch` unnoticed, and it shapes this file into two layers.

Every assertion here states the contract directly, comparing against an
explicitly UTC-constructed instant. Those run everywhere, and they discriminate
on any developer machine that is not itself UTC, which is where the defect was
found.

On top of that, the tests marked with `needs_tz` **force** a non-UTC timezone, so
the discrimination does not depend on where the suite happens to run. That needs
`time.tzset`, which is Unix-only, so they skip on Windows rather than erroring:
the first version of this file called it unconditionally and took out the whole
`platform-tests` Windows job. The contract-level assertions still run there.
"""

from __future__ import annotations

import datetime as dt
import os
import time
import unittest
from contextlib import contextmanager
from typing import TYPE_CHECKING

from cargento_runtime import quota, records

if TYPE_CHECKING:
    from collections.abc import Iterator

# +08:00 with no DST, so the offset is the same in every season and a failure
# reads as a timezone bug rather than as a date-dependent flake. This is also
# the offset the defect was found on.
TZ = "Asia/Taipei"

# `time.tzset` exists on Unix only. Probed rather than keyed off `sys.platform`
# so the skip follows the capability the tests actually need.
HAS_TZSET = hasattr(time, "tzset")
needs_tz = unittest.skipUnless(
    HAS_TZSET, "time.tzset is Unix-only, so the process timezone cannot be forced here"
)


@contextmanager
def tz(name: str) -> Iterator[None]:
    """Run the body with `TZ` set, restoring both the variable and libc's cache.

    `time.tzset` is what actually moves `datetime.timestamp()`'s idea of local
    time; setting the environment variable alone changes nothing in a process
    that has already read it. Callers must carry `@needs_tz`.
    """
    before = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if before is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = before
        time.tzset()


class IsoEpochTest(unittest.TestCase):
    # 2026-01-02T03:04:05Z, chosen so every field differs and a transposition
    # cannot pass by symmetry.
    UTC_EPOCH = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp()

    @needs_tz
    def test_a_naive_stamp_is_read_as_utc_not_as_local(self) -> None:
        # The regression. Under +08:00 the old `fromisoformat().timestamp()`
        # returned this instant minus eight hours, which is what pushed a live
        # turn out of the activity window.
        with tz(TZ):
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T03:04:05"))

    @needs_tz
    def test_the_naive_reading_does_not_move_with_the_timezone(self) -> None:
        readings = []
        for name in ("UTC", TZ, "America/New_York"):
            with tz(name):
                readings.append(records.iso_epoch("2026-01-02T03:04:05"))
        self.assertEqual([self.UTC_EPOCH] * 3, readings)

    @needs_tz
    def test_an_explicit_offset_is_honoured_rather_than_overridden(self) -> None:
        # The common case in practice: every source measured on 2026-08-06 sends
        # one. A fix that forced UTC onto an aware stamp would break these.
        with tz(TZ):
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T03:04:05+00:00"))
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T11:04:05+08:00"))
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-01T22:04:05-05:00"))

    @needs_tz
    def test_a_trailing_z_is_accepted(self) -> None:
        with tz(TZ):
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T03:04:05Z"))

    def test_unusable_input_is_nothing_rather_than_a_guess(self) -> None:
        unusable: tuple[object, ...] = (
            "",
            "not a date",
            "2026-13-45T99:99:99",
            None,
            1_700_000_000,
            [],
            {},
        )
        for value in unusable:
            self.assertIsNone(records.iso_epoch(value), repr(value))


class ContractTest(unittest.TestCase):
    """The rule stated without forcing a timezone, so Windows checks it too.

    These compare against an explicitly UTC-constructed instant, which is the
    contract itself rather than a proxy for it. They cannot fail on a machine
    whose local time is already UTC, and they catch the defect on every machine
    that is not, which includes the one it was found on. The `needs_tz` tests
    above remove that dependency where the platform allows it; these are what
    keeps the Windows runner from asserting nothing at all.
    """

    NAIVE = "2026-01-02T03:04:05"
    EXPECTED = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp()

    def test_every_reader_agrees_a_naive_stamp_is_the_utc_instant(self) -> None:
        # One assertion per reader, because the whole defect was two of the four
        # disagreeing with the other two.
        self.assertEqual(self.EXPECTED, records.iso_epoch(self.NAIVE))
        self.assertEqual(self.EXPECTED, records.parse_ts(self.NAIVE))
        self.assertEqual(self.EXPECTED, records.parse_utc_sql(self.NAIVE.replace("T", " ")))
        self.assertEqual(self.EXPECTED, quota._epoch(self.NAIVE))

    def test_a_naive_stamp_and_its_utc_spelling_are_the_same_instant(self) -> None:
        # The rule as an equality between two inputs rather than against a
        # constant, so it holds whatever the machine's clock is set to.
        for aware in (self.NAIVE + "Z", self.NAIVE + "+00:00"):
            self.assertEqual(records.iso_epoch(aware), records.iso_epoch(self.NAIVE), aware)
            self.assertEqual(records.parse_ts(aware), records.parse_ts(self.NAIVE), aware)

    def test_an_offset_is_never_overridden(self) -> None:
        # Tz-independent by construction: +08:00 and -05:00 name the same instant
        # as the Z spelling, whatever the reader's own zone.
        self.assertEqual(
            records.iso_epoch("2026-01-02T03:04:05Z"),
            records.iso_epoch("2026-01-02T11:04:05+08:00"),
        )
        self.assertEqual(
            records.iso_epoch("2026-01-02T03:04:05Z"),
            records.iso_epoch("2026-01-01T22:04:05-05:00"),
        )


class ParseTsTest(unittest.TestCase):
    """`parse_ts` is the transcript reader: Claude, Pi, turns, transcripts."""

    @needs_tz
    def test_a_naive_transcript_stamp_is_utc(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                records.parse_ts("2026-01-02T03:04:05"),
            )

    @needs_tz
    def test_it_agrees_with_the_shared_helper(self) -> None:
        # Both readers must not drift again, which is how they came to disagree.
        with tz(TZ):
            for value in ("2026-01-02T03:04:05", "2026-01-02T03:04:05Z", "bad"):
                self.assertEqual(records.iso_epoch(value), records.parse_ts(value), value)


class UsageSignalTest(unittest.TestCase):
    @staticmethod
    def _record(value: object) -> dict[str, object]:
        return {
            "type": "assistant",
            "message": {"usage": {"output_tokens": value}},
        }

    def test_claude_output_tokens_are_the_only_measured_signal(self) -> None:
        self.assertEqual(37, records.usage_signal(self._record(37), "claude"))
        self.assertEqual(0, records.usage_signal(self._record(0), "claude"))

    def test_a_claude_shaped_record_is_refused_for_every_other_scanned_harness(self) -> None:
        record = self._record(37)
        for harness in ("codex", "copilot", "gemini", "droid"):
            with self.subTest(harness=harness):
                self.assertIsNone(records.usage_signal(record, harness))

    def test_malformed_or_unmeasured_values_are_nothing_not_zero(self) -> None:
        malformed: tuple[object, ...] = (None, True, -1, 1.5, "37", {}, [])
        for value in malformed:
            with self.subTest(value=value):
                self.assertIsNone(records.usage_signal(self._record(value), "claude"))
        self.assertIsNone(
            records.usage_signal(
                {"type": "user", "message": {"usage": {"output_tokens": 37}}},
                "claude",
            )
        )
        self.assertIsNone(records.usage_signal({"type": "assistant"}, "claude"))


class ParseUtcSqlTest(unittest.TestCase):
    """`parse_utc_sql` reads Copilot's and Goose's SQLite text columns."""

    @needs_tz
    def test_sqlites_space_separated_default_spelling_is_read_as_utc(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                records.parse_utc_sql("2026-01-02 03:04:05"),
            )

    @needs_tz
    def test_an_offset_bearing_column_is_honoured(self) -> None:
        # Copilot's real store was measured sending these, so the naive branch is
        # a guard rather than the normal path.
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                records.parse_utc_sql("2026-01-02 11:04:05+08:00"),
            )

    def test_unusable_input_is_zero_because_the_callers_window_on_it(self) -> None:
        for value in (None, "", "nonsense", 0):
            self.assertEqual(0, records.parse_utc_sql(value), repr(value))


class QuotaEpochTest(unittest.TestCase):
    """`quota._epoch` reads `resets_at`, which drives every reset countdown."""

    @needs_tz
    def test_a_naive_reset_stamp_is_utc(self) -> None:
        # An eight-hour error here moves the countdown and, since A5, the burn
        # projection that fires off `resetAt`.
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                quota._epoch("2026-01-02T03:04:05"),
            )

    @needs_tz
    def test_an_offset_bearing_reset_stamp_is_honoured(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                quota._epoch("2026-01-02T03:04:05+00:00"),
            )

    @needs_tz
    def test_a_numeric_stamp_still_passes_through_unchanged(self) -> None:
        # The endpoint has sent both shapes; epoch seconds carry no timezone
        # question and must not be routed through the ISO reader.
        with tz(TZ):
            self.assertEqual(1_700_000_000.0, quota._epoch(1_700_000_000))
            self.assertIsNone(quota._epoch(0))
            self.assertIsNone(quota._epoch(True))


class StripPromptWrappersTest(unittest.TestCase):
    """The image marker is an envelope around a prompt, not a prompt.

    Both spellings were measured in the wild: Codex writes an XML-ish
    `<image …>` and Claude writes `[Image: source: …]` in plain text.
    """

    def test_a_codex_image_wrapper_yields_the_text_behind_it(self) -> None:
        # All 36 Codex records that open with one carried operator text after
        # it, so this is the case that rejecting on the tag would have lost.
        text = (
            '<image name=[Image #1] path="/var/folders/tmp/Screenshot.png"> </image> '
            "Where are you seeing this?"
        )

        self.assertEqual("Where are you seeing this?", records.strip_prompt_wrappers(text))

    def test_an_unquoted_attribute_with_spaces_and_hashes_does_not_stop_it(self) -> None:
        # Codex spells the name `[Image #1]` with no quotes at all, so an
        # attribute matcher that expected quoting would leave the tag in place.
        self.assertEqual("ok", records.strip_prompt_wrappers("<image name=[Image #1]> </image> ok"))

    def test_several_attachments_are_all_peeled(self) -> None:
        # One message can carry several screenshots, each its own marker.
        codex = '<image path="/a.png"></image><image path="/b.png"></image>look at both'
        claude = "[Image: source: /a.png] [Image: source: /b.png] look at both"

        self.assertEqual("look at both", records.strip_prompt_wrappers(codex))
        self.assertEqual("look at both", records.strip_prompt_wrappers(claude))

    def test_the_no_colon_spelling_is_peeled_too(self) -> None:
        # One record in 386 spells it this way, which is why the separator is a
        # character class rather than a literal colon.
        self.assertEqual("go", records.strip_prompt_wrappers("[Image source: /a.png] go"))

    def test_a_marker_only_message_strips_to_nothing(self) -> None:
        # 385 of 386 Claude `[Image:` records are exactly this.
        self.assertEqual("", records.strip_prompt_wrappers("[Image: source: /a.png]"))

    def test_ordinary_text_is_returned_unchanged_apart_from_trimming(self) -> None:
        self.assertEqual(
            "Fix the flaky test", records.strip_prompt_wrappers("  Fix the flaky test  ")
        )


class InjectedPromptTest(unittest.TestCase):
    """Which user records are the harness talking, rather than the operator.

    Every shape asserted here was counted in a local corpus: 2,737 Codex
    user-role texts across 457 rollouts, and 21,899 Claude user-role texts
    across 3,769 transcripts.
    """

    def test_every_measured_codex_tag_is_rejected(self) -> None:
        for tag in sorted(records._CODEX_USER_TAGS | records._CODEX_DEVELOPER_TAGS):
            with self.subTest(tag=tag):
                self.assertTrue(records.injected_prompt(f"<{tag}>body</{tag}>", "codex"))

    def test_every_measured_claude_tag_is_rejected(self) -> None:
        for tag in sorted(records._CLAUDE_USER_TAGS):
            with self.subTest(tag=tag):
                self.assertTrue(records.injected_prompt(f"<{tag}>body</{tag}>", "claude"))

    def test_the_measured_vocabulary_is_pinned_literally(self) -> None:
        """The two tests above iterate the very sets they assert against, so
        they stay green for any contents: delete the corpus's largest injection
        shape and nothing fails. These figures are the vocabulary itself, so a
        tag that goes missing or an unmeasured one that creeps in is caught.
        """
        self.assertEqual(11, len(records._CODEX_USER_TAGS))
        self.assertEqual(7, len(records._CODEX_DEVELOPER_TAGS))
        self.assertEqual(9, len(records._CLAUDE_USER_TAGS))
        self.assertEqual(
            {
                "bash-input",
                "bash-stdout",
                "local-command-stdout",
                "task-notification",
                "teammate-message",
            },
            (records._CODEX_USER_TAGS | records._CODEX_DEVELOPER_TAGS) & records._CLAUDE_USER_TAGS,
        )
        for tag in ("recommended_plugins", "skill", "subagent_notification", "user_shell_command"):
            self.assertIn(tag, records._CODEX_USER_TAGS)
        for tag in ("permissions", "multi_agent_mode", "collaboration_mode"):
            self.assertIn(tag, records._CODEX_DEVELOPER_TAGS)
        for tag in ("local-command-caveat", "system-reminder", "local-command-stderr"):
            self.assertIn(tag, records._CLAUDE_USER_TAGS)
        # The slash-command wrappers are absent on purpose; see the test below.
        for tag in ("command-message", "command-name", "command-args"):
            self.assertNotIn(tag, records._ANY_INJECTED_TAG)

    def test_a_slash_command_is_the_operator_speaking(self) -> None:
        """A slash command is what the person asked for, in harness markup.

        Rejecting it cost 1,493 of 15,109 `_turn_signal`-reachable Claude
        prompts, and `transcripts.prompt_title` renders these same bytes as
        `/review 1287`, so the predicate agreeing with it is the contract.
        """
        text = (
            "<command-message>review is running…</command-message>\n"
            "<command-name>/review</command-name>\n"
            "<command-args>1287</command-args>"
        )
        for harness in ("codex", "claude", "droid"):
            with self.subTest(harness=harness):
                self.assertFalse(records.injected_prompt(text, harness))

    def test_a_teammate_message_is_still_not_the_operator(self) -> None:
        # The measured cost is accepted, not overlooked: 563 local sessions
        # carry one and will show nothing from it.
        self.assertTrue(
            records.injected_prompt("<teammate-message>go</teammate-message>", "claude")
        )

    def test_an_attribute_bearing_tag_is_still_recognised(self) -> None:
        # The commonest injection of all carries attributes, so a matcher that
        # only understood `<name>` would miss 1,176 Claude records.
        self.assertTrue(
            records.injected_prompt(
                '<teammate-message teammate_id="lead">go</teammate-message>', "claude"
            )
        )

    def test_the_two_harness_vocabularies_do_not_transfer(self) -> None:
        """Codex underscores and Claude hyphens are different sets, and only
        five names are in both. Treating one list as universal would reject
        operator text on the harness that never sends that shape."""
        self.assertTrue(records.injected_prompt("<recommended_plugins>x", "codex"))
        self.assertFalse(records.injected_prompt("<recommended_plugins>x", "claude"))
        self.assertTrue(records.injected_prompt("<local-command-caveat>x", "claude"))
        self.assertFalse(records.injected_prompt("<local-command-caveat>x", "codex"))

    def test_an_unmeasured_harness_gets_the_union(self) -> None:
        # No evidence to narrow with, and every name in either set is machinery
        # no operator opens a prompt with.
        for tag in ("recommended_plugins", "local-command-caveat"):
            with self.subTest(tag=tag):
                self.assertTrue(records.injected_prompt(f"<{tag}>x", "droid"))

    def test_an_image_wrapper_is_stripped_rather_than_rejected(self) -> None:
        text = '<image name=[Image #1] path="/tmp/a.png"></image> Where are you seeing this?'

        self.assertFalse(records.injected_prompt(text, "codex"))

    def test_a_wrapper_around_an_injection_is_still_rejected(self) -> None:
        # Stripping happens first, so what the envelope carries is what decides.
        self.assertTrue(
            records.injected_prompt("[Image: source: /a.png] Stop hook feedback: retry", "claude")
        )

    def test_nothing_left_after_stripping_is_a_rejection(self) -> None:
        for empty in ("", "   ", "[Image: source: /a.png]", "<image></image>"):
            with self.subTest(text=empty):
                self.assertTrue(records.injected_prompt(empty, "claude"))

    def test_every_untagged_prefix_is_rejected_on_both_harnesses(self) -> None:
        """No tag regex can reach these: the harness writes them as prose."""
        for prefix in records._INJECTED_PROMPT_PREFIXES:
            for harness in ("codex", "claude"):
                with self.subTest(prefix=prefix, harness=harness):
                    self.assertTrue(records.injected_prompt(prefix + " and then some", harness))

    def test_warmup_is_matched_whole_not_as_a_prefix(self) -> None:
        # All 97 occurrences are exactly this word. As a prefix it would reject
        # a person asking for a warmup, which is a person saying something.
        self.assertTrue(records.injected_prompt("Warmup", "claude"))
        self.assertFalse(records.injected_prompt("Warmup the cache before the run", "claude"))

    def test_operator_text_survives(self) -> None:
        for text in (
            "Fix the flaky Windows test",
            "commit and push the changes",
            "1",
            # Markup that is not at the front is not an envelope.
            "Replace the <div> wrapper in the header",
            # An unlisted tag is somebody pasting markup, not the harness.
            "<RecceActionProvider> renders twice, find out why",
        ):
            with self.subTest(text=text):
                self.assertFalse(records.injected_prompt(text, "claude"))


class InstructionLineTest(unittest.TestCase):
    """The line-2 primitives: what counts as a continuation, and what publishes."""

    def test_a_short_acknowledgement_is_a_continuation_and_a_short_order_is_not(self) -> None:
        # The whole reason this is a word count rather than a character count.
        # "create a pr" is 11 characters and states work; "yes, go ahead and do
        # that" is 27 and states none. A character threshold picks the wrong one
        # of those two, which is how a "<40 chars" rule came to replace 402 good
        # lines to fix 81 bad ones.
        for text in ("proceed", "continue", "yes, do that", "1 and 2", "sure, proceed"):
            with self.subTest(text=text):
                self.assertTrue(records.bare_continuation(text))
        for text in (
            "resolve the blocker and create the pr",
            "Fix the flaky Windows test and report what moved",
        ):
            with self.subTest(text=text):
                self.assertFalse(records.bare_continuation(text))

    def test_a_reading_with_no_label_is_never_published(self) -> None:
        # The label is what makes a second-hand or stale line survivable, so an
        # unlabelled one is not a degraded reading — it is a claim the runtime
        # cannot support, and there is no branch that may emit one.
        self.assertIsNone(records.instruction_line("", "real text", 100.0))
        self.assertIsNone(records.instruction_line("agent", "", 100.0))
        self.assertIsNone(records.instruction_line("agent", None, 100.0))
        self.assertIsNone(records.instruction_line("agent", "   ", 100.0))

    def test_the_text_is_bounded_and_scrubbed_like_every_other_vendor_string(self) -> None:
        # `last_prompt` beside it is published raw at the collector; this field
        # is not, and the difference is deliberate. The value is untrusted
        # transcript text on its way to the DOM.
        hostile = "drop\u202ethe bidi\x07 override " + "x" * 400
        line = records.instruction_line("earlier", hostile, 12.0)

        assert line is not None
        # Cap plus one, not the cap: the ellipsis `clip` appends sits one past
        # the width it cut to, and scrubbing at the cap takes it back off. This
        # is the bound, not the rendered width \u2014 every real caller hands this
        # already-clipped text, so one character of headroom is what keeps the
        # truncation marked. See the docstring, and line 1's identical `+ 1`.
        self.assertEqual(records.INSTRUCTION_CAP_CHARS + 1, len(line["text"]))
        self.assertNotIn("\u202e", line["text"])
        self.assertNotIn("\x07", line["text"])
        self.assertEqual("earlier", line["label"])
        self.assertEqual(12.0, line["at"])

    def test_a_clipped_line_keeps_the_ellipsis_that_marks_it_clipped(self) -> None:
        # 29 of 1,906 published Claude lines ended in an unmarked mid-token cut,
        # because `clip` appends `\u2026` AFTER cutting to the cap and the scrub then
        # trimmed exactly that character off. A cut with no marker reads as the
        # operator having written a truncated sentence.
        clipped = "x" * records.INSTRUCTION_CAP_CHARS + "\u2026"
        line = records.instruction_line("asked", clipped, 12.0)

        assert line is not None
        self.assertTrue(line["text"].endswith("\u2026"), line["text"][-20:])

    def test_an_unusable_stamp_is_published_as_zero_rather_than_as_now(self) -> None:
        # The page renders an age from this. A missing stamp read as the current
        # time would label a two-hour-old line "earlier, 0s", which is the one
        # reading the label exists to prevent.
        for stamp in (None, 0, -5.0):
            with self.subTest(stamp=stamp):
                line = records.instruction_line("agent", "text", stamp)
                assert line is not None
                self.assertEqual(0, line["at"])


if __name__ == "__main__":
    unittest.main()
