"""Preview or apply one Rope global-symbol move.

The script deliberately moves one top-level class or function at a time so
each ownership change can be inspected and tested before the next move.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

from rope.base.project import Project
from rope.refactor.move import create_move


def symbol_offset(source: Path, symbol: str) -> int:
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(source))
    node = next(
        (
            candidate
            for candidate in tree.body
            if isinstance(candidate, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and candidate.name == symbol
        ),
        None,
    )
    if node is None:
        raise SystemExit(f"top-level symbol {symbol!r} not found in {source}")
    return len("".join(text.splitlines(keepends=True)[: node.lineno - 1]).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("symbol")
    parser.add_argument("destination", help="Importable destination module")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    project = Project(".", ropefolder=None)
    try:
        project.validate(project.root)
        source = project.get_file(args.source.as_posix())
        destination = project.find_module(args.destination)
        if destination is None:
            raise SystemExit(f"destination module {args.destination!r} does not exist")
        mover = create_move(project, source, symbol_offset(args.source, args.symbol))
        changes = mover.get_changes(destination)
        print(changes.get_description())
        if args.apply:
            project.do(changes)
    finally:
        project.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
