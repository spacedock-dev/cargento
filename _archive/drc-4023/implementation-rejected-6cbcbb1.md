# C4 implementation pre-PR review: rejected candidate 6cbcbb1

Candidate: 6cbcbb199d4bda169ac3084c6f811d1b430b052f; base: d5b52abad006972a14df778573cd3abfe9d4f78d. Implementation status and seven approved ACs unchanged. This is an implementation review correction, not a review-gate rejection.


## Preserved review-population.md

# Independent population/retention lens
Reviewer: /root/spacedock_ensign_drc_4023_implementation/c4_population_review
Candidate: 6cbcbb199d4bda169ac3084c6f811d1b430b052f
Disposition: no reproducible blocker.
Probe: rtk proxy python3 -B -, existing NextIntentRefreshTest.run_case assembled-page harness.
Setup retained codex:live-1 annotation with assessment revision_read=1; invalidate/reload to establish assessment.
Transitions: rename project + claude same SID + board-only no project; depart codex while annotation revision unchanged; return codex without project with changed cached goal, same annotation revision; depart then evict annotation with changed revision.
Observed keys/counts/fetches: rename [codex:live-1,claude:live-1,codex:board-only],3rows,2fetches; depart [claude:live-1,codex:live-1],2rows,2fetches; return same2keys,2fetches; evict [claude:live-1],1row,3fetches.
Board/departed totals3/0,1/1,2/0,1/0. First3 states retain exact reading denominator1of1holdswords. Cached source disappears on departure/changes on return. No-project return has correct present label. Eviction removes withdrawn words+reading and says No retained annotation carries a reading.
First probe failed because it rejected substring carries a reading inside correct negative sentence; corrected probe assertion passed exit0, candidate unchanged.
Limits: assembled DOM harness, no additional browser/API run; no full suite/edits/commits/agents.

## Preserved review-source.md

# Independent source/publication lens
Reviewer: /root/spacedock_ensign_drc_4023_implementation/c4_source_review
Candidate: 6cbcbb199d4bda169ac3084c6f811d1b430b052f
Four fields: dashboard reader refreshes board with malformed current-session observer cache; whole Application.collect raises RecursionError preventing bad and healthy rows; value-ac[AC-3] malformed→unavailable and AC1 membership; actual60,012-byte UTF8 sidecar with unused nested array depth30,000 under65,536 cap.
Existing read_sidecar leaked decoder recursion; C4 newly invokes it via aggregate._attach_cached_goals outside per-harness boundary on every collection.
Reproduction: make_runtime(state_dir=temp, annotations_enabled=False,dismissals_enabled=False), injected Pi collector returning base_session bad+healthy; real Application.collect(show_all=True) and sidecar reader.
Output:
control rows ['bad', 'healthy']
nested collection failed RecursionError maximum recursion depth exceeded while decoding a JSON array from a unicode string
recovery rows ['bad', 'healthy']
Malformed local cache synthetic; no shipped producer shown to create nesting. Materiality referred to arbiter. No other blocker from producer/source inspection; no candidate mutation/fullsuite/agents/repeated green checks.

## Preserved arbiter/disposition.md

Disposition: CONFIRMED, current C4 blocker (P2); narrow fix, not defer.
Candidate: 6cbcbb199d4bda169ac3084c6f811d1b430b052f
Base: d5b52abad006972a14df778573cd3abfe9d4f78d

Four fields:
1. Trigger: ordinary Application.collect(show_all=True), annotations and dismissals disabled, two current Pi sessions, bad session observer sidecar containing an unexpected deeply nested JSON field. Actual UTF-8 file: {"unused": + 30,000 [ + 0 + 30,000 ] + }, 60,012 bytes under existing 65,536 cap. Synthetic invalid sidecar shape; not claimed to be produced by the shipped writer.
2. Observed effect: candidate control publishes bad and healthy; nested file raises RecursionError through aggregate.py:802 -> :575 -> observer.py:973 -> :958 before collection returns; deletion restores both. Identical probe on base publishes both with nested file present. This proves ordinary collection regression, not production prevalence, browser rendering, or remote exploitability.
3. Obligation: value-ac[AC-3] malformed cached evidence is unavailable under bounded admission; AC-1 current board membership is collateral damage when the whole collection fails.
4. Evidence: reproduce.py, commands.txt, candidate.txt, base.txt in this directory. Python 3.12.13; real file and decoder, no decoder mock, no producer or repository mutation.

Ownership/materiality: read_sidecar exception omission predates C4, but C4 newly imports it into every ordinary board collection outside the per-harness failure boundary. The base comparison establishes this change owns the new board-wide failure. Impact persists on every collection while the bad cache exists. Local synthetic corruption limits likelihood/severity; it does not negate the explicit malformed-evidence admission contract. P2 correctness blocker, not security escalation.

