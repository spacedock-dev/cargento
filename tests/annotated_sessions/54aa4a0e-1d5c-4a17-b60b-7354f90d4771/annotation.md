# This drift tool MUST be usable

- **Session:** `54aa4a0e-1d5c-4a17-b60b-7354f90d4771`
- **Date:** 2026-09-28 (UTC, first message)
- **Excerpts:** [steering-excerpts.txt](../../raw_sessions/54aa4a0e-1d5c-4a17-b60b-7354f90d4771/steering-excerpts.txt) holds every message cited below. A bare `#N` is a message number; `PR #N` is a pull request
- **Full log:** `tests/raw_sessions/54aa4a0e-1d5c-4a17-b60b-7354f90d4771/54aa4a0e-1d5c-4a17-b60b-7354f90d4771.jsonl`, sanitized and gitignored (local only)

> Green checks and reviewer passes kept saying the work was done, but Claude kept testing under conditions you never had, so it took your pushback to find that the scan was too narrow and the drift panel did not work for a real user.

## Overall goal

Pick the milestone back up after Codex's stretch: finish the walk Codex could not close, clear the issues it turned up, get the Claude Code reader qualified, and end with an Intent and drift panel you and your users can actually use.

## Outcome

- DRC-4719 closed after its walk. The four issues the walk filed (the reading timeout, the stale level after a save, a wrong Codex judgement, the installer canary) were merged or ruled on, along with a test timing-grace fix, the slash-command fixes (DRC-4764, DRC-4766) and a teammate's two run records.
- After you disagreed with "no usable case", a second scan of your own corrections found real cases. Two more scored runs each failed by one judgement (15 of 16), and you then accepted the Claude Code checks anyway, recorded as "accepted", never "passed".
- PR #476 rebuilt the Intent and drift panel over four rounds: a clear consent step, a result with a level meter, a native select for your prompts, popovers that don't move the page, eased motion, a spinner on Save intent, and idle Claude Code sessions that can be analyzed from their own transcript.
- Your two consent rulings built into the same PR: one Allow per provider, and an Allow tied to where your words go. CI green, not merged at the end of the session.

## Lookup: goal → drift → steering

| Part | Goal | Drift | Steering | Outcome |
|---|---|---|---|---|
| 1 | Get grounded on the milestone after Codex's work, finish DRC-4719, then clear the issues the walk filed and the ones that followed. | #7 | #8 | DRC-4719 closed. Readings got a 180-second limit, the stale level and installer canary were fixed, flaky timing tests were fixed, slash-command directions now count as yours, and a teammate's study run was merged. |
| 2 | Find a real case to test the Claude Code reader with, score it, and decide whether Claude Code may read Claude Code sessions. | #31 | #32 | Your corrections turned out to be the missing evidence. Two more scored runs each failed by one judgement. You chose to accept the Claude Code checks anyway, and it was recorded honestly as an acceptance over failed runs. |
| 3 | Make the Intent and drift panel clear and working, the way the original design was. | #43, #51 | #50, #52 | PR #476: a clear consent step, a result in place of the button, roomy textareas, real buttons, a native select for your prompts, popovers that don't move the page, and eased motion. |
| 4 | Make Save and Analyze tell you what they are doing, and cut the remaining long text. | #51, #53, #55 | #54, #58 | Save intent shows a spinner and blocks a second press. Idle Claude Code sessions stay analyzable, and any change is explained in one line. "What is sent" is six short points in a popover. Consent is per provider and tied to where your words go. |

## Pushback messages

