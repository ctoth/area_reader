"""Findings and metrics for ROM 2.4 area files judged against a set loaded together."""

import argparse
import json
import re
import statistics
from collections import Counter
from functools import partial

from attr import attr, attributes

import area_reader.atlas
from area_reader.constants import EXIT_DIRECTIONS, EXIT_FLAGS, ROM_ACT_TYPES, ROM_LIQUIDS, ROM_ROOM_FLAGS

SEVERITIES = ("error", "warning", "info")

# ROM src/special.c spec_table.
SPEC_FUNCTIONS = (
    "spec_breath_any",
    "spec_breath_acid",
    "spec_breath_fire",
    "spec_breath_frost",
    "spec_breath_gas",
    "spec_breath_lightning",
    "spec_cast_adept",
    "spec_cast_cleric",
    "spec_cast_judge",
    "spec_cast_mage",
    "spec_cast_undead",
    "spec_executioner",
    "spec_fido",
    "spec_guard",
    "spec_janitor",
    "spec_mayor",
    "spec_poison",
    "spec_thief",
    "spec_nasty",
    "spec_troll_member",
    "spec_ogre_member",
    "spec_patrolman",
)
# ROM src/const.c item_table.
ITEM_TYPES = (
    "light",
    "scroll",
    "wand",
    "staff",
    "weapon",
    "treasure",
    "armor",
    "potion",
    "clothing",
    "furniture",
    "trash",
    "container",
    "drink",
    "key",
    "food",
    "money",
    "boat",
    "npc_corpse",
    "pc_corpse",
    "fountain",
    "pill",
    "protect",
    "map",
    "portal",
    "warp_stone",
    "room_key",
    "gem",
    "jewelry",
    "jukebox",
)
# ROM src/const.c weapon_table.  handler.c weapon_type() returns WEAPON_EXOTIC for any other word, "exotic" included.
WEAPON_CLASSES = ("sword", "mace", "dagger", "axe", "staff", "flail", "whip", "polearm")
WEAPON_CLASS_DEFAULT = "exotic"
# ROM src/const.c attack_table.
ATTACK_TYPES = (
    "none",
    "slice",
    "stab",
    "slash",
    "whip",
    "claw",
    "blast",
    "pound",
    "crush",
    "grep",
    "bite",
    "pierce",
    "suction",
    "beating",
    "digestion",
    "charge",
    "slap",
    "punch",
    "wrath",
    "magic",
    "divine",
    "cleave",
    "scratch",
    "peck",
    "peckb",
    "chop",
    "sting",
    "smash",
    "shbite",
    "flbite",
    "frbite",
    "acbite",
    "chomp",
    "drain",
    "thrust",
    "slime",
    "shock",
    "thwack",
    "flame",
    "chill",
)
# ROM src/const.c race_table.
RACES = (
    "unique",
    "human",
    "elf",
    "dwarf",
    "giant",
    "bat",
    "bear",
    "cat",
    "centipede",
    "dog",
    "doll",
    "dragon",
    "fido",
    "fox",
    "goblin",
    "hobgoblin",
    "kobold",
    "lizard",
    "modron",
    "orc",
    "pig",
    "rabbit",
    "school monster",
    "snake",
    "song bird",
    "troll",
    "water fowl",
    "wolf",
    "wyvern",
)
# ROM src/tables.c position_table, sex_table and size_table.
POSITIONS = (
    "dead",
    "mortally wounded",
    "incapacitated",
    "stunned",
    "sleeping",
    "resting",
    "sitting",
    "fighting",
    "standing",
)
SEXES = ("none", "male", "female", "either")
SIZES = ("tiny", "small", "medium", "large", "huge", "giant")
# ROM src/const.c liq_table, already kept as ROM_LIQUIDS.
LIQUIDS = tuple(ROM_LIQUIDS)
# ROM src/db.c boot_db: the section names it reads; any other name ends the boot.
ROM_SECTIONS = frozenset(
    {"area", "helps", "mobold", "mobiles", "objold", "objects", "resets", "rooms", "shops", "socials", "specials"}
)
OLD_FORMAT_SECTIONS = frozenset({"mobold", "objold"})
# ROM src/act_move.c rev_dir.
REVERSE = {
    EXIT_DIRECTIONS.NORTH: EXIT_DIRECTIONS.SOUTH,
    EXIT_DIRECTIONS.EAST: EXIT_DIRECTIONS.WEST,
    EXIT_DIRECTIONS.SOUTH: EXIT_DIRECTIONS.NORTH,
    EXIT_DIRECTIONS.WEST: EXIT_DIRECTIONS.EAST,
    EXIT_DIRECTIONS.UP: EXIT_DIRECTIONS.DOWN,
    EXIT_DIRECTIONS.DOWN: EXIT_DIRECTIONS.UP,
}
# ROM src/act_move.c do_lock: a container's key is value[2], a portal's is value[4].
OBJECT_KEY_VALUES = {"container": 2, "portal": 4}

# Stock ROM 2.4b6 has no mob programs.  These three tables are from the MOBprograms 1.4 code as shipped in
# QuickMUD (github.com/avinson/rom24-quickmud): src/tables.c mprog_flags, src/mob_prog.c fn_keyword and
# src/mob_cmds.c mob_cmd_table.
PROGRAM_TRIGGERS = (
    "act",
    "bribe",
    "death",
    "entry",
    "fight",
    "give",
    "greet",
    "grall",
    "kill",
    "hpcnt",
    "random",
    "speech",
    "exit",
    "exall",
    "delay",
    "surr",
)
PROGRAM_CHECKS = frozenset(
    {
        "rand",
        "mobhere",
        "objhere",
        "mobexists",
        "objexists",
        "people",
        "players",
        "mobs",
        "clones",
        "order",
        "hour",
        "ispc",
        "isnpc",
        "isgood",
        "isevil",
        "isneutral",
        "isimmort",
        "ischarm",
        "isfollow",
        "isactive",
        "isdelay",
        "isvisible",
        "hastarget",
        "istarget",
        "exists",
        "affected",
        "act",
        "off",
        "imm",
        "carries",
        "wears",
        "has",
        "uses",
        "name",
        "pos",
        "clan",
        "race",
        "class",
        "objtype",
        "vnum",
        "hpcnt",
        "room",
        "sex",
        "level",
        "align",
        "money",
        "objval0",
        "objval1",
        "objval2",
        "objval3",
        "objval4",
        "grpsize",
    }
)
PROGRAM_COMMANDS = (
    "asound",
    "gecho",
    "zecho",
    "kill",
    "assist",
    "junk",
    "echo",
    "echoaround",
    "echoat",
    "mload",
    "oload",
    "purge",
    "goto",
    "at",
    "transfer",
    "gtransfer",
    "otransfer",
    "force",
    "gforce",
    "vforce",
    "cast",
    "damage",
    "remember",
    "forget",
    "delay",
    "cancel",
    "call",
    "flee",
    "remove",
)
# QuickMUD src/mob_prog.c MAX_NESTED_LEVEL.
PROGRAM_NESTING_LIMIT = 12
PROGRAM_CONDITIONS = ("if", "or", "and")

