# Design: credential redaction in published text

Owner for why the dashboard replaces credential-shaped text before it renders, how the shape list was
measured, and which alternatives were tried and rejected. The module map lives in
[`design-runtime-architecture.md`](design-runtime-architecture.md); the security posture and the
residual exposure live in [`SECURITY.md`](../SECURITY.md).

## The problem

A harness transcript records what the operator typed, verbatim. Cargento reads those transcripts and
publishes prompt text: the session title, the line beneath it, `last_prompt`, the observer goal, and
a Codex title, which comes from a prompt because Codex writes no generated title at all. If a key was
ever pasted into a prompt, the store holds it and the dashboard shows it.

This is not hypothetical on the machine the feature was built on. A sweep of the local Claude store
found seven distinct live Anthropic credentials sitting in ordinary prompt history, in three formats
(`sk-ant-api03-`, `sk-ant-oat01-`, `sk-ant-ort01-`). The operator chose not to rotate them, so the
runtime keeps reading them on every scan.

Loopback does not help. The dashboard is what someone opens to show a colleague what their agents are
doing, so the exposure is the screen and the screenshot, not the network.

## How the shape list was measured

The rule that shaped the whole exercise: measure by counting, never by reading. The investigation
that found the problem wrote prompt corpora to disk and copied the credentials into fifteen files as
a side effect, turning one exposure into many. So every figure below came from a script that emits
counts, filenames, match lengths and character classes, and has no code path that prints a matched
string.

The corpus is the whole local store the collectors themselves read: 12,685 transcripts (12,228 Claude
`projects/**/*.jsonl` plus 457 Codex `rollout-*.jsonl`), 1,982,123 records. Two figures come out of
it for each shape, and they answer different questions. The first says whether a shape exists on
this machine at all. The second, the last column, says what the dashboard actually publishes today:
a genuine prompt is a user record that `records._turn_signal` reads as a prompt and
`records.injected_prompt` does not reject, which is the gate the instruction line already uses.
There are 21,076 of those, and 13 of them carry a credential shape.

| Shape | Anywhere in the corpus | Files | In genuine prompts |
|---|---|---|---|
| `urlcred` (`://user:password@`) | 1,572 | 251 | 4 |
| `pem` (private-key header) | 1,058 | 46 | 0 |
| `jwt` (three base64url segments) | 852 | 126 | 0 |
| `phc_` (PostHog) | 507 | 343 | 2 |
| `AKIA` / `ASIA` (AWS) | 246 | 50 | 1 |
| `sk-` (OpenAI) | 99 | 14 | 2 |
| `sk-ant-` (Anthropic) | 89 | 35 | 1 |
| `sk_live_` / `rk_live_` (Stripe) | 74 | 19 | 0 |
| `gh[pousr]_` (GitHub, legacy) | 57 | 17 | 5 |
| `xox` / `xapp-` (Slack) | 22 | 3 | 2 |
| `glpat-` (GitLab) | 16 | 3 | 0 |
| `npm_` | 12 | 4 | 0 |
| `AIza` (Google) | 0 | 0 | 0 |
| `github_pat_` (GitHub, current) | 0 | 0 | 0 |

Every PEM match is header-only: all 1,058 are the `-----BEGIN … PRIVATE KEY-----` line with no base64
body behind it, which is what a guidance list naming the shape looks like. The `AIza` prefix appears
45 times across 22 files with no 35-character body after it, for the same reason.

## C-1: Redact in place, keep the surrounding words

Dropping the line loses the instruction, and the instruction is why the line is on the card. A prompt
that pasted a key almost always says something around it, so `rotate ghp_…REDACTED then push the
branch` is a useful row and a blank one is not.

## C-2: The marker is visible on purpose

A silent scrub protects the screenshot and tells the operator nothing. Someone who sees
`sk-ant-…REDACTED` on their own card learns that their prompt history holds a live key, and that is
the only route by which it gets rotated. The marker keeps the prefix that names the kind, so it says
which credential to go looking for.

The prefix is a fixed number of leading characters per shape, not a guess at where the secret starts.
`sk-ant-` keeps 7 and stops short of the `api03` / `oat01` / `ort01` discriminator, which would have
been more useful to the operator and is one more character of a live value on a screen.

## C-3: One list, two application points

The filter is one measured list in `records.redact_secrets` and it is applied in exactly two places.

Inside `records.safe_text`, because that is the bound nearly every published untrusted string already
passes through: the title, the instruction line, the observer goal, model names, tool names, the
notification body, and the ask question and its options, which the HTTP ingress bounds through it
because `asks` is a leaf that cannot reach `records` itself. Nothing had to opt in.

Over the assembled rows in `aggregate._redact_published_text`, because `title` and `last_prompt` are
the two published strings that never reach `safe_text`. Nine collectors build them out of the
transcript by hand and bound them with a slice, which is how `last_prompt` came to be published raw
in the first place. Nine call sites would be nine chances for the tenth harness to be forgotten, so
the sweep runs once over every row from every harness. Task subjects go through the same sweep: an
agent's todo written from a prompt that held a key can quote it.

A guard at each render site was rejected for the reason the second paragraph gives. The set of render
sites is a list, and a list is a thing the next feature forgets to join.

