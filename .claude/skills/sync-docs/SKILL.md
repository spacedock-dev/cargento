---
name: sync-docs
description: >-
  Reconcile Cargento's documentation with the code so the docs never fall behind. Diffs the real
  HTTP routes, CLI flags, harness registry, relocation env vars, tunable constants, validator rules
  and CI gate against README.md, AGENTS.md, CONTRIBUTING.md, COMPATIBILITY.md, SECURITY.md and the
  shipped `cargento` skill body; applies the updates; retires implemented plan docs under
  `docs/plans/` by folding their durable content into `docs/design-*.md`; holds the human-facing
  prose it touched to the documented voice standard so the tone does not drift back to
  model-default; and keeps the AGENTS.md / CLAUDE.md pointers accurate. **Run it as part of the pre-PR gate** — after the validation suite
  and before `gh pr create`, so every PR carries the doc updates for the code it changes — and also
  periodically, before a release or whenever the docs feel stale. Invoke with /sync-docs.
---

# sync-docs

Keep the docs true to the code and free of bloat. This is a **docs-only** skill: it never changes
Python, manifests, workflow YAML, or version fields — only Markdown. Each run is a
diff-and-reconcile pass, not a rewrite.

## Hard boundaries — this repository will reject you otherwise

- **Never touch a version field.** The plugin version appears in
  `cargento/.claude-plugin/plugin.json` (the source of truth), `cargento/.codex-plugin/plugin.json`
  and `cargento/gemini-extension.json`, and is owned by the tag-driven Release workflow. The
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
The dashboard test suite asserts the skill body against the code. Both are required checks:

- Frontmatter fields are exactly `name`, `description`, `license` — nothing else, no duplicate keys.
  `name` must be lowercase kebab-case and equal the directory name.
- `description` is required, **at most 300 characters** (300 exactly passes), and may not contain
  `<` or `>`.
- The body must stay host-neutral. These six literal substrings are rejected anywhere in the file:
  `${CLAUDE_PLUGIN_ROOT}`, the user-cache skills path, `mcp__claude_ai_`, `ToolSearch(`,
  `Skill(skill=`, `subagent_type`. *(That second one is why this skill's own path must never be
  pasted into the skill body — write it out in prose instead.)*
- Every relative Markdown link and `#heading-anchor` must resolve inside the repository. In
  practice: **do not add links to repo files at all**, because the plugin is installed without the
  repository around it.
- The documentation-matches-code test additionally requires: every backticked `~/…` path must
  prefix-match (in either direction) a real `resolve_store_roots` output, except `~/.claude/settings*`
  which is carved out; the set of backticked store environment variables must **equal**
  `STORE_ENV_VARS` in the code; the literal `Python 3.11+` must appear; and the body must contain
  `http://127.0.0.1:4553` and must not contain the equivalent `localhost:4553` URL. The repository
  validator applies that same ban to every prose doc — including this file, which is why the banned
  spelling is not written out here.

After any edit under `cargento/skills/`, run `python3 scripts/validate_plugins.py` and
`python3 -m unittest discover -s cargento/skills/cargento/tests -t .` before committing.

## Voice and tone

The prose docs are written for people, and they were humanized in one deliberate pass. An agent
topping them up in model-default voice, one sync at a time, is how that gets undone. Step 7 of the
Procedure exists to stop it, and check (e) in step 9 is the mechanical backstop, since nothing in CI
enforces tone.

**This section is the contract, not the `humanizer` skill.** That skill automates the pass and is
worth using where a harness has it, but this repository does not vendor it and a clean checkout will
not have it. Everything needed to apply the standard by hand is written out below, deliberately, so
the rule survives the tool going missing.

In scope, and the exact set check (e) greps:

```
README.md  CONTRIBUTING.md  COMPATIBILITY.md  SECURITY.md  docs/design-*.md  docs/plans/*.md
```

Out of scope, deliberately: `AGENTS.md` and `CLAUDE.md` (agent contracts loaded verbatim as
instructions), `cargento/skills/cargento/SKILL.md` (a validated artifact with test-asserted
literals, shipped to other harnesses as agent instructions), and this file. Leave their voice alone.

The standard, in order of how often it is violated:

- No em dashes, en dashes, or curly quotes. This is the hard one, and the one check (e) catches.
  Use a period, a comma, a colon, or parentheses instead.
- No mechanical boldface, and no inline-header lists (`- **Thing:** the thing is...`). A list is
  fine; bolding the first two words of every item is the tell.
