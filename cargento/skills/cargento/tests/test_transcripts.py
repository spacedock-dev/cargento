from __future__ import annotations

import dataclasses
import json
import random
import tempfile
import threading
import time
import unicodedata
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

from cargento_runtime import io as runtime_io
from cargento_runtime import records

from .support import (
    LegacyDashboardTestCase,
    dashboard,
    make_config,
)


class CargentoServerTest(LegacyDashboardTestCase):
    def test_metadata_cache_is_safe_under_concurrent_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meta.jsonl"
            path.write_text(json.dumps({"value": "ok"}) + "\n")
            parsed = threading.Event()
            parse_lock = threading.Lock()
            parse_count = 0

            def parse(value: dict[str, Any]) -> dict[str, Any]:
                nonlocal parse_count
                with parse_lock:
                    parse_count += 1
                    wait_for_pair = parse_count <= 2
                    if parse_count == 2:
                        parsed.set()
                if wait_for_pair and not parsed.wait(timeout=5):
                    raise AssertionError("concurrent readers did not reach the metadata parser")
                return {"value": value.get("value")}

            def read() -> Any:
                return dashboard.first_line_meta(str(path), parse)

            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(lambda _: read(), range(100)))

        self.assertTrue(all(result == {"value": "ok"} for result in results))
        self.assertEqual(1, len(dashboard._meta_cache))

    def test_read_tail_keeps_first_record_when_window_starts_on_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_bytes(b"aaaa\nbbbb\ncccc\n")  # 15 bytes

            # Window of 10 starts right after the newline at offset 4:
            # "bbbb" is a complete record and must be kept.
            aligned = runtime_io.read_tail(make_config(tail_bytes=10), str(path))
            # Window of 9 starts mid-"bbbb": the partial line must drop.
            misaligned = runtime_io.read_tail(make_config(tail_bytes=9), str(path))

        self.assertEqual(["bbbb", "cccc", ""], aligned)
        self.assertEqual(["cccc", ""], misaligned)


class BoundedReadTest(unittest.TestCase):
    def test_first_json_record_honors_before_at_and_after_cap(self) -> None:
        payload = b'{"x":1}'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.jsonl"
            path.write_bytes(payload)

            before = runtime_io.read_first_json(
                make_config(first_line_json_cap_bytes=len(payload) - 1),
                str(path),
            )
            at = runtime_io.read_first_json(
                make_config(first_line_json_cap_bytes=len(payload)),
                str(path),
            )
            after = runtime_io.read_first_json(
                make_config(first_line_json_cap_bytes=len(payload) + 1),
                str(path),
            )

        self.assertEqual({}, before)
        self.assertEqual({"x": 1}, at)
        self.assertEqual({"x": 1}, after)

    def test_first_json_record_rejects_non_objects_and_bad_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.jsonl"
            for raw in (b"[1,2]", b"{bad", b"\xff"):
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    self.assertEqual(
                        {},
                        runtime_io.read_first_json(
                            make_config(first_line_json_cap_bytes=64),
                            str(path),
                        ),
                    )
            self.assertEqual(
                {},
                runtime_io.read_first_json(
                    make_config(first_line_json_cap_bytes=64),
                    str(Path(tmp) / "missing"),
                ),
            )

    def test_prefix_bytes_returns_only_the_requested_total_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefix"
            path.write_bytes(b"abcdef")
            self.assertEqual(b"", runtime_io.read_prefix_bytes(str(path), max_bytes=0))
            self.assertEqual(b"abc", runtime_io.read_prefix_bytes(str(path), max_bytes=3))
            self.assertEqual(b"abcdef", runtime_io.read_prefix_bytes(str(path), max_bytes=6))
            self.assertEqual(b"abcdef", runtime_io.read_prefix_bytes(str(path), max_bytes=7))

    def test_bounded_lines_use_independent_per_call_caps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lines"
            path.write_bytes(b"abc\n12345\nz\n")
            self.assertEqual(
                [],
                list(
                    runtime_io.iter_bounded_text_lines(
                        str(path),
                        max_lines=0,
                        per_line_bytes=4,
                    )
                ),
            )
            self.assertEqual(
                ["abc\n", "1234"],
                list(
                    runtime_io.iter_bounded_text_lines(
                        str(path),
                        max_lines=2,
                        per_line_bytes=4,
                    )
                ),
            )
            self.assertEqual(
                ["abc\n", "1234", "5\n", "z\n"],
                list(
                    runtime_io.iter_bounded_text_lines(
                        str(path),
                        max_lines=4,
                        per_line_bytes=4,
                    )
                ),
            )

    def test_bounded_lines_replace_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lines"
            path.write_bytes(b"a\xff\n")
            self.assertEqual(
                ["a\ufffd\n"],
                list(
                    runtime_io.iter_bounded_text_lines(
                        str(path),
                        max_lines=1,
                        per_line_bytes=8,
                    )
                ),
            )


