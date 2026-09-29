"""DRC-4725: shell effects and named secrets at the published/press boundary."""

from __future__ import annotations

import base64
import shlex

from .test_check_line_parser import CheckLineTestCase, project_context, reading


class HeredocExpansionEffectsTest(CheckLineTestCase):
    def test_executable_body_substitutions_age_the_prior_pass_without_publishing_the_body(
        self,
    ) -> None:
        for later in (
            "cat <<EOF\n$(rm -rf zzsentinel7)\nEOF",
            "cat <<EOF\n`rm -rf zzsentinel7`\nEOF",
            "cat <<EOF\n'$(rm -rf zzsentinel7)'\nEOF",
            "cat <<-EOF\n\t$(rm -rf zzsentinel7)\n\tEOF",
            "cat <<A <<'B'\n$(rm zzsentinel7)\nA\nliteral\nB",
            "cat <<'A' <<B\nliteral\nA\n$(rm zzsentinel7)\nB",
            "cat <<EOF\n${X:-$(rm zzsentinel7)}\nEOF",
            "cat <<EOF\n$(echo $(rm zzsentinel7))\nEOF",
            "cat <<EOF\n$\\\n(rm zzsentinel7)\nEOF",
            "cat <<EOF\n\\\\\n$(rm zzsentinel7)\nEOF",
            "bash -c " + shlex.quote("cat <<EOF\n$(rm zzsentinel7)\nEOF"),
        ):
            with self.subTest(later=later[:24]):
                self.fresh()
                self.session.bash("pytest", "1 passed", is_error=False)
                self.session.bash(later, "", is_error=False)
                text, checks, _scan = self.published()
                self.assertIs(True, checks[0]["changed_after"])
                self.assertNotIn("zzsentinel7", text)

    def test_a_continued_unquoted_body_line_cannot_expose_its_literal_commands_as_checks(
        self,
    ) -> None:
        self.session.bash(
            "cat <<EOF\nprefix\\\nEOF\npytest --password EXAMPLEsecrecy987\nEOF", "", is_error=False
        )
        text, checks, _scan = self.published()
        self.assertEqual([], checks)
        self.assertNotIn("pytest", text)

    def test_the_existing_expansion_depth_bound_also_applies_through_heredoc_bodies(self) -> None:
        body = "$(git rev-parse HEAD)"
        for level in range(33):
            body = f"$(cat <<E{level}\n{body}\nE{level}\n)"
        self.session.bash('pytest "' + body + '"', "1 passed", is_error=False)
        _text, checks, scan = self.published()
        self.assertEqual([], checks)
        self.assertEqual(1, scan["not_run"])

    def test_an_executable_body_after_the_check_in_the_same_call_ages_it(self) -> None:
        self.session.bash("pytest && cat <<EOF\n$(rm zzsentinel7)\nEOF", "1 passed", is_error=False)
        text, checks, _scan = self.published()
        self.assertIs(True, checks[0]["changed_after"])
        self.assertNotIn("zzsentinel7", text)

    def test_literal_and_read_only_bodies_do_not_age_a_pass(self) -> None:
        for later in (
            "cat <<'EOF'\n$(rm zzsentinel7)\nEOF",
            'cat <<"EOF"\n$(rm zzsentinel7)\nEOF',
            "cat <<E\\OF\n$(rm zzsentinel7)\nEOF",
            "cat <<EOF\n\\$(rm zzsentinel7)\nEOF",
            "cat <<EOF\n$(git rev-parse HEAD)\nEOF",
            "cat <<EOF\nrm zzsentinel7\nEOF",
            "cat <<'$(rm zzsentinel7)'\nliteral\n$(rm zzsentinel7)",
        ):
            with self.subTest(later=later[:24]):
                self.fresh()
                self.session.bash("pytest", "1 passed", is_error=False)
                self.session.bash(later, "", is_error=False)
                text, checks, _scan = self.published()
                self.assertIs(False, checks[0]["changed_after"])
                self.assertNotIn("zzsentinel7", text)


class InputRedirectSummaryTest(CheckLineTestCase):
    def test_a_pipeline_reader_with_its_own_input_cannot_attribute_that_file_summary(self) -> None:
        self.session.bash("pytest | tail -2 <<EOF\n7 passed\nEOF", "7 passed", is_error=False)
        self.assertEqual("not-recorded", self.only_check()["result"])


