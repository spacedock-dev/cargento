# Design: what language an adapter may be written in, and what admits it

Owner for the question "the harness has no Python hook, so how does its adapter reach the event
lane?". The module map, including which file owns the envelope and which owns identity
normalization, belongs to [design-runtime-architecture.md](design-runtime-architecture.md); the
gate's precedence rules and its evidence ranking belong to
[design-needs-input.md](design-needs-input.md). This document owns the packaging call: which
languages ship, where their files live, and which checks have to grow to see them.

It exists because the answer was unwritten while two gate builds were reading as ready to start,
which is the second time this project has queued work behind a policy nobody had recorded.

Each decision keeps a stable `A-N` anchor. Grep the identifier across `*.py`, `*.toml` and `*.md`
before renumbering anything.

---

## The problem these decisions answer

Cargento's event lane was built for harnesses whose hooks are hook-shaped, which `event_hook.py`
defines in its own header as a fresh process per event, one JSON payload on stdin, and a
`hook_event_name` naming what happened. Claude Code, Codex and Gemini CLI all are. Antigravity is
not, and it already has its own adapter for that reason.

The next two harnesses in the queue are neither. Both would run inside the harness process and
subscribe to a callback, which is a JavaScript or TypeScript surface rather than a subprocess one.
Nothing in the repository said whether such an adapter may ship, and four separate checks assume it
cannot.

## A-1: first-class JavaScript ships outside `cargento_runtime/web/`

Decided 2026-09-07 by the owner, under DEC-11's sibling decision (Linear DRC-4428).

An adapter may be written in JavaScript and bundled outside `cargento_runtime/web/`, which until
now was the only directory holding any non-Python code. The four checks in A-3 widen to accommodate
it.

**Rejected: a thin shim that spawns the Python entry point.** The alternative was a small
JavaScript file under the harness's own plugin directory that filters the harness bus and runs
`python3 event_hook.py <harness>` per event. It is genuinely cheaper in one dimension and worth
recording properly, because it will look attractive again:

- it satisfies `event_hook.py`'s hook-shaped contract literally, so the envelope, the capability
  handling and the vocabulary validation are all reused unchanged;
- it touches none of the four validator surfaces, because the only file that ships is one the
  harness loads and Cargento never validates;
- the `EVENTS_BY_HARNESS` entry stays honest, so the gate-coverage oracle passes without being
  edited.

Its cost is a process spawn per event. For a permission dialog that is once per gate and once per
answer, which is nothing. The owner chose the first-class route anyway, so the shim is recorded here
as a road not taken rather than as a fallback: re-proposing it means reopening A-1, not
reinterpreting it.

**What must not be done either way** is the third option that was on the table: adding an
`EVENTS_BY_HARNESS` entry for a harness that never invokes `event_hook.py`. That satisfies the
oracle in A-2 while making its guarantee false, which is worse than the hand-set boolean the oracle
replaced. The oracle exists because a hand-set boolean beside a hand-written literal once pinned a
bug green.

## A-2: the test oracle and the server's admission gate are different tables

This is the correction that reframed the decision, and it is the most useful fact in this file.

`tests/test_harness_registry.py` derives gate coverage from two routes: a collector that names
`needs_input` in its own module, or an adapter mapping `input_requested`. Declaring
`reports_needs_input=True` for a harness with neither turns the suite red. When this was written the
adapter route read `EVENTS_BY_HARNESS` and nothing else.

But the **server** admits on neither. `events.py` refuses any harness absent from
`IDENTITY_NORMALIZERS`, and states the policy in place: one normalizer per harness whose adapter has
shipped, because the design requires the identity mapping to be established per harness before its
adapter ships. The two tables differ by exactly one key today, and that key is `antigravity`:
`EVENTS_BY_HARNESS` holds Claude, Codex and Gemini, `IDENTITY_NORMALIZERS` holds those three plus
Antigravity. One key is the whole of the divergence, and it is the harness whose adapters are not
hook-shaped.

