# Project cockpit substrate survey

This is a read-only mechanism survey. It does not select or present a UI. The earlier files under `docs/breadboards/project-cockpit/` are historical mock evidence and do not prove availability.

Run the structural probe against an existing local Cargento:

```bash
python3 docs/probes/project-cockpit/substrate_probe.py --port 4553
```

The probe prints no project labels, session ids, questions, options, goals, prompts, or local paths. It never starts a server, registers an ask, invokes a model, or writes an observer sidecar.

## Inventory

| Proposed datum or mechanism | Current source | Availability | Freshness | Identity mapping | Persistence owner | Trust boundary |
|---|---|---|---|---|---|---|
| Project label | Each collector publishes `sessions[].project`; the regular page groups exact label strings | Available, derived | Recomputed on every collection; inherits the member session timestamps | Display label only; no stable project id; collectors converge through `project_from_cwd` or a store-label fallback | None | Harness stores contain untrusted paths and labels; collectors bound them before publication |
| Project grouping | `regular.js projectGroups()` over `/api/data sessions[]` | Available, derived | Every payload revision | Exact string equality on project label | Browser memory for the current render | Same-origin payload; a label collision merges unrelated sessions |
| Project filter | `cargento.projectFilter` in browser `localStorage` | Available | Read at page load, written on filter change | Exact project label | Browser origin | Browser-owned; server cannot inspect or reconcile it |
| Active session membership | Collector `active`, `state`, and `last_activity` fields | Available, measured per collector | Payload identifies generation time; thresholds are collector-specific but frozen in runtime config | Authoritative row key is `(harness, sid)`; display id is not a key | None beyond harness stores | Mixed harness stores; dedupe chooses the freshest copy of a repeated key |
| Session title and current detail | Collector `title`, `last_prompt`, `state_detail` | Partly available | Collector scan or event overlay revision | `(harness, sid)` | Harness store or in-memory overlay | Agent-authored text, escaped only at the page boundary |
| Outstanding ask capability | Running process publishes `ask: true` | Available on the measured daemon | Process lifetime | Registry-generated ask id | `AskRegistry` process memory | Loopback HTTP; registration fields are agent-authored and bounded at ingress |
| Outstanding ask list | Running process publishes `asks[]` | Available but empty in the read-only measurement | Collection after register, answer, withdraw, or expiry | Registry id plus caller-supplied harness, session id, and project | `AskRegistry` process memory; no restart persistence | Caller attribution is not joined authoritatively to `sessions[]` |
| Ask-to-project ownership | Registration payload's `project` string | Available as a claim, not a verified join | Fixed for one ask's lifetime | Caller-supplied string; no project id | Ask registry | Agent/MCP boundary; current server does not prove it matches the asking session |
| Reassign ask to another project | No Cargento route or registry operation | Unavailable | — | — | — | The historical mock's `projectId` mutation is fixture-only and is not product evidence |
| Needs-you from asks | Page queue reads outstanding ask cards; session `needs_input` is a separate collector state | Available, but two distinct signals | Ask registry revision versus collector/event revision | Ask id versus `(harness, sid)` | Process memory and harness stores | Joining the two without a measured identity match can attribute attention incorrectly |
| Observer deterministic goal | Real Claude or Pi transcript through `observer.analyze()` | Available for transcripts `resolve_transcript()` can find | On-demand transcript read | `(harness, sid)` resolves to one transcript; workflow entity dir comes from boot records | None in the read-only probe | Agent-authored transcript; deterministic latest directive can still be stale or incomplete |
| Observer model goal and memory | `/api/observe` model callers | Conditionally available, not exercised here | On demand | Same session mapping as deterministic observer | Sidecar under Cargento state home | Transcript leaves the local process for the configured model gateway; failure falls back or empties memory |
| Observer stage and block | Entity frontmatter plus bounded transcript keyword scan | Partly available | On-demand read | Boot envelope joins transcript to workflow/entity directory | Sidecar only when `/api/observe` writes | Entity state and transcript are untrusted local files; block is lexical, not semantic |
| Session causal history | Spacedock boot records and entity gate metadata in `session.spacedock` | Available only for detected workflow sessions | Collector scan | Workflow/entity paths from boot envelopes; entity slug within workflow | Workflow state checkout | Paths and frontmatter are untrusted; bounded readers and file caps apply |
| Operator-authored project goal | No shipped key, schema, writer, or reducer | Unavailable | — | No project id exists to key it safely | Unchosen | Browser `localStorage` would be origin-local and invisible to the server |
| Goal reload and observer-conflict precedence | Historical mock only | Unavailable | — | Mock project id | Mock browser store | Fixture behavior cannot establish a production trust rule |
| Steering or direct session input | No Cargento delivery transport | Unavailable | — | No registered channel in current runtime | Unchosen | The interaction-origin prototype is a client-state fixture, not a measured Cargento mechanism |

## Read-only measurement

On 2026-08-24, the existing daemon on `127.0.0.1:4553` published 13 active sessions across 7 non-empty project labels. Claude, Codex, Pi, and Antigravity stores were discovered with no collector error. The payload advertised the ask capability and contained zero outstanding asks, so this run proves the empty live registry surface but not a register-to-card round trip.

The deterministic observer probe resolved a real local Claude or Pi transcript without invoking a model or writing a sidecar. Its report records only structural outcomes and freshness; it deliberately omits the derived goal and local path.

## Failure modes and missing mechanisms

- Project labels are presentation strings, not stable identities. Same-label worktrees can merge, and the ask registry accepts a project claim without joining it to a session row.
- A session can be active while its `last_activity` reflects a child; `own_activity` and overlay rules are needed before interpreting that as direct progress.
- A zero-length ask list means no question was pending at the measured revision. It does not prove registration, attribution, answer, withdrawal, or restart behavior.
- Observer output is session-scoped. It provides no project-level remembered goal, and its model-enhanced fields cross a network/model trust boundary.
- Browser project-goal persistence has no shipped schema or conflict rule. Existing project-filter persistence does not make project-goal persistence available.
- Ask reassignment and direct session steering do not exist in the current runtime. Historical fixture reducers must not be promoted into the substrate.

## Smallest demonstrated substrate for shaping

Shaping may build on a read-only project index derived from the live `/api/data sessions[]` payload:

1. Group by the existing project label, while displaying it as a fallible label rather than an id.
2. Key every session by `(harness, sid)` and carry the collector's `active`, `state`, and freshness fields without re-deriving liveness.
3. Show outstanding asks as a separate process-memory lane only when `ask: true`; preserve their caller-supplied attribution as an unverified claim.
4. Link to the existing session observer and Spacedock detail as session-scoped drill-down, labeling deterministic, model-derived, and unavailable fields separately.

Shaping must not include an operator-owned project goal, ask reassignment, project-level observer synthesis, or direct steering until those mechanisms have an explicit identity key, persistence owner, conflict rule, and exercised trust boundary.
