"""ACK!MUD area models, codecs, and reader."""

import logging
from collections import OrderedDict
from operator import setitem

from attr import Factory, attr, attributes

import area_reader.dialects.merc
import area_reader.model
import area_reader.parser
import area_reader.schema
import area_reader.values
from area_reader.native import NativeField, NativeSection, NativeWriteError, render_document
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string
from area_reader.native import word as native_word

logger = logging.getLogger("area_reader")

ACK_TEXT_FLAGS = frozenset("BMPST")
ACK_MOB_EXTRA_FIELDS = 7


def native_numbers(value, owner):
    return " ".join(native_number(item, owner) for item in value)


def native_text_line(value, owner):
    del owner
    text = str(value)
    if "\n" in text:
        raise NativeWriteError("ACK flag text cannot span lines")
    return text


@attributes
class AckAreaFlag:
    """A letter-keyed flag line in an ACK ``#AREA`` header, such as ``T`` (teleport allowed)."""

    letter = area_reader.schema.field(default="", type=str, native=NativeField(1, native_word, suffix=" "))
    text = area_reader.schema.field(default="", type=str, native=NativeField(2, native_text_line))


@attributes
class AckExit(area_reader.model.Exit):
    exit_info = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_number, suffix=" "))
    key = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number, suffix=" "))

    @classmethod
    def read(cls, reader, **kwargs):
        door = reader.read_number()
        description = reader.read_string()
        keyword = reader.read_string()
        exit_info = reader.read_number()
        key = reader.read_number()
        destination = reader.read_number()
        return cls(
            door=door,
            description=description,
            keyword=keyword,
            exit_info=exit_info,
            key=key,
            destination=destination,
        )


def native_room_flags_suffix(owner):
    return "\n" if owner.sector_type is None else " "


@attributes
class AckRoom(area_reader.model.Room):
    room_flags = area_reader.schema.field(
        default=0, type=int, native=NativeField(4, native_number, suffix=native_room_flags_suffix)
    )
    # Some shipped ACK rooms omit the sector number entirely; keep that absence rather than inventing one.
    sector_type = area_reader.schema.field(
        default=0,
        type=int | None,
        native=NativeField(5, native_number, when=lambda owner: owner.sector_type is not None),
    )
    area_number = attr(default=0, type=int)
    exits = area_reader.schema.field(
        default=Factory(list), type=list[AckExit], native=NativeField(8, native_records, suffix="")
    )

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading room with vnum %d", vnum)
        room = cls(
            vnum=vnum,
            name=reader.read_string(),
            description=reader.read_string(),
            room_flags=reader.read_number(),
        )
        reader.skip_whitespace()
        room.sector_type = reader.read_number() if reader.current_char in "+-0123456789" else None
        while True:
            letter = reader.read_letter()
            if letter == "S":
                return room
            if letter == "D":
                room.exits.append(AckExit.read(reader=reader))
            elif letter == "E":
                room.extra_descriptions.append(reader.read_object(area_reader.model.ExtraDescription))
            else:
                reader.parse_fail(f"room {vnum} has record {letter!r}, expected D, E, or S")


@attributes
class AckMobprog:
    """An inline Merc 2.2-style MOBprogram: ``>trigger arguments~`` followed by its command list."""

    trigger = area_reader.schema.field(
        default="", type=area_reader.values.Word, native=NativeField(1, native_word, prefix=">", suffix=" ")
    )
    arguments = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    commands = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))


def native_mobprogs(value, owner):
    return native_records(value, owner) + "|"


