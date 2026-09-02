# Promise-linked work: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every unit of Cargento roadmap work names the promise it serves and how it touches it, and the machinery that selects and accepts work reads that link.

**Architecture:** Prose-only changes to one canonical doc, two repository skills, two Spacedock workflow READMEs, the board's skill and page, and the Linear project. The promise map owns the vocabulary; everything else links to it. No runtime code, no scoring change.

**Tech Stack:** Markdown, one JavaScript template string in `docs/visibility-2x2/index.html`, the Linear MCP tools, `python3 scripts/validate_plugins.py`, `spacedock status --validate`.

**Spec:** [`docs/plans/promise-linked-work.md`](promise-linked-work.md). Read it first. The tables below are copied from it; if they ever disagree, the spec wins and this plan is wrong.

## Global Constraints

- Every task is a docs-only diff. The check that matters is `python3 scripts/validate_plugins.py`, which resolves every relative Markdown link and heading anchor. It must pass before every commit.
- Voice: these files are written for people. No headers in a message-sized insertion, no bullet where a sentence will do, no em-dashes, no "leverage" or "robust". Read the surrounding paragraph and match it.
- Commits are signed off: `git commit -s -m "docs(<scope>): <description>"`. Multi-line messages go through a temp file and `git commit -F`, never a heredoc.
- Line numbers are anchors as of commit `d12fccf` on `main`. Confirm the quoted text is present before editing; if it has moved, find it by content.
- Nothing is renamed: not a journey label, not a board column, not a milestone.
- Task 1 lands before any other task starts. Tasks 2 to 6 run in parallel worktrees on separate branches and land as one PR. Tasks 7 and 8 start only after that PR merges.
- Parallel builders: read **Parallel Work** in `AGENTS.md`. The contention hazards there are real and read like regressions. `SKILL.md` is a conflict hotspot but none of these tasks touch the shipped `cargento/skills/cargento/SKILL.md`.

The vocabulary every task uses:

| ID | Question | Linear label | Board column |
|---|---|---|---|
| P1 | Which of my agents are running? | `journey:open-sessions` | `open` |
| P2 | What is it doing, and when should I come back? | `journey:mid-flight` | `mid` |
| P3 | Is anything waiting on me? | `journey:stopped-at-gate` | `gate` |
| P4 | Will I hit the wall before the work finishes? | `journey:usage` | `usage` |
| P5 | Did anything die quietly? | `journey:end-of-sessions` | `end` |

| Move | Meaning | May change the map's wording |
|---|---|---|
| `keep` | Without this, the board says something untrue about the promise. Most defects. | No |
| `sharpen` | The promise is kept and this makes it more precise, or covers one more harness. | No |
| `extend` | A new clause on an existing promise. | Yes, that promise |
| `new` | Territory no promise covers. Today that is only the Move up a level milestone. | Yes, a new promise |
| `none` | No user-visible effect. Must say why. | No |

---

### Task 1: The promise map owns the vocabulary

**Files:**
- Modify: `docs/promise-map.md:49,64,80,99,119` (the five question headings) and append after line 172 (end of "Keeping this file honest").

**Interfaces:**
- Produces: the heading anchors `#p1-which-of-my-agents-are-running`, `#p2-what-is-it-doing-and-when-should-i-come-back`, `#p3-is-anything-waiting-on-me`, `#p4-will-i-hit-the-wall-before-the-work-finishes`, `#p5-did-anything-die-quietly`, and the section anchor `#how-work-links-to-a-promise`. Tasks 2 to 6 link to the section anchor.

- [ ] **Step 1: Confirm nothing links to the current heading anchors**

Run: `grep -rn "promise-map.md#" --include=*.md --include=*.html --include=*.json . | grep -v "^./.git"`
Expected: no output. If there is output, those links must be updated in the same commit to the new anchors above.

- [ ] **Step 2: Prefix each of the five question headings with its ID**

Change these five lines exactly:

```
### Which of my agents are running?            →  ### P1. Which of my agents are running?
### What is it doing, and when should I come back?  →  ### P2. What is it doing, and when should I come back?
### Is anything waiting on me?                  →  ### P3. Is anything waiting on me?
### Will I hit the wall before the work finishes?   →  ### P4. Will I hit the wall before the work finishes?
### Did anything die quietly?                   →  ### P5. Did anything die quietly?
```