So an adapter POSTing to `/api/events/<harness>` is refused today whatever language it is written
in, and however the test oracle is widened. **Every new adapter therefore requires a Python edit to
`events.py`**, which the original "non-Python adapter" framing obscured entirely. Measured: adding
`reports_needs_input=True` for a harness with no route fails three tests, not one, and the third is
a prose count in a docstring.

That the coverage oracle checked a different table from the one the server admits on was a defect in
its own right, tracked as Linear DRC-4440 and **fixed**. The direction that mattered is the opposite
of the one first written here, and the correction is worth keeping because the wrong one reads
plausibly: it described the oracle reporting a harness as covered while the server refused it, which
needs a harness inside `EVENTS_BY_HARNESS` and absent from `IDENTITY_NORMALIZERS`. No such harness
exists, and reaching that state means adding an `EVENTS_BY_HARNESS` row for a harness that never
invokes `event_hook.py`, which is exactly what A-1 forbids above.

The reachable direction runs the other way. Antigravity is *admitted* by the server and ships two
adapters outside `EVENTS_BY_HARNESS` (`agy_hook.py`, `statusline_hook.py`), so a truthful
`input_requested` mapping in either was refused by the **oracle** while the server would have
accepted the envelope. Measured by mutation: a truthful `"tool_use": "input_requested"` row in
`statusline_hook.AGENT_STATES` plus `reports_needs_input=True` on the Antigravity spec turned three
assertions red, one of them the derived oracle whose whole job is to *demand* the flag. With the fix
in place the same mutation leaves two red, and they are the right two: the hand-written literal set,
and the prose count in `HarnessSpec`'s docstring, which drops from "Six of the ten" to five. A real
Antigravity gate build moves both by hand, and that is what they are for.

The oracle now reads adapter source across both shapes (`EVENTS_BY_HARNESS` for the hook-shaped
adapters, a module-level `HARNESS` plus its own map for the one-harness adapters) and intersects
the result with `IDENTITY_NORMALIZERS`, which is authoritative for admission. So it now covers the
unreachable direction as well, and neither table stands alone. It still reads Python, which is where
A-1 leaves it: a gate mapped in a JavaScript adapter is invisible to it, recorded as a limit in the
derivation's own docstring.

## A-3: four checks are blind to a non-Python adapter, and each is blind differently

Naming them together, because the first attempt at this listed three and the fourth is the one that
fails silently rather than loudly.

1. **The runtime-file inventory.** `CARGENTO_RUNTIME_FILES` is asserted equal to a discovery walk,
   and the walk globs `*.py` at the skill's top level. A bundled `.js` sibling is not discovered, so
   adding it to the inventory fails parity and omitting it means an install missing the adapter
   fails silently. Every non-`.py` entry the inventory carries today is under
   `cargento_runtime/web/` or is a hooks JSON, which is why the gap has never been hit.
2. **Syntax checking.** `scripts/lint_embedded.py` pins its web directory and runs `node --check`
   only over the bundle assembled from it. An adapter outside that directory ships with nothing
   verifying it parses.
3. **Hook vocabulary.** `HOOK_FILE_VOCABULARY` is keyed on JSON hook-file paths and read through a
   JSON loader. There is no seam a JavaScript file can enter, so a new validator that reads adapter
   source as text is required rather than an entry in the existing table.
4. **The harness-argument check.** One guard skips any hook command not containing the literal
   `event_hook.py`. An adapter under a different name silently skips the check that catches a hook
   command passing the wrong harness argument in another harness's hooks file. This is the blind
   spot that costs nothing to introduce and reports nothing when it matters.

A widening that satisfies only the first three leaves the fourth accepting anything.

## A-4: `EVENTS_BY_HARNESS` is a two-file edit

`event_hook.py` ships twice, in the plugin root and in the Gemini extension root, and the two are
byte-identical by validator rule. Editing one is a red build. Recorded here because the table reads
like a single constant and the second copy is in a directory nothing else about the event lane
touches.

---

## What this file does not decide

Whether any particular harness gets an adapter, and what its events are called. That is per-harness
build work with its own capture evidence, and it belongs to the issue for that harness. A-1 says
such an adapter *may* be JavaScript; it does not say any of them is.