class SafeCommonSubstitutionFormsTest(CheckLineTestCase):
    def test_safe_common_reads_preserve_the_pass(self) -> None:
        for body in (
            "git rev-parse HEAD",
            "git merge-base HEAD main",
            "date",
            "date +%s",
            "date -u +%s",
            "gh api repos/example/repo",
            "gh api --method GET repos/example/repo",
            "gh api repos/example/repo -XGET --paginate --jq .name",
        ):
            with self.subTest(body=body):
                self.fresh()
                self.session.bash("pytest", "1 passed", is_error=False)
                self.session.bash(f"echo $({body})", "", is_error=False)
                self.assertIs(False, self.only_check()["changed_after"])

    def test_writing_or_unknown_forms_still_age_the_pass(self) -> None:
        for body in (
            "date -s tomorrow",
            "date --set=tomorrow",
            "date 09291200",
            "date -f %Y 2026",
            "date -j -f %Y 2026",
            "gh api repos/example/repo -X POST",
            "gh api repos/example/repo --method=PATCH",
            "gh api repos/example/repo -f body=x",
            "gh api repos/example/repo --raw-field=body=x",
            "gh api repos/example/repo -Fbody=x",
            "gh api repos/example/repo --input body.json",
            "gh api graphql -f query=mutation",
            "gh api repos/example/repo --cache 1h",
            "gh api repos/example/repo -H 'X-HTTP-Method-Override: POST'",
            "git rev-parse HEAD > output",
            "git merge-base HEAD main $(rm output)",
        ):
            with self.subTest(body=body):
                self.fresh()
                self.session.bash("pytest", "1 passed", is_error=False)
                self.session.bash(f"echo $({body})", "", is_error=False)
                self.assertIs(True, self.only_check()["changed_after"])


class RedirectOperatorIdentityTest(CheckLineTestCase):
    def test_a_literal_fd_shaped_path_ages_the_pass_and_is_listed_when_the_check_writes_it(
        self,
    ) -> None:
        for target in ("'&1'", '"&1"', "\\&1"):
            with self.subTest(target=target):
                self.fresh()
                self.session.bash("pytest", "1 passed", is_error=False)
                self.session.bash(f"ls > {target}", "", is_error=False)
                self.assertIs(True, self.only_check()["changed_after"])
                self.fresh()
                self.session.bash(f"pytest > {target}", "1 passed", is_error=False)
                events, _scan = self.read()
                self.assertEqual(["&1"], [e["title"] for e in events if e["subject"] == "write"])

    def test_descriptor_duplication_and_the_existing_named_dev_null_shape_are_harmless(
        self,
    ) -> None:
        for later in ("ls >&1", "ls 2>&1", "ls {fd}>/dev/null", "ls {fd}>&-"):
            with self.subTest(later=later):
                self.fresh()
                self.session.bash("pytest", "1 passed", is_error=False)
                self.session.bash(later, "", is_error=False)
                self.assertIs(False, self.only_check()["changed_after"])


