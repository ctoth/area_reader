"""SMAUG area models, codecs, and reader."""

import logging
from collections import OrderedDict
from operator import setitem

from attr import Factory, attr, attributes

import area_reader.dialects.merc
import area_reader.dialects.rom
import area_reader.model
import area_reader.parser
import area_reader.schema
import area_reader.serialization
import area_reader.values
from area_reader.constants import (
    EXIT_FLAGS,
    FORMS,
    IMM_FLAGS,
    OFFENSE,
    PARTS,
    SMAUG_ACT_TYPES,
    SMAUG_AFFECTED_BY,
    WEAR_FLAGS,
)
from area_reader.native import NativeField, NativeSection, render_record
from area_reader.native import flag as native_flag
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string
from area_reader.native import word as native_word


class SmaugAreaFile(area_reader.dialects.rom.RomAreaFile):
    MAX_FIX = 3

    def create_area(self):
        return SmaugArea()

    def skip_smaug_programs(self):
        self.skip_whitespace()
        while self.current_char == ">":
            program_end = self.data.find("\n|\n", self.index)
            if program_end == -1:
                program_end = self.data.find("\r\n|\r\n", self.index)
            if program_end != -1:
                self.index = program_end + 3
                self.skip_whitespace()
                continue
            next_record = self.data.find("\n#", self.index)
            if next_record == -1:
                self.index = len(self.data) - 1
                return
            self.index = next_record + 1

    def read_smaug_programs(self):
        programs = []
        self.skip_whitespace()
        while self.current_char == ">":
            self.read_and_verify_letter(">")
            programs.append(
                SmaugProgram(
                    trigger=self.read_word(),
                    argument=self.read_string(),
                    commands=self.read_string(),
                )
            )
            self.skip_whitespace()
        self.read_and_verify_letter("|")
        return programs

    def load_sections(self):
        readers = {
            "area": self.read_area_metadata,
            "author": self.load_author,
            "credits": self.load_credits,
            "flags": self.load_flags,
            "ranges": self.load_ranges,
            "version": self.load_version,
            "resetmsg": self.load_resetmsg,
            "economy": self.load_economy,
            "helps": self.load_helps,
            "mobiles": self.load_mobiles,
            "objects": self.load_objects,
            "rooms": self.load_rooms,
            "resets": self.load_resets,
            "shops": self.load_shops,
            "specials": self.load_specials,
            "repairs": self.load_repairs,
            "continent": self.load_continent,
            "climate": self.load_climate,
            "spelllimit": self.load_spelllimit,
        }
        while True:
            self.skip_whitespace()
            if self.index >= len(self.data):
                return
            section_name = self.read_section_name()
            self.current_section_name = section_name
            if section_name == "$":
                return
            reader = readers.get(section_name)
            if reader is None:
                self.skip_section(section_name)
            else:
                logger.info(f"Processing section {section_name}")
                try:
                    reader()
                except area_reader.parser.ParseError:
                    raise
                except Exception as error:  # noqa: BLE001 - add parser source context to arbitrary model errors
                    self.parse_fail(f"Error reading section {section_name!r}: {error!r}")

    def read_area_metadata(self):
        self.area.name = self.read_string()

    def load_author(self):
        self.area.author = self.read_string()

    def load_credits(self):
        self.area.credits = self.read_string()

    def load_flags(self):
        self.area.flags = self.read_number()
        line = self.read_to_eol().strip()
        self.area.reset_frequency = int(line.split()[0]) if line else 0

    def load_ranges(self):
        self.area.low_soft_range = self.read_number()
        self.area.high_soft_range = self.read_number()
        self.area.low_hard_range = self.read_number()
        self.area.high_hard_range = self.read_number()
        self.read_word()  # $

    def load_version(self):
        self.area.version = self.read_number()

    def load_continent(self):
        self.area.continent = self.read_string()

    def load_climate(self):
        self.area.climate = self.read_number_line()

    def load_spelllimit(self):
        self.area.spelllimit = self.read_number()

    def load_mobiles(self):
        for mob in self.load_smaug_vnum_section(SmaugMob):
            setitem(self.area.mobs, mob.vnum, mob)

    def load_objects(self):
        for item in self.load_smaug_vnum_section(SmaugItem):
            setitem(self.area.objects, item.vnum, item)

    def load_rooms(self):
        for room in self.load_smaug_vnum_section(SmaugRoom):
            setitem(self.area.rooms, room.vnum, room)

    def load_smaug_vnum_section(self, section_object_type):
        while True:
            self.skip_whitespace()
            if self.index >= len(self.data):
                break
            if self.current_char != "#":
                self.parse_fail(f"Expected # got {self.current_char}")
            next_char = self.data[self.index + 1 : self.index + 2]
            if not (next_char.isdigit() or next_char == "-"):
                break
            vnum = self.read_vnum()
            if vnum == 0:
                break
            yield self.read_object(section_object_type, vnum=vnum)

    def load_resets(self):
        for reset in self.read_flat_section(area_reader.dialects.merc.MercReset):
            self.area.resets.append(reset)

    def load_repairs(self):
        while True:
            keeper = self.read_number()
            if keeper == 0:
                break
            fix_type = [self.read_number() for _ in range(self.MAX_FIX)]
            profit_fix = self.read_number()
            shop_type = self.read_number()
            open_hour = self.read_number()
            close_hour = self.read_number()
            comment = self.read_to_eol()
            self.area.repairs.append(
                SmaugRepair(
                    keeper=keeper,
                    fix_type=fix_type,
                    profit_fix=profit_fix,
                    shop_type=shop_type,
                    open_hour=open_hour,
                    close_hour=close_hour,
                    comment=comment,
                )
            )

    def load_resetmsg(self):
        self.area.resetmsg = self.read_string()

    def load_economy(self):
        self.area.high_economy = self.read_number()
        self.area.low_economy = self.read_number()

    def load_room(self, vnum):
        logger.debug("Reading room %d", vnum)
        room = area_reader.model.Room(vnum=vnum)
        room.name = self.read_string()
        room.description = self.read_string()
        room.area_number = self.read_number()
        room.room_flags = self.read_flag()
        self.read_line()
        # room.sector_type, room.tele_delay, room.tele_vnum, room.tunnel, room.max_weight = map(int, line.split())
        self.read_room_data(room)
        return room

    def read_line(self):
        return self.read_to_eol()


