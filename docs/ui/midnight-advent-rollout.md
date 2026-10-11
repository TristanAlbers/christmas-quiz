# Midnight Advent — implementation and validation rollout

**Status:** approved redesign, staged execution plan. **Companion contract:** [Midnight Advent](midnight-advent.md). This is a presentation project; do not reset/reimplement phases or game rules in the historical `implementation_plan.md`.

## Working model

- Product/spec review, GitHub ticket drafting, bounded text/CSS fixes, CI/log triage, independent diff review and merge orchestration: **this chat + GitHub** (minimize local Codex consumption).
- Multi-file CSS/template/JavaScript work requiring rapid live Playwright/screenshot iterations or local Docker/browser/device testing: **local Codex**, `ui_experience` (Medium), scoped to **one ticket**. Use `integrator` only when a concrete projection/HTMX boundary must change; escalate `architect` or `persistence_security` only for a real cross-boundary ambiguity.
- Use existing `.agents/skills/work-polling-ui/SKILL.md`, `work-github-issue`, `execution-router`, `run-health`; use Impeccable critique as a **design review method** if not installed as an executable skill. Run Ponytail only on a complete implementation diff at the mandatory gate, not to block design exploration.
- Keep PRs small, single-purpose and draft until ready. Focused browser tests during implementation; full GitHub Actions on PR commits. Exactly-base/head `PONYTAIL PASS` and green CI precede Codex review; address comments in draft; never merge without explicit user authorization.

## Dependency-ordered PR slices

| Order | Deliverable | Primary owner / execution | Must prove |
| --- | --- | --- | --- |
| 0 | This contract and ticket packets | Chat/GitHub, docs-only | Approved decisions, user intent and authoritative rules reconciled |
| 1 | Shared Midnight Advent visual tokens and one noncritical entry surface (landing/login) | Chat/GitHub or Codex Medium if visual iterations needed | coherent reusable tokens, offline assets, no unexpected gameplay changes |
| 2 | Public TV Advent cabinet + door/chocolate motifs | Local Codex `ui_experience`; chat CI/review | 2 × 25, authoritative state, opening one-shot, readable on TV, public freeze boolean only |
| 3 | Compact team Advent puzzle + resources/media/Hint/Skip | Local Codex `ui_experience` | no 25-door team grid, focus stability, image/audio/long content, legal puzzle-25 Skip |
| 4 | Shop, costs, armed Reverse card | Local Codex `ui_experience` | authoritative dynamic prices, affordability/rejections, modal lifecycle and visibility |
| 5 | Player Freeze, attack/reflection, event-motion polish | Local Codex `ui_experience`; optional `integrator` if projection missing | correct event order, no leakage in frozen DOM, one-shot/reduced-motion |
| 6 | Music (visual preservation) and Challenge takeovers | Chat review + focused Codex UI work | Music unchanged semantically; public Challenge question only at proper phase; controls stable |
| 7 | Global Pause + first-winner/second-finish/finale views | Local Codex `ui_experience`, independent `test_invariants` | all pause submodes, actual music pause, first winner terminal, other team continues, final only after both |
| 8 | Game Master READY/active/modes/reset interface | Local Codex `ui_experience` | controls faithful, readable mobile/tablet, stable during polls, destructive action safe |
| 9 | Cross-screen polish/QA (may yield independent fixes) | Chat + CI, local Codex for hardware inspection only | representative phone/tablet/real TV, all flows, contrast/accessibility, reduced motion, long media |

**Avoid an oversized single PR.** Slices 2–8 should become separate GitHub issues with concrete acceptance, touched areas, owners and regression tests. Prefer serial integration because `app.css`, shared templates, and CSS tokens overlap. Merge foundations first; refresh main between PRs. For an issue, do not add speculative product features in the name of visual alignment.

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
docs/ui/midnight-advent-rollout.md, the issue acceptance criteria, and
.agents/skills/work-polling-ui/SKILL.md. Route to ui_experience; use integrator
only for an explicit projection or HTMX contract need. Preserve all backend
rules, existing URLs, 500ms polling identity, private/public boundaries and
existing tests. Do not import standalone prototype mock state/JS wholesale.
Use focused Playwright/browser screenshot iterations and report exact tests
and the pushed commit SHA. Stop after one bounded issue/PR. Do not merge.
```

## First implementation gate

Complete this **documentation-only PR** first, so future tickets cite one durable repository path. Then create and select the narrow first implementation issue. Avoid spending Codex credits asking it to reconstruct the visual conversation or to monitor CI. A follow-up review can inspect complete screens using preserved prototype screenshots and the shared acceptance criteria.
