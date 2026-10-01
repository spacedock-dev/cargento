# Intent and drift run: sidecar-055892

Exploratory agent-operated pass, recorded from the [sidecar prompt](PROMPT.md). It is not a DRC-4722 human verdict or a qualification case. The participant approved the session choice, the goal and outcome lines, and pressed Allow. Every browser step below was agent-operated. Private captures stay in the gitignored local screenshot folder; none are committed.

| Field | Observation |
|---|---|
| Run label | sidecar-055892 |
| Classification: exploratory agent-operated, exploratory human, or DRC-4722 cold candidate | exploratory agent-operated |
| Cargento `origin/main` SHA | `fa5f2149687a789d274988bbb7e80737882c7bb3` |
| Cargento start flags (omit paths) and platform | First `--port 4571 --daemon` with a new private `CARGENTO_HOME`; restarted as `--port 4571 --window-hours 240 --daemon` on the same home (see Findings 1). No `--observer-model`, no `--no-observer-model`. macOS 27.0.1, Python 3.14.6. |
| Selected session age and generic work description | Claude Code session in this project, last transcript write about 9.6 days old, started about 52 days ago. Onboarding work: explain the repository and recommend next tasks, later a summary of recent work. |
| Why a newer session was skipped | The only newer Claude Code session in this project was the session running this pass, which has no work of its own to check. |
| DRC-4717 and DRC-4683 verdict links and target SHA, if a cold candidate | not applicable: exploratory run |
| Observer's sample capture and press/timing preflight, if a cold candidate | not applicable: exploratory run |
| Reading route and available provider before the walk | Claude route falls back to Codex (OpenAI, `gpt-5.6-luna`), reason `fallback-not-qualified`: "Claude Code checks are built but not yet qualified, so Codex reads this session." Codex CLI 0.159.3 installed. The Claude producer gate was not bypassed. |
| Human walk: date, browser, viewport | not observed: no human walk in this run |
| Agent-operated pass: date, browser, viewport | 2026-10-01, Chrome 154, viewport 1280 wide for capture 01 and 1697 wide for captures 02 to 10 |
| Model provider named by the page | Codex, reaching OpenAI |
| Consent chosen by participant; attempt count | Participant pressed Allow and analyze personally. Consent was stored for Codex and for tool output to OpenAI. One press; the reading was withheld before any model call, so 0 model requests were recorded. |
| Screenshot review: anonymous role, status; issue attachment approved? | participant reviewed all 10 local captures; no issue attachment approved, so the captures stay local |
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
| Draft and confirmed intent | With `?all=1` only, the page showed "Title not published", "0 entries" and a disabled `Analyze drift` (Findings 1). After the window restart, the goal arrived drafted "from your prompt", and the page asked about 5 later directions (#2 to #6) with `Keep my intent` and `Add it to my intent`. The participant approved a typed goal and two typed outcome lines and chose Keep. Saving the typed goal moved the evidence window to the latest prompt before the save: the list went from 6 entries to 1, "5 earlier entries, from before your intent's window opened, are counted and not listed", and the later-direction question disappeared, so Keep could not be pressed (Findings 2). The heading then read "Confirmed", "revision 2 of 2". While an outcome line was unsaved, `Analyze drift` was disabled. | 01, 02, 03, 04, 05; pending review |
| Live monitor and estimate | "Not enough recorded yet", "Live estimate · 09:23", "Reads checks and file paths, not what your intent says." | 06; pending review |
| Analysis consent and phases | The first press on `Analyze drift` showed the disclosure and `Allow and analyze`, with "0 model requests recorded for this session." A first Allow from a participant tab opened before a server restart did not reach the server. The second, in the current tab, stored consent. No analysis started and no phase box appeared. The READING block then said: "This session is idle with no stop and no end observed, so whether there is finished work to read is unknown rather than none." (Findings 3) | 07, 08, 09, 10; pending review |
| Result level and outcome verdicts | not observed: the reading was withheld (`idle-unknown`), so no level or line verdicts exist | none |
| Cited activity and later direction | not observed: no reading, so no citation. The page said "Nothing you have said since you saved these words is in the observed record read for this session." | 10; pending review |
| Steer back and copied correction | not observed: Steer back is offered beside a stored reading, and there was none | none |
| New evidence and Analyze again | not observed: no reading, and a second attempt was not authorized | none |

## Findings and limits

1. **`?all=1` lists an out-of-window Claude Code session but does not read its transcript.** `collectors/claude.py` analyzes a transcript only when the session is inside the display window, so the row had no prompt, no title and 0 entries. The prompt's advice to use `?all=1` for an older session therefore reaches an empty drift panel. The documented `--window-hours` flag widened the window enough to read the session.
2. **A typed goal on a finished session reads only its last turn.** This matches DEC-24 item 13 (typed words open the window at the latest person-authored message at or before the save). On a past session, it means most of the work sits before the window, and the later-direction question goes away with it.
3. **A fresh sidecar cannot complete an analysis of a past session.** `reading.eligibility` reads a session only while it runs, after a turn stop it observed, or after an observed session end. A sidecar started after the session went quiet observes none of these, so the press is withheld as `idle-unknown`. Before the press, the page offered `Allow and analyze` as the primary control and did not say that no reading could start. After the press, it gave the reason but no next step. The SKILL says a control that cannot run "names one next step".
4. The line "Choose a goal or use your prompt, then analyze drift" stayed on the page after a typed goal was saved.

Findings 1, 3 and 4 are filed as [DRC-4763](https://linear.app/recce/issue/DRC-4763), which blocks DRC-4722. The milestone already records the withhold in finding 3 as correct product behaviour; the defect is that the study prompts do not route the sidecar an observed stop. Steps not reached: result level, line verdicts, citations, Steer back, Copy, Update intent and Analyze again. All of them need a stored reading. A public summary alone does not satisfy DRC-4722's screenshot and participant-answer criteria.
