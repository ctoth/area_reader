"""Compile an area source directory to a ROM 2.4 area."""

import argparse
import re
import tempfile
from pathlib import Path

from attr import Factory, attr, attributes, fields, has

import area_reader.model
from area_reader.authoring import tables
from area_reader.authoring.source import (
    FAMILIES,
    LOCK_NAME,
    SINGULAR,
    At,
    Flow,
    SourceError,
    check_text,
    dump_yaml,
    label,
    load_source,
    read_text,
)
from area_reader.constants import EXIT_FLAGS, ROM_ACT_TYPES, SECTOR_TYPES, flag_convert
from area_reader.dialects.rom import (
    RomAffectData,
    RomArea,
    RomAreaFile,
    RomArmorClass,
    RomItem,
    RomMob,
    RomMobprog,
)
from area_reader.native import render_document

MISSING = object()
UNREPRESENTABLE = object()
DICE = re.compile(r"(-?\d+)d(-?\d+)(?:\+?(-?\d+))?")
FLAG_LETTERS = re.compile(r"[A-Za-e]*")
PROGRAM_REFERENCE = re.compile(r"@(room|mob|object):([A-Za-z0-9_:-]*[A-Za-z0-9_])")
REFERENCE_FAMILIES = {"room": "rooms", "mob": "mobs", "object": "objects"}

DOOR_STATES = ("none", "open", "reset_open", "closed", "locked")
# src/db.c reset_area(), case 'D': 0 opens the door, 1 closes it, 2 closes and locks it.
DOOR_RESETS = {"reset_open": 0, "closed": 1, "locked": 2}
# The if_flag column is read and thrown away (src/db.c load_resets); these are the values the stock areas write.
IF_FLAGS = {"M": 0, "O": 0, "P": 1, "G": 1, "E": 1, "D": 0, "R": 0}
NO_LIMIT = -1
NO_KEY = -1
MAX_LEVEL = 60

AREA_KEYS = ("name", "filename", "credits", "levels", "builders", "vnums", "security", "zone", "header")
ROOM_KEYS = (
    "vnum",
    "name",
    "description",
    "sector",
    "flags",
    "heal_rate",
    "mana_rate",
    "owner",
    "clan",
    "area_number",
    "exits",
    "extras",
    "mobs",
    "objects",
    "random_exits",
)
EXIT_KEYS = ("to", "look", "door", "keyword", "description", "key", "pickproof", "nopass", "oneway", "back")
BACK_KEYS = ("keyword", "description", "pickproof", "nopass")
MOB_PLACEMENT_KEYS = ("mob", "count", "max_in_room", "max_in_world", "wears", "carries")
MOB_KEYS = (
    "vnum",
    "keywords",
    "short",
    "long",
    "description",
    "race",
    "level",
    "alignment",
    "sex",
    "act",
    "affected_by",
    "offense",
    "immune",
    "resist",
    "vulnerable",
    "position",
    "size",
    "material",
    "wealth",
    "group",
    "hitroll",
    "hit",
    "mana",
    "damage",
    "damtype",
    "ac",
    "form",
    "parts",
    "special",
    "shop",
    "programs",
)
OBJECT_KEYS = (
    "vnum",
    "keywords",
    "short",
    "long",
    "material",
    "type",
    "level",
    "weight",
    "cost",
    "condition",
    "extra",
    "wear",
    "values",
    "affects",
    "extras",
)
SHOP_KEYS = ("buys", "profit_buy", "profit_sell", "hours")
PROGRAM_KEYS = ("trigger", "phrase", "code", "file", "vnum")
RESET_KEYS = ("command", "if_flag", "arg1", "arg2", "arg3", "arg4", "comment")


@attributes
class Numbers:
    """The vnum of every id of one source area, and of the other areas of the build set by name."""

    vnums = attr()
    sets = attr(default=Factory(dict))

    def resolve(self, value, at, family):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise at.error(f"expected a {SINGULAR[family]} id or a vnum, got {value!r}")
        if isinstance(value, int):
            return value
        area, colon, identifier = value.rpartition(":")
        numbers = self
        if colon:
            if area not in self.sets:
                raise at.error(f"unknown area {area!r} in {value!r}; name its source directory with --set")
            numbers = self.sets[area]
        if identifier not in numbers.vnums[family]:
            raise at.error(f"unknown {SINGULAR[family]} id {value!r}")
        return numbers.vnums[family][identifier]


@attributes
class Door:
    """One side of an exit, as written or as implied by the other side."""

    room = attr()
    direction = attr()
    destination = attr()
    state = attr(default="none")
    keyword = attr(default="")
    description = attr(default="")
    key = attr(default=NO_KEY)
    pickproof = attr(default=False)
    nopass = attr(default=False)
    oneway = attr(default=False)
    back = attr(default=None)
    at = attr(default=None)


@attributes
class Build:
    source = attr()
    numbers = attr()
    area = attr(default=Factory(RomArea))
    defaults = attr(default=Factory(list))
    door_states = attr(default=Factory(dict))
    lock = attr(default=Factory(dict))


# Values


def known_keys(record, at, allowed):
    if not isinstance(record, dict):
        raise at.error(f"expected a mapping, got {record!r}")
    for key in record:
        if key not in allowed:
            raise (at / key).error(f"unknown key; expected one of {', '.join(allowed)}")


def take(record, at, key, convert, default=MISSING):
    if record.get(key) is None:
        if default is MISSING:
            raise (at / key).error("is required")
        return default
    return convert(record[key], at / key)


def integer(value, at):
    if isinstance(value, bool) or not isinstance(value, int):
        raise at.error(f"expected a whole number, got {value!r}")
    return value


def boolean(value, at):
    if not isinstance(value, bool):
        raise at.error(f"expected true or false, got {value!r}")
    return value


def string(value, at):
    if not isinstance(value, str):
        raise at.error(f"expected text, got {value!r}")
    if value[:1].isspace():
        raise at.error("text cannot start with whitespace: ROM skips it when it reads a string")
    return value


def paragraph(value, at):
    """Text ROM shows on lines of its own: it ends with a newline unless it is empty."""
    value = string(value, at)
    return value if not value or value.endswith("\n") else value + "\n"


