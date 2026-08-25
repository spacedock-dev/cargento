# How to use Cargento

What a person configures by hand, one task per section.

Installing the plugin gets you the dashboard. It cannot get you the things that live in your own
configuration: the ask-lane MCP server, the lifecycle hooks that make the board live, a relocated
store. A plugin has no business writing those files, so you write them, and this page is where the
procedures live.

Every command and every snippet here was run before it was written down. Where something could not be
run, it says so rather than guessing.

This page owns none of the following, and links to it instead:

| For | Read |
|---|---|
| Installing the plugin, per harness | [README.md](README.md#1-how-to-set-up) |
| Reading the board: session states, display modes, the queue of things waiting on you, starting and stopping | [cargento/skills/cargento/SKILL.md](cargento/skills/cargento/SKILL.md) |
| What works on which harness and which platform, and what was measured | [COMPATIBILITY.md](COMPATIBILITY.md) |
| What is read, what is sent, and what granting a permission means | [SECURITY.md](SECURITY.md) |
| Working on Cargento itself | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Find the copy your commands will run

Every command below starts with a path to `server.py`, and there are usually two on the machine: the
one your harness installed and the one in a checkout. They are different builds and they answer
differently.

```bash
# The installed copy. The directory carries the plugin version, so it moves on every update.
find ~/.claude/plugins/cache -name server.py -path '*cargento*'
```

On the machine this was written on that printed a 0.10.0 path while the checkout was 0.12.0. Pin
whichever you meant, and use it for everything in the session including `--status` and `--stop`:

```bash
SKILL="$(dirname "$(find ~/.claude/plugins/cache -name server.py -path '*cargento*' | head -1)")"
python3 "$SKILL/server.py" --diagnose
```

Use the same interpreter every time. The one that started the server is recorded in its state file,
and a second Python on the PATH is the usual reason a hook works from one shell and not another. On
native Windows `python3` is not a reliable spelling; use `python` or `py -3`.

## Let a session ask you a question

Cargento ships one MCP tool, `ask_operator`. A session that hits a decision it cannot make calls it,
the question appears as a card on your dashboard, the tool call blocks until you click an option, and
the option you clicked is what the session gets back. Nothing else Cargento does reaches into a
running session, and this only happens because the session asked.

Two harnesses can reach it: Claude Code, where the plugin registers the server for you, and Codex,
where you register it yourself. Antigravity and Gemini CLI cannot, for reasons below.

It pays off on unattended runs. An attended session usually does not call the tool at all, because
ending its turn already reaches you. That was measured both ways and
[docs/design-ask-lane.md](docs/design-ask-lane.md) records the two trials, so do not install this
expecting your next attended session to start asking questions.

### Before either harness

A dashboard has to be running, or the tool has nowhere to put the question and answers the session
with a decline saying so. [SKILL.md](cargento/skills/cargento/SKILL.md#start) owns starting it.

Your installed copy has to contain `mcp_server.py`, beside `server.py` in the skill directory. If it
is missing, your release predates the ask lane and no amount of configuration will help:

```bash
ls ~/.claude/plugins/cache/*/cargento/*/skills/cargento/mcp_server.py     # Claude Code
ls ~/.codex/plugins/cache/*/cargento/*/skills/cargento/mcp_server.py      # Codex
```

The examples below use port 4601, because that is where they were run. The default is 4553.

### Claude Code: nothing to register, one permission to grant

The plugin declares the server itself, so there is nothing to add anywhere. Confirm the harness sees
it:

```bash
claude mcp list
```

```
plugin:cargento:cargento: python3 /.../cargento/skills/cargento/mcp_server.py - Connected
```

The tool arrives under a name qualified by both the plugin and the server key:

```
mcp__plugin_cargento_cargento__ask_operator
```

Guessing that name is the one setup step that fails silently, so read it from the harness rather than
writing it out.

The first call is gated in your terminal before it reaches Cargento. At default permissions the call
is refused and nothing reaches the dashboard, so there is no card and no question. The session is
told:

```
Claude requested permissions to use mcp__plugin_cargento_cargento__ask_operator, but you haven't granted it yet.
```

Interactively that arrives as a prompt you can answer. In an unattended run there is nobody to answer
it, which defeats the point, so grant it in advance. The grant is per project directory, in that
project's `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_cargento_cargento__ask_operator"
    ]
  }
}
```

With that in place the same session called the tool, the card appeared, and the clicked option came
back with no permission denial recorded. [SECURITY.md](SECURITY.md#the-ask-lane-ask_operator) owns
what granting it means and what it does not.

If your dashboard is not on the default port or not under `~/.cargento`, export `CARGENTO_HOME` in
the shell you launch the harness from. The manifest passes no environment of its own and the server
inherits the harness's, which is how the runs above reached a dashboard on 4601 with its state under
a scratch directory. No port needs configuring.

### Register the MCP server in Codex

The plugin does not register it. Point Codex at the `mcp_server.py` inside the installed plugin. The
CLI writes the table for you:

```bash
codex mcp add cargento --env CARGENTO_HOME="$HOME/.cargento" \
  -- python3 ~/.codex/plugins/cache/<marketplace>/cargento/<version>/skills/cargento/mcp_server.py
