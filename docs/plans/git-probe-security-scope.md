# Git probe security scope (DRC-4274)

This is the security contract for the end-of-session git probe decided in DEC-3 (Linear DRC-4122),
written before the probe exists so the implementation PR is held to a published standard.
SECURITY.md describes shipped behaviour only, so the section lives here until the code lands.

The probe PR (DRC-4037) must do three things with this file: promote the section below into
SECURITY.md unchanged, apply the two intro amendments listed after it, and delete this file.

## The section, verbatim

The following lands in SECURITY.md between "Project reads (Spacedock stage strips)" and "Usage
quota reads (the quota fetcher)". It contains no relative links on purpose, so it can move without
rewriting.

---

## Repository git reads (the end-of-session probe)

One feature runs a program inside a directory the user chose. Cargento already records each
session's working directory; when a session ends, the server runs one bounded git command there, so
the board can show that a session stopped with work still in the tree.

The probe is exactly this command, or there is no probe:

    git -c core.fsmonitor= --no-optional-locks status --porcelain

The mechanism is subprocess execution rather than a file open. That is what separates this feature from
every other read Cargento performs, and both flags are load-bearing. Measured 2026-08-28 at git
2.55.0 across four fresh repositories, one probe each, from an identical racy-clean state:

- Without `--no-optional-locks`, the probe writes `.git/index`. The write is git resolving a racy
  stat, not a per-invocation habit, and a repository a live session is editing is the normal case
  for it rather than a corner case.
- Without `-c core.fsmonitor=`, a `core.fsmonitor` script configured in the repository is executed
  under Cargento's identity. A repository can carry that setting in from wherever it was cloned.

Each flag disarms one of those hazards and neither disarms the other's, so neither may be dropped.
There is no fallback to a plain `git status`.

What is published, per session, is two fields and nothing else:

    {dirty: bool | None, changed: int | None}

Both fields are nullable, and `null` means not probed. It is never a confident clean over no evidence.
The probe fires on `session_ended`, and most harnesses do not emit that event today, so most rows
carry `null`. `changed` counts porcelain entries rather than files: git collapses an untracked
directory into a single entry, so a new directory holding three files is one entry, not three.

What is never read:

- File contents, of any file, at any point.
- Diffs and blobs. Nothing asks what changed inside a file, only that something did.
- Branch and upstream state of any kind. The branch name, its tracking branch, and how far ahead or
  behind it sits are all outside this feature.

Porcelain output names paths. Those pathnames are matching hints and are never echoed to
`/api/data`, the same rule and the same wording this document applies to `cwd`.

The cadence is one-shot, on the `session_ended` edge. Never a poll, never on demand, and never on a
turn stop: the completion stamp written when a turn stops is a different edge, and probing there
would put one subprocess in the user's repository per turn for the life of the session.

The off switch is `--no-git`. The probe is on by default and that flag turns it off. It mirrors
`--no-spacedock` at every one of that flag's sites, including the branch that forwards flags to a
respawned daemon, so a restart cannot re-enable a probe the user disabled. With the probe off no
git command runs at all, and both fields stay `null`.

A violation of any boundary in this section is a security bug: a git command other than the one
above, either flag dropped, a read of file contents or diffs or branch state, a pathname reaching a
response, a probe on any edge but session end, a probe while the feature is off, or any write inside
the user's repository.

---

## Intro amendments that ride with the promotion

Scope closes by enumerating the ways an invariant can be weakened, and every entry in that sentence
is a file read, a write to a harness store, or a network destination. Subprocess execution inside a
user's repository is none of the three, so as written the sentence does not reach the section above.
Promoting the section without this amendment files it under a clause that does not cover it.

Two sentences elsewhere in SECURITY.md change in the same PR, and only these:

1. Scope's closing sentence gains one clause, after "writes to harness stores,": "running any
   program inside a user's repository other than the probe described in Repository git reads (the
   end-of-session probe),". The sentence keeps its existing final clause about the hook client.
2. Invariant 2, "Read-only against harness stores.", gains one sentence at the end: "The git probe
   runs inside a repository the user chose rather than a harness store, and it neither writes there
   nor executes anything the repository supplies."

No count in SECURITY.md changes. The probe adds no forwarder, no endpoint, and no outbound request;
the network posture described in Scope is untouched.

## What else the build PR does with this file

- `SKILL.md` gains a `--no-git` row in the flag table.
- The section above is promoted unchanged and this file is deleted, both in that same PR. Leaving
  the file in place states the contract in two places and lets them drift.
- How the porcelain output is parsed into the two fields belongs in the design doc that accompanies
  the implementation, not here. This section fixes what may be run and what may be published, not
  the parse.