def one_of(options, what):
    def convert(value, at):
        if not isinstance(value, str) or value.lower() not in options:
            raise at.error(f"unknown {what} {value!r}; expected one of {', '.join(options)}")
        return value.lower()

    return convert


def flags(table):
    def convert(value, at):
        if isinstance(value, bool):
            raise at.error(f"expected a list of flag names, got {value!r}")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            if not FLAG_LETTERS.fullmatch(value) or len(set(value)) != len(value):
                raise at.error(f"{value!r} is not a ROM flag-letter string; write flag names as a list")
            return sum(flag_convert(letter) for letter in value)
        if not isinstance(value, list):
            raise at.error(f"expected a list of flag names, got {value!r}")
        total = 0
        for index, name in enumerate(value):
            if isinstance(name, int) and not isinstance(name, bool):
                total |= name
            elif isinstance(name, str) and name.lower() in table:
                total |= table[name.lower()]
            else:
                raise (at / index).error(f"unknown flag name {name!r}; expected one of {', '.join(table)}")
        return total

    return convert


def flag_names(value, table):
    """Return a flag value as the source writes it: ROM's names, and any unnamed bits as one number."""
    names = Flow()
    remaining = int(value)
    for name, bit in table.items():
        if remaining & bit == bit:
            names.append(name)
            remaining &= ~bit
    if remaining:
        names.append(remaining)
    return names


def dice(value, at):
    match = DICE.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise at.error(f"expected dice as NdS+B, such as 2d6+4, got {value!r}")
    number, sides, bonus = match.groups()
    return area_reader.model.Dice(number=int(number), sides=int(sides), bonus=int(bonus or 0))


def dice_text(value):
    return f"{value.number}d{value.sides}{value.bonus:+d}"


# Object values: each item type's named form, as (key, value slots, kind, default).


@attributes(frozen=True)
class Number:
    def to_model(self, value, at, numbers):
        del numbers
        return [integer(value, at)]

    def to_source(self, values, ids):
        del ids
        return values[0] if isinstance(values[0], int) else UNREPRESENTABLE


@attributes(frozen=True)
class Switch:
    def to_model(self, value, at, numbers):
        del numbers
        return [int(boolean(value, at))]

    def to_source(self, values, ids):
        del ids
        return bool(values[0]) if values[0] in (0, 1) else UNREPRESENTABLE


@attributes(frozen=True)
class Choice:
    options = attr()
    what = attr()

    def to_model(self, value, at, numbers):
        del numbers
        return [one_of(self.options, self.what)(value, at)]

    def to_source(self, values, ids):
        del ids
        return values[0] if values[0] in self.options else UNREPRESENTABLE


@attributes(frozen=True)
class Flags:
    table = attr()

    def to_model(self, value, at, numbers):
        del numbers
        return [flags(self.table)(value, at)]

    def to_source(self, values, ids):
        del ids
        return flag_names(values[0], self.table) if isinstance(values[0], int) else UNREPRESENTABLE


@attributes(frozen=True)
class Reference:
    family = attr()

    def to_model(self, value, at, numbers):
        return [numbers.resolve(value, at, self.family)]

    def to_source(self, values, ids):
        return ids[self.family].get(values[0], values[0]) if isinstance(values[0], int) else UNREPRESENTABLE


@attributes(frozen=True)
class WeaponDice:
    def to_model(self, value, at, numbers):
        del numbers
        rolled = dice(value, at)
        if rolled.bonus:
            raise at.error("weapon dice have no bonus; write NdS")
        return [rolled.number, rolled.sides]

    def to_source(self, values, ids):
        del ids
        return f"{values[0]}d{values[1]}" if all(isinstance(value, int) for value in values) else UNREPRESENTABLE


@attributes(frozen=True)
class Spells:
    def to_model(self, value, at, numbers):
        del numbers
        if not isinstance(value, list) or len(value) > 4:
            raise at.error("expected a list of up to four spell names")
        spell = one_of(("", *tables.SKILLS), "spell")
        names = [spell("" if name is None else name, at / index) for index, name in enumerate(value)]
        return names + [""] * (4 - len(names))

    def to_source(self, values, ids):
        del ids
        if not all(value == "" or value in tables.SKILLS for value in values):
            return UNREPRESENTABLE
        names = Flow(values)
        while names and names[-1] == "":
            names.pop()
        return names