- [ ] **Step 3: Append the new section at the end of the file**

```markdown

## How work links to a promise

Every unit of roadmap work names the promise it serves and how it touches it. The link is two
labels on the Linear issue and a two-sentence **User value** section at the top of its body: who
notices this and when in their day, then the promise ID and the move. The
[burndown workflow](roadmap-burndown/README.md) requires the section at triage and reads the labels
at selection.

| ID | Question | Linear label | Board column |
|---|---|---|---|
| P1 | Which of my agents are running? | `journey:open-sessions` | `open` |
| P2 | What is it doing, and when should I come back? | `journey:mid-flight` | `mid` |
| P3 | Is anything waiting on me? | `journey:stopped-at-gate` | `gate` |
| P4 | Will I hit the wall before the work finishes? | `journey:usage` | `usage` |
| P5 | Did anything die quietly? | `journey:end-of-sessions` | `end` |

The five labels and the five columns predate the IDs. Nothing was renamed to make this table.

The move says how the work touches its promise.

| Move | Meaning | May change this file |
|---|---|---|
| `keep` | Without this, the board says something untrue about the promise. Most defects land here, because the limits are part of the promise. | No |
| `sharpen` | The promise is kept and this makes it more precise, or covers one more harness. | No |
| `extend` | A new clause on an existing promise. | Yes, that promise |
| `new` | Territory no promise covers. Today that is only the Move up a level milestone. | Yes, a new promise |
| `none` | No user-visible effect. The issue says why, and the Linear project overview counts these so the share stays visible. | No |

A decision issue names the promise its ruling unblocks or forecloses, and takes the move of the
work it gates.

Only `extend` and `new` may change what this file says. A `keep` or `sharpen` merge changes no
wording here, and a burndown that closes one says so in its report.
```

- [ ] **Step 4: Validate**

Run: `python3 scripts/validate_plugins.py`
Expected: the final line begins `Validated 1 skills across 1 plugins`.

Run: `grep -c "^### P[1-5]\. " docs/promise-map.md`
Expected: `5`

- [ ] **Step 5: Commit**

```bash
git add docs/promise-map.md
git commit -s -m "docs(promise-map): give each promise an ID and say how work links to one"
```

---

### Task 2: The burndown skill reads the link

**Files:**
- Modify: `.claude/skills/burndown/SKILL.md:36-43` (the pick order), `:56` (what triage uses), `:78-89` (reconcile steps), `:91` (the report line).

**Interfaces:**
- Consumes: the section anchor `docs/promise-map.md#how-work-links-to-a-promise` from Task 1.
- Produces: the pick rule numbering 1 to 7 that Task 3's Scoring section cites as "seven lexicographic rules".

- [ ] **Step 1: Replace the pick order**

Find the numbered list that begins `1. Drop anything with an open blocker.` and ends `6. Tie-break on state:`. Replace it with:

```markdown
1. Drop anything with an open blocker. A decision issue that is not `Done` is still a blocker, even when its body records the call. Check `blockedBy`, not prose.
2. Release row: `release:r1`, then `r2`, `r3`, `later`.
3. Within that row, prefer an issue whose `move:*` label is not `none`. An issue with no move label ranks as `none` until triage labels it. The labels and what they mean are in [the promise map](../../../docs/promise-map.md#how-work-links-to-a-promise).
4. Then prefer what other open issues are waiting on.
5. Then risk-adjusted impact from the issue's own score table, highest first.
6. Then the smaller estimate.
7. Tie-break on state: `In Progress`, then `Ready for Review`, then `Todo`, then `Backlog`.
```

- [ ] **Step 2: Make triage produce the link**

Find the line `Use what it returns: classification, key files, acceptance criteria, risks.` and append this paragraph directly after it, as its own paragraph:

```markdown
Then write the issue's **User value** brief, two sentences as its first section: who notices this and when in their day, then the promise ID and the move, in the vocabulary of [the promise map](../../../docs/promise-map.md#how-work-links-to-a-promise). Set the `journey:*` and `move:*` labels to match. At least one acceptance criterion must be a property a user can see, with its own `Verified by:` clause; when the move is `none`, the brief says instead why no user sees this change. Inside the roadmap-burndown workflow these are triage outputs and the gate approves them before Linear is written.
```

