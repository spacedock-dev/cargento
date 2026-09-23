# Issues that carry a Design reference

Load this only when an issue in the group has a `## Design reference` section. Inside it is a
`### Prompt to use` heading with a fenced block beneath it. That fence is an instruction, not an
illustration, and both are part of the issue's plan.

## Planning

If the design-project read is unavailable, leave these issues out of the plan and say so in the plan
block. Discovering the refusal while understanding the issue wastes a deep dive, and discovering it
while building wastes a layer. Authorization is typically a slash command, which a dispatched agent
cannot run, so an agent that hits a refusal hands it back to the operator.

## Understanding

- Read the files the section names before any markup is written, and before the Mode 1 walk: the
  criteria that walk produces govern markup that the build then checks against the design's copy.
  The section names the tool, the project and the exact files, and it carries a dated staleness
  check because the design lives outside this repository and is editable. Run that check rather
  than trusting the paths.
- Hand the fenced prompt verbatim to whatever writes the code, including yourself. It is written to
  stand alone in a session with no other context. Summarizing it defeats the point.
- The section carries its own precedence rule for the issue, the design and the repository. That
  rule governs. Do not invent one, and do not assume the design wins because it is more specific.
- A difference between the surface today and the design is the work, not a defect for either walk
  to file. Mode 1's hard rule is never to promote a finding into the branch, and this is the one
  exception, because here the gap is the issue's scope. Tell it so when you invoke it. The exemption
  reaches only what the design deliberately changes: something the design does not address is still
  a defect.
- A design defect the issue does not take up is out of scope: file it. Where the issue does take one
  up, it is the work. Read the issue before filing anything the design confesses to.
- An issue with no Design reference has none. Do not borrow a sibling's.
- A section missing its file list, its precedence rule or its staleness check is incomplete. Name
  the missing part and hand it back rather than filling the gap.

## Building

`visual-review-and-fix` has no design step and is never handed the reference, so carry the design's
copy and its states into the Mode 2 walk yourself and check them there. A string the design
specifies and the build paraphrases is a finding, because the copy on these surfaces is what says
how far the evidence goes.

Never write markup for such an issue without having read what the section names. An implementer who
skips it ships a surface that looks finished and matches nothing.