class ReverseLinesTest(unittest.TestCase):
    """Replaces the reverse mmap scans. A mapped region whose file is truncated
    underneath it raises SIGBUS on POSIX (uncatchable) and blocks the writer's
    truncate on Windows; these are transcripts a live agent may rotate."""

    def setUp(self) -> None:
        self.config = make_config()

    def write(self, tmp: str, text: str) -> str:
        path = Path(tmp) / "t.jsonl"
        # write_bytes, not write_text: Windows text mode translates "\n" to
        # "\r\n", and these tests assert on exact byte boundaries. Harnesses
        # write LF transcripts, which is what this reproduces.
        path.write_bytes(text.encode())
        return str(path)

    def read_back(self, path: str, **kwargs: Any) -> list[str]:
        config = kwargs.pop("config", None) or self.config
        return [raw.decode() for raw in runtime_io.reverse_lines(config, path, **kwargs)]

    def test_yields_lines_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a\nb\nc\n")
            self.assertEqual(["", "c", "b", "a"], self.read_back(path))

    def test_file_without_a_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a\nb\nc")
            self.assertEqual(["c", "b", "a"], self.read_back(path))

    def test_empty_and_missing_files_yield_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([], self.read_back(self.write(tmp, "")))
            self.assertEqual([], self.read_back(str(Path(tmp) / "absent.jsonl")))

    def test_lines_spanning_chunk_boundaries_are_reassembled(self) -> None:
        # The whole risk of chunked reverse reading: a record split across two
        # reads must come back intact. Forced with a chunk far smaller than the
        # lines, at several sizes so no single alignment can hide a bug.
        lines = [f"{i:04d}-" + "x" * (i % 37) for i in range(200)]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "\n".join(lines) + "\n")
            for chunk in (1, 2, 3, 7, 64, 1000):
                with self.subTest(chunk=chunk):
                    got = [
                        line
                        for line in self.read_back(
                            path,
                            config=dataclasses.replace(
                                self.config,
                                reverse_chunk_bytes=chunk,
                            ),
                        )
                        if line
                    ]
                    self.assertEqual(list(reversed(lines)), got)

    def test_contains_filter_never_hides_a_matching_line(self) -> None:
        # The filter tests whole chunks, so a match split across a chunk
        # boundary is exactly what could go missing. Sweep every alignment.
        with tempfile.TemporaryDirectory() as tmp:
            for offset in range(40):
                text = "x" * offset + "\nfiller\nNEEDLE-here\nfiller\n"
                path = self.write(tmp, text)
                for chunk in (1, 2, 3, 5, 8, 13):
                    with self.subTest(offset=offset, chunk=chunk):
                        got = [
                            raw.decode()
                            for raw in runtime_io.reverse_lines(
                                dataclasses.replace(
                                    self.config,
                                    reverse_chunk_bytes=chunk,
                                ),
                                path,
                                contains=b"NEEDLE",
                            )
                            if b"NEEDLE" in raw
                        ]
                        self.assertEqual(["NEEDLE-here"], got)

    def test_contains_filter_matches_the_unfiltered_walk(self) -> None:
        lines = [f"rec{i}" + ("-TARGET" if i % 97 == 0 else "") for i in range(500)]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "\n".join(lines) + "\n")
            for chunk in (4, 16, 256):
                with self.subTest(chunk=chunk):
                    config = dataclasses.replace(self.config, reverse_chunk_bytes=chunk)
                    unfiltered = [
                        raw for raw in runtime_io.reverse_lines(config, path) if b"TARGET" in raw
                    ]
                    filtered = [
                        raw
                        for raw in runtime_io.reverse_lines(config, path, contains=b"TARGET")
                        if b"TARGET" in raw
                    ]
                    self.assertEqual(unfiltered, filtered)
                    self.assertEqual(6, len(filtered))

    def test_matches_a_trivial_reference_across_the_input_space(self) -> None:
        # The strongest guarantee available: compare against slice/split/reverse
        # over a generated corpus, at every chunk size, end_pos and max_bytes.
        # This is what caught the list-accumulation rewrite being correct.
        def reference(data: bytes, stop: int, max_bytes: int | None) -> list[bytes]:
            floor = 0 if max_bytes is None else max(0, stop - max_bytes)
            window = data[floor:stop] if floor else data[:stop]
            out = list(reversed(window.split(b"\n")))
            if floor:
                return out[:-1]  # oldest is a fragment when the walk is bounded
            return [] if stop == 0 else out

        rng = random.Random(11)
        alphabet = [b"a", b"bb", b"", b"NEEDLE", b"xNEEDLEy", b"c" * 40]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f"
            for _ in range(60):
                data = b"\n".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
                if rng.random() < 0.5:
                    data += b"\n"
                path.write_bytes(data)
                size = len(data)
                for stop in {size, max(0, size // 2), max(0, size - 1), 0}:
                    for max_bytes in (None, 3, 10):
                        for chunk in (1, 2, 5, 4096):
                            got = list(
                                runtime_io.reverse_lines(
                                    dataclasses.replace(
                                        self.config,
                                        reverse_chunk_bytes=chunk,
                                    ),
                                    str(path),
                                    stop,
                                    max_bytes=max_bytes,
                                )
                            )
                            if got != reference(data, stop, max_bytes):
                                self.fail(
                                    f"data={data!r} stop={stop} max_bytes={max_bytes} "
                                    f"chunk={chunk}: {got} != {reference(data, stop, max_bytes)}"
                                )

    def test_the_contains_filter_never_hides_a_line(self) -> None:
        # The filter tests each chunk and the completed line rather than a
        # joined buffer, so a match spanning chunks is the risk.
        rng = random.Random(12)
        alphabet = [b"a", b"bb", b"", b"NEEDLE", b"xNEEDLEy", b"c" * 40]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f"
            for _ in range(60):
                data = b"\n".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))
                path.write_bytes(data + rng.choice([b"\n", b""]))
                for chunk in (1, 2, 3, 5, 17, 4096):
                    config = dataclasses.replace(self.config, reverse_chunk_bytes=chunk)
                    plain = [
                        raw
                        for raw in runtime_io.reverse_lines(config, str(path))
                        if b"NEEDLE" in raw
                    ]
                    filtered = [
                        raw
                        for raw in runtime_io.reverse_lines(
                            config,
                            str(path),
                            contains=b"NEEDLE",
                        )
                        if b"NEEDLE" in raw
                    ]
                    self.assertEqual(plain, filtered, f"chunk={chunk} data={data!r}")

    def test_crlf_transcripts_still_parse(self) -> None:
        # Harnesses write LF, but a transcript can pick up CRLF by being copied
        # through a Windows tool. Lines split on "\n" keep a trailing "\r";
        # that must not change what the readers extract.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "crlf.jsonl"
            path.write_bytes(
                b"\r\n".join(
                    [
                        json.dumps({"type": "ai-title", "aiTitle": "CRLF title"}).encode(),
                        json.dumps({"type": "user", "uuid": "u-crlf"}).encode(),
                    ]
                )
                + b"\r\n"
            )
            self.assertEqual("CRLF title", dashboard.claude_session_title(str(path)))
            self.assertEqual("u-crlf", dashboard.claude_last_user_event(str(path)))

    def test_end_pos_limits_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "aaa\nbbb\nccc\n")
            self.assertEqual(["", "bbb", "aaa"], self.read_back(path, end_pos=8))

    def test_max_bytes_drops_the_oldest_partial_line(self) -> None:
        # Stopping mid-file means the oldest line reached is probably a
        # fragment, so it is discarded rather than parsed as a record.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "aaaa\nbbbb\ncccc\n")
            self.assertEqual(["", "cccc"], self.read_back(path, max_bytes=6))

    def test_a_file_truncated_mid_scan_stops_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "\n".join(f"line{i}" for i in range(500)) + "\n")
            walker = runtime_io.reverse_lines(
                dataclasses.replace(self.config, reverse_chunk_bytes=16),
                path,
            )
            next(walker)
            Path(path).write_bytes(b"")  # writer rotates the transcript
            remaining = list(walker)  # must not raise
        self.assertIsInstance(remaining, list)

    def test_a_line_ending_exactly_at_end_pos_is_yielded(self) -> None:
        # Where the reverse and forward halves of scan_turns meet. The forward
        # pass resumes at the same offset, and a forward read starting on a
        # newline never sees the record that newline terminates — so the
        # reverse pass has to yield it. The previous mmap reader searched
        # rfind("\n", 0, end_pos), which excluded that byte and dropped the
        # record from both halves.
        #
        # Note this does not make the split lossless in general: a record
        # straddling the split offset is still missed by both halves. That is a
        # pre-existing limit of the bounded scan, unchanged by this PR.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "first\nsecond\nthird\n")
            split = len("first\nsecond")  # the newline terminating "second"
            self.assertEqual(b"\n", Path(path).read_bytes()[split : split + 1])
            got = [
                raw.decode() for raw in runtime_io.reverse_lines(self.config, path, split) if raw
            ]
        self.assertEqual(["second", "first"], got)

    def test_title_and_user_event_still_scan_the_whole_file(self) -> None:
        # Both readers look past the bounded activity tail, which is why they
        # walk backward at all rather than reusing read_tail().
        filler = [json.dumps({"type": "assistant", "message": {}}) for _ in range(400)]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(
                tmp,
                "\n".join(
                    [
                        json.dumps({"type": "ai-title", "aiTitle": "Old title"}),
                        json.dumps({"type": "user", "uuid": "u-old"}),
                        *filler,
                        json.dumps({"type": "ai-title", "aiTitle": "Newest title"}),
                        json.dumps({"type": "user", "uuid": "u-new"}),
                        *filler,
                    ]
                )
                + "\n",
            )
            with mock.patch.object(dashboard, "REVERSE_CHUNK_BYTES", 128):
                self.assertEqual("Newest title", dashboard.claude_session_title(path))
                self.assertEqual("u-new", dashboard.claude_last_user_event(path))