| # | Time (UTC) | Part | Message (start) |
|---|---|---|---|
| #8 | 2026-10-01 00:42 | 1 | wait, you said "Both lenses are running" but I don't actually see anything running. are they actually running? |
| #32 | 2026-10-01 04:50 | 2 | I know you say there is "No usable case", but I actually disagree. there have been multiple times I have communicated with you or stopped yo… |
| #50 | 2026-10-01 09:48 | 3 | use ultrathink and ultracode on the following. When running the UI, [NAME_2] and I noticed a number of UI issues, UX issues, and interaction… |
| #52 | 2026-10-02 02:09 | 3 | use ultrathink and ultracode on the following. [Image #5] [Image #6] [Image #7] Please look at your changes and use Claude in Chrome. The to… |
| #54 | 2026-10-02 05:22 | 4 | [Image #10] I am looking at http://127.0.0.1:4585/#n=session:[ORG_NAME_2]%2Fcargento:claude:54aa4a0e&from=sessions. After adding the Goal an… |
| #58 | 2026-10-02 05:55 | 4 | [Image #13] Also - this note is long and arduous to read. The text should be clear and to the point, stop overusing prose. And you should al… |

## 1 · Finish what Codex couldn't close

**Goal:** Get grounded on the milestone after Codex's work, finish DRC-4719, then clear the issues the walk filed and the ones that followed.

**Outcome:** DRC-4719 closed. Readings got a 180-second limit, the stale level and installer canary were fixed, flaky timing tests were fixed, slash-command directions now count as yours, and a teammate's study run was merged.

