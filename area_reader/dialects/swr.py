"""SWR/FUSS area models, codecs, and reader."""

from collections import OrderedDict
from operator import setitem

from attr import Factory, attr, attributes

import area_reader.dialects.rom
import area_reader.dialects.smaug
import area_reader.model
import area_reader.schema
import area_reader.serialization
import area_reader.values
from area_reader.native import NativeField, NativeSection, NativeWriteError, render_document
from area_reader.native import number as native_number
from area_reader.native import raw as native_raw
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string
from area_reader.native import word as native_word


class SwrAreaFile(area_reader.dialects.smaug.SmaugAreaFile):
    def create_area(self):
        return SwrArea()

    def __init__(self, filename):
        super().__init__(filename)
        if not self.data.lstrip().startswith("#FUSSAREA"):
            self.area = area_reader.dialects.smaug.SmaugArea()

    def dumps(self):
        return render_document(self.area, self.area.NATIVE_SECTIONS, self.skipped_sections)

    def write(self, path):
        with open(path, mode="wt", encoding="latin-1", newline="\n") as area_file:
            area_file.write(self.dumps())

    def load_sections(self):
        self.skip_whitespace()
        if self.data.startswith("#FUSSAREA", self.index):
            self.read_section_name()
            self.load_fuss_area()
            return
        if self.current_char == "#":
            start = self.index
            self.advance()
            word = self.read_word()
            self.index = start
            if word.isdigit():
                for mob in self.load_smaug_vnum_section(area_reader.dialects.smaug.SmaugMob):
                    setitem(self.area.mobs, mob.vnum, mob)
                return
        super().load_sections()

    def load_mobiles(self):
        for mob in self.load_swr_vnum_section(area_reader.dialects.smaug.SmaugMob):
            setitem(self.area.mobs, mob.vnum, mob)

    def load_objects(self):
        for item in self.load_swr_vnum_section(area_reader.dialects.smaug.SmaugItem):
            setitem(self.area.objects, item.vnum, item)

    def load_rooms(self):
        for room in self.load_swr_vnum_section(area_reader.dialects.smaug.SmaugRoom):
            setitem(self.area.rooms, room.vnum, room)

    def load_swr_vnum_section(self, section_object_type):
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
            self.skip_whitespace()
            if vnum == 0 and (self.index >= len(self.data) or self.current_char == "#"):
                break
            yield self.read_object(section_object_type, vnum=vnum)

    def load_fuss_area(self):
        while True:
            self.skip_whitespace()
            if self.index >= len(self.data):
                return
            section_name = self.read_section_name()
            self.current_section_name = section_name
            if section_name == "areadata":
                self.load_fuss_areadata()
            elif section_name == "mobile":
                mob = self.read_fuss_mobile()
                setitem(self.area.mobs, mob.vnum, mob)
            elif section_name == "object":
                item = self.read_fuss_object()
                setitem(self.area.objects, item.vnum, item)
            elif section_name == "room":
                room = self.read_fuss_room()
                setitem(self.area.rooms, room.vnum, room)
                self.area.resets.extend(room.resets)
            elif section_name == "endarea":
                return
            else:
                self.skip_fuss_value()

    def read_fuss_unknown(self, key):
        line_end = self.data.find("\n", self.index)
        if line_end == -1:
            line_end = len(self.data)
        if "~" in self.data[self.index : line_end]:
            return SwrUnknown(key=key, value=self.read_string(), tilde=True)
        return SwrUnknown(key=key, value=self.read_to_eol().strip(), tilde=False)

    def skip_fuss_value(self):
        return self.read_fuss_unknown("")

    def read_fuss_numbers(self):
        return [int(value) for value in self.read_to_eol().split()]

    def read_fuss_program(self):
        program = SwrProgram()
        while True:
            word = self.read_word()
            if word == "#ENDPROG":
                return program
            if word == "Progtype":
                program.progtype = self.read_string()
            elif word == "Arglist":
                program.argument = self.read_string()
            elif word == "Comlist":
                program.commands = self.read_string()
            else:
                program.unknown.append(self.read_fuss_unknown(word))

    def load_fuss_areadata(self):
        while True:
            word = self.read_word()
            if word == "#ENDAREADATA":
                return
            if word == "Author":
                self.area.author = self.read_string()
            elif word == "Economy":
                self.area.high_economy = self.read_number()
                self.area.low_economy = self.read_number()
            elif word == "Flags":
                self.area.flags = self.read_string()
            elif word == "Name":
                self.area.name = self.read_string()
            elif word == "Ranges":
                values = self.read_fuss_numbers()
                if len(values) >= 4:
                    self.area.low_soft_range = values[0]
                    self.area.high_soft_range = values[1]
                    self.area.low_hard_range = values[2]
                    self.area.high_hard_range = values[3]
            elif word == "ResetMsg":
                self.area.resetmsg = self.read_string()
            elif word == "ResetFreq":
                self.area.reset_frequency = self.read_number()
            elif word == "Version":
                self.area.version = self.read_number()
            else:
                self.area.unknown.append(self.read_fuss_unknown(word))

    def read_fuss_mobile(self):
        mob = SwrMobile()
        while True:
            word = self.read_word()
            if word == "#ENDMOBILE":
                break
            if word == "#MUDPROG":
                mob.programs.append(self.read_fuss_program())
            elif word == "Vnum":
                mob.vnum = self.read_number()
            elif word == "Keywords":
                mob.name = self.read_string()
            elif word == "Short":
                mob.short_desc = self.read_string()
            elif word == "Long":
                mob.long_desc = self.read_string()
            elif word == "Desc":
                mob.description = self.read_string()
            elif word == "Race":
                mob.race = self.read_string()
            elif word == "Position":
                mob.position = self.read_string()
            elif word == "DefPos":
                mob.default_position = self.read_string()
            elif word == "Gender":
                mob.gender = self.read_string()
            elif word == "Stats1":
                mob.stats1 = self.read_fuss_numbers()
            elif word == "Stats2":
                mob.stats2 = self.read_fuss_numbers()
            elif word == "Stats3":
                mob.stats3 = self.read_fuss_numbers()
            elif word == "Stats4":
                mob.stats4 = self.read_fuss_numbers()
            elif word == "Attribs":
                mob.attribs = self.read_fuss_numbers()
            elif word == "Saves":
                mob.saves = self.read_fuss_numbers()
            elif word == "ShopData":
                mob.shop_data = self.read_fuss_numbers()
            elif word == "RepairData":
                mob.repair_data = self.read_fuss_numbers()
            elif word in (
                "Specfun",
                "Specfun2",
                "Actflags",
                "Affected",
                "Speaks",
                "Speaking",
                "Bodyparts",
                "Resist",
                "Immune",
                "Suscept",
                "Attacks",
                "Defenses",
                "VIPFlags",
            ):
                attribute = {
                    "Specfun": "specfun",
                    "Specfun2": "specfun2",
                    "Actflags": "actflags",
                    "Affected": "affected",
                    "Speaks": "speaks",
                    "Speaking": "speaking",
                    "Bodyparts": "bodyparts",
                    "Resist": "resist",
                    "Immune": "immune",
                    "Suscept": "suscept",
                    "Attacks": "attacks",
                    "Defenses": "defenses",
                    "VIPFlags": "vip_flags",
                }[word]
                setattr(mob, attribute, self.read_string())
            else:
                mob.unknown.append(self.read_fuss_unknown(word))
        stats1 = list(mob.stats1)
        stats2 = list(mob.stats2)
        stats3 = list(mob.stats3)
        stats4 = list(mob.stats4)
        while len(stats1) < 6:
            stats1.append(0)
        while len(stats2) < 3:
            stats2.append(0)
        while len(stats3) < 3:
            stats3.append(0)
        while len(stats4) < 5:
            stats4.append(0)
        mob.alignment = stats1[0]
        mob.level = stats1[1]
        mob.thac0 = stats1[2]
        mob.ac = area_reader.dialects.rom.RomArmorClass(
            pierce=stats1[3], bash=stats1[3], slash=stats1[3], exotic=stats1[3]
        )
        mob.wealth = stats1[4]
        mob.experience = stats1[5]
        mob.hit = area_reader.model.Dice(number=stats2[0], sides=stats2[1], bonus=stats2[2])
        mob.damage = area_reader.model.Dice(number=stats3[0], sides=stats3[1], bonus=stats3[2])
        mob.height = stats4[0]
        mob.weight = stats4[1]
        mob.numattacks = stats4[2]
        mob.hitroll = stats4[3]
        mob.damroll = stats4[4]
        mob.start_pos = mob.position
        mob.default_pos = mob.default_position
        mob.sex = mob.gender
        return mob

    def read_fuss_object(self):
        item = SwrObject()
        while True:
            word = self.read_word()
            if word == "#ENDOBJECT":
                break
            if word == "#EXDESC":
                item.extra_descriptions.append(self.read_fuss_extra_description())
            elif word == "#MUDPROG":
                item.programs.append(self.read_fuss_program())
            elif word == "Vnum":
                item.vnum = self.read_number()
            elif word == "Keywords":
                item.name = self.read_string()
            elif word == "Short":
                item.short_desc = self.read_string()
            elif word == "Long":
                item.description = self.read_string()
            elif word == "Type":
                item.type_name = self.read_string()
            elif word == "Action":
                item.action_description = self.read_string()
            elif word == "Flags":
                item.flags = self.read_string()
            elif word == "WFlags":
                item.wflags = self.read_string()
            elif word == "Values":
                item.value = self.read_fuss_numbers()
            elif word == "Stats":
                item.stats = self.read_fuss_numbers()
            elif word == "Spells":
                item.spells = self.read_to_eol().strip()
            else:
                item.unknown.append(self.read_fuss_unknown(word))
        if len(item.stats) > 0:
            item.weight = item.stats[0]
        if len(item.stats) > 1:
            item.cost = item.stats[1]
        if len(item.stats) > 2:
            item.rent = item.stats[2]
        if len(item.stats) > 3:
            item.level = item.stats[3]
        if len(item.stats) > 4:
            item.layers = item.stats[4]
        return item

    def read_fuss_room(self):
        room = SwrRoom()
        while True:
            word = self.read_word()
            if word == "#ENDROOM":
                break
            if word == "#EXIT":
                room.exits.append(self.read_fuss_exit())
            elif word == "#EXDESC":
                room.extra_descriptions.append(self.read_fuss_extra_description())
            elif word == "#MUDPROG":
                room.programs.append(self.read_fuss_program())
            elif word == "Vnum":
                room.vnum = self.read_number()
            elif word == "Name":
                room.name = self.read_string()
            elif word == "Desc":
                room.description = self.read_string()
            elif word == "Sector":
                room.sector = self.read_string()
            elif word == "Stats":
                room.stats = self.read_fuss_numbers()
            elif word == "Reset":
                letter = self.read_letter()
                room.resets.append(SwrReset.read(reader=self, letter=letter))
            elif word == "Flags":
                room.flags = self.read_string()
            else:
                room.unknown.append(self.read_fuss_unknown(word))
        if len(room.stats) > 0:
            room.tele_delay = room.stats[0]
        if len(room.stats) > 1:
            room.tele_vnum = room.stats[1]
        if len(room.stats) > 2:
            room.tunnel = room.stats[2]
        return room

    def read_fuss_exit(self):
        exit = SwrExit()
        while True:
            word = self.read_word()
            if word == "#ENDEXIT":
                return exit
            if word == "Desc":
                exit.description = self.read_string()
            elif word == "Direction":
                exit.door = self.read_string()
            elif word == "Distance":
                exit.distance = self.read_number()
            elif word == "Key":
                exit.key = self.read_number()
            elif word == "Keywords":
                exit.keyword = self.read_string()
            elif word == "ToRoom":
                exit.destination = self.read_number()
            elif word == "Flags":
                exit.flags = self.read_string()
            else:
                exit.unknown.append(self.read_fuss_unknown(word))

    def read_fuss_extra_description(self):
        extra = SwrExtraDescription()
        while True:
            word = self.read_word()
            if word == "#ENDEXDESC":
                return extra
            if word == "ExDescKey":
                extra.keyword = self.read_string()
            elif word == "ExDesc":
                extra.description = self.read_string()
            else:
                extra.unknown.append(self.read_fuss_unknown(word))

    def skip_fuss_program(self):
        self.read_fuss_program()


