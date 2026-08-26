# Security policy

## Scope

Cargento ships three kinds of component that touch the network. The dashboard server
(`cargento/skills/cargento/server.py`, whose code is the `cargento_runtime` package beside it)
reads local coding-agent session stores (transcripts, task
files, SQLite databases) and serves them over HTTP. When the usage feature is on, the server also
makes one kind of outbound request, the quota poll described in Usage quota reads (the quota
fetcher); it carries no session data. The opt-in UI's Space fonts are packaged into its page, so
loading either interface makes no request to a font provider. Four small forwarders ship beside it,
each wired into a harness's own configuration by the user or by the plugin: `notify_hook.py` POSTs
a Claude `Notification` payload to the dashboard, `event_hook.py` posts command-hook lifecycle
events for Claude and Codex, `agy_hook.py` posts Antigravity's hook events, and
`statusline_hook.py` posts Antigravity's status-line state. All four share one transport, so the
loopback check, the proxy suppression and the redirect refusal have a single implementation.

One of them runs somewhere it could do harm. Antigravity's `PreToolUse` hook may return a `decision`
that allows, denies or re-prompts a tool call, so a reporting hook there can block the user's work.
`agy_hook.py` prints exactly `{}` and nothing else, on every path including every failure path, and a
test asserts that for malformed, empty and valid input alike.

The third kind is one stdio MCP server, `mcp_server.py`, described under The ask lane below. It is
not a forwarder and shares none of the four's transport: a harness spawns it, it speaks JSON-RPC on
stdin and stdout, and it reaches the dashboard on loopback under the same three guards.

The posture rests on two invariants:

1. Localhost unless the operator says otherwise. The server binds `127.0.0.1`, and every forwarder
   and the MCP server refuse to reach anywhere but loopback, ignore proxy environment variables, and
   do not follow redirects. `--host` is the one way that first clause moves, it is an explicit
   argument nothing sets for you, and what it costs is under Known and accepted.
   Session data never leaves the machine. The quota poll is the single outbound exception, and it
   carries a vendor token out and quota numbers back, nothing else.
2. Read-only against harness stores. They are opened read-only and never written. Seven endpoints
   mutate, and six of them only in memory: `POST /api/notify` updates needs-input state, and
   `POST /api/usage` stores a quota figure a harness published to its own status-line command.
   `POST /api/events/<harness>` also mutates in memory only, behind the capability described under
   Known and accepted, and so do `POST /api/ask`, `POST /api/answer` and `POST /api/ask/withdraw`,
   which register a question a session asked, record the option the reader chose, and drop a question
   whose asker has stopped waiting for it, all three described under The ask lane. The long
   poll that delivers an answer, `GET /api/ask/<id>`, drops that question from memory once it has,
   which is the delivery completing rather than a change a caller asked for. The seventh,
   `POST /api/dismiss`, does write to disk, but what it writes is
   Cargento's own state under `~/.cargento` and never a harness store, so the read-only rule above stands
   unchanged. What that file holds and how to clear it is in Dismissals. One forwarder writes too:
   `statusline_hook.py`'s deduplication memo under the same directory, which holds a normalized state
   name and a timestamp and nothing about the session's content.
   One `GET` writes as well, which is why it is named here rather than left to the count above.
   `GET /api/observe` is a trigger rather than a poll: it derives one session's goal, stage and open
   block and records the answer as a sidecar under `~/.cargento/observer/`, again Cargento's own
   state and never a harness store. Its two components are the harness key and the session id, and
   both must match `[A-Za-z0-9._-]{1,128}` before either reaches a path. `records.safe_text`
   bounds a string and strips control characters, and passes a separator straight through, so the
   grammar is what keeps the write inside that directory rather than the join. What the route reads
   is covered by Project reads below: the transcript, and the same two kinds of frontmatter a stage
   strip reads, under the same guards and the same `--no-spacedock` switch.

Anything that weakens either invariant is a security bug: a bind reaching an address the operator did
not ask for, a request admitted that the bind's own Host gate should have refused, file reads outside
the documented store paths and the project-read contract below (however the path was derived),
writes to harness stores, or the hook client reaching a non-loopback destination.