NUMBER = Number()
SWITCH = Switch()
VALUE_FORMS = {
    # src/db2.c load_objects: class word, dice number, dice sides, attack word, weapon flags.
    "weapon": (
        ("class", (0,), Choice(tables.WEAPON_CLASSES, "weapon class"), MISSING),
        ("dice", (1, 2), WeaponDice(), MISSING),
        ("attack", (3,), Choice(tables.ATTACKS, "attack type"), MISSING),
        ("flags", (4,), Flags(tables.WEAPON_FLAGS), []),
    ),
    # src/handler.c apply_ac(): value[0..3] by damage class; value[4] is the bulk src/act_wiz.c prints.
    "armor": (
        ("pierce", (0,), NUMBER, 0),
        ("bash", (1,), NUMBER, 0),
        ("slash", (2,), NUMBER, 0),
        ("exotic", (3,), NUMBER, 0),
        ("bulk", (4,), NUMBER, 0),
    ),
    # src/act_obj.c do_put(): value[0] and value[3] are weights in pounds; src/act_move.c: value[1] flags,
    # value[2] key; src/merc.h WEIGHT_MULT: value[4] is a percentage.
    "container": (
        ("capacity", (0,), NUMBER, 0),
        ("flags", (1,), Flags(tables.CONTAINER_FLAGS), []),
        ("key", (2,), Reference("objects"), 0),
        ("max_item_weight", (3,), NUMBER, 0),
        ("weight_multiplier", (4,), NUMBER, 100),
    ),
    # src/act_obj.c do_fill(), do_drink(): capacity, amount held, liquid, poisoned.
    "drink": (
        ("capacity", (0,), NUMBER, 0),
        ("amount", (1,), NUMBER, 0),
        ("liquid", (2,), Choice(tables.LIQUIDS, "liquid"), "water"),
        ("poisoned", (3,), SWITCH, False),
    ),
    # src/act_obj.c do_eat(): value[0] fills, value[1] feeds, value[3] poisons.
    "food": (
        ("hours_full", (0,), NUMBER, 0),
        ("hours_hunger", (1,), NUMBER, 0),
        ("poisoned", (3,), SWITCH, False),
    ),
    # src/update.c char_update(): value[2] hours of light, -1 for ever.
    "light": (("hours", (2,), NUMBER, MISSING),),
    "key": (),
    # src/act_obj.c get_obj(): value[0] silver, value[1] gold.
    "money": (("silver", (0,), NUMBER, 0), ("gold", (1,), NUMBER, 0)),
    # src/db2.c load_objects: spell level, then four spell names.
    "potion": (("level", (0,), NUMBER, MISSING), ("spells", (1, 2, 3, 4), Spells(), [])),
    # src/act_wiz.c do_ostat(): "Has %d(%d) charges of level %d" with value[1], value[2], value[0].
    "wand": (
        ("level", (0,), NUMBER, MISSING),
        ("max_charges", (1,), NUMBER, 0),
        ("charges", (2,), NUMBER, 0),
        ("spell", (3,), Choice(("", *tables.SKILLS), "spell"), MISSING),
    ),
    # src/act_enter.c do_enter(): charges, exit flags, gate flags, destination; src/act_move.c: value[4] key.
    "portal": (
        ("charges", (0,), NUMBER, 0),
        ("exit_flags", (1,), Flags(tables.EXIT_FLAGS), []),
        ("gate_flags", (2,), Flags(tables.GATE_FLAGS), []),
        ("to", (3,), Reference("rooms"), MISSING),
        ("key", (4,), Reference("objects"), 0),
    ),
    # src/act_move.c do_stand()/do_sit(): value[0] people, value[1] weight, value[2] flags;
    # src/update.c hit_gain()/mana_gain(): value[3] and value[4] are percentages.
    "furniture": (
        ("people", (0,), NUMBER, 0),
        ("weight", (1,), NUMBER, 0),
        ("flags", (2,), Flags(tables.FURNITURE_FLAGS), []),
        ("heal", (3,), NUMBER, 100),
        ("mana", (4,), NUMBER, 100),
    ),
}
VALUE_FORMS["fountain"] = VALUE_FORMS["drink"]
VALUE_FORMS["pill"] = VALUE_FORMS["scroll"] = VALUE_FORMS["potion"]
VALUE_FORMS["staff"] = VALUE_FORMS["wand"]

# src/db2.c load_objects reads these slots as words; the rest are numbers.
WORD_SLOTS = {
    "weapon": (0, 3),
    "drink": (2,),
    "fountain": (2,),
    "wand": (3,),
    "staff": (3,),
    "potion": (1, 2, 3, 4),
    "pill": (1, 2, 3, 4),
    "scroll": (1, 2, 3, 4),
}


def empty_values(item_type):
    return ["" if slot in WORD_SLOTS.get(item_type, ()) else 0 for slot in range(5)]


def named_values(item_type, form, at, numbers):
    known_keys(form, at, [key for key, _slots, _kind, _default in VALUE_FORMS[item_type]])
    values = empty_values(item_type)
    for key, slots, kind, default in VALUE_FORMS[item_type]:
        encoded = take(form, at, key, lambda value, where, kind=kind: kind.to_model(value, where, numbers), None)
        if encoded is None:
            if default is MISSING:
                raise (at / key).error("is required")
            encoded = kind.to_model(default, at / key, numbers)
        for slot, value in zip(slots, encoded):
            values[slot] = value
    return values


def raw_values(item_type, value, at):
    if not isinstance(value, list) or len(value) != 5:
        raise at.error("expected the five raw ROM values")
    words = WORD_SLOTS.get(item_type, ())
    for slot, item in enumerate(value):
        if slot in words and not isinstance(item, str):
            raise (at / slot).error(f"ROM reads this value of a {item_type} as a word, got {item!r}")
        if slot not in words:
            integer(item, at / slot)
    return list(value)


# The header


def compile_header(build):
    header, at = build.source.area, build.source.area_at
    known_keys(header, at, AREA_KEYS)
    area = build.area
    area.name = take(header, at, "name", string)
    area.original_filename = take(header, at, "filename", string, f"{build.source.name}.are")
    builders = take(header, at, "builders", string, "")
    levels = take(header, at, "levels", level_range, None)
    credits = take(header, at, "credits", string, None)
    if credits is None:
        if levels is None:
            raise at.error("write credits, or levels so that the credits line can be made")
        credits = f"{{{levels[0]:2} {levels[1]:2}}} {builders:<7} {area.name}"
    elif levels is not None and not credits.startswith("{"):
        credits = f"{{{levels[0]:2} {levels[1]:2}}} {credits}"
    area.metadata = credits
    first, size = take(header, at, "vnums", vnum_block)
    area.first_vnum = first
    area.last_vnum = first + size - 1
    area.header_format = take(header, at, "header", one_of(("areadata", "rom"), "header form"), "areadata")
    security = take(header, at, "security", integer, None)
    zone = take(header, at, "zone", integer, None)
    if area.header_format == "areadata":
        area.builders = builders
        area.security = security
        area.zone = zone
    elif security is not None or zone is not None:
        raise at.error("security and zone are written only by header: areadata")


def level_range(value, at):
    if not isinstance(value, list) or len(value) != 2:
        raise at.error("expected [lowest, highest]")
    return [integer(item, at / index) for index, item in enumerate(value)]


def vnum_block(value, at):
    known_keys(value, at, ("first", "size"))
    return take(value, at, "first", integer), take(value, at, "size", integer)


