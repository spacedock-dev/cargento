---
name: cargento-release
description: Use when cutting a Cargento release, choosing the major, minor or patch bump from what changed since the last tag, pushing the tag, confirming the Release workflow landed, and optionally announcing it in Slack.
---

# cargento-release

One release: decide the number from the evidence, cut it, confirm it landed, and say so in a way
that claims nothing the range does not contain.

Invoke `cargento-release` with no argument to analyse and propose a version. Pass a version
(`0.17.0`) to propose that one instead, and the analysis still runs so a disagreement is visible
rather than silent. Pass `--dry-run` to analyse, print the proposal and stop without tagging.

Versions here are owned by the tag-driven Release workflow. This skill does not edit a version
field, ever. It decides a number, pushes a tag and then watches.

## Prerequisites

- A Git checkout on `main`, current with `origin`, with a clean tree and push access for tags.
- GitHub read access to confirm check status and the published Release.
- For the announcement only: a Slack capability that can resolve a channel and post to it, and the
  `humanizer:humanizer` skill. Both are optional. Missing either costs the announcement and
  nothing else.

If a prerequisite for the release itself is missing, stop before the tag push and say which.

## 1. Pre-flight

Answer all of these before looking at any diff. Any "no" stops the run.

```bash
git checkout main && git fetch --prune origin && git pull --ff-only origin main
git status --porcelain                  # must be empty
LAST=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' '[0-9]*.[0-9]*.[0-9]*' --sort=-creatordate | head -1)
echo "last release: $LAST"
python3 scripts/bump_version.py --current
```

**`$LAST` does not survive between shell invocations.** Every block below re-derives it, and every
one of them checks it is non-empty first. An empty `$LAST` turns `"$LAST"..HEAD` into `..HEAD`,
which git resolves to `HEAD..HEAD`: zero commits, empty diffs, exit 0. It reads exactly like a
release with nothing in it. The glob matches only the two release-tag shapes the Release workflow
accepts, so a stray tag cannot become the baseline either.

- **The tree is clean and `main` is current.** A tag is a pointer to a commit on the remote; a
  local edit is not in it.
- **`bump_version.py --current` equals `$LAST` without its `v`.** If it does not, a previous
  release is half finished. Find out why before adding a second one on top. The workflow is
  idempotent and resumable, so the fix is usually to re-push the existing tag, not to cut a new
  number.
- **`main`'s head is green.** The Release workflow runs the contract validator, its own tests, the
  bump-version tests and the whole dashboard suite, but not the quality gate — no ruff, no mypy, no
  frontend linter, no coverage threshold, no platform matrix — because the gate already ran on every
  commit that reached `main`. That only holds if it actually did:

  ```bash
  gh run list --branch main --commit "$(git rev-parse origin/main)" \
    --json workflowName,status,conclusion
  ```

  Three workflows run on every push to `main` — Quality Gate, Validate and Plugin Compatibility —
  and all three must come back `completed` and `success` for that exact commit. Do not use
  `--limit 1`: it returns whichever of the three finished last, so it will show you a green Plugin
  Compatibility while the gate is red. Filtering on the commit is also what rules out a green run
  belonging to a superseded head.
- **The number is still free.** You do not have one yet, so this check runs in step 4 once the
  proposal names `$VERSION`: `git tag -l "v$VERSION"` and `gh release view "v$VERSION"` must both
  come back empty.

