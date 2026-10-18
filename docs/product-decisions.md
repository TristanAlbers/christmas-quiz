# Explicit product decisions

This file records later user-approved product decisions that intentionally refine or supersede older wording elsewhere in the repository. **Precedence is decision-specific rather than simply filename- or heading-based:** later explicit approved product decisions control the stated presentation questions; older guidance remains binding for everything else unless expressly superseded. It overrides older specifications **only for the specific decisions stated here**. All unrelated game rules and security/privacy requirements keep their existing authority.

## 2026-09-28 — playable runtime is Dutch-first

All normal participant-facing and operator-facing runtime surfaces are Dutch-first. This includes team login and waiting states, Advent puzzle interactions, Hint/Skip/shop/sabotage/Freeze/Uno Reverse/Challenge feedback, Music Quiz states, winner/final states, the public/TV overview and audio controls, and the Game Master interface. Player-visible content authored in the active game package should likewise be Dutch where it is intended to be read by players.

Internal contracts remain English where that protects stability and implementation clarity. Persisted state identifiers such as `READY`, `ADVENT_QUIZ`, `MUSIC_QUIZ`, `PUZZLE`, and `FREEZE`, URL names, audit identifiers, Python symbols, tests, and developer-facing documentation do not need to be renamed. Those technical identifiers must not leak into normal rendered UI; views translate them at the presentation boundary into stable Dutch labels. Product names and established game terms such as Uno Reverse may remain as named concepts.

This is a single-language product decision, not a requirement to add a general localization framework, locale selector, translation catalog, or English parity mode. Validation and recoverable runtime errors shown to players or Game Masters should use concise Dutch wording without exposing raw internal error codes.

## 2026-09-24 — UI/interaction is a first-class requirement

User-visible behavior is not complete merely because its backend mechanics work. Every phase that adds or changes user-visible behavior must include explicit presentation/interaction acceptance criteria and a dedicated UI/interaction implementation stage unless the contract demonstrates that no UI change is required.

The UI should develop a coherent Christmas visual language incrementally instead of deferring presentation until a late polish phase. Required visual semantics must not be replaced by raw text placeholders when the view specification calls for a visual representation.

Polling stability is part of correctness. Under the 500 ms HTMX polling architecture, controls that remain semantically valid must not be recreated in a way that loses focus, caret, native selection, hover/press state, touch interaction, or clicks. Browser regression coverage should exercise these interaction boundaries where relevant.

## 2026-09-24 — team Puzzle View stays focused on the current puzzle

The team Puzzle View intentionally does **not** render the persistent 25-door Advent progression grid. The Advent-calendar metaphor remains required wherever overall puzzle progression is presented: the shared public/TV overview and the administrative view both show the two teams' progression. On the team phone/tablet, the current puzzle is the active event/door experience without a separate persistent progression surface.

The team view groups its resource and status controls above the current-puzzle interaction, with the answer field below that resource area. This keeps the current puzzle and its usable actions prominent on a phone while avoiding a large duplicate overview.

This is a presentation decision only. Each team's independent sequential progression remains backend-authoritative, the authenticated team projection may retain its own progress data for state coordination, and all isolation, completion, recovery, and polling-stability requirements remain unchanged.

## 2026-09-24 — public Advent progression is approved

The shared public/TV overview may expose **coarse Advent progression for both teams** so viewers can follow the race. The approved public progression fields are limited to information needed to render the progression metaphor, such as:

- completed/current/future status for the 25 Advent doors/boxes;
- a concise progress count such as `13/25` or equivalent percentage;
- first-finisher / final-result information when already allowed by the game rules.

This is a deliberate exception to older wording that treated all team progression as private. It does **not** authorize exposing private puzzle content, answers, answer attempts, balances/coins, fragments, hints, Hint inventory, Uno Reverse state, private media, or other team-private data. Freeze and other hidden effects remain private except for the later 2026-09-28 decision below, which permits only the coarse frozen/not-frozen boolean on the normal Advent overview.