class PromptTitleTest(unittest.TestCase):
    """A session with no generated title falls back to its first prompt, and
    the harness wraps some prompts in markup. Measured over 248 real
    transcripts, 138 titles rendered as raw tags before this."""

    def test_a_slash_command_reads_as_the_command(self) -> None:
        prompt = (
            "<command-name>/plugin</command-name>\n"
            "            <command-message>plugin</command-message>\n"
            "            <command-args></command-args>"
        )

        self.assertEqual("/plugin", dashboard.prompt_title(prompt))

    def test_a_command_keeps_its_arguments(self) -> None:
        prompt = (
            "<command-message>recce-dev:claude-code-review</command-message>\n"
            "<command-name>/recce-dev:claude-code-review</command-name>\n"
            "<command-args>https://example.test/pr/1 and fix the findings</command-args>"
        )

        self.assertEqual(
            "/recce-dev:claude-code-review https://example.test/pr/1 and fix the findings",
            dashboard.prompt_title(prompt),
        )

    def test_a_wrapped_payload_shows_its_content_not_the_envelope(self) -> None:
        """The single most common case in the wild: 113 of the 138."""
        prompt = (
            '<teammate-message teammate_id="team-lead">\n'
            "Read the dispatch file and start the review\n"
            "</teammate-message>"
        )

        self.assertEqual(
            "Read the dispatch file and start the review", dashboard.prompt_title(prompt)
        )

    def test_an_ordinary_prompt_is_left_alone(self) -> None:
        self.assertEqual(
            "Fix the flaky Windows test",
            dashboard.prompt_title("Fix the flaky Windows test\nsecond line ignored"),
        )

    def test_markup_with_no_content_yields_nothing(self) -> None:
        # Better to fall through to another signal than to title a card "<>".
        for empty in ("<local-command-stdout></local-command-stdout>", "<a></a>", "   ", ""):
            with self.subTest(prompt=empty):
                self.assertIsNone(dashboard.prompt_title(empty))

    def test_the_title_is_bounded(self) -> None:
        self.assertLessEqual(len(dashboard.prompt_title("x " * 400, limit=10) or ""), 11)

    def test_absolute_paths_collapse_to_their_basename(self) -> None:
        self.assertEqual(
            "Round 3 review of PR #268 (repo pendulum-of-despair)",
            dashboard.prompt_title(
                "Round 3 review of PR #268 (repo /Users/jane/repos/pendulum-of-despair)"
            ),
        )

    def test_urls_and_relative_paths_survive_whole(self) -> None:
        """The repo and PR number in a link are the informative part, and a
        relative path names a file the reader can actually find."""
        for text in (
            "Review https://github.com/spacedock-dev/bridge/pull/77 fully",
            "In bridge, read internal/server/server.go and its siblings",
            "Research how Goose works (github.com/block/goose)",
        ):
            with self.subTest(text=text):
                self.assertEqual(text, dashboard.prompt_title(text))

    def test_truncation_lands_on_a_word_boundary(self) -> None:
        prompt = "Take your time and tell all subagents the same"
        title = dashboard.prompt_title(prompt, limit=30)

        assert title is not None
        self.assertTrue(title.endswith("…"), title)
        self.assertFalse(title.rstrip("…").endswith(" "), title)
        # A word was not cut in half. Compare against the prompt's WORDS: against
        # the bare string this passes on "su", a substring of "subagents", so it
        # could not fail for the mistake it exists to catch.
        self.assertIn(title.rstrip("…").split()[-1], prompt.split())

    def test_short_slashy_text_is_not_treated_as_a_path(self) -> None:
        """Only long paths eat the title budget, and short slash-runs are
        usually not paths at all. `^/api/v1/users$` collapsed to `^users$`
        before the length floor existed."""
        for text in (
            "Match the regex ^/api/v1/users$ in the router",
            "cd ~/repos/cargento && make test",
            "Serve /a/b from the CDN",
        ):
            with self.subTest(text=text):
                self.assertEqual(text, dashboard.prompt_title(text))

    def test_a_clip_does_not_end_on_an_orphaned_combining_mark(self) -> None:
        # The base character it belongs to was cut away, so it would render
        # against the ellipsis instead.
        decomposed = unicodedata.normalize("NFD", "é") * 60
        orphaned = [
            limit
            for limit in range(3, 60)
            if (kept := dashboard.clip(decomposed, limit).rstrip("…"))
            and unicodedata.combining(kept[-1])
        ]

        self.assertEqual([], orphaned)

    def test_a_hard_cut_does_not_leave_dangling_punctuation(self) -> None:
        # One long token has no boundary to fall back to, and ".…" reads as a
        # typo rather than as truncation.
        self.assertEqual("aaaa…", dashboard.clip("aaaa.bbbbbbbbbbbb", limit=5))

    def test_the_path_floor_is_a_boundary_not_a_vibe(self) -> None:
        # Mutation-checked: `<` vs `<=` on SD_MIN_COLLAPSED_PATH survived the
        # suite, so the exact cutover is pinned here.
        def path_of_length(total: int) -> str:
            return "/" + "a" * (total - 4) + "/bc"  # 1 + (total - 4) + 3

        floor = dashboard.SD_MIN_COLLAPSED_PATH
        just_under, just_over = path_of_length(floor - 1), path_of_length(floor)

        self.assertEqual((floor - 1, floor), (len(just_under), len(just_over)))
        self.assertEqual(just_under, dashboard.shorten_paths(just_under), "collapsed below floor")
        self.assertEqual("bc", dashboard.shorten_paths(just_over), "not collapsed at floor")