| Kind | Time (UTC) | What happened | Messages |
|---|---|---|---|
| Claude did | 2026-09-28 11:56 | On 28 September, merged three PRs, then paused the burndown and wrote a handoff so Codex could carry on. | #0 |
| You asked | 2026-09-30 23:22 | Read the milestone and the open issues to get grounded, then finish DRC-4719, which Codex couldn't close because Claude wasn't logged in. | #4 |
| Claude did | 2026-09-30 23:22 | Walked the failure-and-recovery scenarios on made-up sessions. 11 of 12 passed. Filed three issues, including a 60-second timeout that cut off long readings. | #5 |
| You asked | 2026-10-01 00:13 | Take care of the three issues you just filed. | #6 |
| Claude did | 2026-10-01 00:13 | Measured the timeout (it was the provider's response time, not input size), started builders and review lenses. | #7 |
| Claude drifted | 2026-10-01 00:13 | Said "Both lenses are running this time" when all it had checked was that no error had shown up yet. Nothing was visible to you. | #7 |
| You pushed back | 2026-10-01 00:42 | "wait, you said "Both lenses are running" but I don't actually see anything running. are they actually running?" | #8 |
| Claude did | 2026-10-01 00:42 | They were running. Merged the timeout fix, re-walked the long reading (about 81 seconds, now completes), and opened the stale-level fix. | #9 |
| You asked | 2026-10-01 01:03 | Add more grace to the timing checks so tests fail less by chance. Then fix the installer canary too, and finish DRC-4719. | #10, #12, #14 |
| Claude did | 2026-10-01 01:03 | Fixed the flaky tests by fixing races and widening only bounds it could prove still catch a real failure. Reviewed and repinned the installer. Closed DRC-4719. | #11, #13, #15, #17 |
| You asked | 2026-10-01 01:38 | Fix the new slash-command issue (DRC-4764), merge a teammate's study run, and do DRC-4766 after DRC-4764. | #18, #22, #24 |
| Claude did | 2026-10-01 01:38 | Slash commands you type now count as your directions, and a session that opens with /clear no longer gets "/clear" drafted as its goal. Merged the teammate's run record and fixed the study prompts it showed were broken. | #19, #23, #25, #29 |

### Why Claude got confused

- **#8:** Claude took the absence of any model error as proof the reviewers were working, and had started them as hidden background processes, so you had nothing to look at. Claude admitted that was not proof, checked the processes, and switched to monitors you could see.

## 2 · Qualify the Claude Code reader

**Goal:** Find a real case to test the Claude Code reader with, score it, and decide whether Claude Code may read Claude Code sessions.

**Outcome:** Your corrections turned out to be the missing evidence. Two more scored runs each failed by one judgement. You chose to accept the Claude Code checks anyway, and it was recorded honestly as an acceptance over failed runs.

| Kind | Time (UTC) | What happened | Messages |
|---|---|---|---|
| You asked | 2026-10-01 01:22 | Finish DRC-4758: decide the next qualification packet. | #16 |
| Claude did | 2026-10-01 01:22 | Scanned 4,882 of your recorded sessions for a failed test that caught the agent going off on its own. Found none. On your ruling, closed DRC-4758 as "no eligible case". | #17 |
| You asked | 2026-10-01 04:47 | Is DRC-4666 (qualifying the Claude Code reader) still blocked? | #30 |
| Claude drifted | 2026-10-01 04:48 | Said yes, because there is "No usable case" anywhere in your recorded work. | #31 |
| You pushed back | 2026-10-01 04:50 | "I know you say there is "No usable case", but I actually disagree." You have stopped Claude many times to say it was doing the wrong thing or stopped short. "I am surprised you looked through over 4000 recorded sessions and found nothing. Please look again" | #32 |
| Claude did | 2026-10-01 04:52 | Rescanned your own messages for corrections. Found 87 sessions, and all 9 it tried resolved as departures. Said plainly that "no usable case" was wrong. | #33 |
| You asked | 2026-10-01 04:55 | You ruled on Claude's two questions: a departure case can rest on your own correction instead of a failed test, and an old turn stop can be confirmed by the transcript itself when the history store has rolled past it. | #34, #36 |
| Claude did | 2026-10-01 05:09 | Built and merged the transcript rule after full review. Then found that readings only showed the model the first sentence of each of your messages, and fixed that before scoring. | #37, #39, #43 |
| You asked | 2026-10-01 05:44 | Take the reins and finish DRC-4666. Later: keep the gate shut, and authorize one more run. | #38, #48 |
| Claude did | 2026-10-01 08:17 | Ran two more scored runs. Each failed by one judgement (15 of 16), with the miss moving between runs. | #45, #47, #51 |
| You proposed | 2026-10-02 05:53 | Accept the Claude Code checks, so Claude Code reads Claude Code sessions when it is installed. | #56 |
| Claude did | 2026-10-02 05:53 | Recorded it as your acceptance over failed runs, never as a pass, and changed none of the past results. | #57, #59 |

### Why Claude got confused

- **#32:** The scan only looked for one kind of evidence: a failed test check. Claude took that requirement from the DRC-4758 issue text, not from the qualification rules, which only need the agent to leave the asked scope on its own. The scan never read what you typed, so every correction you made was invisible to it.

## 3 · "This UI is still not acceptable"

**Goal:** Make the Intent and drift panel clear and working, the way the original design was.

**Outcome:** PR #476: a clear consent step, a result in place of the button, roomy textareas, real buttons, a native select for your prompts, popovers that don't move the page, and eased motion.

| Kind | Time (UTC) | What happened | Messages |
|---|---|---|---|
| You asked | 2026-10-01 07:43 | Spin up the main version so you can check the UI. | #42 |
| Claude drifted | 2026-10-01 07:43 | Started a dashboard for you that read your sessions but had no hooks, so it could never see a turn stop. Analyze could never run there. | #43, #51 |
| You pushed back | 2026-10-01 09:48 | Seven problems you and a teammate found: too much text, Analyze shifting and doing nothing, no result ever, amateurish prompt pickers, tiny textareas, buttons that don't look like buttons. "This UI is still not acceptable to give to any users" "I WANT to be able to use this feature, this process has been taking much, much too long" | #50 |
| Claude did | 2026-10-01 09:49 | Walked it in Chrome first. Found the first press was a hidden consent step, and the reading was withheld for lack of a stop. Rebuilt the panel and fixed DRC-4770, which made the board forget a stop a few minutes after each turn. | #51 |
| Claude drifted | 2026-10-01 09:49 | Built "Use your prompt" as a custom menu, and "Why" as an accordion that opens instantly and pushes the page down. | #51 |
| You pushed back | 2026-10-02 02:09 | "When I said to make it a dropdown, I literally meant for you to make it a Select dropdown." Toggles jump the page and snap open. The outcome line's controls don't match the Goal's. Opening a session from Sessions switches to the Projects tab. | #52 |
| Claude did | 2026-10-02 02:09 | Made it a native select, made "Why" a popover that moves nothing, fixed the tab, and found and fixed the redraw that cut the motion short, measured in a browser. | #53 |

### Why Claude got confused

- **#50:** Claude had hit the same wall in the DRC-4719 walk: no hooks means no observed stop, so readings are withheld. It even wrote that into the milestone. But it started your dashboard read-only with a scratch home and no hooks, then went back to scoring runs instead of trying the panel itself. At least one earlier build (DRC-4766) shipped with no browser walk, checked only by tests of the page's text.
- **#52:** Your first message asked for text behind tooltips or accordions, and "a dropdown" of prompts. Claude reused the page's disclosure pattern for both, so "dropdown" became a menu that opens in place. This is inferred. It also turned out the CSS easing was written but never seen: a background redraw cut every animation off halfway, and tests only checked that the CSS rule existed.

## 4 · "This drift tool MUST be usable by users"

**Goal:** Make Save and Analyze tell you what they are doing, and cut the remaining long text.

**Outcome:** Save intent shows a spinner and blocks a second press. Idle Claude Code sessions stay analyzable, and any change is explained in one line. "What is sent" is six short points in a popover. Consent is per provider and tied to where your words go.

| Kind | Time (UTC) | What happened | Messages |
|---|---|---|---|
| Claude drifted | 2026-10-01 09:49 | Left the board running for you to try, but Analyze still needed a turn stop the board itself had seen. Claude's own walks used a session it ran through a hooks file, so the stop was always there. The page also said "Analyze opens once this session finishes a turn", which was false. | #51, #53, #55 |
| Claude drifted | 2026-10-01 09:49 | Tucked the long "What is sent" paragraph (about 200 words) behind a disclosure in the Drift card instead of cutting it, and deferred tidying the column of disclosures there. | #51, #53 |
| You pushed back | 2026-10-02 05:22 | Save intent did nothing for seconds. Analyze turned on after 20 to 30 seconds with no sign it would, then turned itself off two minutes later. "What the heck is going on?!" "This drift tool MUST be usable by users" | #54 |
| Claude did | 2026-10-02 05:22 | Counted the turn end Claude Code records in its own transcript, so an idle session can be analyzed without hooks. Added the spinner, cut a save from 0.9 to 0.24 seconds, and made the card say why Analyze opens or closes. | #55, #59 |
| You pushed back | 2026-10-02 05:55 | "this note is long and arduous to read. The text should be clear and to the point, stop overusing prose." Show it in a popup like "Why". | #58 |
| Claude did | 2026-10-02 05:55 | Rewrote it as six short points in a popover. Asked you two consent questions. | #59 |
| You asked | 2026-10-02 10:26 | You ruled on both, as Claude recommended: keep one Allow per provider and reword the amendment, and tie the Allow to where your words go. | #60 |
| Claude did | 2026-10-02 10:26 | Built both, had two adversarial reviews, fixed seven findings, and left PR #476 green and unmerged for your yes. | #61 |

### Why Claude got confused

- **#54:** Claude tested on a fixture session it had fed through a hooks file, so a stop was always observed. Your session had no hooks pointed at that board, so Analyze opened and closed as the session flipped between working and idle. The same refusal hit 26 of the 30 sessions on that board.
- **#58:** This looks like the same paragraph your first UI message named ("Codex reads this Codex session."): its first sentence says which reader reads the session. Claude moved it behind a disclosure rather than shortening it. Its word budget counted only the words visible when the panel is idle, so hidden text didn't count. The budget part is inferred from it being described as "visible words".
