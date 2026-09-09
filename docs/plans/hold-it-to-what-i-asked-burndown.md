# Burndown: Hold it to what I asked

Durable state for an autonomous, quota-interrupted burndown. Written 2026-09-09. Delete when the
work ships.

**If you are a fresh session picking this up, read this file first and trust it over your memory.**

## Where the work is

- Worktree: `.claude/worktrees/hold-it-to-what-i-asked` in `spacedock-dev/cargento`
- Branch: `feat/hold-it-to-what-i-asked`
- Base and PR target: `proto/operator-cockpit`, NOT `main`. That branch is PR #312, open and draft.
- Base commit at start: `01a6687`

The base matters. Three of the five issues need surfaces that exist only on the cockpit branch: the
`Held to` tab's shell, the recovery briefing, and the `--observer-model` CLI switch, which is absent
from `main`.

## The five issues, in dependency order

DRC-4508 blocks DRC-4509 blocks DRC-4511 blocks DRC-4514. DRC-4512 has no blocker.

| Issue | Title | Release | Priority |
| -- | -- | -- | -- |
| DRC-4508 | Record what this session should achieve and produce | r3 | High |
| DRC-4509 | Read your words beside the instruction and the work | r3 | High |
| DRC-4512 | Check the finished work against what you asked for | r3 | High |
| DRC-4511 | See why Cargento thinks a session may be going off track | r3 | Medium |
| DRC-4514 | Review the departures Cargento raised and what you did next | later | Low |

Each issue body carries a `## Design reference` section with a fenced `### Prompt to use`. Read the
issue in Linear for the authoritative text. The design lives in the Claude Design project
`241b0179-ac55-471c-a6cc-dc13b0bf7235`, read with the `DesignSync` tool, which is deferred behind
`ToolSearch "select:DesignSync"`. Authorization is `/design-login`, a slash command a dispatched
agent cannot run: if a read is refused, that is a hand-back, not a workaround.

## Buildability, assessed before starting

This is the part a fresh session must not re-litigate optimistically.

- **DRC-4508 — buildable, with one criterion that cannot be met tonight.** Its acceptance criteria
  require "real resume captures for each harness and version claimed". That needs live Codex and
  Claude sessions resumed and observed. Desk research does not produce it, and this repository has
  a measured history of desk research getting the field wrong. Build the rest; leave that criterion
  explicitly unmet and say so in the PR.
- **DRC-4509 — buildable.** The deterministic observer path ships on `main`; the `STATED GOAL`
  block already exists in `next-project.js`. This adds rows to a list rather than restructuring it.
- **DRC-4512 — partly buildable.** DEC-15b settled the store (session history, no new store, named
  `PROMPT_TEXT_ALLOWLIST` admissions). Final eligibility per harness is still open.
- **DRC-4511 — NOT buildable without a decision.** Its acceptance requires judgements to pass
  "DEC-15's independently reviewed rubric". No rubric exists; writing one is a product-judgement
  call. The `burndown` skill's rule is to stop and file a decision issue rather than guess. Do that.
  Do not invent a rubric to make the milestone look finished.
- **DRC-4514 — gated.** Blocked by DRC-4511, `release:later`, and the milestone itself says
  rescheduling is a call worth making after 4511 ships. Out of scope for this run.

Target for this run: DRC-4508, DRC-4509, DRC-4512, plus a filed decision issue for the rubric
DRC-4511 needs. Anything beyond that is a bonus, not the bar.

## Constraints that will bite

- **Exactly one PR may touch `cargento_runtime/web/`.** All of these do, so all of them ride this
  one PR. That is `AGENTS.md`, Parallel Work, and it is why this is one branch.
- **Frontend byte pins.** On this branch the oracles are `tests/test_next_page.py`,
  `tests/test_next_flag.py`, `tests/test_focus.py` and `tests/test_next_cockpit.py`. Recompute from
  the assets; never resolve them textually.
- **The web bundle is concatenated, not modules.** `page.py`'s `APP_PARTS` joins the files into one
  shared script scope with no `type="module"`. An `import` or `export` statement is a SyntaxError
  that kills the whole bundle. Escape payload-derived strings through `esc()`.
- **Never edit a version field.** `version-guard` fails any PR that does.
- **DCO.** Every commit needs `-s`.
- Commits end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`; PR bodies
  end with the Claude Code attribution line.

## Resume protocol

1. `cd` to the worktree above. Check `git log --oneline origin/proto/operator-cockpit..HEAD` for
   what has already landed.
2. Read `## Progress` below. It is appended to after every completed unit of work, and it is the
   only record that survives a context loss.
3. The Linear MCP may be absent in a headless or cron run. If it is, build from this file and defer
   every Linear write to a later attended pass. Do not skip the writes silently: record them under
   `## Owed to Linear` below so the attended session can do them.
4. Run the canonical pre-PR suite from `AGENTS.md` before pushing anything.

## Progress

- 2026-09-09: worktree and branch created from `01a6687`; this plan committed as the first durable
  state. Nothing built yet.

## Owed to Linear

Nothing yet. Every issue this run touches needs, at minimum: a move to `In Progress` when started,
and the step 4 reconcile receipt comment after the PR merges.