# ROM doc/Rom2.4.doc appendix A: level -> (hit dice, armor class, damage dice), dice as (number, sides, bonus).
RECOMMENDED = {
    1: ((2, 6, 10), 9, (1, 4, 0)),
    2: ((2, 7, 21), 8, (1, 5, 0)),
    3: ((2, 6, 35), 7, (1, 6, 0)),
    4: ((2, 7, 46), 6, (1, 5, 1)),
    5: ((2, 6, 60), 5, (1, 6, 1)),
    6: ((2, 7, 71), 4, (1, 7, 1)),
    7: ((2, 6, 85), 4, (1, 8, 1)),
    8: ((2, 7, 96), 3, (1, 7, 2)),
    9: ((2, 6, 110), 2, (1, 8, 2)),
    10: ((2, 7, 121), 1, (2, 4, 2)),
    11: ((2, 8, 134), 1, (1, 10, 2)),
    12: ((2, 10, 150), 0, (1, 10, 3)),
    13: ((2, 10, 170), -1, (2, 5, 3)),
    14: ((2, 10, 190), -1, (1, 12, 3)),
    15: ((3, 9, 208), -2, (2, 6, 3)),
    16: ((3, 9, 233), -2, (2, 6, 4)),
    17: ((3, 9, 258), -3, (3, 4, 4)),
    18: ((3, 9, 283), -3, (2, 7, 4)),
    19: ((3, 9, 308), -4, (2, 7, 5)),
    20: ((3, 9, 333), -4, (2, 8, 5)),
    21: ((4, 10, 360), -5, (4, 4, 5)),
    22: ((5, 10, 400), -5, (4, 4, 6)),
    23: ((5, 10, 450), -6, (3, 6, 6)),
    24: ((5, 10, 500), -6, (2, 10, 6)),
    25: ((5, 10, 550), -7, (2, 10, 7)),
    26: ((5, 10, 600), -7, (3, 7, 7)),
    27: ((5, 10, 650), -8, (5, 4, 7)),
    28: ((6, 12, 703), -8, (2, 12, 8)),
    29: ((6, 12, 778), -9, (2, 12, 8)),
    30: ((6, 12, 853), -9, (4, 6, 8)),
    31: ((6, 12, 928), -10, (4, 6, 9)),
    32: ((10, 10, 1000), -10, (6, 4, 9)),
    33: ((10, 10, 1100), -11, (6, 4, 10)),
    34: ((10, 10, 1200), -11, (4, 7, 10)),
    35: ((10, 10, 1300), -11, (4, 7, 11)),
    36: ((10, 10, 1400), -12, (3, 10, 11)),
    37: ((10, 10, 1500), -12, (3, 10, 12)),
    38: ((10, 10, 1600), -13, (5, 6, 12)),
    39: ((15, 10, 1700), -13, (5, 6, 13)),
    40: ((15, 10, 1850), -13, (4, 8, 13)),
    41: ((25, 10, 2000), -14, (4, 8, 14)),
    42: ((25, 10, 2250), -14, (3, 12, 14)),
    43: ((25, 10, 2500), -15, (3, 12, 15)),
    44: ((25, 10, 2750), -15, (8, 4, 15)),
    45: ((25, 10, 3000), -15, (8, 4, 16)),
    46: ((25, 10, 3250), -16, (6, 6, 16)),
    47: ((25, 10, 3500), -17, (6, 6, 17)),
    48: ((25, 10, 3750), -18, (6, 6, 18)),
    49: ((50, 10, 4000), -19, (4, 10, 18)),
    50: ((50, 10, 4500), -20, (5, 8, 19)),
    51: ((50, 10, 5000), -21, (5, 8, 20)),
    52: ((50, 10, 5500), -22, (6, 7, 20)),
    53: ((50, 10, 6000), -23, (6, 7, 21)),
    54: ((50, 10, 6500), -24, (7, 6, 22)),
    55: ((50, 10, 7000), -25, (10, 4, 23)),
    56: ((50, 10, 7500), -26, (10, 4, 24)),
    57: ((50, 10, 8000), -27, (6, 8, 24)),
    58: ((50, 10, 8500), -28, (5, 10, 25)),
    59: ((50, 10, 9000), -29, (8, 6, 26)),
    60: ((50, 10, 9500), -30, (8, 6, 28)),
}
# The same appendix: the level a class-flagged mob reads each column at, relative to its own.
CLASS_SHIFTS = {
    ROM_ACT_TYPES.THIEF: {"hit": -1, "ac": -1, "damage": -1},
    ROM_ACT_TYPES.MAGE: {"hit": -1, "ac": -1, "damage": -3},
    ROM_ACT_TYPES.CLERIC: {"damage": -2},
    ROM_ACT_TYPES.WARRIOR: {"hit": 1},
}
# A mob's mean hit points and mean damage are compared with the recommended mean as a ratio.
STAT_RATIO_LOW = 0.5
STAT_RATIO_HIGH = 2.0
# Armor class is compared in the file's units (tenths of the in-game value), averaged over pierce, bash and slash.
AC_TOLERANCE = 5