## Project reads (Spacedock stage strips)

One feature reads paths that are not under a store root. When a session declares itself a Spacedock
first officer, or in Pi's case is taken to be one because its transcript carries a boot envelope,
Cargento reads YAML frontmatter, and only frontmatter, from two kinds of file, so it can show where
each entity sits on its workflow's stage spine:

1. one workflow `README.md`, for the ordered stage list and which stages are initial or terminal;
2. the entity files in that workflow's entity-state directory, for each entity's current `status`.

That is the whole of it. No other project file is opened, and the only directory listed is the
entity-state directory itself, through one non-recursive `scandir`. Nothing is ever walked.

Neither path is guessed. The first officer's own `spacedock status --boot` output, already recorded
in its transcript, names the workflow directory and the entity-state directory as absolute paths.
Cargento uses those values and nothing else. Before any file is opened, all of the following must
hold, and a path failing any one is skipped silently:

- the directory value is absolute, contains no NUL, and encodes for this filesystem. A lone
  surrogate survives JSON decoding, and the checks below it raise `UnicodeEncodeError` rather
  than `OSError`, so an unencodable path would escape every handler here;
- the path is canonicalised with `realpath`, and the README must still resolve inside the workflow
  directory (`commonpath` containment), so a swapped entry cannot redirect the read;
- every file opened is a regular file and not a symlink. This is checked with `lstat`, opened with
  `O_NOFOLLOW` where the platform has it, and confirmed with an `fstat` `(st_dev, st_ino)` match
  against the `stat` the cache key was built from, so a parent-directory swap between the two cannot
  seed the cache from a different file. Windows has no `O_NOFOLLOW`, so there the guarantee rests on
  the `lstat` classification alone and a racing reparse-point swap could still be followed. That is
  the same unclosable class as the `FILE_SHARE_DELETE` window described in the skill body;
- the README frontmatter declares `commissioned-by: spacedock@`, which is Spacedock's own workflow
  discriminator.

The entity-state directory is deliberately not required to sit inside the workflow directory. A
`split-root` workflow legitimately keeps its state elsewhere, and that path carries the same
authority as the workflow path, having come from the same tool result. A per-file discriminator
stands in for containment instead: an entity file counts only if its name is a well-formed slug
(`^[a-z0-9][a-z0-9-]*[a-z0-9]$`, which also excludes `_archive/` and any report left beside the
state) and its `status` names a stage the README declared.

Hard caps: at most 64 KiB read from a README and 8 KiB from an entity file, 400 frontmatter lines
scanned, 32 stage names taken, 120 characters of the README's `title`, 96 entity files read per
workflow (newest first), 12 entities rendered per workflow, and 8 workflows per session. Both reads are cached on
`(realpath, st_mtime_ns, st_size)`, so an unchanged file costs one `stat` per refresh. Entity files
older than the dashboard's freshness window are not opened at all.

Only derived scalars reach `/api/data`: stage names (each validated against Spacedock's
`^[a-z0-9][a-z0-9-]*[a-z0-9]$` grammar), entity slugs, cycle markers, and the README frontmatter's
`title` scalar, shown as the workflow's goal line in the session view. That title is the one piece of
project-authored *text* on the surface, and it is there because a stage spine says where the work is
without saying what it is for; it is capped at 120 characters and passes through the same
control-character and bidi stripping every untrusted string does. No other file text, no frontmatter
body and no filesystem path is ever published, and the page HTML-escapes every value.
Pass `--no-spacedock` to switch the feature off. The read surface is then exactly the documented
store paths.

## Usage quota reads (the quota fetcher)

One feature makes outbound network requests. When the usage feature is on, the server polls each
supported vendor's usage endpoint so the dashboard can show quota windows: how much of the 5-hour
and weekly limits is used and when they reset, or for a vendor that meters spend rather than
requests, how much of the monthly billing period's allowance is used and when the cycle ends.