```

That is the whole configuration, and writing it by hand into `~/.codex/config.toml` is equivalent:

```toml
[mcp_servers.cargento]
command = "python3"
args = ["/Users/you/.codex/plugins/cache/cargento-marketplace/cargento/0.12.0/skills/cargento/mcp_server.py"]

[mcp_servers.cargento.env]
CARGENTO_HOME = "/Users/you/.cargento"
```

Three things about that path and that block:

- The version is in the path. Upgrading installs beside the old copy and leaves the table pointing at
  the version you registered, so re-run `codex mcp add` after an upgrade.
- The `env` block is only needed for a relocated `CARGENTO_HOME`. Leave it out and the server looks
  in `~/.cargento`, where a default dashboard publishes its state file.
- A port can be given directly instead: `args = [".../mcp_server.py", "4601"]` makes the server try
  4601 first. Verified with no state file at all to read.

Check it:

```bash
codex mcp list
```

`Auth: Unsupported` is normal, since the server has no authentication to support. The env value is
masked in that listing rather than dropped. Codex names the tool `mcp__cargento__ask_operator`,
qualified by the server key alone, which is not the same shape as Claude's.

Codex gates the call too, and its own approval policy decides. Under a plain `codex exec`, whose
policy is `never`, the call never reaches Cargento and the session is told `MCP tool call requires
approval, but approval policy is never`. With approvals available, `codex exec --approve-for-me`,
the same call went through end to end and Codex held the tool call for a 75 second wait before
delivering the answer. An interactive session raises an approval prompt on the first call instead.

Codex also has a per-server key for a standing grant:

```toml
[mcp_servers.cargento]
default_tools_approval_mode = "auto"   # accepted values: auto, prompt, writes, approve
```

Codex validates those four values, but setting `auto` did not override `codex exec`'s `never` policy
and under `--approve-for-me` the call was approved either way, so nothing here proves what it does in
an interactive session. Treat it as the thing to try, not as verified.

One difference on the board: a Codex question arrives with no session id, so its card is answerable
but does not attach to a session row. [COMPATIBILITY.md](COMPATIBILITY.md) owns that contract.

### Antigravity and Gemini CLI cannot register it

Antigravity's MCP surface takes a non-empty `serverUrl` per entry, which is a URL. `ask_operator` is a
stdio server, a command and its arguments, and there is no field to put it in. Gemini CLI's extension
root carries hooks only and has no manifest surface to declare a server in. Neither is a gap waiting
on a small fix, and neither has a hand configuration you could add today.

### Checking it worked

| Check | Command | Good looks like |
|---|---|---|
| The dashboard is up | `python3 "$SKILL/server.py" --port 4601 --status` | `Cargento: running on port 4601 (pid ..., since 12:16)` |
| The lane is on | `curl -s http://127.0.0.1:4601/api/data \| python3 -c 'import json,sys; print(json.load(sys.stdin).get("ask"))'` | `True`. Anything else means the lane is off. Do not grep for `"ask":true`: the payload is serialised with spaces after the colon, so that never matches |
| The harness has the server | `claude mcp list` or `codex mcp list` | connected, or `enabled` |
| The tool is reachable | ask the session to name its ask tool | the qualified name above, not a guess |

`--diagnose` will not help here. It reports where session stores are searched and says nothing about
the ask lane, and its `--json` output carries no ask-related key. It is the right tool for a missing
harness, not a missing question.

