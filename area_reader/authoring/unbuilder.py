"""Write a parsed ROM area as an area source directory."""

import argparse
import re
from pathlib import Path

from attr import Factory, attr, attributes

from area_reader.authoring import tables
from area_reader.authoring.builder import (
    DOOR_RESETS,
    IF_FLAGS,
    MISSING,
    NO_KEY,
    NO_LIMIT,
    UNREPRESENTABLE,
    VALUE_FORMS,
    Build,
    Numbers,
    contents,
    dice_text,
    empty_values,
    flag_names,
    mob_gear,
    reset,
)
from area_reader.authoring.normal import reset_groups, reset_key, with_final_newline
from area_reader.authoring.source import (
    FAMILIES,
    HEADER_NAME,
    SINGULAR,
    At,
    Flow,
    FlowMap,
    SourceError,
    dump_yaml,
    label,
    load_yaml,
    write_files,
)
from area_reader.constants import EXIT_FLAGS, ROM_ACT_TYPES
from area_reader.dialects.rom import RomAreaFile

ARTICLES = ("a ", "an ", "the ", "some ")
SLUG_LENGTH = 40
NOT_SLUG = re.compile(r"[^a-z0-9]+")
RECORD_START = re.compile(r"(?m)^(?=  \S)")
KEEP_BLOCK = re.compile(r"(?m)[:-] \|\d*\+\d*$")
CHECK = At("unbuild")
STATE_OF_RESET = {state: name for name, state in DOOR_RESETS.items()}
SECTOR_NAMES = {number: name for name, number in tables.SECTORS.items()}
APPLY_NAMES = {number: name for name, number in tables.APPLIES.items()}
ITEM_TYPE_NAMES = {number: name for name, number in tables.ITEM_TYPES.items()}
WEAR_LOCATION_NAMES = {number: name for name, number in tables.WEAR_LOCATIONS.items()}
AFFECT_TARGETS = {where: (name, table) for name, (where, table) in tables.AFFECT_TARGETS.items()}


@attributes
class Unbuilding:
    area = attr()
    ids = attr()
    # A Build whose numbers resolve those ids, so a placement can be checked by compiling it again.
    build = attr()
    door_states = attr(default=Factory(dict))
    mobs = attr(default=Factory(dict))
    objects = attr(default=Factory(dict))
    shuffles = attr(default=Factory(dict))
    raw = attr(default=Factory(list))

    def ref(self, family, vnum):
        return self.ids[family].get(vnum, vnum)


def slug(text):
    text = text.lower().replace("'", "").strip()
    for article in ARTICLES:
        if text.startswith(article):
            text = text[len(article) :]
            break
    text = NOT_SLUG.sub("-", text).strip("-")
    if len(text) > SLUG_LENGTH:
        text = text[:SLUG_LENGTH].rsplit("-", 1)[0].strip("-")
    return text


def assign_ids(area):
    """Give every record an id slugged from its name; a repeated slug gets -2, -3, ... in record order."""
    ids = {}
    for family in FAMILIES:
        used = set()
        ids[family] = {}
        for vnum, record in getattr(area, family).items():
            base = slug(record.name if family == "rooms" else record.short_desc)
            if not base:
                base = f"{SINGULAR[family]}-{vnum}"
            elif not base[0].isalpha():
                base = f"{SINGULAR[family]}-{base}"
            identifier = base
            serial = 1
            while identifier in used:
                serial += 1
                identifier = f"{base}-{serial}"
            used.add(identifier)
            ids[family][vnum] = identifier
    return ids


def tidy(text):
    """Write paragraph text as the builder completes it: a single line loses the newline the builder adds."""
    text = with_final_newline(text)
    return text[:-1] if text.endswith("\n") and "\n" not in text[:-1] else text


def without_nothing(record):
    return {key: value for key, value in record.items() if value is not None}


# Resets


def nested(state, container, fills):
    """Nest P resets under the object each fills; None when their order is not a nesting."""
    root = []
    path = [(container, root)]
    for fill in fills:
        while path and path[-1][0] != fill.arg3:
            path.pop()
        if not path or fill.arg4 is None:
            return None
        node = {"vnum": fill.arg1, "limit": fill.arg2, "count": fill.arg4, "contains": []}
        path[-1][1].append(node)
        path.append((fill.arg1, node["contains"]))
    return contained(state, root)