LINE_LIMIT = 79
ROOM_DESCRIPTION_MIN_LINES = 2
# 120 characters fires on 23% of the stock ROM rooms; 80 on 9%.
ROOM_DESCRIPTION_MIN_CHARACTERS = 80
CAPITAL_ARTICLES = ("A ", "An ", "The ")
LEVEL_RANGE = re.compile(r"\{\s*(\d+)\s+(\d+)\s*\}")
DIRECTION_PHRASE = re.compile(
    r"\b(?:leads?|leading|continues?|heads?|exits?) (?:to the )?(north|east|south|west)(?:wards?)?(?![-\w])",
    re.IGNORECASE,
)
WORD = re.compile(r"[a-z']+")


@attributes
class Facts:
    """What the whole set says about each vnum, computed once for every rule."""

    loaded_mobs = attr()
    loaded_objects = attr()
    keys = attr()
    used_programs = attr()
    neighbours = attr()


def found(kind, message, vnum=None, index=None):
    return kind, vnum, index, message


def rom_lookup(name, table):
    """ROM's table lookups: the first entry the word is a case-insensitive prefix of, or ``None``."""
    name = str(name).lower()
    return next((entry for entry in table if name and entry.startswith(name)), None)


def commands(area):
    """The resets of an area without its comment lines; a reset finding's index counts these from 0."""
    return [reset for reset in area.resets if reset.command is not None]


def exit_in(room, door):
    """The exit ROM keeps for a direction: the last one written."""
    return next((room_exit for room_exit in reversed(room.exits) if room_exit.door == door), None)


def is_door(room_exit):
    return bool(room_exit.exit_info & EXIT_FLAGS.ISDOOR)


def program_lines(code):
    """Yield ``(line number, words)`` for each program line that is neither blank nor a ``*`` comment."""
    for number, line in enumerate(code.splitlines(), start=1):
        words = line.split()
        if words and not words[0].startswith("*"):
            yield number, words


def gather(atlas):
    kinds = {}
    for kind, _label, _where, vnum in area_reader.atlas.references(atlas):
        kinds.setdefault(kind, set()).add(vnum)
    keys = set(kinds.get("exit_key", ()))
    used_programs = set(kinds.get("mob_program", ()))
    for entry in atlas.areas:
        for item in entry.area.objects.values():
            position = OBJECT_KEY_VALUES.get(item.item_type)
            if position is not None and item.value[position] > 0:
                keys.add(item.value[position])
        for code in entry.area.mobprogs.values():
            for _number, words in program_lines(code):
                if len(words) > 2 and words[0].lower() == "mob" and rom_lookup(words[1], PROGRAM_COMMANDS) == "call":
                    if words[2].isdigit():
                        used_programs.add(int(words[2]))
    forward, backward = area_reader.atlas.adjacency(
        list(area_reader.atlas.exit_links(atlas)) + area_reader.atlas.extra_links(atlas, True, True)
    )
    neighbours = {vnum: forward.get(vnum, []) + backward.get(vnum, []) for vnum in atlas.rooms}
    return Facts(
        loaded_mobs=kinds.get("reset_mob", set()) | kinds.get("program_mob", set()),
        loaded_objects=kinds.get("reset_object", set()) | kinds.get("program_object", set()),
        keys=keys,
        used_programs=used_programs,
        neighbours=neighbours,
    )


def where_of(where, vnum):
    """Turn the place ``atlas.references`` names into a finding's kind and vnum."""
    words = where.split()
    if words[0] in ("shop", "special"):
        return words[0], vnum
    return words[0], int(words[1].rstrip(":"))


def dangling(atlas, entry, facts, kind):
    del facts
    index = getattr(atlas, area_reader.atlas.KINDS[kind])
    family = area_reader.atlas.KINDS[kind].rstrip("s")
    if kind.startswith("reset_"):
        for position, reset in enumerate(commands(entry.area)):
            for argument, reference in area_reader.atlas.RESET_REFERENCES.get(reset.command, ()):
                if reference == kind and getattr(reset, argument) not in index:
                    yield found(
                        "reset",
                        f"{reset.command} reset refers to {family} {getattr(reset, argument)}, which no file defines",
                        index=position,
                    )
        return
    single = area_reader.atlas.Atlas(areas=[entry])
    for reference, _label, where, vnum in area_reader.atlas.references(single):
        if reference == kind and vnum not in index:
            place, number = where_of(where, vnum)
            yield found(place, f"{where} refers to {family} {vnum}, which no file defines", vnum=number)


def exit_no_destination(atlas, entry, facts):
    del atlas, facts
    for room in entry.area.rooms.values():
        for room_exit in room.exits:
            if room_exit.destination <= 0:
                direction = area_reader.atlas.direction_name(room_exit.door)
                yield found("room", f"exit {direction} leads nowhere (destination {room_exit.destination})", room.vnum)


def vnum_out_of_range(atlas, entry, facts):
    del atlas, facts
    area = entry.area
    if area.first_vnum < 0:
        return
    for family, kind in (("rooms", "room"), ("mobs", "mob"), ("objects", "object")):
        for vnum in getattr(area, family):
            if not area.first_vnum <= vnum <= area.last_vnum:
                yield found(kind, f"vnum is outside the area's range {area.first_vnum} to {area.last_vnum}", vnum)


def vnum_collision(atlas, entry, facts):
    del facts
    for family, kind in (("rooms", "room"), ("mobs", "mob"), ("objects", "object")):
        index = getattr(atlas, family)
        for vnum, record in getattr(entry.area, family).items():
            if index[vnum][1] is not record:
                yield found(kind, f"vnum is also defined by {index[vnum][0]}", vnum)


def duplicate_vnum(atlas, entry, facts):
    del atlas, facts
    for diagnostic in entry.diagnostics:
        if diagnostic["kind"] == "duplicate_vnum":
            kind = diagnostic["family"].rstrip("s")
            yield found(kind, "vnum is defined more than once in the file", diagnostic["vnum"])


def skipped_sections(entry):
    return [row["section"] for row in entry.diagnostics if row["kind"] == "skipped_section"]