What is sent: the vendor's own OAuth access token, read from where the harness keeps it (the macOS
Keychain, or the harness's credential file on other platforms), carried in the request's
authorization header. Nothing else. No transcript content, no prompts, no paths, no project names,
no machine identifiers. What comes back is quota numbers: window utilization, reset times, and
per-limit entries. Session data never appears in either direction.

The endpoints, named exactly:

1. Anthropic (Claude Code, and any harness signed in with the same Claude subscription):
   `GET https://api.anthropic.com/api/oauth/usage` with the `anthropic-beta: oauth-2025-04-20`
   header.
2. Cursor: `POST https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage` with an
   empty JSON body and two headers, the bearer authorization and `Content-Type: application/json`.
   This is the RPC the Cursor CLI itself calls for its own `/usage` command, against the backend the
   CLI's config records. The credential is the session token in the macOS Keychain under the service
   name `cursor-access-token`. Read this next part before trusting the name: Cursor stores the
   identical value under `cursor-refresh-token`, so unlike Claude's quota-scoped token this one can
   also mint new sessions. Cargento sends it as a bearer token and never exchanges it, and the
   never-refreshed rule below is what keeps that true. macOS only, because that is the only platform
   where the token's location has been verified; elsewhere Cursor is absent from the band rather than
   read from a guessed path.
3. Codex: no endpoint. Codex writes rate-limit snapshots into its own session files, and Cargento
   reads them from disk like every other store.
4. Copilot: no endpoint. Copilot records its own per-request AI Unit consumption in a local session
   store, and Cargento reads that from disk. Its remaining entitlement is not published locally and
   is not fetched.

No other vendor is polled. A new vendor's endpoint must be named here before it ships. These
endpoints are not documented for third-party use: a vendor can change, break, or block them at any
time, and a failed poll means an empty tile, never a retry storm.

Token handling is read-only, one way, and never expands:

- The token is never refreshed. Refreshing from outside the harness can race the harness for its
  own session. A token the harness would refresh by itself, or one a vendor refuses, switches that
  vendor's usage display off and says which of the two happened; the remedy always belongs to the
  harness. This rule is what bounds the Cursor credential noted above: a value that could mint
  sessions is only ever presented as a bearer token, so the extra capability is never exercised.
- The token is never written to disk, never logged, and never served. `/api/data` and every other
  loopback endpoint must not carry it, in any form.
- Reading the token adds no write access anywhere. Harness stores stay read-only.

Consent and the off switch: the feature is on by default and disclosed before it acts. The first
time the dashboard opens with the feature available, a banner explains the token read and the
request above, and carries the switch that turns the feature off. The setting can be changed later
from the dashboard's configure panel, and `--no-usage` disables the feature for a run regardless
of the stored setting. With the feature off, Cargento's network surface is exactly the three
loopback-bound kinds of component described above, and nothing is fetched.

Polling posture: responses are cached, and at most one request per vendor is made every five
minutes. No polling happens while no dashboard page is connected. `--diagnose` never triggers a
fetch; its output stays a report of local paths only.

A violation of any boundary in this section is a security bug: a request carrying anything beyond
the token, a token reaching a log or a loopback response, a refresh attempt, an unlisted endpoint,
or a fetch with the feature off.

Not every harness needs that request. One publishes its own quota to a user-configured command:
Antigravity pipes a state payload, including a `quota` object, to whatever its status-line setting
names, and a user who points that at `POST /api/usage` gets the same display with no credential
read and no outbound request at all. That payload also carries an account email and a transcript
path, so the receipt is never stored or served as it arrived: only the derived window percentages
and reset times are kept, built into a fresh record field by field. `--no-usage` stops this too: the
quota fields are dropped before storage, so nothing is retained and nothing reaches the band, and
the request still succeeds so a status line never sees an error. The dashboard's own switch is
narrower, and deliberately so. It governs the outbound fetch and the display, which is all it can
govern for a harness that publishes its quota locally: with it off, a pushed receipt is still kept
and still served on the loopback port, exactly as a disk-read tile (Codex, Copilot) is. Withdrawing
retention for a run is what `--no-usage` is for.

