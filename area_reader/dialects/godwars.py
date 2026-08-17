"""GodWars Deluxe area models, codecs, and reader."""

from operator import setitem

from attr import Factory, attr, attributes

import area_reader.dialects.merc
import area_reader.schema
from area_reader.native import NativeField, NativeSection
from area_reader.native import nested as native_nested
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string


@attributes
class GodWarsObjectPower:
    wearer_on = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string, prefix="Q\n"))
    wearer_off = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    wearer_use = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    victim_on = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    victim_off = area_reader.schema.field(default="", type=str, native=NativeField(5, native_tilde_string))
    victim_use = area_reader.schema.field(default="", type=str, native=NativeField(6, native_tilde_string))
    spec_type = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_number, suffix=" "))
    spec_power = area_reader.schema.field(default=0, type=int, native=NativeField(8, native_number))


@attributes
class GodWarsRoomText:
    input = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string, prefix="T\n"))
    output = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    character_output = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    name = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    type = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number, suffix=" "))
    power = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_number, suffix=" "))
    mob = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_number))

    @classmethod
    def read(cls, reader):
        input_text = reader.read_string()
        output = reader.read_string()
        character_output = reader.read_string()
        reader.skip_whitespace()
        name = "" if reader.current_char in "+-0123456789" else reader.read_string()
        return cls(
            input=input_text,
            output=output,
            character_output=character_output,
            name=name,
            type=reader.read_number(),
            power=reader.read_number(),
            mob=reader.read_number(),
        )


@attributes
class GodWarsItem(area_reader.dialects.merc.MercItem):
    power = area_reader.schema.field(
        default=None,
        type=GodWarsObjectPower | None,
        native=NativeField(14, native_nested, suffix="", when=lambda owner: owner.power is not None),
    )

    def read_metadata_record(self, reader, letter):
        if letter == "Q":
            self.power = reader.read_object(GodWarsObjectPower)
            return True
        return super().read_metadata_record(reader, letter)


@attributes
class GodWarsRoom(area_reader.dialects.merc.MercRoom):
    texts = area_reader.schema.field(
        default=Factory(list),
        type=list[GodWarsRoomText],
        native=NativeField(11, native_records, suffix=""),
    )

    def read_metadata_record(self, reader, letter):
        if letter == "T":
            self.texts.append(reader.read_object(GodWarsRoomText))
            return True
        return super().read_metadata_record(reader, letter)


@attributes
class GodWarsArea(area_reader.dialects.merc.MercArea):
    NATIVE_SECTIONS = (
        NativeSection("AREA", owner_section="area", when=lambda area: area.header_format == "area"),
        NativeSection(
            "AREADATA",
            owner_section="areadata",
            end="End\n",
            when=lambda area: area.header_format == "areadata",
        ),
        NativeSection("HELPS", collection="helps", end="0 $~\n"),
        NativeSection("MOBILES", collection="mobs", end="#0\n", mapping=True),
        NativeSection("OBJECTS", collection="objects", end="#0\n", mapping=True),
        NativeSection("ROOMS", collection="rooms", end="#0\n", mapping=True),
        NativeSection("RESETS", collection="resets", end="S\n"),
        NativeSection("SHOPS", collection="shops", end="0\n"),
        NativeSection("SPECIALS", collection="specials", end="S\n"),
    )

    header_format = attr(default=None, type=str | None)
    name = area_reader.schema.field(
        default="", type=str, native=NativeField(1, native_tilde_string, prefix="Name        ", section="areadata")
    )
    builders = area_reader.schema.field(
        default="None",
        type=str,
        native=NativeField(2, native_tilde_string, prefix="Builders    ", section="areadata"),
    )
    first_vnum = area_reader.schema.field(
        default=0,
        type=int,
        native=NativeField(3, native_number, prefix="VNUMs       ", suffix=" ", section="areadata"),
    )
    last_vnum = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_number, section="areadata"))
    security = area_reader.schema.field(
        default=1, type=int, native=NativeField(5, native_number, prefix="Security    ", section="areadata")
    )


class GodWarsAreaFile(area_reader.dialects.merc.MercAreaFile):
    def create_area(self):
        return GodWarsArea()

    def section_readers(self):
        readers = super().section_readers()
        readers["areadata"] = self.read_area_data
        return readers

    def read_area_metadata(self):
        self.area.header_format = "area"
        self.area.metadata = self.read_string()
        self.area.name = self.area.metadata

    def read_area_data(self):
        self.area.header_format = "areadata"
        while True:
            field = self.read_word().lower()
            if field == "end":
                return
            if field == "name":
                self.area.name = self.read_string()
            elif field == "builders":
                self.area.builders = self.read_string()
            elif field == "vnums":
                self.area.first_vnum = self.read_number()
                self.area.last_vnum = self.read_number()
            elif field == "security":
                self.area.security = self.read_number()
            elif field == "reset":
                self.read_to_eol()
            else:
                self.parse_fail(f"Unknown GodWars area metadata field {field!r}")

    def load_objects(self):
        for item in self.load_vnum_section(GodWarsItem):
            setitem(self.area.objects, item.vnum, item)

    def load_rooms(self):
        for room in self.load_vnum_section(GodWarsRoom):
            setitem(self.area.rooms, room.vnum, room)
