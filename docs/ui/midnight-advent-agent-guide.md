# Midnight Advent — agent execution and visual quality guide

**Status: approved 2026-10-11 implementation handoff.** The *what* is defined in [the visual contract](midnight-advent.md), [parent spec #71](https://github.com/TristanAlbers/christmas-quiz/issues/71) and each issue's acceptance criteria. This guide defines *how agents should deliver and validate* a bounded ticket. Follow `AGENTS.md` first.

## Authority, precedence, and current status

1. The later, explicit user-approved decisions in `docs/product-decisions.md` override contrary **older presentation wording**, including the old stacked Hint/Skip rule, the obsolete "view private puzzle under ice" concept, and any early phase-status claims. They do **not** override unrelated safety/domain rules.
2. For the redesign's **appearance and behavior**, `docs/ui/midnight-advent.md` is the binding approved visual contract. The three approved prototypes (V4, Game Master V1, Pause/Victory V1) are reference images/HTML only. Do not copy fake timers, prices, state, UI-only event logic or invented nicknames from them.
3. The parent [spec #71](https://github.com/TristanAlbers/christmas-quiz/issues/71) contains user stories/testing/out-of-scope. The **13 implementation issues #72–#84** (plus final #80) describe the complete vertical slices and have authoritative `Blocked by` text. Labels such as `ready-for-agent` **do not** bypass the blockers.
4. The historical `implementation_plan.md` and phase-contract status lines are *not* permission to restart already implemented phases. Check live code/CI and `docs/ui/midnight-advent-rollout.md`.
5. If a visual requirement appears to conflict with an explicit private/public projection, server clock, gameplay rule or security invariant, the protected rule wins. Report and escalate the exact conflict to `architect`/`integrator`; don't silently change it. Do not weaken tests.

## Correct agent/skill routing

| Work type | Implementer / tool path | Required repo skills | External design skills |
| --- | --- | --- | --- |
| #72 visual foundation, #79 admin READY | Chat/GitHub default; local Codex `ui_experience` (Medium) when browser-driven iterations matter | `execution-router`, `work-github-issue`, `work-polling-ui` (where controls), `midnight-advent-ui` | Anthropic **frontend-design** for new/reshaped appearance; Impeccable **critique/audit/polish** for the real screen |
| #73 TV calendars/chocolates, #74 phone puzzle, #75 shop/Reverse, #76 persistent Freeze, #77 Music, #82 Challenge, #81 transient attacks, #78 Pause, #83 Victory, #84 active admin | Local Codex `ui_experience` (Medium); `integrator` only where proven approved view context missing | `work-github-issue`, `work-polling-ui`, `midnight-advent-ui`, `run-health` for long sessions | Use **frontend-design** to shape changed surface while honoring *already approved* Midnight Advent; run Impeccable **critique**, **audit** and **polish** on actual rendered pages. For #73, #76, #81 and #83 also use Impeccable **animate** when available. |
| #80 real-game audit/rehearsal | Chat/GitHub audit, local browser/devices for genuinely local checks | `run-health`, `work-polling-ui`, `midnight-advent-ui`; `test_invariants` for protected cross-view behavior | Impeccable **audit** and **critique** on integrated screens; report screen-by-screen findings |
| Any complete implementation PR | Original implementing specialist fixes findings; independent verifier when applicable | **`ponytail-review`** on complete current base/head diff, then Codex review, `land-prs` ONLY if user authorizes landing | Impeccable is design QA, **not** a replacement for Ponytail, game invariants, Playwright or CI. |

The `midnight-advent-ui` skill in this repository is **our own integration checklist**; it does not falsely claim Anthropic or Impeccable was installed. Their original sources:

- Anthropic: https://github.com/anthropics/skills/tree/main/skills/frontend-design
- Impeccable (P. Bakaus): https://github.com/pbakaus/impeccable and https://impeccable.style/ — current Codex distribution supports `$impeccable` with commands `critique`, `audit`, `polish`, `animate` as applicable.
- Matt Pocock: https://github.com/mattpocock/skills/tree/main/skills/engineering — `to-spec` and `to-tickets` were applied in this chat to spec #71 and tickets. **Do not rerun product discovery for each ticket.**

**Skill setup must be explicit and verified.** On the trusted *local Codex checkout*, inspect third-party source/license and install to the intended agent provider/scope, only with operator authorization. Official Impeccable setup: `npx impeccable install`, then `/impeccable init`; Codex requires inspecting/approving proposed `/hooks` separately. Its commands are invoked via `$impeccable` in Codex, not assumed to work as `/impeccable` commands. Anthropic's published skill can be installed through `npx skills add anthropics/skills --skill frontend-design` after source review. Do **not** add Node, these tools or their runtime files as a production dependency. Do not silently run a third-party installer or enable hooks; user-installed local/global skills are fine.

At start of a visual implementation, report **skill availability**: `frontend-design: installed / source-guidance only / unavailable`; `impeccable: installed and actually invoked / unavailable`. If Impeccable cannot be executed, still run browser screenshots + manual visual audit, **explicitly mark Impeccable gate NOT RUN** and flag for later independent review. Never claim a skill command ran merely because its principles were followed. Prefer completing a bounded code PR with the missing design gate identified over blocking non-design correctness fixes; do not call its aesthetic check completed.

## Visual acceptance loop (every UI issue)

1. Confirm every listed blocker is resolved **on main**, and read the issue, specific approved contract section, nearest existing template/CSS/JS and relevant previous tests. Identify what can be **reused**; do not restart the app architecture.
2. Document the existing behavior and the approved target for the selected surface. Choose *one* implementable end-to-end behavior and keep shared CSS refactors scoped. No mock data/state logic in production.
3. Build with the existing server projections, Django templates/HTMX and stable interactive surfaces. Do not remount still-valid inputs, dialogs or audio players every 500 ms. For momentary events, use existing event keys and one-shot transitions, not view-state-as-event.
4. Render the real app and take before/after browser evidence at **320/390px phone** for team screens, **tablet** for Game Master and **16:9/1920×1080** for TV where relevant. Exercise actual state, long text, image/audio/no-media fixtures, reduced motion, focus, pointer-down/poll/pointer-up, scroll/overflow and keyboard.
5. If external skills available: apply **frontend-design** to preserve the agreed distinctive creative direction (not invent a new one), run **Impeccable critique → audit → polish**, and **animate** for #73/#76/#81/#83 only when meaningful; review findings against product behavior, apply changes and rerender. If unavailable, record honest manual equivalents, not fake outputs.
6. Run focused browser tests, relevant existing domain/security/recovery invariants and changed-code lint. Leave full deterministic verification to draft PR GitHub Actions. Fix failures at root cause.
7. On complete diff, run repo `ponytail-review`; it must assess reuse/minimality **without deleting privacy, one-shot motion, polling controls, accessibility or distinct tests**. Record exact base/head PASS, obtain green required CI, then enable Codex review. New head/base invalidates PASS. No automatic merging.

## Common issue execution prompt

```text
Implement only GitHub issue #<ID> as one independently demonstrable
Midnight Advent vertical slice. Confirm PR #70 and all of this issue's
Blocked by dependencies have landed on main. Read AGENTS.md,
docs/product-decisions.md, docs/ui/midnight-advent.md,
docs/ui/midnight-advent-agent-guide.md and the issue.
Use repo skills work-github-issue, midnight-advent-ui, and work-polling-ui
where appropriate. Use ui_experience; call integrator only if needed
for an already-approved missing projection. Reuse existing components.
For actual UI styling use installed Anthropic frontend-design and
Impeccable critique/audit/polish (animate when appropriate); record
whether each skill was *actually executed*. If unavailable, do not fake
a pass. Work on a fresh short branch and draft PR, focused
Django-backed Playwright tests, screenshots for relevant target sizes,
and inspect private/public data and 500ms polling integrity.
Maintain strong tests. Run current-base/head Ponytail once complete,
then green CI, then Codex review. Report evidence + SHA and STOP.
Do not merge or tackle another issue.
```

Each ticket embeds a **specific handoff prompt** supplementing this common procedure. Avoid duplicating long skill instructions in every issue. No prompt, source mock, or external skill may override repo authority.
