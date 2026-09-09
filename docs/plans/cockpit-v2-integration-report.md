# Session F integration report

Branch: `proto/operator-cockpit`. Starting commit: `7b50d8b`. Changes are committed locally;
nothing was pushed, merged or rebased in this session.

The dashboard suite is green: **2,668 tests, two skips**, up from **2,648** before edits.
The 20 added tests are 11 observer-consent cases, eight reader/navigation cases, and one vendor
asset oracle. Collection was checked through the test edits; no existing tests disappeared.
The repository script modules also pass: **408 tests, one skip**.

## Failures and expectation changes

The first full dashboard run took 54.454 seconds and reported nine failures:

| Failure | Cause and resolution |
|---|---|
| `test_documentation.ReaderStateInventoryTest.test_only_the_documented_terminal_adds_a_scroll_container` | The substrate now uses `overflow:auto`, and the canonical reader-state document already said so. Updated both the declaration set and the selector oracle from `scroll` to `auto`; it still requires exactly one declared scrolling container, the terminal. |
| `test_focus.CapabilityDeliveryTest.test_the_pinned_assembly_is_untouched` | Stale assembled digest. Recomputed from the actual assets. |
| `test_next_flag.DefaultPageRoutingTest.test_the_canonical_loader_is_the_released_ui_bundle` | Stale assembled length and digest. Recomputed both. In this checkout these two assertions are in the same test. |
| `test_next_page.NextPageAssetContractTest.test_load_page_preserves_its_byte_oracles`, three part subtests | `project.js`, `next-project.js` and `next-cockpit.js` changed during the preceding sessions. Recomputed every APP_PARTS size and digest, including the parts changed here. |
| That same oracle, stylesheet assertion | Stale stylesheet length and digest; regenerated these and the assembled pair reached afterward. |
| `test_project_scope_tree_is_left_at_wide_width_and_stacks_when_narrow` | RC-2 superseded the 180–230px rail and 760px scope breakpoint with a 264px rail and a switcher below 1280px. Updated those expectations. A later full run exposed the next stale assertion in this test: RC-3 now pairs Going on and How things ended in equal columns, replacing the old 2:5 split. Updated that expectation too. |
| `test_the_next_palette_is_dark_only` | The test demanded temporary prototype colors which A2 removed. Removed the temporary exception and strengthened the retired-token check to cover the entire stylesheet. |

The intermediate full run collected 2,668 tests and had only the equal-column expectation failure
(62.647 seconds). The final full run passed in 65.505 seconds. No HTTP, lifecycle or quota module
failed in any full run, so none required a load-related isolated retry.

During implementation, regression tests first failed for the real defects listed below. Two old
tripwire tests then caught duplicate caret restoration introduced by the new focus lane; the lane
now restores once, and their expectations stayed unchanged. The documentation inventory check
also caught the two new input-state functions before their inventory row was added. No assertion
was weakened to hide a behavior failure.

Static checks initially caught an unsorted test import, formatting in two edited test files, and a
Unicode apostrophe in a test literal. These were corrected; the apostrophe test uses a Unicode
escape and still compares the exact rendered text. An extra script-discovery attempt failed
because `scripts/tests` is a namespace directory, not an importable discovery start with `-t .`;
loading all 11 `scripts.tests.test_*` modules explicitly ran all 408 tests successfully.

## Sweep findings and fixes

- Context text autosaved, but redraw discarded its keyboard focus and caret. Chrome measured
  focus moving to BODY and the selection changing from 4–8 to 0–0. Named input restoration now
  preserves focus, caret and internal scroll. A separate input-state lane retains scroll, caret
  and resized dimensions even after focus leaves the input. Final Chrome measurements preserved
  4–8, an 80px focused scroll, a 120px unfocused scroll and a 100px resized height.
- Escape in human context did nothing, and Escape on Done navigated away. Both now cancel the edit,
  restore the value from when editing began in memory and browser storage, and close the editor.
  Tripwire cancellation remains covered by its existing behavior tests.