The public overview should present this progress using the Advent-calendar metaphor; percentage/count text alone is not sufficient.

## 2026-09-24 — specific visual requirements

The following are binding presentation requirements:

- Music Quiz progression is visually obvious across all 11 questions using a progress bar or clear step tracker in addition to the question number.
- Active Uno Reverse and available Hint tokens use deliberate visual card/token/badge treatment rather than raw text prompts.
- Skip remains an immediate completion action and should be presented as a styled action when available, not as stored inventory.
- Team/admin views target phone/tablet use; the shared overview targets desktop/TV use.

These decisions change presentation and approved public projection only. They do not change backend game legality, atomicity, team isolation for private data, or the authoritative state-machine rules.

## 2026-09-24 — team Music Quiz status is intentionally minimal

During the Music Quiz, team phone views should keep only the interaction and progress information needed to answer the active question:

- keep the existing 1–11 visual question tracker;
- keep the existing answer field and submission interaction;
- keep concise answer/result feedback needed for repeated attempts;
- do **not** show a separate `Question N of 11` status heading, elapsed-seconds counter, either team's Music score, previous-winner summary, or final-results countdown in the team status area.

The shared public/TV Music overview remains the place for the full question-number, timer, score, winner, and final-results status presentation. This specifically refines the earlier Music visual requirement: the phrase "in addition to the question number" applies to the public/TV overview, while the team phone view may use the 11-step tracker by itself for question progress.

This is presentation-only. It does not change Music Quiz state, scoring, answer legality, progression, polling architecture, or backend projections.

## 2026-09-25 — Challenge is free, distinct per team, staged, and public while active

Challenge is a once-per-team game action and **never costs points**. Starting it consumes only the initiating team's single Challenge opportunity. Point balance and affordability are not part of Challenge eligibility, initiation, retry, resolution, cancellation, or presentation.

A run can therefore contain at most two normally initiated Challenges: one initiated by Team A and one initiated by Team B. The package supplies a separate Challenge puzzle for each initiating team. Those two puzzles must have distinct identities, and a Challenge question must never be reused by another Challenge in the same run. Both teams still race on the same puzzle within one individual Challenge.

Starting a Challenge enters a server-authoritative **15-second** gathering/grace period before the puzzle becomes answerable. The puzzle and its media remain hidden during that period. The grace period uses Advent gameplay time, so Pause stops the countdown and Resume continues it. Refresh, reconnect, or process restart must recover the same remaining start period. Once it expires, both teams receive the puzzle through the normal synchronized polling path and unlimited penalty-free attempts begin.

While a Challenge is active, the shared public/TV overview switches from the Advent-calendar overview to a dedicated Challenge overview, analogous to the Music Quiz takeover. It may show the Challenge number within the two possible opportunities, initiating/challenged teams, gathering countdown, and—after the grace period—the shared Challenge title/body and first-correct-wins status. It must never expose correct answers, submitted attempts, balances, Hint/Reverse state, Freeze/private effects, private team state, or Challenge media unless separately approved.

These decisions intentionally override older Phase 6 wording that described a paid Challenge, one reusable shared package puzzle, immediate answer availability, or complete Challenge absence from the public/TV overview. All other Challenge outcome, atomicity, recovery, isolation, and polling-stability rules remain unchanged.

## 2026-09-27 — puzzle 25 cannot be skipped by players

Puzzle 25 is the final, game-winning puzzle and is an explicit exception to the generic player Skip rule. A player Skip request targeting the authoritative current puzzle 25 must be rejected before cost deduction or canonical completion. This remains true for stale/direct requests and for puzzle 25 becoming current again after administrative recovery/reopening.

Correct-answer completion of puzzle 25 continues through the normal canonical completion pipeline, including first-finisher and global-finish semantics. Administrator force completion remains a separate privileged completion route and is unchanged. Puzzles 1–24 keep the existing paid Skip behavior.

