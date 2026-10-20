# Midnight Advent — approved Quizzmass UI contract

**Status:** user-approved visual/presentation contract, 2026-10-11. **Scope:** the existing Quizzmass Django/HTMX presentation; **not** new game rules or a new frontend stack. See [rollout](midnight-advent-rollout.md) and [agent/skills handoff](midnight-advent-agent-guide.md) and [visual reference index](midnight-advent-visual-reference-index.md).

## 1. Authority and acceptance

Follow `AGENTS.md` and its authority order. The latest dated *approved* presentation decisions here and in `docs/product-decisions.md` supersede conflicting old aesthetic/layout advice, **not** normative game, security, privacy, clock, concurrency, polling, accessibility or recovery guarantees. The issue tracker [parent spec #71](https://github.com/TristanAlbers/christmas-quiz/issues/71) is the complete accepted user-story/testing statement; implementation issues #72–#84 take their directly applicable, bounded behavior from it. The dated decision in `docs/product-decisions.md` authorizes the presentation refinements below, including the explicit exceptions to older `Views.md` wording. Domain, security, public/private projection, timing, snapshot, gameplay, concurrency, recoverability, and authorization rules remain unchanged. If this contract seems to require new projection fields or state-transition behavior, report the exact discrepancy and route it to `architect`/`integrator` before coding; do not infer new authority from a standalone prototype.

The following have been explicitly approved by the product owner:
- **Midnight Advent V4:** TV and team screens; shop; chocolate; Uno Reverse; Freeze/attack effects; Music and Challenge treatments.
- **Game Master V1:** READY/ADVENT/PAUSED/MUSIC/CHALLENGE/FINISHED control desk.
- **Pause & Victory supplement V1:** global pause in all underlying modes; first finisher, continuing team, final results.

The approved prototype archive is a **handoff artifact currently outside GitHub**. If an implementation agent cannot see the actual screenshots/reference files, it must say so and use this written contract plus existing UI as its baseline, not claim visual fidelity to unseen pixels. Plan an explicit comparison review once those images are available. The exploratory standalone HTML prototypes are **visual references, not implementation source**. They use illustrative content/counters, mock actions, and no backend. Port only verified presentation patterns, not mocked game state or local timers.

## 2. Creative direction and foundation

**A candlelit Christmas mystery housed in a physical Advent cabinet.** Avoid generic dark dashboard components. Pair deep pine, burgundy, antique brass, candlelight highlights, and restrained parchment. A single visual system serves all screens but changes information density by purpose.

Suggested starting palette, subject to measured contrast in the running browser:

| Role | Starting value | Use |
| --- | --- | --- |
| Night | `#061815` | TV/phone background |
| Cabinet | `#10352B` | Advent board/surfaces |
| Brass | `#C9A46A` | borders, progress, ornament |
| Candlelight | `#F2DBA4` | important display accent |
| Burgundy | `#902E42` | numbered doors and marked actions |
| Letter paper | `#EEE0C2` | readable puzzle content (may darken if contrast retained) |
| Frost | `#B4E1EC` | player Freeze treatment |

Use local/system UI fonts for controls and a Georgia-like serif for editorial headlines; no remote fonts/assets or CDN dependency. Use common semantic tokens/component primitives across landing/login, team, admin, and public screens. Decorative motion never replaces textual feedback, disabled-state clarity, visible focus or keyboard support. Honor `prefers-reduced-motion`.

All ordinary player/operator copy is **Dutch-first**; use **Team A** and **Team B** only, without invented team names. The public brand is **Quizzmass**. Internal enum values must not appear in ordinary UI.

## 3. Screen and state contract

| Mode / surface | Public TV | Team phone / tablet | Game Master phone / tablet |
| --- | --- | --- | --- |
| READY | intentional waiting/identity state; no former-run private data | waiting for Game Master, no prior-run private state | package choice with diagnostics for invalid packages, explicit Start |
| ADVENT | paired 25-door Advent cabinets, counts, authoritative `HH:MM:SS`, coarse public Freeze signal only | compact point-first resource row, Reverse/fragment, conspicuous shop, puzzle/media, answer, Hint and Skip | twin progress boards, global Pause, team status/resources and permitted commands |
| MUSIC | approved Music Quiz takeover, 11-step tracker, scores, fixed cosmetic 3-min bar, TV audio enable/volume | minimal 11-step tracker, answer; gathering hides question/answer | current Music phase and scores with legitimate global controls |
| CHALLENGE | centered duel, 30s preparation; actual shared question on TV after preparation only | concise shared puzzle, answer and submit, no unnecessary explainer | challenge status/countdown without invented control powers |
| TEAM FREEZE | keep relevant cabinet visible with coarse `Bevroren` label; no timer/cause/Reverse on public UI | full-screen animated blue ice/blur effect, remaining authoritative Freeze time, no interactive controls | visible per-team status and legal administrative actions |
| GLOBAL PAUSE | amber/gold paused veil over the current underlying scene, timer stopped | clearly paused, no enabled answer/shop/sabotage/Challenge controls | prominent Resume, accurate retained underlying state |
| FIRST FINISHER | short one-shot confetti, then unobstructed twin cabinets + persistent compact first-winner ribbon | winner: confetti then **persistent winner tableau**, no actions; other team: brief nonblocking message, continue puzzle | first winner identified; global game still active |
| GLOBAL FINISHED | distinct final shared result with both 25/25 and the **one** first winner | winner remains winner; second team gets completion, **not a second win** | completed state and explicit admin-only Reset |

### Advent cabinet and chocolate
- Exactly 25 numbered doors per team on public TV and Game Master; **no persistent 25-door grid on the team Puzzle View**.
- Completed doors visibly hinge/open to reveal the **approved shaped milk-chocolate clues**, superseding the original rectangular embossed decorative tiles (product decision 2026-10-18; #101/#102). No visible names or retained numbers on completed doors.
- Use the 11 original transparent PNGs in `quiz/static/quiz/chocolates/` and the exact fixed mapping in `quiz/chocolate_manifest.json`, identical for both teams/across games. Repeated subjects reuse one file. Proportional viewports account for transparent margins with breathing room; wide lights and tall figures must remain intact and recognisable at TV size. Reserve symmetric clearance for the retained open-door edge and shadow as the viewport grows; keep visible artwork centred in each opening. Igloo/train use a modestly smaller optical height.
- Completed-door accessible names identify the earned chocolate subject; current/future accessible names never reveal it. Keep the artwork decorative to avoid duplicate announcements. Game Master compact completed slots show the same clues with their flap hidden; closed numbered slots retain the existing treatment.
- Only server-completed doors render clue artwork. These are earned final-puzzle clues; door 25's Santa is not needed to answer the finale. No new gallery/zoom/phone collection is introduced. Use the #101 handoff concepts and previews as references, never as production state/code.
- Current and future states remain distinguishable from completed, with readable numerals and accurate progress. Door opening is a **one-shot transition** when authoritative completed count advances, not every 500ms poll or every reload. On fresh load, completed doors render open without an animation storm.
- TV-level Freeze adds readable frost to the affected calendar **without replacing the calendar or hiding progress**. Only the public frozen boolean is exposed.

### Team Advent view and shop
- Phone hierarchy: compact identity + authoritative `HH:MM:SS`; prominent point balance; visible earned fragments/armed red Uno Reverse; conspicuous **Winkel**; current puzzle; answer; Hint/Skip.
- Hint and Skip are **side by side where width allows** (an explicit approved refinement to older vertical-stack wording). On very narrow screens/large type, adapt without clipped labels or too-small touch targets. Hint shows token count; Skip shows price/legality; puzzle 25 has **no enabled player Skip**.
- Support no-media, image, audio, hint-revealed, long question, tall image, and keyboard-open variants. Prefer fitting the common sample puzzle within a phone screen; do not truncate long puzzle content or shrink text below readable sizing to promise zero scrolling.
- Shop items must display name, concise effect, **high-contrast price independent of button text**, availability and action. Demo-package prices (illustrative only): Hint 1, Reverse 2, Freeze 3, Challenge gratis. Actual costs/affordability come from authoritative run snapshot/projection; never hardcode.
- Armed Reverse stays conspicuous on the phone; in the shop, it may remain listed with its price and the disabled label **Al actief**, instead of disappearing. Dynamic ineligibility/rejected requests remain clear; rejected shop action retains its dialog and feedback; successful purchase closes dialog before applicable presentation event.
- Red **Reverse-style card** (original local drawing/styling, not a required third-party brand asset) is used when armed and for the major reflection event. Buying only arms protection; reflection occurs only when a qualifying incoming Freeze is actually reversed.

### Transient attacks, Freeze, completion and accessibility
- Freeze launch, victim impact, reflected Reverse on both sides, chocolate-door reveal and first-winner confetti are **important, not optional decorative polish**.
- Preserve attack-first ordering. If reflected, show the outgoing attack followed by the red Reverse/return effect; attacker ultimately receives the authoritative Freeze, protected target remains unfrozen.
- Frozen team's page may show a **safe, generic blurred/ghosted silhouette** of an ordinary puzzle screen behind blue translucent ice. The actual private question, hint or media must **not** be rendered beneath the overlay. Controls are absent/non-interactable. Motion can include snow/crystals and settling frost, with an equally clear static reduced-motion mode.
- Stable statuses persist after one-shot effects; reconnect/reload recovers authoritative outcome without replaying old confetti/attack animations.
- Focus/caret/selection, open dialog, pointer-down/poll/pointer-up, real touch and keyboard interactions survive ordinary 500ms HTMX refreshes when the semantic context is unchanged. Preserve audio element identity and TV Music playhead on pause/resume.

#### Midnight Impact routine feedback (#107)

- A new accepted solve, Skip, Reverse purchase, or Hint purchase may emit a
  private `HX-Trigger-After-Swap` JSON event named
  `routineFeedbackConfirmed`. Its typed detail has `version`, stable opaque
  `eventId`, request `actionId`, `runId`, `kind`, and the server result-state
  context (`globalState`, `teamState`, current `questionId`, `musicPhase`,
  `challengePhase`, `firstFinisherTeamId`, and `gameplayElapsedMs`). Clients compare this context
  with the current authoritative screen before playback so a delayed response
  cannot cover a newer takeover.
- `kind` is one of `puzzle_solved`, `puzzle_skipped`, `reverse_purchased`, or
  `hint_purchased`. Completion events also carry the accepted puzzle `id` and
  door `number`, the exact manifest-derived chocolate `subject` and
  `staticUrl`, plus its `width`, `height`, trimmed `viewBox`, and `isBroad`
  optical-sizing flag. `nextNumber` exists only when a next Advent puzzle
  exists. Client
  code must not infer event meaning from English feedback, points, or clicks.
- Ordinary polls never contain this event. Sequential idempotent receipt
  retries omit it; concurrent duplicate responses retain the same `eventId`
  and `actionId`, which the client must deduplicate. Failed actions emit no
  success event. Run identity provides the reset/new-run boundary.
- Render each treatment as a non-dismissible full-phone takeover with the copy,
  object, and timing approved for #107. Puzzle 25, Pause, team Freeze/attack,
  active Challenge, Music, and final finish suppress routine feedback. A newer
  authoritative takeover cancels a playing treatment and clears its input/focus
  lock without queueing or replaying it.
- Hint purchase uses a layered parchment envelope: fully contained paper at
  rest, hinged flap opening first, then a slip rising through the mouth behind
  the front pocket. Keep the lower edge masked and avoid paper/flap
  intersections throughout the 2.7-second sequence.
- These four treatments deliberately keep their full motion and duration when
  `prefers-reduced-motion: reduce` is set: solve 3.5 seconds, Reverse purchase
  3.4 seconds, Skip 2.8 seconds, and Hint purchase 2.7 seconds. Scope this
  exception to the routine-feedback component; all other Midnight Advent
  reduced-motion rules remain unchanged.

### Global Pause
- Distinct **gold/amber** presentation (not icy blue); the underlying *safe* game scene is recognizable.
- Blocks answers and shop/sabotage/Challenge interaction client-side; backend remains the legality authority. Existing content may be shown **only when authorized for the same viewer**. Do not reveal a private puzzle during an underlying team Freeze.
- Works when pausing Advent, Music question/gathering/results, Challenge preparation/question, or an underlying Freeze. Server clocks, durations, Music playback and countdown projections resume correctly.
- Do not infer Pause or its target from animation history or synthetic browser time.

### Victory
- First team completing puzzle 25 becomes terminal and receives an impactful one-time presentation followed by a **durable, non-animated winner tableau**. Do not permit its controls, attacks or Challenge after finish. TV reverts to race with a compact winner notice. Other team still answers, purchases and progresses.
- Only after the second team completes puzzle 25 does global `FINISHED` occur. Final TV result identifies the first winner; the second team is congratulated for completion, not falsely declared winner. User interfaces recover to the same result after reload.
- Existing transient `endgame-celebration.js` timing alone is not sufficient for the permanent winner view; reuse its one-shot handling and backend markers, but establish the persistent team-finished layout in an appropriate stable projection.

### Game Master
- Operable, legible **regietafel**: high-contrast system status, Pause/Resume, compact twin boards, points and team controls. READY package diagnostics distinguish valid/invalid selections.
- Keep actual supported controls only. No fake Challenge winner selection, cancellation, editing completed puzzle history or recovery command unless separately implemented/authorized.
- Separate destructive Reset from ordinary actions and confirm it. Additional confirmations for impactful admin actions are UX proposals approved as visual treatment **only where existing command semantics support them**; do not break form/HTMX focus/submit behavior.
- Important state updates remain visible during Music, Challenge, Pause, and final finish. Native selects/number inputs and button presses must survive ordinary polling.

## 4. Safety, boundaries and validation

**Immutable boundaries:** Django 5.2 LTS, WSGI/Gunicorn, server templates, bundled HTMX, SQLite, WhiteNoise, Compose; server-authoritative clocks/gameplay and package costs; role/private-media boundaries; first-wins atomicity; exactly-once event/reward/receipt semantics; 500ms polling; recovery; offline LAN play. No SPA rewrite or framework introduced solely for aesthetics.

The public TV must never expose points, balances, fragments, Hint inventory, active Reverse, opponent-private puzzle/media, hidden attempts, Freeze countdown/cause/attacker, or answers. Show only explicitly approved public progress, coarse Freeze, first-winner and approved Music/Challenge content.

Each PR must have focused visual/browser acceptance, including:
1. 320px/390px phone, tablet and 1920×1080/16:9 TV fit; keyboard, focus, readable contrast and touch.
2. Real audio/image/long-text puzzle fixtures; normal phone can be compact but overlong content remains scrollable.
3. Player Freeze and global Pause differ visually/semantically; no private markup under frozen overlay.
4. Reliable state transitions under repeated polling, latency, refresh/reconnect and reduced motion; event animations occur once.
5. First-winner → other team continues → both finish; both winning-team permutations.
6. Existing integration/security/concurrency/recovery/Playwright tests remain stringent and green.

**Approved product**, not evidence of production validation: prototype Chromium smoke tests were isolated and mocked. Production acceptance still requires Django + HTMX browser tests and an actual-device rehearsal before the event.

## 5. Reference provenance

Design iteration trail: Midnight Advent V2/V3 → **approved V4**; **approved Game Master V1**; **approved Pause & Victory V1**. Older V2/V3 presentations and unapproved imaginary team names are superseded. These visual references can be kept in a downloadable design reference pack; the binding implementation decisions are in this document and `docs/product-decisions.md`, not the standalone demo scripts.
