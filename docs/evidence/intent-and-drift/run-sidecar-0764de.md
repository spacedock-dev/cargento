# Intent and drift run: sidecar-0764de

Exploratory agent-operated pass, recorded from the [sidecar prompt](PROMPT.md) on the commit that added its hooks-file step. It is not a DRC-4722 human verdict or a qualification case. It covers two Claude Code sessions, S1 and S2, from one sidecar. The participant approved both session choices and both sets of goal and outcome lines, ran the hooks turn for each, and pressed Analyze and Allow personally. Every other browser step was agent-operated. Private captures stay in the gitignored local screenshot folder; none are committed.

| Field | Observation |
|---|---|
| Run label | sidecar-0764de |
| Classification: exploratory agent-operated, exploratory human, or DRC-4722 cold candidate | exploratory agent-operated |
| Cargento `origin/main` SHA | `07e7290fa4d5dde563b60339771b939266dc3a20` |
| Cargento start flags (omit paths) and platform | `--port <unused loopback port> --window-hours 720 --daemon` with a new private `CARGENTO_HOME`, started once and not restarted. No `--observer-model`, no `--no-observer-model`. macOS 26.5.2, Python 3.11.14. |
| Selected session age and generic work description | S1: last turn about 10.6 hours before the pass, started about 6 days before it; setting up a shared canvas server for a team. S2: last turn about 0.5 hours before the pass, started the same day; a canvas UI change, then a deployment change. Both sessions are in the participant's other repositories, not this one (see Findings 1). |
| Why a newer session was skipped | In each repository the only newer session was actively running with subagents, so a resumed turn would have collided with live work. |
| DRC-4717 and DRC-4683 verdict links and target SHA, if a cold candidate | not applicable: exploratory run |
| Observer's sample capture and press/timing preflight, if a cold candidate | not applicable: exploratory run |
| Reading route and available provider before the walk | Claude route falls back to Codex (OpenAI, `gpt-5.6-luna`), reason `fallback-not-qualified`: "Claude Code checks are built but not yet qualified, so Codex reads this session." Codex CLI 0.153.4, logged in. The Claude producer gate was not bypassed. |
| Human walk: date, browser, viewport | not observed: no human walk in this run |
| Agent-operated pass: date, browser, viewport | 2026-10-01, HeadlessChrome 151 driven by `agent-browser`, viewport 1440 wide for all 23 captures |
| Model provider named by the page | Codex, reaching OpenAI |
| Consent chosen by participant; attempt count | Participant pressed Allow and analyze personally, in their own browser. Consent was stored for Codex and for tool output to OpenAI. The pass allowed one attempt per session. The sidecar recorded three model requests per session, six in all (Findings 4). |
| Screenshot review: anonymous role, status; issue attachment approved? | pending: participant review of 23 local captures |
| DRC-4722 issue comment link, if any | none: private evidence was not submitted |

## Human walk

Not observed: this run is agent-operated, so every row in this section is outside its scope.

| Observation | Result, pass/fail/partial, or reason not observed |
|---|---|
| Presses and elapsed time: Sessions row to result (limit: three presses) | not observed: agent-operated run |
| Presses and elapsed time: Sessions row to copied correction (limit: four presses) | not observed: agent-operated run |
| Draft noticed and checked? | not observed: agent-operated run |
| Each hesitation and its screenshot reference | not observed: agent-operated run |
| Level meaning and source, in participant's words or issue link | not observed: agent-operated run |
| Cited entry found? Meaning of "Can't tell," in participant's words or issue link | not observed: agent-operated run |
| Steer back or Update intent instead; why | not observed: agent-operated run |
| Correction pasted? Did later evidence show a return to intent? | not observed: agent-operated run |
| Would they leave the live monitor on? Verbatim approved answer or issue link | not observed: agent-operated run |
| What would they have done without Cargento? Verbatim approved answer or issue link | not observed: agent-operated run |
| Uncoached from row? Participant did not build panel? | not observed: agent-operated run |

## DRC-4722 verdict handoff

Not applicable: this is not a cold candidate.

## Agent-operated sidecar pass

