# DRC-4271 (DEC-7) — triage evidence probes

Three read-only probes behind the tables in `../drc-4271.md`. They re-derive the figures rather
than accept DEC-7's body, which this workflow wrote on 2026-08-28 and which is therefore not an
independent source.

Run from the skill root so `cargento_runtime` imports:

    cd cargento/skills/cargento
    python3 <path>/probe_distribution.py   # turn-duration distribution
    python3 <path>/probe_coverage.py       # ETA coverage, and how it is biased
    python3 <path>/probe_max_error.py      # the maximum D6 would publish, vs the truth

**The numbers are machine-specific and the method is not.** All three read the live
`~/.claude/projects` store, so another machine re-derives its own figures from its own history.
That is why none of this is committed as a unit test: a test pinned to one machine's session
history asserts the fixture, not the behaviour.

`probe_distribution.py` and `probe_coverage.py` call the shipped scanner (`turns.scan_turns`) and
replay `turn_progress`' own rule, so they cannot drift from the implementation.
`probe_max_error.py` rebuilds absolute turn intervals using the same boundary signals
(`records._turn_signal`, `records.parse_ts`, `config.turn_gap_reset_sec`) because `scan_turns`
publishes durations without their wall-clock positions.
