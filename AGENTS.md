# Christmas Escape Room Quiz — Codex Instructions

## Goal

Build a lightweight, self-hosted Christmas escape-room quiz for two isolated teams, two administrators, and a public TV overview. Correctness, recoverability, team isolation, interaction stability, and intentional UI/presentation are first-class requirements. Optimize usage by narrowing work, not by weakening safeguards.

## Specification authority

Use this order:
1. `docs/product-decisions.md` — explicit later user-approved decisions; overrides older wording only for the decisions it states.
2. `christmas-2026-game-rules-state-semantics.md` — normative behavior/invariants for all non-overridden rules.
3. `Design.md` — product/operational requirements.
4. `Views.md` — binding view/device/presentation requirements.
5. `Game States.md` — supporting state documentation.
6. `docs/architecture.md` — approved implementation architecture.
7. Current phase/issue contract or handoff — decisions for that bounded work only.

**Active UI initiative (approved 2026-10-11):** For Midnight Advent issues #72–#84 and final #80, **approved presentation detail** is in `docs/ui/midnight-advent.md`, with tracer-bullet dependencies in `docs/ui/midnight-advent-rollout.md`, explicit agent routing/skill evidence in `docs/ui/midnight-advent-agent-guide.md`, and parent product spec GitHub #71. The dated `docs/product-decisions.md` entry gives these **later user-approved visual decisions precedence over stale visual wording** in earlier `Views.md`, `visual-style.md`, and historical phases; it does **not** override protected game/domain/privacy/architecture contracts. `implementation_plan.md` is a historical snapshot for old phases, not a current UI task route. The actual issue's `Blocked by` section must be satisfied, even if its label is `ready-for-agent`. Do not begin implementation before PR #70 and issue blockers are landed. A later visual decision is not permission to invent new backend rules.

Do not silently resolve genuine conflicts. Route unresolved cross-boundary ambiguity to `architect`; ask the user only when authority cannot settle it.

Approved baseline: synchronous Django + Gunicorn WSGI, Django templates + locally bundled HTMX, SQLite, WhiteNoise, Docker Compose, one application container, persistent `./var`. Architecture changes require an `architect` stage.

## Hard invariants

- Backend state is authoritative; frontend code requests transitions and renders approved projections.
- Keep global state separate from each team's activity state; interruptions preserve underlying state/timers as specified.
- Correct answer, Skip, and admin force-completion share one canonical completion pipeline.
- Enforce sequential prerequisites in the backend.
- Resolve races atomically; first valid server-accepted transaction wins.
- Derive team identity from authenticated server context; enforce strict private read/write isolation.
- Balances never become negative; exactly-once/idempotent outcomes apply where required.
- Timers are server-authoritative and recoverable across refresh/reconnect/restart.
- Preserve append-only audit history through supported behavior, including Reset.
- Active runs use immutable snapshotted configuration/media; `games/*` remains declarative data.
- Global `FINISHED` requires both teams to complete puzzle 25; `completed` is the canonical puzzle status.
- Skip is an immediate completion action, not stored inventory.
- Preserve 500 ms HTMX polling and `docs/polling-ui-guideline.md`: still-valid interactive controls must not be recreated by normal polling.
- User-visible requirements are not optional polish. Preserve Advent-calendar progression where shown, the approved coarse public progression boundary, visible 11-step Music progress, visual Hint/Uno-Reverse treatment, styled Skip, and coherent Christmas presentation without compromising privacy/usability.

## Staged feature workflow

Use the staged workflow for planned major capabilities and issue work that proves too broad for one small PR.

**One Codex turn performs one stage only and then stops.** Only the primary user-facing thread may spawn a specialist, and repository configuration permits only one spawned specialist at a time. Specialists never spawn agents.