## Process lifecycle: written paths, and `/api/shutdown`

The server writes three files, all under `~/.cargento` (relocatable with `CARGENTO_HOME`,
authoritative when nonblank): `cargento-<port>.json`, recording the running instance (`pid`, `port`,
`started`, `log`, `python`); `cargento-<port>.log`, where a detached (`--daemon`) instance's
output goes; and `cargento-dismissals.json`, the sessions the reader marked handled, described in
Dismissals below. One forwarder writes a fourth, in the same directory and named in invariant 2 above:
`statusline_hook.py` keeps `statusline-<harness>-<session>.json` per conversation, holding a
normalized state name and a timestamp, so a status line that fires many times a turn posts once. The directory is created `0o700` because the log can carry local paths: uncaught
tracebacks land there, not just Python-level prints. Nothing ever removes or rotates the log: a
`--stop` (or a killed process) deletes the state file but leaves the log behind, since it is the
record of a detached run, so `~/.cargento` accumulates one log file per port indefinitely.

`POST /api/shutdown` stops the server and is gated by the same `_local_ok()` checks (`Host`,
`Origin`, `Sec-Fetch-Site`) that already protect `/api/notify`. It adds no new exposure of
consequence: any local process that can reach the port could already read every session on the
machine through `/api/data`, and can now also stop the server. That is a smaller capability inside
the same trust boundary described above, not a new one.

`GET /api/overlays` reads the event overlay ledger and is a diagnostic, described in
[`docs/design-needs-input.md`](docs/design-needs-input.md#n-5-two-different-faults-produce-the-same-row-so-the-ledger-is-now-readable).
It carries no session content: an overlay is a harness name, the collector key for the session, a
state kind, three timestamps, and a subagent id the hook supplied, capped at ingress. The collector
key is Claude's eight-character transcript prefix and the whole session UUID for Codex, Antigravity
and Gemini CLI, and `/api/data` already publishes both, along with titles and prompts this route
never sees. It applies the strict same-origin check rather than the relaxed one `/api/data` uses for
navigations, and answers 503 when the process runs without a coordinator.

The same route serves the bounded record of state disputes, where an event overruled a session the
dashboard had read as waiting. A record holds the same fields plus the two activity timestamps the
reducer compared, and no more: the row's title and its state detail are deliberately absent, because
a state detail can carry a permission prompt's own text, an open question's, or a plan's first line.

## Dismissals

Marking a session handled writes one file, and it is the only thing Cargento writes on your behalf:
`~/.cargento/cargento-dismissals.json`, opened `0600` with the mode in the `open` call so it is never
briefly world-readable, written through a temp file and `os.replace` so a reader mid-write sees the
old file or the new one.

It holds a harness key, a session id, and two timestamps per entry. Nothing else: no title, no
prompt, no project path, no state detail. Nothing sends it anywhere either. The one route that reads
it out is `GET /api/cleared`, on the loopback port, and what that serves back to the page is strictly
less than `/api/data` already does. It applies the strict same-origin check rather than the relaxed
one `/api/data` uses for navigations, and answers 503 under `--no-dismiss`.

Two properties bound what a forged `POST /api/dismiss` can do. The body carries no timestamp: the
watermark that decides how long a mark holds is the server's own clock at the moment it lands, so
there is no value a caller can send that hides a row past that session's next write. And the file is
capped at 256 entries, oldest mark evicted first, so nothing can grow it without limit. A corrupt,
truncated or over-cap file degrades to "no dismissals", with every row visible, rather than
raising, and one malformed entry is dropped on its own without discarding the rest.

To clear it, delete the file, or use the page's `handled` chip to restore individual sessions.
`--no-dismiss` leaves it unread and unwritten for a run.

Two exposures come with the feature and are accepted rather than solved. The first is that clearing a
session suppresses its desktop popup as well as its row, including a session still waiting on an
answer, which is what the control is for when the gate was answered somewhere else. It is also the
most a forged `POST /api/dismiss` can achieve: one session's alert stays silent until that session
writes again, and its standing question is still on the board the moment the row is restored. The
second is that two dashboards on one machine share the one file. Each picks up the other's marks on
its next collection, but two marks landing in the same instant resolve last-writer-wins on the whole
file, and the losing mark is lost.
[`docs/design-dismissals.md`](docs/design-dismissals.md) records why that race is stated rather than
solved.

## The ask lane (`ask_operator`)

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
that is never answered expires and declines. The question is also delivered as a notification: on macOS by the server,
through the same truncation and AppleScript escaping the needs-input popup uses, and elsewhere by the page, which
passes the text to the browser's own notification API and applies neither (it is not building a
shell command, and the text is already bounded at the ingress); the notification is a pointer rather than a decision surface, and an option can
only ever be chosen back in the page.