- Sentence case in headings, not Title Case.
- Prefer `is`/`are`/`has` over "serves as", "stands as", "boasts", "features".
- Cut the AI-vocabulary words: crucial, pivotal, seamless, robust, leverage, delve, showcase,
  underscore, testament, landscape (figurative), tapestry.
- No participle tails bolted on for depth ("..., ensuring reliability", "..., highlighting its
  importance").
- No generic upbeat closers. End on the last concrete fact.

Two things not to do in the name of tone. Never drop a fact to make a sentence flow, and never add
one to make it land: the pass keeps the information and changes only the shape. And do not
flatten the specifics that make these docs worth reading. The measured numbers, the named failure
modes, and above all the rejected-alternatives lists in `docs/design-*.md` are the human signal, not
the noise.

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
A=cargento/skills/cargento/cargento_runtime/aggregate.py
C=cargento/skills/cargento/cargento_runtime/config.py
R=cargento/skills/cargento/cargento_runtime/state.py
W=cargento/skills/cargento/cargento_runtime/web
G=cargento/skills/cargento/cargento_runtime/diagnostics.py
H=cargento/skills/cargento/cargento_runtime/http_api.py
L=cargento/skills/cargento/cargento_runtime/lifecycle.py

# HTTP routes the server actually serves, and who owns the listener. The
# pattern matches the local `path` too: do_POST binds it once and compares that,
# so an `urlparse(...)`-only pattern silently missed both POST routes.
grep -oE '\b(url\.path|path) [!=]= "/[^"]*"' "$H" | grep -oE '"/[^"]*"' | sort -u
grep -nE '^(class CargentoHTTPServer|class _RequestHandler)|^def (normalize_host|reuse_address_allowed|bind_error_message)' "$H"
# CLI flags and their defaults
grep -E -A4 'ap\.add_argument\(' "$S" | grep -E '"--|default='
# The harness registry: one row per supported harness, in the order the page
# renders its chips. Read it from `aggregate.default_harnesses` rather than by
# matching source text, because the rows are multi-line. The third column is
# each callback's defining module. Every row must resolve under
# `cargento_runtime.collectors`; Claude's is the one wrapper the registry builds
# itself, to bind the popup notifier its collector needs.
python3 - "$A" <<'PY'
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parents[1]))
from cargento_runtime import aggregate

for spec in aggregate.default_harnesses(lambda _title, _message: None):
    print(f"{spec.key:10} {spec.label:10} {spec.collect.__module__}")
PY
# Lifecycle operations, and the one respawn contract --daemon uses on Windows
grep -nE '^def (tcp_port|cargento_home|state_path|log_path|write_state|read_state|probe_port|port_released|await_release|instance_status|render_status|stop_instance|fork_daemon|await_daemon|spawn_argv|spawn_detached|await_spawned|prepare_daemon_home|serve)' "$L"
# The application boundary and the registry contract it consumes
grep -nE '^(class Application|class HarnessSpec)|^def default_harnesses|^    def collect' "$A"
grep -nE '^HARNESSES|^def (_legacy_application|_bound_popup_notifier)' "$S"
# What --diagnose reports, and the pinned order it reports stores in
grep -nE '^(_REPORT_KEY_ORDER|def (store_primaries|candidate_report|diagnose|render_diagnosis))' "$G"
# Store-relocation environment variables the resolver advertises
grep -nE '^(STORE_ENV_VARS|CARGENTO_HOME_ENV) = ' "$C"
# Immutable configuration fields, builders, and locked defaults
grep -nE '^(class RuntimeConfig|def (build_runtime_config|resolve_store_roots|store_roots|primary_store))' "$C"
awk '/return RuntimeConfig\\(/,/^    \\)/' "$C"
# Mutable state fields, lock/dictionary factories, and builder/helper bodies
sed -n '/^class CollectMemoEntry/,$p' "$R"
# Python floor: the ruff target and the mypy pin must agree, and match the docs
grep -nE 'target-version|python_version|fail_under' pyproject.toml
# Frontend source ownership, assembly slots, and byte identity
grep -nE 'WEB_DIR|load_frontend' scripts/lint_embedded.py
grep -o '{{CARGENTO_STYLES}}\|{{CARGENTO_APP}}' "$W/index.html" | sort | uniq -c
python3 - "$W" <<'PY'
import hashlib
import sys
from pathlib import Path

web = Path(sys.argv[1])
for name in ("index.html", "styles.css", "app.js"):
    payload = (web / name).read_bytes()
    print(name, len(payload), hashlib.sha256(payload).hexdigest())
