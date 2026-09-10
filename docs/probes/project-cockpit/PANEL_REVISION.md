# Project cockpit panel revision

Checkpoint under review before revision: `196fecf0034d30f5c8074007425a4f36193d22a2`.
Focused identity: `codex:01a035ee-2a7b-76f0-873f-eaddc97860c3` inside the exact
project label `spacedock-research/cargento`.

Both independent reviewers inspected the live HTTP artifact, DOM behavior, API responses, and
checkpoint source. No controllable browser was available. Their scores and the evidence below do
not claim verified visual layout, spacing, responsive behavior, or perceived color contrast.

## Independent panel

| Lens | Score | Direction | Three highest-severity findings |
|---|---:|---|---|
| Information architecture | 3/5 | REVISE | Cold permalink was not authoritative; a browser-local exact-label note was overclaimed as project authority; present state, recency, and handoff were conflated. |
| User experience | 3/5 | REVISE | The focused route was unreliable; active/working/recent terminology was misleading; a meta record was falsely presented as captain-authored steering. |

Shared findings were the critical cold-route failure and unclear temporal semantics. The IA advisor
uniquely emphasized information ownership and returning to work. The UX expert uniquely identified
the concrete provenance falsifier plus busy-state, focus, and live-announcement gaps. The only
material disagreement was chronology: IA found the source structure sound, while UX found one
rendered meta row that invalidated the authorship claim. The concrete rendered counterexample took
precedence.

The panel also found the project-to-focused-session hierarchy, operator-before-observer ordering,
and explicit needs-captain uncertainty sound. The revision preserves those parts.

## Severity-ranked revision

1. URL `mode`, `project`, and `session` now override browser fallback state. Sibling focus remains
   inside the project cockpit and participates in browser history.
2. Present `working now` and `needs captain` are separated from the 24-hour `recent` window and
   recent-idle sibling context.
3. Known system, environment, permissions, skills, apps, plugin, recommendation, and repository
   instruction wrappers are excluded from steering. Remaining user-role rows use weak provenance.
4. The browser-local exact-label field is an operator note remembered in this browser, not durable
   project authority. It still precedes observer inference.
5. The focused mirror separates demonstrable present state, browser-local outcome note, observer
   inference, needs-captain evidence, and unavailable stage/block/outcome boundaries.
6. Observer refresh has an immediate busy state. Refresh, copy, and save outcomes use one polite
   live region, and rerenders restore the focused project control.
7. Codex child lifecycle now uses recorded `task_started`, `task_complete`, and `turn_aborted`
   boundaries. Current Codex metadata's root-session and child-thread identities are retained
   separately so nested children attach to their real top-level session.

## Controlled canary ledger

The earlier Aristotle canary demonstrated the defect: it appeared while live, stayed labeled
running after completion until the 90-second rollout-mtime threshold, then vanished with no history.

The revised Turing canary was sampled through `127.0.0.1:8766/api/data` without reading or reporting
private transcript text:

| Phase | Sample epoch | Carrier session | Sanitized API evidence | Rollout evidence |
|---|---:|---|---|---|
| Before | 1787670765.031 | `01a035ee-2a7b-76f0-873f-eaddc97860c3` | `working`; `running 1 subagent`; child `Volta` | Turing's previous signal was terminal. |
| During | 1787670784.370 | same | `working`; `running 2 subagents`; children `Volta`, `Turing`; both reported `gpt-5.6-sol` | Turing's last signal was `task_started`. |
| After | 1787670838.620 | same | `working`; `running 1 subagent`; child `Volta`; Turing absent | Turing's last signal was `task_complete`; sample was 11.349 seconds after child mtime, inside the old 90-second window. |

This proves visible spawn/activity and immediate terminal retirement for one bounded real nested child.
It does not establish durable completed/interrupted history; no such history is published.

## Remaining unavailable boundaries

- Visual layout and appearance are unverified because no controllable browser was available.
- Workflow stage, open block, and achieved outcome remain unavailable unless a real source reports
  them. The page does not infer them from motion or steering.
- A user-role transcript record does not mechanically establish captain authorship.
- The operator note remains local to this browser origin and exact project label. It can collide
  across same-label checkouts or become orphaned after a label change.
- AskRegistry and event overlays remain process-local, source-bounded signals. Their absence is not
  proof that a session is unblocked.
- Codex completion/interruption history is not published. Only currently open child turns are shown.
