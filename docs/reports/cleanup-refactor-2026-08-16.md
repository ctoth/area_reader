# Cleanup Refactor Fixed-Point Log - 2026-08-16

Target architecture:
- `area_reader.__init__` is an explicit public export surface with no production implementation.
- Shared model, parser, serialization, and native mechanics have one-way ownership.
- ROM, Merc, SMAUG, SWR/FUSS, CircleMUD, and CoffeeMud each own their models, codecs, and readers.
- The package import graph is acyclic and mechanically enforced.

Forbidden surfaces:
- Production classes or functions defined in `area_reader/__init__.py`.
- Wildcard imports, accidental package-global dependencies, compatibility modules, forwarding wrappers, and dual paths.
- Dialect-specific parsing behavior owned by the shared parser.
- Duplicate attrs models, writer metadata, native normalization ledgers, or parser implementations.

Search gates:
- `rg -n '^(class|def|async def) ' area_reader/__init__.py`
- `rg -n 'import \*' area_reader`
- `rg -n 'from area_reader\.__init__|import area_reader\.__init__' .`

Runtime gates:
- `uv run --locked --extra test --group refactor pytest -q`
- `uv run --locked --extra test --group refactor ruff check .`
- `uv run --locked --extra test --group refactor lint-imports`
- `uv run --locked --extra test --group refactor vulture area_reader --min-confidence 90`
- `uv build`
- `git diff --check`

## Iteration 1 - `tooling and provenance`

Slice read:
- `pyproject.toml`
- `uv.lock`
- `.github/workflows/ci.yml`
- `scripts/`

Surfaces:
- Project refactoring tools
  - Disposition: consolidate
  - Owner after cleanup: `[dependency-groups].refactor`
  - Action: lock Rope, Ruff, Import Linter, and Vulture with the project.
  - Evidence: Rope is a library with no console entry point and validates this project with `ropefolder=None`.
- Rope execution
  - Disposition: rewrite
  - Owner after cleanup: `scripts/rope_move.py`
  - Action: provide preview-first, one-symbol move execution with an explicit `--apply` switch.
  - Evidence: global user tool installation cannot expose a Rope executable.

Gate results:
- Pass: `uv lock --check` -> `Resolved 27 packages in 1ms`.
- Pass: `uv run --locked --group refactor python scripts/rope_move.py --help` -> preview/apply interface displayed.
- Pass: `uv run --locked --group refactor ruff check scripts/rope_move.py` -> `All checks passed!`.
- Pass: `uv run --locked --extra test --group refactor pytest -q` -> `950 passed in 71.68s`.
- Pass: `git diff --check` -> no output.

Commit:
- `b71a024 Add locked refactoring tools`.

Next slice:
- Public API contract and shared parser ownership.

## Iteration 2 - `serialization leaf owner`

Slice read:
- `area_reader/__init__.py:3905-3936`
- `test_jsonification.py`

Surfaces:
- `EnumNameConverter`
  - Disposition: move
  - Owner after cleanup: `area_reader.serialization`
  - Action: moved the converter with Rope and updated all callers to the real owner.
  - Evidence: serialization is independent of parser and dialect ownership.
- Rope symbol offset selection
  - Disposition: rewrite
  - Owner after cleanup: `scripts/rope_move.py`
  - Action: select the AST definition name rather than the `class` or `def` keyword.
  - Evidence: the original preview failed with `BadIdentifierError`; the corrected preview produced the intended global move.

Gate results:
- Pass: Rope preview showed only converter ownership and caller import changes.
- Pass: `uv run --locked --extra test --group refactor pytest -q test_jsonification.py --no-cov` -> `524 passed in 1.29s`.
- Pass: `uv run --locked --group refactor ruff check area_reader/serialization.py scripts/rope_move.py` -> `All checks passed!`.
- Pass: import smoke -> `area_reader.serialization`.
- Pass: `git diff --check` -> no output.

Commit:
- `6703e81 Extract serialization owner`.

Next slice:
- Shared model and parser ownership, beginning with leaf value/model symbols.

## Iteration 3 - `shared schema, values, and semantic models`