def native_swr_unknown_value(value, owner):
    if owner.tilde:
        return native_tilde_string(value, owner)
    return native_raw(value, owner)


def native_swr_reset_arg2_suffix(owner):
    return "" if owner.command in ("G", "R") else " "


def native_swr_armor_class(value, owner):
    del owner
    classes = (value.pierce, value.bash, value.slash, value.exotic)
    if len(set(classes)) != 1:
        raise NativeWriteError("SWR mobiles require one armor class value")
    return native_number(value.pierce, None)


def native_swr_dice(value, owner):
    del owner
    return f"{value.number} {value.sides} {value.bonus}"


@attributes
class SwrUnknown:
    key = area_reader.schema.field(
        default="", type=area_reader.values.Word, native=NativeField(1, native_word, suffix=" ")
    )
    value = area_reader.schema.field(default="", type=str, native=NativeField(2, native_swr_unknown_value))
    tilde = attr(default=False, type=bool)


@attributes
class SwrProgram:
    NATIVE_PREFIX = "#MUDPROG\n"
    NATIVE_SUFFIX = "#ENDPROG\n\n"

    progtype = area_reader.schema.field(
        default="", type=str, native=NativeField(1, native_tilde_string, prefix="Progtype  ")
    )
    argument = area_reader.schema.field(
        default="", type=str, native=NativeField(2, native_tilde_string, prefix="Arglist   ")
    )
    commands = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(3, native_tilde_string, prefix="Comlist   ", when=lambda owner: bool(owner.commands)),
    )
    unknown = area_reader.schema.field(
        default=Factory(list), type=list[SwrUnknown], native=NativeField(4, native_records, suffix="")
    )


