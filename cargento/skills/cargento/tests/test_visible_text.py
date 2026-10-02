"""The shared visibility helper drops what a sighted reader does not see, and nothing else."""

from __future__ import annotations

import unittest

from .visible_text import visible_text


class VisibleTextTest(unittest.TestCase):
    def test_a_closed_details_shows_only_its_summary(self) -> None:
        html = (
            "<p>Before</p><details><summary>What is sent</summary><p>The body.</p>loose</details>"
        )

        self.assertEqual("Before What is sent", visible_text(html))

    def test_an_open_details_shows_its_body(self) -> None:
        html = '<details open=""><summary>What is sent</summary><p>The body.</p></details>'

        self.assertEqual("What is sent The body.", visible_text(html))

    def test_a_visually_hidden_node_and_its_children_are_dropped(self) -> None:
        html = (
            '<span class="next-cockpit-reading-count">0 requests'
            '<span class="next-visually-hidden"> <b>0 model requests</b> recorded.</span></span>'
        )

        self.assertEqual("0 requests", visible_text(html))

    def test_a_hidden_attribute_is_dropped(self) -> None:
        self.assertEqual("shown", visible_text("<p hidden>gone</p><p>shown</p>"))

    def test_a_closed_details_nested_in_an_open_one_is_still_closed(self) -> None:
        html = (
            "<details open><summary>Outer</summary><p>Outer body</p>"
            "<details><summary>Inner</summary><p>Inner body</p></details></details>"
        )

        self.assertEqual("Outer Outer body Inner", visible_text(html))

    def test_void_elements_and_unclosed_paragraphs_do_not_leak_hiding(self) -> None:
        html = '<details><summary>S</summary><p>one<br>two</details><p>after<img src="x">'

        self.assertEqual("S after", visible_text(html))

    def test_a_closed_select_shows_only_its_selected_option(self) -> None:
        html = (
            '<p>Goal</p><select><option value="">Use your prompt</option>'
            '<option value="a" selected>First prompt</option><option value="b">Latest</option>'
            "</select><p>after</p>"
        )

        self.assertEqual("Goal First prompt after", visible_text(html))

    def test_a_select_with_nothing_selected_shows_its_first_option(self) -> None:
        html = '<select class="x"><option value="">Use your prompt</option><option>Two</option></select>'

        self.assertEqual("Use your prompt", visible_text(html))

    def test_a_hidden_select_shows_nothing(self) -> None:
        html = '<span class="next-visually-hidden"><select><option>One</option></select></span>ok'

        self.assertEqual("ok", visible_text(html))

    def test_entities_are_decoded(self) -> None:
        self.assertEqual("a & b <c>", visible_text("<p>a &amp; b &lt;c&gt;</p>"))


if __name__ == "__main__":
    unittest.main()