def unknown_section(atlas, entry, facts):
    del atlas, facts
    for section in skipped_sections(entry):
        if section not in ROM_SECTIONS:
            yield found("area", f"#{section.upper()} is not a section ROM reads; boot_db exits on it")


def section_not_checked(atlas, entry, facts):
    del atlas, facts
    for section in skipped_sections(entry):
        if section in OLD_FORMAT_SECTIONS:
            yield found("area", f"#{section.upper()} holds old-format records, which are not read or checked")


def duplicate_exit(atlas, entry, facts):
    del atlas, facts
    for room in entry.area.rooms.values():
        for door, count in Counter(room_exit.door for room_exit in room.exits).items():
            if count > 1:
                direction = area_reader.atlas.direction_name(door)
                yield found("room", f"{count} exits lead {direction}; ROM keeps the last", room.vnum)


def reset_no_mob(atlas, entry, facts):
    del atlas, facts
    seen = False
    for position, reset in enumerate(commands(entry.area)):
        if reset.command == "M":
            seen = True
        elif reset.command in ("G", "E") and not seen:
            yield found(
                "reset", f"{reset.command} reset of object {reset.arg1} has no M reset before it", index=position
            )


def reset_container_not_loaded(atlas, entry, facts):
    del atlas, facts
    loaded = set()
    for position, reset in enumerate(commands(entry.area)):
        if reset.command == "P" and reset.arg3 not in loaded:
            yield found(
                "reset",
                f"P reset puts object {reset.arg1} in object {reset.arg3}, which no earlier reset of the file loads",
                index=position,
            )
        if reset.command in ("O", "G", "E", "P"):
            loaded.add(reset.arg1)


def reset_door_invalid(atlas, entry, facts):
    del facts
    # ROM src/db.c load_resets exits on a D reset whose exit is missing or not a door, or whose state is not 0-2.
    for position, reset in enumerate(commands(entry.area)):
        if reset.command != "D" or reset.arg1 not in atlas.rooms:
            continue
        room = atlas.rooms[reset.arg1][1]
        if reset.arg2 not in range(len(EXIT_DIRECTIONS)):
            yield found("reset", f"D reset of room {reset.arg1} names direction {reset.arg2}", index=position)
            continue
        door = EXIT_DIRECTIONS(reset.arg2)
        direction = area_reader.atlas.direction_name(door)
        room_exit = exit_in(room, door)
        if room_exit is None:
            yield found("reset", f"D reset: room {reset.arg1} has no exit {direction}", index=position)
        elif not is_door(room_exit):
            yield found("reset", f"D reset: the exit {direction} of room {reset.arg1} is not a door", index=position)
        if reset.arg3 not in (0, 1, 2):
            yield found("reset", f"D reset of room {reset.arg1} sets door state {reset.arg3}", index=position)


def reset_limit(atlas, entry, facts):
    del atlas, facts
    # ROM src/db.c reset_area: M loads only while the world count is under arg2 and the room count under arg4;
    # P fills the container up to arg4.  The O reset's arg2 is not read.
    for position, reset in enumerate(commands(entry.area)):
        if reset.command == "M" and reset.arg2 <= 0:
            yield found("reset", f"M reset of mob {reset.arg1} has a world limit of {reset.arg2}", index=position)
        if reset.command == "M" and reset.arg4 is not None and reset.arg4 <= 0:
            yield found("reset", f"M reset of mob {reset.arg1} has a room limit of {reset.arg4}", index=position)
        if reset.command == "P" and reset.arg4 is not None and reset.arg4 <= 0:
            yield found("reset", f"P reset of object {reset.arg1} puts {reset.arg4} in the container", index=position)


def way_back(atlas, room, room_exit):
    """The destination's exit in the reverse direction, or ``None``; only for an exit that leads to a room."""
    return exit_in(atlas.rooms[room_exit.destination][1], REVERSE[room_exit.door])


def leading_exits(atlas, entry):
    """Yield ``(room, exit, direction name)`` for each exit ROM keeps that leads to a room of the set."""
    for room in entry.area.rooms.values():
        for door in EXIT_DIRECTIONS:
            room_exit = exit_in(room, door)
            if room_exit is not None and room_exit.destination in atlas.rooms:
                yield room, room_exit, area_reader.atlas.direction_name(door)


def exit_one_way(atlas, entry, facts):
    del facts
    for room, room_exit, direction in leading_exits(atlas, entry):
        if way_back(atlas, room, room_exit) is None:
            back = area_reader.atlas.direction_name(REVERSE[room_exit.door])
            yield found("room", f"exit {direction} to {room_exit.destination} has no exit {back} back", room.vnum)


def exit_reverse_mismatch(atlas, entry, facts):
    del facts
    for room, room_exit, direction in leading_exits(atlas, entry):
        back = way_back(atlas, room, room_exit)
        if back is not None and back.destination != room.vnum:
            yield found(
                "room",
                f"exit {direction} leads to {room_exit.destination}, whose exit back leads to {back.destination}",
                room.vnum,
            )


def returning_exits(atlas, entry):
    for room, room_exit, direction in leading_exits(atlas, entry):
        back = way_back(atlas, room, room_exit)
        if back is not None and back.destination == room.vnum:
            yield room, room_exit, direction, back


def door_one_sided(atlas, entry, facts):
    del facts
    for room, room_exit, direction, back in returning_exits(atlas, entry):
        if is_door(room_exit) != is_door(back):
            side = "this side" if is_door(room_exit) else "the far side"
            yield found("room", f"exit {direction} to {room_exit.destination} is a door on {side} only", room.vnum)


def door_key_mismatch(atlas, entry, facts):
    del facts
    for room, room_exit, direction, back in returning_exits(atlas, entry):
        if is_door(room_exit) and is_door(back) and max(room_exit.key, 0) != max(back.key, 0):
            yield found(
                "room",
                f"door {direction} to {room_exit.destination} takes key {room_exit.key}, "
                f"the far side takes key {back.key}",
                room.vnum,
            )