@attributes
class SwrExtraDescription:
    NATIVE_PREFIX = "#EXDESC\n"
    NATIVE_SUFFIX = "#ENDEXDESC\n\n"

    keyword = area_reader.schema.field(
        default="", type=str, native=NativeField(1, native_tilde_string, prefix="ExDescKey ")
    )
    description = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(2, native_tilde_string, prefix="ExDesc    ", when=lambda owner: bool(owner.description)),
    )
    unknown = area_reader.schema.field(
        default=Factory(list), type=list[SwrUnknown], native=NativeField(3, native_records, suffix="")
    )


@attributes
class SwrExit:
    NATIVE_PREFIX = "#EXIT\n"
    NATIVE_SUFFIX = "#ENDEXIT\n\n"

    door = area_reader.schema.field(
        default="", type=str, native=NativeField(1, native_tilde_string, prefix="Direction ")
    )
    destination = area_reader.schema.field(
        default=0, type=int, native=NativeField(2, native_number, prefix="ToRoom    ")
    )
    key = area_reader.schema.field(
        default=0, type=int, native=NativeField(3, native_number, prefix="Key       ", when=lambda owner: owner.key > 0)
    )
    distance = area_reader.schema.field(
        default=0,
        type=int,
        native=NativeField(4, native_number, prefix="Distance  ", when=lambda owner: owner.distance != 0),
    )
    description = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(5, native_tilde_string, prefix="Desc      ", when=lambda owner: bool(owner.description)),
    )
    keyword = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(6, native_tilde_string, prefix="Keywords  ", when=lambda owner: bool(owner.keyword)),
    )
    flags = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(7, native_tilde_string, prefix="Flags     ", when=lambda owner: bool(owner.flags)),
    )
    unknown = area_reader.schema.field(
        default=Factory(list), type=list[SwrUnknown], native=NativeField(8, native_records, suffix="")
    )


