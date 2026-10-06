"""An area written out as a visitor would read it, room by room from the way in."""

import argparse
from collections import deque

from attr import Factory, attr, attributes

import area_reader.atlas
from area_reader.constants import EXIT_FLAGS, WEAR_LOCATIONS

# src/db.c reset_area(): the state a D reset leaves a door in.
DOOR_STATES = {0: "open", 1: "closed", 2: "locked"}


@attributes
class Carried:
    """An object a reset loads, with where it is worn (None when carried or lying) and what is put in it."""

    item = attr()
    worn = attr(default=None)
    contents = attr(default=Factory(list))


@attributes
class Present:
    """A mob a reset loads in a room, with what it is given."""

    mob = attr()
    gear = attr(default=Factory(list))


@attributes
class Occupancy:
    mobs = attr(default=Factory(list))
    objects = attr(default=Factory(list))


def replay(atlas, area):
    """What the area's resets put in each room and how they leave each door, by room vnum."""
    rooms = {}
    doors = {}
    holders = {}
    mob = None
    for reset in area.resets:
        if reset.command == "M":
            mob = Present(mob=atlas.mobs[reset.arg1][1])
            rooms.setdefault(reset.arg3, Occupancy()).mobs.append(mob)
        elif reset.command in ("G", "E"):
            worn = WEAR_LOCATIONS(reset.arg3).name.lower() if reset.command == "E" else None
            carried = Carried(item=atlas.objects[reset.arg1][1], worn=worn)
            mob.gear.append(carried)
            holders[reset.arg1] = carried
        elif reset.command == "O":
            carried = Carried(item=atlas.objects[reset.arg1][1])
            rooms.setdefault(reset.arg3, Occupancy()).objects.append(carried)
            holders[reset.arg1] = carried
        elif reset.command == "P":
            carried = Carried(item=atlas.objects[reset.arg1][1])
            holders[reset.arg3].contents.extend([carried] * max(reset.arg4, 1))
            holders[reset.arg1] = carried
        elif reset.command == "D":
            doors[reset.arg1, reset.arg2] = DOOR_STATES[reset.arg3]
    return rooms, doors


def entrance(atlas, area):
    """The first room with an exit that leaves the area; the lowest room when none does."""
    for vnum, room in area.rooms.items():
        if any(leaving.destination in atlas.rooms and leaving.destination not in area.rooms for leaving in room.exits):
            return vnum
    return min(area.rooms)


def walk_order(area, start):
    """Rooms in the order a breadth-first walk from ``start`` meets them, then the rooms it never meets."""
    order = []
    seen = {start}
    queue = deque([start])
    while queue:
        vnum = queue.popleft()
        order.append(vnum)
        for leaving in area.rooms[vnum].exits:
            if leaving.destination in area.rooms and leaving.destination not in seen:
                seen.add(leaving.destination)
                queue.append(leaving.destination)
    return order, [vnum for vnum in area.rooms if vnum not in seen]


def flag_names(value):
    return [member.name.lower() for member in type(value) if member.value and member in value and member.name]


def indented(text, prefix):
    return [prefix + line for line in text.rstrip("\n").splitlines()]


def exit_lines(atlas, area, numbers, doors, room):
    lines = []
    for leaving in room.exits:
        direction = area_reader.atlas.direction_name(leaving.door)
        if leaving.destination in area.rooms:
            target = f"[{numbers[leaving.destination]}] {area.rooms[leaving.destination].name}"
        elif leaving.destination in atlas.rooms:
            label, outside = atlas.rooms[leaving.destination]
            target = f"{outside.name} (another area: {label})"
        elif leaving.destination > 0:
            target = f"room {leaving.destination} (another area)"
        else:
            target = "(cannot be walked; look only)"
        line = f"  {direction}: {target}"
        if leaving.exit_info & EXIT_FLAGS.ISDOOR:
            state = doors.get((room.vnum, leaving.door.value), "open, never reset")
            door = f'door "{leaving.keyword}", {state}'
            if leaving.key > 0:
                key = atlas.objects.get(leaving.key)
                door += f", key: {key[1].short_desc if key else 'object ' + str(leaving.key) + ' (undefined)'}"
            line += f"  [{door}]"
        lines.append(line)
        lines.extend(indented(leaving.description, "      "))
    return lines


def object_lines(carried, indent, label):
    item = carried.item
    lines = [f"{indent}{label}{item.short_desc} ({item.item_type}, level {item.level})"]
    if item.description:
        lines.append(f"{indent}    lying on the floor it reads: {item.description.strip()}")
    for extra in item.extra_descriptions:
        lines.append(f'{indent}    look "{extra.keyword}":')
        lines.extend(indented(extra.description, indent + "        "))
    for inside in carried.contents:
        lines.extend(object_lines(inside, indent + "    ", "inside: "))
    return lines