logger = logging.getLogger("area_reader")


def native_numbers(value, owner):
    del owner
    return " ".join(native_number(item, None) for item in value)


def native_words(value, owner):
    del owner
    return " ".join(native_word(item, None) for item in value)


def native_number_lines(value, owner):
    del owner
    return "\n".join(native_numbers(line, None) for line in value)


def native_smaug_programs(value, owner):
    del owner
    if not value:
        return ""
    return "".join(render_record(program) for program in value) + "|\n"


def native_dice_inline(value, owner):
    del owner
    return f"{value.number}d{value.sides}{value.bonus:+d}"


@attributes
class SmaugProgram:
    trigger = area_reader.schema.field(
        default="", type=area_reader.values.Word, native=NativeField(1, native_word, prefix="> ", suffix=" ")
    )
    argument = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    commands = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))


@attributes
class SmaugMap:
    vnum = area_reader.schema.field(default=0, type=int, native=NativeField(1, native_number, prefix="M ", suffix=" "))
    x = area_reader.schema.field(default=0, type=int, native=NativeField(2, native_number, suffix=" "))
    y = area_reader.schema.field(default=0, type=int, native=NativeField(3, native_number, suffix=" "))
    entry = area_reader.schema.field(default="", type=area_reader.values.Letter, native=NativeField(4, native_word))


@attributes
class SmaugRepair:
    keeper = area_reader.schema.field(default=0, type=int, native=NativeField(1, native_number, suffix=" "))
    fix_type = area_reader.schema.field(
        default=Factory(list), type=list, native=NativeField(2, native_numbers, suffix=" ")
    )
    profit_fix = area_reader.schema.field(default=0, type=int, native=NativeField(3, native_number, suffix=" "))
    shop_type = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_number, suffix=" "))
    open_hour = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number, suffix=" "))
    close_hour = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_number, suffix=""))
    comment = area_reader.schema.field(default="", type=str, native=NativeField(7, area_reader.model.native_comment))


