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

## 1. Establish a bounded run

At the start of substantial work, identify:
- one concrete current objective;
- the current branch/PR/issue or other durable work object;
- the owner/skill for this packet;
- the next validation gate;
- explicit stop conditions.

If the requested work is too broad to define one bounded objective, size/decompose it before implementation.

## 2. Persist progress early

For non-trivial code work:
- use a short-lived branch;
- once there is a meaningful coherent implementation, commit it;
- open a draft PR early enough that branch, SHA, CI, comments, and status become externally observable;
- keep PR/body/handoff current enough that another run can resume from repository state rather than reconstructing a hidden plan.

Do not push broken speculative micro-edits solely for visibility; persist coherent checkpoints.

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

## 5. Waiting and external state

Do not spin waiting for GitHub CI, Codex review, or another external event. Check when useful; if the current environment cannot receive an asynchronous event automatically, leave a durable PR/SHA/status handoff and stop rather than polling indefinitely.

A later run should re-fetch current external state before continuing.

## 6. Scope creep rule

A run may repair directly related defects exposed by its focused validation. It should not absorb unrelated cleanup, refactors, or adjacent feature requests.

If a new issue is independently shippable, record/decompose it and keep the current packet bounded.

## 7. Completion/handoff

End with enough durable context to resume safely:
- objective completed or concrete blocker;
- branch/PR and exact head SHA when applicable;
- changed scope;
- focused validation and CI/review state;
- unresolved actionable findings;
- next owner/action if work remains.

A run that cannot finish but leaves this state is healthier than a long invisible run that continues retrying without new evidence.