Slice read:
- `area_reader/__init__.py:39-424`
- Former common model and codec definitions in `area_reader/__init__.py`
- Shared-model callers in grammar, property, JSONification, and writer tests

Surfaces:
- Declarative attrs field factory
  - Disposition: move
  - Owner after cleanup: `area_reader.schema`
  - Action: moved `field()` out of the monolith and model graph.
  - Evidence: schema metadata is infrastructure used by every dialect, not a semantic model.
- Scalar parser value types
  - Disposition: move
  - Owner after cleanup: `area_reader.values`
  - Action: moved `Letter`, `Word`, and `VNum` to a dependency-free leaf module.
  - Evidence: model definitions and parser dispatch both consume these types.
- Shared Diku models and native codecs
  - Disposition: move
  - Owner after cleanup: `area_reader.model`
  - Action: moved `ExtraDescription`, `MudBase`, `Item`, `Dice`, `Help`, `Exit`, `Room`, `Reset`, and `Special` plus their native codecs.
  - Evidence: these are cross-dialect semantic models; direct constants/native/schema/value imports eliminate package-root cycles.
- Accidental `area_reader.random` exposure
  - Disposition: delete
  - Owner after cleanup: `area_reader.model.random`, as the private dependency of `Dice`.
  - Action: updated the RNG test to patch the real owner and did not add a package re-export.

Gate results:
- Pass: focused shared-model/property tests -> `687 passed in 7.94s`.
- Pass: common owner import smoke -> all complex common types report `area_reader.model`.
- Pass: Ruff on `model.py`, `schema.py`, and `values.py` -> `All checks passed!`.
- Pass: baseline/current node-ID comparison -> `current=945 baseline=945` with no differences.
- Pass: `uv run --locked --extra test --group refactor pytest -q` -> `945 passed in 71.43s`, total coverage `93%`.
- Pass: ownership searches find each moved surface only in its new owner.
- Pass: `git diff --check` -> no output.

Commit:
- `64fe286 Extract shared schema and models`.

Next slice:
- ROM dialect owner, then dependent Merc/SMAUG/SWR owners.

## Iteration 4 - `ROM semantic owner`

Slice read:
- Former ROM model and codec definitions in `area_reader/__init__.py`
- ROM grammar, writer, JSONification, and SWR armor-class callers

Surfaces:
- ROM semantic models and native codecs
  - Disposition: move
  - Owner after cleanup: `area_reader.dialects.rom`
  - Action: moved `RomArea`, `RomMob`, `RomCharacter`, `RomMobprog`, `RomArmorClass`, `RomItem`, `RomAffectData`, and their ROM-only codecs with Rope.
  - Evidence: direct shared-owner and explicit constant imports leave the dialect module independent of the package root.
- ROM/Merc shop record
  - Disposition: move
  - Owner after cleanup: `area_reader.model.RomShop`
  - Action: moved the shared shop record and trade-type codec to the common semantic owner.
  - Evidence: both ROM and Merc readers use the same record and five-slot native contract.
- Root-only conversion lambdas
  - Disposition: delete
  - Owner after cleanup: `area_reader.dialects.rom.multiply_10`; no owner for unused `mark_as_npc`.
  - Action: replaced the armor converter with a named dialect-local function and deleted the unused NPC lambda.

Gate results:
- Pass: ROM owner import smoke -> `area_reader.dialects.rom` for `RomArea` and `RomItem`.
- Pass: focused ROM/error tests -> `91 passed in 4.16s`.
- Pass: locked affected ROM/JSON/SWR tests -> `659 passed in 7.47s`.
- Pass: JSONification contract discovery remains `524 tests collected` after moving it to the real model owners.
- Pass: Ruff on the changed production and test files -> `All checks passed!`.
- Pass: ownership search finds ROM semantic classes and codecs only in `area_reader.dialects.rom`.
- Pass: `git diff --check` -> no output.

Commit:
- `Extract ROM semantic models` (this iteration's commit).

Next slice:
- Merc semantic owner, followed by SMAUG and SWR dependency owners.
