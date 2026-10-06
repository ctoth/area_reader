"""Questions about a set of area files loaded together."""

import argparse
import enum
import json
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
    crossing = [(source, destination) for source, _via, destination in links if crosses(atlas, source, destination)]
    leads_into = {atlas.rooms[destination][0] for _source, destination in crossing}
    leads_out = {atlas.rooms[source][0] for source, _destination in crossing}
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
        result["extra_links"] = [{"from": source, "to": destination, "via": via} for source, via, destination in extras]
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
    owners = {label for label, _room in atlas.rooms.values()}
    labels = [entry.label for entry in atlas.areas if entry.label in owners]
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


def joined(items):
    return ", ".join(map(str, items)) if items else "none"


def room_line(row):
    return f"  {row['vnum']} {row['name']} ({row['area']})"


def room_list(title, rows, show):
    """Return the lines of a room list: its count, and the rooms themselves only when ``show``."""
    if not rows or show:
        return [f"{title}: {len(rows)}", *map(room_line, rows)]
    return [f"{title}: {len(rows)} (list them with --rooms)"]


def totals_line(totals):
    return f"Reachable: {totals['reachable']}. Can walk back: {totals['can_return']}. Both: {totals['both']}."


def summary_text(result, arguments):
    del arguments
    counts = "{rooms} rooms, {exits} exits, {mobs} mobs, {objects} objects, {resets} resets, {shops} shops, "
    counts += "{mob_programs} mob programs."
    lines = []
    for row in result["areas"]:
        vnums = "No rooms." if row["room_vnums"] is None else "Room vnums {} to {}.".format(*row["room_vnums"])
        lines.append(f"{row['file']}: {row['name'] or '(no name)'}. {vnums} {counts.format(**row)}")
    lines.append(f"Totals: {result['totals']['files']} files, {counts.format(**result['totals'])}")
    lines.append(f"Files without rooms: {joined(result['areas_without_rooms'])}")
    for family, found in result["overlaps"].items():
        lines.append(f"Overlapping {family} vnum ranges: {len(found) or 'none'}")
        for overlap in found:
            lines.append(
                "  {first} {} to {} and {second} {} to {}; both define: {}".format(
                    *overlap["first_vnums"], *overlap["second_vnums"], joined(overlap["shared_vnums"]), **overlap
                )
            )
    return lines


def reach_text(result, arguments):
    start = result["start"]
    if start["area"] is None:
        return [f"Room {start['vnum']} is not in the set."]
    followed = result["links"]
    following = followed[0] if len(followed) == 1 else f"{', '.join(followed[:-1])} and {followed[-1]}"
    lines = [
        f"From room {start['vnum']} {start['name']} ({start['area']}), following {following}.",
        f"Rooms: {result['totals']['rooms']}. {totals_line(result['totals'])}",
    ]
    for row in result["areas"]:
        lines.append(
            "{file}: {rooms} rooms, {reachable} reachable, {can_return} can walk back, {both} both.".format(**row)
        )
    lines.append(f"Areas with no room reachable: {joined(result['areas_not_reached'])}")
    lines.append(f"Areas nothing leads into: {joined(result['areas_nothing_leads_into'])}")
    lines.append(f"Areas with no way out: {joined(result['areas_with_no_way_out'])}")
    lines.append(f"Files without rooms: {joined(result['areas_without_rooms'])}")
    lines.extend(room_list("Unreachable rooms", result["unreachable_rooms"], arguments.rooms))
    lines.extend(room_list("No-return rooms (reachable, cannot walk back)", result["no_return_rooms"], arguments.rooms))
    if "walking_totals" in result:
        lines.append(f"Exits only: {totals_line(result['walking_totals'])}")
        lines.extend(room_list("Rooms gained as reachable", result["gained"]["reachable"], arguments.rooms))
        lines.extend(room_list("Rooms gained as able to walk back", result["gained"]["can_return"], arguments.rooms))
        lines.append(f"Links added: {len(result['extra_links'])}")
        lines.extend("  {from} to {to} by {via}".format(**link) for link in result["extra_links"])
    return lines


def links_text(result, arguments):
    lines = []
    for row in result["areas"]:
        lines.append(row["file"])
        for side in ("to", "from"):
            if not row[side]:
                lines.append(f"  {side} no other area")
            for link in row[side]:
                lines.append(f"  {side} {link['area']}: {link['exits']} exits")
                if arguments.rooms:
                    lines.extend("    {from} {direction} to {to}".format(**pair) for pair in link["room_pairs"])
    lines.append(f"One-way area links: {len(result['one_way'])}")
    lines.extend("  {from} to {to}: {exits} exits, none back".format(**link) for link in result["one_way"])
    return lines


def dangling_text(result, arguments):
    del arguments
    lines = []
    for kind, found in result["references"].items():
        lines.append(f"{kind}: {len(found)}")
        lines.extend("  {area}: {where} refers to {vnum}".format(**reference) for reference in found)
    exits = result["exits_without_destination"]
    lines.append(
        "Exits with a destination of 0 or less: {count}. With a description: {with_description}. "
        "With a keyword: {with_keyword}. With neither: {with_neither}.".format(**exits)
    )
    for row in exits["exits"]:
        lines.append(
            "  {area}: room {room} {direction}, destination {destination}, "
            "description {description!r}, keyword {keyword!r}".format(**row)
        )
    lines.append(f"Portals without a fixed destination: {len(result['portals_without_destination'])}")
    lines.extend(
        "  {area}: object {vnum}, destination {destination}".format(**row)
        for row in result["portals_without_destination"]
    )
    lines.append(f"Program lines not read as a vnum: {len(result['program_lines_skipped'])}")
    lines.extend(
        "  {area}: program {program} line {line}: {text} ({reason})".format(**row)
        for row in result["program_lines_skipped"]
    )
    return lines