template = (web / "index.html").read_text(encoding="utf-8")
styles = (web / "styles.css").read_text(encoding="utf-8")
script = (web / "app.js").read_text(encoding="utf-8")
page = (
    template.replace("{{CARGENTO_STYLES}}", styles)
    .replace("{{CARGENTO_APP}}", script)
    .encode("utf-8")
)
print("assembled page", len(page), hashlib.sha256(page).hexdigest())
PY
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
7. **Bring the tone back to the standard.** The prose docs are written for humans, and the fastest
   way for that to rot is an agent topping them up in model-default voice one sync at a time. Apply
   the Voice and tone section to every human-facing doc this pass edited, and re-read the result: it
   must keep every fact and lose only the tells. Do not touch `AGENTS.md`, `CLAUDE.md`, the shipped
   skill body, or this file.

   The `humanizer` skill automates this and is worth using **if your harness has it**, in file mode,
   one doc at a time. It is a third-party skill that this repository does not vendor, so treat it as
   an accelerant and never as a prerequisite. Voice and tone is the contract; a contributor with no
   humanizer installed applies it by hand and is equally done.
8. **Stamp the sync.** Update the marker at the bottom of `COMPATIBILITY.md`:
   `<!-- docs-synced-through: <short-sha> (<YYYY-MM-DD>) -->`. Stamp the `origin/main` tip this
   branch is based on, **not** your branch `HEAD`:
   ```bash
   git rev-parse --short "$(git merge-base origin/main HEAD)"
   ```
   `main` is squash-merged, so a branch commit stops existing the moment the PR lands, and step 1
   then cannot resolve the marker it is supposed to read. A merge-base sha is already on `main` and
   stays there. (This was learned twice the hard way: markers pointing at `a4eb54c` and `ef480af`
   were both orphaned by the squash that shipped them.)
9. **Verify.** All five checks, every run. Use `git status`/`git diff HEAD`, **not** plain
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
   python3 -m unittest discover -s cargento/skills/cargento/tests -t .

   # e. Tone: no em/en dashes or curly quotes in the human-facing prose docs. Nothing in CI
   #    enforces this, so it is the one anti-drift check that only exists here.
   #    `ls` builds the list because step 4 deletes plan docs: a bare `docs/plans/*.md` that
   #    matches nothing stays literal and makes grep exit 2 on a "No such file" error.
   #    The explicit if/else is here because a bare `grep && echo` exits 1 when the docs are
   #    CLEAN, which reads as failure to anyone (or anything) checking the status.
   if grep -n '—\|–\|[“”‘’]' $(ls README.md CONTRIBUTING.md COMPATIBILITY.md SECURITY.md \
        docs/design-*.md docs/plans/*.md 2>/dev/null); then
     echo "TONE DRIFT: reapply Voice and tone to the files listed above"
   else
     echo "tone clean"
   fi
   ```
   **Then decide whether you owe the full gate, by who authors the PR:**
   - **Pre-PR-gate run** — checks a to e are enough. The suite in `AGENTS.md` § Pre-PR Checks ran on
     this same tree minutes ago and the human author owns the result.
   - **Standalone/periodic run** — you are the PR author, so run the **whole** pre-PR suite from
     `AGENTS.md` before opening anything. `quality-gate` is a required check covering ruff, format,
     `mypy --strict`, `lint_embedded.py`, coverage against `fail_under`, and `platform-tests` on
     three OSes; none of that is implied by a to e. Opening a PR you have not gated pushes your own
     verification onto the reviewer.

   Never open or update a PR on the strength of a to e alone.
10. **Stage, commit in the right place, then report.** Never commit to `main`. Stage explicitly —
    new docs are untracked, so `git commit -a` would silently skip them:
    ```bash
    git add -A -- '*.md'          # plus any comment-only repoints from step 5, named individually
    git status --short            # confirm the staged set is what you expect
    ```
    - **Pre-PR-gate run** (invoked on an existing `feat/…`/`fix/…` branch before `gh pr create`):
      commit onto **that same branch** with `git commit -s` — do not create a new branch or a second
      PR; the doc updates ride in the PR you are about to open.
    - **Standalone/periodic run** (started from `main`, no feature work in flight): create a
      `docs/…` branch, commit, and open its own PR — having run the full suite per step 9.

    **A standalone run is not finished when the PR opens; it is finished when the required checks are
    green.** Watch them. If one goes red, either it is your doing — fix it — or it is unrelated to a
    docs-only diff, in which case *prove* that before dismissing it: show the diff touches no code the
    failing test exercises, name the failure mode, and re-run the job. "Probably flaky" without
    evidence is how a real regression ships.

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
