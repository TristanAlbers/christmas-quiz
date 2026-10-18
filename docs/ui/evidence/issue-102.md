# Issue #102 — live integration visual checkpoint

Branch: `feat/102-shaped-chocolate-clues` from main
`37bebd2ee9d870bc3ffef4d0e3fe46caf2acb611`. Visual checkpoint pushed at the user’s request for server testing.
Live implementation approval and final verification remain pending.

- [Approved actual-asset layout reference](issue-102/approved-all-open-reference.png)
- [Real Django overview: A 13/25, B 10/25](issue-102/partial-1920x1080.png)
- [Real Django overview: both 25/25](issue-102/full-1920x1080.png)

All images are 1920×1080. The source concept and enlarged asset sheet were also
inspected in the supplied #101 ZIP. Its hash and all 11 original PNG hashes match
the supplied manifest. No artwork regenerated or modified.

The screenshots use the existing browser test's disposable Django/SQLite fixture
and actual `/overview/` requests, local collected static assets, real projections
and 500 ms HTMX polling. Full progress is seeded without first-winner history so
the existing final victory overlay does not cover the artwork. It is an artwork
inspection fixture, not a change to completion rules or the production finale.

## Smoke evidence

- All 25 slots per team checked against the manifest; repeated subjects resolve
  to identical local asset URLs. Both teams agree.
- Partial state renders only the 23 earned chocolates; full state renders 50.
  Completed numbers are absent; closed numbers remain.
- Every artwork viewport fits inside its door opening, using proportional
  `xMidYMid meet` geometry and the handoff's padded visible bounds. Wings,
  antlers, figures and the lights cable are visually intact.
- All asset requests/decode checks succeeded; no page errors or HTTP failures.
- Calendar DOM identity survives unchanged polls; no initial reveal echo.
- Existing public Freeze/privacy and reduced-motion admin-completion browser
  smoke passed. All three existing calendar presentation checks passed, with
  the earned-only assertion updated for the new contract.
- Django system checks and `git diff --check` passed.

Only render and immediately implicated smoke checks run. Final browser matrix,
canonical completion/recovery checks, CI, Ponytail and Codex review remain after
explicit user approval. Existing browser assertions about the old decorative
cycle must then be adapted to the approved fixed/earned-only artwork contract.

## Differences from the handoff preview

1. Existing production header, clock, audio controls and cabinet layout consume
   more vertical space, so chocolates are smaller than the simplified full-open
   reference. These unrelated elements remain unchanged as requested.
2. Existing production hinges and open flap edges remain; the preview illustrates
   simpler gold door edges. Original PNGs, proportions and mapping match.

Live visual approval is pending. #102 and parent #100 remain open; no merging.