One check that does not block but should be reported: if `COMPATIBILITY.md`'s
`docs-synced-through` marker is behind `main`, say so in the proposal. A release is the natural
moment to stamp it, and [AGENTS.md, "Parallel Work"](../../../AGENTS.md#parallel-work) says to
do that once from `main` after
merges. Do not stamp it silently inside a release run.

## 2. Gather the evidence

Commit census first, because it is cheap and it frames everything else:

```bash
LAST=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' '[0-9]*.[0-9]*.[0-9]*' --sort=-creatordate | head -1); [ -n "$LAST" ] || echo "STOP: no release tag found"
git log --oneline "$LAST"..HEAD | grep -v 'chore(release)'
git log --format='%s' "$LAST"..HEAD | grep -v '^chore(release)' \
  | sed -E -e 's/^([a-z]+)(\([^)]*\))?!?:.*/\1/' -e t -e 's/.*/(unprefixed)/' \
  | sort | uniq -c | sort -rn
git diff --stat "$LAST"..HEAD | tail -1
```

The `-e t -e 's/.*/(unprefixed)/'` pair matters: merge commits here often carry no conventional
prefix at all. Without it the census prints eight full subject lines for `v0.7.0` instead of one
`(unprefixed)` count, and a census that is mostly subject lines is not a census.

Then the scan that actually decides the bump. Each command answers "can a person running Cargento
see or do something they could not before?", and each is a real surface rather than a proxy for
one:

```bash
LAST=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' '[0-9]*.[0-9]*.[0-9]*' --sort=-creatordate | head -1); [ -n "$LAST" ] || echo "STOP: no release tag found"
# A new or changed user-facing surface
git diff --stat "$LAST"..HEAD -- cargento/skills/cargento/cargento_runtime/web
# New or changed CLI flags
git diff "$LAST"..HEAD -- '*/cli.py' | grep -E '^[+-].*add_argument\('
# New or changed HTTP routes, GET ladder and POST table alike
git diff "$LAST"..HEAD -- '*/http_api.py' | grep -E '^[+-].*"/(api|")'
# A harness added or dropped from the registry
git diff "$LAST"..HEAD -- '*/aggregate.py' | grep -E '^[+-].*HarnessSpec\('
# New or removed payload fields every consumer sees
git diff "$LAST"..HEAD -- '*/sessions.py' '*/aggregate.py' | grep -E '^[+-] +"[a-z_]+":'
# New or changed hook events, and the stdio MCP tool
git diff --stat "$LAST"..HEAD -- cargento/hooks cargento/hooks.json '*/notify_hook.py' '*/mcp_server.py'
# The runtime floor (`fail_under` rides along; it is a CI knob, not a surface)
git diff "$LAST"..HEAD -- pyproject.toml | grep -E '^[+-].*(target-version|python_version|fail_under)'
# The shipped product surface, and the store paths a person configures
git diff --stat "$LAST"..HEAD -- cargento/skills/cargento/SKILL.md HOW_TO_USE.md COMPATIBILITY.md
```

Read what comes back. A census line is evidence; a diff hunk is the fact.

Two of those patterns are wider than they look, deliberately. The route grep matches any quoted
absolute path in `http_api.py` because POST routes are not an `if` ladder: they are entries in a
dict, `"/api/answer": self._answer,`. A pattern pinned to `path == "/` finds every GET route and
none of the POST ones, so the release that added `/api/ask`, `/api/answer`, `/api/dismiss` and
`/api/ask/withdraw` would have scanned clean. And the hook-and-MCP stat is there because `v0.13.0`
added `mcp_server.py`, 826 lines of new user-facing surface, that nothing else in this list touches.

## 3. Classify the bump

**The rule is the surface, not the commit type.** A `feat:` prefix is how the author felt about
their change, and it has been wrong in both directions here (see the last section).

**Patch** when every change corrects behaviour that already shipped, or is invisible to someone
running the dashboard. Tests, CI, benchmarks, packaging, internal refactors, comment and doc
corrections, and fixes to a surface that already existed all sit here, however many there are. A
release of twenty-one fixes is still a patch if none of them adds a surface.

**Minor** when a person running Cargento can see or do something they could not before: a new
panel or row field, a new harness, a new flag, a new route, a new hook event, a widened contract,
a newly published payload key.

**Major cannot be derived from the changes.** Cargento is `0.x`, and under semver the major stays
`0` until the interface is declared stable. Cutting `1.0.0` is a decision to commit to that
interface, not a consequence of any diff, so never infer one. If the operator asks for a major,
confirm it is deliberate and say what `1.0.0` would commit to, because those become the things that
need a major to change afterwards: the `/api` payload contract, the CLI flags, the store
relocation environment variables, the Python floor, the hook payload shape, the stdio MCP tool, the
plugin and skill names an install references, and the set of supported harnesses.

**Run the breaking-change scan regardless of the number.** Every grep in step 2 prints removals
alongside additions, and the `-` lines are the breaking half: a dropped CLI flag, a deleted route, a
harness out of the registry, a payload key that stopped being published, a raised Python floor. The
`--stat` commands cannot tell you that on their own, so when `cargento/hooks`, `COMPATIBILITY.md` or
the web assets move, open the diff rather than reading the file count. Below `1.0.0` a break does not
force a major, but it is the single most important thing an announcement can carry, and a Python
floor raised in silence is how an install stops working with no note anywhere. Anything the scan
finds goes into the proposal and into the notes.

## 4. Propose, and stop

A release is irreversible. Tags here are immutable, a ruleset blocks deleting or moving them,
`stable` advances to the released commit, and the shared marketplace serves whatever `stable`
points at. A wrong number cannot be withdrawn, only superseded by the next one, forever.

So print the proposal and wait for an explicit yes. Never tag on an inferred approval.

The proposal carries:

1. The range: `$LAST..HEAD`, and the commit count with `chore(release)` excluded.
2. The census.
3. The classification, with the specific evidence that decided it, named. "Minor, because
   `next-activity.js` gained an instruction line and `sessions.py` publishes a new `instruction`
   key" is a reason. "Minor, 4 feats" is a count.
4. Anything the breaking-change scan found, or an explicit "nothing".
5. The proposed version, and the `docs-synced-through` note if the marker is behind. Prove it is
   free before you print it, because this is the first point in the run at which the number exists:

   ```bash
   VERSION=<the proposed number>
   git tag -l "v$VERSION"                       # must print nothing
   gh release view "v$VERSION"                  # must fail with "release not found"
   ```
6. What pushing the tag will do, in one line each: validate the tag, run the release checks, write
   one `chore(release)` bump commit, move the tag onto it, advance `stable`, publish the Release.
7. The question: cut it, and separately, do you want release notes posted to Slack afterwards?

Ask the Slack question here so the run has one interruption rather than two. The notes themselves
still get their own approval in step 7, because nobody can approve text they have not read.

## 5. Cut it

```bash
VERSION=<the number the operator just approved>        # e.g. VERSION=0.17.0
git checkout main && git pull --ff-only origin main    # again; the wait may have been long
gh run list --branch main --commit "$(git rev-parse origin/main)" \
  --json workflowName,status,conclusion                # green again, on the NEW tip
git tag "v$VERSION"
git push origin "v$VERSION"
```

That second green check is not paranoia. The workflow releases the `main` tip, not the commit you
tagged, so anything that merged while the proposal sat waiting is in this release and the pre-flight
result no longer covers it. If the tip moved, re-run step 2 over the wider range before tagging: the
number you got approved may no longer be the right one.

The `v` prefix is canonical. A bare `0.17.0` also works, but pick one form per release and do not
mix them in a single run.

## 6. Watch it land

Do not report a release until it exists.

```bash
gh run list --workflow Release --limit 1 --json status,conclusion,headBranch,databaseId
gh run watch <id> --exit-status
```

Then confirm all four outcomes, because the workflow does four separate things and a partial run
leaves some of them undone:

```bash
VERSION=<the number you just tagged>
git fetch --tags --force origin && git checkout main && git pull --ff-only origin main
git log --oneline -1                       # the chore(release) bump commit, if one was needed
python3 scripts/bump_version.py --current  # equals the new version
git rev-parse "v$VERSION^{commit}" && git rev-parse origin/stable   # tag moved, stable advanced
gh release view "v$VERSION" --json name,tagName,url
```

The bump commit is the one outcome that is conditional: the workflow skips it when the manifests
already carry the tagged version, which is the initial-release path and the resume path. Step 1's
parity check is what makes it unconditional on every normal release.


If the run failed part way, re-push the same tag rather than picking a new number. Every step is
idempotent and the workflow detects its own resume.

## 7. Announce it, if asked

Only after step 6 confirms the Release exists. Announcing a release that has not published is
worse than not announcing.

**Write the notes for a person, not a changelog.** GitHub already generated the full changelog with
`--generate-notes`, and the Slack message that repeats it is noise. Slack gets what changed for
someone using Cargento, and a link.

Aim for a short paragraph or a few bullets: the version, the one or two things worth knowing,
anything the breaking-change scan found, and the Release URL. If nothing in the range is worth a
person's attention, say that plainly and keep it to a line. A patch release of internal corrections
does not need three bullets invented for it.

**Verify before humanising.** Every claim has to trace to a commit in `$LAST..HEAD`. This is the
step that stops a plausible summary describing work that shipped two releases ago. Check each
sentence against the log, and delete anything you cannot point at.

**Then invoke `humanizer:humanizer` on the draft.** The notes are human-facing prose and they carry
the same voice standard the prose docs do. If that skill is not installed, apply the standard by
hand: it is written out in full in the [`sync-docs` skill's "Voice and tone"
section](../sync-docs/SKILL.md#voice-and-tone), which exists
precisely because this repository does not vendor the tool. No em dashes, no mechanical boldface,
sentence case, no AI-vocabulary words, no participle tails, no upbeat closer.

Resolve the channel at run time rather than trusting a remembered id:

- Search Slack for the `#agentchat` channel and take its id from the result.
- Show the operator the final text and the channel it will go to.
- Send only on an explicit yes. If they would rather see it in Slack first, post it as a draft
  instead of a message and let them send it.
- Report the message link back.

## Hard rules

Never edit a version field in a branch. The Release workflow owns all three, and `version-guard`
fails any PR that changes one.

Never tag without an explicit yes in this run. Approval for a previous release is not approval for
this one.

Never announce before `gh release view` succeeds.

Never put a claim in the notes that is not in the commit range. Nothing else in this process has a
check that would catch it.

Never cut a major to mean "this one is big". At `0.x` that number is not available, and above
`1.0.0` it means a break, which is a fact about the diff rather than a feeling about the release.

Never back-tag or reuse a number. The workflow refuses it, and the refusal is the feature.

## Why the classification is written this way

Measured over the whole tag history on 2026-08-28: 27 release tags, so 26 version decisions after
the initial `0.1.0`. Fifteen minor, eleven patch, no major ever.

Reading the bump off the commit types would have agreed with 23 of those 26 and been wrong three
times, which is why this skill reads surfaces instead:

- `v0.4.3` was a **patch containing a `feat`**. The feat listed Cargento in the shared marketplace
  and retired our own, which is packaging. Nothing on the dashboard changed.
- `v0.8.1` was a **patch containing a `feat`**. That one was `feat(bench)`, a tool for measuring a
  session mix you do not have. A developer benchmark is not a product surface.
- `v0.8.0` was a **minor containing only a `fix`**, and it is the one that does not dissolve. The
  fix was to the release workflow itself.

The first two stop being exceptions the moment the question is "can a user see it?" rather than
"what prefix did the author use?". That is the whole argument for the rule in step 3.

One more thing the history says: `BREAKING CHANGE` and the `!` suffix have been used zero times in
this repository. No breaking change is going to announce itself in commit metadata, so the scan in
step 2 is not belt and braces. It is the only detector there is.
