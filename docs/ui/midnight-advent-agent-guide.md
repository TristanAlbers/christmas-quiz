# Midnight Advent — lean visual-first agent guide

**Approved process: 2026-10-11.** This guide covers *how to implement* one Quizzmass UI issue. Product behavior and accepted design remain in [the UI contract](midnight-advent.md), [product decisions](../product-decisions.md) and the issue's acceptance criteria. Follow `AGENTS.md` and its hard invariants first.

## Authority, scope and prerequisites

- Respect each issue's `Blocked by` dependencies on `main`; a `ready-for-agent` label alone is not permission to proceed. PR #70 and foundational #72/#79 have landed; evaluate later dependencies from actual GitHub status.
- The approved V4, Game Master V1 and Pause/Victory V1 prototype HTML/stills are *visual targets for composition, characteristic controls, hierarchy and proportions*, not sources of fake game data, clock, command, score or animations. See [reference index](midnight-advent-visual-reference-index.md). Local reference directory: `/home/tris/quizzmas-design-references/approved/`. Verify relevant files actually exist. If unavailable, report **VISUAL BLOCKED**, preserve current work and stop visually significant implementation; don't improvise or claim fidelity.
- Keep Django/HTMX, authorized server projections, the 500ms poll boundary, private/public isolation, stable form/media identity, event-once behavior, recovery, Dutch-first copy, keyboard, touch and reduced-motion guarantees. A visual conflict never authorizes weaker game/security rules. Escalate a concrete missing projection or genuine contract conflict rather than manufacturing state.
- Use one issue, one small PR or an existing draft PR; reuse nearby templates, CSS and JS instead of creating a parallel UI framework. Read only issue-relevant rules and code; do not rehash settled product discovery.

## Three-phase delivery — stop before spending the next phase

### 1. Minimal implementation and early screenshot

- Choose the first ordinary, representative screen/state from the **issue-specific prompt**: 390px team phone, Game Master tablet, 1920×1080 TV, or the relevant effect keyframe. Render the *real Django application* with a comparable authorized fixture next to the approved reference.
- Implement the smallest reusable slice and correct obvious composition differences (geometry, hierarchy, signature components, typography and spacing, then palette). A similar pine/gold aesthetic is **not** sufficient reference fidelity.
- Run only the smoke check necessary to know it renders and has not broken an implicated privacy/authorization/invariant boundary. Keep original tests. Long-text, tall-image, no-media, keyboard, 320px, reduced-motion, concurrency and polling edge tests are required at final verification, not a substitute for a first representative comparator. If the work is a privacy/event-sensitive feature, check that specific invariant immediately.

### 2. Visual convergence and explicit user checkpoint

- Iterate narrowly against the reference. Reuse screenshots and fixtures. If two corrections fail to materially improve the design or an approved reference is missing, **stop and report the blocker** rather than starting autonomous review loops.
- Attach or link one **viewable reference-versus-Django comparison**, viewport/state, up to five unresolved material differences, changed files and SHA. For important motion, include meaningful keyframe/settled outcome evidence; avoid exhaustive captures of unchanged views.
- **STOP and request the user's explicit visual approval.** Green CI, passing functional tests, Impeccable scores, agent self-grading or screenshots existing in a local directory do not equal that approval. Do not begin dependent issue work or final reviews before it.

### 3. Verify and deliver once

- After user visual approval, run the focused relevant browser/edge tests, Ruff and domain/integration/security/recovery tests appropriate to changed behavior. Preserve existing assertions; do not reduce coverage to save tokens. Let GitHub Actions verify the full deterministic suite. Draft PR CI may run automatically when commits are pushed; don't manually relaunch the unchanged full suite for reassurance.
- On the complete current diff, perform the **required** exact-current-base/head `ponytail-review`, record `PONYTAIL PASS base=… head=…`, establish green required CI and request Codex review under `AGENTS.md` / `work-github-issue`. Base/head changes invalidate that checkpoint. Fix valid findings and rerun the affected checks; never merge unless separately authorized.
- For #80, reuse earlier accepted comparisons and CI artifacts, then test the integrated cross-role flows and genuine device/VPN/offline constraints. Recheck merged #72/#79. Capture only missing/suspect views; break findings into bounded issues.

## Skills and agent routing: use when they add value

- **Default implementer:** `ui_experience` (Medium) for multi-file real-browser UI; GitHub/chat for low-risk text/documentation. `integrator` only for a proven view/HTMX boundary. `architect`, `persistence_security` and `test_invariants` only when concrete semantics, security/concurrency or recovery risk warrants their expertise; never default to an expensive multi-agent chain. The mandatory current-diff Ponytail gate is distinct from specialist fan-out.
- **Repo skills:** `work-github-issue`, `midnight-advent-ui`, `work-polling-ui` where controls/polling change; `run-health` for a genuinely long/stalled run. Do not copy their full text into every issue.
- **External design tools are OPTIONAL and targeted.** `frontend-design` can help an unsolved substantial design problem. Impeccable `critique`/`polish` can help a specific discrepancy, `animate` an important unconvincing effect, and `audit` the integrated #80 review or a concrete accessibility concern. Do not automatically run all subcommands per PR. Never claim unexecuted commands were run. Do not repeatedly fetch/diff official skill provenance or silently install anything; source inspection is relevant to a **new** installation, not every UI ticket. Original sources: [Anthropic](https://github.com/anthropics/skills/tree/main/skills/frontend-design) and [Impeccable](https://github.com/pbakaus/impeccable).
- **Evidence should be brief**: one comparable screenshot, remaining deltas and SHA at the visual checkpoint; relevant tests/CI and review SHA at final handoff. Avoid verbose audit essays and redundant browser matrices.

## Copy-paste common prompt (combine with the issue-specific prompt)

```text
Implement only the named Midnight Advent issue (or continue its existing PR).
Follow AGENTS.md, issue Blocked by, relevant product/UI authority, and the
lean visual-first guide. Verify the approved reference pack locally. Reuse
existing Django/HTMX components and preserve privacy, state and 500ms polling.
Render a directly comparable real-app screen immediately; fix the biggest
visual differences; run only necessary smoke/invariant checks. Show the
reference-versus-Django screenshot, up to five deltas and SHA. STOP for my
visual approval. Do not run blanket Impeccable, extra agents, full-suite
loops, Ponytail or Codex review before approval. After approval, finish
required tests, CI, exact-pair Ponytail and Codex review; do not merge.
```
