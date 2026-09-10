<!-- Transient. Delete this file when DRC-4511 and DRC-4512 ship, per AGENTS.md's docs table. -->

# The reading producer: implementation brief

Written 2026-09-10 from a design panel of three independent proposals (validator-first,
evidence-ledger, render-gate), each scored by three lenses (false reassurance, buildability in this
PR, reader honesty), then synthesised. Scores were evidence-ledger 22, render-gate 20,
validator-first 18 out of 30; the spine is evidence-ledger and the two grafts are named below.

Four live defects in the current tree were found by that panel rather than by CI, and they are
recorded in section 9 and in the C5 change list. They are defects today, not risks introduced by
this design.

# Implementation brief — the reading producer

Worktree: `/Users/jaredmscott/repos/recce/cargento/.claude/worktrees/hold-it-to-what-i-asked`. Branch `feat/hold-it-to-what-i-asked`, PR #317.

Spine: **evidence-ledger**. Grafted: render-gate's **unknown-key hard refusal** (the only guard that catches a divergence nobody anticipated), validator-first's **producer-copied `clause` / producer-composed `stamp` and `cutoff`** (keeps eleven renderer assertions green that render-gate would have inverted), and the **departures-block third state** all three proposals missed.

Everything below was checked against this worktree. Where I am guessing, it says so.

---

## 0. The three things that must be unrenderable, and where each is stopped

| Forbidden output | Stopped by | Where |
|---|---|---|
| the word "met" as a verdict | the model emits a *token*, never a sentence; `reading.RESULT_BY_TOKEN.get()` misses map to no `result` key | `reading.parse_reply` / `reading.resolve` |
| the word "met" inside prose | `detail` renders only when the criterion's **final** result is `departure`; a verdict word in it demotes the whole criterion | `nextCockpitReadingCriterion`, `reading.VERDICT_WORDS` |
| a departure citing nothing | citations are ledger **indices**, resolved server-side, re-resolved client-side; empty ⇒ `not verifiable` at both layers | `reading.resolve`, `nextReadingCitations` (next-cockpit.js:1131-1137) |
| a deliverable claim on a harness with no work evidence | the Expected Output constraint is never put to the model outside `pi`; the renderer's existing limit demotion stays as backstop | `reading.WORK_EVIDENCE_HARNESSES`, next-cockpit.js:1188-1203 |
| a producer/renderer key divergence | unknown key at either level ⇒ named whole-shape or whole-criterion refusal that draws no verdict | `nextCockpitReadingShape` |

---

## 1. Flat or nested — **one flat row key, one nested value**

The published row gains three flat fields:

```
annotation_assessment       dict | None      the nested reading
annotation_reading_count    int              presses that reached the model
annotation_reading_withheld str              a code-owned sentence, or ""
```

Reconciliation with DEC-15b's five flat names:

- **Those five are HISTORY names, and history admission is deferred** (see §8). `docs/design-reading-a-session.md:76-79` names them "not admitted", and says each still needs its own allowlist line. The flattening argument at `sessions.py:520-527` is explicitly about `history.PROMPT_TEXT_ALLOWLIST` admitting *names*; that tuple (`history.py:183-186`) is a constraint on the **store**, not on the snapshot. Nothing in the snapshot path reads it.
- The renderer already reads the nested shape. `nextCockpitAnnotation`'s field list carries `assessment` (next-cockpit.js:64-65) and `nextCockpitReadingShape` consumes `source.criteria` as one object (:1288). `tests/test_next_cockpit.py:5548` and `:4700-4704` already inject `annotation_assessment` as a nested literal and render it end to end. Publishing the same key with the same shape is **zero JS change at the seam**.
- Why not five flat scalars on the row now: the criteria are two constraints × four fields × a citation list. There is no honest flattening, and `test_history.py`'s existing ban on nested carriers for `tasks`/`subagents`/`spacedock` is a *store* ban, not a row ban.

`annotation_reading_withheld` is a **separate flat scalar, not a member of the assessment**. This is deliberate and it is the fix for validator-first's worst defect: a withheld press stored into the assessment slot makes `annotation.assessment` truthy, which skips the `if(!raw)` arm at next-cockpit.js:1388 — taking the offer button and the disclosure paragraph off the page (they exist only inside that arm, :1414-1420) and handing `nextCockpitDepartures(shape)` an empty departure list, which prints "The reading raised no departure from the revision it read." (:1379-1381) for a press that produced no reading.

---

## 2. The exact keys, and what stops a silent divergence

`reading.Assessment`, a `TypedDict(total=True)` — so `mypy --strict` makes `revisionRead` a type error at the construction site, not a render-time silence.

```python
class Criterion(TypedDict):
    result: NotRequired[str]   # ABSENT when the model said nothing usable (rule 2)
    cites:  tuple[str, ...]    # fact_ids, code-resolved from ledger indices
    detail: str                # "" unless the final result is a departure
    clause: str                # verbatim revisions[i]["goal"|"output"]

class Assessment(TypedDict):
    revision_read: int         # SNAKE. int. never absent, never a string.
    stamp:         str         # producer-composed from application.clock()
    cutoff:        str         # producer-composed from ledger counts
    scope:         str         # "mid-flight" | "final" | "withdrawn"
    scope_text:    str         # SCOPE_TEXT[scope]
    ended_at_read: float | None
    criteria:      dict[str, Criterion]   # exactly {"goal", "output"}
```

`reading.ASSESSMENT_KEYS` and `reading.CRITERION_KEYS` are tuples; JS gains `NEXT_READING_ASSESSMENT_KEYS` / `NEXT_READING_CRITERION_KEYS` with the same members.

Four independent mechanisms, because this is the measured biggest risk:

1. **`total=True` TypedDict** — a producer writing `revisionRead` fails `mypy --strict` in CI.
2. **Unknown-key whole-shape refusal.** At the top of `nextCockpitReadingShape`, `Object.keys(source).filter(k => !NEXT_READING_ASSESSMENT_KEYS.includes(k))`. Non-empty ⇒ return `{malformed: true, unknown: [...], criteria: [], departures: []}`, and `nextCockpitReading` draws the header plus one sentence naming the offending key and **nothing else**. Missing keys are tolerated; unknown keys are fatal. That asymmetry is what keeps the eight existing `CockpitReadingShapeTest` cases and `CockpitHeldToTabTest.test_a_reading_that_read_an_older_revision_says_so` (which injects only four of the seven keys) green.
3. **Unknown-key criterion refusal** — a criterion object carrying a key outside `CRITERION_KEYS` demotes to `not verifiable` with `NEXT_READING_MALFORMED`.
4. **A source-parity contract test** (§7, `ReadingVocabularyIsSpeltOnceTest`) asserting the Python tuples equal the JS literals, the three result sentences appear verbatim, and the JS reads `source.revision_read` and never `source.revisionRead`.

Today `nextCockpitReading` renders the amber stale line only when `shape.revisionRead != null && current != null && revisionRead !== current` (:1437-1441) and `nextCockpitReadingClause` (:1256-1261) falls back to the **current** annotation text when the reading is not historical — so a wrong spelling silently produces a confident reading with no stale line and every criterion captioned with today's typed words. Mechanism 2 turns that into a loud named refusal. Mechanism 1 stops it reaching the wire.

---

## 3. Model prose: exactly one field

**`detail` is the only field a model authors.** Everything else:

| field | provenance |
|---|---|
| `result` | token in, `RESULT_BY_TOKEN` sentence out; miss ⇒ key absent |
| `clause` | copied verbatim from `Revision["goal"]` / `Revision["output"]` (annotations.py:111-114). The model is never shown a slot for it. This also removes a live weakness: the current-annotation fallback at :1258-1260 can no longer mis-caption a historical reading. |
| `cites` | integers in, code-held `fact_id`s out. The model sees `[1] user_message · root transcript · 6h ago · <summary>` and returns `[1,3]`. **It never sees an identifier, so it cannot invent one.** |
| `stamp`, `cutoff`, `scope`, `scope_text`, `revision_read`, `ended_at_read` | measured, or selected from closed dicts |

Bounds and redaction on `detail`:

- `records.safe_text(detail, config.annotation_text_cap_chars)` (240 chars), which is redact-then-clip (`records.py:408-411` → `redact_clip` at :368-405). Applied in `annotations._assessment()` **on the way in and on the way out**, symmetric with `_revision` (annotations.py:163-186) — any local process can rewrite the store file.
- `reading.VERDICT_WORDS` (met, unmet, satisfied, fulfilled, complete, completed, delivered, verified, confirmed, succeeded, failed, passed, passes, done, achieved, proves, proven, correct, incorrect), word-bounded, case-folded. A hit **demotes the whole criterion to `not verifiable` and discards the detail**, with its own `why` sentence. Not a scrub: a scrubbed sentence leaves the claim standing in words nobody wrote. This is a backstop — the primitive is that `detail` renders only on a departure row.
- The list is a guess. It lives as one named constant with the argument beside it so a reviewer can move it in one place.

**`aggregate._RAW_ROW_TEXT` is NOT touched, and that is the decision.** `test_documentation.py:830-835` derives `carriers()` from `_RAW_ROW_TEXT | _RAW_NESTED_TEXT`, and the SECURITY.md clause regex at :840 is `` r"`([A-Za-z_]+(?:\[\]\.[A-Za-z_]+)?)`" `` — it **cannot express a two-deep path** like `annotation_assessment.criteria[].detail`. Adding one there is a regex change plus three byte-identical prose edits (SECURITY.md:1125, SECURITY.md:1592, docs/design-credential-redaction.md:12, bound together by `test_all_three_copies_of_the_list_name_the_same_carriers`) for no safety gain, because the field is already redacted at the store. The nine-carrier count stays nine. SECURITY.md's *Local history* section gains one sentence saying the assessment's only prose field is redacted at the annotation store, in `redact_clip` order, with a test naming it.

---

## 4. What runs the model, and what a missing `codex` says

`observer.CodexGoalModel` (observer.py:162-314) is the only `ModelCaller` in the runtime. **A reading of a Claude Code session is produced by a `codex` subprocess against the reader's own Codex capacity.** This is not papered over: `reading.PROVIDER_NOTE` states it, the offer paragraph names the provider before the first press, and `annotation_reading_count` renders beside the control so the reader watches the spend.

C1 extracts `observer.codex_exec(config, prompt, *, output_cap_bytes) -> str | None` out of `_invoke` (observer.py:216-314), carrying verbatim: `--ignore-user-config`, the sixteen `features.*=false` disables (`_MODEL_DISABLED_FEATURES`, observer.py:54-69), `web_search="disabled"`, `project_doc_max_bytes=0`, `skills.include_instructions=false`, `--model gpt-5.6-luna`, `model_reasoning_effort=max`, `--sandbox read-only`, `--skip-git-repo-check`, `--ephemeral`, `--ignore-rules`, `--output-last-message <tempfile in state_dir>`, absolute-path binary resolution, `stdout/stderr=DEVNULL`, 60 s timeout, tempfile unlinked in `finally`. **Nothing in the suite pins any of those flags today** — I grepped; `tests/test_observer.py` touches only the `--output-last-message` index. C1 adds the argv pin, and that pin is why the extraction is worth doing.

Two deliberate departures from the goal lane:

- **The ledger is assembled incrementally against the byte cap, never post-truncated.** `_invoke` redacts then slices `[:OBSERVER_MODEL_MAX_PROMPT_BYTES]` (observer.py:238-243), which is right for free text and wrong for a numbered menu: a mid-menu cut leaves the model able to cite an index whose row it never saw, and the code would resolve it. `reading.build_prompt` adds entries newest-first while the encoded prompt stays under the cap, records how many it took, and the `cutoff` sentence states that count.
- **A separate in-flight set.** `reading._IN_FLIGHT`, keyed `(os.path.realpath(config.state_dir), f"{harness}:{sid}")` under its own lock — not `observer._MODEL_IN_FLIGHT` (observer.py:46), so a goal refresh and a reading do not block each other and the two spends are countable apart.

**`codex` absent** — `binary_resolver("codex")` returns None or a non-absolute path (observer.py:217-220). That is a **withhold**, not a failed reading: nothing is stored in the assessment slot, `reading_count` is **not** incremented, and `annotation_reading_withheld` carries `WITHHELD["model-unavailable"]`: *"The Codex CLI was not found on this machine, so no reading was made. A reading is produced by a `codex` subprocess whatever harness the session runs on."*

A model call that *started* and then failed (non-zero exit, timeout, unparseable output) is different: the capacity was spent, so `reading_count` **is** incremented and `annotation_reading_withheld` carries `WITHHELD["model-failed"]` — *"The reading did not complete. Nothing was produced, and a fresh press is the only retry."* No automatic retry anywhere (DEC-17).

The disclosure is **new and is not the observer's**. `observer_model.disclosure` names transcript excerpts and a goal summary; a reading additionally sends the reader's own composed prose. `reading.DISCLOSURE` is a separate constant published beside `reading_check` in `Application.collect` (aggregate.py:775-780) and shown before the first press. This is the item most likely to be dropped in implementation.

---

## 5. The withhold arm

`reading.end_kind(row)` mirrors `nextObservedLanding` (next-observed.js:45-48) exactly, so the reading and the HOW IT LANDED cards cannot disagree:

```
ended_at > 0                                  -> "session-end"
state == "idle" and finished_at > 0           -> "turn-stop"
state != "idle"                               -> "running"
scan-only acquisition                         -> "unobservable"
otherwise                                     -> "idle-unknown"
```

**Produce:**

- `running` ⇒ `scope="mid-flight"`, `scope_text = "This covers only the work so far. The session is still running, so nothing here is a reading of how it ended."` (The first sentence is byte-identical to today's, which keeps `CockpitHeldToTabTest.test_a_reading_before_the_end_says_what_it_covers`'s `running` half green.)
- `session-end` **and** `now - ended_at >= config.reading_settle_sec` **and** the latest revision's `at <= ended_at` ⇒ `scope="final"`, `ended_at_read = ended_at`.

**Withhold** — nothing enters the assessment slot; `annotation_reading_withheld` gets a code-owned sentence from `reading.WITHHELD`, a closed dict:

| reason | sentence |
|---|---|
| `turn-stop` | "A turn stop was observed and no session end was, so there is no end for a reading to rest on. Nothing partial is offered instead." |
| `idle-unknown` | "This session is idle with no stop and no end observed, so whether there is finished work to read is unknown rather than none." |
| `unobservable` | "No event from this harness can reach this row, so no end can be observed and no reading can rest on one." |
| `settling` | "This session ended moments ago and its record is still settling. Ask again in a few seconds." |
| `revision-after-end` | "You saved these words after this session ended, so there is no work after them to read them against." |
| `ledger-empty` | "No entry in the observed record names this session, so there is nothing to read your words against. Absence of evidence is not a reading." |
| `record-unread` / `record-error` / `record-partial` | three sentences, not one — `nextCockpitWorkAbsence` (next-cockpit.js:962-980) already established that folding these makes the least true read as the most reassuring |
| `model-unavailable` / `model-failed` | §4 |

**How a withhold differs visibly.** It renders as a single `next-cockpit-reading-why` paragraph under the READING header — italic secondary ink, the third register. It draws:

- **no** `next-cockpit-reading-row`, so no `next-cockpit-reading-result` `<em>`, which is the only element in which the three verdict sentences can appear (:1332);
- **no** `next-cockpit-reading-clause` mono span (:1319-1324), the register reserved for words a person typed;
- **no** stale line and no stamp;
- the offer control **stays on the page**, with the count beside it, so the reader can press again;
- and `nextCockpitDepartures(null, …)`, which says *"No reading has been made, so nothing has been raised"* — **not** *"The reading raised no departure from the revision it read."*

**Codex.** No special case. `SessionEnd` is absent from `CODEX_EVENTS`, so `ended_at` is permanently null and every idle Codex row lands on `turn-stop` or `idle-unknown` and withholds; a running Codex session still reads mid-flight. The criterion is written; the gap closes itself when the capture-gated commit wires `SessionEnd`. The `unobservable` sentence names the harness rather than implying the session did not end.

**Withdrawal** is a publish-time derivation in `_attach_annotations` (aggregate.py:507-551), never a stored fact, so it self-corrects: if `scope == "final"` and the row's current `ended_at` is None or ≠ `ended_at_read`, the published `scope` becomes `"withdrawn"` and `scope_text` becomes *"The session end this reading rested on is no longer published, so its claim to be final is withdrawn."* An `ended_at` that returns restores finality on the next collection.

**History off.** `--no-history` does **not** delete the assessment: it lives in the annotation store, which is bounded by counts with no TTL (annotations.py:18-20, config.py:660-663) and survives a restart. So the note is narrow, and I am flagging it against the captain's wording rather than smoothing it: *"History is off for this run, so nothing about this reading enters the history record. The reading itself is kept with your words until you clear them."* A literal "nothing can be retained" would be false. If the captain meant the broader claim, the sentence changes and nothing else does.