def contained(state, nodes):
    """Write nested P resets as a ``contains`` list, or None for an empty one."""
    plain = [
        node["vnum"] for node in nodes if node["limit"] == NO_LIMIT and node["count"] == 1 and not node["contains"]
    ]
    entries = []
    for node in nodes:
        reference = state.ref("objects", node["vnum"])
        # A bare reference written twice means one reset loading two, so two separate resets are spelled out.
        if node["vnum"] in plain and plain.count(node["vnum"]) == 1:
            entries.append(reference)
            continue
        entry = without_nothing(
            {
                "object": reference,
                "limit": None if node["limit"] == NO_LIMIT else node["limit"],
                "count": None if node["count"] == 1 else node["count"],
                "contains": contained(state, node["contains"]),
            }
        )
        entries.append(entry if "contains" in entry else FlowMap(entry))
    return entries or None


def loaded(state, load, fills):
    """Write a G, E or O reset and the P resets after it as a placement entry; None when they do not nest."""
    inside = nested(state, load.arg1, fills)
    if fills and inside is None:
        return None
    return without_nothing(
        {
            "object": state.ref("objects", load.arg1),
            "limit": None if load.arg2 == NO_LIMIT else load.arg2,
            "contains": inside,
        }
    )


def same_resets(group, compiled):
    return [reset_key(member) for member in group] == [reset_key(member) for member in compiled]


def mob_placement(state, group):
    load = group[0]
    if load.arg3 not in state.area.rooms or load.arg4 is None:
        return None
    equipment = {}
    index = 1
    while index < len(group):
        item = group[index]
        index += 1
        fills = []
        while index < len(group) and group[index].command == "P":
            fills.append(group[index])
            index += 1
        entry = loaded(state, item, fills)
        if entry is None:
            return None
        if len(entry) == 1:
            entry = entry["object"]
        elif "contains" not in entry:
            entry = FlowMap(entry)
        if item.command == "E":
            location = WEAR_LOCATION_NAMES.get(item.arg3)
            if location is None or location in equipment.get("wears", {}):
                return None
            equipment.setdefault("wears", {})[location] = entry
        else:
            equipment.setdefault("carries", []).append(entry)
    compiled = [reset("M", load.arg1, load.arg2, load.arg3, load.arg4), *mob_gear(state.build, equipment, CHECK)]
    if not same_resets(group, compiled):
        return None
    return {"mob": state.ref("mobs", load.arg1), "max_in_room": load.arg4, "max_in_world": load.arg2, **equipment}


def object_placement(state, group):
    load = group[0]
    if load.arg3 not in state.area.rooms:
        return None
    entry = loaded(state, load, group[1:])
    if entry is None:
        return None
    compiled = [
        reset("O", load.arg1, load.arg2, load.arg3),
        *contents(state.build, load.arg1, entry.get("contains"), CHECK),
    ]
    return entry if same_resets(group, compiled) else None


def door_reset(state, reset_):
    slot = reset_.arg1, reset_.arg2
    room = state.area.rooms.get(reset_.arg1)
    if room is None or slot in state.door_states or reset_.arg3 not in STATE_OF_RESET:
        return False
    exits = [exit for exit in room.exits if exit.door.value == reset_.arg2]
    if len(exits) != 1 or not exits[0].exit_info & EXIT_FLAGS.ISDOOR:
        return False
    if not same_resets([reset_], [reset("D", reset_.arg1, reset_.arg2, reset_.arg3)]):
        return False
    state.door_states[slot] = STATE_OF_RESET[reset_.arg3]
    return True


def shuffle_reset(state, reset_):
    if reset_.arg1 not in state.area.rooms or reset_.arg1 in state.shuffles:
        return False
    if not same_resets([reset_], [reset("R", reset_.arg1, reset_.arg2)]):
        return False
    state.shuffles[reset_.arg1] = reset_.arg2
    return True


