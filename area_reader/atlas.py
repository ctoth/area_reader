"""Questions about a set of area files loaded together."""

from pathlib import Path

from attr import Factory, attr, attributes

import area_reader.cli

FAMILIES = ("rooms", "mobs", "objects")


@attributes
class AreaEntry:
    label = attr(type=str)
    path = attr(type=Path)
    area = attr()


@attributes
class Atlas:
    """Every area of a set, with one vnum index per family.

    Each index maps a vnum to ``(label, record)``.  When two files define the
    same vnum the first file given keeps it; ``summary`` lists the clash.
    """

    areas = attr(default=Factory(list), type=list[AreaEntry])
    rooms = attr(default=Factory(dict))
    mobs = attr(default=Factory(dict))
    objects = attr(default=Factory(dict))
    programs = attr(default=Factory(dict))


def area_paths(paths):
    """Expand each directory to its ``*.are`` files in name order; keep files as given."""
    for path in map(Path, paths):
        if path.is_dir():
            yield from sorted(path.glob("*.are"))
        else:
            yield path


def load(paths, dialect=None):
    """Parse every area file into one ``Atlas``.  A file that does not parse raises the parser's error."""
    atlas = Atlas()
    for path in area_paths(paths):
        area = area_reader.cli.load_area(path, dialect).area
        entry = AreaEntry(label=path.name, path=path, area=area)
        atlas.areas.append(entry)
        for family, index in (
            ("rooms", atlas.rooms),
            ("mobs", atlas.mobs),
            ("objects", atlas.objects),
            ("mobprogs", atlas.programs),
        ):
            for vnum, record in getattr(area, family).items():
                index.setdefault(vnum, (entry.label, record))
    return atlas


def vnum_range(collection):
    return [min(collection), max(collection)] if collection else None


def overlaps(atlas, family):
    """Pairs of files whose vnum ranges for ``family`` intersect, with the vnums both define."""
    ranged = [(entry, getattr(entry.area, family)) for entry in atlas.areas if getattr(entry.area, family)]
    found = []
    for position, (first, first_records) in enumerate(ranged):
        for second, second_records in ranged[position + 1 :]:
            if min(first_records) <= max(second_records) and min(second_records) <= max(first_records):
                found.append(
                    {
                        "first": first.label,
                        "first_vnums": vnum_range(first_records),
                        "second": second.label,
                        "second_vnums": vnum_range(second_records),
                        "shared_vnums": sorted(set(first_records) & set(second_records)),
                    }
                )
    return found


def summary(atlas):
    rows = []
    for entry in atlas.areas:
        area = entry.area
        rows.append(
            {
                "file": entry.label,
                "name": area.name,
                "room_vnums": vnum_range(area.rooms),
                "rooms": len(area.rooms),
                "exits": sum(len(room.exits) for room in area.rooms.values()),
                "mobs": len(area.mobs),
                "objects": len(area.objects),
                # Comment lines in #RESETS are kept as resets without a command.
                "resets": sum(1 for reset in area.resets if reset.command is not None),
                "shops": len(area.shops),
                "mob_programs": len(area.mobprogs),
            }
        )
    totals = {"files": len(rows)}
    for count in ("rooms", "exits", "mobs", "objects", "resets", "shops", "mob_programs"):
        totals[count] = sum(row[count] for row in rows)
    return {
        "areas": rows,
        "totals": totals,
        "areas_without_rooms": [row["file"] for row in rows if not row["rooms"]],
        "overlaps": {family: overlaps(atlas, family) for family in FAMILIES},
    }


def find(atlas, text):
    """Rooms by name, and mobs and objects by name or short description, containing ``text``."""
    needle = text.lower()
    rooms = [
        {"vnum": vnum, "name": room.name, "area": label}
        for vnum, (label, room) in atlas.rooms.items()
        if needle in room.name.lower()
    ]
    result = {"text": text, "rooms": rooms}
    for family in ("mobs", "objects"):
        result[family] = [
            {"vnum": vnum, "name": record.name, "short_desc": record.short_desc, "area": label}
            for vnum, (label, record) in getattr(atlas, family).items()
            if needle in record.name.lower() or needle in record.short_desc.lower()
        ]
    return result
