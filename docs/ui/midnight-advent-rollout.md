# Midnight Advent — implementation and validation rollout

**Status:** approved redesign, staged execution plan. **Companion contract:** [Midnight Advent](midnight-advent.md) and [agent/skill execution guide](midnight-advent-agent-guide.md). This is a presentation project; do not reset/reimplement phases or game rules in the historical `implementation_plan.md`.

## Working model

- Product/spec review, GitHub ticket drafting, bounded text/CSS fixes, CI/log triage, independent diff review and merge orchestration: **this chat + GitHub** (minimize local Codex consumption).
- Multi-file CSS/template/JavaScript work requiring rapid live Playwright/screenshot iterations or local Docker/browser/device testing: **local Codex**, `ui_experience` (Medium), scoped to **one ticket**. Use `integrator` only when a concrete projection/HTMX boundary must change; escalate `architect` or `persistence_security` only for a real cross-boundary ambiguity.
- Use `midnight-advent-ui` and relevant repo skills. `frontend-design` and Impeccable are **optional, targeted tools**, not a multi-pass per-ticket checklist. Never claim a skill ran unless it did; do not repeat provenance research or install tools without authorization. Compare one representative real Django screen against approved references **before** broad validation. Run the mandatory Ponytail review only on a completed, visually approved diff.
- Keep PRs small, single-purpose and draft while styling. CI may run automatically on commits; avoid repeated unnecessary manual reruns. Request **user visual approval** after a representative screenshot and brief gap report; only then finish all applicable tests/required green CI and the exact-base/head `PONYTAIL PASS` before Codex review. Never merge without explicit authorization.

## Approved tracer-bullet delivery backlog (Matt Pocock `to-tickets`)