def room_unreachable(atlas, entry, facts):
    """Rooms outside the file's body: the connected group, over the whole set, holding most of the file's rooms."""
    unseen = set(entry.area.rooms)
    groups = []
    while unseen:
        group = set(area_reader.atlas.walk(min(unseen), facts.neighbours)) & set(entry.area.rooms)
        groups.append(group)
        unseen -= group
    if not groups:
        return
    body = max(groups, key=len)
    for vnum in entry.area.rooms:
        if vnum not in body and not is_pet_room(atlas, vnum):
            yield found(
                "room", f"no exit, portal or program connects this room to the file's {len(body)} room body", vnum
            )


def is_pet_room(atlas, vnum):
    """ROM src/act_obj.c do_buy keeps a pet shop's animals in the room numbered one above the shop."""
    return vnum - 1 in atlas.rooms and bool(atlas.rooms[vnum - 1][1].room_flags & ROM_ROOM_FLAGS.PET_SHOP)


def room_no_exit(atlas, entry, facts):
    del facts
    for room in entry.area.rooms.values():
        leads = any(room_exit.destination in atlas.rooms for room_exit in room.exits)
        if not leads and not is_pet_room(atlas, room.vnum):
            yield found("room", "no exit leads to a room", room.vnum)


def key_not_key_type(atlas, entry, facts):
    del facts
    for room in entry.area.rooms.values():
        for room_exit in room.exits:
            if room_exit.key in atlas.objects and atlas.objects[room_exit.key][1].item_type != "key":
                direction = area_reader.atlas.direction_name(room_exit.door)
                item_type = atlas.objects[room_exit.key][1].item_type
                yield found(
                    "room", f"exit {direction} takes key {room_exit.key}, an object of type {item_type}", room.vnum
                )


def key_never_loaded(atlas, entry, facts):
    rooms = {}
    for room in entry.area.rooms.values():
        for room_exit in room.exits:
            if room_exit.key in atlas.objects and room_exit.key not in facts.loaded_objects:
                rooms.setdefault(room_exit.key, []).append(room.vnum)
    for key, vnums in rooms.items():
        yield found("object", f"key of rooms {area_reader.atlas.joined(vnums)} is loaded by no reset or program", key)


def mob_never_loaded(atlas, entry, facts):
    del atlas
    for vnum in entry.area.mobs:
        if vnum not in facts.loaded_mobs:
            yield found("mob", "no M reset or mob mload loads this mob", vnum)


def object_never_loaded(atlas, entry, facts):
    del atlas
    for vnum in entry.area.objects:
        if vnum not in facts.loaded_objects and vnum not in facts.keys:
            yield found("object", "no reset or mob oload loads this object and nothing takes it as a key", vnum)


def program_unused(atlas, entry, facts):
    del atlas
    for vnum in entry.area.mobprogs:
        if vnum not in facts.used_programs:
            yield found("program", "no mob trigger or mob call uses this program", vnum)


def keeper_stock(atlas, keeper):
    """Return whether an M reset loads the keeper, whether one does so in a pet shop, and how many G resets follow."""
    loaded = False
    pet_shop = False
    given = 0
    for entry in atlas.areas:
        holding = False
        for reset in commands(entry.area):
            if reset.command == "M":
                holding = reset.arg1 == keeper
                loaded = loaded or holding
                if holding and reset.arg3 in atlas.rooms:
                    pet_shop = pet_shop or bool(atlas.rooms[reset.arg3][1].room_flags & ROM_ROOM_FLAGS.PET_SHOP)
            elif reset.command == "G" and holding:
                given += 1
    return loaded, pet_shop, given


def shop_keeper_never_loaded(atlas, entry, facts):
    del facts
    for position, shop in enumerate(entry.area.shops):
        if shop.keeper in atlas.mobs and not keeper_stock(atlas, shop.keeper)[0]:
            yield found("shop", "no M reset loads the shop's keeper", shop.keeper, position)


def shop_no_stock(atlas, entry, facts):
    del facts
    for position, shop in enumerate(entry.area.shops):
        loaded, pet_shop, given = keeper_stock(atlas, shop.keeper)
        # ROM src/act_obj.c do_buy sells the mobs of the next room in a pet shop, not the keeper's inventory.
        if loaded and not pet_shop and not given:
            yield found("shop", "no G reset gives the keeper anything to sell", shop.keeper, position)


def special_unknown(atlas, entry, facts):
    del atlas, facts
    for position, special in enumerate(row for row in entry.area.specials if row.command is not None):
        if special.command == "M" and rom_lookup(special.arg2, SPEC_FUNCTIONS) is None:
            yield found("special", f"{special.arg2} is not a ROM spec function", special.arg1, position)


def program_trigger_unknown(atlas, entry, facts):
    del atlas, facts
    for mob in entry.area.mobs.values():
        for mprog in mob.mprogs:
            if rom_lookup(mprog.trig_type, PROGRAM_TRIGGERS) is None:
                yield found("mob", f"{mprog.trig_type} is not a mob program trigger", mob.vnum)


def program_unbalanced_if(atlas, entry, facts):
    del atlas, facts
    for vnum, code in entry.area.mobprogs.items():
        depth = 0
        conditions = False
        for number, words in program_lines(code):
            control = words[0].lower()
            if control == "if":
                depth += 1
                if depth >= PROGRAM_NESTING_LIMIT:
                    yield found("program", f"line {number}: if nested {depth} deep; ROM allows 11", vnum)
            elif control in ("or", "and") and not conditions:
                yield found("program", f"line {number}: {control} does not follow an if", vnum)
            elif control in ("else", "endif") and depth == 0:
                yield found("program", f"line {number}: {control} without if", vnum)
            elif control == "endif":
                depth -= 1
            conditions = control in PROGRAM_CONDITIONS
        if depth:
            yield found("program", f"{depth} if without endif", vnum)


def program_command_unknown(atlas, entry, facts):
    del atlas, facts
    for vnum, code in entry.area.mobprogs.items():
        for number, words in program_lines(code):
            if words[0].lower() == "mob" and rom_lookup("".join(words[1:2]), PROGRAM_COMMANDS) is None:
                yield found("program", f"line {number}: mob {''.join(words[1:2])} is not a mob command", vnum)