@attributes
class SwrReset:
    NATIVE_PREFIX = "Reset "

    command = area_reader.schema.field(
        default="", type=area_reader.values.Letter, native=NativeField(1, native_word, suffix=" ")
    )
    if_flag = area_reader.schema.field(default=0, type=int, native=NativeField(2, native_number, suffix=" "))
    arg1 = area_reader.schema.field(default=0, type=int, native=NativeField(3, native_number, suffix=" "))
    arg2 = area_reader.schema.field(
        default=0, type=int, native=NativeField(4, native_number, suffix=native_swr_reset_arg2_suffix)
    )
    arg3 = area_reader.schema.field(
        default=0,
        type=int,
        native=NativeField(5, native_number, suffix="", when=lambda owner: owner.command not in ("G", "R")),
    )
    comment = area_reader.schema.field(default="", type=str, native=NativeField(6, area_reader.model.native_comment))

    @classmethod
    def read(cls, reader, letter):
        if_flag = reader.read_number()
        arg1 = reader.read_number()
        arg2 = reader.read_number()
        arg3 = 0 if letter in ("G", "R") else reader.read_number()
        return cls(command=letter, if_flag=if_flag, arg1=arg1, arg2=arg2, arg3=arg3, comment=reader.read_to_eol())


@attributes
class SwrMobile(area_reader.dialects.rom.RomCharacter):
    NATIVE_PREFIX = "#MOBILE\n"
    NATIVE_SUFFIX = "#ENDMOBILE\n\n"

    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="Vnum       ")
    )
    name = area_reader.schema.field(
        default="", type=str, native=NativeField(2, native_tilde_string, prefix="Keywords   ")
    )
    short_desc = area_reader.schema.field(
        default="", type=str, native=NativeField(3, native_tilde_string, prefix="Short      ")
    )
    long_desc = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(4, native_tilde_string, prefix="Long       ", when=lambda owner: bool(owner.long_desc)),
    )
    description = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(5, native_tilde_string, prefix="Desc       ", when=lambda owner: bool(owner.description)),
    )
    race = area_reader.schema.field(
        default="", type=str, native=NativeField(6, native_tilde_string, prefix="Race       ")
    )
    position = area_reader.schema.field(
        default="", type=str, native=NativeField(7, native_tilde_string, prefix="Position   ")
    )
    default_position = area_reader.schema.field(
        default="", type=str, native=NativeField(8, native_tilde_string, prefix="DefPos     ")
    )
    specfun = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(9, native_tilde_string, prefix="Specfun    ", when=lambda owner: bool(owner.specfun)),
    )
    specfun2 = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(10, native_tilde_string, prefix="Specfun2   ", when=lambda owner: bool(owner.specfun2)),
    )
    gender = area_reader.schema.field(
        default="", type=str, native=NativeField(11, native_tilde_string, prefix="Gender     ")
    )
    actflags = area_reader.schema.field(
        default="", type=str, native=NativeField(12, native_tilde_string, prefix="Actflags   ")
    )
    affected = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(13, native_tilde_string, prefix="Affected   ", when=lambda owner: bool(owner.affected)),
    )
    stats1 = attr(default=Factory(list), type=list, eq=False)
    stats2 = attr(default=Factory(list), type=list, eq=False)
    stats3 = attr(default=Factory(list), type=list, eq=False)
    stats4 = attr(default=Factory(list), type=list, eq=False)
    alignment = area_reader.schema.field(
        default=0, type=int, native=NativeField(14, native_number, prefix="Stats1     ", suffix=" ")
    )
    level = area_reader.schema.field(default=0, type=int, native=NativeField(15, native_number, suffix=" "))
    thac0 = area_reader.schema.field(default=0, type=int, native=NativeField(16, native_number, suffix=" "))
    ac = area_reader.schema.field(
        default=Factory(area_reader.dialects.rom.RomArmorClass),
        type=area_reader.dialects.rom.RomArmorClass,
        native=NativeField(17, native_swr_armor_class, suffix=" "),
    )
    wealth = area_reader.schema.field(default=0, type=int, native=NativeField(18, native_number, suffix=" "))
    experience = area_reader.schema.field(default=0, type=int, native=NativeField(19, native_number))
    hit = area_reader.schema.field(
        default=Factory(area_reader.model.Dice),
        type=area_reader.model.Dice,
        native=NativeField(20, native_swr_dice, prefix="Stats2     "),
    )
    damage = area_reader.schema.field(
        default=Factory(area_reader.model.Dice),
        type=area_reader.model.Dice,
        native=NativeField(21, native_swr_dice, prefix="Stats3     "),
    )
    height = area_reader.schema.field(
        default=0, type=int, native=NativeField(22, native_number, prefix="Stats4     ", suffix=" ")
    )
    weight = area_reader.schema.field(default=0, type=int, native=NativeField(23, native_number, suffix=" "))
    numattacks = area_reader.schema.field(default=0, type=int, native=NativeField(24, native_number, suffix=" "))
    hitroll = area_reader.schema.field(default=0, type=int, native=NativeField(25, native_number, suffix=" "))
    damroll = area_reader.schema.field(default=0, type=int, native=NativeField(26, native_number))
    attribs = area_reader.schema.field(
        default=Factory(list),
        type=list,
        native=NativeField(
            27, area_reader.dialects.smaug.native_numbers, prefix="Attribs    ", when=lambda owner: bool(owner.attribs)
        ),
    )
    saves = area_reader.schema.field(
        default=Factory(list),
        type=list,
        native=NativeField(
            28, area_reader.dialects.smaug.native_numbers, prefix="Saves      ", when=lambda owner: bool(owner.saves)
        ),
    )
    speaks = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(29, native_tilde_string, prefix="Speaks     ", when=lambda owner: bool(owner.speaks)),
    )
    speaking = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(30, native_tilde_string, prefix="Speaking   ", when=lambda owner: bool(owner.speaking)),
    )
    bodyparts = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(31, native_tilde_string, prefix="Bodyparts  ", when=lambda owner: bool(owner.bodyparts)),
    )
    resist = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(32, native_tilde_string, prefix="Resist     ", when=lambda owner: bool(owner.resist)),
    )
    immune = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(33, native_tilde_string, prefix="Immune     ", when=lambda owner: bool(owner.immune)),
    )
    suscept = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(34, native_tilde_string, prefix="Suscept    ", when=lambda owner: bool(owner.suscept)),
    )
    attacks = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(35, native_tilde_string, prefix="Attacks    ", when=lambda owner: bool(owner.attacks)),
    )
    defenses = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(36, native_tilde_string, prefix="Defenses   ", when=lambda owner: bool(owner.defenses)),
    )
    vip_flags = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(37, native_tilde_string, prefix="VIPFlags   ", when=lambda owner: bool(owner.vip_flags)),
    )
    shop_data = area_reader.schema.field(
        default=Factory(list),
        type=list,
        native=NativeField(
            38,
            area_reader.dialects.smaug.native_numbers,
            prefix="ShopData   ",
            when=lambda owner: bool(owner.shop_data),
        ),
    )
    repair_data = area_reader.schema.field(
        default=Factory(list),
        type=list,
        native=NativeField(
            39,
            area_reader.dialects.smaug.native_numbers,
            prefix="RepairData ",
            when=lambda owner: bool(owner.repair_data),
        ),
    )
    programs = area_reader.schema.field(
        default=Factory(list), type=list[SwrProgram], native=NativeField(40, native_records, suffix="")
    )
    unknown = area_reader.schema.field(
        default=Factory(list), type=list[SwrUnknown], native=NativeField(41, native_records, suffix="")
    )
    start_pos = attr(default="", type=str)
    default_pos = attr(default="", type=str)
    sex = attr(default="", type=str)


