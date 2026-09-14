## Stage Report: review

Verdict: **REJECTED / NO-GO**. PR https://github.com/spacedock-dev/cargento/pull/335; head `735785dd3699df01d2ec1b7dbd7de1fa9bbaa66e`; base `4b2120dac7dfe0ca63ebe8c5fc7f28d8d4fc1801`; MERGEABLE / BLOCKED, not CLEAN.
Depth: full adversarial security review retained from three independent lenses, completeness critic and reproducing arbiter; one fresh reviewer used, zero additional workers, no candidate edits or repeated owned suites.

- DONE: Independently account for all six approved ACs using the actual candidate and boundary evidence, with the required security lenses and reproducing arbitration completed before opening the PR.
  Five SHA-verified candidate-qualified artifacts and production diff cover all six; AC-2 scheduling proof and AC-6 Windows containment remain unfulfilled as detailed below.
- DONE: Read current-head CI and all top-level/Copilot inline comments, investigate new findings read-only, and route any owned material correction with its evidence and proposed disposition.
  All 12 check-run head SHAs match; Windows and quality-gate fail; top-level reviews and inline comments are both empty, including Copilot; FO authorized the one owned Material fix.
- DONE: Report GO or NO-GO with exact PR/head/mergeability, review evidence, actual surface, checklist accounting and safe worktree/merge handoff state.
  NO-GO; correction package below preserves scope and thresholds; worktree remains clean and required for correction, so removal and merge are not ready.
Checklist totals: DONE 3; SKIPPED 0; FAILED 0 review tasks. Acceptance proof: AC-2 partial and AC-6 failed on Windows; this accounting does not claim passing CI.

### Acceptance evidence and limits

AC-1: lens1 verified both real shape-capture hashes against recorder originals and harmless success/failure driver outputs; actual-hook replay covers Bash/tool_input.command. Claude PostToolUseFailure is excluded; Codex success/failure share PostToolUse. No live calls repeated here or successful-effect claim made.
AC-2: lens1's 41 actual-hook cases and 19 ingress refusals, lens2's authenticated refusals, and arbiter's eight hook-to-HTTP-to-reader cases prove fixed six-field/private-sentinel boundaries locally; Windows test_irreversible.py:223 misses four positive reports, so supported-platform socket scheduling evidence is not green.
AC-3: lens3 executes both assembled routes, escapes hostile owner text and distinguishes absence/off/unsupported states; retained Mode 2 live drive proves routing/redraw/focus. Fresh reviewer inspected corrected Attention/session and unsupported screenshots; this is retained browser evidence, not a new browser walk.
AC-4: lens2 compares 1,530 deliveries to an independent ordering/cap oracle (1,000 global, 20/session), checks concurrent/end survival and actual history exclusion; lens3 proves 27 retained/20 displayed; critic serves orphan reports then exact 24h expiry. Logical/current-run retention, duplicates and collection-paced redraw remain explicit limits.
AC-5: lens2 and arbiter exercise malformed/missing/off enablement, stale-on/off HTTP rejection and fresh-off matcher suppression; authored listener replacement and real spawn argv through child parser/config prove off propagation. No detached OS daemon respawn was independently launched; approved enabled-replacement race remains.
AC-6: lens1 separately measures actual sleep/spin exit and completed-late-success suppression; GIL-regex negative control times out. Current-head Windows sleep subprocess exceeds the authored 250ms startup-inclusive window, so supported-platform containment is unproved; nominal 5ms and 250ms limits remain unchanged.
Artifacts: /tmp/spacedock-dispatch/drc-4025-review-{lens1,lens2,lens3,critic,arbiter}.md; all five SHA-256 values match drc-4025-review-manifest.json and head 735785d. Zero pre-PR findings; one new current-head CI proof finding.

### Current-head finding and authorized correction

