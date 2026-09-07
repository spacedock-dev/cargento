"""The harness registry's gate-coverage disclosure, and the oracles that hold it.

These four checks were written against `reports_needs_input` in
`tests/test_page.py`, and they went out together in 8d2585c when the next UI
replaced the old one and that file was deleted as collateral. Nothing replaced
them, and `HarnessSpec`'s own docstring went on telling a reader that
`tests/test_next_page.py` derived the expected set, which no test there has ever
done. They live in a file of their own now rather than in `test_next_page.py`:
that file owns the frontend byte pins, which is the surface two branches most
often collide on, and none of what is here reads a byte of the page.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any

import event_hook
from cargento_runtime import events as runtime_events

from .support import REGISTRY, SERVER_PATH, STORE_KEYS, RuntimeTestCase, collect, store_patch

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

# Where the shipped adapters live: beside the launcher at the skill's top level,
# not under `cargento_runtime/`. Passed to the derivation below rather than read
# inside it, so a test can point it at a synthetic adapter.
ADAPTER_DIR = SERVER_PATH.parent


def _non_docstring_constants(tree: ast.AST) -> set[str]:
    """Every string constant in a parsed module except its docstrings.

    Split out of `_writes_a_wait` because the adapter read below needs the same
    exclusion for the same reason: a module that only *discusses* an event must
    not be read as mapping one.
    """
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings
    }


def _module_string(tree: ast.Module, name: str) -> str | None:
    """The value of a module-level `name = "<literal>"` assignment, or None."""
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return node.value.value
    return None


def _adapter_gate_harnesses(adapter_dir: Path) -> set[str]:
    """Every harness an adapter maps a gate for AND the server will admit.

    Two tables, and only one of them is authoritative for admission. An adapter's
    own event map says what it *sends*; `events.IDENTITY_NORMALIZERS` says what
    the server *accepts*, and `events.parse` refuses any harness absent from it
    outright. A gate reaches the board only where both hold, so the flag is
    demanded on the intersection rather than on either table alone. That this
    read one table while the server read the other is DRC-4440, and A-2 in
    `docs/design-adapter-packaging.md` is where the two were first told apart.

    The send half is read from two shapes, because the adapters have two.
    `event_hook.py` serves every hook-shaped harness from one file and keys them
    by harness in `EVENTS_BY_HARNESS`; every other adapter serves exactly one
    harness, names it in a module-level `HARNESS`, and carries a map of its own.
    Antigravity's two are the second shape, and reading only the first is what
    made this refuse a truthful declaration for a harness the server admits. The
    fix could not be an `EVENTS_BY_HARNESS` row for it: A-1 forbids one for a
    harness that never invokes `event_hook.py`, because that satisfies this
    oracle while making its guarantee false.

    Parsed rather than grepped, for `_writes_a_wait`'s reason on a second file: a
    text read of `statusline_hook.py` finds `input_requested` in the paragraph
    explaining why it is NOT mapped, and would take the decline for the mapping.

    Where it stops: this reads Python source. A-1 permits an adapter written in
    JavaScript, and a gate mapped in one would be invisible here. Recorded as a
    limit rather than papered over, on the same rule as `_writes_a_wait`'s.
    """
    sends = {
        harness
        for harness, table in event_hook.EVENTS_BY_HARNESS.items()
        if "input_requested" in table.values()
    }
    for path in sorted(adapter_dir.glob("*_hook.py")):
        if path.name == "event_hook.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        harness = _module_string(tree, "HARNESS")
        if harness is not None and "input_requested" in _non_docstring_constants(tree):
            sends.add(harness)
    return {harness for harness in sends if harness in runtime_events.IDENTITY_NORMALIZERS}


def _writes_a_wait(collect_fn: Callable[..., Any]) -> bool:
    """Whether a collector's own module names the `needs_input` state itself.

    The derived half of the gate-capability check. Reading the module is the
    point: any set of harnesses written down by hand has to be written by whoever
    set the flag, from the same belief, so it can only ever agree with them. This
    cannot — it asks the module what state it actually names.

    Two reaches, because there are two ways to name it. The parsed tree rather
    than the text, with docstring constants excluded, so a module that merely
    *discusses* needs-input in a comment or a docstring is not read as detecting
    one; and then the imported names, because `from ..events import
    OVERLAY_NEEDS_INPUT` puts the state in the namespace and leaves nothing in
    the source for the tree to find. Dunders are skipped there so the docstring
    exclusion survives the second reach.

    Both stay conservative in the same direction, which matters more than reach:
    a false positive would demand `reports_needs_input=True` on a harness that
    cannot detect a gate, which is the promise-the-board-cannot-keep error this
    whole disclosure exists to prevent. What neither reach can see is a state
    fetched from another module by a call, which is `WaitDerivationReachTest`.
    """
    module = inspect.getmodule(collect_fn)
    assert module is not None
    tree = ast.parse(inspect.getsource(module))
    if "needs_input" in _non_docstring_constants(tree):
        return True
    return any(
        value == "needs_input"
        for name, value in vars(module).items()
        if not name.startswith("__") and isinstance(value, str)
    )


def _throwaway_collector(tmp: str, name: str, source: str) -> ModuleType:
    """Import `source` as a real module on disk, the way a collector is imported.

    `_writes_a_wait` reads a module's source file, so a synthetic collector has
    to be a file a real import executed. A `ModuleType` assembled by hand has no
    source for `inspect` to find and would only ever exercise half the helper.
    """
    path = Path(tmp) / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WaitDerivationReachTest(unittest.TestCase):
    """What `_writes_a_wait` can see, and the spelling it cannot.

    The derivation above is only worth what it detects, and the comment on it is
    only worth what it does not overclaim. These three fix both ends against
    synthetic collectors rather than against the real ones, which all happen to
    use the plainest spelling today and so cannot tell the reaches apart.
    """

    def _collector(self, name: str, source: str) -> ModuleType:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(sys.modules.pop, name, None)
        return _throwaway_collector(tmp.name, name, source)

    def test_the_state_reached_through_an_imported_constant_is_seen(self) -> None:
        # `OVERLAY_NEEDS_INPUT` is the name the runtime already uses for this
        # state, so a collector spelling it that way is the idiomatic write, not
        # an exotic one. It puts the state in the module's namespace and nowhere
        # in its source, which is invisible to the parsed tree and plain to
        # `vars()`. `test_contracts`'s import-graph allowlist is what catches it
        # first today, but that allowlist is edited by hand by whoever adds the
        # import, so it cannot be the only thing standing here.
        module = self._collector(
            "cargento_probe_collector_constant",
            "from cargento_runtime.events import OVERLAY_NEEDS_INPUT\n"
            "\n"
            "\n"
            "def collect() -> str:\n"
            "    return OVERLAY_NEEDS_INPUT\n",
        )
        self.assertTrue(_writes_a_wait(module.collect))

    def test_the_state_named_only_in_a_docstring_is_not_seen(self) -> None:
        # The direction the derivation must not get wrong: a module that only
        # discusses the state must not be read as publishing one, because a false
        # positive here demands `reports_needs_input=True` on a harness that
        # cannot detect a gate. Both reaches have to hold that line, and a module
        # docstring is both a constant in the tree and a string in the namespace,
        # so this one case exercises them together.
        module = self._collector(
            "cargento_probe_collector_docstring",
            '"""needs_input"""\n\n\ndef collect() -> str:\n    return "idle"\n',
        )
        self.assertFalse(_writes_a_wait(module.collect))

    def test_the_state_reached_through_another_module_is_not_seen(self) -> None:
        # The blind spot, pinned as a limit rather than papered over. A collector
        # that calls a helper elsewhere for the state names it nowhere a read of
        # its own module can find: not in its source, not in its namespace. No
        # other oracle covers it either when the helper sits in a module the
        # collector already imports, since the import graph is then unchanged.
        # Deciding it needs following a call across modules, so the honest move is
        # to record where the derivation stops and keep its comment that narrow.
        self._collector(
            "cargento_probe_gate_helper",
            'def gate_state() -> str:\n    return "needs_input"\n',
        )
        module = self._collector(
            "cargento_probe_collector_helper",
            "import cargento_probe_gate_helper as helper\n"
            "\n"
            "\n"
            "def collect() -> str:\n"
            "    return helper.gate_state()\n",
        )
        self.assertFalse(_writes_a_wait(module.collect))


class AdapterGateDerivationReachTest(unittest.TestCase):
    """What `_adapter_gate_harnesses` admits, and the three things it refuses.

    Against synthetic adapters rather than the shipped ones, because the shipped
    ones cannot exercise the widening: no adapter outside `EVENTS_BY_HARNESS`
    maps `input_requested` today, which is how the defect sat here unnoticed. The
    last test is the shipped read, and it is the one holding the false-positive
    direction against the real files.
    """

    def _adapters(self, name: str, source: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        (directory / name).write_text(source, encoding="utf-8")
        return directory

    def test_a_gate_from_an_adapter_outside_the_hook_table_is_admitted(self) -> None:
        # DRC-4440's falsifier. Antigravity is admitted by `events.py` and ships
        # two adapters, neither hook-shaped and neither keyed in
        # `EVENTS_BY_HARNESS`, so a gate mapped in one was refused here while the
        # server would have accepted the envelope. Measured before the fix: a
        # truthful `"tool_use": "input_requested"` row in
        # `statusline_hook.AGENT_STATES` plus `reports_needs_input=True` on the
        # Antigravity spec turned three assertions in this file red, and one of
        # them was the derived oracle that exists to DEMAND the flag.
        self.assertNotIn("antigravity", event_hook.EVENTS_BY_HARNESS)
        adapters = self._adapters(
            "agy_hook.py",
            'HARNESS = "antigravity"\n\nSTATES = {"tool_use": "input_requested"}\n',
        )
        self.assertIn("antigravity", _adapter_gate_harnesses(adapters))

    def test_a_declaration_with_no_adapter_behind_it_is_still_refused(self) -> None:
        # The direction the widening must not break. Widening what counts as an
        # adapter is only safe while a flag with nothing behind it still fails:
        # Goose ships no adapter of any shape, Gemini's maps every event but this
        # one, and neither collector names the state. Both must stay out of the
        # derived set, and the oracle below must stay red for a spec set claiming
        # either.
        adapters = self._adapters(
            "goose_hook.py",
            'HARNESS = "goose"\n\nEVENTS = {"Start": "turn_started"}\n',
        )
        derived = _adapter_gate_harnesses(adapters)
        by_collector = {spec.key for spec in REGISTRY if _writes_a_wait(spec.collect)}
        declared = {spec.key for spec in REGISTRY if spec.reports_needs_input}
        for harness in ("goose", "gemini"):
            with self.subTest(harness=harness):
                self.assertNotIn(harness, derived)
                self.assertNotEqual(by_collector | derived, declared | {harness})

    def test_an_adapter_the_server_will_not_admit_is_not_a_route(self) -> None:
        # The mirror direction, which `docs/design-adapter-packaging.md` A-2 used
        # to describe as the reachable one. A gate an adapter maps for a harness
        # `events.py` refuses never reaches a row, so declaring the flag would be
        # a promise the board cannot keep -- the same error as the lying chip,
        # arriving from the other table.
        self.assertNotIn("droid", runtime_events.IDENTITY_NORMALIZERS)
        adapters = self._adapters(
            "droid_hook.py",
            'HARNESS = "droid"\n\nEVENTS = {"Ask": "input_requested"}\n',
        )
        self.assertNotIn("droid", _adapter_gate_harnesses(adapters))

    def test_the_shipped_adapters_map_a_gate_for_exactly_two_harnesses(self) -> None:
        # The false-positive direction against the real files, and why the read is
        # parsed rather than grepped. `statusline_hook.py` spends a paragraph on
        # why `tool_use` is NOT mapped -- the status line is a repeating render,
        # so an `input_requested` posted from there would be cleared by the next
        # push, and sending it needs a precedence rule in the overlay reducer
        # rather than a row in that table. Its source therefore carries
        # `input_requested` in a comment while `AGENT_STATES` maps only `working`
        # and `idle`, and a text search would take the decline for the mapping
        # and demand a flag Antigravity cannot honour.
        self.assertEqual({"claude", "codex"}, _adapter_gate_harnesses(ADAPTER_DIR))


class HarnessGateCoverageTest(RuntimeTestCase):
    """`reports_needs_input`: the declaration, its derivation, its prose, its wire."""

    def test_only_the_four_harnesses_with_a_gate_path_declare_one(self) -> None:
        # The same shape as `reports_rate` and for the same reason, on the
        # field where getting it wrong is worse. A harness with no gate detection
        # publishes no needs-input row, which is the identical payload a harness
        # WITH detection publishes when nothing is waiting -- so a row, a count and
        # a quiet board cannot say which of the two they are. Declaring it per
        # harness is what lets a reader tell "nothing is waiting" from "nothing
        # here could tell you".
        #
        # A literal set, not a re-read of the registry: comparing the flag to
        # itself would pass whichever way a row was set. Flipping one on here
        # without teaching its collector to emit `needs_input` would publish a
        # promise the board cannot keep, which is strictly worse than the gap.
        self.assertEqual(
            {"claude", "codex", "copilot", "cursor"},
            {spec.key for spec in REGISTRY if spec.reports_needs_input},
        )

    def test_the_gate_flag_matches_the_harnesses_that_actually_have_a_path(self) -> None:
        # The check that would have caught the defect this test was written for.
        # `reports_needs_input` is a hand-set bool, and the first review of the
        # change that added it found Codex shipping gate detection through the
        # event overlay while its own strip chip said "no gate detection" -- the
        # exact inversion the disclosure exists to prevent, pinned green by a
        # sibling test asserting a literal set.
        #
        # So derive the truth instead of restating it. A gate reaches the board by
        # exactly two routes: a collector that sets the state itself, or an adapter
        # that maps `input_requested` for a harness the server admits. A collector
        # that names the state in its own module, by literal or by imported
        # constant, and an adapter that maps it, are both demanded to declare the
        # flag here rather than shipping a lying chip.
        #
        # The adapter half used to read `EVENTS_BY_HARNESS` alone, which is one of
        # the adapter shapes and not the table the server admits on. Antigravity's
        # two adapters sit outside it, so a truthful mapping there was refused
        # here -- DRC-4440. `_adapter_gate_harnesses` reads both shapes now and
        # intersects them with what `events.py` will accept.
        #
        # What this does not cover, said plainly rather than guessed at, and now
        # two things rather than one. A collector that reaches the state through a
        # helper in another module names it nowhere a read of one module can find,
        # and following a call across modules is not something a heuristic here
        # should pretend to do; every collector today uses the bare literal. And
        # both halves read Python, while A-1 in `docs/design-adapter-packaging.md`
        # permits a JavaScript adapter. Both are left uncovered on the same rule
        # the deleted frontend pin below was deleted under.
        #
        # The collector half used to be the literal `{"claude"}`, because Claude's
        # was the only collector that produced a wait. Copilot's now does too, from
        # the `permission.requested`/`permission.completed` pair, and a literal
        # widened by hand is exactly the hand-written set this test exists to
        # replace -- it would have to be edited by the same person who set the flag,
        # from the same belief, so it could never contradict them. Reading the
        # collector modules for the state they actually write can.
        #
        # It has since paid for itself once. Cursor's gate read landed in its
        # collector and this test failed on the flag before anyone thought to set
        # it, which is the direction that matters: the derivation demanded the
        # declaration rather than being widened to agree with one.
        by_collector = {spec.key for spec in REGISTRY if _writes_a_wait(spec.collect)}
        by_adapter = _adapter_gate_harnesses(ADAPTER_DIR)
        self.assertEqual(
            by_collector | by_adapter,
            {spec.key for spec in REGISTRY if spec.reports_needs_input},
        )

    def test_the_prose_that_counts_gate_blind_harnesses_stays_true(self) -> None:
        # The count in `HarnessSpec`'s docstring is the only place a reader is told
        # how much of the board is silent by construction, and it has been wrong
        # twice: `reports_needs_input` went from one harness to two to three, and
        # the sentence stayed at "Eight of the ten" through both. Nothing in ruff,
        # mypy, the validator or the suite reads a comment, so it survived until
        # someone read it and believed it.
        #
        # The frontend half of this check is gone rather than repointed. It used to
        # read `regular.js` and ban a spelled-out count from the comment above
        # `gateBlind()`, on the rule that a count there buys nothing because the
        # function reads the payload's per-harness flag: that comment had carried
        # "Nine of the ten" through two consecutive features that changed it. Both
        # the asset and the function went with the old UI in 8d2585c. Today the
        # payload flag is read in `next-attention.js` (`nextAttentionCoverage`,
        # `nextAttentionCoverageHtml`) and `next-sessions.js`
        # (`nextOperationsReportsBlocks`), and none of the three carries a comment
        # that counts anything, so there is no count to ban and inventing a pin on
        # a comment that does not exist would only pin the pin. The rule survives
        # as a rule: a spelled-out count in a frontend comment about gate coverage
        # rots at the rate of the registry, and the fix is to delete it rather than
        # to test it.
        words = (
            "no",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
        )
        blind = sum(1 for spec in REGISTRY if not spec.reports_needs_input)
        docstring = type(REGISTRY[0]).__doc__ or ""
        self.assertIn(
            f"{words[blind].capitalize()} of the {words[len(REGISTRY)]} cannot observe a gate",
            docstring,
        )

    def test_the_payload_publishes_the_gate_coverage_per_harness(self) -> None:
        # Six of the ten rows are silent about gates by construction, and the page
        # cannot derive that from anything else it is sent. Without this the server
        # could stop publishing the flag and every page-side test would stay green,
        # because they all feed synthetic payloads.
        with (
            tempfile.TemporaryDirectory() as tmp,
            store_patch(**dict.fromkeys(STORE_KEYS, tmp)),
        ):
            data = collect()

        self.assertEqual(
            {spec.key: spec.reports_needs_input for spec in REGISTRY},
            {h["key"]: h["reports_needs_input"] for h in data["harnesses"]},
        )

    def test_a_gate_mechanism_that_can_be_switched_off_names_its_condition(self) -> None:
        # `reports_needs_input` answers "can a gate on this harness reach the
        # board", and for Codex the honest answer is "where the operator has
        # approvals on". Its mechanism is the bundled `PermissionRequest` hook,
        # which cannot fire in a session that never asks, so for an operator
        # running with approvals off a quiet Codex row is the all-clear the flag
        # exists to prevent -- the same inversion as a lying chip, arriving as
        # silence instead.
        #
        # Declared here rather than derived from a harness config, and that was
        # investigated rather than assumed: `approval_policy` is overridable per
        # invocation (`codex exec -c approval_policy=...`) and per project, so a
        # global read cannot say whether a given session will ask, and acting on
        # one would publish "no gate observable here" while a session sat at a
        # prompt. A condition that qualifies the capability is a property of the
        # mechanism, which is what this registry already declares.
        #
        # A literal, for the same reason the capability set above is a literal:
        # re-reading the field would agree with whatever it was set to.
        self.assertEqual(
            {"codex": "where approvals are enabled"},
            {
                spec.key: spec.reports_needs_input_when
                for spec in REGISTRY
                if spec.reports_needs_input_when is not None
            },
        )
        # A condition on a row that reports no gate qualifies nothing. The page
        # drops it, so a spec that set one would be silently inert here.
        self.assertEqual(
            [],
            [
                spec.key
                for spec in REGISTRY
                if spec.reports_needs_input_when is not None and not spec.reports_needs_input
            ],
        )

    def test_the_payload_publishes_the_gate_condition_beside_the_capability(self) -> None:
        # Same argument as the flag above: the page cannot derive the condition,
        # and every page-side test feeds a synthetic payload, so the server could
        # stop publishing it and nothing else would go red.
        with (
            tempfile.TemporaryDirectory() as tmp,
            store_patch(**dict.fromkeys(STORE_KEYS, tmp)),
        ):
            data = collect()

        self.assertEqual(
            {spec.key: spec.reports_needs_input_when for spec in REGISTRY},
            {h["key"]: h["reports_needs_input_when"] for h in data["harnesses"]},
        )
