"""Merc area models, codecs, and reader."""

import logging
from collections import OrderedDict
from operator import setitem

from attr import Factory, attr, attributes

import area_reader.dialects.rom
import area_reader.model
import area_reader.parser
import area_reader.schema
import area_reader.serialization
import area_reader.values
from area_reader.constants import (
    AFFECTED_BY,
    EXIT_FLAGS,
    FORMS,
    IMM_FLAGS,
    MERC_ACT_TYPES,
    MERC_ROOM_FLAGS,
    OFFENSE,
    PARTS,
    WEAR_FLAGS,
)
from area_reader.native import NativeField, NativeSection, NativeWriteError, render_document
from area_reader.native import flag as native_flag
from area_reader.native import nested as native_nested
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string


class MercAreaFile(area_reader.parser.AreaFile):
    def create_area(self):
        return MercArea()

    def dumps(self):
        return render_document(self.area, self.area.NATIVE_SECTIONS, self.skipped_sections)

    def write(self, path):
        with open(path, mode="wt", encoding="latin-1", newline="\n") as area_file:
            area_file.write(self.dumps())

    def load_mobiles(self):
        for mob in self.load_vnum_section(MercMob):
            setitem(self.area.mobs, mob.vnum, mob)

    def load_objects(self):
        for item in self.load_vnum_section(MercItem):
            setitem(self.area.objects, item.vnum, item)

    def load_rooms(self):
        for room in self.load_vnum_section(MercRoom):
            setitem(self.area.rooms, room.vnum, room)

    def load_resets(self):
        for reset in self.read_flat_section(MercReset):
            self.area.resets.append(reset)

    def read_area_metadata(self):
        self.area.metadata = self.read_string()


logger = logging.getLogger("area_reader")


def native_four_numbers(value, owner):
    if len(value) != 4:
        raise NativeWriteError("Merc object values must contain four entries")
    return " ".join(native_number(item, owner) for item in value)


def native_merc_exit_lock(value, owner):
    del owner
    locks = {
        int(EXIT_FLAGS.NONE): 0,
        int(EXIT_FLAGS.ISDOOR): 1,
        int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF): 2,
    }
    try:
        return str(locks[int(value)])
    except KeyError:
        raise NativeWriteError(f"Merc exit flags {value!r} have no native lock code")


def native_merc_reset_arg2_suffix(owner):
    return "" if owner.command in ("G", "R") else " "


@attributes
class MercAffectData:
    type = attr(default=-1)
    duration = attr(default=-1)
    location = area_reader.schema.field(default=-1, native=NativeField(1, native_number, prefix="A\n"))
    modifier = area_reader.schema.field(default=-1, native=NativeField(2, native_number))
    bitvector = attr(default=0)


@attributes
class MercExit(area_reader.model.Exit):
    exit_info = area_reader.schema.field(
        default=0,
        type=EXIT_FLAGS,
        converter=EXIT_FLAGS,
        native=NativeField(4, native_merc_exit_lock),
    )


@attributes
class MercReset:
    command = area_reader.schema.field(
        default=None,
        native=NativeField(
            1, area_reader.model.native_reset_command, suffix=area_reader.model.native_reset_command_suffix
        ),
    )
    if_flag = area_reader.schema.field(
        default=0,
        native=NativeField(2, native_number, suffix=" ", when=lambda owner: owner.command is not None),
    )
    arg1 = area_reader.schema.field(
        default=None,
        native=NativeField(3, native_number, suffix=" ", when=lambda owner: owner.command is not None),
    )
    arg2 = area_reader.schema.field(
        default=None,
        native=NativeField(
            4, native_number, suffix=native_merc_reset_arg2_suffix, when=lambda owner: owner.command is not None
        ),
    )
    arg3 = area_reader.schema.field(
        default=None,
        native=NativeField(5, native_number, suffix="", when=lambda owner: owner.command not in (None, "G", "R")),
    )
    arg4 = attr(default=None)
    arg5 = attr(default=None)
    comment = area_reader.schema.field(default=None, native=NativeField(6, area_reader.model.native_comment))

    @classmethod
    def read(cls, reader, letter):
        command = letter
        if_flag = reader.read_number()
        arg1 = reader.read_number()
        arg2 = reader.read_number()
        if letter == "G" or letter == "R":
            arg3 = 0
        else:
            arg3 = reader.read_number()
        comment = reader.read_to_eol()
        return cls(command=command, if_flag=if_flag, arg1=arg1, arg2=arg2, arg3=arg3, comment=comment)