def program_check_unknown(atlas, entry, facts):
    del atlas, facts
    for vnum, code in entry.area.mobprogs.items():
        for number, words in program_lines(code):
            if words[0].lower() in PROGRAM_CONDITIONS and "".join(words[1:2]).lower() not in PROGRAM_CHECKS:
                yield found("program", f"line {number}: {''.join(words[1:2])} is not an if check", vnum)


def mob_word_unknown(atlas, entry, facts, fields, table, what):
    del atlas, facts
    for mob in entry.area.mobs.values():
        for field in fields:
            if rom_lookup(getattr(mob, field), table) is None:
                yield found("mob", f"{field} {getattr(mob, field)!r} is not a ROM {what}", mob.vnum)


def item_type_unknown(atlas, entry, facts):
    del atlas, facts
    for item in entry.area.objects.values():
        if rom_lookup(item.item_type, ITEM_TYPES) is None:
            yield found("object", f"item type {item.item_type!r} is not a ROM item type", item.vnum)


def weapon_word_unknown(atlas, entry, facts, position, table, what):
    del atlas, facts
    for item in entry.area.objects.values():
        if rom_lookup(item.item_type, ITEM_TYPES) == "weapon" and rom_lookup(item.value[position], table) is None:
            yield found("object", f"weapon value {position} {item.value[position]!r} is not a ROM {what}", item.vnum)


def liquid_unknown(atlas, entry, facts):
    del atlas, facts
    for item in entry.area.objects.values():
        if (
            rom_lookup(item.item_type, ITEM_TYPES) in ("drink", "fountain")
            and rom_lookup(item.value[2], LIQUIDS) is None
        ):
            yield found("object", f"liquid {item.value[2]!r} is not a ROM liquid", item.vnum)


def dice_mean(number, sides, bonus):
    return number * (sides + 1) / 2 + bonus


def recommended(mob, column):
    """The appendix row a mob reads ``column`` at, or ``None`` when its level is outside the table."""
    if mob.level not in RECOMMENDED:
        return None
    level = mob.level
    for flag, shifts in CLASS_SHIFTS.items():
        if mob.act & flag:
            level += shifts.get(column, 0)
    return RECOMMENDED[min(max(level, min(RECOMMENDED)), max(RECOMMENDED))]


def mob_dice_off_level(atlas, entry, facts, field, column, position):
    del atlas, facts
    for mob in entry.area.mobs.values():
        row = recommended(mob, column)
        if row is None:
            continue
        dice = getattr(mob, field)
        mean = dice_mean(dice.number, dice.sides, dice.bonus)
        expected = dice_mean(*row[position])
        if not STAT_RATIO_LOW * expected <= mean <= STAT_RATIO_HIGH * expected:
            yield found(
                "mob",
                f"{field} dice {dice.number}d{dice.sides}+{dice.bonus} average {mean:g}; "
                f"about {expected:g} is recommended at level {mob.level}",
                mob.vnum,
            )


def mob_ac_off_level(atlas, entry, facts):
    del atlas, facts
    for mob in entry.area.mobs.values():
        row = recommended(mob, "ac")
        if row is None:
            continue
        mean = (mob.ac.pierce + mob.ac.bash + mob.ac.slash) / 30
        if abs(mean - row[1]) > AC_TOLERANCE:
            yield found("mob", f"armor class averages {mean:g}; {row[1]} is recommended at level {mob.level}", mob.vnum)


def level_outside_area_range(atlas, entry, facts, family, kind, unset=None):
    """``unset`` is a level that means "any": 0 on an object."""
    del atlas, facts
    levels = LEVEL_RANGE.search(entry.area.metadata or "")
    if levels is None:
        return
    low, high = map(int, levels.groups())
    for record in getattr(entry.area, family).values():
        if record.level != unset and not low <= record.level <= high:
            yield found(kind, f"level {record.level} is outside the area's level range {low} to {high}", record.vnum)


def text_empty(atlas, entry, facts, family, kind, field):
    del atlas, facts
    for record in getattr(entry.area, family).values():
        if not getattr(record, field).strip():
            yield found(kind, f"{field} is empty", record.vnum)


def text_lines(text):
    return [line for line in text.splitlines() if line.strip()]


def room_description_short(atlas, entry, facts):
    del atlas, facts
    for room in entry.area.rooms.values():
        text = room.description.strip()
        lines = len(text_lines(text))
        if text and (lines < ROOM_DESCRIPTION_MIN_LINES or len(text) < ROOM_DESCRIPTION_MIN_CHARACTERS):
            yield found("room", f"description is {lines} lines and {len(text)} characters", room.vnum)


def record_texts(area):
    """Yield ``(kind, vnum, texts)`` for the prose of each room, mob and object."""
    for room in area.rooms.values():
        texts = [room.description, *(extra.description for extra in room.extra_descriptions)]
        yield "room", room.vnum, texts + [room_exit.description for room_exit in room.exits]
    for mob in area.mobs.values():
        yield "mob", mob.vnum, [mob.long_desc, mob.description]
    for item in area.objects.values():
        yield "object", item.vnum, [item.description, *(extra.description for extra in item.extra_descriptions)]


def line_too_long(atlas, entry, facts):
    del atlas, facts
    for kind, vnum, texts in record_texts(entry.area):
        lengths = [len(line) for text in texts for line in text.splitlines() if len(line) > LINE_LIMIT]
        if lengths:
            yield found(
                kind, f"{len(lengths)} text lines exceed {LINE_LIMIT} columns; the longest is {max(lengths)}", vnum
            )


def room_description_no_newline(atlas, entry, facts):
    del atlas, facts
    for room in entry.area.rooms.values():
        if room.description.strip() and not room.description.endswith("\n"):
            yield found("room", "description does not end with a newline", room.vnum)


def mob_long_not_one_line(atlas, entry, facts):
    del atlas, facts
    for mob in entry.area.mobs.values():
        text = mob.long_desc
        if text.strip() and not (text.endswith("\n") and text.count("\n") == 1):
            yield found("mob", f"long_desc is {text.count(chr(10))} newline-ended lines, not one", mob.vnum)


