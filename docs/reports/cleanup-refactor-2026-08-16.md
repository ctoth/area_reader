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

## Iteration 5 - `Merc semantic owner`

Slice read:
- Former Merc model and codec definitions in `area_reader/__init__.py`
- Merc writer, parser characterization, and JSONification callers

Surfaces:
- Merc semantic models and native codecs
  - Disposition: move
  - Owner after cleanup: `area_reader.dialects.merc`
  - Action: moved `MercArea`, `MercItem`, `MercMob`, `MercRoom`, `MercReset`, `MercExit`, `MercAffectData`, and their three Merc-native codecs with Rope.
  - Evidence: the resulting owner imports common semantics and ROM ancestry directly, with explicit constants and no package-root dependency.
- JSONification attrs-class discovery
  - Disposition: rewrite
  - Owner after cleanup: the actual model and dialect modules under test.
  - Action: added the Merc owner to the discovery module tuple.
  - Evidence: the contract continues to collect `524 tests` after Merc classes leave the root.

Gate results:
- Pass: Merc owner import smoke -> `area_reader.dialects.merc` for `MercArea` and `MercItem`.
- Pass: locked Merc/parser/JSON/error tests -> `734 passed in 8.75s`.
- Pass: Ruff on the changed production and test files -> `All checks passed!`.
- Pass: ownership search finds Merc semantic classes and codecs only in `area_reader.dialects.merc`.
- Pass: `git diff --check` -> no output.

