"""Questions about a set of area files loaded together."""

import enum
import re
from collections import deque
from pathlib import Path

from attr import Factory, attr, attributes

import area_reader.cli

FAMILIES = ("rooms", "mobs", "objects")

# Every kind of vnum reference, with the atlas index that resolves it.
KINDS = {
    "exit_destination": "rooms",
    "exit_key": "objects",
    "reset_mob": "mobs",
    "reset_object": "objects",
    "reset_room": "rooms",
    "reset_container": "objects",
    "shop_keeper": "mobs",
    "special_mob": "mobs",
    "mob_program": "programs",
    "portal_destination": "rooms",
    "program_room": "rooms",
    "program_mob": "mobs",
    "program_object": "objects",
}
RESET_REFERENCES = {
    "M": (("arg1", "reset_mob"), ("arg3", "reset_room")),
    "O": (("arg1", "reset_object"), ("arg3", "reset_room")),
    "P": (("arg1", "reset_object"), ("arg3", "reset_container")),
    "G": (("arg1", "reset_object"),),
    "E": (("arg1", "reset_object"),),
    "D": (("arg1", "reset_room"),),
    "R": (("arg1", "reset_room"),),
}
# ROM act_enter.c: get_room_index(portal->value[3]).
PORTAL_DESTINATION_VALUE = 3
# ROM "mob" commands that take a vnum: the argument position after the command word, and what it names.
PROGRAM_COMMANDS = {
    "transfer": (2, "program_room"),
    "gtransfer": (2, "program_room"),
    "otransfer": (2, "program_room"),
    "goto": (1, "program_room"),
    "at": (1, "program_room"),
    "mload": (1, "program_mob"),
    "oload": (1, "program_object"),
}
# The commands that move a player; goto and at move the mob, otransfer an object.
PROGRAM_TRANSFERS = ("transfer", "gtransfer")
BARE_INTEGER = re.compile(r"\d+")


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


def direction_name(door):
    return door.name.lower() if isinstance(door, enum.Enum) else str(door)


def program_commands(code):
    """Yield ``(line number, text, command, vnum, reason)`` for each vnum-taking "mob" command in a program.

    Only a bare integer in the argument position ROM defines is a vnum; for
    anything else ``vnum`` is ``None`` and ``reason`` says why it was skipped.
    """
    for number, line in enumerate(code.splitlines(), start=1):
        words = line.split()
        if len(words) < 2 or words[0].lower() != "mob" or words[1].lower() not in PROGRAM_COMMANDS:
            continue
        command = words[1].lower()
        position = PROGRAM_COMMANDS[command][0] + 1
        if len(words) <= position:
            yield number, line.strip(), command, None, "no vnum argument"
        elif BARE_INTEGER.fullmatch(words[position]) is None:
            yield number, line.strip(), command, None, "argument is not a bare integer"
        else:
            yield number, line.strip(), command, int(words[position]), None


def is_portal(item):
    return item.item_type == "portal"


def references(atlas):
    """Yield ``(kind, label, where, vnum)`` for every vnum an area refers to, resolved or not."""
    for entry in atlas.areas:
        area = entry.area
        for room in area.rooms.values():
            for room_exit in room.exits:
                where = f"room {room.vnum} {direction_name(room_exit.door)}"
                if room_exit.destination > 0:
                    yield "exit_destination", entry.label, where, room_exit.destination
                if room_exit.key > 0:
                    yield "exit_key", entry.label, where, room_exit.key
        for reset in area.resets:
            for argument, kind in RESET_REFERENCES.get(reset.command, ()):
                where = f"reset {reset.command} {reset.arg1} {reset.arg2} {reset.arg3}"
                yield kind, entry.label, where, getattr(reset, argument)
        for shop in area.shops:
            yield "shop_keeper", entry.label, f"shop of keeper {shop.keeper}", shop.keeper
        for special in area.specials:
            if special.command == "M":
                yield "special_mob", entry.label, f"special {special.arg2}", special.arg1
        for mob in area.mobs.values():
            for mprog in mob.mprogs:
                yield "mob_program", entry.label, f"mob {mob.vnum} {mprog.trig_type} trigger", mprog.vnum
        for item in area.objects.values():
            if is_portal(item) and item.value[PORTAL_DESTINATION_VALUE] > 0:
                yield "portal_destination", entry.label, f"object {item.vnum}", item.value[PORTAL_DESTINATION_VALUE]
        for program, code in area.mobprogs.items():
            for number, text, command, vnum, _reason in program_commands(code):
                if vnum is not None:
                    where = f"program {program} line {number}: {text}"
                    yield PROGRAM_COMMANDS[command][1], entry.label, where, vnum


