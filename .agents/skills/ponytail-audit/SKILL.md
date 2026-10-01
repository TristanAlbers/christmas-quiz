---
name: ponytail-audit
description: Read-only whole-repository audit for unnecessary complexity in the Christmas Quiz codebase. Finds candidates to delete, reuse, consolidate, or replace with Python/Django/browser-native behavior while protecting invariants, security, recovery, polling stability, tests, migrations, and intentional compatibility layers.
---

Use this skill for explicit repo-wide simplification/debt investigations or periodic maintenance reviews. It is not required for every PR and it never applies changes by itself.

## Purpose

Find accumulated complexity that no longer earns its maintenance cost, especially complexity introduced incrementally by agent-driven feature work. Produce cleanup candidates that can be evaluated and implemented separately without turning an audit into a high-risk refactor.

## Authority and exclusions

Follow `AGENTS.md` and the repository authority order before judging a construct unnecessary.

Do not treat the following as removable merely because they are verbose, duplicated-looking, or old:
- security, authentication, authorization, team isolation, or trust-boundary validation;
- transaction, concurrency, idempotency, recovery, snapshot, audit, timer, or first-wins protections;
- canonical completion/state-machine enforcement and server-authoritative projections;
- polling-safe interaction behavior, accessibility, or required UI/presentation behavior;
- compatibility facades/shims still needed by callers, persisted data, contracts, or migration boundaries;
- focused tests that protect distinct domain, integration, browser, concurrency, security, recovery, or polling invariants;
- historical applied migrations.

A candidate that crosses one of these areas must include explicit evidence that the guarantee survives the proposed simplification. If that evidence is not available, report it as `investigate`, not `delete` or `consolidate`.

## Audit method

Scan the repository broadly, then trace each candidate far enough to avoid false positives. Prefer evidence from imports/callers, routes, templates, tests, contracts, current product decisions, and active configuration over file names or age.

Hunt for:
- dead files, helpers, flags, branches, compatibility paths, static assets, and configuration no longer referenced;
- one-use abstractions or wrappers that add no current boundary or compatibility value;
- repeated behavior that can reuse an existing project primitive;
- Python/Django code duplicating standard framework capabilities;
- custom JavaScript duplicating HTML/CSS/browser/HTMX behavior;
- issue-specific CSS/JS or presentation helpers that have become safe to consolidate after the issue landed;
- dependencies that can be removed because the platform or existing stack covers their only use;
- stale phase/issue compatibility layers whose original constraint no longer exists;
- duplicated documentation/contracts that can be retired only if authority remains unambiguous;
- tests that are truly duplicate protection, not merely similar setup or neighboring assertions.

Do not recommend broad rewrites merely to make code aesthetically uniform. Prefer high-confidence deletions and consolidations with small blast radius.

## Classification

Each finding uses one tag:
- `delete` — high-confidence dead/unneeded code; nothing replaces it;
- `reuse` — existing project primitive can replace a parallel implementation;
- `stdlib` — Python/Django capability can replace custom code;
- `native` — HTML/CSS/browser/HTMX capability can replace custom frontend code;
- `consolidate` — multiple live implementations can safely share one existing or smaller root implementation;
- `investigate` — plausible complexity debt, but current evidence is insufficient to prove removal safe.

## Output

Rank findings by expected maintenance reduction and confidence, not raw line count alone.

For each finding report:

`<tag> | <confidence high/medium/low> | <path(s)> | <what can shrink> | <replacement or deletion> | <evidence/guardrail>`

Where practical, include approximate files/lines/dependency reduction, but do not fabricate precision. A 20-line compatibility shim with a subtle recovery guarantee can be more valuable than deleting 200 lines of harmless CSS, so explain risk and ownership.

End with:
- high-confidence candidates suitable for small cleanup issues/PRs;
- `investigate` candidates needing specialist analysis;
- protected areas intentionally left alone;
- whether a follow-up audit is warranted after the proposed cleanups.

If nothing meaningful can be simplified, report that the repository is already lean enough and stop.

## Turning audit findings into work

The audit is read-only. Do not batch all findings into one cleanup PR.

For accepted findings:
1. create or select the smallest independently shippable cleanup packet;
2. route it to the specialist that owns the behavior being simplified;
3. preserve or strengthen the tests/invariants that prove the simplification safe;
4. implement through the normal issue/PR workflow;
5. run `ponytail-review` on the cleanup PR before Codex review and landing like any other implementation PR.

Use repo-wide audits periodically or when complexity has visibly accumulated, not as ritual work after every feature.