Proposed minimum repair: add RecursionError to read_sidecar decoding failure exceptions so it returns None, plus one real-sidecar regression proving collection preserves the bad row with cached_deterministic_goal=None and the healthy row. Avoid broad catch in aggregate or changes to producers, schema, thresholds, UI, or stores. Retest through this retained arbiter handle if separately authorized. No candidate edits or commits performed.

## Arbiter commands.txt

```text
rtk proxy python3 -B /var/folders/pw/_rjswpfn53s0_xyrwtz8jvh00000gn/T/drc-4023-c4-arbiter-oznbgun7/reproduce.py /Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023
rtk proxy python3 -B /var/folders/pw/_rjswpfn53s0_xyrwtz8jvh00000gn/T/drc-4023-c4-arbiter-oznbgun7/reproduce.py /Users/jaredmscott/repos/recce/cargento

```

## Arbiter candidate.txt

```text
candidate exit=0
ROOT /Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023
control rows [('bad', None), ('healthy', None)]
FILE_BYTES 60012 READ_CAP 65536
nested FAILED RecursionError maximum recursion depth exceeded while decoding a JSON array from a unicode string
Traceback (most recent call last):
  File "/var/folders/pw/_rjswpfn53s0_xyrwtz8jvh00000gn/T/drc-4023-c4-arbiter-oznbgun7/reproduce.py", line 16, in collect
    result = app.collect(show_all=True)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023/cargento/skills/cargento/cargento_runtime/aggregate.py", line 802, in collect
    _attach_cached_goals(config, out_sessions)
  File "/Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023/cargento/skills/cargento/cargento_runtime/aggregate.py", line 575, in _attach_cached_goals
    row["cached_deterministic_goal"] = observer.cached_deterministic_goal(
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023/cargento/skills/cargento/cargento_runtime/observer.py", line 973, in cached_deterministic_goal
    cached = read_sidecar(config, harness, sid) or {}
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023/cargento/skills/cargento/cargento_runtime/observer.py", line 958, in read_sidecar
    value = json.loads(handle.read(config.state_read_cap_bytes))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jaredmscott/.pyenv/versions/3.12.13/lib/python3.12/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jaredmscott/.pyenv/versions/3.12.13/lib/python3.12/json/decoder.py", line 338, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jaredmscott/.pyenv/versions/3.12.13/lib/python3.12/json/decoder.py", line 354, in raw_decode
    obj, end = self.scan_once(s, idx)
               ^^^^^^^^^^^^^^^^^^^^^^
RecursionError: maximum recursion depth exceeded while decoding a JSON array from a unicode string
recovery rows [('bad', None), ('healthy', None)]

```

## Arbiter base.txt

```text
base exit=0
ROOT /Users/jaredmscott/repos/recce/cargento
control rows [('bad', None), ('healthy', None)]
FILE_BYTES 60012 READ_CAP 65536
nested rows [('bad', None), ('healthy', None)]
recovery rows [('bad', None), ('healthy', None)]

```

## Arbiter reproduce.py

```text
from pathlib import Path
import sys, tempfile, traceback
root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "cargento/skills/cargento"), str(root)]
from cargento.skills.cargento.tests.support import make_runtime
from cargento_runtime.aggregate import Application, HarnessSpec
from cargento_runtime.sessions import base_session
from cargento_runtime import observer
print("ROOT", root)
with tempfile.TemporaryDirectory(prefix="drc-4023-arbiter-state-") as state_dir:
    config, state = make_runtime(state_dir=Path(state_dir), annotations_enabled=False, dismissals_enabled=False)
    spec = HarnessSpec(key="pi", label="Pi", discover=lambda *_: True, collect=lambda *_: [base_session("pi", "bad", "example"), base_session("pi", "healthy", "example")])
    app = Application(config, state, (spec,), native_notifier=lambda *_: "", popup_notifier=lambda *_: None, diagnostic_sink=print)
    def collect(label):
        try:
            result = app.collect(show_all=True)
            print(label, "rows", [(r["sid"], r.get("cached_deterministic_goal")) for r in result["sessions"]])
        except Exception as exc:
            print(label, "FAILED", type(exc).__name__, str(exc))
            traceback.print_exc(file=sys.stdout)
    collect("control")
    path = Path(observer.sidecar_path(config, "pi", "bad"))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = '{"unused":' + '[' * 30000 + '0' + ']' * 30000 + '}'
    path.write_text(payload, encoding="utf-8")
    print("FILE_BYTES", path.stat().st_size, "READ_CAP", config.state_read_cap_bytes)
    collect("nested")
    path.unlink()
    collect("recovery")

```