The team UI must not expose an enabled Skip action on puzzle 25. It may retain the visual action position as an explicitly disabled final-puzzle control, but frontend state is never the enforcement boundary.

## 2026-09-27 — Music opens with a gathering period

Issue #44 adds a fixed 60-second, server-authoritative gathering period before Music question 1. Gathering is a Music subphase: the global state becomes `MUSIC_QUIZ` and Advent gameplay is suspended as soon as puzzle 13 triggers Music. Pause freezes the Music clock, while refresh, reconnect, process restart, and active downtime recover from that same clock and do not restart gathering.

At 60,000 active Music milliseconds question 1 becomes available. Questions 2–11 still begin immediately after the preceding first-correct winner. Active Music questions remain unlimited in duration.

On the shared TV, an active question uses a decorative player-style progress bar labelled from `0:00` to `3:00`. The three-minute endpoint is not a deadline and does not advance, expire, or restrict a question. The bar does not inspect or represent the real audio duration or playback position.

## 2026-09-27 — Music Quiz display refinement

Player-facing Dutch copy names the mode `Muziek Quiz` as two words. On the shared TV, the active-question progress bar is a large visual element on the same fixed three-minute scale, without visible endpoint time labels. Its full state remains cosmetic: it does not advance or restrict the question and remains independent of audio duration and playback position.

## 2026-09-28 — public Advent overview branding, timer and Freeze visibility

The normal shared public/TV Advent overview is an event-facing surface, not a diagnostic state display. Its prominent game branding is **Quizzmass**. Raw backend/global-state labels such as `ADVENT_QUIZ` must not be shown to normal viewers, and technical wording such as `Advent Quiz in progress` should not be used as the main presentation.

Total Advent playing time is still derived exclusively from the existing server-authoritative gameplay clock, including its Pause and recovery semantics. The public overview formats that elapsed value as fixed `HH:MM:SS` for TV readability. Formatting is presentation-only and does not introduce a client-owned clock or reset behavior.

During the normal Advent overview, the public projection may expose **one additional coarse field per team: whether that team is currently frozen**. This is the only newly public team-state exception. It is sufficient to show a clear frost/ice treatment and textual Dutch `Bevroren` state. The public projection and UI must not expose Freeze remaining duration, source, cause, attacker, reflected-Reverse details, or any attack inventory.

All other private resource/effect boundaries remain in force. In particular, the public overview must not expose points/balances, Hint-token inventory, Uno Reverse state, fragments, submitted answers/attempts, private puzzle or hint content, private media, Challenge opportunities/inventory outside the dedicated active Challenge overview, or any other hidden team state. Music and active Challenge takeover screens retain their own separately approved projection rules and do not gain this Freeze field.

The Freeze treatment layers onto the existing festive Advent calendar so progression remains readable. Frozen state is communicated with text/iconography rather than color alone, and normal 500 ms polling should add/remove the treatment directly from authoritative state without relying on prior animation history. No enter/exit animation is required; any future animation must respect reduced-motion preferences.

## 2026-09-28 — normal team Puzzle View prioritizes points and contextual actions

The normal team Puzzle View uses a deliberately simpler phone-first hierarchy. The point balance is the dominant resource element. Earned fragments and Uno Reverse state remain visible as compact persistent resources. Raw backend state/status chrome such as `Game: ADVENT_QUIZ`, generic state badges, and permanently displayed resolved-Challenge results do not belong in normal play.

The earlier requirement that available Hint tokens receive deliberate visual treatment is retained but refined: Hint inventory is shown **inside the contextual Hint action bar**, not as a separate top-level Hint-token resource card. At the time this decision was recorded, the Hint action sat directly above Skip; the **later 2026-10-11 approval explicitly changes that arrangement to side-by-side when legible**, with vertical reflow allowed for small screens. It still communicates the remaining token count, and is visibly disabled when no token can legally be used. Skip communicates its point cost and affordability/legality; puzzle 25 remains an explicitly disabled final-puzzle exception. Backend command validation remains authoritative for both actions.