def assign_vnums(source):
    """Give every id its vnum: its pin, else its locked number, else the lowest free number of the block."""
    first, size = take(source.area, source.area_at, "vnums", vnum_block)
    vnums = {}
    lock = {}
    for family in FAMILIES:
        records = getattr(source, family)
        assigned = {}
        owners = {}
        for identifier, (record, at) in records.items():
            if isinstance(record, dict) and record.get("vnum") is not None:
                vnum = integer(record["vnum"], at / "vnum")
                if vnum in owners:
                    raise (at / "vnum").error(f"vnum {vnum} is already pinned by {SINGULAR[family]} {owners[vnum]!r}")
                owners[vnum] = identifier
                assigned[identifier] = vnum
        lock[family] = {}
        for identifier, vnum in (source.lock.get(family) or {}).items():
            if identifier in assigned or vnum in owners:
                continue
            owners[vnum] = identifier
            lock[family][identifier] = vnum
            if identifier in records:
                assigned[identifier] = vnum
        free = (vnum for vnum in range(first, first + size) if vnum not in owners)
        for identifier, (_record, at) in records.items():
            if identifier not in assigned:
                vnum = next(free, None)
                if vnum is None:
                    raise at.error(
                        f"the vnum block {first}..{first + size - 1} is exhausted: no number is left for this "
                        f"{SINGULAR[family]}"
                    )
                assigned[identifier] = lock[family][identifier] = vnum
        vnums[family] = {identifier: assigned[identifier] for identifier in records}
    return vnums, lock


# Records


def extra_descriptions(record, at):
    extras = record.get("extras")
    if extras is None:
        return []
    where = at / "extras"
    if isinstance(extras, dict):
        entries = [(string(keyword, where / keyword), text, where / keyword) for keyword, text in extras.items()]
    elif isinstance(extras, list):
        entries = []
        for index, entry in enumerate(extras):
            known_keys(entry, where / index, ("keywords", "text"))
            entries.append((take(entry, where / index, "keywords", string), entry.get("text"), where / index / "text"))
    else:
        raise where.error("expected a mapping from keywords to text")
    return [
        area_reader.model.ExtraDescription(keyword=keyword, description=paragraph(text, text_at))
        for keyword, text, text_at in entries
    ]


def compile_room(build, identifier, record, at):
    del identifier
    known_keys(record, at, ROOM_KEYS)
    sector = take(record, at, "sector", sector_type, 0)
    return area_reader.model.Room(
        name=take(record, at, "name", string),
        description=take(record, at, "description", paragraph, ""),
        owner=take(record, at, "owner", string, "") or None,
        clan=take(record, at, "clan", string, ""),
        area_number=take(record, at, "area_number", integer, 0),
        room_flags=take(record, at, "flags", flags(tables.ROOM_FLAGS), 0),
        sector_type=sector,
        heal_rate=take(record, at, "heal_rate", integer, 100),
        mana_rate=take(record, at, "mana_rate", integer, 100),
        extra_descriptions=extra_descriptions(record, at),
    )


def sector_type(value, at):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return tables.SECTORS[one_of(tuple(tables.SECTORS), "sector")(value, at)]


def level_row(level, offset):
    return tables.RECOMMENDED_BY_LEVEL[min(max(level + offset, 1), MAX_LEVEL)]


def recommended(level, act):
    """Return the hit dice, armor class and damage dice Rom2.4.doc Appendix A recommends for a mobile."""
    offsets = [0, 0, 0]
    divisor = tables.DEFAULT_MAGIC_AC_DIVISOR
    for name, (adjustment, magic_divisor) in tables.CLASS_ADJUSTMENTS.items():
        if act & tables.ACT_FLAGS[name]:
            offsets = [total + step for total, step in zip(offsets, adjustment)]
            divisor = min(divisor, magic_divisor)
    armor = level_row(level, offsets[1])[1]
    # "(ac - 10) / n + 10", with the division truncated as the engine's integer arithmetic would.
    magic = int((armor - 10) / divisor) + 10
    return level_row(level, offsets[0])[0], (armor, armor, armor, magic), level_row(level, offsets[2])[2]


def armor_class(value, at):
    known_keys(value, at, ("pierce", "bash", "slash", "exotic"))
    values = {}
    for name in ("pierce", "bash", "slash", "exotic"):
        values[name] = take(value, at, name, integer)
        if values[name] % 10:
            raise (at / name).error(f"armor class is written in tenths of a file unit: {values[name]} is not a multiple of 10")
    return RomArmorClass(**values)


def positions(value, at):
    position = one_of(tables.POSITIONS, "position")
    if isinstance(value, dict):
        known_keys(value, at, ("start", "default"))
        return take(value, at, "start", position), take(value, at, "default", position)
    return position(value, at), position(value, at)


def compile_mob(build, identifier, record, at):
    known_keys(record, at, MOB_KEYS)
    race = take(record, at, "race", one_of(tuple(tables.RACES), "race"))
    level = take(record, at, "level", integer)
    act = take(record, at, "act", flags(tables.ACT_FLAGS), 0) | ROM_ACT_TYPES.IS_NPC
    hit, armor, damage = recommended(level, act)
    mana = tables.STOCK_MANA_BY_LEVEL[min(max(level, 1), MAX_LEVEL)]

    def default(key, value, origin):
        if record.get(key) is None:
            build.defaults.append((f"mobs.{identifier}.{key}", value, origin))
        return value

    appendix = f"Rom2.4.doc Appendix A, level {level}"
    armor_default = dict(zip(("pierce", "bash", "slash", "exotic"), (value * 10 for value in armor)))
    start, default_position = take(record, at, "position", positions, ("stand", "stand"))
    return RomMob(
        name=take(record, at, "keywords", string),
        short_desc=take(record, at, "short", string),
        long_desc=take(record, at, "long", paragraph),
        description=take(record, at, "description", paragraph, ""),
        race=race,
        act=act,
        affected_by=take(record, at, "affected_by", flags(tables.AFFECT_FLAGS), 0),
        alignment=take(record, at, "alignment", integer, 0),
        group=take(record, at, "group", integer, 0),
        level=level,
        hitroll=take(record, at, "hitroll", integer, 0),
        hit=dice(take(record, at, "hit", lambda value, where: value, default("hit", hit, appendix)), at / "hit"),
        mana=dice(
            take(record, at, "mana", lambda value, where: value, default("mana", mana, f"stock median, level {level}")),
            at / "mana",
        ),
        damage=dice(
            take(record, at, "damage", lambda value, where: value, default("damage", damage, appendix)), at / "damage"
        ),
        damtype=take(record, at, "damtype", one_of(tables.ATTACKS, "damage type"), "none"),
        ac=armor_class(take(record, at, "ac", lambda value, where: value, default("ac", armor_default, appendix)), at / "ac"),
        off_flags=take(record, at, "offense", flags(tables.OFF_FLAGS), 0),
        imm_flags=take(record, at, "immune", flags(tables.IMM_FLAGS), 0),
        res_flags=take(record, at, "resist", flags(tables.IMM_FLAGS), 0),
        vuln_flags=take(record, at, "vulnerable", flags(tables.IMM_FLAGS), 0),
        start_pos=start,
        default_pos=default_position,
        sex=take(record, at, "sex", one_of(tables.SEXES, "sex"), "none"),
        wealth=take(record, at, "wealth", integer, 0),
        form=take(
            record,
            at,
            "form",
            flags(tables.FORM_FLAGS),
            default("form", tables.bits(tables.RACES[race].form), f"race {race}"),
        ),
        parts=take(
            record,
            at,
            "parts",
            flags(tables.PART_FLAGS),
            default("parts", tables.bits(tables.RACES[race].parts), f"race {race}"),
        ),
        size=take(record, at, "size", one_of(tables.SIZES, "size"), "medium"),
        material=take(record, at, "material", string, "0"),
    )