@attributes
class SwrObject(area_reader.model.Item):
    NATIVE_PREFIX = "#OBJECT\n"
    NATIVE_SUFFIX = "#ENDOBJECT\n\n"

    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="Vnum     ")
    )
    name = area_reader.schema.field(
        default="", type=str, native=NativeField(2, native_tilde_string, prefix="Keywords ")
    )
    type_name = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(3, native_tilde_string, prefix="Type     ", when=lambda owner: bool(owner.type_name)),
    )
    short_desc = area_reader.schema.field(
        default="", type=str, native=NativeField(4, native_tilde_string, prefix="Short    ")
    )
    description = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(5, native_tilde_string, prefix="Long     ", when=lambda owner: bool(owner.description)),
    )
    action_description = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(
            6, native_tilde_string, prefix="Action   ", when=lambda owner: bool(owner.action_description)
        ),
    )
    flags = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(7, native_tilde_string, prefix="Flags    ", when=lambda owner: bool(owner.flags)),
    )
    wflags = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(8, native_tilde_string, prefix="WFlags   ", when=lambda owner: bool(owner.wflags)),
    )
    value = area_reader.schema.field(
        default=Factory(list),
        type=list,
        native=NativeField(9, area_reader.dialects.smaug.native_numbers, prefix="Values   "),
    )
    stats = attr(default=Factory(list), type=list, eq=False)
    weight = area_reader.schema.field(
        default=0, type=int, native=NativeField(10, native_number, prefix="Stats    ", suffix=" ")
    )
    cost = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number, suffix=" "))
    rent = area_reader.schema.field(default=0, type=int, native=NativeField(12, native_number, suffix=" "))
    level = area_reader.schema.field(default=0, type=int, native=NativeField(13, native_number, suffix=" "))
    layers = area_reader.schema.field(default=0, type=int, native=NativeField(14, native_number))
    spells = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(15, native_raw, prefix="Spells   ", when=lambda owner: bool(owner.spells)),
    )
    extra_descriptions = area_reader.schema.field(
        default=Factory(list), type=list[SwrExtraDescription], native=NativeField(16, native_records, suffix="")
    )
    programs = area_reader.schema.field(
        default=Factory(list), type=list[SwrProgram], native=NativeField(17, native_records, suffix="")
    )
    unknown = area_reader.schema.field(
        default=Factory(list), type=list[SwrUnknown], native=NativeField(18, native_records, suffix="")
    )