def raw_reset(reset_):
    record = FlowMap(command=reset_.command, arg1=reset_.arg1, arg2=reset_.arg2)
    if reset_.command not in ("G", "R"):
        record["arg3"] = reset_.arg3
    if reset_.command in ("M", "P"):
        record["arg4"] = reset_.arg4
    if reset_.if_flag != IF_FLAGS.get(reset_.command):
        record["if_flag"] = reset_.if_flag
    if reset_.comment:
        record["comment"] = reset_.comment
    return record


def attach_resets(state):
    """Hang every reset group on its room where the source format can say it; keep the rest raw."""
    for group in reset_groups(state.area.resets):
        first = group[0]
        placement = None
        if first.command == "M":
            placement = mob_placement(state, group)
            if placement is not None:
                state.mobs.setdefault(first.arg3, []).append(placement)
        elif first.command == "O":
            placement = object_placement(state, group)
            if placement is not None:
                state.objects.setdefault(first.arg3, []).append(placement)
        elif first.command == "D":
            placement = door_reset(state, first) or None
        elif first.command == "R":
            placement = shuffle_reset(state, first) or None
        elif first.command in ("G", "E") or any(
            other.command in ("O", "G", "E", "P") and other.arg1 == first.arg3 for other in state.area.resets
        ):
            # Kept raw it would follow every other reset, and there join a mob or container it never belonged to.
            raise SourceError(
                state.area.name,
                "",
                f"reset {first.command} {first.arg1} has no earlier reset to belong to (an M for a G or E, the "
                "container's own reset for a P); it cannot keep its meaning once resets are regrouped",
            )
        if placement is None:
            state.raw.extend(raw_reset(member) for member in group)
    count_mobs(state)


def count_mobs(state):
    """Fold repeated loads of a mob into ``count`` and drop the limits the builder would supply itself."""
    in_world = {}
    in_room = {}
    for room, placements in state.mobs.items():
        folded = []
        for placement in placements:
            if folded and folded[-1][0] == placement:
                folded[-1][1] += 1
            else:
                folded.append([placement, 1])
            mob = placement["mob"]
            in_world[mob] = in_world.get(mob, 0) + 1
            in_room[mob, room] = in_room.get((mob, room), 0) + 1
        state.mobs[room] = folded
    for room, folded in state.mobs.items():
        placements = []
        for placement, count in folded:
            mob = placement["mob"]
            gear = {key: value for key, value in placement.items() if key in ("wears", "carries")}
            placements.append(
                without_nothing(
                    {
                        "mob": mob,
                        "count": None if count == 1 else count,
                        "max_in_room": None
                        if placement["max_in_room"] == in_room[mob, room]
                        else placement["max_in_room"],
                        "max_in_world": None
                        if placement["max_in_world"] == in_world[mob]
                        else placement["max_in_world"],
                        **gear,
                    }
                )
            )
        state.mobs[room] = placements


# Exits


def exit_side(state, slot, exit):
    """What the two sides of an exit are compared on: door state and key first, then the rest."""
    door = bool(exit.exit_info & EXIT_FLAGS.ISDOOR)
    return (
        state.door_states.get(slot, "open") if door else "none",
        exit.key if door else NO_KEY,
        exit.keyword,
        bool(exit.exit_info & EXIT_FLAGS.PICKPROOF),
        bool(exit.exit_info & EXIT_FLAGS.NOPASS),
        with_final_newline(exit.description),
    )


def exit_modes(state):
    """Decide how each exit is written: plain, written (two-way), implied by its other side, or oneway."""
    sides = {}
    for room in state.area.rooms.values():
        for exit in room.exits:
            slot = room.vnum, exit.door.value
            if slot in sides:
                raise SourceError(
                    f"room {room.vnum}",
                    "",
                    f"two {tables.DIRECTIONS[slot[1]]} exits cannot be written in a source room",
                )
            sides[slot] = exit
    modes = {}
    for slot, exit in sides.items():
        if slot in modes:
            continue
        back_slot = exit.destination, tables.REVERSE[slot[1]]
        back = sides.get(back_slot)
        if exit.destination not in state.area.rooms:
            modes[slot] = "plain"
        elif back is None or back.destination != slot[0]:
            modes[slot] = "oneway"
        else:
            here, there = exit_side(state, slot, exit), exit_side(state, back_slot, back)
            if here[:2] != there[:2]:
                modes[slot] = modes[back_slot] = "oneway"
            elif there == (*here[:5], ""):
                modes[slot], modes[back_slot] = "written", "implied"
            elif here == (*there[:5], ""):
                modes[slot], modes[back_slot] = "implied", "written"
            else:
                modes[slot] = modes[back_slot] = "written"
    return modes