def affect(entry, at, level):
    known_keys(entry, at, ("apply", "modifier", "to", "bits"))
    apply = take(entry, at, "apply", apply_type, 0)
    modifier = take(entry, at, "modifier", integer, 0)
    if entry.get("to") is None:
        if entry.get("bits") is not None:
            raise (at / "bits").error("bits need `to`: affects, immune, resist or vulnerable")
        return RomAffectData(where="TO_OBJECT", type=-1, level=level, duration=-1, location=apply, modifier=modifier)
    where, table = tables.AFFECT_TARGETS[take(entry, at, "to", one_of(tuple(tables.AFFECT_TARGETS), "affect target"))]
    return RomAffectData(
        where=where,
        type=-1,
        level=level,
        duration=-1,
        location=apply,
        modifier=modifier,
        bitvector=take(entry, at, "bits", flags(table), 0),
    )


def apply_type(value, at):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    names = (*tables.APPLIES, *tables.APPLY_ALIASES)
    name = one_of(names, "apply type")(value, at)
    return tables.APPLIES[tables.APPLY_ALIASES.get(name, name)]


def compile_object(build, identifier, record, at):
    del identifier
    item_type = take(record, at, "type", one_of(tuple(tables.ITEM_TYPES), "item type"))
    known_keys(record, at, (*OBJECT_KEYS, item_type))
    if record.get("values") is not None and record.get(item_type) is not None:
        raise (at / item_type).error("write either the named form or the raw values, not both")
    if record.get("values") is not None:
        value = raw_values(item_type, record["values"], at / "values")
    elif item_type in VALUE_FORMS:
        value = named_values(item_type, record.get(item_type) or {}, at / item_type, build.numbers)
    else:
        if record.get(item_type) is not None:
            raise (at / item_type).error(f"a {item_type} has no named values; write values: [..five numbers..]")
        value = empty_values(item_type)
    level = take(record, at, "level", integer, 0)
    condition = take(record, at, "condition", integer, 100)
    if condition not in tables.CONDITIONS:
        raise (at / "condition").error(f"ROM stores a condition as one of {', '.join(map(str, tables.CONDITIONS))}")
    affects = record.get("affects") or []
    if not isinstance(affects, list):
        raise (at / "affects").error("expected a list of affects")
    return RomItem(
        name=take(record, at, "keywords", string),
        short_desc=take(record, at, "short", string),
        description=take(record, at, "long", string, ""),
        material=take(record, at, "material", string, ""),
        item_type=item_type,
        extra_flags=take(record, at, "extra", flags(tables.EXTRA_FLAGS), 0),
        wear_flags=take(record, at, "wear", flags(tables.WEAR_FLAGS), 0),
        value=value,
        level=level,
        weight=take(record, at, "weight", integer, 0),
        cost=take(record, at, "cost", integer, 0),
        condition=condition,
        affected=[affect(entry, at / "affects" / index, level) for index, entry in enumerate(affects)],
        extra_descriptions=extra_descriptions(record, at),
    )


COMPILERS = {"rooms": compile_room, "mobs": compile_mob, "objects": compile_object}


def compile_records(build):
    for family in ("mobs", "objects", "rooms"):
        collection = getattr(build.area, family)
        for identifier, (record, at) in getattr(build.source, family).items():
            if not isinstance(record, dict):
                raise at.error(f"expected a mapping, got {record!r}")
            compiled = COMPILERS[family](build, identifier, record, at)
            compiled.vnum = build.numbers.vnums[family][identifier]
            collection[compiled.vnum] = compiled


# Exits


def written_door(build, room, direction, value, at):
    if not isinstance(value, dict):
        return Door(room, direction, build.numbers.resolve(value, at, "rooms"), at=at)
    known_keys(value, at, EXIT_KEYS)
    if value.get("look") is not None:
        if value.get("to") is not None or value.get("description") is not None:
            raise (at / "look").error("a look-only exit leads nowhere and `look` is its description")
        destination = -1
        description = take(value, at, "look", paragraph)
    else:
        destination = build.numbers.resolve(take(value, at, "to", lambda item, where: item), at / "to", "rooms")
        description = take(value, at, "description", paragraph, "")
    back = value.get("back")
    if back is not None:
        known_keys(back, at / "back", BACK_KEYS)
    door = Door(
        room,
        direction,
        destination,
        state=take(value, at, "door", one_of(DOOR_STATES, "door state"), "none"),
        keyword=take(value, at, "keyword", string, ""),
        description=description,
        key=build.numbers.resolve(take(value, at, "key", lambda item, where: item, NO_KEY), at / "key", "objects"),
        pickproof=take(value, at, "pickproof", boolean, False),
        nopass=take(value, at, "nopass", boolean, False),
        oneway=take(value, at, "oneway", boolean, False),
        back=back,
        at=at,
    )
    if door.state == "none" and (door.pickproof or door.nopass):
        raise at.error("pickproof and nopass describe a door; give the exit a `door`")
    return door