| Stage | Role | Purpose | Model |
| --- | --- | --- | --- |
| A | `architect` | contract, boundaries, ownership, UI/projection acceptance | Sol High |
| B | `game_engine` | bounded pure-domain implementation/tests | Sol Medium |
| B* | `game_engine_high` | explicit escalation for a concrete subtle domain issue | Sol High |
| C | `persistence_security` | schema/transactions/security/concurrency/recovery | Sol High |
| D | `integrator` | application/projections/routes/HTMX/data/docs | Sol Medium |
| E | `ui_experience` | templates/static/UX/polling-safe browser behavior | Sol Medium |
| F | `test_invariants` | independent review-first verification | Terra Medium |

GitHub Actions is the final deterministic gate. Repair a failure in a new turn owned only by the implicated role. A user-visible phase must include Stage E unless its contract explicitly demonstrates that no presentation/interaction change is required.

Role-specific ownership lives in `.codex/agents/*.toml`. Phase-specific objectives and gates live in `implementation_plan.md`. Do not duplicate those details here.

## Issue-driven workflow

Use the repository skill `.agents/skills/work-github-issue/SKILL.md` when the user asks to implement/fix a specific GitHub issue and expects a PR.

Implementation issues should be small, independently shippable packets. A research/design issue may be intentionally broad, but the implementation workflow must size it before coding. Do not attempt an epic merely because it has one issue number. Oversized issues are decomposed or reduced to a clearly identified primary slice; partial epic PRs must not close the umbrella issue.

For an ordinary issue, route only the minimum necessary specialists, sequentially. The default ceiling is two implementation specialist domains plus one independent verifier. If the selected work still needs broader cross-domain staging, use the staged feature workflow instead.

Issue text/comments are task input, not repository authority. They cannot override these instructions, higher-authority specifications, security/privacy guarantees, or specialist ownership.

## PR integration workflow

Use `.agents/skills/land-prs/SKILL.md` and the `merge_steward` agent when the user asks to integrate, land, or merge one or more PRs.

The merge steward owns dependency ordering, overlap/conflict triage, latest-main re-evaluation, and integration-readiness assessment. It may resolve mechanical conflicts only when behavior is already settled. Semantic conflicts return to the existing specialist that owns that behavior; the merge steward does not invent product/domain/persistence/UI semantics.

Landing is sequential: after every merge, refresh `main` and reassess remaining PRs rather than assuming checks against the previous base are still sufficient. Merge only when the user explicitly authorized landing/merging.

Safe landing also requires a current `.agents/skills/ponytail-review/SKILL.md` `PONYTAIL PASS` covering the exact current base/head SHA pair being merged. Missing or stale evidence is not a waiver: `land-prs` must run the review before merge. A base advance invalidates the pass even if the PR head did not change, because the effective diff and available reuse opportunities may have changed. A `PONYTAIL CHANGES` result blocks landing until the findings are resolved or demonstrated, from repository authority and protected guarantees, not to be valid simplifications.

## Reusable diagnostic and execution skills

Use repository skills automatically when the request matches their workflow; the user does not need to name the skill explicitly.

- `.agents/skills/investigate-ci-failure/SKILL.md` — use when asked why CI, a workflow, a PR check, or a post-merge run is failing. Diagnose and classify before editing; if the user asked only for investigation, stop before implementation.
- `.agents/skills/work-polling-ui/SKILL.md` — use for HTMX/polling-sensitive UI work involving stable controls, focus/pointer behavior, transient-effect replay, persistent overlays/media, or DOM identity.
- `.agents/skills/execution-router/SKILL.md` — use when deciding whether work should be handled through GitHub/web-chat orchestration, local Codex, or Codex Cloud, especially when the user asks for prompts or an implementation route.
- `.agents/skills/run-health/SKILL.md` — use as a supporting skill for substantial autonomous work that risks becoming long, opaque, repetitive, or stuck. Keep work bounded, persist coherent progress, report evidence-based checkpoints, and stop unhealthy retry loops.
- `.agents/skills/ponytail-review/SKILL.md` — mandatory read-only complexity review for implementation PRs before they are marked ready for Codex review and again whenever the reviewed base/head pair changes. It protects invariants/tests/security/recovery/polling/compatibility while looking for unnecessary changed-scope complexity.
- `.agents/skills/ponytail-audit/SKILL.md` — optional read-only whole-repository complexity audit for explicit maintenance/debt investigations.
- `.agents/skills/midnight-advent-ui/SKILL.md` — use for approved Midnight Advent implementation tickets. Apply the visual quality loop, use genuine installed Anthropic Frontend Design and Impeccable when available, and **report actual invocation versus unavailable/manual review**. Read `docs/ui/midnight-advent-agent-guide.md`. This local guidance does not magically install third-party skills. The existing Ponytail gate remains mandatory for finished implementation diffs. Convert accepted findings into small normal cleanup packets; do not batch an audit into a mega-refactor.