@attributes
class SmaugExit(area_reader.model.Exit):
    door = area_reader.schema.field(default=None, type=int, native=NativeField(1, native_number, prefix="D"))
    description = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    keyword = area_reader.schema.field(
        default="", type=area_reader.values.Word, native=NativeField(3, native_tilde_string)
    )
    locks = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_number, suffix=" "))
    exit_info = attr(default=0, type=EXIT_FLAGS, converter=EXIT_FLAGS)
    key = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number, suffix=" "))
    destination = area_reader.schema.field(default=None, type=int, native=NativeField(6, native_number, suffix=" "))
    distance = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_number, suffix=" "))
    x = attr(default=0, type=int)
    y = attr(default=0, type=int)
    pulltype = area_reader.schema.field(default=0, type=int, native=NativeField(8, native_number, suffix=" "))
    pull = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number))


@attributes
class SmaugMob(area_reader.dialects.rom.RomMob):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    long_desc = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    race = attr(default="", type=str)
    act = area_reader.schema.field(
        default=SMAUG_ACT_TYPES.IS_NPC.value,
        type=SMAUG_ACT_TYPES,
        converter=SMAUG_ACT_TYPES,
        native=NativeField(5, native_flag, suffix=" "),
    )
    affected_by = area_reader.schema.field(
        default=0, type=SMAUG_AFFECTED_BY, converter=SMAUG_AFFECTED_BY, native=NativeField(6, native_flag, suffix=" ")
    )
    alignment = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_number, suffix=" "))
    native_type = area_reader.schema.field(
        default="S", type=area_reader.values.Letter, native=NativeField(8, native_word)
    )
    group = attr(default=0, type=int)
    level = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number, suffix=" "))
    hitroll = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number, suffix=" "))
    ac = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number, suffix=" "))
    hit = area_reader.schema.field(
        default=Factory(area_reader.model.Dice),
        type=area_reader.model.Dice,
        native=NativeField(12, native_dice_inline, suffix=" "),
    )
    mana = attr(default=Factory(area_reader.model.Dice), type=area_reader.model.Dice)
    damage = area_reader.schema.field(
        default=Factory(area_reader.model.Dice), type=area_reader.model.Dice, native=NativeField(13, native_dice_inline)
    )
    damtype = attr(default="", type=area_reader.values.Word)
    economy_lines = area_reader.schema.field(
        default=Factory(list),
        type=list,
        native=NativeField(14, native_number_lines, when=lambda owner: bool(owner.economy_lines)),
    )
    position_line = area_reader.schema.field(default=Factory(list), type=list, native=NativeField(15, native_numbers))
    complex_lines = area_reader.schema.field(
        default=Factory(list),
        type=list,
        native=NativeField(16, native_number_lines, when=lambda owner: bool(owner.complex_lines)),
    )
    wealth = attr(default=0, type=int)
    start_pos = attr(default=0, type=int)
    default_pos = attr(default=0, type=int)
    sex = attr(default=0, type=int)
    off_flags = attr(default=0, type=OFFENSE, converter=OFFENSE)
    imm_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
    res_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
    vuln_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
    form = attr(default=0, type=FORMS, converter=FORMS)
    parts = attr(default=0, type=PARTS, converter=PARTS)
    size = attr(default=None, type=area_reader.values.Word)
    material = attr(default="", type=str)
    mprogs = attr(default=Factory(list), type=list[area_reader.dialects.rom.RomMobprog] | None)
    programs = area_reader.schema.field(
        default=Factory(list), type=list[SmaugProgram], native=NativeField(17, native_smaug_programs, suffix="")
    )

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading SMAUG mob %d", vnum)
        name = reader.read_string()
        short_desc = reader.read_string()
        long_desc = reader.read_string()
        description = reader.read_string()
        act = reader.read_flag() | SMAUG_ACT_TYPES.IS_NPC
        affected_by = reader.read_flag()
        alignment = reader.read_number()
        letter = reader.read_letter()
        level = reader.read_number()
        hitroll = reader.read_number()
        ac = reader.read_number()
        hit = area_reader.model.Dice.read(reader=reader)
        damage = area_reader.model.Dice.read(reader=reader)
        if letter not in ("S", "C", "V"):
            reader.parse_fail(f"Reading SMAUG MOB vnum {vnum} unexpected type {letter}")
        numeric_lines = []
        while True:
            reader.skip_whitespace()
            if reader.current_char == "#" or reader.current_char == ">":
                break
            numeric_lines.append(reader.read_number_line())
        complex_line_count = 0
        if letter in ("C", "V"):
            complex_line_count = 4
        if letter == "V":
            complex_line_count = 5
        position_index = len(numeric_lines) - complex_line_count - 1
        if position_index < 0:
            reader.parse_fail(f"SMAUG MOB vnum {vnum} missing position line")
        position_line = numeric_lines[position_index]
        if len(position_line) < 3:
            reader.parse_fail(f"SMAUG MOB vnum {vnum} malformed position line")
        money_values = []
        for line in numeric_lines[:position_index]:
            money_values.extend(line)
        wealth = money_values[0] if money_values else 0
        start_pos = position_line[0]
        default_pos = position_line[1]
        sex = position_line[2]
        economy_lines = numeric_lines[:position_index]
        complex_lines = numeric_lines[position_index + 1 :]
        programs = reader.read_smaug_programs() if reader.current_char == ">" else []
        return cls(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            long_desc=long_desc,
            description=description,
            act=act,
            affected_by=affected_by,
            alignment=alignment,
            native_type=letter,
            level=level,
            hitroll=hitroll,
            ac=ac,
            hit=hit,
            damage=damage,
            economy_lines=economy_lines,
            position_line=position_line,
            complex_lines=complex_lines,
            wealth=wealth,
            start_pos=start_pos,
            default_pos=default_pos,
            sex=sex,
            programs=programs,
        )