def dangling(atlas):
    """Every reference to a vnum no file in the set defines, by kind, and what was not treated as a reference."""
    unresolved = {kind: [] for kind in KINDS}
    for kind, label, where, vnum in references(atlas):
        if vnum not in getattr(atlas, KINDS[kind]):
            unresolved[kind].append({"area": label, "where": where, "vnum": vnum})
    exits = [
        {
            "area": entry.label,
            "room": room.vnum,
            "direction": direction_name(room_exit.door),
            "destination": room_exit.destination,
            "description": room_exit.description,
            "keyword": room_exit.keyword,
        }
        for entry in atlas.areas
        for room in entry.area.rooms.values()
        for room_exit in room.exits
        if room_exit.destination <= 0
    ]
    return {
        "references": unresolved,
        "counts": {kind: len(found) for kind, found in unresolved.items()},
        "exits_without_destination": {
            "count": len(exits),
            "with_description": sum(1 for row in exits if row["description"].strip()),
            "with_keyword": sum(1 for row in exits if row["keyword"].strip()),
            "with_neither": sum(1 for row in exits if not row["description"].strip() and not row["keyword"].strip()),
            "exits": exits,
        },
        "portals_without_destination": [
            {"area": entry.label, "vnum": item.vnum, "destination": item.value[PORTAL_DESTINATION_VALUE]}
            for entry in atlas.areas
            for item in entry.area.objects.values()
            if is_portal(item) and item.value[PORTAL_DESTINATION_VALUE] <= 0
        ],
        "program_lines_skipped": [
            {"area": entry.label, "program": program, "line": number, "text": text, "reason": reason}
            for entry in atlas.areas
            for program, code in entry.area.mobprogs.items()
            for number, text, _command, vnum, reason in program_commands(code)
            if vnum is None
        ],
    }


def depends(atlas):
    """For each area, the other areas that define vnums it refers to, counted by kind."""
    needs = {entry.label: {} for entry in atlas.areas}
    for kind, label, _where, vnum in references(atlas):
        index = getattr(atlas, KINDS[kind])
        if vnum in index and index[vnum][0] != label:
            needs[label].setdefault(index[vnum][0], {}).setdefault(kind, []).append(vnum)
    return {
        "areas": [
            {
                "file": label,
                "needs": [
                    {
                        "area": other,
                        "counts": {kind: len(found[kind]) for kind in KINDS if kind in found},
                        "vnums": {kind: sorted(set(found[kind])) for kind in KINDS if kind in found},
                    }
                    for other, found in sorted(others.items())
                ],
            }
            for label, others in needs.items()
        ]
    }


def exit_links(atlas):
    """Yield ``(from vnum, via, to vnum)`` for each exit whose destination is a room of the set."""
    for vnum, (_label, room) in atlas.rooms.items():
        for room_exit in room.exits:
            if room_exit.destination in atlas.rooms:
                yield vnum, direction_name(room_exit.door), room_exit.destination


def portal_links(atlas):
    """Yield a link for each portal an O reset places in a room; carried or contained portals have no room."""
    for entry in atlas.areas:
        for reset in entry.area.resets:
            if reset.command == "O" and reset.arg1 in atlas.objects and reset.arg3 in atlas.rooms:
                item = atlas.objects[reset.arg1][1]
                if is_portal(item) and item.value[PORTAL_DESTINATION_VALUE] in atlas.rooms:
                    yield reset.arg3, f"portal {item.vnum}", item.value[PORTAL_DESTINATION_VALUE]


def program_links(atlas):
    """Yield a link from the room an M reset loads a mob in to each room its programs transfer a player to."""
    for entry in atlas.areas:
        for reset in entry.area.resets:
            if reset.command == "M" and reset.arg1 in atlas.mobs and reset.arg3 in atlas.rooms:
                for mprog in atlas.mobs[reset.arg1][1].mprogs:
                    if mprog.vnum in atlas.programs:
                        for _number, _text, command, vnum, _reason in program_commands(atlas.programs[mprog.vnum][1]):
                            if command in PROGRAM_TRANSFERS and vnum in atlas.rooms:
                                yield reset.arg3, f"program {mprog.vnum}", vnum


def extra_links(atlas, portals, progs):
    found = []
    if portals:
        found.extend(portal_links(atlas))
    if progs:
        found.extend(program_links(atlas))
    return list(dict.fromkeys(found))


def walk(start, neighbours):
    """Return each vnum reachable from ``start`` mapped to the ``(previous vnum, via)`` that first reached it."""
    reached = {start: None}
    queue = deque([start])
    while queue:
        vnum = queue.popleft()
        for via, destination in neighbours.get(vnum, ()):
            if destination not in reached:
                reached[destination] = (vnum, via)
                queue.append(destination)
    return reached


def adjacency(links):
    forward = {}
    backward = {}
    for source, via, destination in links:
        forward.setdefault(source, []).append((via, destination))
        backward.setdefault(destination, []).append((via, source))
    return forward, backward


def room_row(atlas, vnum):
    if vnum not in atlas.rooms:
        return {"vnum": vnum, "name": None, "area": None}
    label, room = atlas.rooms[vnum]
    return {"vnum": vnum, "name": room.name, "area": label}


def reach_sets(atlas, start, links):
    """Return the rooms reachable from ``start`` and the rooms that can reach it, over ``links``."""
    if start not in atlas.rooms:
        return set(), set()
    forward, backward = adjacency(links)
    return set(walk(start, forward)), set(walk(start, backward))