class MalformedRecordTest(unittest.TestCase):
    """Every harness payload is untyped JSON read off disk. `x.get("k") or {}`
    is not a guard: any truthy non-dict passes the `or` and the next .get()
    raises, killing the collector for that refresh."""

    HOSTILE: ClassVar[list[Any]] = [5, "str", [1, 2], {"k": "v"}, None, True]
    PLACEHOLDER = "__HOSTILE__"
    # One record per harness that the analyzer really does parse, used to prove
    # a hostile neighbour did not leave it unable to read anything else.
    WELL_FORMED: ClassVar[dict[str, dict[str, Any]]] = {
        "claude": {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"content": [{"type": "text", "text": "hello"}]},
        },
        "codex": {"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}},
        "gemini": {"type": "user", "content": "hello"},
        "copilot": {"type": "user.message", "data": {"content": "hello"}},
        "droid": {"type": "user", "message": {"content": "hello"}},
    }

    def substitute(self, template: Any, value: Any) -> Any:
        if template == self.PLACEHOLDER:
            return value
        if isinstance(template, dict):
            return {k: self.substitute(v, value) for k, v in template.items()}
        if isinstance(template, list):
            return [self.substitute(v, value) for v in template]
        return template

    def templates(self) -> list[tuple[str, Any, list[dict[str, Any]]]]:
        hostile = self.PLACEHOLDER
        return [
            (
                "claude",
                dashboard.analyze_transcript,
                [
                    {"type": "assistant", "message": {"usage": hostile, "content": hostile}},
                    {"type": "user", "message": {"content": hostile}},
                    {"type": "assistant", "message": hostile},
                    {"type": "last-prompt", "lastPrompt": hostile},
                ],
            ),
            (
                "codex",
                dashboard.analyze_codex_transcript,
                [
                    {"type": "event_msg", "payload": hostile},
                    {"type": "event_msg", "payload": {"type": "token_count", "info": hostile}},
                    {
                        "type": "event_msg",
                        "payload": {"type": "token_count", "info": {"last_token_usage": hostile}},
                    },
                    {"type": "event_msg", "payload": {"type": "user_message", "message": hostile}},
                    {
                        "type": "response_item",
                        "payload": {"type": "function_call", "name": hostile},
                    },
                ],
            ),
            (
                "gemini",
                dashboard.analyze_gemini_transcript,
                [
                    {"type": "gemini", "toolCalls": hostile, "tokens": hostile},
                    {"type": "user", "content": hostile},
                    {"$set": hostile},
                    {"$set": {"messages": hostile}},
                ],
            ),
            (
                "copilot",
                dashboard.analyze_copilot_events,
                [
                    {"type": "session.start", "data": hostile},
                    {"type": "session.start", "data": {"context": hostile}},
                    {"type": "user.message", "data": hostile},
                    {"type": "subagent.started", "data": hostile},
                ],
            ),
            (
                "droid",
                dashboard.analyze_droid_transcript,
                [
                    {"type": "message", "message": hostile},
                    {"type": "message", "message": {"role": "user", "content": hostile}},
                    {"type": "message", "message": {"role": "assistant", "content": hostile}},
                ],
            ),
        ]

    def test_a_hostile_record_neither_raises_nor_poisons_the_analyzer(self) -> None:
        """The contract is that one bad record does not take a collector
        offline, so surviving the record is only half of it: the analyzer must
        still parse the good records around it. "Did not raise" would also pass
        an analyzer that bailed out and returned nothing from then on.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            for harness, analyzer, templates in self.templates():
                for template in templates:
                    for value in self.HOSTILE:
                        record = self.substitute(template, value)
                        with self.subTest(harness=harness, record=json.dumps(record)[:70]):
                            path.write_text(json.dumps(record) + "\n")
                            result = analyzer(str(path))

                            self.assertIsInstance(
                                result, dict, "a collector cannot use a non-dict result"
                            )
                            # The same analyzer, on the same file, with the bad
                            # record followed by a well-formed one.
                            path.write_text(
                                json.dumps(record) + "\n" + json.dumps(self.WELL_FORMED[harness])
                            )

                            self.assertIsInstance(analyzer(str(path)), dict)

    def test_typed_accessors(self) -> None:
        not_dicts: list[Any] = [5, "str", [1, 2], None, True]
        for value in not_dicts:
            self.assertEqual({}, records.as_dict(value))
            self.assertEqual({}, records.message_dict({"message": value}))
        self.assertEqual({"a": 1}, records.as_dict({"a": 1}))
        self.assertEqual({"a": 1}, records.message_dict({"message": {"a": 1}}))
        self.assertEqual({}, records.message_dict("not-a-record"))
        not_lists: list[Any] = [5, "str", {"k": 1}, None, True]
        for value in not_lists:
            self.assertEqual([], records.as_list(value))
        self.assertEqual([1, 2], records.as_list([1, 2]))

    def test_safe_text_replaces_controls_and_truncates(self) -> None:
        self.assertEqual("a b c", records.safe_text("a\x00b\nc", 10))
        self.assertEqual("abc", records.safe_text("abcdef", 3))


class ReviewFixTest(unittest.TestCase):
    """Regressions found by the adversarial review passes on PR #7."""

    NOW = 1_700_000_000.0

    def test_reverse_lines_stays_linear_on_one_long_record(self) -> None:
        # chunk + carry per chunk made this quadratic: a 64 MB single-line
        # transcript took 0.9s, and large tool results do produce such records.
        #
        # Best-of-three per size, because a single sample is what made this
        # flaky on the Windows runner: one slow read reported a 9.0x ratio for
        # 4x the bytes on code that really scales at ~4x. The minimum is the
        # least contaminated estimate, and a quadratic regression cannot hide
        # in it.
        #
        # 16/64 MB rather than 4/16 so the measured time clears the floor below
        # on every runner. The floor stops a fast machine's near-zero baseline
        # from collapsing the budget into the noise, but it also caps
        # sensitivity: the comparison only fails a quadratic regression while
        # timings[0] > floor / 2, so the floor has to stay well under a real
        # measurement rather than replace it.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "long.jsonl"
            timings = []
            for megabytes in (16, 64):
                path.write_bytes(b"x" * (megabytes * 1024 * 1024))
                samples = []
                for _ in range(3):
                    start = time.perf_counter()
                    list(runtime_io.reverse_lines(make_config(), str(path)))
                    samples.append(time.perf_counter() - start)
                timings.append(min(samples))
        # Quadratic would be ~16x for 4x the bytes. Linear is ~4x; allow 8x for
        # a loaded CI runner while still failing a quadratic regression.
        self.assertLess(timings[1], max(timings[0], 0.01) * 8, f"non-linear: {timings}")
