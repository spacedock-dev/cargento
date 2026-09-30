# Intent and drift teammate evidence

[Share this prompt](PROMPT.md) with a developer who uses Claude Code for real work and did not build the Intent and drift panel. Their agent can set up a separate Cargento instance, observe the walk, and record what the panel said about a recent session. [The run template](RUN_TEMPLATE.md) gives each return the same shape.

There are two different observations. In the human walk for [DRC-4722](https://linear.app/recce/issue/DRC-4722), the developer starts at a Sessions row and drives the panel without coaching. Their agent records presses, timing, hesitation, screenshots, and answers. After that walk, the agent may operate the panel itself on a separate scratch instance to gather more technical evidence. Label that second run `agent-operated`; it cannot stand in for either human participant.

This repository is public. Commit only a participant-approved, redacted copy of the run template under this directory. Keep raw transcripts, saved goals, checklist text, clipboard contents, local paths, session IDs, and unredacted screenshots out of Git. The agent saves original captures under the gitignored `docs/screenshots/DRC-4722/` directory. A person reads each screenshot before a verdict. The issue's required screenshots and verbatim participant answers can be attached to Linear after the participant reviews what will be shared with that workspace. A public report can link to that issue comment without repeating the material.

Use a branch and a PR into `main` for the public report. The repository's main ruleset and [PR workflow](../../../AGENTS.md#pr-workflow) apply. A report without an observed result, or without the participant's review, says `partial` rather than `pass`.

VoiceOver in [DRC-4718](https://linear.app/recce/issue/DRC-4718) is macOS's built-in screen reader. It speaks control names, states, status changes, and analysis progress while a person navigates with the keyboard. That is a separate accessibility walk; an agent's accessibility-tree inspection does not replace the person-run VoiceOver transcript the issue requests.