F1 released user/workflow: Windows operator receives admitted Bash after-tool command reports through the normal hook process.
F1 observable harm: four documented positive socket cases fail and actual sleep-hook exit proof times out; the required supported-platform quality gate blocks delivery. This does not establish a lexical product defect or universal scheduling failure.
F1 affected boundary: value-ac[AC-2] positive/private-byte socket evidence; value-ac[AC-6] actual-hook 250ms supported-CI containment; contract[AGENTS.md#quality-gate] required platform checks must pass.
F1 trigger: run 34847818390/job 103988008758 on the exact head, test_irreversible.py:223 missing sqlite3 DROP, rm -Rf, Codex rtk psql DROP and Codex rtk proxy rm -fR reports; line 327 raises subprocess.TimeoutExpired(0.25) for forced sleep. 3,384 tests / 191.518s / four failures / one error / 45 skips; Windows script tests never ran.
Materiality: Material proof failure. Ownership: C6 implementation. Proposed disposition: fix; distinct FO authorization received before any candidate mutation or reviewer rerun. No extra security lens or arbiter needed for the observed CI assertion; cause remains to be isolated.
Diagnosis: run_hook includes Python/import startup before main, while its 250ms parent timer starts before process launch. The 90-positive matrix also conflates fixed lexical/socket correctness with the production daemon's intentional total-start/join-over-5ms discard. Neither causal explanation is proved by the Windows log alone.
Authorized assignment: isolate startup/import, actual-main, matcher/result and process-exit phases with bounded diagnostics; correct the platform/oracle boundary. A readiness handshake may exclude interpreter/import setup only if actual main, daemon worker and real process exit remain inside unchanged 250ms and the excluded startup cost is reported separately. Deterministic socket scheduling/clock control may isolate lexical/private-byte proof only; retain separate unmodified nominal-5ms discard, completed-late-success suppression, sleep/spin shutdown and rejected GIL-regex proofs. Do not delete Windows coverage, weaken positives, raise caps or change production thresholds; run required changed-boundary checks and current-head CI, then return to this reviewer.
Correction inputs: `drc-4025/correction-inputs/review-1/briefing.json` and `briefing.review.jsonl` in the state checkout; rejected snapshot `drc-4025/review-rejected-735785d.md`. The log deliberately awaits implementation's disposition and closing Resolution; FO alone records review/1 after correction. No gate prepare or round record ran here.

### CI, surface and safe handoff

Checks: ten success, two failure, all at 735785d. Quality Gate run 34847818390: lint, mypy, Python 3.11 floor, coverage (86.5%), Ubuntu and macOS pass; Windows and aggregator fail. Validate 34847818269, compatibility smoke 34847818259 and version guard 34847818420 pass. Local 86.7% coverage is distinct from CI's 86.5%.
Raw current-head evidence: code-worktree ignored docs/screenshots/c6-fresh-review/{windows-failure.log,checks.json,reviews.json,inline-comments.json}; actual job summaries were read, not merely check badges.
Surface independently recomputed: runtime 13 files/514 changed lines vs 11–14/450–850; support 17/688 vs 12–15/500–950; docs 7/186 vs 4–6/100–200. Over upper file estimates: support 13.3%, docs 16.7%, within 25%; all LOC ranges satisfied. Total 37 files, +1,255/-133, two DCO commits. ACs unchanged.
Tracked candidate worktree clean; no review server, harness, test suite or daemon launched. Preserve this worktree for correction, PR 224 and sibling work. No merge, branch removal, main reset or Linear update. FO owns eventual merge/removal/reconciliation ordering.
State transport: FO authorized id drc-4025 plus folder-form index.md migration and only the consumed triage room-ref relocation. Old gate identities/digest/approval/application and all room bytes are preserved; status --validate is the shipped validator. The requested gate validate CLI does not exist (exit 2), so no such pass is claimed.

### Summary

Fresh review confirms the retained independent security and reader evidence but rejects this head because Windows leaves required C6 proofs and CI incomplete. Implementation receives one authorized correction with unchanged scope and thresholds; the reviewer remains addressable for the corrected head.
