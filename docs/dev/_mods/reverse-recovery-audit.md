---
name: reverse-recovery-audit
description: "Brownfield shape/plan mindset: assume the abstraction already exists, classify it with evidence (5-tier), and only greenfield what is confirmed MISSING"
version: 0.1.0
---

# Reverse-Recovery Audit — Assume It Exists, Prove What's Missing

> Adapted from the qnow development workflow for Cargento. Keep Cargento
> examples here rather than changing the generic rule below.

## Why This Exists

In a brownfield codebase, the default planning instinct — "the feature doesn't
work, so plan to build it" — is systematically wrong and expensive. It
produces duplicate implementations beside broken-but-present ones, misses
one-line wiring fixes disguised as features, and inflates a one-seam repair
into a broad rebuild. Cargento is a compact codebase with shared behavior
across several harnesses, so recovering the existing seam is normally cheaper
and safer than introducing a parallel launcher, parser, or install path.

## The Rule

**Before planning ANY capability as new work, run the reverse-recovery audit:
assume the abstraction already exists, hunt for it, classify it with
evidence, and only greenfield what is confirmed MISSING.**

### 5-tier classification (evidence ladder)

| Tier | Meaning | Minimum evidence |
|------|---------|------------------|
| `WORKING` | works end-to-end | behavioral E2E (API-level or browser) or a runtime walk — **unit tests alone never qualify** |
| `WORKING_UNIT_UNPROVEN` | logic tested, wiring unproven | unit tests pass, no seam proof |
| `EXISTS_BROKEN` | implemented but fails | concrete defect evidence: broken wiring, contract mismatch, swallowed error/rejection path, failing runtime probe |
| `STUB` | abstraction only | type/contract/route/page skeleton with placeholder logic |
| `MISSING` | no abstraction | exhaustive search came up empty (see below) |

### Discipline

1. **Layer-trace before classifying**: UI entry → API contract → handler →
   domain logic → persistence/projection → UI readback. Record file:line per
   layer or the literal `MISSING`. One broken layer ≠ MISSING — it is
   EXISTS_BROKEN at that seam, and the fix is scoped to that seam.
2. **MISSING requires proof of absence, not absence of proof.** Search domain
   nouns in every language the codebase uses, across contracts, routes,
   domain types, and UI surfaces, with at least two search strategies before
   writing MISSING. "Not found after one grep" is the easiest false claim.
3. **Every non-runtime classification carries a `disproof_hook`** — the one
   command or observation that would flip it. The audit stays
   self-correcting instead of authoritative.
4. **Unit tests prove logic, never wiring.** Silent-failure architectures
   (event-sourced rejection-as-event, schema-boundary stripping, CQRS
   projection lag) fail BETWEEN tested units; seam claims need runtime or
   E2E evidence.
5. **Boundary conditions.** Greenfield domains take no search tax — the rule
   is "prove MISSING before building", not "never build". And
   cheapest-literal recovery is a scope tool, not an architecture tool: when
   a recovered abstraction fights the domain model, escalate to a redesign
   decision instead of contorting the old shape.

### Where it binds

- **shape stage**: frame the entity around recovered capability + named gaps,
  citing existing abstractions by file:line, not around "build X".
- **plan stage**: every task that creates a new file/domain/route MUST carry
  a classification line justifying why recovery was impossible (MISSING with
  search evidence). Plan reviewers reject greenfield tasks without it.
- **any "build/add/implement X" request**: run the audit for the touched
  capability before writing the plan.