@attributes
class AckMob:
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    long_desc = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    act = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number, suffix=" "))
    affected_by = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_number, suffix=" "))
    alignment = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_number, suffix=" S\n"))
    level = area_reader.schema.field(default=0, type=int, native=NativeField(8, native_number, suffix=" "))
    sex = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number))
    ac_mod = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number, suffix=" "))
    hr_mod = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number, suffix=" "))
    dr_mod = area_reader.schema.field(default=0, type=int, native=NativeField(12, native_number))
    player_class = area_reader.schema.field(
        default=0, type=int, native=NativeField(13, native_number, prefix="! ", suffix=" ")
    )
    clan = area_reader.schema.field(default=0, type=int, native=NativeField(14, native_number, suffix=" "))
    race = area_reader.schema.field(default=0, type=int, native=NativeField(15, native_number, suffix=" "))
    position = area_reader.schema.field(default=0, type=int, native=NativeField(16, native_number, suffix=" "))
    skills = area_reader.schema.field(default=0, type=int, native=NativeField(17, native_number, suffix=" "))
    cast = area_reader.schema.field(default=0, type=int, native=NativeField(18, native_number, suffix=" "))
    defense = area_reader.schema.field(default=0, type=int, native=NativeField(19, native_number))
    mobprogs = area_reader.schema.field(
        default=Factory(list),
        type=list[AckMobprog],
        native=NativeField(20, native_mobprogs, when=lambda owner: bool(owner.mobprogs)),
    )

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading mob %d", vnum)
        name = reader.read_string()
        short_desc = reader.read_string()
        long_desc = reader.read_string()
        description = reader.read_string()
        act = reader.read_number()
        affected_by = reader.read_number()
        alignment = reader.read_number()
        reader.read_and_verify_letter("S")
        mob = cls(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            long_desc=long_desc,
            description=description,
            act=act,
            affected_by=affected_by,
            alignment=alignment,
            level=reader.read_number(),
            sex=reader.read_number(),
            ac_mod=reader.read_number(),
            hr_mod=reader.read_number(),
            dr_mod=reader.read_number(),
        )
        reader.read_and_verify_letter("!")
        (
            mob.player_class,
            mob.clan,
            mob.race,
            mob.position,
            mob.skills,
            mob.cast,
            mob.defense,
        ) = (reader.read_number() for _ in range(ACK_MOB_EXTRA_FIELDS))
        reader.skip_whitespace()
        if reader.current_char == ">":
            while reader.read_letter() == ">":
                mob.mobprogs.append(
                    AckMobprog(
                        trigger=reader.read_word(), arguments=reader.read_string(), commands=reader.read_string()
                    )
                )
            reader.index -= 1
            reader.read_and_verify_letter("|")
        return mob


@attributes
class AckItem:
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    item_type = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_number, suffix=" "))
    extra_flags = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number, suffix=" "))
    wear_flags = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_number, suffix=" "))
    item_apply = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_number))
    value = area_reader.schema.field(default=Factory(list), type=list, native=NativeField(8, native_numbers))
    weight = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number))
    affected = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.dialects.merc.MercAffectData],
        native=NativeField(10, native_records, suffix=""),
    )
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(11, native_records, suffix=""),
    )
    level = area_reader.schema.field(
        default=None,
        type=int | None,
        native=NativeField(12, native_number, prefix="L\n", when=lambda owner: owner.level is not None),
    )

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading object %d", vnum)
        item = cls(
            vnum=vnum,
            name=reader.read_string(),
            short_desc=reader.read_string(),
            description=reader.read_string(),
            item_type=reader.read_number(),
            extra_flags=reader.read_number(),
            wear_flags=reader.read_number(),
            item_apply=reader.read_number(),
            value=[reader.read_number() for _ in range(4)],
            weight=reader.read_number(),
        )
        while True:
            letter = reader.read_letter()
            if letter == "A":
                item.affected.append(
                    area_reader.dialects.merc.MercAffectData(
                        location=reader.read_number(), modifier=reader.read_number()
                    )
                )
            elif letter == "E":
                item.extra_descriptions.append(reader.read_object(area_reader.model.ExtraDescription))
            elif letter == "L":
                item.level = reader.read_number()
            else:
                reader.index -= 1
                return item


