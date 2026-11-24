---
status: draft
reason: ""
depends_on:
  - failures/failures.md
reviewed:
  hash: ""
  deps: {}
sources: []
approvals: []
---

# Failure Mode and Effects Analysis (FMEA)

This worksheet is a view over the failure documents in this folder: one row per analysed
failure mode and cause. The failure documents stay the source; when they change, this
worksheet is regenerated.

## Scope

[To be determined. The system, release or part covered, the functions analysed, and what is
left out.]

## Scales

[TBD — the severity scale used (Critical, High, Medium, Low, as in the failure documents).
When scores are on: the 1–10 scales for severity, occurrence and detection, with what each
band means for this project, and how the priority number is used.]

## Worksheet

[TBD — one row per failure mode and cause.]

<!-- Row format (scores off):
| ID | Function | Failure mode | Effect | Cause | Current controls | Severity | Recommended action | Owner | Source |
| FM-001 | Save an entry | Entry lost on reload | The person loses their list | Storage write fails silently | Write result checked; error shown | High | Add a storage self-check at start-up | [owner] | [failure-01-lost-entry.md](failure-01-lost-entry.md) |

With scores on, replace Severity with: S | O | D | RPN, and add after Owner: S' | O' | D' | RPN'
(the scores expected once the action is done).
-->

## Actions

[TBD — the recommended actions in the order they should be done, each with the rows it
covers, its owner and its state (planned, in progress, done).]
