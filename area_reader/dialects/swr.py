"""SWR/FUSS area models, codecs, and reader."""

from collections import OrderedDict

from attr import Factory, attr, attributes

import area_reader.dialects.rom
import area_reader.dialects.smaug
import area_reader.model
import area_reader.schema
import area_reader.values
from area_reader.native import NativeField, NativeSection, NativeWriteError
from area_reader.native import number as native_number
from area_reader.native import raw as native_raw
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string
from area_reader.native import word as native_word


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