- [ ] **Step 3: Add the reconcile step and the report field**

Find step `5.` of the reconcile list (it begins `If the closed issue still blocks something`) and its indented explanation ending `this is the why not.` Append after that explanation:

```markdown
6. If the issue's move was `extend` or `new`, draft the change to the promise wording and hand it to
   the `sync-docs` pass, which owns the three copies. A `keep` or `sharpen` merge changes no promise
   wording; say so rather than leaving it implied.
```

Then change the report line from:

```
Then report: issue worked, milestone updated, overview refreshed, what became unblocked, what is next.
```

to:

```
Then report: issue worked, which promise it moved and how, milestone updated, overview refreshed, what became unblocked, what is next.
```

- [ ] **Step 4: Update the count in the As-of refresh**

Find reconcile step `3.` (`Refresh the project overview's "As of" block.`) and append one sentence to it: `The block's open-issues-by-move line is part of that refresh.`

- [ ] **Step 5: Validate**

Run: `python3 scripts/validate_plugins.py`
Expected: passes.

Run: `grep -c "^[1-7]\. " .claude/skills/burndown/SKILL.md`
Expected: at least `13` (seven pick rules plus six reconcile steps).

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/burndown/SKILL.md
git commit -s -m "docs(burndown): pick, triage and reconcile on the promise link"
```

---

### Task 3: The roadmap-burndown workflow carries the link

**Files:**
- Modify: `docs/roadmap-burndown/README.md:99-116` (field reference), `:126-137` (Scoring), `:172-173` (selection's refreshed fields), `:203-227` (triage outputs), `:250-258` (triage gate), `:818-860` (Issue Template).

**Interfaces:**
- Consumes: pick rule count "seven" from Task 2; section anchor from Task 1.
- Produces: frontmatter fields `promise:` and `move:` and the `## User value` section heading that Task 7 and Task 8 write into Linear bodies in the same shape.

- [ ] **Step 1: Add two rows to the field reference**

After the row that begins `| \`release\` | string |`, insert:

```markdown
| `promise` | string | The promise ID from the `journey:*` label, `P1` to `P5`, or empty. Cached at `selection`; the label is authority. |
| `move` | enum | The `move:*` label: `keep`, `sharpen`, `extend`, `new`, `none`, or empty when not yet labelled. Drives rule 3 of the pick order. Empty ranks as `none`. |
```

- [ ] **Step 2: Fix the rule count in Scoring**

Change `The pick order is the \`burndown\` skill's six lexicographic rules` to `The pick order is the \`burndown\` skill's seven lexicographic rules`.

- [ ] **Step 3: Refresh the two new fields at selection**

Change the selection output bullet that begins `` `linear-status`, `release`, `estimate` and `milestone` refreshed `` to:

```markdown
  - `linear-status`, `release`, `estimate`, `milestone`, `promise` and `move` refreshed on the
    surviving entities from the fetch, so the cached fields are not lying to the next stage.
```

- [ ] **Step 4: Add three triage outputs**

In the `triage` stage's `- **Outputs:**` list, insert directly after the bullet that ends `The split is declared here, at the gate, so a plan to build a harness that automates an interactive AC is visible before the harness exists.`:

```markdown
  - The issue's **User value** brief drafted as the first section of the rewrite: two sentences,
    who notices this and when in their day, then the promise ID and the move, in the vocabulary of
    [the promise map](../promise-map.md#how-work-links-to-a-promise). For a decision issue, the
    promise the ruling unblocks or forecloses.
  - The `journey:*` and `move:*` labels to set, named here and written by `implementation` with
    the rewrite. Until they are set the issue ranks as `none` at `selection`.
  - At least one acceptance criterion that is a property a user can see, with its own `Verified
    by:` clause. When the move is `none`, one sentence in the brief on why no user sees this
    change, and the gate is told so up front.
```

- [ ] **Step 5: Put user value first at the gate**

Change the start of the `- **Gate content:**` bullet from `Show the captured original against the drafted rewrite,` to `Show the User value brief and the labels first, then the captured original against the drafted rewrite,`.

