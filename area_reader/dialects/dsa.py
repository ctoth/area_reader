"""Devil's Silence ("DSA Format") area models, codecs, and reader.

DSA is a ROM derivative. Its #AREA header starts with a ``DSA Format~`` marker and ends in keyed
lines; mobiles, objects, rooms, and exits carry ROM bodies followed by keyed lines up to ``End``;
the area help is bare text ended by ``-1 $~``; and resets live inside rooms as ``Reset ...`` lines
instead of a #RESETS section. Keyed lines are kept verbatim because their meaning is DSA-specific.
"""

import logging
from collections import OrderedDict
from operator import setitem

from attr import Factory, attributes

import area_reader.dialects.rom
import area_reader.model
import area_reader.schema
from area_reader.native import NativeField, NativeSection, NativeWriteError, render_document
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string

logger = logging.getLogger("area_reader")

DSA_MARKER = "DSA Format"
DSA_HELP_END = "-1 $~"
DSA_RECORD_END = "End"
# Keyed lines whose value is a tilde-terminated string; every other key's value runs to end of line.
DSA_STRING_KEYS = frozenset({"Bldrs", "Descr", "Spec"})
DSA_RESET_KEY = "Reset"


def native_key(value, owner):
    del owner
    text = str(value)
    if not text or any(char.isspace() for char in text):
        raise NativeWriteError(f"DSA key {text!r} must be one word")
    return text


def native_keyed_value(value, owner):
    if owner.key in DSA_STRING_KEYS:
        return native_tilde_string(value, owner)
    text = str(value)
    if "\n" in text:
        raise NativeWriteError(f"DSA {owner.key} value cannot span lines")
    return text


def native_keyed_block(value, owner):
    return native_records(value, owner) + DSA_RECORD_END


@attributes
class DsaKeyedLine:
    """One ``Key value`` trailer line, such as ``MaxWorld 1``, ``Flags AB``, or ``Reset O 5412 1 100 0``."""

    key = area_reader.schema.field(default="", type=str, native=NativeField(1, native_key, suffix=" "))
    value = area_reader.schema.field(default="", type=str, native=NativeField(2, native_keyed_value))


def read_keyed_lines(reader):
    lines = []
    while True:
        key = reader.read_word()
        if key == DSA_RECORD_END:
            return lines
        if not key:
            reader.parse_fail("Unterminated DSA keyed block, expected End")
        if key in DSA_STRING_KEYS:
            value = reader.read_string()
        else:
            value = reader.read_to_eol().strip()
        lines.append(DsaKeyedLine(key=key, value=value))


@attributes
class DsaMob(area_reader.dialects.rom.RomMob):
    trailer_text = area_reader.schema.field(default="", type=str, native=NativeField(30, native_tilde_string))
    keyed = area_reader.schema.field(
        default=Factory(list), type=list[DsaKeyedLine], native=NativeField(31, native_keyed_block)
    )

    @classmethod
    def read(cls, reader, vnum, **kwargs):
        mob = super().read(reader, vnum, **kwargs)
        mob.trailer_text = reader.read_string()
        mob.keyed = read_keyed_lines(reader)
        return mob


@attributes
class DsaItem(area_reader.dialects.rom.RomItem):
    trailer_text = area_reader.schema.field(default="", type=str, native=NativeField(15, native_tilde_string))
    keyed = area_reader.schema.field(
        default=Factory(list), type=list[DsaKeyedLine], native=NativeField(16, native_keyed_block)
    )

    @classmethod
    def read(cls, reader, vnum=None, **kwargs):
        item = super().read(reader, vnum=vnum, **kwargs)
        item.trailer_text = reader.read_string()
        item.keyed = read_keyed_lines(reader)
        return item


@attributes
class DsaExit(area_reader.model.Exit):
    keyed = area_reader.schema.field(
        default=Factory(list), type=list[DsaKeyedLine], native=NativeField(7, native_keyed_block)
    )

    @classmethod
    def read(cls, reader, **kwargs):
        exit = super().read(reader, **kwargs)
        exit.keyed = read_keyed_lines(reader)
        return exit


def native_reset_comment(value, owner):
    del owner
    text = str(value)
    if "\n" in text:
        raise NativeWriteError("DSA reset comments cannot span lines")
    return f" {text}" if text else ""


@attributes
class DsaReset:
    """A room-embedded ``Reset <command> <vnum> <arg2> <arg3> <arg4> <comment>`` line.

    DSA writes four numbers for every command (e.g. ``M 21904 1 100 0``, ``E 21916 16 100 0``); their meaning
    past the vnum is DSA-specific, so they are kept positionally.
    """

    command = area_reader.schema.field(default="", type=str, native=NativeField(1, native_key, prefix="Reset "))
    arg1 = area_reader.schema.field(default=0, type=int, native=NativeField(2, native_number, prefix=" ", suffix=""))
    arg2 = area_reader.schema.field(default=0, type=int, native=NativeField(3, native_number, prefix=" ", suffix=""))
    arg3 = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_number, prefix=" ", suffix=""))
    arg4 = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number, prefix=" ", suffix=""))
    comment = area_reader.schema.field(default="", type=str, native=NativeField(6, native_reset_comment))


def native_dsa_room_suffix(owner):
    return "S\n" + native_records(owner.resets, owner) + native_keyed_block(owner.keyed, owner) + "\n"