`reading.NO_READING_YET` ("No reading has been made…") and `reading.HISTORY_OFF_NOTE` are asserted **unequal and both reachable** — "nothing retained" and "nothing to retain" never render alike.

---

## 6. Commit plan — five commits, strict order, each independently green

### C1 — `refactor(observer): one bounded codex exec, and the first test that pins its flags`
Files: `cargento_runtime/observer.py`, `tests/test_observer.py`.
Extracts `observer.codex_exec()`; `CodexGoalModel._invoke` becomes its first caller with no behaviour change. Adds `CodexExecArgvTest` asserting the full argv (see §7).
**Inverts nothing.** No user-visible change, nothing new called ⇒ self-verify review depth (AGENTS.md, Calibrating Effort).

### C2 — `feat(reading): the evidence ledger and the shape rules, with no caller`
Files: **new** `cargento_runtime/reading.py`; `cargento_runtime/config.py`; `scripts/validate_plugins.py`; `docs/design-runtime-architecture.md`; **new** `tests/test_reading.py`.
Contents: `RESULT_*`, `RESULTS`, `RESULT_BY_TOKEN`, `CONSTRAINTS`, `ASSESSMENT_KEYS`, `CRITERION_KEYS`, `VERDICT_WORDS`, `WORK_EVIDENCE_HARNESSES = ("pi",)`, `SCOPE_TEXT`, `WITHHELD`, `NO_READING_YET`, `HISTORY_OFF_NOTE`, `DISCLOSURE`, `PROVIDER_NOTE`, `Criterion`/`Assessment` TypedDicts, `author_of`, `build_ledger`, `end_kind`, `eligibility`, `build_prompt`, `parse_reply`, `resolve`, `_IN_FLIGHT`, `CodexReadingModel`.
Two new `config.py` fields only — `reading_settle_sec = 8.0` and `reading_ledger_max_entries = 40` — in one block, because `config.py` is a named conflict hotspot. `detail`'s bound reuses `annotation_text_cap_chars`; the prompt bound reuses `OBSERVER_MODEL_MAX_PROMPT_BYTES`; the per-entry summary clip is a module constant in `reading.py`.
**`reading.py` MUST be added to `CARGENTO_RUNTIME_FILES` (scripts/validate_plugins.py:132) in this commit** — `scripts/tests/test_validate_plugins.py:106-112` rglobs `cargento_runtime` for `.py` and asserts set equality. Miss it and `scripts.tests.test_validate_plugins` is red on the first run.
**Inverts nothing.** Nothing imports the module.