def reach_totals(atlas, reachable, can_return):
    return {
        "rooms": len(atlas.rooms),
        "reachable": len(reachable),
        "can_return": len(can_return),
        "both": len(reachable & can_return),
    }


def reach(atlas, start, portals=False, progs=False):
    """Walk the set from room ``start``: what it reaches and what can come back, per area.

    Exits alone are followed unless ``portals`` or ``progs`` add the links of
    ``portal_links`` and ``program_links``; then the result also carries the
    exits-only totals and the rooms the added links gained.  A closed or
    locked door is still an exit.
    """
    walking = list(exit_links(atlas))
    extras = extra_links(atlas, portals, progs)
    links = walking + extras
    reachable, can_return = reach_sets(atlas, start, links)
    owned = {entry.label: [] for entry in atlas.areas}
    for vnum, (label, _room) in atlas.rooms.items():
        owned[label].append(vnum)
    leads_into = {atlas.rooms[destination][0] for source, _via, destination in links if crosses(atlas, source, destination)}
    leads_out = {atlas.rooms[source][0] for source, _via, destination in links if crosses(atlas, source, destination)}
    with_rooms = [label for label, vnums in owned.items() if vnums]
    result = {
        "start": room_row(atlas, start),
        "links": ["exits"] + ["portals"] * portals + ["programs"] * progs,
        "totals": reach_totals(atlas, reachable, can_return),
        "areas": [
            {
                "file": label,
                "rooms": len(owned[label]),
                "reachable": len(reachable.intersection(owned[label])),
                "can_return": len(can_return.intersection(owned[label])),
                "both": len((reachable & can_return).intersection(owned[label])),
            }
            for label in with_rooms
        ],
        "areas_not_reached": [label for label in with_rooms if not reachable.intersection(owned[label])],
        "areas_nothing_leads_into": [label for label in with_rooms if label not in leads_into],
        "areas_with_no_way_out": [label for label in with_rooms if label not in leads_out],
        "areas_without_rooms": [label for label, vnums in owned.items() if not vnums],
        "unreachable_rooms": [room_row(atlas, vnum) for vnum in atlas.rooms if vnum not in reachable],
        "no_return_rooms": [room_row(atlas, vnum) for vnum in atlas.rooms if vnum in reachable - can_return],
    }
    if portals or progs:
        walking_reachable, walking_return = reach_sets(atlas, start, walking)
        result["walking_totals"] = reach_totals(atlas, walking_reachable, walking_return)
        result["gained"] = {
            "reachable": [room_row(atlas, vnum) for vnum in atlas.rooms if vnum in reachable - walking_reachable],
            "can_return": [room_row(atlas, vnum) for vnum in atlas.rooms if vnum in can_return - walking_return],
        }
        result["extra_links"] = [
            {"from": source, "to": destination, "via": via} for source, via, destination in extras
        ]
    return result


def crosses(atlas, source, destination):
    return atlas.rooms[source][0] != atlas.rooms[destination][0]


def links(atlas):
    """The area graph over exits: who leads to whom, by how many exits, and which links are one-way."""
    pairs = {}
    for source, via, destination in exit_links(atlas):
        if crosses(atlas, source, destination):
            key = (atlas.rooms[source][0], atlas.rooms[destination][0])
            pairs.setdefault(key, []).append({"from": source, "direction": via, "to": destination})
    labels = [entry.label for entry in atlas.areas if any(owner == entry.label for owner, _room in atlas.rooms.values())]
    return {
        "areas": [
            {
                "file": label,
                "to": [
                    {"area": other, "exits": len(pairs[label, other]), "room_pairs": pairs[label, other]}
                    for other in labels
                    if (label, other) in pairs
                ],
                "from": [
                    {"area": other, "exits": len(pairs[other, label]), "room_pairs": pairs[other, label]}
                    for other in labels
                    if (other, label) in pairs
                ],
            }
            for label in labels
        ],
        "one_way": [
            {"from": source, "to": destination, "exits": len(found)}
            for (source, destination), found in sorted(pairs.items())
            if (destination, source) not in pairs
        ],
    }


def path(atlas, start, goal, portals=False, progs=False):
    """The shortest path from room ``start`` to room ``goal``; ``steps`` is ``None`` when there is none."""
    result = {"from": start, "to": goal, "missing": [vnum for vnum in (start, goal) if vnum not in atlas.rooms]}
    result["steps"] = None
    if result["missing"]:
        return result
    forward, _backward = adjacency(list(exit_links(atlas)) + extra_links(atlas, portals, progs))
    reached = walk(start, forward)
    if goal not in reached:
        return result
    steps = [{**room_row(atlas, goal), "direction": None}]
    vnum = goal
    while reached[vnum] is not None:
        vnum, via = reached[vnum]
        steps.append({**room_row(atlas, vnum), "direction": via})
    result["steps"] = steps[::-1]
    return result


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