The parent [specification #71](https://github.com/TristanAlbers/christmas-quiz/issues/71) was converted into **13 approved, independently demonstrable tickets**; each issue now records its authoritative `Blocked by` references and its own acceptance criteria. This replaces the earlier nine broad presentation slices. Documentation PR #70 has landed. Remaining issue-specific blockers must still be verified before work.

| Ticket | Complete real-app outcome | Blocked by other tickets | Suggested route |
| --- | --- | --- | --- |
| [#72](https://github.com/TristanAlbers/christmas-quiz/issues/72) | Shared visual primitives and working login/waiting | None | Chat/GitHub; optional local Codex |
| [#73](https://github.com/TristanAlbers/christmas-quiz/issues/73) | TV 25-door cabinets, chocolate and public frost | #72 | Local Codex `ui_experience` |
| [#74](https://github.com/TristanAlbers/christmas-quiz/issues/74) | Compact phone puzzle, media and Hint/Skip | #72 | Local Codex `ui_experience` |
| [#75](https://github.com/TristanAlbers/christmas-quiz/issues/75) | Usable shop, dynamic price cards and armed red Reverse | #74 | Local Codex `ui_experience` |
| [#76](https://github.com/TristanAlbers/christmas-quiz/issues/76) | Safe, persistent frozen-team phone UI | #74 | Local Codex `ui_experience` |
| [#81](https://github.com/TristanAlbers/christmas-quiz/issues/81) | Attacking, impact and red-card Reverse choreography | #75, #76 | Local Codex `ui_experience` |
| [#77](https://github.com/TristanAlbers/christmas-quiz/issues/77) | Approved real Music TV/phone experience | #73, #74 | Local Codex `ui_experience` |
| [#82](https://github.com/TristanAlbers/christmas-quiz/issues/82) | Shared TV Challenge puzzle and minimal phone answer | #73, #74 | Local Codex `ui_experience` |
| [#78](https://github.com/TristanAlbers/christmas-quiz/issues/78) | Global gold Pause across modes, resume semantics | #76, #77, #82 | Local Codex `ui_experience` |
| [#83](https://github.com/TristanAlbers/christmas-quiz/issues/83) | One first winner, opponent continues, final tableau | #73, #74 | Local Codex `ui_experience` + invariant review |
| [#79](https://github.com/TristanAlbers/christmas-quiz/issues/79) | Admin READY, valid package selection and Start | #72 | Chat/GitHub or local Codex |
| [#84](https://github.com/TristanAlbers/christmas-quiz/issues/84) | Active Game Master control desk and safe Reset | #73, #79 | Local Codex `ui_experience` |
| [#80](https://github.com/TristanAlbers/christmas-quiz/issues/80) | Full integrated real-device/game-flow acceptance | #81, #78, #83, #84 | Chat + CI + local device rehearsal |

A ticket's listed blockers are **hard prerequisites**. Other tickets need not be implemented in exact row order. For example, after #72 lands, #73, #74 and #79 can be prepared concurrently in isolated branches; shared CSS/template changes should still be integrated sequentially against refreshed main. GitHub tool access currently offers text-based `Blocked by` references, not native dependency or sub-issue links. Follow the issue text to establish the frontier.

These are **vertical presentation slices**, not architectural layers: each connects existing server state/projection through actual rendered Django/HTMX UI and browser acceptance. No new schema or API is necessary by default; introducing one is a separately justified architecture decision, not a ticket-sizing trick.

**Mandatory reuse and prefactoring:** the repository already has entry theme tokens, a 25-door component and opening mechanism, Freeze/Reverse event handling, and confetti logic. Extend and converge on existing component boundaries before adding new ones. The small shared-style #72 ticket precedes themed gameplay changes; do not create a broad parallel CSS rewrite. Use the approved V4, Game Master V1 and Pause/Victory V1 mockups only as visual references, never as sources of fake clocks/costs/state.

**Visual-reference portability:** the standalone prototype pack exists outside the repository. An implementation agent must receive it in its workspace when screenshot/visual comparison is required; repository contract and issue acceptance remain authoritative, and the agent must never silently improvise missing mock details. No runtime dependency may be introduced on the reference pack.

## Each ticket's definition of done

1. **Early visual:** verify the relevant approved reference exists; implement a small real Django/HTMX slice, render one ordinary representative viewport and compare geometry/components/hierarchy. Run minimal render/security smoke checks. Missing reference means VISUAL BLOCKED.
2. **Owner checkpoint:** fix dominant discrepancies, show the user a reference-versus-real-Django capture, up to five differences and the SHA, then **STOP for explicit visual approval**. Do not spend tokens on routine design-skill chains or broad test/review cycles first.
3. **Required safety verification:** after approval, exercise applicable phone/tablet/TV sizes, long/media edge cases, accessibility, reduced motion, authorized public/private DOM, audio, focus/caret/pointer across 500ms polls, domain and recovery invariants. Preserve existing tests. GitHub CI owns the full suite and must be green at delivery.
4. **Review/landing:** mandatory current-base/head Ponytail PASS, green CI and Codex review, with valid findings resolved. Merge **only** with separate user authorization. #80 reuses prior accepted visual evidence and audits integrated gaps, including already-landed #72/#79.

## Issue starter — copyable handoff for Codex

```text
Work only on the selected Midnight Advent issue; continue its existing draft PR
if present. Check dependencies, AGENTS.md and the lean agent guide. Reuse the
current Django/HTMX app and protect server state/privacy/500ms polling. Verify
the approved local reference, render one comparable real-app screenshot, fix
significant layout mismatches, run small smoke checks and STOP for user visual
approval with the screenshot, remaining deltas and SHA. No blanket design
skills, multi-agent reviews or broad testing before this checkpoint. After
approval run required tests/CI, exact-base/head Ponytail and Codex review.
Never merge without separate authorization.
```

## Current frontier and visual gate

PR #70 and foundation #72/#79 are merged. The open #74 PR #87 has not passed product visual acceptance: continue that PR in a small corrective pass, capture the actual V4-versus-Django phone screen and stop for owner approval before final testing/review. A good CI result is not approval of appearance. Future tickets follow only their `Blocked by` prerequisites and the same lean workflow; avoid spending local Codex tokens re-reading long historical conversations or monitoring unchanged CI.