- [ ] **Step 6: Extend the Issue Template**

In the YAML frontmatter block of the Issue Template, insert after `release:`:

```yaml
promise:
move:
```

Then insert before `## Problem`:

```markdown
## User value

{Triage: two sentences. Who notices this and when in their day. Then the promise ID and the move,
per the promise map's "How work links to a promise". When the move is `none`, why no user sees it.}

```

- [ ] **Step 7: Validate**

Run: `python3 scripts/validate_plugins.py`
Expected: passes.

Run: `cd docs/roadmap-burndown && spacedock status --validate`
Expected: `VALID`

Run: `grep -c "^## User value" docs/roadmap-burndown/README.md`
Expected: `1`

- [ ] **Step 8: Commit**

```bash
git add docs/roadmap-burndown/README.md
git commit -s -m "docs(roadmap-burndown): triage drafts user value, selection caches the promise"
```

---

### Task 4: The future-ui workflow frames against the five questions

**Files:**
- Modify: `docs/future-ui-exploration/README.md:78` (framing outputs), `:109` (crucible gate), `:160-164` (template, between Design bet and Baseline).

**Interfaces:**
- Consumes: the P-IDs and section anchor from Task 1.

- [ ] **Step 1: Point framing at the map**

Change the framing output bullet from:

```
- Outputs include a concise bet, the user questions it should answer, the command-risk baseline, explicit non-goals, and evidence that would invalidate the model rather than merely suggest polish.
```

to:

```
- Outputs include a concise bet, which of the five questions in [the promise map](../promise-map.md#how-work-links-to-a-promise) it answers by ID and which move the bet would be, the command-risk baseline, explicit non-goals, and evidence that would invalidate the model rather than merely suggest polish.
```

- [ ] **Step 2: Add the promise to the crucible gate**

Change the crucible gate bullet's second sentence from `It shows whether a person can quickly answer overall situation, current assignment, execution state, current activity, next action, and captain responsibility.` to `It shows whether a person can quickly answer overall situation, current assignment, execution state, current activity, next action, and captain responsibility, and the promise the bet serves, in the map's words.`

- [ ] **Step 3: Give the framing output a home in the template**

Insert between the `## Design bet` section and `## Baseline and command risk`:

```markdown
## User questions

Which of the promise map's five questions this bet answers, by ID, and which move it would be.

```

- [ ] **Step 4: Validate**

Run: `python3 scripts/validate_plugins.py`
Expected: passes.

Run: `cd docs/future-ui-exploration && spacedock status --validate`
Expected: `VALID`

- [ ] **Step 5: Commit**

```bash
git add docs/future-ui-exploration/README.md
git commit -s -m "docs(future-ui): frame each bet against a promise"
```

---

### Task 5: The board names the link

**Files:**
- Modify: `.claude/skills/visibility-2x2/SKILL.md:47-49`, `docs/visibility-2x2/README.md` (after the paragraph ending `the other 30 were proposed afterwards.`), `docs/visibility-2x2/index.html:517`.

**Interfaces:**
- Consumes: the P-ID order P1 to P5 matches the `columns` order in `docs/visibility-2x2/items.json` (`open`, `mid`, `gate`, `usage`, `end`). Rendering is by position; no data field is added.

- [ ] **Step 1: The skill**

Change `**journey** (a story-map of narrative stage against release)` to `**journey** (a story-map of narrative stage against release, where each column is an item's link to one of the five promises and the Promise row is the map's wording verbatim)`.

- [ ] **Step 2: The board README**

Insert after the paragraph that ends `the other 30 were proposed afterwards.`:

```markdown
Each item's `column` is its link to one of the five promises in
[`docs/promise-map.md`](../promise-map.md#how-work-links-to-a-promise), and the journey view's
Promise row carries that file's wording verbatim. The board scores what to build; the map says what
a user is promised. The link is what keeps them from saying different things.
```

- [ ] **Step 3: Render the ID beside each promise**

Change the promise-row line in `drawJour()` from:

```javascript
  s+=DATA.columns.map(c=>`<div class="jprom">${c.promise?esc(c.promise):''}</div>`).join('');
```

to:

```javascript
  s+=DATA.columns.map((c,i)=>`<div class="jprom"><b>P${i+1}</b> ${c.promise?esc(c.promise):''}</div>`).join('');
```

- [ ] **Step 4: Validate**

Run: `python3 scripts/validate_plugins.py`
Expected: passes.

Run: `python3 scripts/lint_embedded.py --allow-missing-node`
Expected: passes. The frontend linter covers the shipped `web/` sources; run it anyway so a stray edit elsewhere is caught.

Open the board with the `visibility-2x2` skill, switch to the journey view, and confirm each Promise cell begins with a bold `P1` to `P5` in column order.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/visibility-2x2/SKILL.md docs/visibility-2x2/README.md docs/visibility-2x2/index.html
git commit -s -m "docs(visibility-2x2): name the column as the promise link and show the ID"
```

---

### Task 6: Sync-docs and release read the link

**Files:**
- Modify: `.claude/skills/sync-docs/SKILL.md:49` (the promise-map row), `:328` (the Labels row of the Linear table) and the text directly after that table.
- Modify: `.claude/skills/cargento-release/SKILL.md:270-271`.

- [ ] **Step 1: Extend the promise-map row's contract**

In the `docs/promise-map.md` row of the ownership table, change the third column from ending `Change one, change all three.` to ending `Change one, change all three. The "How work links to a promise" section is the only place the promise IDs and the move taxonomy are defined; every other file links to it.`

- [ ] **Step 2: Add the label check to the Linear pass**

Change the Labels row from `| **Labels** | Release row, journey stage, origin. They *are* the record. | Restating a label's content in prose. |` to `| **Labels** | Release row, journey stage, move, origin. They *are* the record. | Restating a label's content in prose. |`.

Then, directly after the paragraph that ends `Closing work should make it shorter.`, add:

```markdown
   One read-only check on the tracker: every open issue in the project carries a `journey:*` label
   and a `move:*` label. Report the ones that do not; do not label them here, because the label is a
   triage product and setting it without the brief is the drift this check exists to catch.
```

- [ ] **Step 3: Group release claims by promise**

Change item 2 of the release-note order from:

```
2. What this release changes about keeping that promise, as two to four bolded claims, each one
   sentence of what a user can now do and one of what backs it.
```

to:

```
2. What this release changes about keeping that promise, as two to four bolded claims grouped by
   promise ID and move, each one sentence of what a user can now do and one of what backs it. The
   IDs and moves are the ones on the merged issues; a claim with no issue behind it is a claim the
   release did not ship.
```

- [ ] **Step 4: Validate**

Run: `python3 scripts/validate_plugins.py`
Expected: passes.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sync-docs/SKILL.md .claude/skills/cargento-release/SKILL.md
git commit -s -m "docs(skills): sync-docs checks the labels, release groups by promise"
```

---

### Task 7: Linear labels, project paragraph, As-of line

Runs only after the PR carrying Tasks 2 to 6 has merged. Uses the Linear MCP tools; nothing in the repository changes.

**Files:**
- Linear: team `DRC`, project `cargento-visibility-2x2-roadmap-c43e013de860`.

**Interfaces:**
- Produces: the five `move:*` labels that Task 8 applies.

- [ ] **Step 1: Create the five labels on the DRC team**

One `create_issue_label` call each. Names and descriptions exactly:

| name | description |
|---|---|
| `move:keep` | Promise move: without this, the board says something untrue about the promise. Most defects. |
| `move:sharpen` | Promise move: the promise is kept and this makes it more precise, or covers one more harness. |
| `move:extend` | Promise move: a new clause on an existing promise. May change the promise map's wording. |
| `move:new` | Promise move: territory no promise covers. May add a promise to the map. |
| `move:none` | Promise move: no user-visible effect. The issue says why. Counted in the project overview. |

Use the DRC team's UUID for `teamId`; find it with `list_teams`. Colour is not specified; pick one per label and keep the five distinct.

- [ ] **Step 2: Confirm they exist**

Run `list_issue_labels` with `name: "move:"` on team `DRC`.
Expected: exactly five labels.

- [ ] **Step 3: Add the project paragraph**

`save_project` with a `patch` on the description: `insert_after` the anchor `**Every milestone below leads with the user value it exists to deliver.** The engineering record follows underneath it, unchanged.` with:

```markdown

**Every issue carries two labels.** A `journey:*` label names the promise it serves, `P1` to `P5`, and a `move:*` label says how: `keep`, `sharpen`, `extend`, `new` or `none`. Each issue opens with a two-sentence User value section that says who notices and when. The vocabulary is defined once, in `docs/promise-map.md` under "How work links to a promise", and nowhere else.
```

- [ ] **Step 4: Add the As-of line**

In the same description, `insert_after` the anchor line that begins `Per release row: **Release 1 is complete` (use the whole sentence up to `\`later\` has fifteen.` as the anchor) with a new paragraph:

```markdown

By move, open issues: keep 0, sharpen 0, extend 0, new 0, none 0, unlabelled N.
```

where `N` is the count of open project issues at the time of the edit. Task 8 rewrites this line with real counts as its last step; leaving zeros here for a day is honest, because that is what the labels say.

- [ ] **Step 5: Record what was done**

No Linear comment is needed. Report in chat: the five label IDs and the two description anchors edited.

---

### Task 8: Backfill the open issues

Runs after Task 7. Batches by milestone, one milestone per subagent, the captain reviews the first batch before the rest run.

**Files:**
- Linear: every open issue in the project. Open means state `Backlog`, `Todo`, `In Progress`, `Ready for Review` or `Blocked`. `Done` and `Canceled` are left untouched.

**Interfaces:**
- Consumes: the `move:*` labels from Task 7, the `## User value` shape from Task 3.

- [ ] **Step 1: List the batch**

`list_issues` with `project: cargento-visibility-2x2-roadmap-c43e013de860`, `limit: 250`, fields `title, status, projectMilestone, labels, description`. Filter in memory to open states and to the milestone assigned to this batch. Issues with no milestone form their own batch.

- [ ] **Step 2: For each issue, decide promise and move from the body, not the title**

Rules, in order:
1. If a `journey:*` label is present, the promise is that label. Otherwise read the body and the owning milestone's stage sentence ("Stage N of a user's day") and assign the matching label. A decision issue takes the promise of the work it gates; find that work through `blocks`.
2. Move: a defect whose fix makes the board stop saying something untrue is `keep`. Coverage of one more harness, or a more precise version of a kept promise, is `sharpen`. A new clause a user could read on the map is `extend`. Anything under the Move up a level milestone is `new`. Test infrastructure, CI, tooling and audits with no user-visible effect are `none`.
3. When two moves both fit, take the one nearer the top of that list.

- [ ] **Step 3: Write the brief and the labels**

`save_issue` with `id` set, `addLabels` set to the two labels, and a `patch` of one `prepend` operation:

```markdown
## User value

<Who notices this and when in their day, one sentence.> <Promise ID and move, one sentence, for example "P3, keep: the gate queue would otherwise show a granted permission as still waiting.">

```

For `move:none`, the second sentence says why no user sees the change instead of naming a promise clause. Do not edit anything else in the body.

- [ ] **Step 4: Verify the batch**

`list_issues` again for the milestone. For every open issue, confirm both labels are present and the description begins with `## User value`.
Expected: no exceptions in this batch.

- [ ] **Step 5: Report the batch**

In chat, one line per issue: identifier, promise, move. The captain reviews the first batch and either corrects the rules above or releases the remaining batches.

- [ ] **Step 6: After the last batch, rewrite the As-of line**

Count open issues by move with one `list_issues` pass over the project and replace the `By move, open issues:` line in the project description with the real counts and `unlabelled 0`. If unlabelled is not zero, list the offenders in chat; that is the state the sync-docs check will report until they are fixed.

---

## Self-review against the spec

- Spec section 1 (promise map): Task 1.
- Spec section 2 (Linear): Tasks 7 and 8.
- Spec section 3 (burndown skill, roadmap-burndown README): Tasks 2 and 3.
- Spec section 4 (future-ui): Task 4.
- Spec section 5 (board): Task 5.
- Spec section 6 (sync-docs, release): Task 6.
- Verification list in the spec: each task's validate step. The Linear query returning none without both labels is Task 8 step 6.
- Out of scope in the spec: no task touches scoring, item fields, milestone structure, Done or Canceled issues, or any label or column name.