def implied_door(door):
    """The other side of a two-way exit: the same door, keyword and key, leading back."""
    back, at = door.back or {}, door.at / "back"
    return Door(
        door.destination,
        tables.REVERSE[door.direction],
        door.room,
        state=door.state,
        keyword=take(back, at, "keyword", string, door.keyword),
        description=take(back, at, "description", paragraph, ""),
        key=door.key,
        pickproof=take(back, at, "pickproof", boolean, door.pickproof),
        nopass=take(back, at, "nopass", boolean, door.nopass),
        at=door.at,
    )


def compile_exits(build):
    written = {}
    for identifier, (record, at) in build.source.rooms.items():
        room = build.numbers.vnums["rooms"][identifier]
        exits = record.get("exits") or {}
        known_keys(exits, at / "exits", tables.DIRECTIONS)
        for name, value in exits.items():
            direction = tables.DIRECTIONS.index(name)
            written[room, direction] = written_door(build, room, direction, value, at / "exits" / name)

    doors = dict(written)
    for door in written.values():
        if door.oneway or door.destination not in build.area.rooms:
            continue
        slot = door.destination, tables.REVERSE[door.direction]
        other = written.get(slot)
        if other is None:
            if slot in doors:
                raise door.at.error(
                    f"this exit and {'.'.join(doors[slot].at.path)} in {doors[slot].at.file} both make the "
                    f"{tables.DIRECTIONS[slot[1]]} exit of the room they lead to; mark one `oneway: true`"
                )
            doors[slot] = implied_door(door)
        elif (other.destination, other.state, other.key) != (door.room, door.state, door.key):
            raise door.at.error(
                f"disagrees with the other side, {'.'.join(other.at.path)} in {other.at.file}: the two sides of a "
                "two-way exit must agree on destination, door and key, or each be marked `oneway: true`"
            )
        elif door.back is not None:
            raise (door.at / "back").error(f"the other side is written at {'.'.join(other.at.path)} in {other.at.file}")

    for (room, direction), door in sorted(doors.items()):
        lock = EXIT_FLAGS.NONE
        if door.state != "none":
            lock = EXIT_FLAGS.ISDOOR
            lock |= EXIT_FLAGS.PICKPROOF if door.pickproof else 0
            lock |= EXIT_FLAGS.NOPASS if door.nopass else 0
        if door.state in DOOR_RESETS:
            build.door_states[room, direction] = DOOR_RESETS[door.state]
        build.area.rooms[room].exits.append(
            area_reader.model.Exit(
                door=direction,
                description=door.description,
                keyword=door.keyword,
                exit_info=lock,
                key=door.key,
                destination=door.destination,
            )
        )


# Resets


def reset(command, arg1, arg2, arg3=0, arg4=0):
    return area_reader.model.Reset(
        command=command, if_flag=IF_FLAGS[command], arg1=arg1, arg2=arg2, arg3=arg3, arg4=arg4, comment=""
    )


def placed(entry, at, key, allowed):
    """Return a placement entry as a mapping; a bare reference is the entry with only its ``key``."""
    if isinstance(entry, dict):
        known_keys(entry, at, allowed)
        if entry.get(key) is None:
            raise (at / key).error("is required")
        return entry, at / key
    return {key: entry}, at


def contents(build, container, entries, at):
    """P resets filling ``container``. A bare reference written n times is one reset loading n."""
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise at.error("expected a list of objects")
    resets = []
    bare = {}
    for index, written in enumerate(entries):
        entry, where = placed(written, at / index, "object", ("object", "limit", "count", "contains"))
        vnum = build.numbers.resolve(entry["object"], where, "objects")
        if not isinstance(written, dict):
            if vnum in bare:
                bare[vnum].arg4 += 1
                continue
            bare[vnum] = reset("P", vnum, NO_LIMIT, container, 1)
            resets.append(bare[vnum])
            continue
        resets.append(
            reset(
                "P",
                vnum,
                take(entry, at / index, "limit", integer, NO_LIMIT),
                container,
                take(entry, at / index, "count", integer, 1),
            )
        )
        resets.extend(contents(build, vnum, entry.get("contains"), at / index / "contains"))
    return resets


def gear(build, command, written, at, location=0):
    entry, where = placed(written, at, "object", ("object", "limit", "contains"))
    vnum = build.numbers.resolve(entry["object"], where, "objects")
    loaded = reset(command, vnum, take(entry, at, "limit", integer, NO_LIMIT), location)
    return [loaded, *contents(build, vnum, entry.get("contains"), at / "contains")]


def mob_gear(build, entry, at):
    resets = []
    for key in entry:
        if key == "wears":
            known_keys(entry["wears"], at / "wears", tuple(tables.WEAR_LOCATIONS))
            for location, written in entry["wears"].items():
                resets.extend(gear(build, "E", written, at / "wears" / location, tables.WEAR_LOCATIONS[location]))
        elif key == "carries":
            if not isinstance(entry["carries"], list):
                raise (at / "carries").error("expected a list of objects")
            for index, written in enumerate(entry["carries"]):
                resets.extend(gear(build, "G", written, at / "carries" / index))
    return resets


def room_placements(build, family, key, allowed):
    """Yield (room vnum, entry, at, referenced vnum) for every ``mobs`` or ``objects`` entry of every room."""
    for identifier, (record, at) in build.source.rooms.items():
        entries = record.get(family) or []
        if not isinstance(entries, list):
            raise (at / family).error("expected a list")
        for index, written in enumerate(entries):
            entry, where = placed(written, at / family / index, key, allowed)
            vnum = build.numbers.resolve(entry[key], where, family)
            yield build.numbers.vnums["rooms"][identifier], entry, at / family / index, vnum


