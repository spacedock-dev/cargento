---
name: sync-docs
description: >-
  Reconcile Cargento's documentation with the code so the docs never fall behind. Diffs the real
  HTTP routes, CLI flags, harness registry, relocation env vars, tunable constants, validator rules
  and CI gate against README.md, AGENTS.md, CONTRIBUTING.md, COMPATIBILITY.md, SECURITY.md and the
  shipped `cargento` skill body; applies the updates; retires implemented plan docs under
  `docs/plans/` by folding their durable content into `docs/design-*.md`; and keeps the AGENTS.md /
  CLAUDE.md pointers accurate. **Run it as part of the pre-PR gate** — after the validation suite
  and before `gh pr create`, so every PR carries the doc updates for the code it changes — and also
  periodically, before a release or whenever the docs feel stale. Invoke with /sync-docs.
---

# sync-docs

Keep the docs true to the code and free of bloat. This is a **docs-only** skill: it never changes
Python, manifests, workflow YAML, or version fields — only Markdown. Each run is a
diff-and-reconcile pass, not a rewrite.

## Hard boundaries — this repository will reject you otherwise

- **Never touch a version field.** The plugin version appears in `.claude-plugin/marketplace.json`
  (twice), `cargento/.claude-plugin/plugin.json`, `cargento/.codex-plugin/plugin.json` and
  `cargento/gemini-extension.json`, and is owned by the tag-driven Release workflow. The
  `version-guard` check fails any PR that changes one. Never write a version literal into Markdown
  either — it would drift permanently and unwatched. Illustrative tags (`git tag v0.2.0`) are fine.
- **Never change the plugin description casually.** It must stay byte-identical across five
  manifests; `scripts/validate_plugins.py` enforces parity. If a correction genuinely requires a new
  description, change all five in the same commit — or leave it and report it as unresolved.
- **Never edit application code**, even to make a doc claim true. If a doc is right and the code is
  wrong, report it; do not fix it here. The one exception is a comment that cites a document you
  deleted or renamed — repointing that reference is part of the deletion (step 5).
- **Never weaken a validator rule to make an edit pass.** If a doc fix and a validator rule are
  jointly unsatisfiable, stop and surface it rather than leaving a required check red.
- **Respect the exclusion list** below. Some Markdown here is an input to a program, not prose.

## When to run

- **Before opening a PR** (the primary trigger). Per `AGENTS.md`, `/sync-docs` is a step in the
  branch → commit → validation suite → **sync-docs** → push → `gh pr create` workflow, so the doc
  updates for a change ride in the same PR and the docs never drift between merges. Scope the pass
  to what your branch touched (step 1).
- Periodically, or before tagging a release, as a full reconcile even without a code change.

## The doc-ownership map — consolidate, don't proliferate