@attributes
class AckArea:
    NATIVE_SECTIONS = (
        NativeSection("AREA", owner_section="area"),
        NativeSection("HELPS", collection="helps", end="0 $~\n", when=lambda area: bool(area.helps)),
        NativeSection("ROOMS", collection="rooms", end="#0\n", mapping=True),
        NativeSection("MOBILES", collection="mobs", end="#0\n", mapping=True),
        NativeSection("OBJECTS", collection="objects", end="#0\n", mapping=True),
        NativeSection("SHOPS", collection="shops", end="0\n"),
        NativeSection("RESETS", collection="resets", end="S\n"),
        NativeSection("SPECIALS", collection="specials", end="S\n"),
        NativeSection("OBJFUNS", collection="objfuns", end="S\n"),
    )

    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string, section="area"))
    keyword = area_reader.schema.field(
        default="", type=str, native=NativeField(2, native_tilde_string, prefix="K ", section="area")
    )
    level_label = area_reader.schema.field(
        default="", type=str, native=NativeField(3, native_tilde_string, prefix="L ", section="area")
    )
    area_number = area_reader.schema.field(
        default=0, type=int, native=NativeField(4, native_number, prefix="N ", section="area")
    )
    min_level = area_reader.schema.field(
        default=0, type=int, native=NativeField(5, native_number, prefix="I ", suffix=" ", section="area")
    )
    max_level = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_number, section="area"))
    first_vnum = area_reader.schema.field(
        default=0, type=int, native=NativeField(7, native_number, prefix="V ", suffix=" ", section="area")
    )
    last_vnum = area_reader.schema.field(default=0, type=int, native=NativeField(8, native_number, section="area"))
    offset = area_reader.schema.field(
        default=0, type=int, native=NativeField(9, native_number, prefix="X ", section="area")
    )
    reset_rate = area_reader.schema.field(
        default=0, type=int, native=NativeField(10, native_number, prefix="F ", section="area")
    )
    reset_message = area_reader.schema.field(
        default="", type=str, native=NativeField(11, native_tilde_string, prefix="U ", section="area")
    )
    owner = area_reader.schema.field(
        default="", type=str, native=NativeField(12, native_tilde_string, prefix="O ", section="area")
    )
    can_read = area_reader.schema.field(
        default="", type=str, native=NativeField(13, native_tilde_string, prefix="R ", section="area")
    )
    can_write = area_reader.schema.field(
        default="", type=str, native=NativeField(14, native_tilde_string, prefix="W ", section="area")
    )
    flags = area_reader.schema.field(
        default=Factory(list),
        type=list[AckAreaFlag],
        native=NativeField(15, native_records, suffix="", section="area"),
    )
    helps = attr(default=Factory(list), type=list[area_reader.model.Help])
    rooms = attr(default=Factory(OrderedDict), type=dict[int, AckRoom])
    mobs = attr(default=Factory(OrderedDict), type=dict[int, AckMob])
    objects = attr(default=Factory(OrderedDict), type=dict[int, AckItem])
    resets = attr(default=Factory(list), type=list[area_reader.dialects.merc.MercReset])
    shops = attr(default=Factory(list), type=list[area_reader.model.RomShop])
    specials = attr(default=Factory(list), type=list[area_reader.model.Special])
    objfuns = attr(default=Factory(list), type=list[area_reader.model.Special])
    mobprogs = attr(default=Factory(OrderedDict))


class AckAreaFile(area_reader.parser.AreaFile):
    def create_area(self):
        return AckArea()

    def dumps(self):
        return render_document(self.area, self.area.NATIVE_SECTIONS, self.skipped_sections)

    def write(self, path):
        with open(path, mode="wt", encoding="latin-1", newline="\n") as area_file:
            area_file.write(self.dumps())

    def section_readers(self):
        readers = super().section_readers()
        readers["objfuns"] = self.load_objfuns
        return readers

    def read_area_metadata(self):
        self.area.name = self.read_string()
        while True:
            self.skip_whitespace()
            if self.current_char in ("#", "\0"):
                return
            letter = self.read_letter()
            if letter == "K":
                self.area.keyword = self.read_string()
            elif letter == "L":
                self.area.level_label = self.read_string()
            elif letter == "N":
                self.area.area_number = self.read_number()
            elif letter == "I":
                self.area.min_level = self.read_number()
                self.area.max_level = self.read_number()
            elif letter == "V":
                self.area.first_vnum = self.read_number()
                self.area.last_vnum = self.read_number()
            elif letter == "X":
                self.area.offset = self.read_number()
            elif letter == "F":
                self.area.reset_rate = self.read_number()
            elif letter == "U":
                self.area.reset_message = self.read_string()
            elif letter == "O":
                self.area.owner = self.read_string()
            elif letter == "R":
                self.area.can_read = self.read_string()
            elif letter == "W":
                self.area.can_write = self.read_string()
            elif letter in ACK_TEXT_FLAGS:
                self.area.flags.append(AckAreaFlag(letter=letter, text=self.read_to_eol().strip()))
            else:
                self.parse_fail(f"Unknown ACK area header key {letter!r}")

    def load_mobiles(self):
        for mob in self.load_vnum_section(AckMob):
            setitem(self.area.mobs, mob.vnum, mob)

    def load_objects(self):
        for item in self.load_vnum_section(AckItem):
            setitem(self.area.objects, item.vnum, item)

    def load_rooms(self):
        for room in self.load_vnum_section(AckRoom):
            setitem(self.area.rooms, room.vnum, room)

    def load_resets(self):
        for reset in self.read_flat_section(area_reader.dialects.merc.MercReset):
            self.area.resets.append(reset)

    def load_objfuns(self):
        for objfun in self.read_flat_section(area_reader.model.Special):
            self.area.objfuns.append(objfun)
