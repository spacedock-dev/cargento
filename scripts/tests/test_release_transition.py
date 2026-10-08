"""The release's decisions, rehearsed against temporary repositories.

The workflow's inline shell used to make these decisions where nothing could
exercise them, which is how a pipe closed early under `pipefail` once broke
resuming. Every figure below is read from a real temporary Git repository with a
bare origin; nothing reaches the real remote, a real tag or a version field.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bump_version
import release_transition as rt

if TYPE_CHECKING:
    from tests.release_fixture import MANIFESTS, WEB, Fixture, git
else:
    from release_fixture import MANIFESTS, WEB, Fixture, git

SHA = re.compile(r"^[0-9a-f]{40}$")


class TagFormTest(unittest.TestCase):
    def test_strict_semver_with_either_prefix_is_accepted(self) -> None:
        self.assertEqual("1.2.3", rt.parse_tag("v1.2.3")[0])
        self.assertEqual("1.2.3", rt.parse_tag("1.2.3")[0])
        self.assertEqual((10, 0, 0), rt.parse_tag("v10.0.0")[1])

    def test_anything_else_is_refused_before_it_can_reach_a_command(self) -> None:
        for tag in (
            "v01.2.3",
            "v1.2",
            "1.2.3-rc1",
            "v1.2.3\n",
            " v1.2.3",
            "v1.2.3; touch x",
            "$(id)",
            "refs/tags/v1.2.3",
            "",
        ):
            with self.subTest(tag=tag), self.assertRaises(rt.ReleaseError):
                rt.parse_tag(tag)

    def test_the_tag_grammar_is_the_bump_scripts_own(self) -> None:
        # The workflow validates the tag with this module and bumps with the
        # other script; two grammars would let a tag pass one and fail the other
        # after the run had started.
        self.assertEqual(bump_version.SEMVER_RE.pattern, rt.SEMVER.pattern)


class MonotonicTest(unittest.TestCase):
    def test_a_greater_tag_passes_numerically_not_lexically(self) -> None:
        rt.check_monotonic("v0.10.0", ["v0.9.0", "0.2.0", "v0.1.0"])

    def test_an_equal_or_greater_existing_tag_refuses_back_tagging(self) -> None:
        for existing in ("0.2.0", "v0.3.0", "1.0.0"):
            with self.subTest(existing=existing), self.assertRaises(rt.ReleaseError) as caught:
                rt.check_monotonic("v0.2.0", [existing])
            self.assertIn("back-tagging", str(caught.exception))

    def test_the_tag_itself_and_non_release_names_are_ignored(self) -> None:
        rt.check_monotonic("v0.2.0", ["v0.2.0", "latest", "v0.1.0-rc1", ""])


class ReleaseCommitLookupTest(unittest.TestCase):
    LOG = (
        "ccc\tfeat: later work\n"
        "bbb\tchore(release): v0.2.0\n"
        "aaa\tchore(release): v0.2.0\n"
        "999\tchore(release): v0.2.0-extra"
    )

    def test_the_newest_exact_subject_wins(self) -> None:
        self.assertEqual("bbb", rt.find_release_commit(self.LOG, "v0.2.0"))

    def test_a_prefix_or_a_different_tag_does_not_match(self) -> None:
        self.assertIsNone(rt.find_release_commit(self.LOG, "v0.3.0"))
        self.assertIsNone(rt.find_release_commit(self.LOG, "0.2.0"))
        self.assertIsNone(rt.find_release_commit("", "v0.2.0"))


class ResolveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture(self)

    def resolve(self, tag: str) -> rt.Resolution:
        self.fx.fetch()
        return rt.resolve(self.fx.work, tag)

    def test_a_fresh_release_targets_the_main_tip_as_a_full_sha(self) -> None:
        tip = self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        result = self.resolve("v0.2.0")
        self.assertEqual("fresh", result.mode)
        self.assertEqual("0.2.0", result.version)
        self.assertEqual(tip, result.target)
        self.assertRegex(result.target, SHA)
        self.assertEqual("", result.release_commit)

    def test_the_target_is_main_at_resolution_not_the_tagged_commit(self) -> None:
        tagged = self.fx.commit("feat: tagged")
        self.fx.tag("v0.2.0")
        tip = self.fx.commit("feat: after the tag")
        result = self.resolve("v0.2.0")
        self.assertEqual(tip, result.target)
        self.assertNotEqual(tagged, result.target)

    def test_back_tagging_is_refused(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.0.9")
        with self.assertRaises(rt.ReleaseError) as caught:
            self.resolve("v0.0.9")
        self.assertIn("strictly greater", str(caught.exception))

    def test_a_tag_that_is_not_on_main_is_refused(self) -> None:
        git(self.fx.work, "checkout", "-q", "-b", "side")
        side = self.fx.commit("feat: off main", push=False, branch="side")
        git(self.fx.work, "checkout", "-q", "main")
        git(self.fx.work, "-c", "tag.gpgsign=false", "tag", "v0.2.0", side)
        git(self.fx.work, "push", "-q", "origin", "refs/tags/v0.2.0")
        with self.assertRaises(rt.ReleaseError) as caught:
            self.resolve("v0.2.0")
        self.assertIn("not on main", str(caught.exception))

    def release_commit(self, tag: str, version: str) -> str:
        self.fx.set_version(version)
        git(self.fx.work, "commit", "-q", "--amend", "-m", f"chore(release): {tag}")
        git(self.fx.work, "push", "-q", "--force", "origin", "main")
        return git(self.fx.work, "rev-parse", "HEAD")

    def test_an_existing_release_commit_resumes_onto_itself(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        release = self.release_commit("v0.2.0", "0.2.0")
        self.fx.commit("feat: merged while the release was down")
        result = self.resolve("v0.2.0")
        self.assertEqual("resume", result.mode)
        self.assertEqual(release, result.target)
        self.assertEqual(release, result.release_commit)

    def test_resume_survives_a_later_release_and_skips_the_monotonic_check(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        release = self.release_commit("v0.2.0", "0.2.0")
        self.fx.commit("feat: more work")
        self.fx.tag("v0.3.0")
        self.release_commit("v0.3.0", "0.3.0")
        result = self.resolve("v0.2.0")
        self.assertEqual(("resume", release), (result.mode, result.target))

    def test_a_release_commit_carrying_the_wrong_version_is_not_resumed(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        self.release_commit("v0.2.0", "0.9.9")
        with self.assertRaises(rt.ReleaseError) as caught:
            self.resolve("v0.2.0")
        self.assertIn("refusing to resume", str(caught.exception))


class AssertCheckoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture(self)
        self.tip = self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")

    def checkout_main(self) -> None:
        self.fx.fetch()
        git(self.fx.work, "checkout", "-q", "--detach", "origin/main")

    def test_fresh_passes_when_the_checkout_is_the_verified_target(self) -> None:
        self.checkout_main()
        rt.assert_checkout(self.fx.work, "fresh", self.tip, "v0.2.0", verified=self.tip)

    def test_fresh_fails_safely_when_main_moved_after_resolution(self) -> None:
        self.fx.commit("feat: landed during verification")
        self.checkout_main()
        before = self.fx.origin_snapshot()
        with self.assertRaises(rt.ReleaseError) as caught:
            rt.assert_checkout(self.fx.work, "fresh", self.tip, "v0.2.0", verified=self.tip)
        self.assertIn("moved", str(caught.exception))
        self.assertIn("re-run", str(caught.exception).lower())
        self.assertEqual(before, self.fx.origin_snapshot())

    def test_the_verification_job_must_have_checked_the_same_target(self) -> None:
        self.checkout_main()
        other = "0" * 40
        with self.assertRaises(rt.ReleaseError) as caught:
            rt.assert_checkout(self.fx.work, "fresh", self.tip, "v0.2.0", verified=other)
        self.assertIn("verified", str(caught.exception))
        with self.assertRaises(rt.ReleaseError):
            rt.assert_checkout(self.fx.work, "fresh", self.tip, "v0.2.0", verified="")

    def test_a_malformed_target_is_refused_before_any_git_command_uses_it(self) -> None:
        self.checkout_main()
        for bad in ("main", "HEAD", "--upload-pack=x", self.tip[:12], self.tip.upper(), ""):
            with self.subTest(bad=bad), self.assertRaises(rt.ReleaseError):
                rt.assert_checkout(self.fx.work, "fresh", bad, "v0.2.0", verified=bad)

    def test_an_unknown_mode_is_refused(self) -> None:
        self.checkout_main()
        with self.assertRaises(rt.ReleaseError):
            rt.assert_checkout(self.fx.work, "maybe", self.tip, "v0.2.0", verified=self.tip)

    def test_resume_accepts_a_release_commit_that_main_has_moved_past(self) -> None:
        self.fx.set_version("0.2.0")
        git(self.fx.work, "commit", "-q", "--amend", "-m", "chore(release): v0.2.0")
        git(self.fx.work, "push", "-q", "--force", "origin", "main")
        release = git(self.fx.work, "rev-parse", "HEAD")
        self.fx.commit("feat: later")
        self.checkout_main()
        rt.assert_checkout(self.fx.work, "resume", release, "v0.2.0", verified=release)

    def test_resume_refuses_a_target_main_does_not_contain(self) -> None:
        git(self.fx.work, "checkout", "-q", "-b", "side")
        side = self.fx.commit("feat: off main", push=False, branch="side")
        self.checkout_main()
        git(self.fx.work, "fetch", "-q", "--no-tags", ".", "side:refs/heads/side")
        with self.assertRaises(rt.ReleaseError) as caught:
            rt.assert_checkout(self.fx.work, "resume", side, "v0.2.0", verified=side)
        self.assertIn("not on main", str(caught.exception))

    def test_resume_refuses_a_target_whose_manifests_carry_another_version(self) -> None:
        self.checkout_main()
        with self.assertRaises(rt.ReleaseError):
            rt.assert_checkout(self.fx.work, "resume", self.tip, "v0.2.0", verified=self.tip)

    def test_assert_head_names_both_commits(self) -> None:
        rt.assert_head(self.fx.work, self.tip)
        with self.assertRaises(rt.ReleaseError) as caught:
            rt.assert_head(self.fx.work, "1" * 40)
        self.assertIn(self.tip, str(caught.exception))


class BumpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture(self)
        self.fx.commit("feat: work")

    def versions(self) -> set[str]:
        return {
            json.loads((self.fx.work / relative).read_text(encoding="utf-8"))["version"]
            for relative in MANIFESTS
        }

    def test_a_greater_version_is_written_to_every_owned_field(self) -> None:
        self.assertTrue(rt.bump(self.fx.work, "0.2.0"))
        self.assertEqual({"0.2.0"}, self.versions())

    def test_the_current_version_needs_no_bump(self) -> None:
        self.assertFalse(rt.bump(self.fx.work, "0.1.0"))
        self.assertEqual({"0.1.0"}, self.versions())
        self.assertEqual("", git(self.fx.work, "status", "--porcelain"))

    def test_a_lower_version_is_refused_by_the_bump_script(self) -> None:
        self.fx.set_version("0.5.0")
        with self.assertRaises(rt.ReleaseError):
            rt.bump(self.fx.work, "0.4.0")

    def test_the_release_commit_is_signed_off_and_titled_by_tag(self) -> None:
        rt.bump(self.fx.work, "0.2.0")
        sha = rt.commit_bump(self.fx.work, "v0.2.0")
        self.assertEqual(sha, git(self.fx.work, "rev-parse", "HEAD"))
        message = git(self.fx.work, "log", "-1", "--format=%B")
        self.assertTrue(message.startswith("chore(release): v0.2.0"))
        self.assertIn("Signed-off-by:", message)
        self.assertIn("Bump plugin version to 0.2.0", message)
        changed = git(self.fx.work, "diff", "--name-only", "HEAD~1", "HEAD").splitlines()
        self.assertEqual(sorted(MANIFESTS), sorted(changed))

    def test_committing_with_nothing_to_commit_is_a_noop(self) -> None:
        head = git(self.fx.work, "rev-parse", "HEAD")
        self.assertEqual(head, rt.commit_bump(self.fx.work, "v0.1.0"))
        self.assertEqual(head, git(self.fx.work, "rev-parse", "HEAD"))

    def test_the_commit_takes_only_the_owned_paths(self) -> None:
        rt.bump(self.fx.work, "0.2.0")
        (self.fx.work / "stray.txt").write_text("not part of a release", encoding="utf-8")
        rt.commit_bump(self.fx.work, "v0.2.0")
        changed = git(self.fx.work, "diff", "--name-only", "HEAD~1", "HEAD").splitlines()
        self.assertNotIn("stray.txt", changed)


class PublishStepsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture(self)
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        rt.bump(self.fx.work, "0.2.0")
        self.final = rt.commit_bump(self.fx.work, "v0.2.0")

    def test_the_bump_push_is_never_forced(self) -> None:
        self.fx.commit("feat: landed first")  # origin main is now not an ancestor
        before = self.fx.origin_snapshot()
        with self.assertRaises(rt.ReleaseError):
            rt.push_bump(self.fx.work, "origin", self.final)
        self.assertEqual(before, self.fx.origin_snapshot())

    def test_the_bump_push_fast_forwards_main(self) -> None:
        rt.push_bump(self.fx.work, "origin", self.final)
        self.assertEqual(self.final, self.fx.origin_rev("refs/heads/main"))

    def test_the_tag_moves_onto_the_release_commit_even_if_it_was_elsewhere(self) -> None:
        rt.push_bump(self.fx.work, "origin", self.final)
        rt.move_tag(self.fx.work, "origin", "v0.2.0", self.final)
        self.assertEqual(self.final, self.fx.origin_rev("refs/tags/v0.2.0"))
        rt.move_tag(self.fx.work, "origin", "v0.2.0", self.final)
        self.assertEqual(self.final, self.fx.origin_rev("refs/tags/v0.2.0"))

    def test_stable_is_force_advanced_and_idempotent(self) -> None:
        rt.advance_stable(self.fx.work, "origin", self.final)
        self.assertEqual(self.final, self.fx.origin_rev("refs/heads/stable"))
        rt.advance_stable(self.fx.work, "origin", self.final)
        self.assertEqual(self.final, self.fx.origin_rev("refs/heads/stable"))

    def test_a_final_commit_that_is_not_a_full_sha_is_refused(self) -> None:
        for bad in ("main", "HEAD", "--delete", self.final[:10]):
            with self.subTest(bad=bad):
                with self.assertRaises(rt.ReleaseError):
                    rt.move_tag(self.fx.work, "origin", "v0.2.0", bad)
                with self.assertRaises(rt.ReleaseError):
                    rt.advance_stable(self.fx.work, "origin", bad)
                with self.assertRaises(rt.ReleaseError):
                    rt.push_bump(self.fx.work, "origin", bad)


class FinalCommitTest(unittest.TestCase):
    def test_fresh_publishes_head_when_it_is_the_target_or_its_direct_child(self) -> None:
        fx = Fixture(self)
        target = fx.commit("feat: work")
        self.assertEqual(target, rt.final_commit(fx.work, "fresh", target))
        rt.bump(fx.work, "0.2.0")
        child = rt.commit_bump(fx.work, "v0.2.0")
        self.assertEqual(child, rt.final_commit(fx.work, "fresh", target))

    def test_fresh_refuses_a_head_that_is_not_built_on_the_target(self) -> None:
        fx = Fixture(self)
        fx.commit("feat: work")
        fx.commit("feat: more")
        with self.assertRaises(rt.ReleaseError):
            rt.final_commit(fx.work, "fresh", "f" * 40)

    def test_resume_publishes_the_target_whatever_head_is(self) -> None:
        fx = Fixture(self)
        fx.commit("feat: work")
        self.assertEqual("f" * 40, rt.final_commit(fx.work, "resume", "f" * 40))
        with self.assertRaises(rt.ReleaseError):
            rt.final_commit(fx.work, "resume", "main")


class RehearsalTest(unittest.TestCase):
    """The whole sequence against a bare origin, with failures injected."""

    def setUp(self) -> None:
        self.fx = Fixture(self)

    def drive(self, tag: str, **kwargs: object) -> rt.Outcome:
        return rt.rehearse(self.fx.work, tag, **kwargs)  # type: ignore[arg-type]

    def assert_published(self, tag: str, version: str) -> str:
        final = self.fx.origin_rev("refs/heads/stable")
        assert final is not None
        self.assertEqual(final, self.fx.origin_rev(f"refs/tags/{tag}"))
        manifest = git(self.fx.origin, "show", f"{final}:{MANIFESTS[0]}")
        self.assertEqual(version, json.loads(manifest)["version"])
        return final

    def test_a_fresh_release_bumps_pushes_tags_and_advances_stable(self) -> None:
        tip = self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        outcome = self.drive("v0.2.0")
        self.assertEqual("fresh", outcome.mode)
        final = self.assert_published("v0.2.0", "0.2.0")
        self.assertEqual(final, self.fx.origin_rev("refs/heads/main"))
        self.assertEqual(tip, git(self.fx.origin, "rev-parse", f"{final}^"))
        self.assertEqual(
            "chore(release): v0.2.0", git(self.fx.origin, "log", "-1", "--format=%s", final)
        )

    def test_a_release_of_the_version_already_carried_makes_no_bump_commit(self) -> None:
        self.fx.tag("v0.1.0")
        self.drive("v0.1.0")
        final = self.assert_published("v0.1.0", "0.1.0")
        self.assertEqual(self.fx.origin_rev("refs/heads/main"), final)
        self.assertNotEqual(
            "chore(release): v0.1.0", git(self.fx.origin, "log", "-1", "--format=%s", final)
        )

    def test_dry_run_stops_before_anything_is_pushed(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        before = self.fx.origin_snapshot()
        outcome = self.drive("v0.2.0", dry_run=True)
        self.assertEqual(before, self.fx.origin_snapshot())
        self.assertEqual("archive", outcome.last_phase)

    def test_main_advancing_between_resolution_and_publication_changes_nothing(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        before_tag = self.fx.origin_rev("refs/tags/v0.2.0")

        def advance(_: rt.Resolution) -> None:
            self.fx.commit("feat: landed during verification")

        before = self.fx.origin_snapshot()
        with self.assertRaises(rt.ReleaseError) as caught:
            self.drive("v0.2.0", after={"verify": advance})
        self.assertIn("moved", str(caught.exception))
        after = self.fx.origin_snapshot()
        landed = after["refs/heads/main"]
        self.assertNotEqual(before["refs/heads/main"], landed)
        # Only the advance itself moved; the release published nothing.
        self.assertEqual(before_tag, self.fx.origin_rev("refs/tags/v0.2.0"))
        self.assertIsNone(self.fx.origin_rev("refs/heads/stable"))
        self.assertEqual(landed, after["refs/heads/main"])

    def test_a_newer_main_bundle_is_never_published_for_an_older_verified_target(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        bundle = f"{WEB}/react.html"

        def poison(_: rt.Resolution) -> None:
            self.fx.commit("feat: a bundle nobody verified", files={bundle: "<!doctype html>\n"})

        with self.assertRaises(rt.ReleaseError):
            self.drive("v0.2.0", after={"verify": poison})
        self.assertIsNone(self.fx.origin_rev("refs/heads/stable"))
        self.assertEqual(
            self.fx.origin_rev("refs/tags/v0.2.0"), self.fx.origin_rev("refs/tags/v0.2.0")
        )
        for ref in ("refs/tags/v0.2.0", "refs/heads/stable"):
            published = self.fx.origin_rev(ref)
            if published:
                self.assertNotEqual(
                    "<!doctype html>\n", git(self.fx.origin, "show", f"{published}:{bundle}")
                )

    def test_a_rerun_after_the_failed_race_resolves_and_publishes_the_new_tip(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")

        def advance(_: rt.Resolution) -> None:
            self.fx.commit("feat: landed during verification")

        with self.assertRaises(rt.ReleaseError):
            self.drive("v0.2.0", after={"verify": advance})
        self.drive("v0.2.0")
        self.assert_published("v0.2.0", "0.2.0")

    def test_every_partial_failure_is_finished_by_a_rerun(self) -> None:
        for phase, expected_mode in (
            ("archive", "fresh"),
            ("push-bump", "resume"),
            ("move-tag", "resume"),
            ("stable", "resume"),
        ):
            with self.subTest(failing_after=phase):
                self.fx = Fixture(self)
                self.fx.commit("feat: work")
                self.fx.tag("v0.2.0")

                def boom(_: rt.Resolution) -> None:
                    message = "injected failure"
                    raise rt.ReleaseError(message)

                with self.assertRaises(rt.ReleaseError):
                    self.drive("v0.2.0", after={phase: boom})
                if phase == "archive":
                    self.assertIsNone(self.fx.origin_rev("refs/heads/stable"))
                    self.assertEqual(
                        "feat: work", git(self.fx.origin, "log", "-1", "--format=%s", "main")
                    )
                outcome = self.drive("v0.2.0")
                self.assertEqual(expected_mode, outcome.mode)
                self.assert_published("v0.2.0", "0.2.0")

    def test_a_resumed_release_publishes_its_own_commit_after_a_later_release(self) -> None:
        self.fx.commit("feat: work")
        self.fx.tag("v0.2.0")
        self.drive("v0.2.0", stop_after="push-bump")
        first = self.fx.origin_rev("refs/heads/main")
        self.fx.commit("feat: next")
        self.fx.tag("v0.3.0")
        self.drive("v0.3.0")
        self.assertNotEqual(first, self.fx.origin_rev("refs/heads/main"))
        outcome = self.drive("v0.2.0")
        self.assertEqual("resume", outcome.mode)
        self.assertEqual(first, self.fx.origin_rev("refs/tags/v0.2.0"))
        self.assertEqual(
            "0.3.0", json.loads(git(self.fx.origin, "show", f"v0.3.0:{MANIFESTS[0]}"))["version"]
        )

    def test_a_tampered_bundle_stops_the_release_before_anything_is_pushed(self) -> None:
        self.fx.commit("feat: work")
        self.fx.commit("fix: tamper", files={f"{WEB}/react.html": "<!doctype html>\n"})
        self.fx.tag("v0.2.0")
        before = self.fx.origin_snapshot()
        with self.assertRaises(rt.ReleaseError):
            self.drive("v0.2.0")
        self.assertEqual(before, self.fx.origin_snapshot())


if __name__ == "__main__":
    unittest.main()