| File | Owns | Rule |
|------|------|------|
| `README.md` | The front door: what Cargento is, prerequisites, per-harness install, the skill inventory table, a short "how it works", links out. | Keep short. No command suites and no reference tables — link to the owner. **Validator-asserted:** the literals `/cargento:cargento` and `codex plugin add cargento@cargento-marketplace` must appear verbatim; rewording either fails the required `validate` check. |
| `AGENTS.md` | **Canonical** repository contract and the source of truth for process: architecture tree, doc map, commit conventions, PR workflow, the pre-PR command list, the quality gate, versioning/releases, portability rules. | Every process command list is defined here once; other docs link. `CLAUDE.md` imports it, so edits propagate. Never rename or move it — Codex and Claude both load it by name. |
| `CLAUDE.md` | Claude-Code-only addenda. | Line 1 must stay the bare `@AGENTS.md` import. Nothing that would also be true in Codex — that belongs in `AGENTS.md`. |
| `CONTRIBUTING.md` | The human contributor journey: clone → dev setup → run locally → the quality gate → tests → what the validator enforces → `server.py` design constraints → commits → PRs → adding a harness → releases. | Task-oriented. Reference the pre-PR suite in `AGENTS.md` rather than re-listing it; duplicated command lists are how they drift. |
| `COMPATIBILITY.md` | **Canonical** cross-harness and cross-platform contract: the per-runtime surface matrix, the per-OS capability matrix, the platform caveats, the native per-runtime validators, and **the Python floor** (with the list of every other place it is restated). Carries the sync marker. | Matrices and their footnotes. *Why* a row reads the way it does belongs in `docs/design-*.md`. |
| `SECURITY.md` | Security posture: the invariants, the known-and-accepted exposures, and private reporting. Covers the whole shipped surface — `server.py` **and** `notify_hook.py`. | Anything that weakens an invariant is a security bug and belongs here. Keep the contact address equal to the one in `CODE_OF_CONDUCT.md`; nothing checks it. |
| `cargento/skills/cargento/SKILL.md` | **Canonical** product surface: per-harness data sources, session states, start/stop, notifications, options, interpretation notes, common mistakes. | A *shipped, validated artifact* — see the constraints below. It is installed without the repository, so it must never contain a repo-relative link or repo process. |
| `docs/design-*.md` | The durable *why/how* per area — decisions that outlive the build, **including alternatives that were tried and rejected and the reason why**. | A decision earns a place here if re-deriving it would cost a day, or if a maintainer would otherwise re-attempt something already proven wrong. |
| `docs/plans/*.md` | **Transient** plans for *unshipped* work only. | Once the work ships, fold the durable *what* into the owning doc and the durable *why* into `docs/design-*.md`, then **delete the plan file.** |
| `.github/PULL_REQUEST_TEMPLATE.md` | The PR author's checklist. | Must mirror the real gate in `AGENTS.md` — if the gate gains a step, this gains a checkbox. Never rename; GitHub loads it by path. The HTML comments are deliberate hints. |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1, verbatim. | **Never edit the text.** Only the enforcement contact is ours. |
| `.claude/skills/*/SKILL.md` | Repository development skills, including this one. Not shipped with the plugin. | Editable prose, but keep the path — Claude Code discovers these by directory name, and `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md` and the PR template point at it. The banned portability literals are legal here because this tree is not shipped; the validator link-checks these files but does not marker-scan them. |

### Constraints on `cargento/skills/cargento/SKILL.md`

`scripts/validate_plugins.py` scans every Markdown file under `cargento/skills/`, and
`tests/test_server.py` asserts the skill body against the code. Both are required checks:

- Frontmatter fields are exactly `name`, `description`, `license` — nothing else, no duplicate keys.
  `name` must be lowercase kebab-case and equal the directory name.
- `description` is required, **at most 300 characters** (300 exactly passes), and may not contain
  `<` or `>`.
- The body must stay host-neutral. These six literal substrings are rejected anywhere in the file:
  `${CLAUDE_PLUGIN_ROOT}`, the user-cache skills path, `mcp__claude_ai_`, `ToolSearch(`,
  `Skill(skill=`, `subagent_type`. *(That second one is why this skill's own path must never be
  pasted into the skill body — write it out in prose instead.)*
- Every relative Markdown link must resolve inside the repository. In practice: **do not add links
  to repo files at all**, because the plugin is installed without the repository around it.
- The documentation-matches-code test additionally requires: every backticked `~/…` path must
  prefix-match (in either direction) a real `resolve_store_roots` output, except `~/.claude/settings*`
  which is carved out; the set of backticked store environment variables must **equal**
  `STORE_ENV_VARS` in the code; the literal `Python 3.11+` must appear; and the body must contain
  `http://127.0.0.1:4553` and must not contain the equivalent `localhost:4553` URL. The repository
  validator applies that same ban to every prose doc — including this file, which is why the banned
  spelling is not written out here.

After any edit under `cargento/skills/`, run `python3 scripts/validate_plugins.py` and
`python3 -m unittest cargento/skills/cargento/tests/test_server.py` before committing.

## Markdown that is not documentation — never reconcile these

Some Markdown here is consumed by a program, reproduced verbatim from upstream, or generated.
Editing it changes behavior or breaks a licence, silently.

