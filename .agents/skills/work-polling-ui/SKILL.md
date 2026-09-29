---
name: work-polling-ui
description: Implement or investigate HTMX/polling-sensitive UI behavior where normal 500 ms polling must preserve valid interactions, transient effects, media, focus, pointer behavior, or DOM identity. Use for polling regressions, replaying animations, replaced controls, overlays, persistent audio, and similar UI work.
---

Use this skill for UI changes where correctness depends on the relationship between server-authoritative state, HTMX polling, and browser lifecycle rather than static markup alone.

## Boundary and authority

- Follow `AGENTS.md`, `Views.md`, and `docs/polling-ui-guideline.md`.
- Backend state remains authoritative. Client code may preserve presentation state or DOM identity but must not invent game state.
- Normal 500 ms polling must not recreate still-valid interactive controls merely to refresh read-only state.
- Do not solve polling problems by reducing polling frequency, disabling synchronization, or moving authoritative behavior into browser-only state.

## 1. Identify the presentation class

Before editing, classify each affected element:

- **Persistent interactive node** — answer input, button, select, dialog, audio element, or control whose identity/focus/value/playhead must survive unchanged polls.
- **Read-only projection** — score, resource value, timer, eligibility text, status; may update frequently without disturbing stable controls.
- **Transient event presentation** — wrong-answer flash, door opening, Freeze impact, Uno Reverse activation, confetti; should play once for a newly observed authoritative action/event and not replay on ordinary polls/reload history.
- **Persistent authoritative surface** — frozen lock/result/banner/current mode; must reconstruct correctly from server state after reload and remain stable under polling.

Keep these concerns in separate swap/lifecycle boundaries where practical.

## 2. Choose the trigger correctly

Prefer:
- action responses for effects caused by the browser's own successful command;
- persisted monotonic event/revision identifiers for events that another actor can cause;
- authoritative state for persistent surfaces;
- an initial-load baseline that acknowledges existing history without replaying stale transient effects.

Do not use generic poll arrival, arbitrary timeouts, CSS animation events, or session-local guesses as substitutes for authoritative event/state boundaries.

## 3. Preserve interaction stability

For controls that remain semantically valid across a poll, preserve where applicable:
- exact DOM-node identity;
- focus and caret/selection;
- typed value;
- native open/interaction state;
- pointer-down -> poll -> pointer-up behavior;
- audio/video element identity, source semantics and playhead where required;
- dialog usability and explicit close behavior.

If authoritative context changes enough that a control is no longer valid, replace/reconcile it deliberately and test that transition separately.

## 4. Transient effects

Transient presentation must:
- trigger once per relevant newly observed event/action;
- not replay because of unchanged polling;
- not replay historical events on fresh/reloaded pages unless the product explicitly requires it;
- not block committed authoritative state reconciliation;
- use `pointer-events: none` when the effect is decorative and gameplay should remain available;
- provide a meaningful `prefers-reduced-motion` treatment.

Persistent outcomes remain visible through normal authoritative rendering after the transient effect ends.

## 5. Browser acceptance

Test the product invariant rather than incidental browser behavior. Prefer:
- response/OOB contents;
- DOM-node identity before/after multiple polls;
- focus, value and caret preservation;
- real pointer-down -> poll(s) -> pointer-up flows;
- event/revision advancement;
- reload non-replay plus correct persistent state;
- reduced-motion final state;
- phone/tablet/TV geometry where the requirement is layout-sensitive.

Avoid relying primarily on:
- raw `animationstart` counts;
- arbitrary sleeps;
- exact scheduling of CSS/JS events;
- fragile whitespace/text serialization when structural assertions express the invariant better.

## 6. Scope and routing

Use `ui_experience` as the primary owner for template/static/browser work. Add `integrator` only when projection/swap boundaries or Django orchestration must change. If durable event revisions, transactions, authorization, or concurrency semantics must change, route that bounded portion to the appropriate owner instead of hiding it in UI code.

For meaningful polling-sensitive changes, use `test_invariants` for an independent review when it materially improves confidence.

## 7. Handoff

Report:
- presentation classes/boundaries changed;
- authoritative trigger/state used;
- which nodes must remain stable and which may reconcile;
- focused browser acceptance run;
- reduced-motion and reload behavior;
- any remaining polling/UI debt.