The answer interaction appears before the Hint/Skip action pair so the current puzzle remains the primary task. Still-valid answer, Hint, and Skip controls must remain mounted across ordinary 500 ms polling. Resource polling may update displayed points/fragments/Reverse state and mutate the text/disabled properties of those contextual actions, but must not replace the controls while their semantic puzzle context is unchanged.

Action/result feedback is contextual and transient. A newly resolved Challenge may briefly show its outcome, but ordinary polling must not restart that feedback interval or turn the result into permanent status chrome. This decision changes presentation only and does not alter game-state legality, costs, rewards, fragments, Challenge outcomes, or team isolation.

## 2026-10-11 — approved Midnight Advent visual overhaul

The product owner approves the **Midnight Advent V4** team/public visual language, **Game Master V1**, and **Pause & Victory V1**. On **2026-10-11**, the owner also approved using **Matt Pocock's `to-spec` and `to-tickets`** for the engineering handoff (skipping a separate `grill-me` interview as already done conversationally); the full spec is GitHub issue **#71** and the **13 independent, dependency-annotated implementation tickets are #72–#84**. Visual implementation uses the repo-owned `midnight-advent-ui` orchestration skill plus appropriately verified *genuine* Anthropic Frontend Design and Impeccable audits, and retains Ponytail/CI/Codex review gates. See [agent guide](ui/midnight-advent-agent-guide.md). The binding bounded design is documented in [`docs/ui/midnight-advent.md`](ui/midnight-advent.md) and its [rollout](ui/midnight-advent-rollout.md). Those documents refine **presentation only**; all unrelated normative gameplay, authorization, public/privacy, clock, challenge/music, and polling requirements remain binding.

Explicit presentation refinements of older view wording:
- On normal team phones, **Hint and Skip may sit side by side** when legible, rather than being vertically stacked; preserve contextual token/cost/disabled semantics and the no-Skip-on-puzzle-25 rule.
- A first-finishing team's brief confetti is followed by a **persistent, non-interactive winner tableau**. The other team continues, the TV retains an unobtrusive winner marker, and global `FINISHED` still requires both teams to complete puzzle 25.
- Global Pause has a distinct clear **gold/amber suspended** treatment for TV and teams, with no active player commands and correct preserved underlying mode/timers; a player Freeze retains the separate blue icy treatment, with **no private puzzle/hint/media rendered under ice**.
- Completed doors open to reveal Christmas chocolates. **The 2026-10-18 shaped-chocolate clue decision below supersedes the original rectangular, decorative-only treatment.**
- Armed Uno Reverse is conspicuous as a **red Reverse-style card**; purchase merely arms it, and a qualifying Freeze reflection gets a major event animation. The shop visibly shows **server-derived** costs and availability for Hint, Reverse, Freeze, and the free Challenge.
- The approved Music Quiz TV aesthetic is retained; Challenge phones keep only necessary shared puzzle and answer controls, and the shared Challenge question appears on TV only after its authoritative grace period.
- No invented team names: label teams **Team A** and **Team B**. Runtime remains Dutch-first. All new presentation effects support reduced motion and polling-stable interaction.

Standalone design prototypes are references, **not** production code or permission to hardcode sample values. This UI decision does not authorize a frontend framework migration, game-engine rewrite, new admin powers, or weakening existing tests.

## 2026-10-12 — Music gathering and final results are visually distinct

The approved dark Midnight Advent presentation covers the full Music lifecycle,
including the gathering countdown and the final-results interstitial. The
preparation countdown must have strong light-on-dark contrast, not the former
pastel Advent component colors.

The active Music question remains minimal on team phones under the 2026-09-24
decision. **Once question 11 is resolved**, the separate phone final-results
screen may show a prominent Music winner announcement, a celebratory one-shot
effect for the winning team, and a live countdown until Advent resumes. This
is distinct from the normal active-question *status area* prohibition on a
final-results countdown. The other team sees a respectful completion state,
without falsely being declared the Music winner; phone views do not expose
Music scores or opponent-private game information.