| Path / pattern | Why it is off-limits | Allowed action |
|---|---|---|
| `CODE_OF_CONDUCT.md` | Verbatim Contributor Covenant 2.1. The version is pinned by the README badge and by the self-attestation near the end. | Fix the enforcement contact only. Never reword the covenant. |
| `LICENSE`, `NOTICE` | Apache-2.0 text and its §4(d) attribution. Extensionless, so no `*.md` sweep reaches them — but a "tidy the docs" pass can. | None. Edits are legal changes. |
| `.github/ISSUE_TEMPLATE/*.yml` | GitHub issue *forms*: prose inside a validated schema. | Edit `label` / `description` strings only; never touch keys, `id`s or `labels:`. Keep the harness options aligned with the registry, but do not delete the non-harness catch-all option. |
| `.github/ISSUE_TEMPLATE/config.yml` | Chooser config. Its `name`/`about` strings do render, but the security-advisory URL is load-bearing. | None — and if it must change, keep it consistent with `SECURITY.md`. |
| `coverage-comment.md` | Written by a CI step and read back by the next one; its marker comment must stay byte-identical to what the comment action matches on. Untracked. | Never. If it appears locally it is CI debris. |
| Markdown under `**/tests/**` or created by a fixture | Test input; its content is asserted on. | Never. New fixtures must live **outside** `cargento/skills/`, or the validator will scan them and fail the build. |
| `cargento/commands/*.md` | Rejected outright by the validator as legacy commands. | Never create Markdown there. |
| `.git/`, `.mypy_cache/`, `.ruff_cache/`, `__pycache__/`, `node_modules/`, `.venv/` | Not source. | Never. |

### Classifying Markdown this table does not list

Before editing any `*.md` you have not touched before, run the checks — never judge by filename:

```bash
F=<path>
# 1. Tracked? Untracked Markdown is generated or scratch until proven otherwise.
git ls-files --error-unmatch "$F" >/dev/null 2>&1 || echo "UNTRACKED — establish why before editing"
# 2. Does a program reach it? Search the basename outside Markdown.
grep -rn --exclude-dir={.git,.mypy_cache,.ruff_cache,__pycache__} -F "$(basename "$F")" \
  --include='*.py' --include='*.yml' --include='*.yaml' --include='*.json' --include='*.toml' .
```

Then apply, in order:

1. **A hit is a candidate, not a consumer.** It is a consumer only if the path is opened, read,
   globbed, counted, or asserted on there. A filename inside a comment or an error string is not.
   Open the hit and read it. Then split the verdict by *what* is consumed: a file whose mere
   existence or links are checked has a **frozen path but editable content** — deleting or renaming
   it fails the build, editing it does not. A file whose *strings* are asserted has those specific
   strings frozen. Every entry in `ROOT_DOCS` in `scripts/validate_plugins.py` is in the first
   category; `README.md` and the shipped skill body are in both.
2. **Location outranks content.** Anything under `cargento/skills/` is a shipped artifact and gets
   the full constraint set above, including `references/` or `operations/` files that do not exist
   yet. Anything a required check asserts against code is system-consumed even when it reads like
   prose — in this repository that is the skill body and `README.md`.
3. **Convention-located files keep their exact path.** `AGENTS.md`, `CLAUDE.md`, `SECURITY.md`,
   `CODE_OF_CONDUCT.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/*`, and every
   `SKILL.md`. "Grep found no consumer" means nothing for this class.
4. **Verbatim upstream is never-touch — but match the whole document, not a mention.** The test is
   whether the file *is* the upstream artifact, not whether it links to one. `README.md` and
   `CONTRIBUTING.md` both link the licence and are ordinary docs.
5. **A command block under a "Validation", "Test plan" or "Pre-PR" heading is executable content.**
   Every line must stay literally runnable, and the block must be complete relative to the real
   gate. Do not reword a command for readability.
6. **Stable in-document identifiers are part of the contract.** Decision IDs (`D-1`…`D-6` in
   `docs/design-*.md`) and heading anchors are cited from code comments and from other docs, and
   only the anchors are gate-checked. Before renumbering or renaming one, grep the identifier across
   `*.py`, `*.toml` and `*.md` and repoint every citation — or don't renumber.
