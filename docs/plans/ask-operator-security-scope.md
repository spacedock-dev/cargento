# The ask lane: security scope, written before the code

Foundation ticket for the input power DEC-2 ([DRC-4054](https://linear.app/recce/issue/DRC-4054/dec-2-decision-let-cargento-act-not-just-observe))
allowed on 2026-08-22, in one shape only: the session asks, Cargento answers. The build is
[DRC-4172](https://linear.app/recce/issue/DRC-4172/let-a-session-ask-cargento-a-question-and-wait-for-the-answer-dec-2s).

This document is documentation only. It exists so the implementation PR is held to a published
standard instead of writing its own, which is what DEC-2 means by "the amendment lands before the
code, as DEC-1's did".

Home of the contract, on the precedent DEC-1 set with DRC-4061: the section below is drafted here
verbatim, the build PR promotes it into `SECURITY.md` unchanged, and deletes this file. `SECURITY.md`
therefore keeps describing only shipped behaviour at every commit, while the contract is still settled
and reviewable before any code exists. That precedent's own plan doc, `quota-fetch-security-scope.md`,
is deliberately not linked here: it no longer exists, because the fetcher PR deleted it on promotion,
which is the same thing this file expects to happen to it.

## What was measured first, and what it changed

DEC-2's approval rests on a 150 second hold measured on two harnesses. That measurement was re-run
attended before this contract was written, because the original was taken on a path no user is on:
headless `claude -p` with permissions pre-granted, and Codex under `approval: never` with
`sandbox: danger-full-access`. Captures:
[`../captures/claude/mcp-ask-gate-2.1.239-macos.jsonl`](../captures/claude/mcp-ask-gate-2.1.239-macos.jsonl)
and [`../captures/codex/mcp-ask-gate-0.146.1-macos.jsonl`](../captures/codex/mcp-ask-gate-0.146.1-macos.jsonl).

The hold survives. The premise does not survive unqualified, and the difference is a security fact
rather than a scheduling one.

On both harnesses, at default permission settings, the first `ask_operator` call raises a gate in the
user's own terminal, and it raises it *before* the call reaches the MCP server. The server saw
`tools/list` and then nothing at all until a human answered in the terminal. So on a first call there
is nothing for the dashboard to show, and the reader has to walk to the terminal anyway, which
unblocks the agent by their presence and defeats the point of asking.

The gate is once per directory, not once per call. Claude offers "Yes, and don't ask again", which
writes `permissions.allow: ["mcp__<server>__<tool>"]` into the project's
`.claude/settings.local.json`; Codex offers "Always allow". After the grant, the call reaches the
server with no human involved and holds correctly.

Three consequences the contract has to carry. The allow-list entry is part of what ships, not a
footnote, because without it the feature is a no-op at default settings. Granting it is the user
handing Cargento a standing permission, so it belongs in the security document rather than only in a
setup guide. And the grant is scoped to a directory, so it is not a global switch and the document
should not describe it as one.

A stdio server spawned by Claude Code inherits `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PROJECT_DIR` and
`AI_AGENT`, measured in a fresh interactive session. That is where a question card's attribution comes
from, and it matters here because a card that cannot say which session is waiting is unanswerable
under this repository's normal workload of several agents at once.

## Two counts in `SECURITY.md` are already wrong, and must be recounted rather than incremented

Before adding anything, the build PR fixes these. Both were wrong before this feature existed, and
incrementing them would preserve the error.

`SECURITY.md` line 10 says "Three small forwarders ship beside it", then names four
(`notify_hook.py`, `event_hook.py`, `agy_hook.py`, `statusline_hook.py`), then says "All four share
one transport" in the same paragraph. The count is four.

`SECURITY.md` line 28 says "Three endpoints mutate", then enumerates `POST /api/notify`,
`POST /api/usage` and `POST /api/events/<harness>`, and then calls `POST /api/dismiss` "the third"
when it is the fourth. The count is four today.

The ask lane adds two routes, so the sentence becomes six, and an MCP stdio server is not a forwarder
and does not share the four's one transport. It needs its own sentence in Scope rather than joining
that list.

## The shape the contract is written against

Decided at kickoff, because the security properties depend on it.

The wait is a bounded long poll, not one held request. The MCP server registers the question with a
fast POST that returns an id, then re-polls with a short deadline until the tool deadline expires.
This is the server to dashboard hop only. The harness holds its own stdio call for the whole
deadline, and the dashboard never sees that connection.

The reason is that a single 150 second held request would require three things the runtime does not
have: a bound on concurrent holds, since `ThreadingHTTPServer` spawns a thread per request and the
only concurrency budget anywhere is `stream_max_clients`; a release with a decline wired into both
`_shutdown` and `lifecycle.serve`'s finally block, since handler threads are daemons that nothing
joins and a stop today would drop the connection rather than answer it; and a read deadline on the
accept path, since a peer that declares a small `Content-Length` and then goes silent pins a handler
indefinitely. A poll that returns in seconds makes all three ordinary.

The answer is an index, never a string. The options are stored server side when the question is
registered. The answer body carries the question id and an integer index, an out of range index is a
no-op, and the MCP server returns `options[index]` from its own copy of the list. This is the load
bearing security decision in the whole feature: if the route accepted an option string that became
the tool result, it would be a general purpose channel for putting attacker chosen text into any
local agent's context, bounded only by a body cap. As an index, the worst a forged answer can do is
choose the wrong one of the options the agent itself offered.

## The section to promote into `SECURITY.md`

Verbatim. It goes after Dismissals and before Known and accepted, matching how the quota section was
scoped: exactly what is read, exactly what is sent, hard boundaries.

---

### The ask lane (`ask_operator`)

Cargento ships one MCP tool. A session that wants a human decision calls `ask_operator`, and the
question appears in the dashboard for the reader to answer. This is the only path by which anything
a reader does in Cargento reaches a running session, and it exists because the session asked.

What it is, precisely. Cargento ships a stdio MCP server beside the dashboard. It is not one of the
four forwarders and shares none of their transport. A harness spawns it, it speaks JSON-RPC on stdin
and stdout, and it holds the agent's tool call open while the question is outstanding. It registers
the question with the dashboard over loopback and polls for the answer.

The direction is the invariant. Cargento never reaches into a session. A session can only ever be
waiting because it asked to be, and a session that never calls the tool is untouched by all of this.
Nothing is typed into a terminal, no harness store is written, and the tool cannot answer a native
permission prompt. That last point is not a limitation to be lifted later: answering a harness's own
gate is refused, and the four probes DEC-2 filed are research rather than a roadmap.

What the reader's click can and cannot say. The question's options are recorded when the question is
registered. An answer names the question and an option by index, and the MCP server returns its own
copy of that option to the agent. An answer cannot introduce text. The strongest thing a forged
answer can do is select the wrong one of the options the asking agent itself wrote, and it cannot put
new content into that agent's context.

What is bounded. The question text and the option list are bounded when they arrive, and rendered as
text and never as markup. The number of questions outstanding at once is capped, and the honest
answer past the cap is a refusal the server turns into a decline rather than an error. A question
that is never answered expires and declines.

Failure is always a decline, never a hang. If the dashboard is not running, if no reader answers, if
the deadline passes, or if the process is stopped while a question is outstanding, the tool returns a
decline and the agent proceeds as it judges best. A stopped dashboard releases every outstanding
question before it exits.

The standing permission this needs, and what granting it means. At default settings every harness
gates the first call to this tool in the user's own terminal, before the call reaches Cargento. The
feature is therefore useless until the user grants the tool once, which on Claude Code writes
`permissions.allow: ["mcp__cargento__ask_operator"]` into that project's
`.claude/settings.local.json`. Granting it means that project's sessions may pause themselves on a
Cargento question without asking again. It is scoped to that directory, it is the user's to revoke by
deleting the line, and Cargento never writes it.

Answering is a real decision. Every other click in the dashboard changes what you see. This one
changes what an agent does next, with your credentials, in your repository. The exposure that follows
is recorded under Known and accepted rather than solved here, because loopback is not a per-user
boundary.

---

### The paragraph to add under Known and accepted

Verbatim, following the event-ingress paragraph.

---

The ask lane inherits the loopback exposure above, and it is the first place where that exposure
reaches beyond what a reader sees. Any local process that can reach the port can answer a question a
session is waiting on. Two things keep this narrow rather than solved. An answer selects an option by
index from a list the asking agent wrote, so a forgery cannot introduce text into an agent's context,
only choose badly among choices the agent already offered. And a session is only ever waiting because
it asked, so there is no question to answer unless an agent raised one. A per-reader
authentication would be the real fix, and it is not available: the dashboard page is served as fixed
bytes with no per-run secret in it, and a local process could read such a secret anyway.

---

## What the build PR does with this file

Promote both sections into `SECURITY.md` unchanged, fix the two counts named above, delete this file,
and update the docs map if it lists it. Then the two claims elsewhere that this feature falsifies:

`cargento/skills/cargento/SKILL.md` line 77 currently reads "Nothing marks a gate answered. Cargento
does not write to a session, so a mark would record only that you clicked something". It has to
distinguish a native gate, which is still unanswerable and where the whole existing argument stands,
from a question a session asked, which is answerable because the session is holding the call open.
The shipped skill body is out of the voice pass's scope and carries test asserted literals, so treat
it as a validated artifact and change only what became false.

`docs/design-needs-input.md` N-8 rejected a handled mark because it would be "the page asserting
something no collector measured". That argument is not invalidated and must not be quietly abandoned.
An `ask_operator` answer is measured: the session asked, and it is holding the call open until the
answer arrives. Write that carve-out into N-8 explicitly, or the codebase holds two opposed arguments
about one surface.

`COMPATIBILITY.md` line 10 is an MCP row reading "Not used" in all four columns with the rationale
"no MCP server is bundled", and line 66 says needs-input detection exists only for Claude Code
sessions. Rewrite the row per harness, as registered, not registered, or measured, and claim it for
no column that was not measured attended. Two were.

## Done when

This document is merged and `scripts/validate_plugins.py` passes, which resolves relative links and
heading anchors across the owned docs, plans included. The implementation issue can then quote the
contract instead of inventing it.
