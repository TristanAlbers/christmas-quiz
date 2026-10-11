# Issue #74 — team Advent panel evidence

One bounded Midnight Advent ticket. No backend rules/projections, new dependencies,
phone calendar grid, shop-content redesign, or other UI tickets are included.
Existing partial #74 edits were continued rather than discarded.

## Prerequisites and implementation

PR #70 merged as `c781e0fd05905320812e01651cbef48b1adb1474`; #72 landed
via PR #85 as `e33511f028b19a26c425eda4bac238392a59722a`. Both were verified
on main before implementation. Main subsequently advanced to
`4e77d7f35f2a3a60cac42351f6a8565cc5b39294` (admin READY, #79); the PR is
refreshed against it with both tickets' CI entries preserved.

The normal Advent question uses an editorial parchment section, readable serif
heading/body, contained images, existing native audio, answer form, and contextual
Hint/Skip. Resources stay point-first; fragments remain readable, armed Reverse
stays red, and Winkel is conspicuous. Actions share a row at 390px and reflow at
320px. All numbers, costs, timers, eligibility, question/media and resources remain
server-derived. No stable-control polling boundary or JavaScript was changed.

## Design skills — actual execution

- `frontend-design`: **USED**, loaded from
  `/home/tris/.agents/skills/frontend-design/SKILL.md`. Its guidance was applied to
  the actual Django screenshots: a product-specific pine/brass cabinet, one
  memorable parchment puzzle surface, local serif display, readable left-aligned
  copy, restrained resource chrome, visible selection/caret and focus. Changes
  include parchment typography, compact resources, active red Reverse, contained
  media and responsive controls. During the initial run, the installed file was
  compared byte-for-byte with official upstream at the user's request (matching
  SHA-256 `d91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3`).
  The resumed run followed the updated ticket and did not repeat that check.
- `impeccable`: **USED**, loaded from
  `/home/tris/.agents/skills/impeccable/SKILL.md`; `context` genuinely ran in the
  implementation pass using the installed engine in `/tmp/impeccable-cache`.
  The command references `critique`, `audit`, and `polish` were loaded and applied
  to rendered output. These are agent workflows, not fabricated CLI subcommands.
- `critique`: two isolated assessments, executed sequentially to respect the
  repository's one-specialist limit: `visual_critique` (design A) and
  `invariant_audit` (detector/browser evidence B). A was completed before B's
  findings entered synthesis. Source target: `quiz/templates/quiz/_question_pane.html`;
  runtime slug: `quiz-templates-quiz-question-pane-html`. No ignore list exists.
- `audit`: detector genuinely executed on `quiz/templates/quiz`: **0 findings**.
  Linked-stylesheet warnings reflect Django `{% static %}` syntax; actual CSS and
  rendered output were separately inspected. Independent technical audit:
  accessibility 3, performance 3, theming 4, responsive 4, integrity 4 = **18/20**.
  This is a bounded review score, not a WCAG certification.
- `polish`: reviewed the complete interaction path and diff; active Reverse and
  revealed-hint foregrounds were corrected, real audio/tall-image fixtures replaced
  incomplete fixtures, the old stacked-action assertion was updated to the approved
  side-by-side requirement, a redundant reduced-motion rule was removed, and final
  whitespace was cleaned. No tests were removed or weakened.
- Browser detector overlay: **NOT RUN**. A real `live-server --background` attempt
  in an isolated temporary directory failed with `Timed out waiting for live server
  to start`; `stop --keep-inject` confirmed no running server. No visible overlay is
  claimed. Actual Django/Chromium screenshots and interaction tests did run.

## Impeccable critique synthesis

Authored for Quizzmass: pine cabinet, brass divisions, parchment letter and burgundy
Reverse/Skip form a coherent Christmas mystery rather than a generic dashboard.
The before/after comparison preserves the approved phone hierarchy and Dutch copy.
Cognitive load is low: one mild single-focus issue at 320px, with the resource rows
occupying extra vertical space. Long content's scrolling is intentional.

