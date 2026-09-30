# Intent and drift run: <random label>

Copy this file to a new Markdown file in this directory. The participant reviews the completed copy before it is committed to this public repository. Use `not observed` and a reason for a missing field; do not turn a blank into a pass. The public copy uses anonymous labels and links to approved Linear evidence, not raw session material.

| Field | Observation |
|---|---|
| Run label | |
| Classification: exploratory agent-operated, exploratory human, or DRC-4722 cold candidate | |
| Cargento `origin/main` SHA | |
| Cargento start flags (omit paths) and platform | |
| Selected session age and generic work description | |
| Why a newer session was skipped | |
| DRC-4717 and DRC-4683 verdict links and target SHA, if a cold candidate | |
| Observer's sample capture and press/timing preflight, if a cold candidate | |
| Reading route and available provider before the walk | |
| Human walk: date, browser, viewport | |
| Agent-operated pass: date, browser, viewport | |
| Model provider named by the page | |
| Consent chosen by participant; attempt count | |
| Screenshot review: anonymous role, status; issue attachment approved? | |
| DRC-4722 issue comment link, if any | |

## Human walk

| Observation | Result, pass/fail/partial, or reason not observed |
|---|---|
| Presses and elapsed time: Sessions row to result (limit: three presses) | |
| Presses and elapsed time: Sessions row to copied correction (limit: four presses) | |
| Draft noticed and checked? | |
| Each hesitation and its screenshot reference | |
| Level meaning and source, in participant's words or issue link | |
| Cited entry found? Meaning of "Can't tell," in participant's words or issue link | |
| Steer back or Update intent instead; why | |
| Correction pasted? Did later evidence show a return to intent? | |
| Would they leave the live monitor on? Verbatim approved answer or issue link | |
| What would they have done without Cargento? Verbatim approved answer or issue link | |
| Uncoached from row? Participant did not build panel? | |

## DRC-4722 verdict handoff

Fill this table for each cold candidate. The Linear verdict comment, after participant approval, must attach the reviewed screenshots and session notes. If that handoff has not happened, mark every row `partial` or `pending owner upload`, and do not close the issue.

| Step | Run label | Width | Pass/fail/partial | Reviewed screenshot or issue attachment | Cited entry numbers or approved UI strings |
|---|---|---|---|---|---|
| Sessions row to result | | | | | |
| Result to copied correction | | | | | |
| Draft, level source, citation, and "Can't tell" | | | | | |
| Choice, paste, and later evidence | | | | | |
| Each hesitation (add a row) | | | | | |

| Follow-up | Observation or link |
|---|---|
| Press-count overrun or misunderstood level/"Can't tell" defect in this milestone | |
| Misread string and its governing design or overrule | |
| Approved verbatim answers and notes attachment, or pending owner upload | |
| New cold participant needed after a fix, or owner acceptance link | |

## Agent-operated sidecar pass

| Stage | Rendered output, result source, citation numbers, or reason not observed | Screenshot reference and human review status |
|---|---|---|
| Draft and confirmed intent | | |
| Live monitor and estimate | | |
| Analysis consent and phases | | |
| Result level and outcome verdicts | | |
| Cited activity and later direction | | |
| Steer back and copied correction | | |
| New evidence and Analyze again | | |

## Findings and limits

Record any mismatch with a real check as a concrete observation, with the visible words and entry numbers but no private excerpt. Note whether an issue was filed. State which requested stage was not reachable and why. Keep raw screenshots in the gitignored local folder and retain that checkout until review and handoff are complete. Include only participant-reviewed, redacted images in a public PR. A public summary alone does not satisfy DRC-4722's screenshot and participant-answer criteria.