- More, project plan, raw status, earlier Course rows and other directions lacked restoration keys.
  They now retain disclosure state. Project-level substrate disclosures previously had no key
  without a selected session; they now use a project key and retain summary focus. The canonical
  reader-state inventory includes these lanes. Selection over rendered text remains deliberately
  unmanaged, as the contract requires.
- Single-session projects intentionally collapse the scope rail. Their Console nevertheless asked
  readers to select an exact session without offering a link. It now offers “Open this session’s
  console.” The rendered href is tested and the link was followed in Chrome to the exact-session
  terminal explanation.
- Shared-label caveats, tool-failure explanations, ending outcome sentences and the command status
  sentence used accent tints. They now use neutral ink. Status glyphs, border cues and measured
  quota/progress marks retain their encodings; no tinted panel background was found. `--accent-dim`
  remains allowed. The final rendered sweep across projects, sessions, attention, session detail
  and all four cockpit tabs found no small sans body sentences or tinted body sentences in the
  forced waiting/ended/missing-data fixtures. The remaining standalone em dash is an aria-hidden
  sentence separator, not an absent value.
- Three older history-renderer helpers still contained dash placeholders. They now say “Current
  activity not observed,” “No current step observed,” and “Current block state not observed.”
  Counted zeroes and sorting sentinels remain measurements or internal bookkeeping; no unknown
  value rendered as a bare zero was found in the reviewed states.
- RC-12's backend was hardened but its consent UI was explicitly unfinished. Console now reuses
  the quota consent pattern with separate observer consent and an explicit Summarize action.
  Granting consent alone and passive panel refreshes send no model request. It displays the exact
  session's returned goal and model status. Two new race tests caught a passive response replacing
  a newer explicit result; passive loads now wait during a model request and unique request
  identities invalidate older replies.
- RC-11 vendor pins were missing. Added size and SHA-256 checks for xterm JS, CSS, license and
  provenance file. All four are already present in `CARGENTO_RUNTIME_FILES`; vendor bytes were
  neither downloaded nor changed.

New observer absence/state reasons are: “Observer model availability has not been read,”
“Observer model is disabled for this run” with both enable/rollback flags, “Select one exact
session to request an optional model goal summary,” “Observer disclosure is unavailable; model
requests are withheld,” “The requested model summary is in progress,” “The summary request failed.
Local analysis remains available,” “Model summaries are off in this browser,” “Model status was
not published,” and “No goal summary was published by this refresh.” The disclosure itself comes
from the backend; it is not a second hand-maintained copy. The UI also explains that consent alone
sends nothing, that model failures fall back to local analysis, and that credential redaction does
not remove private prose.

## Verification and limits

All requested checks passed: `ruff check .`, `ruff format --check .`, `mypy`,
`lint_embedded.py`, `validate_plugins.py`, `bump_version.py --current` (0.23.0), and the full
dashboard unittest suite. All repository script tests passed separately. The RC-8 modules are
included in the full dashboard suite. Forty-three focused backend security/documentation checks
also passed for asset gating, observer consent/redaction, dispatch ownership/mode/symlink/bounds,
absolute Spacedock resolution, registration permissions and bounded read-only streaming.

SECURITY's input-read inventory was independently re-derived from the merged runtime:
`claude_data.py` 1, `collectors/codex.py` 1, `project_context.py` 3, `transcripts.py` 2:
**seven expressions across four modules, unchanged**. No version field changed.

Navigation tests derive destinations from rendered HTML for cards, rows and chips; `p`, `s`, `a`
and Escape are exercised through the assembled event handlers. The existing waiting-session
briefing tests pass. Chrome showed the waiting session in COMMAND above the tabs. At 1280px,
rail links measured 252px inside the 264px column and showed both harness and usable title text.
At 1100px the scope switcher replaced the rail. At 390px the expanded switcher stayed readable
and document width equalled viewport width: 390px. Captures are in the gitignored
`docs/screenshots/session-f-1280-waiting.png`, `session-f-1100-scope.png` and
`session-f-390-scope.png`.

Firefox/Safari, an actual external observer call and a live registered tmux stream were not
exercised. Their boundaries were tested locally with fixtures; no session content was sent to a
model during verification. The temporary Chrome fixtures and review servers were cleaned up.
The documentation's existing qualifications about document-scroll clamping remain intact.