@attributes
class DsaRoom(area_reader.model.Room):
    NATIVE_SUFFIX = staticmethod(native_dsa_room_suffix)

    exits = area_reader.schema.field(
        default=Factory(list), type=list[DsaExit], native=NativeField(8, native_records, suffix="")
    )
    resets = area_reader.schema.field(default=Factory(list), type=list[DsaReset])
    keyed = area_reader.schema.field(default=Factory(list), type=list[DsaKeyedLine])

    def read_trailer(self, reader):
        while True:
            key = reader.read_word()
            if key == DSA_RECORD_END:
                return
            if key == DSA_RESET_KEY:
                self.resets.append(
                    DsaReset(
                        command=reader.read_word(),
                        arg1=reader.read_number(),
                        arg2=reader.read_number(),
                        arg3=reader.read_number(),
                        arg4=reader.read_number(),
                        comment=reader.read_to_eol().strip(),
                    )
                )
            elif not key:
                reader.parse_fail("Unterminated DSA room, expected End")
            else:
                reader.index -= len(key)
                self.keyed.extend(read_keyed_lines(reader))
                return

    def read_metadata(self, reader):
        while True:
            letter = reader.read_letter()
            if letter == "S":
                self.read_trailer(reader)
                return
            if letter == "D":
                self.exits.append(DsaExit.read(reader=reader))
            elif letter == "E":
                self.extra_descriptions.append(reader.read_object(area_reader.model.ExtraDescription))
            elif letter == "H":
                self.heal_rate = reader.read_number()
            elif letter == "M":
                self.mana_rate = reader.read_number()
            elif letter == "C":
                self.clan = reader.read_string()
            elif letter == "O":
                self.owner = reader.read_string()
            else:
                reader.parse_fail(f"Don't know how to process DSA room attribute: {letter}")


def native_dsa_help_text(value, owner):
    del owner
    text = "".join(help.text for help in value)
    if DSA_HELP_END in text:
        raise NativeWriteError(f"DSA help text cannot contain {DSA_HELP_END!r}")
    return text


@attributes
class DsaArea(area_reader.dialects.rom.RomArea):
    NATIVE_SECTIONS = (
        NativeSection("AREA", owner_section="area"),
        NativeSection("HELPS", owner_section="helps", end=DSA_HELP_END + "\n", when=lambda area: bool(area.helps)),
        NativeSection("MOBILES", collection="mobs", end="#0\n", mapping=True),
        NativeSection("OBJECTS", collection="objects", end="#0\n", mapping=True),
        NativeSection("ROOMS", collection="rooms", end="#0\n", mapping=True),
        NativeSection("RESETS", collection="resets", end="S\n", when=lambda area: bool(area.resets)),
        NativeSection("SPECIALS", collection="specials", end="S\n"),
        NativeSection("SHOPS", collection="shops", end="0\n"),
        NativeSection("MOBPROGS", owner_section="mobprogs", end="#0\n", when=lambda area: bool(area.mobprogs)),
    )

    marker = area_reader.schema.field(
        default=DSA_MARKER, type=str, native=NativeField(0, native_tilde_string, section="area")
    )
    header_keyed = area_reader.schema.field(
        default=Factory(list), type=list[DsaKeyedLine], native=NativeField(6, native_keyed_block, section="area")
    )
    helps = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.Help],
        native=NativeField(1, native_dsa_help_text, suffix="", section="helps"),
    )
    rooms = area_reader.schema.field(default=Factory(OrderedDict), type=dict[int, DsaRoom])
    mobs = area_reader.schema.field(default=Factory(OrderedDict), type=dict[int, DsaMob])
    objects = area_reader.schema.field(default=Factory(OrderedDict), type=dict[int, DsaItem])


class DsaAreaFile(area_reader.dialects.rom.RomAreaFile):
    def create_area(self):
        return DsaArea()

    def dumps(self):
        return render_document(self.area, self.area.NATIVE_SECTIONS, self.skipped_sections)

    def read_area_metadata(self):
        marker = self.read_string()
        if marker != DSA_MARKER:
            self.parse_fail(f"Expected {DSA_MARKER!r} marker, got {marker!r}")
        self.area.original_filename = self.read_string()
        self.area.name = self.read_string()
        self.area.metadata = self.read_string()
        self.area.first_vnum = self.read_number()
        self.area.last_vnum = self.read_number()
        self.area.header_keyed = read_keyed_lines(self)

    def load_helps(self):
        self.skip_whitespace()
        end = self.data.find(DSA_HELP_END, self.index)
        if end == -1:
            self.parse_fail(f"Unterminated DSA help, expected {DSA_HELP_END!r}")
        text = self.data[self.index : end]
        self.index = end + len(DSA_HELP_END)
        if text:
            self.area.helps.append(area_reader.model.Help(level=0, keyword="", text=text))

    def load_mobiles(self):
        for mob in self.load_vnum_section(DsaMob):
            setitem(self.area.mobs, mob.vnum, mob)

    def load_objects(self):
        for item in self.load_vnum_section(DsaItem):
            setitem(self.area.objects, item.vnum, item)

    def load_rooms(self):
        for room in self.load_vnum_section(DsaRoom):
            setitem(self.area.rooms, room.vnum, room)
