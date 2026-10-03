---
name: run-health
description: Keep long autonomous repository work bounded, observable, and recoverable. Use as a supporting skill for substantial implementation, CI/review repair loops, or web/cloud runs that risk appearing stuck, repeating work, or losing durable progress.
---

Use this skill alongside the task-specific workflow. It does not replace `work-github-issue`, staged feature work, `investigate-ci-failure`, or `land-prs`; it constrains how long-running work proceeds.

## Boundary

- Follow `AGENTS.md` and the task-specific skill/agent ownership.
- Do not invent artificial work merely to produce progress updates.
- Do not loop indefinitely on an unchanged failure, pending review, unavailable environment, or repeated tool error.
- Durable repository state is preferred over invisible conversational state.
- CI failures and review findings are actionable evidence, not automatic reasons to hand control back to the user.
- Repository lifecycle actions remain owned by the primary user-facing thread: specialists do not create branches, commit, push, open/update PRs, or trigger reviews unless their owning workflow explicitly says otherwise. Specialists return a bounded implementation/diagnostic packet to the primary thread.

## 1. Establish a bounded run

At the start of substantial work, identify:
- one concrete current objective;
- the current branch/PR/issue or other durable work object;
- the owner/skill for this packet;
- the next validation gate;
- explicit stop conditions.

If the requested work is too broad to define one bounded objective, size/decompose it before implementation.

## 2. Persist progress early

For non-trivial code work, the primary thread should:
- use a short-lived branch;
- once there is a meaningful coherent implementation, commit it;
- open a draft PR early enough that branch, SHA, CI, comments, and status become externally observable;
- keep PR/body/handoff current enough that another run can resume from repository state rather than reconstructing a hidden plan.

A specialist working inside that lifecycle should make only its owned repository edits/validation and return its completed packet to the primary thread; it must not create a competing branch or PR.

Do not push broken speculative micro-edits solely for visibility; persist coherent checkpoints.

### Durable autonomous-run checkpoint

When a primary web/chat run is expected to continue automatically after an external
GitHub event, maintain exactly one top-level PR comment containing a machine-readable
checkpoint:

```text
<!-- agent-run-health {"mode":"active","phase":"ci","expected":"ci","head_sha":"<40-char SHA>"} -->
Run health: active ...
```

Update the same comment rather than creating a history of checkpoint comments.
Only checkpoint comments authored by the repository owner or a collaborator are
trusted; untrusted PR commenters cannot control run-health state. GitHub's
server-side comment `updated_at` timestamp is the durable last-progress time; do
not invent a separate client timestamp.

Use:
- `mode=active` only while this run is supposed to continue after the named
  external event;
- `expected=ci` while waiting for the repository CI workflow on the exact head;
- `expected=review` only when this run is intentionally staying alive for review
  evidence rather than using the normal clean review handoff;
- `mode=handoff` before an intentional clean stop where a later user/run is
  expected to resume;
- `mode=complete` when no further autonomous continuation is expected.

Every new pushed head must update `head_sha` before waiting. If the current PR head
differs from the checkpoint, the watchdog deliberately refuses to infer a stall.

The scheduled `Agent run watchdog` workflow inspects only `active` checkpoints.
It paginates PR comments/review evidence rather than assuming the newest state is in
the first API page. Review evidence must belong to the exact checkpoint head; review
activity attached to an older commit does not advance the current wait. It does not
flag healthy pending waits. It marks a run stalled only when actionable CI/review
evidence is newer than the checkpoint and has remained unattended beyond the
configured threshold.

Immediately before emitting a stall record, the watchdog re-fetches the current PR
state/head, latest trusted checkpoint, and current CI state when CI is the expected
event. If the PR closed, the head/checkpoint changed, or a newer CI run is now queued
or in progress, newer repository state wins and the stale detection is discarded.
The watchdog never overwrites the primary checkpoint; it emits one idempotent,
separate resume/stall record keyed to that checkpoint version instead. Only records
authored by `github-actions[bot]` satisfy that idempotency check, so outside commenters
cannot forge a suppression marker.

The watchdog is detection/recovery context only. It does not merge, edit product
code, weaken gates, or restart a stopped ChatGPT/web-chat execution. Automatic
resumption requires an external supervisor and is a separate capability.