| Nielsen heuristic | Score / 4 |
| --- | ---: |
| System status | 4 |
| Match with real world | 4 |
| Control/freedom | 3 |
| Consistency | 4 |
| Error prevention | 4 |
| Recognition | 4 |
| Efficiency | 3 |
| Minimalism | 3 |
| Error recovery | 3 |
| Contextual help | 3 |
| Total | **35/40** |

No P0/P1 finding. Remaining minor visual debt: 320px resource height, repeated
availability wording, and the footprint of disabled final Skip. Adding “van 25”
to the current-door label is an optional clarity improvement, not a grid requirement.
First-time users have labelled actions; keyboard users have native controls and
visible focus; mobile users have readable reflow but must scroll for long puzzles.
Questions skipped: the user explicitly fixed the bounded scope and forbade reopening
product design. No new design decisions were needed.

## Screenshots and visual comparison

Actual Django LiveServer + Chromium, authenticated team projection and snapshotted
fixture media. Local captures (generated, not production assets):

- `artifacts/ui-74-before/issue74-main-before-{320,390,768}.png`: true main templates
  at `e33511f`, captured in an isolated git archive with the same long/media fixture.
- `artifacts/ui-74/issue74-after-390-long-mixed-media.png`: long Dutch text, a real
  240×720 PNG, playable WAV, focus/caret and side-by-side actions.
- `issue74-after-320-no-media.png`, `issue74-after-768-tablet.png`,
  `issue74-after-390-reduced-motion.png`: no-media/revealed-hint and responsive states.
- `issue74-after-{320,390}-final-puzzle.png`: enabled answer, explicitly disabled Skip.
- `issue74-baseline-current-dom-390.png` is a CSS-disabled diagnostic, **not** the
  true main before screenshot.

Compared with available approved
`/home/tris/quizzmas-design-references/approved/quizzmas-midnight-v4-mobile.png`.
Readable content, point/shop emphasis and the approved palette are retained; the
production page uses real content/native audio rather than prototype state.
CI retains the after captures as artifact `midnight-advent-issue-74` on PR #87.

## Focused validation and review

- **14 browser tests passed** across `test_issue74_team_advent_panel`,
  `test_issue42_team_ui`, `test_issue39_puzzle_audio`, `test_live_sync`, and
  `test_interaction_stability`; Ruff on changed Python passed.
- **17 invariant tests passed** across integration final Skip/puzzle audio and
  security audio/team isolation. No unchanged full suite was rerun locally.
- New acceptance exercises actual typing/keyboard and input focus/caret at both
  phone widths, audio node/playhead across ordinary polls, Hint/Skip node identity,
  real mouse down → two 500ms polls → mouse up, semantic puzzle replacement,
  text/no-media, tall image, tablet, reduced motion, and final Skip at 320/390.
- Independent `test_invariants` review: **PASS**, no production/UI defect. Freeze
  still excludes private puzzle/hint/media; command validation and canonical
  completion remain unchanged.
- Physical phone keyboard occlusion, synthesized touch, assistive-technology use
  and a full independent computed-contrast scan are **NOT RUN**. Keyboard evidence
  is Chromium typing/tab navigation, not an on-device virtual keyboard claim.

Exact final CI and base/head Ponytail evidence are recorded in the PR description
so this document need not embed its own commit SHA. Codex review is prepared only
once CI and exact-pair Ponytail pass. No merge or issue closure is authorized.


## Final visual approval and integration (2026-10-11)

The initial checkpoint above predates the final user-approved visual remediation.
The completed phone view has readable larger typography at 390/320px, one contained
Hint/Skip title and status line per control, and two static red/gold ornament cards
instead of earned-fragment letter badges. Actual fragment earning/accounting has
not changed. The points label is separated from its number, and the parchment
reserves image-like height without media. Resolved Challenges no longer hide the
clock or trigger repetitive live announcements. Poll-safe answer/Hint/Skip, native
media, team isolation, and final-puzzle Skip restrictions are retained.

The four temporary root-level visual exploration scripts were omitted during
landing cleanup; the CI-backed Django screenshot fixture is retained. The actual
current-head screenshot artifact, CI result and current exact-pair Ponytail review
are linked from PR #87.