def compile_resets(build):
    mobs = list(room_placements(build, "mobs", "mob", MOB_PLACEMENT_KEYS))
    objects = list(room_placements(build, "objects", "object", ("object", "limit", "contains")))
    in_world = {}
    in_room = {}
    for room, entry, at, mob in mobs:
        count = take(entry, at, "count", integer, 1)
        in_world[mob] = in_world.get(mob, 0) + count
        in_room[mob, room] = in_room.get((mob, room), 0) + count

    resets = build.area.resets
    for identifier, (record, at) in build.source.rooms.items():
        here = build.numbers.vnums["rooms"][identifier]
        for (room, direction), state in sorted(build.door_states.items()):
            if room == here:
                resets.append(reset("D", room, direction, state))
        for room, entry, where, mob in mobs:
            if room != here:
                continue
            load = reset(
                "M",
                mob,
                take(entry, where, "max_in_world", integer, in_world[mob]),
                room,
                take(entry, where, "max_in_room", integer, in_room[mob, room]),
            )
            equipment = mob_gear(build, entry, where)
            for _load in range(take(entry, where, "count", integer, 1)):
                resets.append(load)
                resets.extend(equipment)
        for room, entry, where, vnum in objects:
            if room == here:
                resets.append(reset("O", vnum, take(entry, where, "limit", integer, NO_LIMIT), room))
                resets.extend(contents(build, vnum, entry.get("contains"), where / "contains"))
        if record.get("random_exits") is not None:
            resets.append(reset("R", here, integer(record["random_exits"], at / "random_exits")))
    resets.extend(raw_reset(record, at) for record, at in build.source.resets)


def raw_reset(record, at):
    known_keys(record, at, RESET_KEYS)
    command = take(record, at, "command", one_of(("m", "o", "p", "g", "e", "d", "r"), "reset command")).upper()
    has_room = command not in ("G", "R")
    counted = command in ("M", "P")
    for key, used in (("arg3", has_room), ("arg4", counted)):
        if not used and record.get(key) not in (None, 0):
            raise (at / key).error(f"a {command} reset has no {key}")
    arg4 = 0
    if counted:
        # ROM 2.3 resets end after the third argument; the reader records that as no fourth argument.
        arg4 = record["arg4"] if "arg4" in record and record["arg4"] is None else take(record, at, "arg4", integer)
    return area_reader.model.Reset(
        command=command,
        if_flag=take(record, at, "if_flag", integer, IF_FLAGS[command]),
        arg1=take(record, at, "arg1", integer),
        arg2=take(record, at, "arg2", integer),
        arg3=take(record, at, "arg3", integer) if has_room else 0,
        arg4=arg4,
        comment=take(record, at, "comment", line, ""),
    )


def line(value, at):
    if not isinstance(value, str) or "\n" in value:
        raise at.error(f"expected one line of text, got {value!r}")
    return value


# Shops, specials, programs, helps


def buy_types(value, at):
    if not isinstance(value, list) or len(value) > area_reader.model.MAX_TRADE_TYPES:
        raise at.error(f"expected up to {area_reader.model.MAX_TRADE_TYPES} item types")
    item_type = one_of(tuple(tables.ITEM_TYPES), "item type")
    numbers = [
        item if isinstance(item, int) and not isinstance(item, bool) else tables.ITEM_TYPES[item_type(item, at / index)]
        for index, item in enumerate(value)
    ]
    return numbers + [0] * (area_reader.model.MAX_TRADE_TYPES - len(numbers))


def hours(value, at):
    if not isinstance(value, list) or len(value) != 2:
        raise at.error("expected [opening hour, closing hour]")
    return [integer(item, at / index) for index, item in enumerate(value)]


def shop(record, at, keeper):
    opens, closes = take(record, at, "hours", hours, [0, 23])
    return area_reader.model.RomShop(
        keeper=keeper,
        buy_type=take(record, at, "buys", buy_types, [0] * area_reader.model.MAX_TRADE_TYPES),
        profit_buy=take(record, at, "profit_buy", integer, 100),
        profit_sell=take(record, at, "profit_sell", integer, 100),
        open_hour=opens,
        close_hour=closes,
        comment=take(record, at, "comment", line, ""),
    )


def special(record, at, mob, key):
    name = take(record, at, key, one_of(tables.SPECIALS, "special procedure"))
    return area_reader.model.Special(command="M", arg1=mob, arg2=name, comment=take(record, at, "comment", line, ""))


def program_code(build, entry, at):
    if entry.get("code") is not None and entry.get("file") is not None:
        raise (at / "file").error("write either code or file, not both")
    if entry.get("file") is not None:
        path = build.source.directory / take(entry, at, "file", string)
        if not path.is_file():
            raise (at / "file").error(f"no such file: {label(path)}")
        at = At(label(path))
        code = read_text(path)
        check_text(code, at)
    elif entry.get("code") is not None:
        at = at / "code"
        code = entry["code"]
    else:
        return None
    string(code, at)

    def number(match):
        return str(build.numbers.resolve(match.group(2), at, REFERENCE_FAMILIES[match.group(1)]))

    return PROGRAM_REFERENCE.sub(number, code)


def compile_mob_extras(build):
    area = build.area
    bodies = {}
    entries = []
    for identifier, (record, at) in build.source.mobs.items():
        mob = area.mobs[build.numbers.vnums["mobs"][identifier]]
        if record.get("shop") is not None:
            known_keys(record["shop"], at / "shop", SHOP_KEYS)
            area.shops.append(shop(record["shop"], at / "shop", mob.vnum))
        if record.get("special") is not None:
            area.specials.append(special(record, at, mob.vnum, "special"))
        programs = record.get("programs") or []
        if not isinstance(programs, list):
            raise (at / "programs").error("expected a list of programs")
        for index, entry in enumerate(programs):
            where = at / "programs" / index
            known_keys(entry, where, PROGRAM_KEYS)
            program = RomMobprog(
                trig_type=take(entry, where, "trigger", string),
                vnum=take(entry, where, "vnum", integer, None),
                trig_phrase=str(take(entry, where, "phrase", lambda value, at: value, "")),
            )
            string(program.trig_phrase, where / "phrase")
            mob.mprogs.append(program)
            entries.append((program, program_code(build, entry, where), where))
    for record, at in build.source.shops:
        known_keys(record, at, ("keeper", *SHOP_KEYS, "comment"))
        area.shops.append(shop(record, at, take(record, at, "keeper", integer)))
    for record, at in build.source.specials:
        known_keys(record, at, ("mob", "special", "comment"))
        area.specials.append(special(record, at, take(record, at, "mob", integer), "special"))

    for vnum, (code, at) in build.source.mobprogs.items():
        bodies[integer(vnum, at)] = string(code, at)
    pinned = {program.vnum for program, _code, _at in entries if program.vnum is not None} | set(bodies)
    free = (vnum for vnum in range(area.first_vnum, area.last_vnum + 1) if vnum not in pinned)
    for program, code, at in entries:
        if program.vnum is None:
            program.vnum = next(free, None)
            if program.vnum is None:
                raise at.error(f"the vnum block {area.first_vnum}..{area.last_vnum} has no number left for this program")
        if code is None:
            continue
        if bodies.setdefault(program.vnum, code) != code:
            raise at.error(f"program {program.vnum} is written elsewhere with different code")
    for vnum in sorted(bodies):
        area.mobprogs[vnum] = bodies[vnum]