## 3. Progress checkpoints

For substantial runs, report concise checkpoints at useful boundaries:
- route/scope established;
- meaningful implementation/diagnostic finding;
- blocker or change of hypothesis;
- validation/CI started or evidence obtained;
- final handoff.

Report evidence such as branch, PR, SHA, failing test/job, or completed slice rather than generic "still working" messages.

## 4. Detect unhealthy loops

Treat the run as unhealthy when one or more occurs:
- the same command/tool/action is retried without new evidence;
- the same CI failure is rerun repeatedly without a changed hypothesis or patch;
- work expands into a new implementation domain not in the packet;
- the run is waiting on external review/CI while doing unrelated speculative edits;
- environment/setup failure prevents the requested validation and repeated retries do not change that fact;
- the agent can no longer state the exact current objective, branch/PR, or next gate.

When detected, stop the loop and choose one of: narrow the reproduction, route to `investigate-ci-failure`, switch execution environment via `execution-router`, hand off to the owning specialist, or report the blocker.

A failing CI run is not an unhealthy loop by itself. For an ordinary issue packet owned by the primary thread, new failure evidence should normally be diagnosed, repaired, pushed, and validated again without asking the user to approve each iteration.

For the staged feature workflow, preserve its stricter ownership rule: one Codex turn performs one stage only, and a CI repair happens in a new turn owned only by the implicated role. Do not let `run-health` extend the current stage across that boundary.

## 5. CI and review gates

For an ordinary issue packet owned by the primary thread, use GitHub Actions as an autonomous feedback loop while implementation is still active:
- keep the PR draft during implementation and CI repair;
- when CI fails, apply `investigate-ci-failure`, make the smallest root-cause repair, push, and let CI run again;
- do not stop merely because another CI iteration is required;
- treat CI as green only when the required checks for the exact current PR head SHA have passed.

For staged feature work, do not apply that same-turn repair loop across stages. Capture the exact failing SHA/job/evidence and hand off the repair to a new turn owned by the implicated role, as required by `AGENTS.md`.

Before spending review capacity, re-check current `main`, mergeability, and material overlap. If the branch must be refreshed or repaired, do that first through the owning workflow and restore exact-head green CI.

Once implementation is complete and exact-head CI is green, the primary thread should:
1. mark the PR ready for review so the configured Codex review is triggered;
2. verify that the review was successfully triggered or queued;
3. record the exact reviewed head SHA;
4. STOP the current run instead of waiting or polling for the review result.

After actionable review feedback is available in a later primary-thread run:
- return the PR to draft before code changes;
- address the findings through the correct owning workflow and restore exact-head green CI;
- deliver the PR for re-review and STOP again after confirming the review trigger;
- for a second/subsequent Codex review, prefer an explicit instruction to review only the changes since the last reviewed SHA and verify the prior findings, but do not claim this is a guaranteed delta-only review mode.

## 6. Waiting and external state

Do not spin indefinitely waiting for GitHub CI, Codex review, or another external event. During an ordinary issue implementation/CI repair loop, continue while new actionable evidence arrives and the run remains healthy. During staged feature work, preserve the stage/turn handoff rules instead of continuing across ownership boundaries.

The intentional clean stop is the review boundary above: exact-head CI green, current-main/mergeability rechecked, review triggered/queued, and exact reviewed SHA recorded. A later run should re-fetch current external state before continuing.

## 7. Scope creep rule

A run may repair directly related defects exposed by its focused validation when the owning workflow permits that repair in the same run. It should not absorb unrelated cleanup, refactors, or adjacent feature requests.

If a new issue is independently shippable, record/decompose it and keep the current packet bounded.

## 8. Completion/handoff

End with enough durable context to resume safely:
- objective completed or concrete blocker;
- branch/PR and exact head SHA when applicable;
- changed scope;
- focused validation and CI/review state;
- unresolved actionable findings;
- next owner/action if work remains.

For the intentional review gate, explicitly report that exact-head CI is green, which SHA was delivered for review, and that the review trigger/queue was observed.

A run that cannot finish but leaves this state is healthier than a long invisible run that continues retrying without new evidence.