Claude Code's own MCP log, on macOS at
`~/Library/Caches/claude-cli-nodejs/<encoded-cwd>/mcp-logs-plugin-cargento-cargento/`, records the
connection lifecycle only. It did not contain the server's own diagnostics on either the working or
the refused path, so do not go looking there for the reason a question was declined. The reason is in
the text the tool returned to the session, which is written to be quotable.

### The off switch

Start the dashboard with `--no-ask` and the lane is closed in both directions: the routes refuse, and
the page offers no control because the payload carries no `ask` flag.

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"question":"probe","options":["a","b"]}' http://127.0.0.1:4602/api/ask
```

```
{"ok":false,"reason":"disabled"}
```

That machine-readable reason matters. A session asking a lane-off dashboard is told the truth rather
than that nothing is running, and the server stops there instead of shopping the question to another
dashboard that has the lane on. There is no per-project or per-session setting: the flag belongs to
the dashboard process, so turning the lane back on means restarting without it.

### What the session experiences

One tool call, blocked, returning one string: the label on the card you clicked, character for
character, never text from anywhere else. [SECURITY.md](SECURITY.md#the-ask-lane-ask_operator) owns
why the answer travels as an index rather than a string.

Everything else resolves to a decline the session can act on rather than an error it has to
interpret. Observed: nothing listening, the lane switched off, and the dashboard stopped while a
question was outstanding, which released the waiting session in 12 seconds. Each one ends by telling
the session to use its own judgement and say what it chose. A question nobody answers is retired
after five minutes and the session is told the same thing.

A second click on the same card is a no-op. Four answers racing one question produced one accepted
and three no-ops, and the session saw the first.

Cargento will not answer your harness's own permission prompts, type into a terminal, or reach a
session that never called the tool.

## Make the board live rather than polled

Without hooks, state comes from reading session stores on a cadence. With them, a harness pushes
lifecycle events to the dashboard and the board reacts as things happen.
[SKILL.md](cargento/skills/cargento/SKILL.md#notifications) owns the hook JSON, the event names, and
which ones matter. What it cannot own is the absolute path those snippets need, because the shipped
skill body is installed without the repository and is forbidden to name one. Resolve it with `$SKILL`
from the first section, then paste the resolved path into the snippet.

Claude Code's hooks go in `~/.claude/settings.json`. Antigravity's status line goes in its own
settings file. Both are yours to edit; the plugin does not write either.

## See why a harness is missing

A collector skips a store it cannot read rather than taking the dashboard down, so a wrong path and an
idle machine look identical on the board. `--diagnose` is the only thing that tells them apart. It
reads local paths, transmits nothing, and starts no server:

```bash
python3 "$SKILL/server.py" --diagnose
```

Two traps in reading its output, both reproduced:

- **Read the store lines, not the harness lines.** `[ok  ]` beside a harness means the collector ran,
  not that it read anything. A directory at mode `000` and a file that is not a SQLite database both
  still printed `[ok  ] <Harness> 0 session(s)`, with the real problem further down under the stores.
- **The `overrides` line is narrower than it reads.** It lists only the per-harness store variables,
  so `CARGENTO_HOME` can move everything Cargento writes while that line still says `none`.

## Move it: ports, a second dashboard, and where state lives

`--port` moves the listener. `CARGENTO_HOME` moves everything Cargento writes, which is its state
file, the dismissal store and the daemon log. Two dashboards on different ports coexist, and each
publishes its own state file.

The per-harness store variables `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME`, `COPILOT_HOME`,
`PI_CODING_AGENT_DIR` and `PI_CODING_AGENT_SESSION_DIR` point Cargento at a store somewhere other
than its default. Set one and confirm with `--diagnose` that the store line moved, rather than
assuming it did.

`--host` moves the bind address, and it is the one flag here that changes who can read the board
rather than where you read it from. It takes two values: `127.0.0.1`, the default, and `0.0.0.0`,
every interface. Nothing narrower is accepted. `--host 10.0.0.2` is a usage error, not a bind, because
`--status`, `--stop`, the hook forwarders and the MCP server all reach the dashboard over loopback
and a single-interface bind does not answer there. Binding one interface is a reasonable thing to
want; it is refused rather than half-supported. IPv4 only, too: the server has never spoken IPv6, so
`--host ::1` is a usage error rather than a bind failure.

Nothing authenticates the reader that arrives. Whatever can reach the port reads the whole board:
every session's titles, prompts and project paths. It can also POST to the board, including stopping
the dashboard and answering a question a session is waiting on. The Host and Origin checks still
refuse a hostname, so a web page cannot rebind its way in, but they cannot tell one remote address
from another. [SECURITY.md](SECURITY.md#known-and-accepted) states the scope.

So the first thing to try is not this flag:

```bash
# On the machine you are reading from. Nothing on the dashboard host changes.
ssh -L 4553:127.0.0.1:4553 you@the-agent-machine
python3 -m webbrowser -t http://127.0.0.1:4553/
```

That gets a remote board over a channel that already authenticates you, with the dashboard still
bound to loopback. Reach for `--host` when there is no ssh to be had, such as a container publishing
a port or a VM whose host browser cannot see its loopback:

```bash
python3 "<skill-dir>/server.py" --port 4553 --host 0.0.0.0 --daemon
```

Then open `http://<the machine's address>:4553/`. Not its hostname: a name is refused whichever
address it resolves to, and that is the rebinding defense rather than a bug. `--daemon` re-spawns
itself on Windows and carries the address across, so a detached remote-bound dashboard stays remote
bound.