def exit_source(state, slot, exit, mode):
    door, key, keyword, pickproof, nopass, description = exit_side(state, slot, exit)
    look = exit.destination == -1
    target = state.ref("rooms", exit.destination)
    if not (look or door != "none" or keyword or description or mode == "oneway"):
        return target
    return without_nothing(
        {
            "look": tidy(description) if look else None,
            "to": None if look else target,
            "door": None if door == "none" else door,
            "keyword": keyword or None,
            "description": tidy(description) if description and not look else None,
            "key": None if key == NO_KEY else state.ref("objects", key),
            "pickproof": pickproof or None,
            "nopass": nopass or None,
            "oneway": True if mode == "oneway" else None,
        }
    )


# Records


def extras_source(record):
    extras = record.extra_descriptions
    if not extras:
        return None
    keywords = [extra.keyword for extra in extras]
    if len(set(keywords)) == len(keywords):
        return {extra.keyword: tidy(extra.description) for extra in extras}
    return [{"keywords": extra.keyword, "text": tidy(extra.description)} for extra in extras]


def room_source(state, room, modes):
    sector = getattr(room.sector_type, "value", room.sector_type)
    exits = {
        tables.DIRECTIONS[exit.door.value]: exit_source(
            state, (room.vnum, exit.door.value), exit, modes[room.vnum, exit.door.value]
        )
        for exit in sorted(room.exits, key=lambda exit: exit.door.value)
        if modes[room.vnum, exit.door.value] != "implied"
    }
    return without_nothing(
        {
            "vnum": room.vnum,
            "name": room.name,
            "description": tidy(room.description) if room.description else None,
            "sector": SECTOR_NAMES.get(sector, sector),
            "flags": flag_names(room.room_flags, tables.ROOM_FLAGS) or None,
            "heal_rate": None if room.heal_rate == 100 else room.heal_rate,
            "mana_rate": None if room.mana_rate == 100 else room.mana_rate,
            "owner": room.owner or None,
            "clan": room.clan or None,
            "area_number": room.area_number or None,
            "exits": exits or None,
            "extras": extras_source(room),
            "mobs": state.mobs.get(room.vnum),
            "objects": state.objects.get(room.vnum),
            "random_exits": state.shuffles.get(room.vnum),
        }
    )


def shop_source(shop):
    buys = list(shop.buy_type)
    while buys and buys[-1] == 0:
        buys.pop()
    return {
        "buys": Flow(ITEM_TYPE_NAMES.get(number, number) for number in buys),
        "profit_buy": shop.profit_buy,
        "profit_sell": shop.profit_sell,
        "hours": Flow([shop.open_hour, shop.close_hour]),
    }


def programs_source(state, mob, written):
    programs = []
    for program in mob.mprogs:
        entry = {"trigger": program.trig_type, "phrase": program.trig_phrase, "vnum": program.vnum}
        if program.vnum in state.area.mobprogs and program.vnum not in written:
            written.add(program.vnum)
            entry["code"] = state.area.mobprogs[program.vnum]
        programs.append(entry)
    return programs or None


