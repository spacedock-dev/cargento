---
name: pr-merge
description: Push branches and create/track GitHub PRs for workflow entities
version: 0.12.2
---

# PR Merge

Manages the PR lifecycle for workflow entities processed in worktree stages. Pushes branches, creates PRs, detects merged PRs, and advances entities accordingly.

## Hook: startup

Scan all entity files (in the workflow directory only, not `_archive/`) for entities with a non-empty `pr` field and a non-terminal status. For each, extract the PR number (strip any `#`, `owner/repo#` prefix) and check: `gh pr view {number} --json state --jq '.state'`.

If `MERGED`, advance the entity to its terminal stage. Because a `mod-block` may be set while the PR is pending, the clear and the terminalization are two separate `--set` calls (the mechanism refuses combining `mod-block=` with terminal fields):
1. `spacedock status --workflow-dir {dir} --set {slug} mod-block=` when a `mod-block` is set (skip when empty);
2. `spacedock status --workflow-dir {dir} --set {slug} status={terminal} completed verdict=PASSED worktree=`, then `spacedock status --workflow-dir {dir} --archive {slug}`.

Clean up any worktree/branch. Report each auto-advanced entity to the captain.

If `CLOSED` (closed without merge), report to the captain: "{entity title} has PR {pr number} which was closed without merging. How to proceed? Options: reopen the PR, create a new PR from the same branch, or clear `pr` and fall back to local merge." Wait for the captain's direction before taking action.

If `OPEN`, no action needed — the PR is still in review.

If `gh` is not available, warn the captain and skip PR state checks.

## Hook: idle

Check PR-pending entities using the same logic as the startup hook: scan entity files for non-empty `pr` and non-terminal status, run `gh pr view` for each, and advance merged PRs (two-step `mod-block=` clear then terminalize). This is the workflow's PR-pending scan: the generic event loop fires this idle hook and owns no PR scan of its own, so a workflow with no `pr-merge` mod never reaches for `gh` in its loop. Report any advanced entities to the captain.

## Hook: merge

Resolve the PR base once: `BASE=$(spacedock dispatch trunk --workflow-dir {dir})` — the workflow's configured integration trunk (default `main` when no `trunk:` key is set). `dispatch trunk` emits exactly a **bare branch name** (e.g. `main`), so `$( )` yields `$BASE` clean (command substitution strips the single trailing newline). Always quote `"$BASE"` at use sites — the push, the rebase, the draft, and the `gh pr create --base` below.

**PR APPROVAL GUARDRAIL — Do NOT push or create a PR without explicit captain approval.** Before presenting the draft, construct the full PR body so the captain reviews the actual prose that will land on GitHub.

Compute the product short SHA first with `git rev-parse --short HEAD` in the worktree directory. If it exits non-zero, substitute the literal string `main` and report the fallback to the captain.

Resolve the audit receipt from the entity file's own Git repository, never by assumption:

1. From the product worktree, resolve `PRODUCT_REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')`.
2. Resolve the entity's state root with `git -C {entity directory} rev-parse --show-toplevel`; require `git -C {state root} ls-files --error-unmatch {entity-relative-path}`.
3. Read `git -C {state root} remote get-url origin`. Accept only `https://github.com/{owner}/{repo}[.git]` and `git@github.com:{owner}/{repo}[.git]`, strip the optional `.git`, and call the result `STATE_REPO`.
4. Require `STATE_REPO` to differ from `PRODUCT_REPO`. Equality is the product-repository prohibition and always takes the plaintext fallback.
5. Resolve the full state commit with `STATE_SHA=$(git -C {state root} rev-parse HEAD)`.
6. Prove that exact commit is remote with `gh api "repos/$STATE_REPO/commits/$STATE_SHA" --silent`.
7. Prove that exact entity path exists at that commit with `gh api --method GET "repos/$STATE_REPO/contents/{entity-relative-path}" -f "ref=$STATE_SHA" --silent`.

Only after every command above succeeds may the receipt link. Use the full
`STATE_SHA`, the shortest entity id from
`spacedock status --short-id {entity ref}`, and the entity-relative path:

Concatenate `[{short-id}]` and
`(/{state-owner}/{state-repo}/blob/{state-full-sha}/{entity-relative-path})` with no
separator.

Any failure takes the plaintext fallback: missing `gh`, auth, or network;
unparseable or absent origin; same product and state repository; untracked
entity; missing remote commit; or missing path at that exact commit. A
split-root state checkout with no `origin` therefore always falls back:

`Audit: local-only workflow receipt; product head {product-short-sha}.`

Do not invent a remote, point the link at the product repository, copy state into the product branch, or publish state automatically.

Build the full PR body using the template below: motivation lead, `## What changed`, `## Evidence`, `---` separator, the resolved audit receipt, and a `Closes {issue}` line if frontmatter `issue` is set. This is the body that will be passed to `gh pr create` verbatim; do not reconstruct it after approval.

Then present the draft to the captain:

- **Title:** {entity title}
- **Branch:** {branch} -> $BASE
- **Changes:** {N} file(s) changed across {N} commit(s)
- **Files:** {list of changed files}
- **Body:**

  ```
  {constructed body}
  ```