The TV is the shared scoreboard and must visibly declare the overall Music
champion from the authoritative accumulated score (not merely the winner of
question 11), with a legible final score and countdown until Advent returns.
Any brief confetti must respect reduced motion and must not replay on every
500ms poll or after reload. The Music champion is **not** the Advent first
finisher: there are no extra awards, puzzle completions, or rule changes.

Advent's authoritative gameplay clock intentionally stays stopped during
Music's gathering, questions, and final results, while Music's separate
authoritative clock governs the transition back. The UI must make this
distinction explicit. Game Master Pause freezes the Music countdown as well;
refresh, recovery, and return to Advent remain server-derived.

## 2026-10-12 — Music elapsed-time bar and live return display refinement

On the shared TV, the decorative Music bar begins empty at the start of
**each new question** and fills slowly across a fixed **three-minute**
illustrative scale, stopping when full. It represents the authoritative
question's elapsed Music time, **not** playback position or a question
deadline. Questions remain open indefinitely until a server-accepted answer
wins. Game Master Pause stops its movement; refresh and 500ms polling
reconstruct its position from the authoritative Music clock. The persistent
TV audio tray is visually centered beneath the Music stage without replacing
the underlying audio element.

During the separate final-results phase, the phone's visible return clock
must update continuously even while HTMX preserves the final-results card.
The existing 500ms team status poll carries fresh server time; a local
display-only ticker may interpolate between snapshots and must respect
Pause/Resume. The server exclusively determines the Advent-resume
transition, including after reload or recovery. The TV uses the same
display-only countdown principle.

## 2026-10-12 — Challenge gathering lasts 30 seconds

The product owner changes the earlier **15-second** Challenge gathering period to **30 seconds**. This is the authoritative grace duration for every Challenge and overrides the 2026-09-25 duration only; all previously approved costs, eligibility, per-initiator puzzles, one-opportunity-per-team rule, first-correct result, Pause/restart recovery, Freeze outcomes, and privacy guarantees are unchanged.

Both team phones and the public TV must visibly count down from the latest server-authoritative remaining time. A display-only tick may interpolate between the existing 500 ms polls, but it cannot reveal the question or enable an answer before the server ends gathering. The active TV shows both the public shared puzzle title **and the full readable question body**; the layout may scroll long shared text automatically without hiding the ordinary question or overlapping other TV content.


## 2026-10-18 — approved shaped-chocolate puzzle clues (#100–#102)

The approved #101 handoff replaces the rectangular decorative tiles with 11
shaped milk-chocolate subjects. These are public, earned clues for the final
puzzle, identical for both teams and across games. The fixed 25-door mapping
is recorded in `quiz/chocolate_manifest.json`; repeated subjects reuse the same
locally bundled PNG. Use the original approved bytes and proportional, optically
centred artwork, including intact wings, antlers and lights.

Only authoritative completed doors reveal chocolates, without visible subject
names or retained numbers. Closed-door numbers, hinges and progression remain.
Door 25's Santa is not required to solve puzzle 25: the necessary clues are
already earned before answering. This changes presentation/clue meaning only;
scoring, answers, canonical completion, game rules and privacy boundaries do not
change. No collection, gallery or zoom view is added. Existing surfaces that
render chocolates use this mapping; the team phone remains focused on its puzzle.

Reference: `quizzmas-chocolate-handoff-v1.zip`, SHA-256
`2c45c7f1d32bd740262869333117ffda80de52eb5ac1fef63e7eed8c7fa377ac`.
The supplied concepts and previews are approved design references, not production
code or authoritative state. Design approval does not substitute for explicit
approval of the live Django partial/full overview at 1920×1080. Preserve 500 ms
polling, one-shot reveal, reduced motion and refresh/reconnect recovery.
