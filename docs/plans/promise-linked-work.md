# Promise-linked work

A plan for unshipped work. Delete this file once the six work packages below have landed, and
fold anything durable into the owning docs named in each package.

## Why

CL asked, on the 0.20 release thread, for the journey map to say what Cargento promises a fresh
user and how that user gets there. [`docs/promise-map.md`](../promise-map.md) now does that, the
README leads with it, the release skill writes notes from it, the Visibility 2x2 board carries it
as a Promise row, and every Linear milestone opens with the user value it exists to deliver.

None of that reaches the machinery that chooses or accepts work. The burndown pick order is six
rules and no rule names a promise. The triage template has no user-value section. Acceptance
criteria are end-state properties with a verification clause, which is right, but nothing requires
one of them to be a property a user can see. The board scores on impact minus detector risk and
never reads the journey column. The future-ui framing stage keeps its own six-fact list beside
the map's five questions and does not cite them. The one enforced user-value moment in the whole
chain is the pr-merge mod requiring the PR body to lead with end-user value, which fires after the
code is written.

In Linear, the original board items carry `journey:*` labels that already map one to one onto the
five stages. About half the issues in the project carry none: every decision issue, every
discovered-by-agent defect, the whole next-UI tree. Those are the issues that got built last month.

The shift is therefore not a rewrite of issue prose. It is a required link from every unit of work
to a promise, and a link that does something at selection and at acceptance.

## Three rules

**Link, do not rewrite.** An issue states which promise it serves and how. It does not have to
sound like marketing.

**Keeping a promise true is user value.** The map says the limits are part of the promise. A
defect that would make the board say something untrue is therefore work on the promise, and it is
classified as such rather than as overhead.

**Work that serves no promise is allowed, declared, and counted.** Test infrastructure, CI,
tooling. It carries the `none` move, it says why no user sees it, and its share of open work is one
line in the project overview.

## Vocabulary

Owned by [`docs/promise-map.md`](../promise-map.md), in a new section titled "How work links to a
promise". Every other file links to that section rather than restating it.

| ID | Question | Linear label | Board column |
|---|---|---|---|
| P1 | Which of my agents are running? | `journey:open-sessions` | `open` |
| P2 | What is it doing, and when should I come back? | `journey:mid-flight` | `mid` |
| P3 | Is anything waiting on me? | `journey:stopped-at-gate` | `gate` |
| P4 | Will I hit the wall before the work finishes? | `journey:usage` | `usage` |
| P5 | Did anything die quietly? | `journey:end-of-sessions` | `end` |

The five journey labels and the five board columns already exist. The IDs are new and are the only
new spelling. Nothing is renamed.

**The move** says how a piece of work touches its promise. One label from a new `move:*` group.

| Move | Meaning | May change the map's wording |
|---|---|---|
| `keep` | Without this, the board says something untrue about the promise. Most defects. | No |
| `sharpen` | The promise is kept and this makes it more precise, or covers one more harness. | No |
| `extend` | A new clause on an existing promise. | Yes, that promise |
| `new` | Territory no promise covers. Today that is only the Move up a level milestone. | Yes, a new promise |
| `none` | No user-visible effect. Must say why. | No |

A decision issue names the promise its ruling unblocks or forecloses, and takes the move of the
work it gates.

## The changes, per surface

Line numbers are as of commit `d12fccf` on `main` and are anchors for the implementer, not part
of the contract.

### 1. The promise map

Add the section "How work links to a promise" after "Keeping this file honest". It holds the two
tables above and the decision-issue rule, in about twenty lines. Add the P-ID to each of the five
question headings so a link target exists per promise. The section closes with the sentence that
only `extend` and `new` may change what this file says, and that a `keep` or `sharpen` merge
never does.

### 2. Linear

- Create five labels, `move:keep`, `move:sharpen`, `move:extend`, `move:new`, `move:none`, on the
  DRC team, each with a one-line description copied from the table above.
- Every open issue in the project gets a `## User value` section as its first section: two
  sentences, who notices this and when in their day, then the promise ID and the move. Then both
  labels. Done and Canceled issues are left as record.
- The project description gains one paragraph after "Every milestone below leads with the user
  value it exists to deliver", stating that every issue carries a journey label and a move label
  and linking the map's new section. The "As of" block gains one line: open issues by move.

### 3. The burndown skill and the roadmap-burndown workflow

`.claude/skills/burndown/SKILL.md`:

- Pick order, after rule 2 (release row): a new rule 3, "Within the row, prefer an issue whose
  move is not `none`. An issue with no move label ranks as `none` until triage labels it." Rules
  3 to 6 become 4 to 7.
- Reconcile, after step 3 (the "As of" refresh): the by-move line is part of that refresh.
  New step 6: "If the issue's move was `extend` or `new`, draft the change to the promise wording
  and hand it to the sync-docs pass. A `keep` or `sharpen` merge changes no wording; say so."
- The report line adds which promise moved and how.

`docs/roadmap-burndown/README.md`:

- Field reference (lines 99 to 116) and Issue Template (818 to 843): add cached `promise:` and
  `move:` fields beside `release:`, filled at `selection` from the labels.
- Issue Template: add `## User value` above `## Problem`, with the two-sentence brief.
- `triage` outputs (194 to 258): three additions. The drafted `## User value` section as part of
  the Linear rewrite. The two labels to set, written to Linear by `implementation` with the
  rewrite. At least one acceptance criterion that is a user-visible property with its own
  `Verified by:` clause, or, when the move is `none`, one sentence on why no user sees it.
- `triage` gate content: user value shown first.
- `review` (308 to 363): no new rule. The user-visible criterion is reproduced like every other.

### 4. The future-ui workflow

`docs/future-ui-exploration/README.md`:

- `framing` outputs (line 78): "the user questions it should answer" becomes "which of the five
  questions in the promise map it answers, by ID, and which move the bet would be".
- Template: add `## User questions` between `## Design bet` and `## Baseline and command risk`,
  so the framing output has a place to land.
- `crucible` gate (line 109): add "and the promise the bet serves, in the map's words".
- The six-fact list at line 42 stays. It is the board's own vocabulary for command truth.

### 5. The board

`.claude/skills/visibility-2x2/SKILL.md` and `docs/visibility-2x2/README.md`: one sentence each,
that the journey column is an item's link to a promise and the Promise row is the verbatim copy of
the map's wording. `docs/visibility-2x2/index.html`: show the P-ID beside each promise in the
journey view's Promise row. No scoring change and no new item field.

### 6. Sync-docs and release

`.claude/skills/sync-docs/SKILL.md`: the promise-map row extends its change-all-three rule to the
new section. The Linear pass gains one read-only check: every open issue in the project carries a
journey label and a move label, reported and not written.

`.claude/skills/cargento-release/SKILL.md`: the release note groups its claims by promise ID and
move. It already leads with the promise.

## Work packages

| WP | Scope | Model | Depends on | Done when |
|---|---|---|---|---|
| 1 | Section 1, the promise map | Opus | nothing | The section exists, each question heading carries its ID, the validator passes |
| 2 | Section 3, burndown skill and roadmap-burndown README | Opus | WP 1 | Both files updated at the anchors above, `spacedock status --validate` prints VALID |
| 3 | Section 4, future-ui README | Sonnet | WP 1 | File updated, `spacedock status --validate` prints VALID |
| 4 | Section 5, board skill, README and journey view | Sonnet | WP 1 | Sentences in place, P-IDs render in the Promise row |
| 5 | Section 6, sync-docs and release skills | Sonnet | WP 1 | Both skills updated |
| 6 | Section 2, Linear | Sonnet for the user-value sentences, Haiku for label passes | the PR carrying WP 1 to 5 merged | Zero open project issues without both labels, project paragraph and As-of line in place |

WP 1 lands first, alone, because it fixes the wording everyone else copies. WP 2 to 5 run in
parallel worktrees and land as one docs PR. They share no file, and the repository's own guidance
is one PR per conflict surface rather than per issue. WP 6 runs after that PR merges, in batches
by milestone, and the captain reviews the first batch before the rest are written.

## Verification

- `python3 scripts/validate_plugins.py` on every PR. The diffs are prose, so it is the check that
  matters, and it resolves every link and heading anchor including the new P-ID targets.
- A sync-docs pass before each PR opens.
- `spacedock status --validate` in `docs/roadmap-burndown` and `docs/future-ui-exploration`.
- For WP 6, a Linear query over open project issues returning none without both labels, and the
  As-of line matching that query's counts.

## Out of scope

- Any change to the board's scoring, or a per-item promise field. The blind panel scored the build
  order; re-ranking it on promise moves is a separate decision with its own audit.
- Restructuring milestones. Six of eight already map onto the five stages plus "beyond" and the
  other two are complete.
- Rewriting Done or Canceled issues.
- Renaming the `journey:*` labels or the board columns.