7. **Most restrictive wins; never-touch beats everything.** Where two rules conflict irreconcilably,
   stop and ask.

When in doubt, leave the file alone and list it under `Unresolved:` in the report. A missed doc
update is cheap; a silently broken fixture or system prompt is not.

## Extract the "code truth"

Run these from the repository root; the output is what the docs MUST match.

```bash
S=cargento/skills/cargento/server.py

# HTTP routes the server actually serves
grep -oE '(url\.path|urlparse\(self\.path\)\.path) [!=]= "[^"]+"' "$S" | grep -oE '"/[^"]*"' | sort -u
# CLI flags and their defaults
grep -E -A4 'ap\.add_argument\(' "$S" | grep -E '"--|default='
# The harness registry — one collector per supported harness
awk '/^HARNESSES/,/^\]$/' "$S" | grep -oE 'collect_[a-z]+' | sort -u
# Store-relocation environment variables the resolver advertises
grep -oE 'STORE_ENV_VARS = \(.*\)' "$S"
# Tunable constants the docs quote by value (ports, thresholds, windows)
grep -nE '^[A-Z_]+ = [0-9]' "$S"
# Python floor: the ruff target and the mypy pin must agree, and match the docs
grep -nE 'target-version|python_version|fail_under' pyproject.toml
# The real CI command surface
grep -nE '^\s+(- name:|run:|  +[a-z].*)$' .github/workflows/quality-gate.yml | grep -E 'ruff|mypy|coverage|unittest|lint_embedded|validate_plugins'
grep -nE 'run: ' .github/workflows/validate.yml
# What the validator enforces on documentation
grep -nE 'PORTABILITY_MARKERS|SHARED_FRONTMATTER_FIELDS|ROOT_DOCS|BANNED_DOC_LITERALS|maximum is 300' \
  scripts/validate_plugins.py
```

Cross-check every count a doc states — "eight harnesses", "five places", a port, a threshold in
minutes, a Python version. Stale counts are this repository's most common drift.

## Procedure

1. **Scope the diff.** Find what landed since the last sync. Drive this off the
   `docs-synced-through` marker at the bottom of `COMPATIBILITY.md`, **not** off the last commit
   that touched the file — once any commit on this branch edits `COMPATIBILITY.md`, that commit
   *is* the last one to touch it and the range collapses to empty exactly when you need it:
   ```bash
   MARKER=$(grep -oE 'docs-synced-through: [0-9a-f]+' COMPATIBILITY.md | awk '{print $2}')
   git log --oneline "${MARKER:-origin/main}..HEAD"
   git log --stat "${MARKER:-origin/main}..HEAD" -- '*.py' '*.toml' '*.yml'
   ```
   The `--stat` output tells you which subsystems moved, so you know where to look; the extraction
   above is the ground truth. If the marker is missing or unresolvable, fall back to
   `origin/main..HEAD` and say so in the report.
2. **Reconcile each doc against the code truth.** Every real item must appear correctly wherever it
   is documented, and every doc claim must still match the code. Build the full checklist of edits
   before making any. **Prune as you go:** tighten entries that bloated into specs, collapse an
   explanation repeated across docs down to the one owner plus a link, and delete shipped TODOs and
   caveats that no longer apply.
3. **Diff the command lists against each other.** The pre-PR suite, the CI workflows and the PR
   template checklist drift apart quietly, and a short local copy is worse than none — a contributor
   follows it, passes, and then fails the required gate. `AGENTS.md` owns the canonical list; every
   other mention must match it or link to it. Actually run any command you document for the first
   time.
4. **Retire implemented plan docs.** For each file under `docs/plans/`: decide whether the work
   shipped by checking the **code**, not the document's own status markers — a plan that says "DONE"
   is a claim, not evidence. If it shipped, make sure its durable *what* reached the owning doc and
   its durable *why* reached `docs/design-*.md` — **especially the alternatives that were tried and
   rejected**, which are the expensive things to lose — then **delete the plan file**. Keep only
   plans for genuinely unshipped work, trimmed to what remains.