def compile_helps(build):
    for record, at in build.source.helps:
        known_keys(record, at, ("level", "keywords", "text"))
        build.area.helps.append(
            area_reader.model.Help(
                level=take(record, at, "level", integer, 0),
                keyword=take(record, at, "keywords", string),
                text=take(record, at, "text", string),
            )
        )


# Build


def compile_source(source, sets=()):
    """Compile a loaded source directory; ``sets`` are the other loaded directories it may refer to by name."""
    vnums, lock = assign_vnums(source)
    others = {other.name: Numbers(assign_vnums(other)[0]) for other in sets}
    build = Build(source=source, numbers=Numbers(vnums, others), lock=lock)
    compile_header(build)
    compile_records(build)
    compile_exits(build)
    compile_resets(build)
    compile_mob_extras(build)
    compile_helps(build)
    return build


def render(area):
    return render_document(area, area.NATIVE_SECTIONS)


def write_area(path, text):
    with open(path, mode="wt", encoding="latin-1", newline="\n") as area_file:
        area_file.write(text)


def parse(text):
    """Parse rendered area text with the ROM reader."""
    with tempfile.TemporaryDirectory(prefix="area-reader-build-") as temporary:
        path = Path(temporary) / "built.are"
        write_area(path, text)
        area_file = RomAreaFile(path)
        area_file.load_sections()
    return area_file


def first_difference(built, parsed, path="area"):
    """Name the first place two models differ, or return None."""
    if type(built) is not type(parsed):
        return f"{path}: built {built!r}, parsed {parsed!r}"
    if has(type(built)):
        pairs = [(attribute.name, getattr(built, attribute.name), getattr(parsed, attribute.name)) for attribute in fields(type(built))]
    elif isinstance(built, dict):
        if list(built) != list(parsed):
            return f"{path}: built keys {list(built)!r}, parsed keys {list(parsed)!r}"
        pairs = [(key, built[key], parsed[key]) for key in built]
    elif isinstance(built, list):
        if len(built) != len(parsed):
            return f"{path}: built {len(built)} entries, parsed {len(parsed)}"
        pairs = [(index, left, right) for index, (left, right) in enumerate(zip(built, parsed))]
    else:
        return None if built == parsed else f"{path}: built {built!r}, parsed {parsed!r}"
    for name, left, right in pairs:
        difference = first_difference(left, right, f"{path}.{name}")
        if difference is not None:
            return difference
    return None


@attributes
class Built:
    area = attr()
    text = attr()
    output = attr()
    defaults = attr()
    lock = attr()


def lock_text(lock):
    return (
        "# Vnums area-reader build has assigned. Keep this file with the source: it is why adding a record\n"
        "# never renumbers another. An id that is no longer defined keeps its number reserved.\n"
        + dump_yaml({family: lock[family] for family in FAMILIES if lock[family]})
    )


def build(directory, output=None, sets=()):
    """Compile ``directory`` to a ROM area file and return what was built.

    The rendered text is parsed back with the ROM reader, and nothing is written unless the parsed area
    equals the compiled one.
    """
    source = load_source(directory)
    compiled = compile_source(source, [load_source(other) for other in sets])
    text = render(compiled.area)
    parsed = parse(text)
    difference = first_difference(compiled.area, parsed.area)
    if difference is not None or parsed.area != compiled.area:
        raise SourceError(
            label(directory), "", f"the built area does not read back as it was written ({difference})"
        )
    output = Path(output) if output is not None else Path(compiled.area.original_filename)
    write_area(output, text)
    if any(compiled.lock[family] for family in FAMILIES):
        lock_path = source.directory / LOCK_NAME
        text_of_lock = lock_text(compiled.lock)
        if not lock_path.is_file() or read_text(lock_path) != text_of_lock:
            with open(lock_path, "w", encoding="utf-8", newline="\n") as lock_file:
                lock_file.write(text_of_lock)
    return Built(area=compiled.area, text=text, output=output, defaults=compiled.defaults, lock=compiled.lock)


def defaults_report(defaults):
    """One line for each mob value that was filled in, as it would be written in the source."""
    lines = []
    for key, value, origin in defaults:
        if isinstance(value, dict):
            value = "{" + ", ".join(f"{name}: {item}" for name, item in value.items()) + "}"
        elif isinstance(value, int):
            table = tables.FORM_FLAGS if key.endswith(".form") else tables.PART_FLAGS
            value = "[" + ", ".join(str(name) for name in flag_names(value, table)) + "]"
        lines.append(f"{key}: {value}  ({origin})")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="area-reader build", description="Compile an area source directory to a ROM 2.4 area file."
    )
    parser.add_argument("source", help="the source directory (holds area.yaml)")
    parser.add_argument("-o", "--output", help="the area file to write (default: the header's filename, here)")
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="DIR",
        help="another source directory whose ids may be referenced as DIRNAME:id",
    )
    parser.add_argument(
        "--show-defaults", action="store_true", help="print every mob value that was filled in because it was omitted"
    )
    arguments = parser.parse_args(argv)
    built = build(arguments.source, arguments.output, arguments.sets)
    area = built.area
    print(
        f"{built.output}: {len(area.rooms)} rooms, {len(area.mobs)} mobs, {len(area.objects)} objects, "
        f"{len(area.resets)} resets, vnums {area.first_vnum}..{area.last_vnum}"
    )
    if arguments.show_defaults:
        print("\n".join(defaults_report(built.defaults)))
    return 0
