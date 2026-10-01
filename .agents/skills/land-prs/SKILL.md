---
name: land-prs
description: Review, order, refresh, repair conflicts in, and safely land one or more Christmas Quiz pull requests. Use when the user asks to merge, land, integrate, approve, or safely combine specific/open PRs.
---

Use this skill for requests such as "land PRs #12, #14 and #17 safely" or "integrate the ready PRs".

## Boundary

- Follow `AGENTS.md` and the repository authority order.
- This skill coordinates repository integration. Production semantics remain owned by the existing specialists.
- The primary user-facing thread owns GitHub actions and may invoke `merge_steward`. Specialists never spawn specialists.
- Formal GitHub approval is not a substitute for review and may be impossible when the connected identity authored the PR. Record integration readiness instead.
- Merge only when the user's request explicitly authorizes landing/merging. A request to review/check PRs stops before merge.
- A PR is not safe to land unless its exact merge-head SHA has a current `.agents/skills/ponytail-review/SKILL.md` `PONYTAIL PASS`.

## 1. Build the candidate packet

For every candidate PR, inspect:
- PR title/body, linked issue(s), base/head branch and exact head SHA;
- changed filenames/diff and overlap with other candidate PRs;
- review submissions, unresolved review threads/comments, and requested changes;
- current CI/check results for that head;
- whether the branch is behind or conflicts with current `main`;
- whether the PR claims to complete an epic when it only implements a slice;
- durable Ponytail review evidence and the exact head SHA it covers.

Exclude or stop on draft/incomplete PRs with known blocking findings unless the user explicitly asked to repair them.

A missing or stale Ponytail checkpoint is not an automatic permanent blocker: run the read-only `ponytail-review` against the complete current PR diff. If it returns `PONYTAIL PASS`, record the exact head SHA and continue readiness evaluation. If it returns `PONYTAIL CHANGES`, the PR is not safe to land until those findings are resolved or demonstrated, using repository authority and protected guarantees, not to be valid simplifications.

## 2. Determine dependency and merge order

Ask `merge_steward` to produce the smallest safe sequential order based on behavioral dependencies and overlapping files/contracts.

Prefer:
- independent/non-overlapping prerequisites first;
- foundational schema/domain contracts before consumers when both are already approved;
- low-risk independent PRs without unnecessary waiting on unrelated candidates.

Do not merge multiple candidates based only on all being green against an old `main`. After each merge, reassess every remaining candidate against the new `main`.

## 3. Conflict policy

Mechanical conflicts may be repaired in the affected PR branch when intent on both sides is already settled: formatting, imports, adjacent documentation, generated ordering, or straightforward non-semantic combination of independent edits.

A conflict is semantic when resolving it requires choosing behavior, ownership, data shape, transaction guarantees, authorization/privacy, state-machine semantics, projections, or user interaction behavior.

Route semantic repairs narrowly:
- cross-boundary contract/architecture -> `architect`;
- game rules/state machine -> `game_engine`, with `game_engine_high` only on explicit escalation;
- schema/transaction/auth/isolation/recovery -> `persistence_security`;
- application/projection/routes/HTMX -> `integrator`;
- presentation/interaction/polling -> `ui_experience`.

After a semantic repair, use focused validation and `test_invariants` when the repair affects behavioral, concurrency/security/recovery, or polling-sensitive guarantees.

Any conflict repair, review fix, rebase-generated manual edit, or other commit changes the head SHA and invalidates the prior Ponytail checkpoint. After the repair and applicable validation, rerun `ponytail-review` on the complete PR diff and record a new `PONYTAIL PASS` before merge.

Do not create an improvised mega-merge branch that hides which PR introduced which behavior unless the user explicitly requests such a strategy.

## 4. Complexity gate

Immediately before final readiness assessment, verify that the exact current PR head SHA has a durable `PONYTAIL PASS`.

If no current pass exists:
1. run `.agents/skills/ponytail-review/SKILL.md` read-only against the complete PR diff and current base context;
2. if the result is `PONYTAIL PASS`, record `PONYTAIL PASS @ <head-sha>` in the PR description or another durable PR note;
3. if the result is `PONYTAIL CHANGES`, stop landing that PR and return the findings to the specialist that owns the affected behavior;
4. after any accepted simplification, rerun focused validation/invariant review as applicable, re-establish green CI, and rerun Ponytail review for the new head.

Do not let `merge_steward` invent semantic simplifications to satisfy this gate. Ponytail is a complexity reviewer, not an authority over product behavior, persistence guarantees, security, tests, polling interaction, or intentional compatibility layers.

Repo-wide `ponytail-audit` is **not** a landing requirement. It is a separate maintenance tool; safe landing requires only the changed-scope `ponytail-review` pass.

## 5. Readiness gate per PR

Immediately before merge, require:
- expected PR head SHA still matches what was reviewed;
- the exact current head has a recorded `PONYTAIL PASS`;
- no unresolved blocking review finding;
- current `main` relationship/conflict status has been rechecked;
- applicable focused validation for any repair is green;
- repository CI/checks for the head being merged are green (or a clearly documented repository limitation makes that unavailable and the user explicitly accepts proceeding).

Do not merge a stale or unexpectedly changed head. Re-review changed scope instead, including a fresh Ponytail pass for the new SHA.

## 6. Sequential landing

For each ready PR:
1. merge only that PR using the repository-supported method;
2. verify the merge succeeded and capture the resulting main commit;
3. refresh current `main`;
4. re-evaluate overlap, conflict status, review relevance, Ponytail checkpoint validity, and CI needs for every remaining PR;
5. repair/revalidate only what became stale because of the newly landed change.

Do not enable repository-wide auto-merge, change branch protection/rulesets, or alter unrelated repository settings unless the user explicitly asks.

## 7. Final handoff

Report:
- PRs merged and resulting order;
- PRs not merged and the concrete blocker;
- conflicts repaired and which specialist owned semantic repairs;
- Ponytail review evidence used for each merged PR, including reviewed head SHA;
- CI/review evidence used;
- any remaining issue/epic work that was intentionally not closed.