5. **Fix cross-references.** After deleting or renaming any doc, repoint everything that referenced
   it, including non-Markdown files, which are the easy misses:
   ```bash
   grep -rn --exclude-dir={.git,.mypy_cache,.ruff_cache,__pycache__} \
     -e 'docs/plans/' -e 'docs/design-' -e '<the-deleted-file>' .
   ```
   Comments in `.py`, `.toml` and `.yml` count. Repointing them is allowed here even though this is
   a docs-only skill: a comment naming a file you deleted is a doc reference, not behavior.
6. **Update the pointers.** Keep the `AGENTS.md` architecture tree and doc map, and `README.md`'s
   links, current. `CLAUDE.md` imports `AGENTS.md`, so those edits propagate — but check that no
   Claude-only bullet has become universally true (move it up) or obsolete (delete it).
7. **Stamp the sync.** Update the marker at the bottom of `COMPATIBILITY.md` to the current `HEAD`:
   `<!-- docs-synced-through: <short-sha> (<YYYY-MM-DD>) -->`.
8. **Verify.** All four checks, every run. Use `git status`/`git diff HEAD`, **not** plain
   `git diff` — a bare `git diff` shows neither your new untracked docs nor a staged deletion, so it
   reports "clean" for exactly the changes this pass makes:
   ```bash
   # a. Nothing but docs changed (comment-only repoints from step 5 are the allowed exception).
   git status --porcelain -uall | awk '{print $NF}' | grep -vE '\.md$'

   # b. No version field moved anywhere on this branch. `version-guard` compares the PR head
   #    against the MERGE BASE, so an already-committed bump is invisible to `git diff HEAD` and
   #    passes `bump_version.py --current` (which only checks five-way parity, not immutability).
   git diff "$(git merge-base origin/main HEAD)"..HEAD \
     -- '*plugin.json' '*marketplace.json' '*gemini-extension.json' | grep -E '^[+-].*"version"'

   # c. The validator: link and anchor resolution across prose docs and bundled skill Markdown,
   #    the banned literals, description length, and the portability markers.
   python3 scripts/validate_plugins.py

   # d. If you touched the skill body, the documentation-matches-code assertions.
   python3 -m unittest cargento/skills/cargento/tests/test_server.py
   ```
   Do **not** run the rest of the Python suite for a docs-only pass unless a doc claims a command
   you changed.
9. **Stage, commit in the right place, then report.** Never commit to `main`. Stage explicitly —
   new docs are untracked, so `git commit -a` would silently skip them:
   ```bash
   git add -A -- '*.md'          # plus any comment-only repoints from step 5, named individually
   git status --short            # confirm the staged set is what you expect
   ```
   - **Pre-PR-gate run** (invoked on an existing `feat/…`/`fix/…` branch before `gh pr create`):
     commit onto **that same branch** with `git commit -s` — do not create a new branch or a second
     PR; the doc updates ride in the PR you are about to open.
   - **Standalone/periodic run** (started from `main`, no feature work in flight): create a
     `docs/…` branch, commit, and open its own PR.

   End with a one-line report:
   `Added: … | Corrected: … | Retired (deleted): … | Unresolved: …`, plus the new sync marker.

## When NOT to change something

- A doc deliberately records a known gap or an accepted trade-off — the skill body's "Known gap"
  note, `COMPATIBILITY.md`'s unsupported-WSL-topology paragraph, `SECURITY.md`'s "Known and
  accepted" section. Preserve it. Remove such a note only when the underlying code changed; quietly
  deleting an honest caveat is worse than the caveat.
- A `docs/design-*.md` entry that explains why an approach was **rejected**. It describes code that
  does not exist, which is exactly what makes it look stale and exactly why it is there. Never
  prune it on those grounds.
- Version and description fields, per the hard boundaries above.
- Any file in the exclusion table, or any file whose classification you are unsure of.