@attributes
class SmaugItem(area_reader.model.Item):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    action_description = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    item_type = area_reader.schema.field(default=-1, type=int, native=NativeField(5, native_number, suffix=" "))
    extra_flags = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_flag, suffix=" "))
    wear_flags = area_reader.schema.field(
        default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS, native=NativeField(7, native_flag, suffix=" ")
    )
    header_tail = area_reader.schema.field(default=Factory(list), type=list, native=NativeField(8, native_numbers))
    layers = attr(default=0, type=int)
    level = attr(default=0, type=int)
    value = area_reader.schema.field(default=Factory(list), type=list, native=NativeField(9, native_numbers))
    weight = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number, suffix=" "))
    cost = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number, suffix=" "))
    cost_tail = area_reader.schema.field(default=Factory(list), type=list, native=NativeField(12, native_numbers))
    spell_words = area_reader.schema.field(
        default=Factory(list),
        type=list,
        native=NativeField(13, native_words, when=lambda owner: bool(owner.spell_words)),
    )
    affected = area_reader.schema.field(default=Factory(list), native=NativeField(14, native_records, suffix=""))
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(15, native_records, suffix=""),
    )
    programs = area_reader.schema.field(
        default=Factory(list), type=list[SmaugProgram], native=NativeField(16, native_smaug_programs, suffix="")
    )

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading SMAUG object %d", vnum)
        name = reader.read_string()
        short_desc = reader.read_string()
        description = reader.read_string()
        action_description = reader.read_string()
        item_type = reader.read_number()
        extra_flags = reader.read_flag()
        wear_flags = reader.read_flag()
        header = [int(value) for value in reader.read_to_eol().split()]
        layers = header[0] if len(header) > 0 else 0
        level = header[1] if len(header) > 1 else 0
        reader.skip_whitespace()
        value = [int(value) for value in reader.read_to_eol().split()]
        reader.skip_whitespace()
        cost_line = [int(value) for value in reader.read_to_eol().split()]
        weight = cost_line[0] if len(cost_line) > 0 else 0
        cost = cost_line[1] if len(cost_line) > 1 else 0
        cost_tail = cost_line[2:]
        reader.skip_whitespace()
        spell_words = []
        if reader.current_char not in ("A", "E", ">", "#"):
            spell_words = reader.read_to_eol().split()
        affected = []
        extra_descriptions = []
        programs = []
        while True:
            letter = reader.read_letter()
            if letter == "A":
                aff = area_reader.dialects.merc.MercAffectData()
                affected.append(aff)
                aff.type = -1
                aff.duration = -1
                aff.location = reader.read_number()
                aff.modifier = reader.read_number()
            elif letter == "E":
                extra_descriptions.append(reader.read_object(area_reader.model.ExtraDescription))
            elif letter == ">":
                reader.index -= 1
                programs = reader.read_smaug_programs()
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
            header_tail=header,
            value=value,
            level=level,
            weight=weight,
            cost=cost,
            cost_tail=cost_tail,
            spell_words=spell_words,
            affected=affected,
            extra_descriptions=extra_descriptions,
            layers=layers,
            programs=programs,
        )