@attributes
class SwrRoom(area_reader.model.MudBase):
    NATIVE_PREFIX = "#ROOM\n"
    NATIVE_SUFFIX = "#ENDROOM\n\n"

    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="Vnum     ")
    )
    name = area_reader.schema.field(
        default="", type=str, native=NativeField(2, native_tilde_string, prefix="Name     ")
    )
    sector = area_reader.schema.field(
        default="", type=str, native=NativeField(3, native_tilde_string, prefix="Sector   ")
    )
    flags = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(4, native_tilde_string, prefix="Flags    ", when=lambda owner: bool(owner.flags)),
    )
    stats = attr(default=Factory(list), type=list, eq=False)
    tele_delay = area_reader.schema.field(
        default=0,
        type=int,
        native=NativeField(
            5,
            native_number,
            prefix="Stats    ",
            suffix=" ",
            when=lambda owner: any((owner.tele_delay, owner.tele_vnum, owner.tunnel)),
        ),
    )
    tele_vnum = area_reader.schema.field(
        default=0,
        type=int,
        native=NativeField(
            6, native_number, suffix=" ", when=lambda owner: any((owner.tele_delay, owner.tele_vnum, owner.tunnel))
        ),
    )
    tunnel = area_reader.schema.field(
        default=0,
        type=int,
        native=NativeField(7, native_number, when=lambda owner: any((owner.tele_delay, owner.tele_vnum, owner.tunnel))),
    )
    description = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(8, native_tilde_string, prefix="Desc     ", when=lambda owner: bool(owner.description)),
    )
    exits = area_reader.schema.field(
        default=Factory(list), type=list[SwrExit], native=NativeField(9, native_records, suffix="")
    )
    resets = area_reader.schema.field(
        default=Factory(list), type=list[SwrReset], native=NativeField(10, native_records, suffix="")
    )
    extra_descriptions = area_reader.schema.field(
        default=Factory(list), type=list[SwrExtraDescription], native=NativeField(11, native_records, suffix="")
    )
    programs = area_reader.schema.field(
        default=Factory(list), type=list[SwrProgram], native=NativeField(12, native_records, suffix="")
    )
    unknown = area_reader.schema.field(
        default=Factory(list), type=list[SwrUnknown], native=NativeField(13, native_records, suffix="")
    )