Failure is always a decline, never a hang. If the dashboard is not running, if no reader answers, if
the deadline passes, or if the process is stopped while a question is outstanding, the tool returns a
decline and the agent proceeds as it judges best. A stopped dashboard releases every outstanding
question before it exits. A tool call that gives up for any of those reasons also withdraws its own
question on the way out, so a card nobody is waiting on leaves the board instead of staying clickable
until its deadline. A click on a question whose asker has gone is accepted and discarded either way,
which is why the withdrawal matters to the reader rather than to the agent.

The standing permission this needs, and what granting it means. At default settings every harness
gates the first call to this tool in the user's own terminal, before the call reaches Cargento. The
feature is therefore useless until the user grants the tool once, which on Claude Code writes
`permissions.allow: ["mcp__plugin_cargento_cargento__ask_operator"]` into that project's
`.claude/settings.local.json`. Granting it means that project's sessions may pause themselves on a
Cargento question without asking again. It is scoped to that directory, it is the user's to revoke by
deleting the line, and Cargento never writes it.

Answering is a real decision. Every other click in the dashboard changes what you see. This one
changes what an agent does next, with your credentials, in your repository. The exposure that follows
is recorded under Known and accepted rather than solved here, because loopback is not a per-user
boundary.

## Known and accepted

`--host` hands that same access to a network. `--host 0.0.0.0` is the operator
saying the machine's network may read the board, and there is no second gate behind it: everything
the paragraph below grants another account on the machine, a non-default bind grants anything that
can reach the port. Reading `/api/data` is the whole board: every session's titles, prompts and
project paths. Writing is the seven POST routes, `/api/shutdown` and `/api/answer` among them, so a
reachable dashboard can be killed, and a question a session is waiting on can be answered by
somebody other than you. There is nothing to authenticate with, for the reason the ask-lane
paragraph below gives: the page is served as fixed bytes with no per-run secret in it.

What the non-default bind does *not* spend is the rebinding defense. The Host and Origin gate widens
to addresses and never to names. Under `0.0.0.0`, that means any address a client could arrive on.
A page on `http://evil.example:4553` whose DNS points at the machine is refused in both modes, and
the `Sec-Fetch-Site` cross-site check runs unchanged. The gate tells a name from an address; it
cannot tell one remote client from another. So the honest scope is: use `--host` on a network you
would hand the transcripts to, and reach a dashboard over `ssh -L` otherwise.

Loopback is not a per-user boundary. Any other account on the same machine can `GET /api/data` and
read every session's titles and prompts, or forge a `POST /api/notify`. The Host, `Sec-Fetch` and
Origin checks defeat browser-based DNS rebinding, but they do not defeat a local process. This
matters more on a shared Linux host than on a personal laptop. Please report a *bypass* of the checks
that do exist. The absence of per-user isolation is documented here rather than treated as a new
finding.

Event ingress is the exception, and it is narrow. `POST /api/events/<harness>` requires a per-run
capability, because a general lifecycle overlay is more powerful than the side state `/api/notify`
sets: a forged `session_ended` can suppress a permission alert, and a looped `turn_started` can mask
a blocked session. The server generates one secret per process, derives one token per harness from
it, and publishes only the derived tokens in the state file, opened `0600` with the mode in the
`open` call so the token is never briefly world-readable. A token from one adapter cannot post as
another harness, and a token recovered from an old state file is useless against the next run. The
comparison is constant-time.

