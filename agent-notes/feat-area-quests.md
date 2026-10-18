# feat/area-quests (2026-10-18)

## Goal

Quests in the area source format (Mongoose hub `notes/quests.md` section 10 step 3): a `quests` key, built into
`--format json` for the Mongoose MOO loader, with a solution each quest ships with.

## State

- `source.py`: `quests` top-level key, merged by id like the record families (duplicate id refused).
- `builder.py`: `compile_quests` after `compile_helps`. Fields are `$quest`'s; references become
  `{room|mob|object: vnum}`; texts become lists of lines; checks: known keys, objective is event xor state,
  `@` match words, state's first argument a role, stage names unique, `after` resolves and has no ring,
  `needs`/`of` in range, credits need a giver, `solution` non-empty, `carried` (a `moved` objective's object
  needs the `take` wear flag). `--format rom` refuses a quest; `document` adds `quests`.
- Tests: 21 in `test_authoring.py` (search "quest"); full suite 1743 passed. Run with
  `uv run --extra test pytest -o addopts=""` (pytest-cov is not in the test extra here).
- MOO side and the guest walkthrough: hub `reports/quests-lost-ledger-acceptance-2026-10-18.md`.

## Decisions and why

- The source writes `$quest`'s own fields rather than tbaMUD's: the MOO engine is the target and tba's one
  objective per quest is a subset. Writing `.qst` for a tba target is not done.
- `giver` is left out of the JSON when absent: the MOO's JSON import has no clean null.
- Checks that need the whole world (giver placed by a reset, target reachable) are not in `build`; they belong
  in a `lint` over the JSON, not written.

## Next step

PR review and merge by Q; then the reset/reachability checks.