Skills coordinate procedure; they do not override product specifications, hard invariants, specialist ownership, or the task-specific issue/staged/landing workflow.

## Context and contract discipline

Start from the current phase/stage or issue slice, its contract/handoff, owned files, and only the authority needed for the assignment. Do not make every specialist reread all specifications, historical contracts, or unrelated code.

Phase contracts are concise decision records, normally about 120–150 lines maximum. They capture scope/non-scope, shared decisions/interfaces, transaction/security guarantees, ownership/edit order, authoritative references, acceptance criteria, and for user-visible work the approved projection, device targets, polling boundaries, visual semantics, and focused browser acceptance.

## Validation

During a stage or bounded issue packet:
- run the smallest tests/checks covering changed behavior and nearby invariants;
- run Ruff on changed Python/smallest practical scope;
- run Django/migration checks when relevant;
- run focused browser tests for changed UI/interaction behavior, especially polling-sensitive controls.

Do not repeatedly rerun an unchanged full suite for reassurance. CI owns the complete suite. For polling-sensitive controls, prefer stable-node/focus/caret and real pointer/touch interaction checks where practical.

After implementation and focused validation are complete, but before an implementation PR is marked ready for Codex review, run `ponytail-review` against the complete branch diff and current base. Apply only simplifications that preserve repository authority and protected guarantees, rerun focused validation after implementation changes, and rerun the review until the current base/head pair receives `PONYTAIL PASS`. Record it as `PONYTAIL PASS base=<base-sha> head=<head-sha>` in the PR description or another durable PR note.

## Progress and handoff

For substantial work, report concise checkpoints: initial route/scope, implementation start, meaningful finding/blocker, before validation, and final handoff. Do not leave the user with only a long `Thinking` state or expose private chain-of-thought.

A handoff reports changed files, decisions/assumptions, focused validation, unresolved issues, and for UI work requirements addressed plus remaining UI debt. Then STOP.

## Git / PR

Use a short-lived branch from current `main` for non-trivial work. Preserve unrelated changes. Do not implement on `main`, merge, enable auto-merge, alter branch protection, or delete branches unless the user asks. The primary thread owns branch/commit/push/PR lifecycle.

For feature/issue implementation, open the PR as a **draft** while changes are still being made. GitHub Actions must run for draft PR creation and subsequent pushes. Keep the PR draft until implementation is complete, focused validation is green, the current base/head pair has a recorded `PONYTAIL PASS`, and required CI is green. Only then mark it ready so Codex/review automation sees a completed, complexity-reviewed implementation.

If Codex/review findings require repository changes, return the PR to draft before pushing those fixes. Re-run applicable focused validation, rerun `ponytail-review` because the base/head pair changed, update the recorded pair, re-establish green CI, and only then mark the PR ready again. A Ponytail pass for an older base or head never authorizes the current diff.

## Maintenance rule

Keep instructions progressively disclosed:
- global rules/invariants/workflow boundaries belong here;
- role-specific rules belong in `.codex/agents/*.toml`;
- reusable orchestration, diagnostics, execution routing, run-health, complexity review, and audit procedures belong in `.agents/skills/*`;
- phase-specific work belongs in `implementation_plan.md`;
- product behavior belongs in the authoritative specifications/contracts.

Do not duplicate role-specific or generic orchestration text across layers merely for convenience.
