# Future UI Command Surface Design

**Status:** Captain-approved on 2026-08-31; corrected after crucible review on 2026-08-31

## Purpose

The `?next=true` surface must answer a command question before it presents inventory, but it must
not manufacture a command frame when the payload has no command fact. The overview answers,
“Where does my attention belong?” A project shows workflow only when Spacedock supplies it. A
session leads with what the agent is doing now, then progressively discloses assignment, next
action, and human response only when their owning sources publish them.

This correction replaces the first prototype's always-present captain lede, workflow absence
panel, and four equally weighted session cells. Those mechanisms made bounded absence copy feel
like operational evidence.

## Evidence boundary

The browser may render only facts present in the current API payload. It must not infer intent from
a project name, treat a clipped title as a durable assignment, infer a next action from activity
narration, or turn an absent workflow record into proof that no workflow exists.

The source owners are:

- Codex command facts: `Codex transcript`
- Claude command facts: `Claude transcript`
- Antigravity command facts: `AGY CLI log`
- Outstanding requests: the payload's exact `asks` records
- Spacedock workflow and authority context: a session's non-null Spacedock record

An instruction whose label is `asked` is a published assignment. The full instruction remains
authoritative when a shorter title echoes it. `agent` and `earlier` instructions are execution
context, not assignments. The first in-progress or pending task is a published next action. Missing
facts are not primary cards; plain-language source ownership belongs in a collapsed source-coverage
disclosure.

## Captain and request semantics

The captain and first officer ruled that an exact ask from any harness remains operationally
important. It may lead the overview as `NEEDS YOU — <question>`. `CAPTAIN` wording and authority
semantics require both an exact ask and positive Spacedock evidence on its owning session or
project. Without an exact ask, the overview has no request lede at all.

Project rows use the same evidence-backed label. If there is no response to request, the row omits
the `RESPONSE` region and reflows its situation rather than leaving an empty labeled column.
Projects remain ordered by exact asks, executing sessions, needs-input signals, then idle sessions.
An unmatched needs-input signal may describe its bounded situation but cannot invent a request.

## Project workflow disclosure

A project has workflow evidence only when one of its sessions carries a non-null Spacedock record.
With no such record, the entire workflow region and its wrapper are omitted. This is not an error
state and does not warrant “source unavailable” copy.

When Spacedock evidence exists, the project renders the concrete workflow strips and plans in that
record. If the record has no renderable plan, the existing first-officer or ensign role may support
its role-specific context. A generic empty workflow panel is never shown.

## Session command hierarchy

The session title remains identity and context. Directly below it, an always-present `CURRENT
ACTIVITY` lede renders the known state and detail. An `agent` or `earlier` instruction may appear
there with its qualifier as execution context.

Below the lede, the session renders only supported command facts:

1. `ASSIGNMENT`: the full `asked` instruction, when published.
2. `NEXT`: the first in-progress task, then the first pending task, when published and no exact ask
   supersedes it.
3. `NEEDS YOU`: the exact ask for a plain session, or `CAPTAIN` when that session also carries
   Spacedock evidence.

An exact ask is one response fact, not duplicated as both next action and captain response. When
assignment or next-action evidence is absent, a collapsed `SOURCE COVERAGE` details element may
state in plain language that the named transcript or log did not publish it. The disclosure stays
secondary and does not expose internal field or schema names.

Health warnings, answer controls, tasks, subagents, and token evidence remain below this hierarchy.
All untrusted text is escaped at render sites.

## Live refresh recovery

A single failed `/api/data` attempt remains quiet. After two consecutive failures, the surface
keeps the last successful payload visible and explains that the live refresh failed twice, so the
displayed data may be stale. It must not claim the event stream stopped: the failure boundary also
catches HTTP errors, JSON parsing, and local observation failures.

When a prior success time is known, the notice reports how long ago the displayed data was last
successfully received. It states the active automatic retry cadence: 20 seconds when event streams
are available, or 5 seconds for the legacy polling path. A `Retry now` button invokes the same
single refresh path and is disabled while that attempt is in flight, preventing overlapping manual
retries. Any successful refresh clears the failure count and the notice.

## Visual treatment

The current-activity lede is visually dominant. Optional command facts form a compact, reflowing
group below it. Source coverage uses a native collapsed details control. Semantic labels remain
visible at narrow widths, source qualifiers wrap, project rows remain keyboard-clickable, and the
refresh notice is an accessible status with a normal button.

## Verification

Behavior tests must fail against the rejected candidate before production code changes and prove:

- a plain exact ask leads with `NEEDS YOU`, while the same ask with Spacedock evidence uses
  `CAPTAIN`;
- no ask produces no top-level request lede or empty project response column;
- a plain project omits the workflow region; positive Spacedock records retain concrete or
  role-specific context;
- current activity leads every session, supported assignment/next/request facts appear only when
  present, and missing facts live only in collapsed plain-language source coverage;
- an exact ask is not duplicated as a next action;
- the first refresh failure is quiet; the second explains the exact boundary, retained/stale view,
  age and cadence; manual retry cannot overlap; and recovery clears the notice.

After focused tests pass, derive every changed frontend part's byte size and SHA-256 plus the
assembled page pins mechanically. Capture the overview, project, and the same Codex, Claude, and
AGY session identities in Chrome from the committed candidate bytes.

## Non-goals

This prototype does not add a sidecar model, synthesize a semantic timeline, change the stable UI,
alter collector payloads, invent estimates, confidence, delegation, workflow, intent, authority,
or causal links, or diagnose the transport beyond the observed refresh failures.