Both `--status` and `--stop` find a live instance by probing the port, so neither needs the home the
dashboard was started with. Tested: a dashboard started under a scratch `CARGENTO_HOME` was stopped
by a `--stop` issued with no `CARGENTO_HOME` at all, and its state file was cleaned up anyway, because
the process removes its own on the way out.

## Turn a feature off

Each flag belongs to the dashboard process, so changing one means restarting.

| Flag | What stops |
|---|---|
| `--no-ask` | The ask lane, in both directions. See the off switch above |
| `--no-usage` | The one outbound request Cargento makes. No quota is fetched and no section renders |
| `--no-dismiss` | Marking a session handled, and the store that remembers it |
| `--no-events` | The event coordinator. State comes from scanning stores rather than from pushed events |
| `--no-spacedock` | Reading Spacedock workflow state out of a project |

[SKILL.md](cargento/skills/cargento/SKILL.md#options) owns the full option reference.

## Usage and quota

This is the only thing Cargento sends anywhere. It is on by default, carries the vendor's own token
and nothing else, and is gated behind a first-run disclosure in the page plus a five minute floor.
`--no-usage` switches it off for the process, and the page's own configure control switches it off
without a restart. [SECURITY.md](SECURITY.md#usage-quota-reads-the-quota-fetcher) owns the contract,
including what is sent, what comes back, and what is never touched.

## Stop a dashboard, and unstick a port

```bash
CARGENTO_HOME="$HOME/.cargento" python3 "$SKILL/server.py" --port 4553 --stop
```

[SKILL.md](cargento/skills/cargento/SKILL.md#stop) owns the last-resort per-platform commands for a
port that stays held.

State files accumulate, but only from runs that never exited cleanly. A dashboard removes its own on
the way out, so a kill, a crash or a sleeping machine is what leaves one behind. They are inert, since
a stale record is told from a live instance by probing the port, but each one holds that dead run's
capability tokens and nothing sweeps them, so they are worth deleting by hand if you have collected a
pile. Tracked as DRC-4181.

## Troubleshooting

| Symptom | Likely cause | What to run |
|---|---|---|
| A harness's sessions are missing | Its store is elsewhere, or unreadable | `--diagnose`, and read the store lines rather than the harness lines |
| The board is empty and the harness is installed | You are running a different copy than you think | Re-pin `$SKILL` from the first section |
| A question never appears | The lane is off, or the first call was gated in the terminal | Check `"ask":true` in the payload, then check the grant |
| The session says no dashboard is running | It is looking at a different `CARGENTO_HOME` or port | Export `CARGENTO_HOME` in the shell that launches the harness |
| The session says the lane is switched off | The dashboard was started with `--no-ask` | Restart without the flag |
| A hook works in one shell and not another | Two Pythons on the PATH | Use one interpreter for everything |

Anything that looks like a defect rather than a configuration problem belongs in an issue. The
security contact is in [SECURITY.md](SECURITY.md).
