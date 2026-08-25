# Plan: the next UI behind `?next=true`

This is the execution map for the opt-in overview, project and session UI. Linear owns live status;
this file records the dependency order and disappears when DRC-4231 pins the finished bundle and
documents the shipped flag.

## Standing constraints

- `web/index.html`, `web/styles.css` and every `APP_PARTS` file stay byte-identical throughout the
  milestone.
- `tests/test_next_flag.py` and `tests/test_next_isolation.py` land in DRC-4217 and are not edited by
  later layers.
- At most two builder worktrees run at once. Full suites run serially.
- Each issue has one branch and one pull request. A stack follows a real dependency lane, and merges
  run from the bottom upward.
- Persistent history remains out of scope. CL has been told that history-backed regions are
  windowed or withheld after reload. [DRC-4234](https://linear.app/recce/issue/DRC-4234) owns the
  later decision about allowing persistent session history.

## Delivery waves

| Wave | Issues | Result |
|---|---|---|
| 1 | DRC-4217 | Separate loader, route, harness, packaging checks and origin firewall. This merges alone. |
| 2 | DRC-4223 and DRC-4218 | Measured start stamps in the payload lane, while the UI lane gains chrome, routes and its data loop. |
| 3 | DRC-4224 | Harness-gated token totals, after the scanner foundation. |
| 4 | DRC-4219 and DRC-4220 | Sessions and projects fill the two overview tabs in parallel. |
| 5 | DRC-4221 | Project view and one plan block per workflow. |
| 6 | DRC-4222 | Current and finished project activity. |
| 7 | DRC-4225 | Minimal session view and click-through from the flat list. |
| 8 | DRC-4226 and DRC-4228 | Windowed workstream history, plus local-only steer and guardrail controls. |
| 9 | DRC-4227 | Honest delegation state without invented history. |
| 10 | DRC-4229 | Live activity treatment for sessions and subagents. |
| 11 | DRC-4230 | Namespaced next-page stream election. Cut this parity layer first if the stack runs long. |
| 12 | DRC-4231 | Final byte oracles, shipped docs and deletion of this plan. This merges alone. |

DRC-4217 is a singleton stack based on `main`. After it merges, the payload and UI lanes start from
the new base. Converging layers are rebased locally before submission so every commit remains
DCO-signed, then merged only when the current head is clean and its required checks are green.
