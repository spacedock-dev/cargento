PASS — narrow authorized C4 correction re-review
Exact candidate HEAD: 09cd65de9917962d86bd9a7892ac963506679904
Previous reviewed HEAD: 6cbcbb199d4bda169ac3084c6f811d1b430b052f

The sole runtime correction adds RecursionError to read_sidecar failure handling. It returns None for the reported decoder failure without widening the catch to unrelated aggregate failures or changing source admission, caps, UI, or stores.

Independent retained reproduction: real 60,012-byte nested JSON file under 65,536-byte cap now permits Application.collect(show_all=True) to publish both bad and healthy rows, with None cached evidence, before and after file deletion. See corrected-probe.txt and reproduce.py.

New committed regression: ran only PublishedSessionFieldSetTest.test_malformed_cached_goal_cannot_remove_any_board_session; 1 test passed. Its assertions verify both session identities, unavailable cached evidence, and byte-preserving retention of the corrupt file.

Regression negative control: removed only the RecursionError exception arm from an in-memory compiled copy of read_sidecar, without editing the candidate. The same new test then produced exactly 1 error, RecursionError, at Application.collect through cached_deterministic_goal. See regression-negative.txt. The driver reports exit 0 because this expected failure is asserted. Initial negative-control setup failed before testing because the compiled copy lacked postponed annotations; retained in regression-negative-harness-setup-error.txt. Corrected scratch driver restored the original future-annotations compilation context; that setup failure is not candidate evidence.

Disposition: previously confirmed finding is resolved and regression test is effective. No new finding in this bounded re-review. No candidate edits, commits, full-suite reruns, additional agents, or immutable correction-room edits.

## commands.txt

```text
rtk proxy python3 -B /var/folders/pw/_rjswpfn53s0_xyrwtz8jvh00000gn/T/drc-4023-c4-arbiter-retest-09cd65d-ckb_x3cu/reproduce.py /Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023
rtk proxy python3 -B /var/folders/pw/_rjswpfn53s0_xyrwtz8jvh00000gn/T/drc-4023-c4-arbiter-retest-09cd65d-ckb_x3cu/regression_check.py /Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023 current
rtk proxy python3 -B /var/folders/pw/_rjswpfn53s0_xyrwtz8jvh00000gn/T/drc-4023-c4-arbiter-retest-09cd65d-ckb_x3cu/regression_check.py /Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023 negative

```

## corrected-probe.txt

```text
corrected-probe exit=0
ROOT /Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023
control rows [('bad', None), ('healthy', None)]
FILE_BYTES 60012 READ_CAP 65536
nested rows [('bad', None), ('healthy', None)]
recovery rows [('bad', None), ('healthy', None)]

```

## regression-green.txt

```text
regression-green exit=0
test_malformed_cached_goal_cannot_remove_any_board_session (cargento.skills.cargento.tests.test_sessions.PublishedSessionFieldSetTest.test_malformed_cached_goal_cannot_remove_any_board_session) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.066s

OK
MODE current tests 1 errors 0 failures 0

```

## regression-negative-harness-setup-error.txt

```text
regression-negative exit=1
Traceback (most recent call last):
  File "/var/folders/pw/_rjswpfn53s0_xyrwtz8jvh00000gn/T/drc-4023-c4-arbiter-retest-09cd65d-ckb_x3cu/regression_check.py", line 13, in <module>
    exec(compile(source, "<in-memory-prior-reader>", "exec"), namespace)
  File "<in-memory-prior-reader>", line 1, in <module>
NameError: name 'RuntimeConfig' is not defined. Did you mean: 'RuntimeWarning'?

```

## regression-negative.txt

```text
regression-negative exit=0
test_malformed_cached_goal_cannot_remove_any_board_session (cargento.skills.cargento.tests.test_sessions.PublishedSessionFieldSetTest.test_malformed_cached_goal_cannot_remove_any_board_session) ... ERROR

======================================================================
ERROR: test_malformed_cached_goal_cannot_remove_any_board_session (cargento.skills.cargento.tests.test_sessions.PublishedSessionFieldSetTest.test_malformed_cached_goal_cannot_remove_any_board_session)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023/cargento/skills/cargento/tests/test_sessions.py", line 1513, in test_malformed_cached_goal_cannot_remove_any_board_session
    rows = app.collect(show_all=True)["sessions"]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023/cargento/skills/cargento/cargento_runtime/aggregate.py", line 802, in collect
    _attach_cached_goals(config, out_sessions)
  File "/Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023/cargento/skills/cargento/cargento_runtime/aggregate.py", line 575, in _attach_cached_goals
    row["cached_deterministic_goal"] = observer.cached_deterministic_goal(
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jaredmscott/repos/recce/cargento/.worktrees/spacedock-ensign-drc-4023/cargento/skills/cargento/cargento_runtime/observer.py", line 973, in cached_deterministic_goal
    cached = read_sidecar(config, harness, sid) or {}
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<in-memory-prior-reader>", line 9, in read_sidecar
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

----------------------------------------------------------------------
Ran 1 test in 0.049s

FAILED (errors=1)
MODE negative tests 1 errors 1 failures 0

```

## regression_check.py

```text
from pathlib import Path
import sys, inspect, unittest
root=Path(sys.argv[1])
sys.path[:0]=[str(root / "cargento/skills/cargento"), str(root)]
from cargento.skills.cargento.tests import test_sessions
from cargento_runtime import observer
if sys.argv[2] == "negative":
    source=inspect.getsource(observer.read_sidecar)
    expected="except (OSError, ValueError, json.JSONDecodeError, RecursionError):"
    assert source.count(expected)==1
    source=source.replace(expected, "except (OSError, ValueError, json.JSONDecodeError):")
    namespace=observer.__dict__.copy()
    exec(compile("from __future__ import annotations\n" + source, "<in-memory-prior-reader>", "exec"), namespace)
    observer.read_sidecar=namespace["read_sidecar"]
suite=unittest.TestSuite([test_sessions.PublishedSessionFieldSetTest("test_malformed_cached_goal_cannot_remove_any_board_session")])
result=unittest.TextTestRunner(verbosity=2).run(suite)
print("MODE", sys.argv[2], "tests", result.testsRun, "errors", len(result.errors), "failures", len(result.failures))
if sys.argv[2] == "negative":
    assert result.testsRun==1 and len(result.errors)==1 and "RecursionError" in result.errors[0][1] and not result.failures
else:
    assert result.wasSuccessful()

```

## reproduce.py

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