Wait for the captain's explicit approval before pushing. Do NOT infer approval from silence, acknowledgment of the summary, or the gate approval that preceded this step — only an explicit "push it", "go ahead", "yes", or equivalent counts.

**On approval:** First, push the trunk so the integration branch is current: `git push origin "$BASE"`. This never publishes split-root state. Then rebase the worktree branch onto the trunk: `git rebase "$BASE"` (from the worktree directory). Then push the worktree branch: `git push origin {branch}`. If any step fails (no remote, auth error, rebase conflict), report to the captain and fall back to local merge.

Then create the PR by running `gh pr create --base "$BASE" --head {branch} --title "{entity title}" --body "{constructed body}"` against the body already constructed above — do not rebuild it. If `gh` is not available, warn the captain and fall back to local merge.

### PR body template

Lead with motivation + end-user value; audit metadata goes at the bottom. The goal is that a reviewer or future debugger sees the "why" first and the audit receipt last.

**Template structure (top to bottom):**

| Section | Required | Content |
|---|---|---|
| Motivation lead | **yes** | 1 sentence, ≤ 25 words, blending motivation and end-user value. No parentheticals. |
| `## What changed` | **yes** | Action-verb bullets, 3–5 total, each ≤ 15 words. One change per bullet. No rationale inside the bullet — if a change needs justification, it belongs in the task body, not the PR. |
| `## Evidence` | **yes when validation ran** | Test suites with `N/N passed` format, 1–2 bullets. Do not include per-test-class breakdowns or enumerated suite lists — one pass ratio per suite, plus at most one line confirming live-probe verification. |
| `## Review guidance` | optional | 1 line pointing reviewer at the critical file or risky change — include only when a stage report explicitly flagged it |
| `---` separator + audit receipt | **yes** | Link only for a distinct state repository whose exact full commit and entity path are proven through GitHub; every failed check uses `Audit: local-only workflow receipt; product head {product-short-sha}.` |
| `Closes {issue}` | **yes when issue set** | Under the audit receipt, using the value exactly as it appears in frontmatter, e.g., `#48` or `owner/repo#48` |
| `Related: {siblings}` | optional | Under Closes, only when stage reports flagged follow-ups |

**Extraction rules (apply deterministically from the entity file):**

| PR body section | Source in entity file | Transformation |
|---|---|---|
| Motivation lead | Entity body paragraph(s) between closing `---` and the first `##` heading | Condense first paragraph to 1-2 sentences. Lead with impact or action verb — not "This PR" or "This task". Blend motivation + value. |
| What changed | Implementation stage report's `[x]` DONE items | One action-verb bullet per meaningful unit. Collapse sibling bullets that describe the same thing. Drop `[x]` markers. Do NOT include "what we deliberately did NOT change" bullets — scope boundaries belong in the task body, not the PR, unless a validation stage report flagged them as risk. |
| Evidence | Validation stage report items that assert AC verification (typically rerun-test items) | One bullet per suite with `N/N passed` format. Include any quantitative result the stage report explicitly called out (wallclock delta, size %, perf). Fallback to implementation report's self-test items if no validation stage exists. |
| Review guidance | Explicit "focus on X" / "risk here" notes in either stage report | 1 line. **Omit if no such note exists.** |
| Audit receipt | Product `owner/repo`; entity file's Git root, tracked relative path, parsed state `owner/repo`, full state HEAD SHA, remote commit proof, and exact path-at-ref proof | Link only when product and state repositories differ and both GitHub API checks succeed. Concatenate `[{short-id}]` and `(/{state-owner}/{state-repo}/blob/{state-full-sha}/{entity-relative-path})` with no separator; every failure emits `Audit: local-only workflow receipt; product head {product-short-sha}.` |
| Closes | Entity frontmatter `issue` field (exactly as written) | Prefix `Closes ` |
| Related | Explicit "related task" / "follow-up" mentions in stage reports | 1 line. **Omit if none.** |

Target total length: **60-120 words**.

**Key design decisions:**

1. **Lead with motivation + end-user value.** First content is a 1-2 sentence user-facing impact statement. The audit receipt moves to the bottom as audit metadata.
2. **Prescribed sections + extraction rules** — not a strict verbatim template, not free-form. The mod specifies headings and source subsections; the FO paraphrases rather than pasting.
3. **Evidence section is conditional on validation stage.** Non-validated workflows fall back to implementation self-test evidence.
4. **Review guidance and Related are opt-in.** They appear only when stage reports explicitly flagged them, to prevent bloat.

Set the entity's `pr` field to the PR number (e.g., `#57`). Report the PR to the captain.

**On decline:** Do NOT automatically fall back to local merge. Ask the captain how to proceed — options include local merge or leaving the branch unmerged. Only act on the captain's explicit choice.

Do NOT archive yet. The entity stays at its current stage with `pr` set until the PR is merged. The FO handles advancement to the terminal stage and archival when it detects the merge (via this idle hook, the startup hook, or the reconcile sweep's un-advanced-pr class).
