---
name: ponytail-review
description: Review a Christmas Quiz implementation diff for unnecessary complexity before Codex review and before safe landing. Read-only by default: identify simplifications without weakening product requirements, invariants, security, recovery, polling stability, accessibility, or intentional compatibility behavior.
---

Use this skill when an implementation is functionally complete and needs a final complexity pass before it is considered ready for review or landing.

## Purpose

Prevent agent-driven implementation bloat without turning minimalism into a competing product or safety requirement. The goal is the smallest correct implementation that preserves the repository's documented guarantees.

This skill is a review gate, not an implementation owner. It proposes simplifications; the existing specialist that owns the affected behavior decides and applies any non-trivial change.

## Authority and protected behavior

Follow `AGENTS.md` and the repository authority order first. A smaller diff is never preferable when it weakens a higher-authority requirement.

Do **not** classify the following as bloat merely because they add code, files, or tests:
- authentication, authorization, team isolation, trust-boundary validation, or security controls;
- transaction, idempotency, concurrency, first-wins, durable-timer, recovery, snapshot, or audit guarantees;
- server-authoritative state and canonical completion pipelines;
- polling-safe DOM identity, focus/pointer stability, transient-effect correctness, or required browser behavior;
- accessibility basics or explicitly required presentation behavior;
- compatibility facades/shims that current callers, persisted data, migrations, or approved contracts still require;
- focused domain, integration, browser, concurrency, recovery, and security tests that protect distinct invariants.

Existing test overlap is not enough to recommend deletion. Recommend test consolidation only when you can name the duplicated guarantee and show that the surviving test still fails for the same regression class.

Historical migrations are not cleanup targets. Do not recommend rewriting applied migration history merely to make the tree smaller.

## Review scope

Review the complete PR/branch diff against its current base, not only the last commit. Read the issue/contract and the touched flow far enough to distinguish accidental complexity from intentional architecture.

Look specifically for:
- a new helper, abstraction, service, adapter, config flag, indirection, or file with only one real use and no requirement for extension;
- duplicated behavior already present in the repository;
- custom Python that the standard library or Django already handles cleanly;
- custom JavaScript where HTML/CSS/HTMX/native browser behavior already satisfies the requirement;
- a new dependency for behavior already covered by the platform or installed stack;
- issue-specific CSS/JS/helpers that can safely reuse an existing shared primitive;
- wrappers that only delegate and add no required compatibility, isolation, transaction, projection, or presentation boundary;
- speculative flexibility for future features not present in the current requirement;
- repeated checks that belong in one shared root-cause location;
- unnecessary files, branches, flags, dead compatibility paths, or comments introduced by the current change.

Prefer deletion, reuse, stdlib/native platform behavior, and the smallest existing abstraction that already fits. Do not perform opportunistic architecture rewrites outside the changed scope.

## Finding format

For each actionable finding, report:

`<path>:<line or area> — <tag>: <what is unnecessary>. Replace with <smaller approach>. Safety note: <why required guarantees remain intact>.`

Use one of these tags:
- `delete` — nothing is needed in its place;
- `reuse` — existing project behavior already covers it;
- `stdlib` — Python/Django already provides it;
- `native` — HTML/CSS/browser/HTMX behavior already provides it;
- `shrink` — same behavior can be expressed materially more simply;
- `consolidate` — duplicated changed-scope behavior can share an existing root implementation.

Do not invent a finding to satisfy the gate. If the diff is already lean, say so.

## Gate result

End with exactly one gate result:
- `PONYTAIL PASS` — no actionable changed-scope complexity remains; or
- `PONYTAIL CHANGES` — one or more actionable findings should be addressed before review/landing.

Record both the exact reviewed base SHA and head SHA. Use a durable checkpoint such as `PONYTAIL PASS base=<base-sha> head=<head-sha>`. The checkpoint is valid only for that exact base/head pair because either side changing can change the effective diff and available reuse opportunities.

If accepted findings cause a repository change, focused validation must be rerun and this review must be rerun against the new head. If the PR base advances, rerun this review against that new base even when the head is unchanged. A changed base or head invalidates the prior checkpoint; rerunning a read-only diff review is cheaper and clearer than reasoning about exceptions.

## Workflow integration

For normal implementation PRs:
1. implementation and focused validation complete;
2. run this skill on the complete diff while the PR is still draft;
3. route non-trivial findings back to the specialist that owns the affected behavior;
4. apply only changes that preserve documented guarantees;
5. rerun focused validation after implementation changes and rerun this review whenever the base or head changed;
6. record `PONYTAIL PASS base=<base-sha> head=<head-sha>` in the PR description or another durable PR note;
7. only then may the PR be marked ready for Codex review.

A later Codex-review fix changes the head, so return the PR to draft, apply the fix, revalidate, rerun this skill, update the reviewed base/head pair, restore green CI, and only then mark ready again.

Safe landing must verify a current `PONYTAIL PASS` for the exact current base/head pair. If evidence is missing or stale, `land-prs` runs this review before merge. A `PONYTAIL CHANGES` result blocks landing until the findings are resolved or shown, with repository-authority evidence, not to be valid simplifications.

## Boundary

This skill does not replace correctness, security, invariant, UI, or Codex review. It intentionally reviews only unnecessary complexity in the changed scope.