@attributes
class MercRoom(area_reader.model.Room):
    owner = attr(default=None, type=str)
    clan = attr(default="", type=str)
    room_flags = area_reader.schema.field(
        default=0,
        type=MERC_ROOM_FLAGS,
        converter=MERC_ROOM_FLAGS,
        native=NativeField(4, native_flag),
    )
    heal_rate = attr(default=100, type=int)
    mana_rate = attr(default=100, type=int)
    exits = area_reader.schema.field(
        default=Factory(list), type=list[MercExit], native=NativeField(8, native_records, suffix="")
    )

    def read_metadata(self, reader):
        logger.debug("Reading room data for %d", self.vnum)
        while True:
            letter = reader.read_letter()
            if letter == "S":
                break
            if letter == "D":
                self.exits.append(MercExit.read(reader=reader))
            elif letter == "E":
                self.extra_descriptions.append(reader.read_object(area_reader.model.ExtraDescription))
            else:
                reader.parse_fail(f"room {self.vnum} has flag {letter} not DES")


@attributes
class MercMob(area_reader.dialects.rom.RomMob):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    long_desc = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    extra_descriptions = attr(default=Factory(list), type=list[area_reader.model.ExtraDescription])
    race = attr(default="", type=str)
    group = attr(default=0, type=int)
    act = area_reader.schema.field(
        default=MERC_ACT_TYPES.IS_NPC.value,
        type=MERC_ACT_TYPES,
        converter=MERC_ACT_TYPES,
        native=NativeField(5, native_flag),
    )
    affected_by = area_reader.schema.field(
        default=0, type=AFFECTED_BY, converter=AFFECTED_BY, native=NativeField(6, native_flag)
    )
    alignment = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_number))
    level = area_reader.schema.field(default=0, type=int, native=NativeField(8, native_number, prefix="S\n"))
    hitroll = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number))
    ac = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number))
    hit = area_reader.schema.field(
        default=Factory(area_reader.model.Dice), type=area_reader.model.Dice, native=NativeField(11, native_nested)
    )
    damage = area_reader.schema.field(
        default=Factory(area_reader.model.Dice), type=area_reader.model.Dice, native=NativeField(12, native_nested)
    )
    mana = attr(default=Factory(area_reader.model.Dice), type=area_reader.model.Dice)
    damtype = attr(default="", type=area_reader.values.Word)
    material = attr(default="", type=str)
    wealth = area_reader.schema.field(default=0, type=int, native=NativeField(13, native_number))
    xp = area_reader.schema.field(default=0, type=int, native=NativeField(14, native_number))
    default_pos = area_reader.schema.field(default=0, type=int, native=NativeField(15, native_number))
    start_pos = area_reader.schema.field(default=0, type=int, native=NativeField(16, native_number))
    sex = area_reader.schema.field(default=0, type=int, native=NativeField(17, native_number))
    off_flags = attr(default=0, type=OFFENSE, converter=OFFENSE)
    imm_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
    res_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
    vuln_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
    form = attr(default=0, type=FORMS, converter=FORMS)
    parts = attr(default=0, type=PARTS, converter=PARTS)
    size = attr(default=None, type=area_reader.values.Word)
    mprogs = area_reader.schema.field(default=Factory(list), type=list[area_reader.dialects.rom.RomMobprog] | None)

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading Mob %d", vnum)
        name = reader.read_string()
        short_desc = reader.read_string()
        long_desc = reader.read_string()
        description = reader.read_string()
        act = reader.read_flag()
        affected_by = reader.read_flag()
        alignment = reader.read_flag()
        letter = reader.read_letter()
        level = reader.read_number()
        hitroll = reader.read_number()
        ac = reader.read_number()
        hit = area_reader.model.Dice.read(reader=reader)
        damage = area_reader.model.Dice.read(reader=reader)
        wealth = reader.read_number()
        xp = reader.read_number()
        default_pos = reader.read_number()  # position
        start_pos = reader.read_number()  # start pos
        sex = reader.read_number()
        if letter != "S":
            reader.parse_fail(f"Reading MOB vnum {vnum} non S: {letter}")
        return cls(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            long_desc=long_desc,
            description=description,
            act=act,
            affected_by=affected_by,
            alignment=alignment,
            level=level,
            hitroll=hitroll,
            ac=ac,
            hit=hit,
            damage=damage,
            wealth=wealth,
            xp=xp,
            start_pos=start_pos,
            default_pos=default_pos,
            sex=sex,
        )