def description_duplicate(atlas, entry, facts, family, kind):
    del atlas, facts
    groups = {}
    for record in getattr(entry.area, family).values():
        if record.description.strip():
            groups.setdefault(record.description.strip(), []).append(record.vnum)
    for vnums in groups.values():
        if len(vnums) > 1:
            yield found(
                kind, f"{len(vnums)} {family} share one description: {area_reader.atlas.joined(vnums)}", vnums[0]
            )


def short_descriptions(area):
    for family, kind in (("mobs", "mob"), ("objects", "object")):
        for record in getattr(area, family).values():
            if record.short_desc.strip():
                yield kind, record


def short_desc_period(atlas, entry, facts):
    del atlas, facts
    for kind, record in short_descriptions(entry.area):
        if record.short_desc.rstrip().endswith("."):
            yield found(kind, f"short_desc {record.short_desc!r} ends with a period", record.vnum)


def short_desc_capital_article(atlas, entry, facts):
    del atlas, facts
    for kind, record in short_descriptions(entry.area):
        if record.short_desc.startswith(CAPITAL_ARTICLES):
            yield found(kind, f"short_desc {record.short_desc!r} starts with a capital article", record.vnum)


def short_desc_no_keyword(atlas, entry, facts):
    del atlas, facts
    for kind, record in short_descriptions(entry.area):
        keywords = record.name.lower().split()
        if keywords and not any(keyword in record.short_desc.lower() for keyword in keywords):
            yield found(kind, f"short_desc {record.short_desc!r} has none of the keywords {record.name!r}", record.vnum)


def description_direction_no_exit(atlas, entry, facts):
    del atlas, facts
    for room in entry.area.rooms.values():
        present = {area_reader.atlas.direction_name(room_exit.door) for room_exit in room.exits}
        named = {match.group(1).lower() for match in DIRECTION_PHRASE.finditer(room.description)}
        for direction in sorted(named - present):
            yield found("room", f"description speaks of a way {direction}, where the room has no exit", room.vnum)


# Each rule: its severity and a function of (atlas, entry, facts) yielding found(...) tuples.
RULES = {
    **{
        f"dangling-{kind.replace('_', '-')}": ("error", partial(dangling, kind=kind))
        for kind in area_reader.atlas.KINDS
    },
    "exit-no-destination": ("info", exit_no_destination),
    "vnum-out-of-range": ("error", vnum_out_of_range),
    "vnum-collision": ("error", vnum_collision),
    "duplicate-vnum": ("error", duplicate_vnum),
    "unknown-section": ("error", unknown_section),
    "section-not-checked": ("warning", section_not_checked),
    "duplicate-exit": ("error", duplicate_exit),
    "reset-no-mob": ("error", reset_no_mob),
    "reset-container-not-loaded": ("error", reset_container_not_loaded),
    "reset-door-invalid": ("error", reset_door_invalid),
    "reset-limit": ("warning", reset_limit),
    "exit-one-way": ("warning", exit_one_way),
    "exit-reverse-mismatch": ("warning", exit_reverse_mismatch),
    "door-one-sided": ("warning", door_one_sided),
    "door-key-mismatch": ("warning", door_key_mismatch),
    "room-unreachable": ("warning", room_unreachable),
    "room-no-exit": ("warning", room_no_exit),
    "key-not-key-type": ("warning", key_not_key_type),
    "key-never-loaded": ("warning", key_never_loaded),
    "mob-never-loaded": ("warning", mob_never_loaded),
    "object-never-loaded": ("warning", object_never_loaded),
    "program-unused": ("warning", program_unused),
    "shop-keeper-never-loaded": ("error", shop_keeper_never_loaded),
    "shop-no-stock": ("warning", shop_no_stock),
    "special-unknown": ("error", special_unknown),
    "program-trigger-unknown": ("error", program_trigger_unknown),
    "program-unbalanced-if": ("error", program_unbalanced_if),
    "program-command-unknown": ("error", program_command_unknown),
    "program-check-unknown": ("error", program_check_unknown),
    "item-type-unknown": ("error", item_type_unknown),
    "mob-race-unknown": ("warning", partial(mob_word_unknown, fields=("race",), table=RACES, what="race")),
    "mob-position-unknown": (
        "error",
        partial(mob_word_unknown, fields=("start_pos", "default_pos"), table=POSITIONS, what="position"),
    ),
    "mob-sex-unknown": ("error", partial(mob_word_unknown, fields=("sex",), table=SEXES, what="sex")),
    "mob-size-unknown": ("error", partial(mob_word_unknown, fields=("size",), table=SIZES, what="size")),
    "mob-damtype-unknown": (
        "warning",
        partial(mob_word_unknown, fields=("damtype",), table=ATTACK_TYPES, what="attack type"),
    ),
    "weapon-class-unknown": (
        "warning",
        partial(weapon_word_unknown, position=0, table=(*WEAPON_CLASSES, WEAPON_CLASS_DEFAULT), what="weapon class"),
    ),
    "weapon-damtype-unknown": (
        "warning",
        partial(weapon_word_unknown, position=3, table=ATTACK_TYPES, what="attack type"),
    ),
    "liquid-unknown": ("error", liquid_unknown),
    "mob-hit-dice-off-level": ("warning", partial(mob_dice_off_level, field="hit", column="hit", position=0)),
    "mob-damage-dice-off-level": (
        "warning",
        partial(mob_dice_off_level, field="damage", column="damage", position=2),
    ),
    "mob-ac-off-level": ("warning", mob_ac_off_level),
    "mob-level-outside-area-range": ("info", partial(level_outside_area_range, family="mobs", kind="mob")),
    "object-level-outside-area-range": (
        "info",
        partial(level_outside_area_range, family="objects", kind="object", unset=0),
    ),
    "room-name-empty": ("error", partial(text_empty, family="rooms", kind="room", field="name")),
    "room-description-empty": ("error", partial(text_empty, family="rooms", kind="room", field="description")),
    "mob-name-empty": ("error", partial(text_empty, family="mobs", kind="mob", field="name")),
    "mob-short-desc-empty": ("error", partial(text_empty, family="mobs", kind="mob", field="short_desc")),
    "mob-long-desc-empty": ("error", partial(text_empty, family="mobs", kind="mob", field="long_desc")),
    "mob-description-empty": ("warning", partial(text_empty, family="mobs", kind="mob", field="description")),
    "object-name-empty": ("error", partial(text_empty, family="objects", kind="object", field="name")),
    "object-short-desc-empty": (
        "error",
        partial(text_empty, family="objects", kind="object", field="short_desc"),
    ),
    "object-description-empty": (
        "warning",
        partial(text_empty, family="objects", kind="object", field="description"),
    ),
    "room-description-short": ("warning", room_description_short),
    "line-too-long": ("warning", line_too_long),
    "room-description-no-newline": ("warning", room_description_no_newline),
    "mob-long-desc-not-one-line": ("warning", mob_long_not_one_line),
    "room-description-duplicate": ("warning", partial(description_duplicate, family="rooms", kind="room")),
    "mob-description-duplicate": ("warning", partial(description_duplicate, family="mobs", kind="mob")),
    "short-desc-period": ("warning", short_desc_period),
    "short-desc-capital-article": ("warning", short_desc_capital_article),
    "short-desc-no-keyword": ("warning", short_desc_no_keyword),
    "description-direction-no-exit": ("info", description_direction_no_exit),
}


