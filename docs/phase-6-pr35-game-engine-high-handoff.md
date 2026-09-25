# PR #35 Challenge repair handoff

Status: game-engine-high packet complete, 2026-09-25. This is a repair handoff,
not a new Phase 6 contract.

## Domain outcome

- Challenge is free and the pure start decision always returns zero point delta.
  The retained compatibility `cost` argument now accepts only the integer `0`;
  boolean, float, negative, and positive values are invalid input.
- Each team retains its independent one-use opportunity. A spent opportunity is
  the stable eligibility/direct-command reason even while a later Challenge is
  transiently active.
- The 15-second gathering period is calculated from server gameplay time. The
  pure clock rejects negative values and impossible current-time regression.
- Existing domain outcomes remain unchanged: unlimited penalty-free wrong
  answers, first correct answer wins, no rewards/progression/Music, initiator
  win applies direct Freeze, and Uno Reverse remains preserved.
- Dedicated per-initiator puzzle selection and no run-level question reuse are
  correctly implemented outside the pure domain boundary by package validation
  and persistence constraints.

Changed in this packet:

- `quiz/domain/phase6.py`
- `tests/domain/test_phase6.py`

Focused validation: 16 Phase 6 domain tests pass; Ruff passes; `git diff
--check` passes.

## PR review and ancestry audit

All five original automated review findings have repository fixes and focused
regressions: HTTP-safe request-ID rotation, provenance-neutral Freeze copy,
finite numeric expected-answer validation, legacy-run opportunity hiding, and
durable winning-attempt pairing. No remaining finding belongs to the pure
domain layer.

The earlier main integration is correctly ordered. Commit
`f7c9bbeb6e306223c7e043acd1f9a295734c9cb8` (PR #38) is a direct ancestor of
the repaired Phase 6 history, followed by the Phase 6 replay and the focused
route reconciliation commit `f5c268bb37a97df7300474b2255cba6c54905ee3`.
GitHub CI also built synthetic merge `66ededee7632dda464fb7486f809f78a971c6cfe`
of PR head `16368c7c4e1709a7bb510e8b529634202f830c15` onto that base, so the current
failure is not a merge conflict or missing-base problem.

## Current CI blocker

Run `36156086571`, job `108141112390`, passes image build, Ruff, Django check,
migration parity, and all backend tests. Only these browser tests fail:

- `PhaseSixBrowserTests.test_free_start_gathering_tv_takeover_and_wrong_attempt_stability`
- `PhaseSixBrowserTests.test_initiator_win_freeze_admin_monitoring_and_tv_state`

Both time out waiting for `#challenge-answer-input` after
`_finish_grace_period()`. That helper sets `Run.gameplay_elapsed_ms` to exactly
15,000, but the Challenge was started after gameplay time zero. Therefore
`current_gameplay_ms - Challenge.started_gameplay_ms` remains below the required
15,000 ms and the server correctly keeps the Challenge in `starting`.

## Next owner and acceptance

Recommended next specialist: `ui_experience`.

Ownership is limited to the Phase 6 browser fixture/test and, only if reproduced
as a real presentation defect, the Challenge templates/static interaction.
Advance the test gameplay clock to at least
`Challenge.started_gameplay_ms + CHALLENGE_GRACE_PERIOD_MS`; do not shorten or
bypass the production grace rule.

Acceptance:

- both failed browser tests pass deterministically in the CI container;
- the team answer form and public puzzle remain hidden before the boundary and
  appear through polling at/after it;
- the Music-like public takeover, two distinct team puzzles, free initiation,
  polling-stable wrong attempts, and privacy assertions remain intact;
- no application, persistence, migration, or domain semantics are weakened;
- run the two Phase 6 browser tests, Ruff on changed files, and `git diff
  --check`, then return to the primary thread for commit/push/PR lifecycle.
