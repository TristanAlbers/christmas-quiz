---
name: midnight-advent-ui
description: Implement one approved Midnight Advent Django/HTMX UI issue with a cheap reference-matching screenshot checkpoint, then rigorous safety tests and review after visual approval.
---

# Midnight Advent UI — lean integration skill

Read `AGENTS.md`, the selected issue and the **relevant** parts of `docs/product-decisions.md`, `docs/ui/midnight-advent.md` and `docs/ui/midnight-advent-agent-guide.md`. This repo skill does not install or impersonate Anthropic/Impeccable.

## Before work

1. Verify the issue's `Blocked by` items are landed on `main` (PR #70 already landed). Continue an existing draft PR when applicable; do not duplicate.
2. Verify the **actual** approved local reference HTML/PNG in `/home/tris/quizzmas-design-references/approved/`. If missing, report **VISUAL BLOCKED** and stop significant styling; do not claim a screenshot comparison.
3. Read only relevant current code/test seams. Reuse existing theme, 25-door, Freeze/Reverse, audio, confetti and HTMX component boundaries. Default to one implementer; escalate only for a concrete missing projection or protected invariant.

## Work cheaply before extensive verification

1. Implement the smallest issue-specific Django view change with real server-derived state, not prototype mock scripts, costs, timers or effects.
2. Immediately render one ordinary representative viewport/state and compare with the approved reference. Match composition, hierarchy, signature components and proportions—not just palette. Use separate stress fixtures later.
3. Run the smallest real-app render and implicated security/polling smoke checks. Preserve every existing assertion.
4. Show one accessible reference-versus-actual screenshot, up to five material deltas, changed files and SHA. After at most two non-improving attempts, **STOP for user visual approval or a specific blocker**. No blanket Impeccable, provenance verification, independent agent chain, broad test loops or review yet.

## Protected guarantees

- All server-authoritative game data, isolated team/public/admin projections and private media boundaries remain intact; no hidden private content under ice.
- Preserve 500ms HTMX stable controls, focus/caret, pointer-down/up, native input/audio nodes, one-shot event identity, server clocks, canonical completion, accessibility and reduced-motion outcomes.
- The first puzzle-25 winner does not end the global game; 25th puzzle Skip is disabled. Pause gold and Freeze blue must remain distinct.
- If an action affects security, concurrent state, replay or recovery, run the **corresponding focused invariant immediately** even before visual approval.

## After user visual approval

Run changed-scope browser/media/keyboard/reduced-motion tests and related existing invariants, then required GitHub CI. Current-base/head `PONYTAIL PASS` is mandatory before Codex review; rereview after meaningful changes. Do not weaken tests, claim unavailable skill execution, or merge without separate user authorization.

External `frontend-design` and Impeccable commands are **optional targeted tools** for real problems, not automatic compliance gates. For final integrated #80, reuse earlier evidence and perform a holistic audit only where helpful.

Detailed procedure: `docs/ui/midnight-advent-agent-guide.md`.
