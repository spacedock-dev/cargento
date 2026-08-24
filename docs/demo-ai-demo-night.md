# Cargento — 2-minute demo script and busy-work rig

For the PicCollage **AI Demo Night, Wednesday 12 August 2026** (Karen's thread in `#general`, 6 Aug).
Two minutes, pre-recorded, played back-to-back with other people's demos in a bilingual
Mandarin/English room. Karen asked for an RSVP through the event form as well as the Slack reply —
confirm that is done.

Every claim here was checked against Cargento **0.10.0** on this laptop, and every command was run
against the real CLIs. Where a check failed, the failure is recorded rather than the intention.
Figures move fast — the Claude 5-hour window rose 3 points during the writing of this document — so
treat all of them as "re-read on the day".

- [Part 1 — the script](#part-1--the-script)
- [Part 2 — the busy-work rig](#part-2--the-busy-work-rig)
- [Part 3 — pre-flight checklist](#part-3--pre-flight-checklist)
- [Part 4 — recording mechanics and retakes](#part-4--recording-mechanics-and-retakes)
- [Part 5 — claims to avoid](#part-5--claims-to-avoid)
- [Part 6 — the bench: cut material, ready for questions](#part-6--the-bench-cut-material-ready-for-questions)
- [Appendix — what this machine reports today](#appendix--what-this-machine-reports-today)

---

## Part 1 — the script

**One idea for the whole two minutes:** *you cannot see which of your agents is waiting on you.*
Every beat serves that. A beat that does not has been cut, and the cut material is parked in
[Part 6](#part-6--the-bench-cut-material-ready-for-questions) where it can answer a question instead
of costing you the payoff.

### Budget

Price the narration at **130 wpm**, not 145. Much of this room is hearing English as a second
language while also reading a dense dashboard, and a reel played to a crowd needs the slower pace.
130 wpm is 2.17 words per second, so 120 seconds affords about **260 words absolute maximum** — and
that maximum leaves nothing at all for the screen.

This script is **167 words**: 77 seconds spoken, **43 seconds of silence**. That 36% is deliberate. A
screen demo is watched, not listened to, and the two places it must be silent are the moment you
answer the blocked agent and the closing card.

| Beat | Words | Speech at 130 wpm | Slot | Silence in slot |
|---|---|---|---|---|
| B1 cold open | 25 | 11.5s | 0:00–0:22 | 10.5s |
| B2 reveal | 11 | 5.1s | 0:22–0:29 | 1.9s |
| B3 harness strip | 34 | 15.7s | 0:29–0:47 | 2.3s |
| B4 the payoff | 40 | 18.5s | 0:47–1:18 | **12.5s** |
| B5 working cards | 29 | 13.4s | 1:18–1:40 | 8.6s |
| B6 usage | 13 | 6.0s | 1:40–1:51 | 5.0s |
| B7 close | 15 | 6.9s | 1:51–2:00 | 2.1s |
| | **167** | **77.1s** | **120s** | **42.9s** |

B1's 10.5 seconds of silence is not slack — it is the shot doing its work. Let the frozen pane and
the climbing timer sit there unexplained before you say anything.

### Shot list

No em dashes in the spoken lines. An em dash is inaudible — read aloud it is just a pause — so
narration built on them comes out as written prose rather than speech. Every break below is a full
stop or a colon on purpose.

| # | Slot | On screen | Say |
|---|---|---|---|
| B1 | 0:00–0:22 | Four terminal panes tailing four agent logs. **Three visibly scrolling, one frozen**, with a large elapsed timer overlaid on the frozen pane. No dashboard anywhere. Project name legible in a corner from frame 1 | "Four coding agents, all working for me. Three of them are busy. That one has been waiting on me for **[N]** minutes. And I hadn't noticed." |
| B2 | 0:22–0:29 | Cut to the dashboard, whole page, cursor still | "This is Cargento. One local page, every agent working right now." |
| B3 | 0:29–0:47 | Cursor traces the discovered-harnesses strip | "Top strip: every harness it knows about. Green means it found that tool's data on this machine. I didn't configure Codex or Antigravity for this. It reads what these tools already write to disk." |
| B4 | 0:47–1:18 | Red needs-input band; the macOS notification lands in frame. Speak, then **stop**: answer in the terminal and let the band clear in silence. Speak the last line over the cleared board | "There's the one. It's blocked on me. It didn't guess that from a timeout: Claude left a question open, so Cargento saw it and fired a desktop notification." *(silence — answer it, let the band clear)* "That's the whole idea. Everything else here is in service of it." |
| B5 | 1:18–1:40 | Scroll to the working cards; rest on one carrying distinct subagent pills | "Underneath, a card per working agent: what it's doing this second, the subagents it spawned, how long this turn has run against comparable past turns, and its token rate." |
| B6 | 1:40–1:51 | Cursor to the usage section, which is already on screen. Rest on the Claude 5-hour bar | "It also tracks what you're burning. Every vendor's quota window, in one place." |
| B7 | 1:51–2:00 | Static title card, held in near-silence | "If you run more than one agent, you already have this problem. Cargento is free." |

The title card carries the things that are retained by being **read**, not said:

```
Cargento
github.com/spacedock-dev/cargento
Apache-2.0 · stdlib Python, no dependencies · runs entirely on your machine
```

### Beat notes

**B1 — the cold open is the whole argument, and it must not be a reading test.** Four panes at
1920×1080 give each about 960×540 of small monospace, projected, to a partly non-native room after
someone else's demo. Nobody will read it, so a question like "can you tell which one?" gets the
honest answer *no* — which is not the answer the beat wants. Motion and one big number read at any
resolution: **three panes scrolling, one frozen, one large timer.** Then the line lands on what the
audience can already see.

**B1 — `[N]` has a floor, and it creates a shooting order.** Let one session sit blocked for **at
least eight minutes** and bank the B1 shot during that window, *before* you start the answer cycle
for B4. If you film the panes first and block afterwards, the timer reads "1 minute", the premise
collapses, and B1 and B4 are visibly not the same session.

**B1 — say Antigravity, never Gemini.** `agy` lands on the Antigravity row; Gemini is a separate row
and it is grey on this machine. Calling it Gemini makes your first sentence contradict the screen.

**B2 — "every agent working right now", not "every agent on the machine".** Part 3 has you launch
with `--window-hours 3` precisely so that most agents on this machine do *not* appear. The narrower
claim is the true one and it is not weaker.

**B3 — green does not mean "found sessions".** It is `discovered && !error` (`web/regular.js:20`),
and for most harnesses `discovered` is a store-presence probe, not a session count
(`collectors/claude.py:270`, `collectors/codex.py:19`, and the same shape in copilot, cursor, goose
and opencode). An empty store directory renders green with zero sessions.

**B3 — "six of ten" is cut from the narration on purpose.** B1 already said four. A third number in
the first 45 seconds invites counting, and the count does not reconcile: the strip is
window-independent, so after `--window-hours 3` you can have six green dots above a board showing
four cards. The figure is a good answer to a question ([Part 6](#part-6--the-bench-cut-material-ready-for-questions)),
not a line of script.

**B4 — this is the only beat whose timing cannot be fudged, and the silence is the point.** Speak the
27 words while the band is already red. Then stop. Answer the question on camera and let the band
clear with nothing on the soundtrack. Narrating over the clear is how this beat dies: the audience
*hears* that the problem was solved instead of *watching* it happen, and that difference is the demo.
The closing line goes over the cleared board, after the visual has landed.

**B4 — use a real `AskUserQuestion`, not a permission prompt.** This matters more than it looks.
The collector resolves state in a fixed order (`collectors/claude.py:441-457`):

```python
if info and info["pending_input_tool"]:
    session_state = "needs_input"  # wins outright
elif subagents or is_fresh(..., 90):
    session_state = "working"  # swallows the next branch
elif hook:
    session_state = "needs_input"  # loses while busy
```

A *hook-delivered* needs-input — a permission prompt, or the injection in
[Part 4](#part-4--recording-mechanics-and-retakes) — takes the **third** branch, and is therefore
invisible while the session has running subagents or any activity inside 90 seconds. The rig
deliberately keeps subagents running on the director, so the permission-prompt variant of B4 will
silently fail on you.

**Measured 2026-08-09: the first branch does not save the open-question variant either, and the
reason is not the ordering.** Claude Code does not write the `AskUserQuestion` `tool_use` record to
the transcript until the question is *answered*, so `pending_input_tool` is `None` for exactly as
long as the gate is open. Held at a live gate, `analyze_transcript` returned
`pending_input_tool: None, last_tool: None`; the only `AskUserQuestion` strings in the file were the
prompt text asking for one. The first branch therefore cannot fire while anyone is waiting, and both
variants of B4 depend on the same hook/overlay path.

That path had its own defect, fixed in `fix/needs-input-survives-background-writes`: a background
task completing appended bookkeeping records to the parked transcript, which moved the mtime that
`own_activity` reported, and the overlay reducer read that as "the human answered" and dropped the
wait for the rest of its life. That is what put `Needs you: 0` on screen for three minutes during the
rig run. With the fix, hold B4 on a session whose parent transcript is quiet and check the tile
before you roll: the gate is now visible, but nothing in the shot proves it stayed visible except
looking.

**B5 — do not say "amber" here.** B5 rests on a working card, and regular mode's long-turn marker is
`.lwarn`, coloured `--alert` (`web/regular.js:428`, `web/styles.css:156`, `--alert` at
`web/styles.css:15`) — red, in the same red as the band you just cleared. Amber is the *calm* ledger's
chip only. If a card in your take is genuinely flagged and you have the seconds spare, say "the
warning marker means this one has crossed fifteen minutes" — and only if the elapsed clock on screen
has actually crossed it, since the flag also fires on a projection (`turns.py:251` applies
`max(est_total, elapsed) >= 900`, `config.py:332`).

**B5 — "comparable turns", not "turns usually take".** The estimate is the median of only those past
turns that already lasted at least as long as the current one (`turns.py:236-245`), and it is `None`
when no past turn was this long. It is a conditional median, not an average, and the narration should
not describe it as one.

**B5 — verify the subagent pills read as three different names before you record.** The label falls
back through `name`, `description`, `agentType` from the sidecar metadata
(`collectors/claude.py:210-222`). Three concurrent subagents on this machine rendered three
*identical* pills. If yours do, cut "the subagents it spawned" — it is a clause, not a beat. Note also
that the card draws at most six pills (`web/regular.js:518`), so do not present the row as a complete
list of what is running.

**B6 — "every vendor's quota window", not "five-hour and weekly".** Only Claude has both of those.
Codex publishes weekly only; Cursor publishes a monthly billing cycle and no other window
(`quota.py:616`). Naming two specific windows while a monthly row is on screen is contradicted by the
screen. Also note the usage section needs no keystroke in regular mode — it sits between the tiles and
the needs-input band and has been on screen since B2, so B6 names something the audience has been
looking at for a minute rather than revealing it.

**B7 — the close creates desire; the card carries the facts.** Licence and dependency count are
retained by being readable, not by being spoken, and saying them costs seconds. "Nothing leaves the
box" is also a defensive frame answering an objection nobody has raised yet — it belongs on
[the bench](#part-6--the-bench-cut-material-ready-for-questions). What this audience should leave with
is that this exists, it is free, and they can run it tonight.

### If you are running long

The script is already cut to 167 words, so there is no fat left. If your rehearsal still overruns,
cut whole beats rather than shaving clauses — **B6 (11s)**, then **B5's subagent clause**. Both live
on the bench and both answer better as questions.

Do not cut B4, and do not shorten its silence.

---

## Part 2 — the busy-work rig

Paste this into a **fresh interactive Claude Code session**. That session becomes the director: it
builds a throwaway project, launches agents across four harnesses, hands you the cold-open shot, and
then blocks on you on purpose so B4 is repeatable.

Launch it from a directory you do not mind seeing on screen — the director's own row shows
`project · session id` drawn from its working directory.

**Every launch command below has been run against the real CLI.** Three of the four were wrong in the
first draft of this document. Two failed outright in under a second — and they failed *quietly*, in a
way that would have left the director reporting success while two harnesses never started. The
corrections below are the forms that actually parse.

````markdown
You are the director for a 2-minute screen recording of Cargento, a dashboard that maps live
coding-agent sessions. Your job is to make this machine look busy across four harnesses for about
20 minutes, using only throwaway work in a sandbox directory, and to hand me two specific shots.

## Hard constraints

- All work happens under `~/cargento-demo`. Create nothing outside it. Touch no other repo.
- No network calls, no package installs, no git push, no edits to any settings file.
- Never pass any blanket-permission flag. The list is longer than the two obvious ones, because
  Copilot's escalations are named nothing like Claude's or Codex's and its own help recommends one of
  them: `--dangerously-skip-permissions`, `--dangerously-bypass-approvals-and-sandbox`,
  `--allow-all-tools`, `--allow-all`, `--allow-all-paths`, `--allow-all-urls`, `--yolo`.
  If you hit permission friction, stop and tell me instead of escalating.
- Never pass `--ephemeral` to codex: it skips writing session files, so the session becomes
  invisible to the dashboard, which defeats the point.
- Include the literal token `CARGENTO-DEMO-RIG` in the text of every prompt you pass to another
  CLI. `agy` takes its working directory from its cwd and never as an argument, so the sandbox path
  is not in its argv — this token is the only reliable way to find every rig process afterwards.
- Launch each background agent in a subshell that `exec`s the CLI, so the PID you record is the CLI
  itself and not a wrapper shell:
  `( cd <dir> && exec nohup <cli> … >>~/cargento-demo/logs/<name>.log 2>&1 ) & echo $! >>~/cargento-demo/.pids`
- Generate `~/cargento-demo/stop.sh` that kills exactly the recorded PIDs and nothing else.

## Step 1 — build the sandbox

Create `~/cargento-demo/widget-shop`, `git init` it and make one commit **before** anything is
launched into it (codex refuses to run outside a repo). Fill it with a small, obviously fictional
Python project: about six files, ~400 lines — an order/pricing/inventory toy. Plant a handful of
real but harmless defects (an off-by-one in pagination, a float used for money, a mutable default
argument, a missing timezone, an unbounded cache, a swallowed exception).

Nothing about a real company, product, customer or credential. This directory name and these file
names will be on screen in a public video.

Also create `~/cargento-demo/logs/` and `~/cargento-demo/widget-shop/reports/`. Reports go **inside**
`widget-shop`, not beside it: codex's write sandbox is rooted at the directory you pass it, so a
sibling directory would be unwritable and its incremental writes would fail.

## Step 2 — register tracked tasks

Use TaskCreate to open four tasks named so they read well on a dashboard row: "Audit pricing for
rounding errors", "Review pagination boundaries", "Draft regression tests for inventory",
"Summarise findings". Mark one in progress.

Complete one — but let it run **at least a minute** before you complete it. A task finished in under
30 seconds is excluded from the estimate calculation, so completing one instantly produces exactly
the "no estimate" state that completing it was supposed to remove.

## Step 3 — launch three of your own subagents

Launch three subagents in one message so they run concurrently, each auditing different files.

- Give them three **clearly different** names. The names are what appear as pills on the dashboard,
  and three subagents with similar descriptions render as three identical pills, which is useless on
  camera. Then tell me what the three names are so I can check them against the screen.
- Run them on a cheaper model than your own, so the pills carry a visible model label. A subagent
  shows a model only when the child's and the parent's are both known and different.
- Have each one write **a separate file per source file reviewed** under
  `~/cargento-demo/widget-shop/reports/`,
  and append as it goes. Do not ask for one long essay at the end — see the note on tool calls below.

## Step 4 — launch one session per harness, in the background, staggered

Stagger these ~45 seconds apart so the board fills in visibly. Tee each one's output to
`~/cargento-demo/logs/<harness>.log`; those logs are what the cold-open shot films. Check each CLI
with `command -v` first and skip any that is missing rather than failing the run.

Use these command shapes exactly. **Flag order is load-bearing in two of the four**, and both were
wrong in the first draft of this document — each failed in under a second, silently enough that a
director agent would have reported four harnesses launched. The rule worth remembering: put the
prompt immediately after `-p` and let the flags follow it.

- Claude — **the prompt goes immediately after `-p`**, and the launch must `cd` into the sandbox.
  Both `--allowedTools` and `--add-dir` are variadic, so a prompt placed after either is read as one
  more tool name or directory and the run dies in under a second with *"Input must be provided either
  through stdin or as a prompt argument"*. A comma-separated tool list does **not** save you;
  `--add-dir` still eats it. And `--add-dir` only *adds* to the allowed set — it does not move the
  working directory, so without the `cd` the launch directory stays writable with `Write` in the
  allowlist:
  `( cd ~/cargento-demo/widget-shop && exec claude -p "<prompt>" --model sonnet --add-dir ~/cargento-demo --allowedTools Read Glob Grep Write Edit )`
  Launch a second on a different model for model diversity on the board. `Bash` is deliberately not in
  the allowlist. If a session hangs rather than finishing, tell me and stop — do **not** reach for
  `--permission-mode acceptEdits` or any bypass flag on your own; whether print mode denies or waits
  on a tool outside the allowlist is not something we have measured.
- Codex — needs `--add-dir` as well as `-C`. `-s workspace-write` makes only the `-C` root writable,
  and the reports directory below is a sibling of it, so incremental writes would be sandbox-denied
  and the card would grey out mid-take:
  `codex exec -C ~/cargento-demo/widget-shop --add-dir ~/cargento-demo -s workspace-write --skip-git-repo-check "<prompt>"`
  The repo-check flag is redundant inside a git repo and is cheap insurance if `git init` did not take.
- Antigravity — **flags first, `-p` last with the prompt as its value.** `-p`/`--print`/`--prompt` is
  a Go string flag, so `agy -p --sandbox …` sets the prompt to the literal text `--sandbox`,
  sandboxing never engages, and the real prompt is silently discarded — three failures at once, one
  of them a safety failure. This form was run and returned a normal answer:
  `( cd ~/cargento-demo/widget-shop && exec agy --sandbox --print-timeout 15m -p "<prompt>" )`
  After it starts, confirm the sandbox actually engaged and tell me. This machine's `agy` settings
  carry `toolPermission: "always-proceed"`, so `--sandbox` is the only restraint there is.
- Copilot — it has `-C`, and without it the row is labelled with my directory instead of the sandbox.
  Copilot also restricts file access to the working directory by default, so `-C` is doing
  containment work here and not just cosmetics:
  `copilot -C ~/cargento-demo/widget-shop -p "<prompt>" --allow-tool='write' --allow-tool='shell(ls)' --allow-tool='shell(cat)' --add-dir ~/cargento-demo`
  Copilot's help says `--allow-all-tools` is "required for non-interactive mode", and we have not
  tested whether the granular allowlist is enough. Watch for a third outcome as well as a refusal or
  a stall: with no allow flags at all, headless Copilot is not refused. It starts, reaches the gated
  tool and auto-denies every gated call in about a millisecond, so the run looks healthy while
  nothing it asks for happens (`docs/captures/copilot/permission-events-1.0.78-macos.jsonl`). If
  Copilot refuses, stalls, or comes back with denied tool results, **tell me and drop Copilot from
  the rig** — do not escalate. Three harnesses honestly counted beat four with the
  filesystem opened up.

**Every prompt must force frequent tool calls.** A session is Working only if its store changed in
the last 90 seconds, and a transcript is appended per *message*, not per token — so one long final
answer writes nothing for its whole duration and the card flips to idle mid-generation, then snaps
back. Ask for many small reads and writes: one file read at a time, one report file appended per
step. That is what keeps the card blue.

Note also that `--print-timeout` is a wait ceiling, not a duration: it does not make anything run
longer. If an agent finishes before I say stop, relaunch it with fresh work into the same log file so
the log keeps scrolling.

Then confirm the rig is actually up, which is **not** the same as counting harnesses in the payload —
this machine already has idle sessions from three harnesses, so a naive count passes before anything
launches. Record a start timestamp first, then poll:

```bash
curl -s http://127.0.0.1:4553/api/data | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(sorted({s['harness'] for s in d['sessions']
              if s['state']=='working' and s['last_activity'] > $START}))"
```

Report the list. If a harness never appears, say which and why rather than proceeding quietly.

## Step 5 — hand me the cold-open shot

Print, ready to paste, a single `tmux` command that opens a four-pane split with one pane per agent
log, each running `tail -f`. tmux is installed here (3.7b); if `command -v tmux` somehow fails, print
four separate `tail -f` commands instead and say that is what you are doing.

Do not launch it yourself and do not attach to it — I need to frame that window on camera.

## Step 6 — block on me, repeatedly

Once the Step 4 check passes, use **AskUserQuestion** to ask me a short, real question about the
sandbox: two or three plausible options, nothing rhetorical. It must be AskUserQuestion specifically
— a permission prompt does not produce the state I am filming while your subagents are running.

Then **every time I answer, do a little more sandbox work and ask another one.** I need several
takes. Space them out: do at least a minute of real work between questions.

## Step 7 — report

Print: the sandbox path, the log directory, the PID file, `stop.sh`, the tmux command from Step 5,
the three subagent names from Step 3, and one line per launched agent giving harness, model and the
exact command used. Then ask your first question and wait.
````

### Tearing it down

```bash
sh ~/cargento-demo/stop.sh          # kills only the PIDs the director recorded
```

Then check nothing survived, because a forgotten `agy` keeps burning Antigravity quota. Two sweeps,
because neither is sufficient alone:

```bash
pgrep -fl 'CARGENTO-DEMO-RIG' || echo "no rig prompts running"
pgrep -fl 'agy|codex|copilot|github-mcp-server' || echo "no harness processes running"
```

The token sweep finds the four launched agents, because all four CLIs are directly-exec'd binaries
and macOS `pgrep -f` does not truncate long argv — a 60,000-character command line still matched in
testing, so a long prompt is safe. What it cannot see:

- **Child processes started by the agents.** Copilot starts `github-mcp-server` by default; Claude
  starts a process per configured MCP server; any shell command an agent runs is its own PID. None
  carry the token, so the first sweep can print "clean" with those still alive. That is what the
  second sweep is for.
- **The director's three subagents have no operating-system process at all.** They run inside the
  director, so they are in neither sweep and `stop.sh` cannot address them. They die with the
  director, so this is a gap in what the check can tell you rather than a leak — but do not read a
  clean sweep as proof that nothing is generating.

Eyeball both lists before you walk away. Only then:

```bash
rm -rf ~/cargento-demo              # after you have the footage, not before
```

---

## Part 3 — pre-flight checklist

### Privacy — do this first; it is the one that cannot be fixed in post

The board shows **real session titles and real project paths**. This machine has 2585 Claude sessions
and 166 Codex sessions on disk, with titles like *"Debug Spacedock workflow steps not displaying"*.
That is internal work product, and a public demo video is a publication.

- [ ] Narrow the window, then restart:

      python3 "<skill-dir>/server.py" --port 4553 --stop
      python3 "<skill-dir>/server.py" --port 4553 --window-hours 3 --daemon

      `--window-hours` takes a float (`cli.py`), so `1.5` is legal if 3 is still too wide.
- [ ] **Read the idle titles in both modes before you record.** Do not believe that regular mode
      hides them: the idle list is clipped to `max-height:184px` with a fade (`web/main.js:81`), and
      each row is about 52px and renders its title at 17px (`web/regular.js:554`,
      `web/styles.css:199`). That is roughly **three fully legible titles plus a faded fourth, in
      every whole-page shot** — which includes B2 and the close, not just a ledger view.
- [ ] **`?all=1` is a clickable link sitting on the page, in frame, in both modes** — `Show all
      sessions`, rendered next to the idle drawer whenever the window is narrowed
      (`web/main.js:94`, `web/calm.js:610`). It is not a URL you have to decide to type; it is one
      stray click from putting every session back on screen. Keep the cursor away from it, and do not
      click it to "check something" mid-take.

      The window itself is a real server-side filter, which is the good news: sessions outside it are
      dropped inside each collector before the payload exists (`aggregate.py:243`,
      `collectors/claude.py:313`), and the SSE stream is pinned to the unfiltered-off variant
      (`http_api.py:399`), so no display mode, keystroke or devtools poke can surface them. That link
      is the one exception, and it works by triggering a fresh server-side collection
      (`http_api.py:337`).
- [ ] **The window filters on file mtime, not on how old the work is.** Any old session *resumed or
      merely touched* in the last three hours comes back carrying its original title. A `claude -c`
      an hour before the shoot can drag a year-old internal title into frame. This is why reading the
      titles is mandatory rather than a backstop: `--window-hours` narrows recency, not sensitivity.
- [ ] Confirm the green count you could be asked about matches the rows on screen. The harness strip
      is window-independent, so `--window-hours 3` leaves six green dots above a board that may show
      four cards. This is why B3's narration no longer states a count.
- [ ] Decide about the usage figures deliberately: the strip shows your real Claude percentages and
      your real Cursor spend, `$0.18 of $20.00` **for the current billing period**, not for today.

### Quota — this is a gate, not a footnote

This is the item most likely to cost you the evening, and the evidence is this document's own
authoring session. The Claude 5-hour window read **79%** when writing started and **99%** about three
hours later — 79, then 82, then 88, then 99 — without any of the rig running. Amber starts at 70% and
red at 90% (`web/usage.js:113-114`), so it was already amber at the first reading and effectively
spent by the last.

A single agent session doing ordinary work moves that bar 20 points in an afternoon. The rig is
several agent sessions plus a 20-minute recording.

- [ ] **The 5-hour bar must read under 40% before you launch the rig.** Read the reset time off the
      row and wait for it if you have to. This is a gate, not a preference: at 99% there is nothing
      to record with, and at 82% one run of the rig plausibly finishes the window.
- [ ] Plan the shoot for **early in a fresh 5-hour window**, and do not spend that window on anything
      else first — including building the sandbox. Have the director build the project, then check the
      bar again before Step 4 launches anything.
- [ ] Pin the **director** to a cheap model too. It is the largest single consumer, and telling the
      launched agents to use cheap models does nothing about it.
- [ ] Record **one long take and cut it down**. Re-running the rig per retake is what exhausts the
      quota; the director's re-asking is what makes that unnecessary.
- [ ] After the rig is up, re-check the usage strip for the **Codex row**. Claude and Cursor quota are
      fetched live, but Codex quota is read from Codex's own session files and is only as fresh as its
      last active turn — and snapshots older than the window are dropped rather than shown against a
      window that has already reset. That snapshot was **19.8 hours old** here, so at
      `--window-hours 3` the Codex row disappears until the rig's own `codex exec` writes a fresh one.

### Browser state — the dashboard remembers things between sessions

Seven `localStorage` keys under `cargento.*` persist per browser: `displayMode`, `usageOpen`,
`usageCfg`, `usageEnabled`, `usageModalSeen`, plus `leader` and `revision`, which are the
tab-election lease and carry no user state.

- [ ] Rehearse in calm mode and the page **opens in calm mode** on the take, wrecking B2. Land in
      regular mode at the end of every rehearsal. (Calm's sort order is a plain module variable and
      resets to `attention` on reload; the display mode does not.)
- [ ] A fresh browser profile shows the **usage-disclosure banner** on first load — in flow, at the
      top of the board in regular mode and as the first row inside the calm frame, never over it
      (`web/usage.js:803`). There is nothing to dismiss: answer it with **Keep usage on** before the
      take, or use a profile that has already seen it. The other button, "Turn it off", empties B6.
- [ ] If B6 comes up empty, the flag to check is **`cargento.usageEnabled`** — the feature switch,
      which blanks usage in both modes (`web/usage.js:83`, `web/usage.js:763`). Once it is off in a
      browser it stays off. Confirm the strip populates before recording.

      Not `cargento.usageOpen`: that one is **calm-mode only** (`web/usage.js:787` gates
      `usageBandCalm`; `usageSectionRegular` at `web/usage.js:777` has no such test). An earlier draft
      of this document had that backwards, and chasing the wrong flag costs you the take.
- [ ] Do not press `u` during the take. It is a *toggle*, not an opener, and the band defaults to open
      (`web/usage.js:54`, `web/usage.js:821`) — so pressing it blanks the thing you are pointing at.
      It is also calm-mode only (`web/calm.js:432`, below the mode guard), so in regular mode it does
      nothing and reads as a broken feature.

### Capture and audio — the two things discovered too late on playback

- [ ] **Capture the whole display, not the browser window.** The macOS notification renders in the
      display's top-right corner, outside the browser. A window-scoped capture region loses B4's
      popup, and you find out after the rig is torn down. Verify one popup is in frame before you
      commit to the long take.
- [ ] Normalise the audio to a stated loudness (**−16 LUFS** is a reasonable target) and check the
      mix on laptop speakers. Playing 6 dB quieter than the previous demo in the reel fails harder
      than any wording problem in this document.
- [ ] No music. It fights the notification chime, which is a sound you want the room to hear.
- [ ] **Burn in English subtitles.** The room is bilingual and you are asking people to read a dense
      dashboard while listening to a second language. This is the cheapest comprehension win here.
- [ ] Make the project name legible from frame 1 — a corner lower-third over B1 costs no narration
      seconds. In a reel, nobody knows whose demo this is otherwise.
- [ ] Say "mark" aloud before each usable event during the long take. The waveform spike is how the
      editor finds the banked B4 takes in twenty minutes of footage.

### Readability at a venue

- [ ] Browser zoom to ~150%, window at 1920×1080, dark theme. At 100% the board is unreadable on a
      projector.
- [ ] Hide the bookmarks bar and other tabs. Do not use browser full-screen if it changes your
      capture region — see the whole-display item above.
- [ ] Silence every other notification source. The only popup in frame should be Cargento's.
- [ ] Mouse movement is narration too. One target per beat, and stop moving while a number is read.

### Wiring — optional, and skipping it is defensible

"No configuration in the other harnesses" is a genuine selling point. For the record:

- [ ] Cargento is **not** installed as a plugin in Codex or `agy` here. Both run scan-only:
      discovery, state, ETA and token rate all still work, and Codex quota still appears because it
      comes off Codex's own session files. What you lose is event-driven freshness.
- [ ] Antigravity has no `statusLine`. (Checked: `~/.gemini/antigravity-cli/settings.json` exists and
      is 373 bytes — it is *not* empty, it simply has no `statusLine` key. It does carry
      `toolPermission: "always-proceed"`, which is why the `agy --sandbox` flag order in Part 2 is a
      safety matter and not a detail, and it pins a model, so `agy` will not contribute model
      diversity whatever the prompt asks.) Wiring `statusline_hook.py` would add a fourth vendor to
      B6 — see [the skill body](../cargento/skills/cargento/SKILL.md).
- [ ] The `Notification` and `SessionEnd` hooks are **not** in `~/.claude/settings.json`. They are not
      needed for B4. Note the split they affect: hook-driven popups fire with no browser tab open,
      but transcript-detected questions need a collection pass, which the periodic tick gates on a
      connected stream (`observation.py:416-419`) — so that path needs the dashboard page open, which
      it will be.

---

## Part 4 — recording mechanics and retakes

**Record long, cut to 2:00, voice over the finished cut.** Do not attempt a live single take with
narration. Timing a spoken sentence to an event you do not control fails far more often than it
works, and B4 depends on exactly that.

1. Start the dashboard with the narrowed window. Open the page and leave it open ~10 minutes so the
   rate sparklines have history.
2. Start the rig. Wait for its Step 4 check to pass, then re-check the usage strip for the Codex row.
3. Open the four-pane log window the rig printed and frame it. Start the screen recording, capturing
   the whole display.
4. Wait for the director to block on you, and then **leave it blocked at least eight minutes.** Film
   the four-pane cold open during that window — three panes scrolling, one frozen, timer overlaid.
   This ordering is the easiest thing in the whole plan to get wrong.
5. Now answer the question on camera and let the band clear. Repeat to bank several B4 takes, leaving
   **at least 60 seconds between takes** (see the cooldown note below). Say "mark" before each.
6. Capture the working cards and the usage strip.
7. Stop recording, tear the rig down, then edit. Record narration against the locked cut.

### Retakes are cheap but they are not free

The director re-asks after every answer, so you can bank B4 takes without restarting anything. Two
limits apply, both from `config.py:329-331` and `notifications.py:290-296`:

- A popup fires at most once per 60 seconds per session, with a 15-second global floor. Takes closer
  together than a minute get the band but no popup.
- A popup with the **same message text** as the previous one is suppressed for 600 seconds. Real
  AskUserQuestion takes vary their text naturally; the injection below does not.

### The injection fallback, and the three ways it does nothing

If a real pending question will not appear on camera, the same state can be produced directly — it is
the identical payload Claude Code itself posts:

```bash
echo '{"session_id":"<a session id Cargento already lists>","notification_type":"permission_prompt","message":"Claude needs your permission to run Bash"}' \
  | python3 "<skill-dir>/notify_hook.py"
```

Four things about it, verified rather than assumed. The first three are ways it fails **silently**:

- **The target must be quiet.** A hook-delivered needs-input loses the branch race to `working`
  whenever the session has running subagents or any activity inside 90 seconds
  (`collectors/claude.py:441-457`). Aim it at a session that is idle on the board *right now* —
  aiming it at the busy director produces nothing visible at all.
- **The target must not be a subagent.** A subagent prefix is dropped outright
  (`notifications.py:277-279`).
- **The message must differ from last time.** Re-running this line with the same string gets you one
  popup per ten minutes and silent no-ops in between.
- **An unknown session id still fires the popup.** It does not produce a row — but `notifications.py`
  never checks the id against a live session, so a mistyped id gives you a desktop notification with
  nothing behind it, which is the worst thing that can happen mid-take. Copy the id from `/api/data`.

The `message` string is rendered as the row's detail almost verbatim: it is truncated at 500
characters and MCP tool names are rewritten, neither of which touches a plain sentence. It will be
read on screen, so write it as a real permission prompt.

Injected notifications live in memory only, so restarting the server clears them.

Use this to rehearse timing. If it ends up in the final cut, keep B4's narration to what it actually
is — a permission prompt Cargento detected — and do not describe it as an open question. It produces
real state through the real code path, which is what makes it a legitimate retake tool; the line it
must not cross is narrating a synthetic trigger as an organic one.

### Fallback if the rig will not cooperate

Drop to two harnesses and rewrite B1 to say two. A short honest demo of two live agents beats a
padded one claiming four while the screen shows three. Never narrate a count the screen does not
support.

---

## Part 5 — claims to avoid

Each is wrong or unprovable in a 2-minute video, and each has a true version.

| Don't say | Why | Say instead |
|---|---|---|
| "It monitors ten agents" | Ten are *supported*; six were discovered here, and only what is installed can appear | "Ten harnesses supported, six found on this laptop" |
| "Every agent on the machine" | The window filter is what makes the board readable, and you set it to 3 hours on purpose | "Every agent working right now" |
| "Green means it found sessions" | Green is `discovered && !error`, and `discovered` is a store-presence probe for most harnesses — an empty store renders green | "Green means it found that tool's data on this machine" |
| "The amber flag" (on a working card) | Regular mode's long-turn marker is `--alert` red; amber is the calm ledger's chip only | "The warning marker" |
| "Five-hour and weekly windows across vendors" | Only Claude has both. Codex is weekly-only; Cursor is a monthly billing cycle | "Every vendor's quota window" |
| "Nothing leaves your machine" | Exactly two outbound endpoints exist, both quota, both on by default: `quota.py:65` and `quota.py:70`. Everything else in the runtime is loopback | "Nothing leaves the box but the quota check" — and `--no-usage` turns it off |
| "It's agentless" / "zero config" | The plugin does install lifecycle hooks, and Antigravity's status line is a manual step | "It reads what these tools already write to disk" |
| "`agy` is Gemini" | `agy` is Antigravity CLI. Gemini CLI is a separate row, grey here since it stopped serving consumer accounts in June 2026 | "Antigravity" |
| "It tells you an agent is stuck" | Only `needs input` means blocked. `long turn` means long; `stale` means idle a while. Neither claims stuck | "It tells you which one is waiting on you" |
| "It predicts when you'll hit your limit" | Burn projection deliberately refuses that verdict: a rate and an interval, never a race call against the reset | "It shows how fast you're burning; you make the call" |
| "Rate zero means idle" | A dash is unmeasured — either nobody reports it *or the read failed*; a zero is a measurement | "A dash is unmeasured; a zero is a measurement" |

---

## Part 6 — the bench: cut material, ready for questions

These were cut from the script for time or comprehension, not because they are weak. Each is a good
answer to a question and a bad use of ten seconds of a reel.

**Calm mode.** One dense ledger row per session for boards with more agents than fit as cards,
sorted by attention so whatever needs a human is at the top. `c` toggles it. It was cut because the
demo only has four agents on screen, so it cannot actually show the scale it exists for.

**The dash.** Where a harness publishes no token rate, the cell shows a dash rather than a zero,
because an absent measurement and a measured zero are different facts. This is arguably the most
principled thing in the product and it was still cut: reading it off a first-encounter ledger takes
five inferential steps, and a stranger's default reading of a blank cell is "broken, or not
supported yet". It costs trust in six seconds and earns it in sixty.

**Burn projection.** Off by default. Fits a slope through each quota window's readings and prints the
rate, its resolution, and the interval in which the window is projected to hit 100% — and pointedly
does *not* say whether the reset gets there first, because a slope fitted to a handful of integer
readings cannot settle that. Needs three readings spanning ten minutes before it says anything, and
loses them on reload.

**"Six of ten."** Claude, Codex, Pi, Antigravity, Copilot and Cursor were found here; Gemini,
OpenCode, Goose and Droid were not.

**The security model.** Read-only local file reads, a loopback-only server, and two outbound quota
endpoints that can be switched off. `SECURITY.md` is the contract.

---

## Appendix — what this machine reports today

Captured 7 August 2026, Cargento 0.10.0, macOS, Python 3.12.13. Re-run `--diagnose` on the day.

| Harness | Discovered | Sessions on disk | CLI installed |
|---|---|---|---|
| Claude | yes | 2585 → 2594 | yes |
| Codex | yes | 166 → 167 | yes |
| Pi | yes | 2 | no |
| Gemini | no | – | no |
| Antigravity | yes | 15 → 18 | yes (`agy`) |
| Copilot | yes | 2 | yes |
| OpenCode | no | – | no |
| Cursor | yes | 3 | yes (`cursor-agent`) |
| Goose | no | – | no |
| Droid | no | – | no |

The arrows are the same three hours: session counts grow monotonically while you work, so treat every
count here as a floor. The **Discovered** column is the stable part and was correct at every reading.

Six discovered, five drivable from a shell. Usage populated for three vendors: Claude (5-hour
**79% → 99%** across the session, weekly 31% → 34%, one per-model row labelled `Fable` at 0%), Codex
(weekly 54% throughout, snapshot ~20h old), Cursor (monthly 1%, `$0.18 of $20.00` for the billing
period). Native notifications: `osascript`. Calm mode's default sort is `attention`; the default
display mode is `regular`. tmux 3.7b installed. CLI versions tested: claude 2.1.224, codex 0.146.1,
agy 1.1.11, Copilot 1.0.78.

Two things follow for the script. Do not speak a percentage on camera — read what is on screen or say
nothing. And the `Fable` row sitting at 0% renders as an empty bar, which is a weak thing to rest a
sentence on, so B6 names no specific window.

Related reading: [the shipped skill body](../cargento/skills/cargento/SKILL.md) for behaviour,
[SECURITY.md](../SECURITY.md) for the quota-read contract, [README.md](../README.md) for install.