@attributes
class SwrArea(area_reader.dialects.smaug.SmaugArea):
    NATIVE_END = "#ENDAREA\n"
    NATIVE_SECTIONS = (
        NativeSection("FUSSAREA", owner_section="fuss_header"),
        NativeSection("AREADATA", owner_section="area", end="#ENDAREADATA\n\n"),
        NativeSection("MOBILE", collection="mobs", mapping=True, emit_header=False),
        NativeSection("OBJECT", collection="objects", mapping=True, emit_header=False),
        NativeSection("ROOM", collection="rooms", mapping=True, emit_header=False),
    )

    version = area_reader.schema.field(
        default=0, type=int, native=NativeField(1, native_number, prefix="Version    ", section="area")
    )
    name = area_reader.schema.field(
        default="", type=str, native=NativeField(2, native_tilde_string, prefix="Name       ", section="area")
    )
    author = area_reader.schema.field(
        default="", type=str, native=NativeField(3, native_tilde_string, prefix="Author     ", section="area")
    )
    low_soft_range = area_reader.schema.field(
        default=0, type=int, native=NativeField(4, native_number, prefix="Ranges     ", suffix=" ", section="area")
    )
    high_soft_range = area_reader.schema.field(
        default=0, type=int, native=NativeField(5, native_number, suffix=" ", section="area")
    )
    low_hard_range = area_reader.schema.field(
        default=0, type=int, native=NativeField(6, native_number, suffix=" ", section="area")
    )
    high_hard_range = area_reader.schema.field(
        default=0, type=int, native=NativeField(7, native_number, section="area")
    )
    high_economy = area_reader.schema.field(
        default=0, type=int, native=NativeField(8, native_number, prefix="Economy    ", suffix=" ", section="area")
    )
    low_economy = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number, section="area"))
    resetmsg = area_reader.schema.field(
        default="",
        type=str,
        native=NativeField(
            10, native_tilde_string, prefix="ResetMsg   ", section="area", when=lambda owner: bool(owner.resetmsg)
        ),
    )
    reset_frequency = area_reader.schema.field(
        default=0,
        type=int,
        native=NativeField(
            11, native_number, prefix="ResetFreq  ", section="area", when=lambda owner: owner.reset_frequency != 0
        ),
    )
    flags = area_reader.schema.field(
        default="",
        native=NativeField(
            12, native_tilde_string, prefix="Flags      ", section="area", when=lambda owner: bool(owner.flags)
        ),
    )
    unknown = area_reader.schema.field(
        default=Factory(list), type=list[SwrUnknown], native=NativeField(13, native_records, section="area", suffix="")
    )
    mobs = attr(default=Factory(OrderedDict), type=dict[int, SwrMobile])
    objects = attr(default=Factory(OrderedDict), type=dict[int, SwrObject])
    rooms = attr(default=Factory(OrderedDict), type=dict[int, SwrRoom])