def depends_text(result, arguments):
    del arguments
    lines = []
    for row in result["areas"]:
        if not row["needs"]:
            lines.append(f"{row['file']} needs no other area.")
        for need in row["needs"]:
            kinds = ", ".join(
                f"{kind} {count} ({joined(need['vnums'][kind])})" for kind, count in need["counts"].items()
            )
            lines.append(f"{row['file']} needs {need['area']}: {kinds}")
    return lines


def path_text(result, arguments):
    del arguments
    if result["missing"]:
        missing = " and ".join(f"room {vnum} is not in the set" for vnum in result["missing"])
        return [f"No path from {result['from']} to {result['to']}: {missing}."]
    if result["steps"] is None:
        return [f"No path from {result['from']} to {result['to']}."]
    lines = [f"Path from {result['from']} to {result['to']}: {len(result['steps']) - 1} moves."]
    for step in result["steps"]:
        move = "" if step["direction"] is None else f", go {step['direction']}"
        lines.append(f"{step['vnum']} {step['name']} ({step['area']}){move}")
    return lines


def find_text(result, arguments):
    del arguments
    lines = [f"Rooms: {len(result['rooms'])}", *map(room_line, result["rooms"])]
    for family in ("mobs", "objects"):
        lines.append(f"{family.title()}: {len(result[family])}")
        lines.extend("  {vnum} {short_desc} [{name}] ({area})".format(**row) for row in result[family])
    return lines


def without_room_lists(question, result):
    """Drop the per-room lists that ``--rooms`` asks for."""
    if question == "reach":
        return {key: value for key, value in result.items() if key not in ("unreachable_rooms", "no_return_rooms")}
    if question == "links":
        areas = [
            {
                **row,
                "to": [{"area": link["area"], "exits": link["exits"]} for link in row["to"]],
                "from": [{"area": link["area"], "exits": link["exits"]} for link in row["from"]],
            }
            for row in result["areas"]
        ]
        return {**result, "areas": areas}
    return result


QUESTIONS = {
    "summary": (lambda atlas, arguments: summary(atlas), summary_text),
    "reach": (
        lambda atlas, arguments: reach(atlas, arguments.start, arguments.with_portals, arguments.with_progs),
        reach_text,
    ),
    "links": (lambda atlas, arguments: links(atlas), links_text),
    "dangling": (lambda atlas, arguments: dangling(atlas), dangling_text),
    "depends": (lambda atlas, arguments: depends(atlas), depends_text),
    "path": (
        lambda atlas, arguments: path(
            atlas, arguments.start, arguments.goal, arguments.with_portals, arguments.with_progs
        ),
        path_text,
    ),
    "find": (lambda atlas, arguments: find(atlas, arguments.text), find_text),
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="area-reader atlas", description="Answer a question about a set of area files loaded together."
    )
    questions = parser.add_subparsers(dest="question", required=True)

    def question(name, description, rooms=False, links=False):
        subparser = questions.add_parser(name, help=description, description=description)
        if rooms:
            subparser.add_argument("--rooms", action="store_true", help="list the individual rooms")
        if links:
            subparser.add_argument(
                "--with-portals", action="store_true", help="also follow portals that resets place in rooms"
            )
            subparser.add_argument(
                "--with-progs", action="store_true", help="also follow mob program transfers from a mob's reset room"
            )
        return subparser

    def area_set(subparser):
        subparser.add_argument("--json", action="store_true", help="print JSON instead of text")
        subparser.add_argument(
            "--type",
            choices=("auto", *area_reader.cli.DIALECTS),
            default="auto",
            help="area dialect (default: detect it)",
        )
        subparser.add_argument("paths", nargs="+", help="area files, or directories of *.are files")

    area_set(question("summary", "Counts per area, totals and overlapping vnum ranges."))
    reach_parser = question("reach", "What a walk from one room reaches and what can walk back.", True, True)
    reach_parser.add_argument("--from", dest="start", type=int, required=True, help="the room vnum to walk from")
    area_set(reach_parser)
    area_set(question("links", "Which areas have exits to which, and the one-way links.", rooms=True))
    area_set(question("dangling", "References to vnums that no file in the set defines."))
    area_set(question("depends", "Which other areas each area needs loaded, and why."))
    path_parser = question("path", "The shortest path between two rooms.", links=True)
    path_parser.add_argument("start", type=int, help="the room vnum to start in")
    path_parser.add_argument("goal", type=int, help="the room vnum to arrive in")
    area_set(path_parser)
    find_parser = question("find", "Rooms, mobs and objects whose name or short description contains a text.")
    find_parser.add_argument("text", help="the text to look for, case-insensitively")
    area_set(find_parser)
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    atlas = load(arguments.paths, None if arguments.type == "auto" else arguments.type)
    answer, text = QUESTIONS[arguments.question]
    result = answer(atlas, arguments)
    if arguments.json:
        rooms = getattr(arguments, "rooms", True)
        print(json.dumps(result if rooms else without_room_lists(arguments.question, result)))
    else:
        print("\n".join(text(result, arguments)))
    return 0
