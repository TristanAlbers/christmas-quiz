---
name: investigate-ci-failure
description: Diagnose a failing or flaky GitHub Actions/PR check before changing code. Use when the user asks why CI, a workflow, a PR check, or a post-merge run is failing, especially when they ask to investigate or report first.
---

Use this skill to determine what failed, why it failed, and who should own the repair. Diagnosis comes before implementation unless the user explicitly asks to fix the failure in the same task.

## Boundary and authority

- Follow `AGENTS.md` and the repository authority order.
- Do not treat a red check as proof of a product defect. Distinguish product regressions, test defects/flakes, stale-base integration failures, setup/environment failures, and infrastructure/transient failures.
- Inspect the exact failing head/merge SHA. Do not reason from an older successful run as if it validates a changed head.
- Preserve test strength. A flaky or badly targeted assertion should be replaced with a deterministic assertion of the same product invariant, not weakened or skipped.

## 1. Establish the failure packet

Collect the smallest evidence needed:
- PR/head SHA or post-merge main SHA;
- failing workflow/run, job, step, and relevant log excerpt;
- nearby successful/failed runs when recurrence matters;
- changed files/diff when the failure may be caused by the PR;
- relevant test and production code only after the failing signal is identified.

If multiple jobs fail, identify whether they share one root cause before treating them as separate defects.

## 2. Classify before editing

Classify the failure as one of:

1. **Product regression** — implementation violates an intended behavior/invariant.
2. **Deterministic test defect** — assertion/harness encodes the wrong requirement or stale specification.
3. **Nondeterministic/flaky test** — the invariant may hold but the observed proxy depends on timing, scheduling, animation events, sleeps, or other unstable signals.
4. **Stale-base/integration failure** — branch was green against an older `main` but no longer composes with current `main`.
5. **Environment/setup failure** — dependency, packaging, Docker, browser, Python, migration/bootstrap, or CI configuration prevents meaningful validation.
6. **Transient infrastructure failure** — external runner/service failure with no evidence of repository behavior being wrong.

Do not propose a code fix until the evidence supports one class more strongly than the alternatives.

## 3. Reproduce narrowly

Prefer the smallest reproduction that tests the suspected invariant:
- one test/module before a suite;
- one CI job before rerunning the whole workflow;
- deterministic state/DOM/response assertions over raw timing events;
- compare exact same SHA reruns when flakiness is suspected.

A rerun that passes is evidence of nondeterminism, not proof by itself. Explain what unstable mechanism could account for the difference.

## 4. Route the repair

When a repair is requested, route only to the implicated owner:
- domain/state semantics -> `game_engine`;
- persistence/auth/concurrency/recovery -> `persistence_security`;
- application/projection/HTMX orchestration -> `integrator`;
- presentation/browser/polling behavior -> `ui_experience`;
- test-only cross-cutting invariant correction -> `test_invariants` or owning implementation role as appropriate;
- CI/setup/workflow mechanics -> primary thread unless specialist semantics are implicated.

Use `.agents/skills/work-polling-ui/SKILL.md` when the failure is specifically about polling-stable interaction or one-shot presentation behavior.

## 5. Investigation-only endpoint

When the user asked to investigate but not fix, stop after reporting:
- exact failing SHA/run/job/test;
- classification and evidence;
- likely root cause;
- whether the product or the test is wrong;
- smallest safe repair route;
- uncertainty that remains.

Do not silently push a speculative fix.

## 6. Fix-and-verify endpoint

If the user also requested a repair:
- make the smallest root-cause patch;
- run the focused reproduction first;
- preserve or improve the original invariant coverage;
- push once the repair is coherent;
- use GitHub Actions as the full clean-environment gate;
- report exact-head CI evidence.