@attributes
class SmaugRoom(area_reader.model.Room):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    owner = attr(default=None, type=str)
    clan = attr(default="", type=str)
    area_number = area_reader.schema.field(default=0, type=int, native=NativeField(3, native_number, suffix=" "))
    room_flags = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_flag, suffix=" "))
    sector_type = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number, suffix=" "))
    heal_rate = attr(default=100, type=int)
    mana_rate = attr(default=100, type=int)
    tele_delay = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_number, suffix=" "))
    tele_vnum = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_number, suffix=" "))
    tunnel = area_reader.schema.field(default=0, type=int, native=NativeField(8, native_number, suffix=" "))
    max_weight = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number))
    exits = area_reader.schema.field(
        default=Factory(list), type=list[SmaugExit], native=NativeField(10, native_records, suffix="")
    )
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(11, native_records, suffix=""),
    )
    maps = area_reader.schema.field(
        default=Factory(list), type=list[SmaugMap], native=NativeField(12, native_records, suffix="")
    )
    programs = area_reader.schema.field(
        default=Factory(list), type=list[SmaugProgram], native=NativeField(13, native_smaug_programs, suffix="")
    )
    light = attr(default=0)

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading SMAUG room with vnum %d", vnum)
        name = reader.read_string()
        description = reader.read_string()
        area_number = reader.read_number()
        room_flags = reader.read_flag()
        line = reader.read_to_eol()
        values = [int(value) for value in line.split()]
        while len(values) < 5:
            values.append(0)
        room = cls(
            vnum=vnum,
            name=name,
            description=description,
            area_number=area_number,
            room_flags=room_flags,
            sector_type=values[0],
            tele_delay=values[1],
            tele_vnum=values[2],
            tunnel=values[3],
            max_weight=values[4],
        )
        room.read_metadata(reader)
        return room

    def read_metadata(self, reader):
        while True:
            letter = reader.read_letter()
            if letter == "S":
                break
            if letter == "D":
                self.exits.append(self.read_exit(reader))
            elif letter == "E":
                self.extra_descriptions.append(reader.read_object(area_reader.model.ExtraDescription))
            elif letter == "M":
                self.maps.append(
                    SmaugMap(
                        vnum=reader.read_number(),
                        x=reader.read_number(),
                        y=reader.read_number(),
                        entry=reader.read_letter(),
                    )
                )
            elif letter == ">":
                reader.index -= 1
                self.programs = reader.read_smaug_programs()
            else:
                reader.parse_fail(f"SMAUG room {self.vnum} has unknown flag {letter}")

    def read_exit(self, reader):
        door = reader.read_number()
        description = reader.read_string()
        keyword = reader.read_string()
        reader.skip_whitespace()
        line = reader.read_to_eol()
        values = [int(value) for value in line.split()]
        while len(values) < 6:
            values.append(0)
        locks, key, destination, distance, pulltype, pull = values[:6]
        if locks == 1:
            exit_info = EXIT_FLAGS.ISDOOR
        elif locks == 2:
            exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF
        else:
            exit_info = locks
        return SmaugExit(
            door=door,
            description=description,
            keyword=keyword,
            locks=locks,
            exit_info=exit_info,
            key=key,
            destination=destination,
            distance=distance,
            pulltype=pulltype,
            pull=pull,
        )