### C3 — `feat(annotations): a reading may be stored beside the revisions`
Files: `cargento_runtime/annotations.py`, `cargento_runtime/sessions.py`, `cargento_runtime/aggregate.py`, `tests/test_annotations.py`, `tests/test_sessions.py`, `SECURITY.md`.
`Annotation` gains `assessment: NotRequired[Assessment]`, `readings: NotRequired[int]`, `withheld: NotRequired[str]`; `_assessment()` validator (drops the object **whole** on any failure, refuses bools before ints per `_revision`'s discipline at annotations.py:173-176, `safe_text` on `detail`, unknown keys dropped, `result` confined to `RESULTS`); `record_reading()` and `record_withheld()` written but uncalled; `published()` emits `assessment` (None), `reading_count` (0), `reading_withheld` (""); `annotate()` carries the assessment forward as it carries `settled` (annotations.py:488-490); `clear()` deletes it, which the docstring at :583-586 already promises.
`sessions.base_session` declares the three new keys beside `annotation_settled_revision` (sessions.py:542). `_attach_annotations` gains the withdrawal derivation.
**Inverts:** `tests/test_sessions.py:41` `DECLARED_SESSION_FIELDS` (+3 names) — that is a fixture edit, and `PublishedSessionFieldSetTest.test_every_published_session_row_declares_the_same_field_set` (:1360-1375) and `CargentoServerTest` (:837) both go red until it is made.
Every published value is None/0/"" and nothing produces one ⇒ green.

### C4 — `feat(http): POST /api/reading, gated no looser than the observer model`
Files: `cargento_runtime/http_api.py`, `cargento_runtime/reading.py` (the model lane wiring), `tests/test_http_api.py`, `tests/test_history.py`, `tests/test_documentation.py`, `SECURITY.md`.
**Placement, non-negotiable:** define `_reading` immediately **after `_annotate` (http_api.py:1133-1229) and before `_events` (:1230)**. `test_documentation.py:2042` slices `source[index("def _focus(self)") : index("def do_POST(self)")]` and asserts `"reason":` does not appear in it. `_focus` is at :1276 and `do_POST` at :1349, so a handler written in the natural place — at the end of the POST group — lands inside that slice and the reply's `"reason"` field turns a green test red for a reason about the focus route.
**Ruff:** `http_api.py` has **no** `C901`/`PLR0912`/`PLR0915` exemption in `pyproject.toml` (the list at lines 55-92 covers cli, config, records, transcripts, turns, claude_data, spacedock, lifecycle, notifications and five collectors, and `select = ALL` is on). So the gate goes in `_reading_refusal(self, payload) -> tuple[int, str] | None` and `_reading` stays a short caller. That also makes every gate condition unit-testable without a socket.
**The gate**, in order — nine conditions against `_project_context`'s five (http_api.py:690-711):
1. `_local_ok()` (already run by `do_POST` at :1351).
2. `config.annotations_enabled` else 503 — `_annotate`'s reason at :1153-1156.
3. `config.observer_model_enabled` else 503 (`--observer-model` / `--no-observer-model`, cli.py:200/205).
4. `annotations.ABSTENTION_CHECK == ABSTENTION_CHECK_PASSED` else 503. **On this branch the constant is `not-run` (annotations.py:74), so the route always refuses here and a local `curl` cannot outrun the check.** Button and route are gated by the same constant, so they agree by construction. The abstention check itself must drive `reading.produce()` through the Python API, never through the route.
5. `not self._is_document_navigation()` **and** `self._loopback_resource_ok()` (:529-535). A lured navigation reads nothing back but would still spend the reader's capacity.
6. `payload["observer_model"] == 1` — the page's per-press disclosure echo, the same token `/api/project-context` requires.
7. `payload["press"] is True` — DEC-17's "asserted rather than assumed", made mechanical. The literal appears in exactly one place in `next-cockpit.js`, inside the click listener, pinned by a source test. Nothing on render, poll, reconnect, resume, focus change or revision save has it.
8. `harness` and `sid` are non-empty strings naming exactly one row in the current collection; `project` is read off that row, never off the body. **No 404 on a miss** — `_focus`'s ruling (a harness name is public, a session id is not); an unknown session answers 200 `{"ok":true,"produced":false,"why":...}`.
9. One in flight per session, `reading._IN_FLIGHT`; a second press answers **409** and calls nothing.
No `coordinator.authorized` capability — that would take `test_documentation.py:1975`'s `assertEqual(2, gated)` to 3 and falsify "Two carry a capability and they are not worth the same." The precedent that fits is the quota fetch: harm is a side effect on the reader's own capacity, held by `_loopback_resource_ok` plus the navigation refusal. The accepted exposure (a local process with no fetch metadata can spend one reading) goes in SECURITY.md.
Handler work: `application.collect_json(show_all=False)` for the row → `project_context.collect(..., refresh=False, focus=(harness, sid), model_consent=False)` for `semantic.facts` (verified: `refresh` only reaches the observer snapshot's own model call, so this costs no second model call) → `reading.produce()` → `annotations.record_reading()` / `record_withheld()` → `state.snapshot.clear()` (`_annotate`'s reason at :1216-1218).
**Inverts:** `test_history.py:976` `assertEqual(9, len(routes))` → 10; `test_documentation.py:1974` `assertEqual(10, routes)` → 11; SECURITY.md:1667 "Writing is the ten POST routes" → eleven; SECURITY.md:1669 "nothing to authenticate with on eight of them" → nine. `assertEqual(2, gated)` unchanged.
Green, and the producer is genuinely reachable — every test drives it with `ABSTENTION_CHECK` patched to `passed`.

### C5 — `feat(next): wire the reading control, and narrow what a reading may render`
Files: `cargento_runtime/web/next-cockpit.js`, `tests/test_next_cockpit.py`, `tests/test_next_page.py`, `tests/test_next_flag.py`, `tests/test_focus.py`, `tests/test_contracts.py`, `docs/design-reader-state.md`, `docs/design-reading-a-session.md`, `HOW_TO_USE.md`.
The only commit that touches `web/`, so **one** byte-pin round. Nine JS changes:
1. `NEXT_READING_ASSESSMENT_KEYS` / `NEXT_READING_CRITERION_KEYS` and the two unknown-key refusals.
2. `detail` keyed on the **final** result, not the declared one — fixing a live defect: `detail` is set unconditionally at :1226 and rendered whenever truthy at :1332, so a declared `departure` demoted by rule 3, 5, 7 or DEC-16 currently prints its departure prose under the demoted result.
3. `nextReadingAuthor(entry)` → `"person" | "agent" | "derived"`; `derived` is `type === "observer_snapshot"` (which covers all three `_OBSERVER_ACTOR_CLAIMS` values, project_context.py:2187-2191, not just the `model-derived` prefix the current `modelDerived` flag catches at :976). A result other than `not verifiable` resting **only** on `derived` cites demotes, on **both** constraints. Derived entries stay citable — they are real evidence of what the session said — they just cannot carry a result alone.
4. `narration` split in three, because today's *"Rests on the agent's own account alone."* (:1227-1228) is **false** for an observer snapshot, and false in the flattering direction: agent-only keeps today's sentence; agent-plus-derived gets *"Rests on the agent's own account and Cargento's derived summary of it, and on nothing a person wrote."*
5. `scope_text` from the reading replaces the `provisional` block keyed on `observed.landing.endKind` (:1431-1435); `observed` drops from `nextCockpitReading`'s signature and its call site at :1629.
6. The withheld arm, reading `annotation.reading_withheld`; `reading_count` and `reading_withheld` added to the field list at :64-65.
7. `nextCockpitReadingControl(session, annotation)` hoisted out of the `if(!raw)` branch so **the control and the count render whether or not a reading exists**. Today `reading-ask` is rendered at :1416 inside that branch alone, so once any assessment is stored the button disappears — DEC-17's required count could only ever render as 0, and a reader staring at the amber "revision 3 is current" line would have no way to ask for a current reading.
8. `nextCockpitDepartures(shape, workSource)` with the third state (§9).
9. The `reading-ask` dispatch arm beside `conflict-settle` (:2548-2561) and `async nextCockpitAskForReading(session)`, shaped on `nextCockpitConflictSettle` (:1661-1681): POST once, `await refreshNext()`, on any failure `renderNext()` with a per-session mark and **no retry**.
**Recompute all five byte pins from the assets:** `tests/test_next_page.py:686-713` (per-part size and digest for `next-cockpit.js`, plus the assembled length 799_998 and digest), `tests/test_next_flag.py:67-70` (assembled length **and** digest, in the same test), `tests/test_focus.py:1011-1014` (assembled digest). Two assertions pin the length and three pin the digest; recomputing only the first leaves CI red on the other two.
Run the `sync-docs` skill last so doc updates land on this branch.

---

## 7. Test plan

Each row: the class it lands in, the fixture it needs, the mutation it must catch.

**A. `CodexExecArgvTest` — new class in `tests/test_observer.py`.**
Fixture: a fake `runner` capturing `argv`, `binary_resolver` returning `/usr/bin/codex`, `make_config(observer_model_enabled=True)`. Mutation: dropping `--sandbox read-only`, `--ignore-user-config`, `--ephemeral`, or any `features.*=false` from `codex_exec`. **Today nothing in the suite catches any of those** — a second model lane that quietly dropped the sandbox would ship green.

**B. `ReadingVocabularyIsSpeltOnceTest` — new class in `tests/test_contracts.py`,** beside `AnnotationFieldCollapseTest` (:673), using the same idiom (`frontend_page.WEB_DIR / "next-cockpit.js"`, no fixture). Four assertions: `set(reading.ASSESSMENT_KEYS)` equals the JS literal; same for `CRITERION_KEYS`; the three sentences in `reading.RESULTS` appear verbatim; the JS reads `source.revision_read` and never `source.revisionRead`. Mutation: rename a key on one side only.

**C. `test_a_python_produced_assessment_renders_its_stale_line` — `CockpitRecheckFindingsTest` (tests/test_next_cockpit.py:5441),** which owns `FIXTURE = NextCockpitCompositionTest.FIXTURE` and its own `run_fixture` (:5452-5456), and whose `test_the_rendered_tab_resolves_a_citation_older_than_the_window` (:5520) is today the **only** site that walks row → `nextCockpitAnnotation` → `nextCockpitReading`.
Fixture: build a real two-revision annotation in Python, call `annotations.record_reading()` then `annotations.published(entry)`, and `json.dumps` the **produced** value into `__dashboard.sessions[0].annotation_assessment` — never a hand-written literal. All fifteen existing fixture sites hand-write the snake key, which is exactly why they would stay green.
Mutation: emit `revisionRead`, or a string, or omit the key. Two of the three then also trip test D.

**D. `test_an_unknown_key_refuses_the_whole_reading` — new `CockpitReadingRefusalTest` in `tests/test_next_cockpit.py`.** Copy `FIXTURE` and the three-line `run_fixture` from `CockpitReadingShapeTest` (:4771-4788); a class without it inherits nothing usable. Feeds `{revisionRead:1, criteria:{goal:{result:"departure", cites:["u1"], detail:"x"}}}` and asserts the rendered HTML contains the refusal sentence and the literal `revisionRead`, and contains **neither** `departure` **nor** `consistent with the evidence read`. Mutation: revert the key filter — the page then renders a full confident reading, which is the measured silent failure.

**E. Seven rule tests + the ledger tests — `tests/test_reading.py`, new module, own `TestCase`, own builders, inheriting nothing** (deliberate: `test_annotations`' classes are revision- and settlement-shaped, and a text-anchored test landing in the wrong class is how two tests on this branch went green without running).
- token `met` ⇒ `result` key absent (rule 1/2)
- `departure` with `cites:[]` ⇒ unverifiable; with `cites:[99]` ⇒ unverifiable (rule 3)
- `detail` containing "delivered" ⇒ whole criterion demoted, detail dropped (rule 4)
- harness `claude` ⇒ `output` never appears in the prompt **and** is emitted unverifiable (rule 5)
- reply carrying a single blended verdict ⇒ both criteria unverifiable (rule 6)
- `output` with only agent cites ⇒ unverifiable; `goal` departure on agent cites ⇒ stands (rule 7)
- **the derived column:** `author_of` over all three literal `_OBSERVER_ACTOR_CLAIMS` strings; a result resting only on `derived` demotes on both constraints
- **`test_the_ledger_is_bounded_before_it_is_printed_never_after`:** entries exceeding the cap; assert the prompt contains no partial row and the highest citable index equals the number of rows printed. Catches a post-truncated menu, which resolves an index the model never saw.
- `parse_reply` returns objects whose keys are exactly `{result, cites, detail}` — a reply carrying `clause`, `stamp`, `cutoff` or `revision_read` has all four dropped.
- `end_kind` and `eligibility`: the settle window, `revision-after-end`, a Codex row with null `ended_at` withholding with the harness sentence.

**F. `TheReadingEndKindMatchesTheLandingAxisTest` — new class in `tests/test_next_observed.py`,** subclassing `NextPageJsHarness`. Runs `nextObservedLanding` in node over the matrix (idle/working/needs_input × `ended_at` set/null × `finished_at` set/null × scan-only/event) and asserts each `endKind` equals `reading.end_kind` on the same row. Without it the withholding ruling rests on two independent derivations that can disagree **silently**: the server withholds while the card next door says the session ended.

**G. `StoredAssessmentTest` — new class in `tests/test_annotations.py`, with its own `setUp`** building a tmp `state_home` and config. Covers: a malformed assessment drops **whole**, never partially; a bool where an int is declared is refused; `annotate` carries it forward while minting a revision; `clear` deletes it; **an `AKIA`-shaped value in `detail` comes back masked at a length that would have cut it** (redact-before-clip); `reading_count` increments on a stored reading and on a `model-failed` withhold, and does **not** on any other withhold.

**H. `ReadingRouteTest` — new class in `tests/test_http_api.py`.** Copy `_runtime`, `_serving` and `_post` from `AnnotateRouteTest` (:2717-2757) and retarget `_post` at `/api/reading`; do **not** land inside that class — it builds an annotations-only application with no observer model, so a reading test placed there would 503 forever and read as a pass. Nine subtests, one per gate condition, each asserting the status **and that the injected model runner recorded zero invocations**. The zero-invocation half is load-bearing: a gate that answers 503 after spending the reader's capacity has not held. Plus: two concurrent presses ⇒ one 200, one 409, exactly one invocation; an unknown session ⇒ 200 with `produced:false` and never 404.

**I. `test_the_reading_arm_exists_unconditionally` — added to `ReadingControlIsWiredTest` (tests/test_contracts.py:709).** One line: `self.assertEqual(set(), unwired_cockpit_actions(source, reachable=True))`, unconditional. Today the inventory test discards `reading-ask` while `ABSTENTION_CHECK` is `not-run` (:670-672), so on this branch it would pass with no arm at all. The synthetic-source sibling at :745-771 needs no change — verified, it builds its own strings and never reads `next-cockpit.js`.

**J. `test_the_annotation_field_list_is_derived` — new class in `tests/test_documentation.py`.** Parses the `fields = [ … ]` array literal out of `nextCockpitAnnotation` (next-cockpit.js:64-65) and asserts it equals `set(annotations.published(None))`. That array is a three-defect site and every defect was the page reading a field nothing publishes. **It fails today** (`assessment` is in the JS, absent from Python), so it lands in C3 with the field.

**K. `test_a_turn_stop_withholds_a_reading_and_says_why` — REPLACES `test_a_turn_stop_is_not_a_session_end_for_the_reading_scope` in `CockpitRecheckFindingsTest` (tests/test_next_cockpit.py:5577-5618).** Renders with `annotation.reading_withheld = WITHHELD["turn-stop"]` and no assessment; asserts the sentence renders, **no** `next-cockpit-reading-result` element renders, the offer control still renders, and the departures block says "No reading has been made". **Keep** the existing assertions that `nextObservedLanding` still reports `endKnown` for both events (:5615-5617) — the change narrows what the READING keys on and must not rewrite HOW IT LANDED.

**L. `test_the_departures_block_says_which_kind_of_nothing_it_means` — `CockpitReadingShapeTest` (:4760),** which owns `ENTRIES` (:4772-4784) and `run_fixture`. Four cases against `nextCockpitDepartures`: no reading; a malformed reading; a reading whose criteria are all `not verifiable`; and a work source in state `unread`/`error`. Assert four **distinct** sentences and that only the genuinely-clean case says "raised no departure".

---

## 8. Every existing test I expect to go red, and why

| Test | Commit | Why | Action |
|---|---|---|---|
| `tests/test_sessions.py:41` `DECLARED_SESSION_FIELDS` (via `PublishedSessionFieldSetTest:1360`, `CargentoServerTest:837`, and `test_history.py:442-444`'s subset oracle) | C3 | three new published names | add the three names |
| `tests/test_documentation.py` `TheAnnotationRebuildListIsDerivedTest` (new, test J) | C3 | it fails today because `assessment` is in the JS and not in Python | lands with the field |
| `tests/test_history.py:976` `assertEqual(9, len(routes))` | C4 | tenth exact POST route | → 10 |
| `tests/test_documentation.py:1974` `assertEqual(10, routes)` | C4 | eleventh counting the `/api/events/` prefix | → 11 |
| SECURITY.md:1667 "Writing is the ten POST routes" (pinned at test_documentation.py:1976) | C4 | prose count | → eleven |
| SECURITY.md:1669 "nothing to authenticate with on eight of them" (pinned at :1977) | C4 | prose count | → nine |
| `tests/test_next_page.py:686-713` — per-part size+digest for `next-cockpit.js`, assembled length, assembled digest | C5 | `web/` changed | recompute from the assets |
| `tests/test_next_flag.py:67-70` — assembled length **and** digest | C5 | same | recompute |
| `tests/test_focus.py:1011-1014` — assembled digest | C5 | same | recompute |
| `tests/test_next_cockpit.py:5577` `test_a_turn_stop_is_not_a_session_end_for_the_reading_scope` | C5 | the captain's withholding ruling deletes the surface it asserts | **rewritten** as test K, keeping its `endKnown` half |
| `tests/test_next_cockpit.py:4646` `test_a_reading_before_the_end_says_what_it_covers` | C5 | `scope_text` comes from the reading, not the live row, so a stored mid-flight reading keeps saying "covers only the work so far" after the session ends; its `ended` assertion currently expects False | flip `ended` to True with the reason — a reading describes the moment it was taken |

**Expected to stay green, verified by reading them:** all eight cases in `CockpitReadingShapeTest` (:4791-5040) — they call the shape function with subsets of the key set, and refusal is on *unknown* keys only; `CockpitHeldToTabTest.test_a_reading_that_read_an_older_revision_says_so` (:4679) — `stamp` and `cutoff` survive as producer-composed strings, which is the main reason this design does not delete them; `test_a_reading_with_no_departure_still_states_its_cutoff` (:5691); `test_the_rendered_tab_resolves_a_citation_older_than_the_window` (:5520) — its assessment uses two known keys and its cite is a `user_message`; `ReadingControlIsWiredTest` (:709) in both branches after C5; the carrier count of nine at test_documentation.py:836 and all three prose copies.

---

## 9. The thing all three proposals missed, and its fix

`nextCockpitDepartures(shape)` prints *"The reading raised no departure from the revision it read."* (next-cockpit.js:1379-1381) whenever `shape.departures` is empty. `departures` is `criteria.filter(row => row.result === DEPARTURE)` (:1285). So it prints that sentence when every criterion was demoted, and — worse — when the page could not resolve a single citation because its own project-context fetch has not landed: `nextCockpitWorkSource` returns `{entries: [], state: "unread"}` or `{state: "error"}` **with no `all` key** (:893-895), and the caller passes `workSource.all || workSource.entries` (:1615). On that redraw every criterion demotes under rule 3 and a stored reading holding two real departures renders as "raised no departure", with its own cutoff line underneath vouching for how many entries it read.

The tree has been bitten by this class once already — the comment at :899-907 records the 20-row display window doing exactly this, fixed by passing `all`. The residual is untouched, and this PR is what finally makes the sentence reachable in earnest.

Fix, in C5: `nextCockpitDepartures(shape, source)` with five states — no reading (today's sentence); malformed shape ("A reading was made and this board could not read it, so nothing here is raised"); `source.state !== "read"` ("The observed record is not on the page right now, so the entries this reading cited cannot be resolved and nothing can be raised from it"); every criterion unverifiable ("This reading verified neither constraint, so it raised nothing and confirmed nothing"); and only then today's sentence.

---

## 10. Deferred, one line each

- **History admission of the five `assessment_*` names.** DEC-15b's own change: `history.observation()` (history.py:199-241) returns a fixed eight-key dict with no conditional omission, and `test_the_declared_field_tuple_is_what_a_record_actually_has` (test_history.py:458-464) plus `test_the_record_keeps_only_fields_the_board_already_publishes` (:446-452) together require five **new flat published row fields** before the store can hold them.
- **`PROMPT_TEXT_ALLOWLIST` entries for the assessment.** Nothing enters the store, so nothing needs one. `history.PROMPT_DERIVED_CARRIERS` gains `annotation_assessment` in C3 as a declaration only.
- **A Claude-side model lane.** `CodexGoalModel` is the only `ModelCaller` in the runtime; a second provider is a separate capture-gated commit.
- **Codex `SessionEnd`.** Absent from `CODEX_EVENTS`, so `ended_at` is permanently null; the final-reading criterion is written and the gap closes itself when the capture-gated wiring lands.
- **A stable `fact_id` for observer snapshots.** `_semantic_id("observer", harness, sid, observed_at, goal)` (project_context.py:2205-2211) rehashes on every refresh for **all three** actor claims. Mitigated here — a derived-only citation can never carry a result anyway, so losing one can only demote something already demoted — not fixed.
- **Persisting `detail`, `clause` and `cites`.** A retained reading answers "did it depart", not "how". That is DEC-15b's own scope.
- **Asynchronous production.** The handler blocks up to 60 s, as `_observe` already does. A job id plus a poll route buys a second state machine, a new GET route, and an orphaned-job class for a press the reader is sitting in front of.
- **Enabling the control.** `ABSTENTION_CHECK` stays `not-run` (annotations.py:74). What ships is a producer the check can be run against — which is what the check needs and cannot be run without.

---

## 11a. Settled 2026-09-10, before C2: the ledger derives in Python

Section 11 below asked whether `reading.build_ledger` can reproduce
`nextCockpitWorkEntries`, and named taking the entry list from the page as the fallback. Settled by
reading both sides:

`nextCockpitWorkEntries` (next-cockpit.js:954-977) is a pure transform over `semantic.facts` that
reads only `fact_id`, `type`, `by`, `summary`, `at`, `actor_claim`, `evidence.source`,
`evidence.confidence` and `source_session.{harness,sid}` — every one of them a field
`project_context` already puts on the fact dict (project_context.py:1981-1989, :2209-2218). The
filter is `source_session.harness:sid` equality (:555-560) and the sort is ascending `at`. A Python
reconstruction over the same list is the same data, not a second derivation of it.

The genuine risk is narrower than section 11 states, and it is not about the transform: it is
**which collection**. `nextCockpitWorkSource` prefers the focus-scoped fetch where it has landed and
falls back to the project-scoped one (:891-895), so the page can be looking at a different
collection from the one the producer read seconds earlier. When that happens the model cites a
`fact_id` the page cannot resolve, rule 3 demotes it, and the reader gets an abstention nothing on
screen explains.

**That case is already closed by section 9's third state** — the `source.state !== "read"` arm and
the all-unverifiable arm both render a sentence naming the reason. No further work, and no fallback
to page-supplied entries.

The parity test in section 11 is still written, as a guard rather than as a gamble.

## 11. Riskiest assumption, and how to settle it before C4

**That `reading.build_ledger` (Python) reproduces `nextCockpitWorkEntries` (next-cockpit.js:955-983) exactly** — the same session-key filter, the same ascending sort by `at`, the same `id` from `fact_id`, and the same `source` composed as `evidence.source · evidence.confidence`. If any of those diverges, the model cites an id that resolves in the producer and not on the page, rule 3 demotes it, and the reader sees a reading that abstains for a reason nothing on screen explains. It fails toward safe, so review will not catch it — it will just quietly make the feature useless.

I checked the half I could without running anything: `_semantic_fact_from_event` hashes `fact_id` over `raw_kind`, harness, sid, `at`, workflow binding, entity, lineage and title (project_context.py:1970-1979), all stable across two collections of an unchanged transcript. I did **not** verify that a Python reconstruction of the `source` string agrees for every fact type, nor that the focus-scoped and project-scoped contexts produce the same fact set for one session — `nextCockpitWorkSource` prefers the focused fetch **where it has landed** (:891-895), so the two derivations can be reading different collections seconds apart.

**Settle it in C2, before writing C4.** Build a fixture with one fact of each `_SEMANTIC_FACT_TYPES` value (project_context.py:69-80) plus one observer snapshot, drive it through `reading.build_ledger` in Python and `nextCockpitWorkEntries` in node, and assert the `(id, type, source, author)` tuples are equal set-wise. It needs `NextPageJsHarness`, so it lands in `tests/test_next_cockpit.py` beside `CockpitReadingShapeTest` (:4760), **not** in the pure-Python `tests/test_reading.py`.

If it cannot be made to pass: the producer stops deriving entries, and **the route takes the offered entry list from the page** as untrusted input bounded by count and per-field cap, so there is exactly one derivation and a citation resolves against the list the reader is actually looking at. The tree already argues for that at next-cockpit.js:874-877 ("a citation resolves against the same list the reader can see rather than against a second collection assembled from the same facts"). That is a C5-shaped client change, so decide it before C2 rather than after the PR opens.

Second, smaller, and also a guess: `config.reading_settle_sec = 8.0`. The measurement behind it is 5.581 s for the slowest clean end; the headroom for at-least-once reordered delivery is my judgement, not a measurement, and the comment must say which half is which.