"""Derive the per-level default mana dice for authored mobs from the stock ROM areas.

Rom2.4.doc Appendix A recommends hit points, armor class and damage by level but has no mana column, so the
mana default is measured instead of invented: for each level, the mana dice of the stock mobile whose average
mana is the (lower) median among the stock mobiles of that level. A level no stock mobile has takes the dice
of the nearest lower level that has one. The output is pasted into ``area_reader/authoring/tables.py``
(``STOCK_MANA_BY_LEVEL``).

    python scripts/derive_rom_mob_defaults.py test/rom
"""

import argparse
from pathlib import Path

import area_reader.dialects.rom

LEVELS = range(1, 61)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("areas", type=Path)
    arguments = parser.parse_args()

    by_level = {}
    for path in sorted(arguments.areas.glob("*.are")):
        area_file = area_reader.dialects.rom.RomAreaFile(path)
        area_file.load_sections()
        for mob in area_file.area.mobs.values():
            mana = mob.mana
            average = mana.number * (mana.sides + 1) / 2 + mana.bonus
            by_level.setdefault(mob.level, []).append((average, mana.number, mana.sides, mana.bonus))

    print("STOCK_MANA_BY_LEVEL = {")
    previous = None
    for level in LEVELS:
        samples = sorted(by_level.get(level, []))
        if samples:
            _average, number, sides, bonus = samples[(len(samples) - 1) // 2]
            previous = (number, sides, bonus)
            note = f"median of {len(samples)}"
        else:
            note = "no stock mobile; previous level"
        if previous is None:
            raise SystemExit(f"no stock mobile at or below level {level}")
        number, sides, bonus = previous
        print(f'    {level}: "{number}d{sides}+{bonus}",  # {note}')
    print("}")


if __name__ == "__main__":
    main()