def mob_lines(area, present, count):
    mob = present.mob
    times = f"  (x{count})" if count > 1 else ""
    lines = [f"  {mob.long_desc.strip()}{times}"]
    lines.append(
        f"      {mob.short_desc}: level {mob.level} {mob.race}; {', '.join(flag_names(mob.act)) or 'no flags'}"
    )
    lines.append("      look:")
    lines.extend(indented(mob.description, "          "))
    for carried in present.gear:
        lines.extend(object_lines(carried, "      ", f"wears on {carried.worn}: " if carried.worn else "carries: "))
    for shop in area.shops:
        if shop.keeper == mob.vnum:
            lines.append(f"      keeps a shop, open {shop.open_hour} to {shop.close_hour}")
    for special in area.specials:
        if special.arg1 == mob.vnum:
            lines.append(f"      special: {special.arg2}")
    for program in mob.mprogs:
        lines.append(f"      program on {program.trig_type} {program.trig_phrase!r}:")
        lines.extend(indented(area.mobprogs.get(program.vnum, "(program not defined)"), "          "))
    return lines


def room_lines(atlas, area, numbers, occupancy, doors, vnum):
    room = area.rooms[vnum]
    sector = getattr(room.sector_type, "name", str(room.sector_type)).lower()
    flags = ", ".join([sector, *flag_names(room.room_flags)])
    lines = [f"## [{numbers[vnum]}] {room.name}  ({flags})", ""]
    lines.extend(indented(room.description, ""))
    lines.append("")
    lines.append("Exits:")
    lines.extend(exit_lines(atlas, area, numbers, doors, room) or ["  none"])
    for extra in room.extra_descriptions:
        lines.append(f'Look "{extra.keyword}":')
        lines.extend(indented(extra.description, "    "))
    here = occupancy.get(vnum, Occupancy())
    if here.mobs:
        lines.append("Here:")
        counted = {}
        for present in here.mobs:
            counted.setdefault(present.mob.vnum, [present, 0])[1] += 1
        for present, count in counted.values():
            lines.extend(mob_lines(area, present, count))
    if here.objects:
        lines.append("Things:")
        for carried in here.objects:
            lines.extend(object_lines(carried, "  ", ""))
    lines.append("")
    return lines


def walk(atlas, entry, start=None, anonymous=False):
    """The walk-through of one area of ``atlas`` as a list of text lines."""
    area = entry.area
    start = entrance(atlas, area) if start is None else start
    order, unreached = walk_order(area, start)
    numbers = {vnum: position for position, vnum in enumerate([*order, *unreached], start=1)}
    occupancy, doors = replay(atlas, area)
    lines = [f"# {area.name}", ""]
    if not anonymous:
        lines.extend([f"Credits: {area.metadata}", ""])
    lines.append(f"{len(area.rooms)} rooms, {len(area.mobs)} kinds of mob, {len(area.objects)} kinds of object.")
    lines.append(f"The walk starts at [{numbers[start]}] {area.rooms[start].name}.")
    lines.append("")
    for vnum in order:
        lines.extend(room_lines(atlas, area, numbers, occupancy, doors, vnum))
    if unreached:
        lines.extend(["# Rooms the walk never reaches", ""])
        for vnum in unreached:
            lines.extend(room_lines(atlas, area, numbers, occupancy, doors, vnum))
    for help_entry in area.helps:
        lines.extend([f"# Help: {help_entry.keyword}", "", *indented(help_entry.text, ""), ""])
    return lines


def build_parser():
    parser = argparse.ArgumentParser(
        prog="area-reader walk", description="Write a ROM area out as a visitor would read it, room by room."
    )
    parser.add_argument("--from", dest="start", type=int, metavar="VNUM", help="room to start from")
    parser.add_argument("--anonymous", action="store_true", help="leave out the credits line")
    parser.add_argument(
        "--with",
        dest="context",
        action="append",
        default=[],
        metavar="PATH",
        help="area files or directories loaded only so exits and objects in other areas can be named; repeatable",
    )
    parser.add_argument("path", metavar="AREA", help="the area file to walk")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    target = next(iter(area_reader.atlas.area_paths([arguments.path])))
    context = [path for path in area_reader.atlas.area_paths(arguments.context) if path.resolve() != target.resolve()]
    atlas = area_reader.atlas.load([target, *context], "rom")
    print("\n".join(walk(atlas, atlas.areas[0], arguments.start, arguments.anonymous)))
    return 0