@attributes
class MercItem(area_reader.model.Item):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    action_description = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    item_type = area_reader.schema.field(default=-1, type=int, native=NativeField(5, native_number))
    extra_flags = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_number))
    wear_flags = area_reader.schema.field(
        default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS, native=NativeField(7, native_number)
    )
    value = area_reader.schema.field(default=Factory(list), type=list, native=NativeField(8, native_four_numbers))
    weight = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number))
    cost = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number))
    cost_per_day = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number))
    level = attr(default=0, type=int)
    affected = area_reader.schema.field(default=Factory(list), native=NativeField(12, native_records, suffix=""))
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(13, native_records, suffix=""),
    )

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading object %d", vnum)
        name = reader.read_string()
        short_desc = reader.read_string()
        description = reader.read_string()
        action_description = reader.read_string()
        item_type = reader.read_number()
        extra_flags = reader.read_flag()
        wear_flags = reader.read_flag()
        value = [reader.read_number(), reader.read_number(), reader.read_number(), reader.read_number()]
        weight = reader.read_number()
        cost = reader.read_number()
        cost_per_day = reader.read_number()
        affected = []
        extra_descriptions = []
        while True:
            letter = reader.read_letter()
            if letter == "A":
                aff = MercAffectData()
                affected.append(aff)
                aff.type = -1
                aff.duration = -1
                aff.location = reader.read_number()
                aff.modifier = reader.read_number()
            elif letter == "E":
                extra_descriptions.append(reader.read_object(area_reader.model.ExtraDescription))
            else:
                reader.index -= 1
                break
        return cls(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            description=description,
            action_description=action_description,
            item_type=item_type,
            extra_flags=extra_flags,
            wear_flags=wear_flags,
            value=value,
            weight=weight,
            cost=cost,
            cost_per_day=cost_per_day,
            affected=affected,
            extra_descriptions=extra_descriptions,
        )


@attributes
class MercArea:
    NATIVE_SECTIONS = (
        NativeSection("AREA", owner_section="area"),
        NativeSection("HELPS", collection="helps", end="0 $~\n"),
        NativeSection("MOBILES", collection="mobs", end="#0\n", mapping=True),
        NativeSection("OBJECTS", collection="objects", end="#0\n", mapping=True),
        NativeSection("ROOMS", collection="rooms", end="#0\n", mapping=True),
        NativeSection("RESETS", collection="resets", end="S\n"),
        NativeSection("SHOPS", collection="shops", end="0\n"),
        NativeSection("SPECIALS", collection="specials", end="S\n"),
    )

    metadata = area_reader.schema.field(default="", native=NativeField(1, native_tilde_string, section="area"))
    helps = attr(default=Factory(list))
    rooms = attr(default=Factory(OrderedDict))
    mobs = attr(default=Factory(OrderedDict))
    objects = attr(default=Factory(OrderedDict))
    resets = attr(default=Factory(list))
    specials = attr(default=Factory(list))
    shops = attr(default=Factory(list))
    mobprogs = attr(default=Factory(OrderedDict))
