"""Print the race and skill-name tables of a ROM 2.4 source tree as Python literals.

The output is pasted into ``area_reader/authoring/tables.py`` (``RACES`` and ``SKILLS``), so those tables are
copies of ``src/const.c`` rather than recollections of it.

    python scripts/extract_rom_tables.py C:\\Users\\Q\\src\\Rom24b6
"""

import argparse
import re
from pathlib import Path

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DOUBLED = ("aa", "bb", "cc", "dd", "ee")
FLAG_DEFINE = re.compile(r"(?m)^#define\s+(\w+)\s+\((\w+)\)")
RACE = re.compile(r'\{\s*"([^"]+)",\s*(TRUE|FALSE),([^{}]*)\}')
SKILL = re.compile(r'\{\s*"([^"]+)",\s*\{')


def table_body(text, declaration):
    start = text.index(declaration)
    return text[start : text.index("\n};", start)]


def letters(expression, defines):
    """Return a flag expression such as ``RES_FIRE|B`` as ROM flag letters in bit order."""
    names = []
    for term in expression.split("|"):
        term = term.strip()
        if term == "0":
            continue
        names.append(defines.get(term, term))
    order = [*LETTERS, *DOUBLED]
    # An area file spells the doubled letters aa..ee as single lower-case letters a..e.
    return "".join(name[0] for name in sorted(names, key=order.index))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("upstream", type=Path)
    arguments = parser.parse_args()
    source = arguments.upstream / "src"
    defines = dict(FLAG_DEFINE.findall((source / "merc.h").read_text(encoding="latin-1")))
    const = (source / "const.c").read_text(encoding="latin-1")

    print("RACES = {")
    for name, _pc, flags in RACE.findall(table_body(const, "race_table")):
        fields = [letters(field, defines) for field in flags.split(",") if field.strip()]
        if len(fields) != 8:
            raise SystemExit(f"race {name!r} has {len(fields)} flag fields, expected 8")
        print(f"    {name!r}: Race({', '.join(repr(field) for field in fields)}),")
    print("}")

    print("SKILLS = (")
    for name in SKILL.findall(table_body(const, "skill_table")):
        print(f"    {name!r},")
    print(")")


if __name__ == "__main__":
    main()