Nothing remains red.

## Final byte pins

Every row below was recomputed from local bytes. Font pins were also exercised by the passing
asset suite; their files were unchanged. The assembled size and digest agree at every pin site.

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `next-boot.js` | 22,576 | `758106a0d2b488ad589e4f74aeced032284d62850ec5f9003013f04d16b592f7` |
| `next-observed.js` | 26,473 | `24821122e96cc1cf412e2613adc77c07b31919ac790894209677b19d26d03b6e` |
| `next-attention.js` | 56,348 | `2ca8f16c43783c74d21e22aae8adf3099187bdd2a67754ba5e918060c0a75184` |
| `next-notify.js` | 6,457 | `19430b5fbe080dc13f43ee5c714a1da453dd0ff4b82f1abaeecce105cb373a06` |
| `next-cockpit-compat.js` | 599 | `ebc70801be79cd5805a85a281dd0566a08a97bab72d0356ae923d20f60310db4` |
| `project.js` | 105,499 | `563db97a7f62d06acaf33da4fa37619ba12501194ad0ff003e8db409ae276943` |
| `next-chrome.js` | 37,051 | `e7ba0644817abdbb6e6730dda7f1c7cd6d58a189c0578bb1884286b0ce738320` |
| `next-capacity.js` | 32,192 | `fccfae64553820ba7da58439694808fdae9275bba00f4d85119db58d36d0ef6b` |
| `next-sessions.js` | 19,745 | `dbb317ce92bf0bd2b5121b43ab50cbe8878f8712fcfa51581a5b01cb87527f4e` |
| `next-projects.js` | 4,186 | `0e270a7cecb33368ed71876fae7493104fe29027b695e100e6f24b5527820e0b` |
| `next-project.js` | 13,397 | `08d06ee829b8d01f71bfb066eb0df08be67c22c4fd191ca14ad4ab258dea44b1` |
| `next-activity.js` | 6,632 | `62f971c5e2a570068b7e2c3ee72b2499774d14a3b739f6f908962f91b98382f1` |
| `next-session.js` | 20,189 | `74458dc9744c6718f964b0db1b7befcee870d6fb58bb8837f7ece6a9af1271fb` |
| `next-workstream.js` | 18,659 | `9680ee01d19296e87cf9b35230a51a7e98ddc764c5bfb80f0e18e7723ece8a04` |
| `next-delegation.js` | 14,508 | `36ecd098147995ae96b5ca7846c6a4366142da400a27a2dd5dfcef9ace01fdb6` |
| `next-controls.js` | 11,563 | `838fd2f076ebd1da0c97dc5f937f43d51435bc12d901f2a5d1136bcafa8987a7` |
| `next-cockpit.js` | 81,068 | `3c9a44d271e9a1c7059bc76f106fe40f38b5d851c650d55d186681df94ae9339` |
| `next-render.js` | 8,630 | `efe65035d6af60cfdfd5e5e87e2f6dcd8757286b7bf81ee36f6624098da52cbc` |
| `next-live.js` | 3,375 | `4883888e27c3cded21d3bfeb1862b3a9555c8e39316cd53bcaf9a3c31341bb64` |
| `styles.css` | 88,784 | `7be9f66fac3848fecefa5ad3b701431f5dca489ee8cc7c324394a94c02e7acc0` |
| `vendor/xterm.js` | 488,663 | `14903579ff54664cd72f8e8699e6961a6272c21863ec1c3b118cdc8af5d4a972` |
| `vendor/xterm.css` | 7,112 | `854a7c0fb70e8b1a083c16797ab827299fb18744f5ad34f227b48337e33293c6` |
| `vendor/xterm-LICENSE.txt` | 1,261 | `b569f629d00f2626a8100df2a1798210535621e42164dfd426a6fe5aac7b0ccd` |
| `vendor/SOURCES.txt` | 534 | `426b3d3a2288c8f88c9b960b5089294aa35c7e77a84969650633669b884e2e45` |
| `assembled` | 704,375 | `0ba93cf91b90b61a0bc932c65fe527b4879afb209a678596f369e6bc87200da8` |