## C-4: Redaction runs before the bound, not after

A key cut at a 140-character cap is still a hundred usable characters of key, and a shape whose tail
fell off no longer matches, so bounding first publishes exactly the values the filter exists to
catch. `safe_text` therefore scrubs control characters, redacts, and truncates, in that order.

A control character struck through the middle of a key defeats the match in either order. That is a
limit of shape matching rather than of the ordering, and it is in `SECURITY.md` with the rest of the
residual.

## C-5: The token anchor is checked in the replacer, not written as a lookbehind

Ten of the fourteen shapes have to start a token, or `dask-` followed by a long hyphenated identifier
reads as an OpenAI key. The obvious spelling is a `(?<![A-Za-z0-9_-])` lookbehind on each
alternative, and it was measured and rejected: a leading lookbehind leaves no literal for `re` to
build its first-character skip from, and the substitution cost on a 140-character line goes from
21.5 us to 36.5 us. The check moved into the replacement function, which sees the match offset and
the source string, and every alternative now opens with a literal.

The anchor is not cosmetic. A hyphen counts as inside a token, and that one decision rejects 78 of
the 177 `sk-` candidates in the local store: 177 is what a rule that treats a preceding hyphen as a
boundary finds, and 99 is what the shipped rule finds.

## C-6: The gate, and what it costs

`safe_text` is a hot path. A literal substring scan runs before the alternation, and the alternation
runs only if one of the shape prefixes is present, or if the text holds both `@` and `://`. Measured
per call:

| Input | Before | After | Alternation with no gate |
|---|---|---|---|
| 4-character tool name | 366 ns | 412 ns | 461 ns |
| 22-character model id | 529 ns | 967 ns | 3,214 ns |
| 140-character prompt line | 1.70 us | 3.49 us | 23.2 us |
| 2,000-character observer blob | 18.9 us | 46.6 us | 321 us |

End to end that is a whole collection moving from 32.3 ms to 33.9 ms, a 4.8% cost, on
`scripts/bench_collect.py --simulate balanced-five --repeat 7`.

Two details of the gate are measured rather than chosen. The five GitHub prefixes are spelled out
instead of gating on `gh`, which appears inside "highlight" and "tonight" and put ordinary English on
the slow path. And `://` is not a gate literal on its own: it is paired with `@`, because the
dashboard's own address (`http://127.0.0.1:4553/api/data`) is in prompts constantly and a bare `://`
gate would send most of them through the alternation for nothing.

An optimization in front of a security filter is a way to ship a measured shape switched off, so
`RedactSecretsTest` asserts every alternative is still reachable through the gate.

The alternation was checked for backtracking blowup on adversarial input, since it runs over
untrusted text. The worst of eight probes (4,000 characters of near-miss AWS prefixes) takes 0.62 ms,
and the `://user:password` shape with an `@` sitting before the scheme rather than after it takes
0.51 ms on 3,000 characters. Nothing here is quadratic in a way a prompt could exploit.

## False positives, and the two thresholds they set

Of the 21,076 genuine operator prompts, 13 are altered (0.062%). Classified by the structure of the
match, never by reading it:

- Seven carry a value with a credential's format and a credential's length, at an assignment or
  inside quotes: one Anthropic key of 108 characters, three prompts holding five GitHub tokens of 40,
  two PostHog keys of 47, and one prompt holding two Slack tokens. Redacting those is the filter
  working.
- Two carry one repeated 42-character all-lowercase hyphenated identifier that opens a token with
  `sk-`. Those are false positives.
- Four carry a short `://user:password@` run of 6 to 16 characters, all lowercase, three distinct
  values. Whether any of them is a real password cannot be decided without reading it, which was not
  done. One of those four also carries the documented AWS placeholder `AKIAIOSFODNN7EXAMPLE`, which
  is definitely not a secret.

So the honest reading is seven correct, three wrong, three unjudged. Two thresholds came out of it.

The OpenAI body requires 32 characters rather than the 20 the format needs. At 20 the filter alters
25 further genuine prompts, and every one is a hyphenated identifier. 32 does not clear the two
above; requiring an uppercase character in the body would, and that was rejected too, because
OpenRouter spells its key `sk-or-v1-` followed by 64 lowercase hex and the rule that fixes two
prompts loses a vendor.

The PEM body class excludes the space that `\s` would have allowed. With `\s` a prompt that merely
names the header swallows the rest of the sentence; without it, a header with no key behind it costs
one word.

Four candidates that look like credentials and must survive are pinned as tests: a 40-character hex
git SHA, a UUID, a base64 blob in a pasted diff, and a long absolute file path. So are the dashboard's
own URL, a scp-style git remote, a URL with a user and no password, and a `postgres:16` image tag.

## What this does not buy

A shape list covers the formats it was measured against. A credential in a format nobody has seen
goes through unmarked, and a filter that misses gives false confidence, which is worse than no filter
for anyone who trusts it. Two of the fourteen shapes are on the list with a count of zero for exactly
that reason: `github_pat_` is the token format GitHub issues today, and shipping only the legacy
`ghp_` spelling would have been the false confidence in miniature.

The rule outside the software is unchanged. Do not paste a credential into a prompt, and rotate one
that was.