def mob_source(state, mob, shop, special, written):
    if mob.group is None or mob.shielded_by is not None:
        raise SourceError(f"mob {mob.vnum}", "", "the ROM 2.3 and ROT mobile layouts cannot be written as area source")
    race = tables.RACES.get(mob.race)
    position = (
        mob.start_pos if mob.start_pos == mob.default_pos else FlowMap(start=mob.start_pos, default=mob.default_pos)
    )
    armor = mob.ac
    return without_nothing(
        {
            "vnum": mob.vnum,
            "keywords": mob.name,
            "short": mob.short_desc,
            "long": tidy(mob.long_desc),
            "description": tidy(mob.description) if mob.description else None,
            "race": mob.race,
            "level": mob.level,
            "alignment": mob.alignment or None,
            "sex": None if mob.sex == "none" else mob.sex,
            "act": flag_names(mob.act & ~ROM_ACT_TYPES.IS_NPC, tables.ACT_FLAGS) or None,
            "affected_by": flag_names(mob.affected_by, tables.AFFECT_FLAGS) or None,
            "offense": flag_names(mob.off_flags, tables.OFF_FLAGS) or None,
            "immune": flag_names(mob.imm_flags, tables.IMM_FLAGS) or None,
            "resist": flag_names(mob.res_flags, tables.IMM_FLAGS) or None,
            "vulnerable": flag_names(mob.vuln_flags, tables.IMM_FLAGS) or None,
            "position": None if position == "stand" else position,
            "size": None if mob.size == "medium" else mob.size,
            "material": None if mob.material == "0" else mob.material,
            "wealth": mob.wealth or None,
            "group": mob.group or None,
            "hitroll": mob.hitroll or None,
            "hit": dice_text(mob.hit),
            "mana": dice_text(mob.mana),
            "damage": dice_text(mob.damage),
            "damtype": mob.damtype,
            "ac": FlowMap(pierce=armor.pierce, bash=armor.bash, slash=armor.slash, exotic=armor.exotic),
            "form": None if race and mob.form == tables.bits(race.form) else flag_names(mob.form, tables.FORM_FLAGS),
            "parts": None
            if race and mob.parts == tables.bits(race.parts)
            else flag_names(mob.parts, tables.PART_FLAGS),
            "special": special,
            "shop": shop,
            "programs": programs_source(state, mob, written),
        }
    )


def values_source(state, item):
    """An object's values under its type's named form, or as raw ``values`` when the form cannot say them."""
    blank = empty_values(item.item_type)
    form = VALUE_FORMS.get(item.item_type)
    if form is not None:
        named = {}
        covered = set()
        for key, slots, kind, default in form:
            value = kind.to_source([item.value[slot] for slot in slots], state.ids)
            if value is UNREPRESENTABLE:
                named = None
                break
            covered.update(slots)
            if default is MISSING or value != default:
                named[key] = value
        if named is not None and all(item.value[slot] == blank[slot] for slot in range(5) if slot not in covered):
            return {item.item_type: FlowMap(named)} if named else {}
    return {} if item.value == blank else {"values": Flow(item.value)}


def affect_source(affect):
    apply = APPLY_NAMES.get(affect.location, affect.location)
    if affect.where == "TO_OBJECT":
        return FlowMap(apply=apply, modifier=affect.modifier)
    name, table = AFFECT_TARGETS[affect.where]
    entry = FlowMap(to=name, bits=flag_names(affect.bitvector, table))
    if affect.location:
        entry["apply"] = apply
    if affect.modifier:
        entry["modifier"] = affect.modifier
    return entry


def object_source(state, item):
    return without_nothing(
        {
            "vnum": item.vnum,
            "keywords": item.name,
            "short": item.short_desc,
            "long": item.description or None,
            "material": item.material or None,
            "type": item.item_type,
            "level": item.level or None,
            "weight": item.weight or None,
            "cost": item.cost or None,
            "condition": None if item.condition == 100 else item.condition,
            "extra": flag_names(item.extra_flags, tables.EXTRA_FLAGS) or None,
            "wear": flag_names(item.wear_flags, tables.WEAR_FLAGS) or None,
            **values_source(state, item),
            "affects": [affect_source(affect) for affect in item.affected] or None,
            "extras": extras_source(item),
        }
    )


def header_source(area):
    if area.header_format not in ("rom", "areadata"):
        raise SourceError(area.name, "", f"the {area.header_format!r} area header cannot be written as area source")
    return without_nothing(
        {
            "name": area.name,
            "filename": area.original_filename,
            "credits": area.metadata,
            "builders": area.builders or None,
            "vnums": FlowMap(first=area.first_vnum, size=area.last_vnum - area.first_vnum + 1),
            "security": area.security,
            "zone": area.zone,
            "header": area.header_format,
        }
    )