Commit:
- `Extract Merc semantic models` (this iteration's commit).

Next slice:
- SMAUG semantic owner, then SWR/FUSS semantic owner.

## Iteration 6 - `SMAUG semantic owner`

Slice read:
- Former SMAUG model and codec definitions in `area_reader/__init__.py`
- SMAUG writer, parser characterization, and JSONification callers

Surfaces:
- SMAUG semantic models and native codecs
  - Disposition: move
  - Owner after cleanup: `area_reader.dialects.smaug`
  - Action: moved `SmaugArea`, `SmaugRoom`, `SmaugItem`, `SmaugMob`, `SmaugExit`, `SmaugRepair`, `SmaugMap`, `SmaugProgram`, and five SMAUG-native codecs with Rope.
  - Evidence: the resulting owner imports Merc/ROM ancestry and common owners directly, with explicit constants and no package-root dependency.
- JSONification attrs-class discovery
  - Disposition: consolidate
  - Owner after cleanup: the actual model and dialect modules under test.
  - Action: added the SMAUG owner to the discovery module tuple.
  - Evidence: the contract continues to collect `524 tests` after SMAUG classes leave the root.

Gate results:
- Pass: SMAUG owner import smoke -> `area_reader.dialects.smaug` for `SmaugArea` and `SmaugItem`.
- Pass: locked SMAUG/parser/JSON/error tests -> `718 passed in 8.18s`.
- Pass: Ruff on the changed owner and callers -> `All checks passed!`.
- Pass: ownership search finds SMAUG semantic classes and codecs only in `area_reader.dialects.smaug`.
- Pass: `git diff --check` -> no output.

Commit:
- `Extract SMAUG semantic models` (this iteration's commit).

Next slice:
- SWR/FUSS semantic owner.

## Iteration 7 - `SWR/FUSS semantic owner`

Slice read:
- Former SWR/FUSS model and codec definitions in `area_reader/__init__.py`
- SWR writer/property/parser and JSONification callers

Surfaces:
- SWR/FUSS semantic models and native codecs
  - Disposition: move
  - Owner after cleanup: `area_reader.dialects.swr`
  - Action: moved `SwrArea`, `SwrRoom`, `SwrObject`, `SwrMobile`, `SwrReset`, `SwrExit`, `SwrExtraDescription`, `SwrProgram`, `SwrUnknown`, and four SWR-native codecs with Rope.
  - Evidence: the resulting owner imports ROM/SMAUG ancestry and common owners directly, with no package-root dependency.
- JSONification attrs-class discovery
  - Disposition: consolidate
  - Owner after cleanup: the actual model and dialect modules under test.
  - Action: added the SWR owner to the discovery module tuple.
  - Evidence: the contract continues to collect `524 tests` after SWR classes leave the root.

Gate results:
- Pass: SWR owner import smoke -> `area_reader.dialects.swr` for `SwrArea` and `SwrObject`.
- Pass: locked SWR/parser/JSON/error tests -> `728 passed in 9.37s`.
- Pass: Ruff on the changed owner and callers -> `All checks passed!`.
- Pass: ownership search finds SWR semantic classes and codecs only in `area_reader.dialects.swr`.
- Pass: `git diff --check` -> no output.

Commit:
- `Extract SWR semantic models` (this iteration's commit).

Next slice:
- CircleMUD owner, then CoffeeMud XML owner.

## Iteration 8 - `CircleMUD semantic owner`

Slice read:
- Former CircleMUD model and codec definitions in `area_reader/__init__.py`
- Circle grammar/property/writer, parser characterization, and JSONification callers

Surfaces:
- CircleMUD semantic models and native codecs
  - Disposition: move
  - Owner after cleanup: `area_reader.dialects.circle`
  - Action: moved the ten Circle semantic classes, `CircleMobFlags`, and fourteen Circle-native conversion/rendering functions with Rope.
  - Evidence: the resulting owner imports ROM ancestry and common owners directly, with explicit constants and no package-root dependency.
- JSONification enum and attrs discovery
  - Disposition: consolidate
  - Owner after cleanup: one explicit `OWNER_MODULES` tuple.
  - Action: made both enum and attrs discovery traverse real owners, including Circle.
  - Evidence: an intermediate audit exposed `502 tests collected`; the repaired contract restores `524 tests collected`.

Gate results:
- Pass: Circle owner import smoke -> `area_reader.dialects.circle` for `CircleArea` and `CircleItem`.
- Pass: locked Circle/parser/JSON/error tests -> `713 passed in 9.11s`.
- Pass: Ruff on the changed owner and callers -> `All checks passed!`.
- Pass: ownership search finds Circle semantic classes and codecs only in `area_reader.dialects.circle`.
- Pass: `git diff --check` -> no output.

Commit:
- `Extract CircleMUD semantic models` (this iteration's commit).

Next slice:
- CoffeeMud XML semantic owner.

## Iteration 9 - `CoffeeMud XML semantic owner`

Slice read:
- Former CoffeeMud semantic/XML codec definitions in `area_reader/__init__.py`
- CoffeeMud writer, parser characterization, and JSONification callers

Surfaces:
- CoffeeMud semantic records and XML/native codecs
  - Disposition: move
  - Owner after cleanup: `area_reader.dialects.coffeemud`
  - Action: moved eight CoffeeMud semantic classes and twenty-one XML/native rendering functions with Rope in bounded batches.
  - Evidence: the resulting owner imports schema/native infrastructure directly and has no package-root dependency.
- JSONification owner discovery
  - Disposition: consolidate
  - Owner after cleanup: the explicit `OWNER_MODULES` tuple.
  - Action: added the CoffeeMud owner even though its current attrs fields do not add enum cases.
  - Evidence: the contract remains `524 tests collected`.

Gate results:
- Pass: CoffeeMud owner import smoke -> `area_reader.dialects.coffeemud` for `CoffeeMudArea` and `CoffeeMudItem`.
- Pass: locked CoffeeMud/parser/JSON/error tests -> `699 passed in 10.45s`.
- Pass: Ruff on the changed owner and callers -> `All checks passed!`.
- Pass: ownership search finds CoffeeMud semantic classes and codecs only in `area_reader.dialects.coffeemud`.
- Pass: `git diff --check` -> no output.

Commit:
- `Extract CoffeeMud semantic models` (this iteration's commit).

Next slice:
- Neutral shared parser, then dialect reader owners.

## Iteration 10 - `neutral shared parser`

Slice read:
- `ParseError` and `AreaFile` in `area_reader/__init__.py`
- Direct parser callers across lexical, grammar, writer, error, and JSON tests

Surfaces:
- Shared lexical/object parser
  - Disposition: move and rewrite
  - Owner after cleanup: `area_reader.parser`
  - Action: made construction neutral, moved SMAUG program parsing to its reader, moved `AreaFile` and `ParseError` with Rope, and replaced generated root/wildcard imports with direct shared owners.
  - Evidence: `parser.py` has no dialect or package-root import; `RomAreaFile` now explicitly declares `RomArea` as its model owner.
- Parser source file lifetime
  - Disposition: rewrite
  - Owner after cleanup: `AreaFile.__init__`
  - Action: replaced the manually opened/stored/closed file with a context manager and retained only parsed data plus filename.
  - Evidence: no later method uses a file handle.

Gate results:
- Pass: parser owner import smoke -> `area_reader.parser` for `AreaFile` and `ParseError`.
- Pass: direct parser/reader characterization -> `244 passed in 11.09s`.
- Pass: locked complete no-coverage suite -> `950 passed in 27.55s`.
- Pass: exact node-ID comparison against `c682de6` -> `current=950 baseline=950` with no differences.
- Pass: Ruff on the parser and changed callers -> `All checks passed!`.
- Pass: parser root/wildcard/dialect dependency searches -> no output.
- Pass: temporary detached worktree removal -> `exists_after=False`.

Commit:
- `Extract neutral shared parser` (this iteration's commit).

Next slice:
- Move all six reader classes to their dialect owners.

## Iteration 11 - `dialect readers, CLI, and package surface`

Slice read:
- Six reader classes remaining in `area_reader/__init__.py`
- `print_area`, `main`, console entry point, and accidental root constant/native callers

Surfaces:
- Dialect readers
  - Disposition: move
  - Owner after cleanup: their corresponding `area_reader.dialects.*` modules.
  - Action: moved all six reader classes with Rope and replaced transitional package-root/wildcard imports with direct parser, model, native, serialization, and ancestry imports.
  - Evidence: all reader `__module__` values identify their dialect owners; production root/wildcard dependency searches return zero matches.
- Area model construction
  - Disposition: rewrite
  - Owner after cleanup: each dialect reader's `create_area()` override.
  - Action: replaced forward class-body references with runtime model construction methods.
  - Evidence: readers may remain before their models in Rope-generated files without undefined-name imports or a shared-parser dialect dependency.
- Package and command-line surfaces
  - Disposition: consolidate
  - Owner after cleanup: reader-only `area_reader.__init__` and `area_reader.cli`.
  - Action: reduced `__init__.py` to explicit reader imports/`__all__`, moved CLI functions with Rope, and changed the console target to `area_reader.cli:main`.
  - Evidence: `init_lines=17`, `init_defs=0`, CLI smoke prints `cli_area_name=In the Air`.
- Import architecture
  - Disposition: enforce
  - Owner after cleanup: Import Linter configuration in `pyproject.toml`.
  - Action: forbade constants/model/native/parser/schema/serialization/values from importing dialects.
  - Evidence: `Contracts: 1 kept, 0 broken` across 16 files and 59 dependencies.
- Accidental root constants/native helpers
  - Disposition: delete
  - Owner after cleanup: `area_reader.constants` and `area_reader.native`.
  - Action: changed tests to use real owners and did not restore aliases.

Gate results:
- Pass: locked complete no-coverage suite -> `950 passed in 22.75s` before adding CLI characterization.
- Pass: exact configured coverage suite -> `950 passed in 71.92s`, total coverage `93%` before CLI characterization.
- Pass: CLI characterization -> `3 passed in 0.41s`.
- Pass: final exact configured suite with CLI characterization -> `953 passed in 81.87s`, total coverage `94%`.
- Pass: global Ruff -> `All checks passed!`.
- Pass: Vulture at 90% confidence -> no output.
- Pass: Import Linter -> `Contracts: 1 kept, 0 broken`.
- Pass: structural searches -> `init_defs=0`, `production_wildcards=0`, `production_root_imports=0`.
- Pass: `uv lock --check` -> `Resolved 27 packages in 1ms`.

Commit:
- `Move readers and CLI to explicit owners` (this iteration's commit).

Next slice:
- Final configured suite, build, writer-oracle availability checks, and fixed-point audit.

## Iteration 12 - `final fixed point`

Runtime oracle results:
- Pass: ROM accepted canonical `test/rom/air.are` and remained live through the boot window.
- Pass: Merc accepted canonical `test/merc/air.are` and remained live through the boot window.
- Not run: SMAUG upstream `C:/Users/Q/src/smaugfuss` is unavailable.
- Pass: SWR/FUSS accepted canonical upstream `area/limbo.are` and remained live through the boot window.
- Pass: CircleMUD accepted the canonical indexed world and remained live through the boot window.
- Pass: CoffeeMud canonical catalogs match their original loader baselines across six catalog families.

Final gates:
- Pass: exact configured suite -> `953 passed in 81.87s`, total coverage `94%`.
- Pass: CLI module coverage -> `100%`.
- Pass: root surface -> `17` lines, `0` definitions, `0` production wildcard imports, `0` production root imports.
- Pass: console smoke -> `cli_area_name=In the Air`.
- Pass: `uv lock --check` -> `Resolved 27 packages in 1ms`.

Distribution gates:
- Pass: `uv build` produced `area_reader-0.1.0.tar.gz` and `area_reader-0.1.0-py3-none-any.whl`.
- Pass: wheel inspection -> `wheel_required_modules_missing=0`.
- Pass: wheel console metadata -> `area-reader = area_reader.cli:main`.

Remaining gates before retention:
- None.

Final fixed-point results:
- Pass: global Ruff -> `All checks passed!`.
- Pass: Vulture at 90% confidence -> `vulture_findings=0`.
- Pass: Import Linter -> `Contracts: 1 kept, 0 broken` across 16 files and 59 dependencies.
- Pass: bytecode compilation -> no output.
- Pass: structural searches -> `init_defs=0 production_wildcards=0 production_root_imports=0`.
- Pass: `git diff --check` -> no output.

Fixed point:
- Every production definition has one real owner.
- Shared foundations cannot depend on dialects.
- The root contains reader exports only.
- No compatibility modules, forwarding wrappers, aliases, or duplicate model/parser paths were added.