@attributes
class SmaugArea(area_reader.dialects.rom.RomArea):
    NATIVE_SECTIONS = (
        NativeSection("AREA", owner_section="area"),
        NativeSection("VERSION", owner_section="version", when=lambda area: area.version != 0),
        NativeSection("AUTHOR", owner_section="author", when=lambda area: bool(area.author)),
        NativeSection("CREDITS", owner_section="credits", when=lambda area: bool(area.credits)),
        NativeSection("RANGES", owner_section="ranges"),
        NativeSection("RESETMSG", owner_section="resetmsg", when=lambda area: bool(area.resetmsg)),
        NativeSection("FLAGS", owner_section="flags"),
        NativeSection("ECONOMY", owner_section="economy"),
        NativeSection("CONTINENT", owner_section="continent", when=lambda area: bool(area.continent)),
        NativeSection("CLIMATE", owner_section="climate", when=lambda area: bool(area.climate)),
        NativeSection("SPELLLIMIT", owner_section="spelllimit", when=lambda area: area.spelllimit != 0),
        NativeSection("HELPS", collection="helps", end="0 $~\n"),
        NativeSection("MOBILES", collection="mobs", end="#0\n", mapping=True),
        NativeSection("OBJECTS", collection="objects", end="#0\n", mapping=True),
        NativeSection("ROOMS", collection="rooms", end="#0\n", mapping=True),
        NativeSection("RESETS", collection="resets", end="S\n"),
        NativeSection("SHOPS", collection="shops", end="0\n"),
        NativeSection("REPAIRS", collection="repairs", end="0\n"),
        NativeSection("SPECIALS", collection="specials", end="S\n"),
    )

    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string, section="area"))
    metadata = attr(default="", type=str)
    original_filename = attr(default="", type=str)
    first_vnum = attr(default=-1, type=int)
    last_vnum = attr(default=-1, type=int)
    version = area_reader.schema.field(default=0, type=int, native=NativeField(1, native_number, section="version"))
    author = area_reader.schema.field(
        default="", type=str, native=NativeField(1, native_tilde_string, section="author")
    )
    credits = area_reader.schema.field(
        default="", type=str, native=NativeField(1, native_tilde_string, section="credits")
    )
    low_soft_range = area_reader.schema.field(
        default=0, type=int, native=NativeField(1, native_number, suffix=" ", section="ranges")
    )
    high_soft_range = area_reader.schema.field(
        default=0, type=int, native=NativeField(2, native_number, suffix=" ", section="ranges")
    )
    low_hard_range = area_reader.schema.field(
        default=0, type=int, native=NativeField(3, native_number, suffix=" ", section="ranges")
    )
    high_hard_range = area_reader.schema.field(
        default=0, type=int, native=NativeField(4, native_number, suffix="\n$\n", section="ranges")
    )
    resetmsg = area_reader.schema.field(
        default="", type=str, native=NativeField(1, native_tilde_string, section="resetmsg")
    )
    flags = area_reader.schema.field(
        default=0, type=int, native=NativeField(1, native_number, suffix=" ", section="flags")
    )
    reset_frequency = area_reader.schema.field(
        default=0, type=int, native=NativeField(2, native_number, section="flags")
    )
    high_economy = area_reader.schema.field(
        default=0, type=int, native=NativeField(1, native_number, suffix=" ", section="economy")
    )
    low_economy = area_reader.schema.field(default=0, type=int, native=NativeField(2, native_number, section="economy"))
    continent = area_reader.schema.field(
        default="", type=str, native=NativeField(1, native_tilde_string, section="continent")
    )
    climate = area_reader.schema.field(
        default=Factory(list), type=list, native=NativeField(1, native_numbers, section="climate")
    )
    spelllimit = area_reader.schema.field(
        default=0, type=int, native=NativeField(1, native_number, section="spelllimit")
    )
    helps = attr(default=Factory(list), type=list[area_reader.model.Help])
    rooms = attr(default=Factory(OrderedDict))
    mobs = attr(default=Factory(OrderedDict))
    objects = attr(default=Factory(OrderedDict))
    resets = attr(default=Factory(list))
    specials = attr(default=Factory(list))
    shops = attr(default=Factory(list))
    repairs = attr(default=Factory(list), type=list[SmaugRepair])