class CallWideNamedTailMaskingTest(CheckLineTestCase):
    def test_all_segments_assignments_and_wrappers_mask_their_named_values_in_prompt_tails(
        self,
    ) -> None:
        placeholder = "EXAMPLEsecrecy987"
        for command in (
            f"echo --password {placeholder}; pytest",
            f"PASSWORD={placeholder} pytest",
            f"env PASSWORD={placeholder} pytest",
            f"pytest; echo --token={placeholder}",
            "bash -c " + shlex.quote(f"PASSWORD={placeholder} pytest"),
            f"PASSWORD={placeholder} bash -c 'pytest'",
        ):
            with self.subTest(command=command[:20]):
                self.fresh()
                self.session.bash(command, f"+ PASSWORD={placeholder}\n1 passed", is_error=False)
                text, _checks, _scan = self.published()
                self.assertTrue(any(row.get("tail") for row in self.ledger))
                self.assertNotIn(placeholder, text)

    def test_executed_substitution_bodies_also_supply_named_values_to_the_tail_scrub(self) -> None:
        placeholder = "EXAMPLEsecrecy987"
        for command in (
            f'pytest "$(echo --password {placeholder})"',
            f"pytest; cat <<EOF\n$(echo --password {placeholder})\nEOF",
            f"pytest; cat <<EOF\n$(echo $(echo --token={placeholder}))\nEOF",
        ):
            with self.subTest(command=command[:20]):
                self.fresh()
                self.session.bash(
                    command, f"+ echo --password {placeholder}\n1 passed", is_error=False
                )
                text, _checks, _scan = self.published()
                self.assertTrue(any(row.get("tail") for row in self.ledger))
                self.assertNotIn(placeholder, text)

    def test_apostrophe_xtrace_spellings_hide_the_whole_value(self) -> None:
        placeholder = "EXAMPLEpw'withQuote"
        for echoed in (shlex.quote(placeholder), "'EXAMPLEpw'\\''withQuote'", placeholder):
            with self.subTest(quoted=echoed != placeholder):
                self.fresh()
                self.session.bash(
                    f"pytest --password {shlex.quote(placeholder)}",
                    f"+ pytest --password {echoed}\n1 passed",
                    is_error=False,
                )
                text, _checks, _scan = self.published()
                self.assertNotIn("EXAMPLEpw", text)
                self.assertNotIn("withQuote", text)

    def test_a_masked_word_never_rewrites_an_unrelated_filename_or_identifier(self) -> None:
        self.session.bash(
            "pytest --password test",
            "test_a.py contest test-file.py src/test\nvalue=test, test\n1 passed",
            is_error=False,
        )
        _text, _checks, _scan = self.published()
        tail = next(row["tail"] for row in self.ledger if row.get("tail"))
        self.assertIn("test_a.py contest test-file.py src/test", tail)
        self.assertNotIn("value=test, test", tail)

    def test_masking_happens_before_a_long_value_is_clipped_to_the_tail(self) -> None:
        placeholder = "EXAMPLE" + "a" * 200 + "Z"
        self.session.bash(
            f"PASSWORD={placeholder} pytest", f"+ PASSWORD={placeholder}\n1 passed", is_error=False
        )
        text, _checks, _scan = self.published()
        tail = next(row["tail"] for row in self.ledger if row.get("tail"))
        self.assertLessEqual(len(tail), 180)
        self.assertNotIn("a" * 20, text)

    def test_wrapper_command_text_does_not_turn_runner_or_summary_words_into_a_masked_value(
        self,
    ) -> None:
        placeholder = "EXAMPLEsecrecy987"
        for command in (
            "bash -c " + shlex.quote(f"PASSWORD={placeholder} pytest"),
            "bash -c " + shlex.quote(f"echo --password {placeholder}; pytest"),
        ):
            with self.subTest(command=command[:20]):
                self.fresh()
                self.session.bash(
                    command,
                    f"+ PASSWORD={placeholder} pytest\npytest report: 1 passed",
                    is_error=False,
                )
                _text, _checks, _scan = self.published()
                tail = next(row["tail"] for row in self.ledger if row.get("tail"))
                self.assertIn("pytest report: 1 passed", tail)
                self.assertNotIn(placeholder, tail)

    def test_the_existing_short_and_arbitrarily_encoded_value_limits_remain(self) -> None:
        encoded = base64.b64encode(b"EXAMPLElongSecret").decode()
        self.session.bash("pytest --password abc", f"abc {encoded}\n1 passed", is_error=False)
        _text, _checks, _scan = self.published()
        tail = next(row["tail"] for row in self.ledger if row.get("tail"))
        self.assertIn("abc", tail)
        self.assertIn(encoded, tail)