# Files


def document(data, spaced=False):
    """Render one source file, with a blank line between records when that reads back the same."""
    text = dump_yaml(data)
    if load_yaml(text, "unbuild") != data:
        raise SourceError("unbuild", "", f"the YAML written for {', '.join(data)} does not read back as it was written")
    if spaced:
        head, first, *records = RECORD_START.split(text)
        opened = head + first
        for previous, record in zip([first, *records], records):
            # A blank line after a block scalar that keeps its trailing newlines would add one to it.
            opened += ("" if KEEP_BLOCK.search(previous) else "\n") + record
        if load_yaml(opened, "unbuild") == data:
            return opened
    return text


def unbuild(area, skipped_sections=()):
    """Return the source directory for a parsed ROM area, as a mapping from file name to text."""
    if skipped_sections:
        names = ", ".join(f"#{name.upper()}" for name, _body in skipped_sections)
        raise SourceError(
            area.name, "", f"sections the reader does not model cannot be written as area source: {names}"
        )
    ids = assign_ids(area)
    numbers = Numbers({family: {identifier: vnum for vnum, identifier in ids[family].items()} for family in FAMILIES})
    state = Unbuilding(area=area, ids=ids, build=Build(source=None, numbers=numbers))
    attach_resets(state)
    modes = exit_modes(state)

    shops = {}
    specials = {}
    raw_shops = []
    raw_specials = []
    for shop in area.shops:
        if shop.keeper in area.mobs and shop.keeper not in shops:
            shops[shop.keeper] = shop_source(shop)
        else:
            raw_shops.append(FlowMap(keeper=shop.keeper, **shop_source(shop)))
    for special in area.specials:
        if special.command is None:
            continue
        if special.command != "M":
            raise SourceError(area.name, "", f"special line {special.command!r} cannot be written as area source")
        if special.arg1 in area.mobs and special.arg1 not in specials:
            specials[special.arg1] = special.arg2
        else:
            raw_specials.append(FlowMap(mob=special.arg1, special=special.arg2))

    written = set()
    mobs = {
        ids["mobs"][vnum]: mob_source(state, mob, shops.get(vnum), specials.get(vnum), written)
        for vnum, mob in area.mobs.items()
    }
    files = {HEADER_NAME: document({"area": header_source(area)})}
    if area.rooms:
        rooms = {ids["rooms"][vnum]: room_source(state, room, modes) for vnum, room in area.rooms.items()}
        files["rooms.yaml"] = document({"rooms": rooms}, spaced=True)
    if mobs:
        files["mobs.yaml"] = document({"mobs": mobs}, spaced=True)
    if area.objects:
        objects = {ids["objects"][vnum]: object_source(state, item) for vnum, item in area.objects.items()}
        files["objects.yaml"] = document({"objects": objects}, spaced=True)
    if area.helps:
        helps = [{"level": entry.level, "keywords": entry.keyword, "text": entry.text} for entry in area.helps]
        files["helps.yaml"] = document({"helps": helps})
    raw = without_nothing(
        {
            "resets": state.raw or None,
            "shops": raw_shops or None,
            "specials": raw_specials or None,
            "mobprogs": {vnum: code for vnum, code in area.mobprogs.items() if vnum not in written} or None,
        }
    )
    if raw:
        files["raw.yaml"] = document(raw)
    return files


def unbuild_file(path, directory):
    """Parse a ROM area file and write its source directory; returns the files written."""
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise SourceError(label(directory), "", "unbuild writes into a new or empty directory")
    area_file = RomAreaFile(path)
    area_file.load_sections()
    files = unbuild(area_file.area, area_file.skipped_sections)
    write_files(directory, files)
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="area-reader unbuild", description="Write a ROM 2.4 area file as an area source directory."
    )
    parser.add_argument("area", help="the ROM area file")
    parser.add_argument("-o", "--output", required=True, help="the source directory to create")
    arguments = parser.parse_args(argv)
    files = unbuild_file(arguments.area, arguments.output)
    print(f"{arguments.output}: {', '.join(files)}")
    return 0
