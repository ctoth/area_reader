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
- `Add locked refactoring tools` (this iteration's commit).

Next slice:
- Public API contract and shared parser ownership.