class CoordinatedSecurityCorrectionTest(CheckLineTestCase):
    def assert_selected_prompt_omits(self, placeholder: str) -> None:
        prompt, selection = reading.build_prompt(
            self.ledger, goal="Keep synthetic checks correct", max_bytes=65536
        )
        checks = [row for row in selection.entries if row.get("subject") == "check"]
        self.assertEqual(1, len(checks))
        self.assertNotIn(placeholder, prompt)
        self.assertIn("pytest", prompt)

    def test_wrapper_postscript_named_args_remain_private_without_masking_runner_text(self) -> None:
        placeholder = "EXAMPLEpositional973"
        for wrapper in ("bash -c", "sh -c", "bash -lc"):
            for arguments in (f"--password {placeholder}", f"TOKEN={placeholder}"):
                with self.subTest(wrapper=wrapper, assignment="=" in arguments):
                    self.fresh()
                    command = f"{wrapper} 'pytest' {arguments}"
                    self.session.bash(
                        command, f"+ {command}\npytest report: 1 passed", is_error=False
                    )
                    text, checks, _scan = self.published()
                    self.assertEqual(1, len(checks))
                    self.assertNotIn(placeholder, text)
                    self.assertIn(
                        "pytest report: 1 passed",
                        next(row["tail"] for row in self.ledger if row.get("tail")),
                    )
                    self.assert_selected_prompt_omits(placeholder)

    def test_forwarded_named_args_withhold_a_check_write_path_before_any_output_grant(self) -> None:
        placeholder = "EXAMPLEpositional973"
        for arguments in (f"_ --password {placeholder}", f"_ TOKEN={placeholder}"):
            with self.subTest(assignment="=" in arguments):
                self.fresh()
                command = "bash -c " + shlex.quote(f'pytest "$@" > {placeholder}') + " " + arguments
                self.session.bash(command, f"+ {command}\n1 passed", is_error=False)
                events, scan = self.read()
                self.assertEqual(
                    [], [event["title"] for event in events if event["subject"] == "write"]
                )
                self.assertEqual(1, scan["outside_paths"])
                text, checks, _scan = self.published()
                self.assertEqual(1, len(checks))
                self.assertNotIn(placeholder, text)
                self.assert_selected_prompt_omits(placeholder)

    def test_arithmetic_nested_exec_and_backticks_mask_values_without_claiming_known_effects(
        self,
    ) -> None:
        placeholder = "EXAMPLEarith973"
        for nested in (
            f"$(SECRET_KEY={placeholder} date +%s)",
            f"`echo --password {placeholder}; echo 1`",
        ):
            for where in ("echo ", "cat <<EOF\n"):
                with self.subTest(backtick=nested.startswith("`"), heredoc="EOF" in where):
                    self.fresh()
                    command = "pytest; " + where + "$(( " + nested + " + 1 ))"
                    if "EOF" in where:
                        command += "\nEOF"
                    self.session.bash(
                        command, f"+ SECRET_KEY={placeholder}\n1 passed", is_error=False
                    )
                    text, checks, _scan = self.published()
                    self.assertEqual(1, len(checks))
                    self.assertIs(True, checks[0]["changed_after"])
                    self.assertNotIn(placeholder, text)
                    self.assert_selected_prompt_omits(placeholder)

    def test_ordinary_exec_and_arithmetic_literal_controls_keep_their_existing_classification(
        self,
    ) -> None:
        placeholder = "EXAMPLEarith973"
        self.session.bash(
            "pytest; echo $(SECRET_KEY=" + placeholder + " date +%s)",
            f"+ SECRET_KEY={placeholder}\n1 passed",
            is_error=False,
        )
        text, checks, _scan = self.published()
        self.assertIs(False, checks[0]["changed_after"])
        self.assertNotIn(placeholder, text)
        self.assert_selected_prompt_omits(placeholder)
        call = project_context._ShellCall(
            0, str(self.cwd), {"command": "pytest; echo $(( TOKEN=" + placeholder + " + 1 ))"}
        )
        self.assertNotIn(placeholder, call.masked_values)
        self.assertEqual([], [value for value in call.masked_values if "TOKEN" in value])

    def test_heredoc_executable_file_redirects_age_a_prior_pass_before_empty_or_cd_shortcuts(
        self,
    ) -> None:
        for body in ("> changed.txt", "cd . > changed.txt"):
            with self.subTest(cd=body.startswith("cd")):
                self.fresh()
                self.session.bash("pytest", "1 passed", is_error=False)
                self.session.bash("cat <<EOF\n$(" + body + ")\nEOF", "", is_error=False)
                _text, checks, _scan = self.published()
                self.assertEqual(1, len(checks))
                self.assertIs(True, checks[0]["changed_after"])
                self.assert_selected_prompt_omits("changed.txt")

    def test_heredoc_empty_and_cd_devnull_redirects_stay_read_only(self) -> None:
        for body in ("> /dev/null", "cd . > /dev/null"):
            with self.subTest(cd=body.startswith("cd")):
                self.fresh()
                self.session.bash("pytest", "1 passed", is_error=False)
                self.session.bash("cat <<EOF\n$(" + body + ")\nEOF", "", is_error=False)
                _text, checks, _scan = self.published()
                self.assertEqual(1, len(checks))
                self.assertIs(False, checks[0]["changed_after"])
                self.assert_selected_prompt_omits("/dev/null")
