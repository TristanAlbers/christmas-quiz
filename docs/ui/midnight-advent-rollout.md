# Midnight Advent — implementation and validation rollout

**Status:** approved redesign, staged execution plan. **Companion contract:** [Midnight Advent](midnight-advent.md) and [agent/skill execution guide](midnight-advent-agent-guide.md). This is a presentation project; do not reset/reimplement phases or game rules in the historical `implementation_plan.md`.

## Working model

- Product/spec review, GitHub ticket drafting, bounded text/CSS fixes, CI/log triage, independent diff review and merge orchestration: **this chat + GitHub** (minimize local Codex consumption).
- Multi-file CSS/template/JavaScript work requiring rapid live Playwright/screenshot iterations or local Docker/browser/device testing: **local Codex**, `ui_experience` (Medium), scoped to **one ticket**. Use `integrator` only when a concrete projection/HTMX boundary must change; escalate `architect` or `persistence_security` only for a real cross-boundary ambiguity.
- Use existing `.agents/skills/midnight-advent-ui/SKILL.md`, `work-polling-ui`, `work-github-issue`, `execution-router`, `run-health`; use **installed** Anthropic Frontend Design and **installed, actually executed** Impeccable `critique`, `audit`, `polish`, and selective `animate` for real UI screens. If unavailable, mark those checks **NOT RUN** and distinguish manual review. Do not silently install third-party code or enable hooks; details in the agent guide. Run Ponytail only on a completed implementation diff at the mandatory gate, not to block exploration.
- Keep PRs small, single-purpose and draft until ready. Focused browser tests during implementation; full GitHub Actions on PR commits. Exactly-base/head `PONYTAIL PASS` and green CI precede Codex review; address comments in draft; never merge without explicit user authorization.

## Approved tracer-bullet delivery backlog (Matt Pocock `to-tickets`)

The parent [specification #71](https://github.com/TristanAlbers/christmas-quiz/issues/71) was converted into **13 approved, independently demonstrable tickets**; each issue now records its authoritative `Blocked by` references and its own acceptance criteria. This replaces the earlier nine broad presentation slices. The documentation-only PR #70 is the common prerequisite: implementation must not begin until this contract is merged.

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

1. Identify active state and available backend view context from repo; do not manufacture values.
2. Implement the smallest coherent screen/function; no domain changes unless explicitly approved.
3. Browser acceptance on changed device targets and edge cases, including actual 500ms polling, click/pointer/focus/modal continuity, no private data, no hidden controls.
4. Reduced-motion and Dutch copy check; viewport contrast and overflow verified.
5. Green required GitHub Actions for the exact head; independent invariant review only where behavior warrants.
6. Mandatory full-diff Ponytail review for exact base/head `PONYTAIL PASS`; ready-for-Codex review only after pass and green; fix meaningful remarks and repeat gates.
7. Chat performs safe-landing workflow **only when user requests merge**.

## First ticket starter — copyable handoff for Codex

```text
Implement only the named Midnight Advent issue on a fresh branch and draft PR.
Read AGENTS.md, docs/product-decisions.md, docs/ui/midnight-advent.md,
docs/ui/midnight-advent-agent-guide.md, .agents/skills/midnight-advent-ui/SKILL.md,
docs/ui/midnight-advent-rollout.md, the issue acceptance criteria, and
.agents/skills/work-polling-ui/SKILL.md. Route to ui_experience; use integrator
only for an explicit projection or HTMX contract need. Preserve all backend
rules, existing URLs, 500ms polling identity, private/public boundaries and
existing tests. Do not import standalone prototype mock state/JS wholesale.
Use installed Anthropic frontend-design and Impeccable critique/audit/polish where
available, with honest evidence of which commands actually ran. Use focused
Django-backed Playwright/browser screenshot iterations and report exact tests
and the pushed commit SHA. Stop after one bounded issue/PR. Do not merge.
```

## First implementation gate

Complete this **documentation-only PR** first, so future tickets cite one durable repository path. The ticket set #72–#84 has been published through the approved `to-tickets` flow; each ticket now includes a targeted, copyable **Agent implementation prompt**, skills and verification ownership. Select a frontier ticket, beginning with #72 **only after this PR is landed**. Avoid spending Codex credits asking it to reconstruct the visual conversation or to monitor CI. A follow-up review can inspect complete screens using preserved prototype screenshots and the shared acceptance criteria.