| Stage | Rendered output, result source, citation numbers, or reason not observed | Screenshot reference and human review status |
|---|---|---|
| Draft and confirmed intent | On both rows the goal arrived drafted "from your prompt" as the harness's injected launch instruction, not anything the participant typed (Findings 2). The participant approved a typed goal and outcome lines: three for S1, two for S2. Saving the typed goal opened the window at the latest prompt. S1 listed 1 entry. S2 said "3 earlier entries, from before your intent's window opened, are counted and not listed." The later-direction question disappeared on save, so Keep could not be pressed before the hooks turn. Both headings read "Confirmed", "revision 2 of 2". | S1 01–06, S2 01–05; pending review |
| Live monitor and estimate | "Not enough recorded yet", "Live estimate", "Reads checks and file paths, not what your intent says." on both. | S1 07, S2 06; pending review |
| Analysis consent and phases | After the hooks turn, S1 showed "A turn stop was observed; no session end was" and the helper "Reads the session up to its last turn against your intent." About three minutes later the row reverted to working (Findings 3). After `/exit`, both rows read "ended" and "A session end was observed". The participant answered the later-direction question raised by the hooks turn with Keep and pressed Analyze. On S2 the page showed "Analyzing drift" with "Preparing what is sent", "Waiting for Codex", "Checking the reply" and Cancel, beside an already stored result. | S1 08, 09; S2 07; pending review |
| Result level and outcome verdicts | Both readings: level "Can't tell". Goal: "Can't tell: nothing recorded shows this yet". Every outcome line: "Can't tell" with "limit · This constraint was not put to the reading when it was made, so no verdict on it was asked for." Both said "A session end was observed before this was read, so this covers the work through that end." Departures: "This reading verified none of the constraints it read, so it raised nothing and confirmed nothing." The header beside each result read "Not enough recorded yet". | S1 10, S2 08; pending review |
| Cited activity and later direction | No entry was cited in either reading. Each window held only person-authored prompts: "1 entry · 1 direction you gave · 0 observed of what it did" (S1) and "2 entries · 2 directions you gave · 0 observed of what it did" (S2). The later direction from the hooks turn was settled with Keep: "You settled this … against revision 2." | S1 10, S2 08; pending review |
| Steer back and copied correction | Steer back opened a correction box after a short delay. The text Copy wrote to the clipboard matched the box exactly: 553 characters on S1 and 414 on S2, as captured from the page's clipboard call. The button then read "Copied". Each correction listed every outcome line as having nothing recorded yet, although the reading asked no verdict on those lines (Findings 5). | S1 11–13, S2 09–10; pending review |
| Update intent instead | not offered on either session: the page draws it only under a departure, and neither reading raised one | S1 12, S2 09; pending review |
| New evidence and Analyze again | not observed as a deliberate step: the extra requests in Findings 4 were not planned second attempts | none |

## Findings and limits

1. **This repository held no usable session.** The only Claude Code sessions in this project were the one running this pass and a 29-day-old session with three prompts whose workspace no longer exists. With the participant's approval, the shortlist moved to two of the participant's other repositories.
2. **A Conductor-launched session's draft goal and row title come from the harness's injected launch instruction.** Both rows offered that instruction as the goal drafted "from your prompt". The draft cannot be adopted, and typing a goal opens the window at the latest prompt. A Conductor session therefore has no route to a meaningful goal whose window covers the work.
3. **A non-conversation transcript record turns an idle or ended row back into working.** On S1 the hooks turn stopped and the sidecar published `finished_at` with state `idle`. About three minutes later Claude Code appended a `system` record of subtype `away_summary`. The row then reported `working`, "running Bash", a turn in progress with an estimate, and "No stop or end observed", and `finished_at` was cleared. S2 showed the same state after Conductor re-attached the session. After `/exit`, both rows published `ended_at` and the page said "ended", but `/api/data` still reported `working`, and the TURN row still read "… into turn". The study prompt's precondition, idle with `finished_at`, was gone within minutes; only an observed session end held.
4. **Each session recorded three model requests against a one-attempt budget.** The participant reports pressing Analyze at least twice on S1. On S2 the participant pressed Analyze before running the hooks turn. The page accepted the press although no stop or end had been observed, while the row reported the working state from finding 3. A reading made then cannot cover a finished turn. Each press spends from the twelve-per-day budget, and a failed press is not refunded.
5. **Both readings were "Can't tell" for a structural reason, not a judgement about the work.** A typed goal opens the window at the latest prompt. A finished session's latest prompt has little or no work after it, so the window held only prompts. With no work evidence sent, the outcome lines were not put to the reading. Steer back still told the session that nothing was recorded for every line. The correction joins each line to its state with ".:" when the line ends in a period. Prior run [sidecar-055892](run-sidecar-055892.md) Finding 2 records the same window rule.
6. The line "Choose a goal or use your prompt, then analyze drift" stayed on the page after a typed goal was saved, as in sidecar-055892 Finding 4.

No issue has been filed yet; findings 2 to 5 await the participant's approval to file in the Intent and drift milestone. Steps not reached: a reading with a level other than "Can't tell", cited entries, Update intent instead, and a deliberate Analyze again. A public summary alone does not satisfy DRC-4722's screenshot and participant-answer criteria.
