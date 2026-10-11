---
name: midnight-advent-ui
description: Implement and review one approved Midnight Advent UI ticket with true source-of-truth Django state, polling-safe controls, and explicitly verified visual quality skills. Use for Quizzmass issues #72–#84 and final UI acceptance #80.
---

# Midnight Advent UI — implementation skill

Read `AGENTS.md`, the issue, `docs/product-decisions.md`, `docs/ui/midnight-advent.md`, and `docs/ui/midnight-advent-agent-guide.md`. This is a local integration skill and does **not** install or impersonate Anthropic/Impeccable.

## Before coding

- Confirm issue `Blocked by` edges including **PR #70 merged** and all predecessor issues **landed on main**. `ready-for-agent` label does not override blockers.
- Route to the smallest specialist(s) per `.agents/skills/work-github-issue/SKILL.md` and `.agents/skills/execution-router/SKILL.md`. Prefer `ui_experience` for UI; add `integrator` only for a demonstrated missing approved projection.
- Read the existing code/test seam. Existing shared `theme.css`, calendar opening, sound, Freeze, attack, endgame and HTMX behaviors should be reused, not cloned into new helpers by default.
- Confirm actual external design skills installed **before claiming use**: https://github.com/anthropics/skills/tree/main/skills/frontend-design and https://github.com/pbakaus/impeccable. On Codex, prefer installed `$frontend-design` / `$impeccable`. No silent install/hook approval; report any unavailable skill.

## During work

- Protect role-specific projections: no public balances/fragments/hints/Reverse or private media; no actual private puzzle/hint/media DOM behind the frozen overlay.
- Use state/event values supplied by Django, never fake frontend prices/clocks/rules. Global Pause is **gold**, per-team Freeze is **blue**, and 25th-puzzle first-finish doesn't globally end game.
- Stable interactive DOM identity under **500ms polling**; semantic context changes may swap. Use `.agents/skills/work-polling-ui/SKILL.md` with focus, caret, pointer, modal, audio and animation-once checks.
- Render actual Django pages, not only an HTML demo. Compare before/after screenshot against approved references, test narrow phone, relevant TV/tablet, media fixtures, keyboard and reduced-motion.
- When installed, apply Anthropic `frontend-design` to the **approved** direction and Impeccable `critique`, `audit`, `polish`; for theatrical interaction also `animate`. Inspect findings and address meaningful issues.
- Mark missing external skill runs **NOT RUN** rather than asserting equivalent execution. Manual visual critique can be recorded separately.

## End of bounded ticket

Run focused tests and browser checks, green CI on draft PR; independent `test_invariants` when protected behavior is touched; current SHA-bounded `ponytail-review` for minimal correct diff; then ready-for-Codex review. Report exact tests/screens/skill execution, changes and blockers. Never merge without explicit instruction.

Read the detailed acceptance/handoff: `docs/ui/midnight-advent-agent-guide.md`.