def fraction(part, whole):
    return part / whole if whole else None


def spread(values):
    if not values:
        return None
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def metrics(area):
    rooms = list(area.rooms.values())
    mobs = list(area.mobs.values())
    items = list(area.objects.values())
    exits = [room_exit for room in rooms for room_exit in room.exits]
    doors = [room_exit for room_exit in exits if is_door(room_exit)]
    lengths = [len(room.description.strip()) for room in rooms]
    special_mobs = {special.arg1 for special in area.specials if special.command == "M"}
    prose = [text for _kind, _vnum, texts in record_texts(area) for text in texts]
    words = WORD.findall(" ".join(prose).lower())
    return {
        "rooms": len(rooms),
        "mobs": len(mobs),
        "objects": len(items),
        "resets": len(commands(area)),
        "shops": len(area.shops),
        "specials": len(special_mobs),
        "programs": len(area.mobprogs),
        "exits": len(exits),
        "exits_per_room": fraction(len(exits), len(rooms)),
        "room_description_length_mean": statistics.mean(lengths) if lengths else None,
        "room_description_length_median": statistics.median(lengths) if lengths else None,
        "rooms_with_extra_description": fraction(sum(1 for room in rooms if room.extra_descriptions), len(rooms)),
        "distinct_room_names": fraction(len({room.name.strip() for room in rooms}), len(rooms)),
        "distinct_room_descriptions": fraction(len({room.description.strip() for room in rooms}), len(rooms)),
        "mobs_with_program_or_special": fraction(
            sum(1 for mob in mobs if mob.mprogs or mob.vnum in special_mobs), len(mobs)
        ),
        "doors": len(doors),
        "locked_doors": sum(1 for room_exit in doors if room_exit.key > 0),
        "keys": sum(1 for item in items if item.item_type == "key"),
        "item_types": dict(Counter(str(item.item_type) for item in items)),
        "sectors": dict(Counter(getattr(room.sector_type, "name", str(room.sector_type)).lower() for room in rooms)),
        "mob_levels": spread([mob.level for mob in mobs]),
        "description_words": len(words),
        "description_type_token_ratio": fraction(len(set(words)), len(words)),
    }


def lint(atlas, targets):
    """Run every rule over the ``targets``, entries of ``atlas``; the rest of the set only resolves references."""
    facts = gather(atlas)
    findings = []
    for entry in targets:
        for rule, (severity, check) in RULES.items():
            for kind, vnum, index, message in check(atlas, entry, facts):
                findings.append(
                    {
                        "rule": rule,
                        "severity": severity,
                        "file": entry.label,
                        "kind": kind,
                        "vnum": vnum,
                        "index": index,
                        "message": message,
                    }
                )
    return {
        "findings": findings,
        "counts": {severity: sum(1 for row in findings if row["severity"] == severity) for severity in SEVERITIES},
        "metrics": {entry.label: metrics(entry.area) for entry in targets},
    }


def at_least(findings, severity):
    """The findings as severe as ``severity`` or more."""
    kept = SEVERITIES[: SEVERITIES.index(severity) + 1]
    return [row for row in findings if row["severity"] in kept]


def place(row):
    number = row["index"] if row["vnum"] is None else row["vnum"]
    return row["kind"] if number is None else f"{row['kind']} {number}"


def lint_text(result):
    lines = []
    for label in dict.fromkeys(row["file"] for row in result["findings"]):
        lines.append(label)
        lines.extend(
            f"  {row['severity']} {row['rule']} {place(row)}: {row['message']}"
            for row in result["findings"]
            if row["file"] == label
        )
    lines.append("Errors: {error}. Warnings: {warning}. Info: {info}.".format(**result["counts"]))
    return lines


def build_parser():
    parser = argparse.ArgumentParser(
        prog="area-reader lint", description="Report defects in ROM 2.4 area files, and measure them."
    )
    parser.add_argument("--json", action="store_true", help="print findings, counts and metrics as JSON")
    parser.add_argument(
        "--with",
        dest="context",
        action="append",
        default=[],
        metavar="PATH",
        help="area files or directories loaded only so references resolve; repeatable",
    )
    parser.add_argument(
        "--min-severity", choices=SEVERITIES, default="info", help="list only findings at least this severe"
    )
    parser.add_argument("paths", nargs="+", metavar="PATH", help="area files, or directories of *.are files, to judge")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    targets = list(area_reader.atlas.area_paths(arguments.paths))
    atlas = area_reader.atlas.load([*targets, *arguments.context], "rom")
    result = lint(atlas, atlas.areas[: len(targets)])
    shown = {**result, "findings": at_least(result["findings"], arguments.min_severity)}
    if arguments.json:
        print(json.dumps(shown))
    else:
        print("\n".join(lint_text(shown)))
    return 1 if result["counts"]["error"] else 0