What that does **not** buy: the file mode is advisory, exactly as the state directory's `0700` is.
It does not apply to a directory that already exists, Windows ignores it, and root reads it either
way. Any process running as the same user can read the token and post events, and that stays inside
the trust boundary for the same reason the rest of this section does, since such a process can read
the user's secret material directly. An overlay may also only ever patch a row a collector produced;
it can never create or delete one, and it can only write `state`, `state_detail`, `active`,
`blocked_since`, the acquisition marker and `finished_at`, the stamp of the turn's last observed
stop. `--no-events` turns the whole path off for a run.

The event envelope is allowlisted at both ends. Each adapter builds the nine permitted fields one at
a time from the native payload, so the prompt, the tool name, the tool input and the tool output are
dropped in the hook and never put on a socket; the server then validates independently, because a
hook's output is untrusted regardless of who wrote it. Codex's payloads carry `prompt`, `tool_input`,
`tool_response` and `last_assistant_message`, and Antigravity's carry the account email and the
transcript path; none of those reach a socket. `statusline_hook.py` also shapes `/api/usage` down to
the `quota` block alone, which is what this document asks for a paragraph below rather than sending
the whole status-line document and relying on the server to discard it. `cwd` and `transcript_path` are
matching hints and are never echoed to `/api/data`.

The ask lane inherits the loopback exposure above, and it is the first place where that exposure
reaches beyond what a reader sees. Any local process that can reach the port can answer a question a
session is waiting on. Two things keep this narrow rather than solved. An answer selects an option by
index from a list the asking agent wrote, so a forgery cannot introduce text into an agent's context,
only choose badly among choices the agent already offered. And a session is only ever waiting because
it asked, so there is no question to answer unless an agent raised one. A per-reader
authentication would be the real fix, and it is not available: the dashboard page is served as fixed
bytes with no per-run secret in it, and a local process could read such a secret anyway.

A question's attribution is unverified, and this is the second half of that exposure. `harness`,
`session_id` and `project` are taken from the registration body and bounded, and nothing checks that
the named session exists or that the caller is it, so any local process that can reach the port can
put a card on the board that reads as coming from a specific session in a specific repository. Two
things bound the damage. The card is its own band and touches no collector-measured session state, so
a forged attribution cannot alter a row, a state, a count or a dismissal
([`docs/design-ask-lane.md`](docs/design-ask-lane.md#a-4-an-outstanding-question-is-its-own-band-not-a-row-in-sessions)
records why the band is separate); and answering the card still
only selects among options its own registrant wrote, so the forger gains nothing from being answered.
What a forgery does buy is plausibility, at the one place in the dashboard where a reader makes a
decision, which is why it is named here rather than left implicit in the loopback paragraph above. That
plausibility now reaches a reader with no tab open, because the question also raises a notification. The
title renders the display label of the harness key the registration claimed, and neither the key nor the
claim is verified. A registration that inherits or forges the harness environment variable titles the
banner with that harness. What the registry lookup does buy is that the title is a name the registry
carries or nothing at all, so a 120-character agent-authored string cannot reach it, and an
unattributable question is announced as "An agent" rather than under a borrowed name.
Verifying it would need a per-session secret that the sessions do not have and that the loopback
boundary could not keep.

`--diagnose` output is sensitive. It prints the home directory, the interpreter path, the *values* of
the store relocation variables, every candidate store path, and per-path read errors. Nothing is
transmitted, but redact it before pasting it into a public issue.

## Reporting a vulnerability

Please do not open a public issue for security problems. Instead:

- Use [GitHub private vulnerability reporting](https://github.com/spacedock-dev/cargento/security/advisories/new), or
- Email dev@reccehq.com with a description and reproduction steps.

You can expect an acknowledgment within a few days. Please allow time for a fix to land and release before public disclosure.

## Supported versions

Only the latest released version of the plugin receives security fixes.
