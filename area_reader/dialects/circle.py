"""CircleMUD area models, codecs, and reader."""

import enum
from collections import OrderedDict

from attr import Factory, attr, attributes

import area_reader.dialects.rom
import area_reader.model
import area_reader.schema
import area_reader.values
from area_reader.constants import EXIT_FLAGS, WEAR_FLAGS
from area_reader.native import NativeField, NativeWriteError, render_record
from area_reader.native import flag as native_flag
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string


def circle_asciiflag_conv(flag):
    flag = str(flag)
    if flag.isdigit():
        return int(flag)
    flags = 0
    for char in flag:
        if char.islower():
            flags |= 1 << (ord(char) - ord("a"))
        elif char.isupper():
            flags |= 1 << (26 + ord(char) - ord("A"))
    return flags


def native_circle_numbers(value, owner):
    del owner
    if not isinstance(value, (list, tuple)) or len(value) != 4 or not all(isinstance(item, int) for item in value):
        raise NativeWriteError("Circle object values require exactly four integers")
    return " ".join(str(item) for item in value)


def native_circle_number_lines(value, owner):
    del owner
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, int) for item in value):
        raise NativeWriteError("Expected a sequence of integers")
    return "".join(f"{item}\n" for item in value)


def native_circle_text_lines(value, owner):
    del owner
    if not isinstance(value, (list, tuple)):
        raise NativeWriteError("Expected a sequence of lines")
    lines = []
    for item in value:
        text = str(item)
        if "\n" in text or "\r" in text:
            raise NativeWriteError("A native line cannot contain a newline")
        lines.append(text + "\n")
    return "".join(lines)


def native_circle_messages(value, owner):
    del owner
    if len(value) != 7:
        raise NativeWriteError("Circle shops require exactly seven messages")
    return "".join(native_tilde_string(message, None) + "\n" for message in value)


def native_circle_dice(value, owner):
    del owner
    if not isinstance(value, area_reader.model.Dice):
        raise NativeWriteError("Expected Circle dice")
    return f"{value.number}d{value.sides}{value.bonus:+d}"


def native_circle_hitroll(value, owner):
    del owner
    if not isinstance(value, int):
        raise NativeWriteError("Expected an integer hitroll")
    return str(20 - value)


def native_circle_armor_class(value, owner):
    del owner
    if not isinstance(value, int):
        raise NativeWriteError("Expected an integer armor class")
    if value % 10:
        raise NativeWriteError(f"Armor class {value!r} is not divisible by ten")
    return str(value // 10)


def native_circle_exit_lock(value, owner):
    del owner
    locks = {
        int(EXIT_FLAGS.NONE): 0,
        int(EXIT_FLAGS.ISDOOR): 1,
        int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF): 2,
    }
    try:
        return str(locks[int(value)])
    except (KeyError, TypeError, ValueError):
        raise NativeWriteError(f"Exit flags {value!r} have no Circle lock code")


def native_circle_mobile_type(value, owner):
    if value not in ("S", "E"):
        raise NativeWriteError("Circle mobile type must be 'S' or 'E'")
    if value == "S" and owner.especs:
        raise NativeWriteError("Simple Circle mobiles cannot contain especs")
    return value


def native_circle_especs(value, owner):
    del owner
    lines = []
    for key, item in value.items():
        if any(char in str(key) for char in ":\r\n") or any(char in str(item) for char in "\r\n"):
            raise NativeWriteError("Invalid Circle enhanced-mobile espec")
        lines.append(f"{key}: {item}\n")
    return "".join(lines)


def native_circle_reset_command(value, owner):
    if value not in ("M", "O", "E", "P", "D", "G", "R"):
        raise NativeWriteError(f"unsupported Circle reset command {value!r}")
    if value in ("G", "R") and owner.arg3 is not None:
        raise NativeWriteError(f"{value} resets must omit arg3")
    if value not in ("G", "R") and owner.arg3 is None:
        raise NativeWriteError(f"{value} resets requires arg3")
    return value


def native_circle_float(value, owner):
    del owner
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise NativeWriteError("Expected a number")
    return str(float(value))


def native_circle_mapping_records(value, owner):
    del owner
    return "".join(render_record(record) for record in value.values())


class CircleMobFlags(enum.IntFlag):
    SPEC = 1 << 0
    SENTINEL = 1 << 1
    SCAVENGER = 1 << 2
    ISNPC = 1 << 3
    AWARE = 1 << 4
    AGGRESSIVE = 1 << 5
    STAY_ZONE = 1 << 6
    WIMPY = 1 << 7
    AGGR_EVIL = 1 << 8
    AGGR_GOOD = 1 << 9
    AGGR_NEUTRAL = 1 << 10
    MEMORY = 1 << 11
    HELPER = 1 << 12
    NOCHARM = 1 << 13
    NOSUMMON = 1 << 14
    NOSLEEP = 1 << 15
    NOBASH = 1 << 16
    NOBLIND = 1 << 17
    NOTDEADYET = 1 << 18


@attributes
class CircleExit:
    door = area_reader.schema.field(default=0, native=NativeField(1, native_number, prefix="D"))
    description = area_reader.schema.field(default="", native=NativeField(2, native_tilde_string))
    keyword = area_reader.schema.field(default="", native=NativeField(3, native_tilde_string))
    exit_info = area_reader.schema.field(
        default=EXIT_FLAGS.NONE,
        type=EXIT_FLAGS,
        converter=EXIT_FLAGS,
        native=NativeField(4, native_circle_exit_lock, suffix=" "),
    )
    key = area_reader.schema.field(default=-1, native=NativeField(5, native_number, suffix=" "))
    destination = area_reader.schema.field(default=-1, native=NativeField(6, native_number))


@attributes
class CircleRoom(area_reader.model.MudBase):
    NATIVE_SUFFIX = "S\n"

    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    zone_number = area_reader.schema.field(default=0, native=NativeField(4, native_number, suffix=" "))
    room_flags = area_reader.schema.field(default=0, native=NativeField(5, native_flag, suffix=" "))
    sector_type = area_reader.schema.field(default=0, native=NativeField(6, native_number))
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(7, native_records, suffix=""),
    )
    exits = area_reader.schema.field(
        default=Factory(dict), native=NativeField(8, native_circle_mapping_records, suffix="")
    )
    source_file = attr(default="", type=str)


@attributes
class CircleMob(area_reader.dialects.rom.RomCharacter):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    long_desc = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(5, native_tilde_string))
    act = area_reader.schema.field(
        default=CircleMobFlags.ISNPC.value,
        type=CircleMobFlags,
        converter=CircleMobFlags,
        native=NativeField(6, native_flag, suffix=" "),
    )
    affected_by = area_reader.schema.field(default=0, native=NativeField(7, native_flag, suffix=" "))
    alignment = area_reader.schema.field(default=0, native=NativeField(8, native_number, suffix=" "))
    mob_type = area_reader.schema.field(default="S", type=str, native=NativeField(9, native_circle_mobile_type))
    level = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number, suffix=" "))
    hitroll = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_circle_hitroll, suffix=" "))
    ac = area_reader.schema.field(default=0, native=NativeField(12, native_circle_armor_class, suffix=" "))
    hit = area_reader.schema.field(
        default=Factory(area_reader.model.Dice),
        type=area_reader.model.Dice,
        native=NativeField(13, native_circle_dice, suffix=" "),
    )
    damage = area_reader.schema.field(
        default=Factory(area_reader.model.Dice), type=area_reader.model.Dice, native=NativeField(14, native_circle_dice)
    )
    wealth = area_reader.schema.field(default=0, native=NativeField(15, native_number, suffix=" "))
    exp = area_reader.schema.field(default=0, native=NativeField(16, native_number))
    default_pos = area_reader.schema.field(default=0, native=NativeField(17, native_number, suffix=" "))
    start_pos = area_reader.schema.field(default=0, native=NativeField(18, native_number, suffix=" "))
    sex = area_reader.schema.field(default=0, native=NativeField(19, native_number))
    especs = area_reader.schema.field(
        default=Factory(dict),
        native=NativeField(20, native_circle_especs, suffix="E\n", when=lambda owner: owner.mob_type == "E"),
    )
    source_file = attr(default="", type=str)


@attributes
class CircleAffectData:
    NATIVE_PREFIX = "A\n"

    location = area_reader.schema.field(default=0, native=NativeField(1, native_number, suffix=" "))
    modifier = area_reader.schema.field(default=0, native=NativeField(2, native_number))


@attributes
class CircleItem(area_reader.model.Item):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    action_description = area_reader.schema.field(default="", native=NativeField(5, native_tilde_string))
    item_type = area_reader.schema.field(default=-1, type=int, native=NativeField(6, native_number, suffix=" "))
    extra_flags = area_reader.schema.field(default=0, type=int, native=NativeField(7, native_flag, suffix=" "))
    wear_flags = area_reader.schema.field(
        default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS, native=NativeField(8, native_flag)
    )
    value = area_reader.schema.field(default=Factory(list), type=list, native=NativeField(9, native_circle_numbers))
    weight = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number, suffix=" "))
    cost = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number, suffix=" "))
    rent = area_reader.schema.field(default=0, native=NativeField(12, native_number))
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(13, native_records, suffix=""),
    )
    affected = area_reader.schema.field(default=Factory(list), native=NativeField(14, native_records, suffix=""))
    level = attr(default=0, type=int)
    source_file = attr(default="", type=str)


@attributes
class CircleReset:
    command = area_reader.schema.field(default="", native=NativeField(1, native_circle_reset_command, suffix=" "))
    if_flag = area_reader.schema.field(default=0, native=NativeField(2, native_number, suffix=" "))
    arg1 = area_reader.schema.field(default=0, native=NativeField(3, native_number, suffix=" "))
    arg2 = area_reader.schema.field(
        default=0,
        native=NativeField(4, native_number, suffix=lambda owner: "\n" if owner.command in ("G", "R") else " "),
    )
    arg3 = area_reader.schema.field(
        default=None, native=NativeField(5, native_number, when=lambda owner: owner.command not in ("G", "R"))
    )


@attributes
class CircleZone:
    NATIVE_SUFFIX = "S\n"

    vnum = area_reader.schema.field(default=0, native=NativeField(1, native_number, prefix="#"))
    name = area_reader.schema.field(default="", native=NativeField(2, native_tilde_string))
    bot = area_reader.schema.field(default=0, native=NativeField(3, native_number, suffix=" "))
    top = area_reader.schema.field(default=0, native=NativeField(4, native_number, suffix=" "))
    lifespan = area_reader.schema.field(default=0, native=NativeField(5, native_number, suffix=" "))
    reset_mode = area_reader.schema.field(default=0, native=NativeField(6, native_number))
    resets = area_reader.schema.field(default=Factory(list), native=NativeField(7, native_records, suffix=""))
    source_file = attr(default="", type=str)


@attributes
class CircleShop:
    vnum = area_reader.schema.field(default=0, native=NativeField(1, native_number, prefix="#", suffix="~\n"))
    products = area_reader.schema.field(
        default=Factory(list), native=NativeField(2, native_circle_number_lines, suffix="-1\n")
    )
    profit_buy = area_reader.schema.field(default=0.0, native=NativeField(3, native_circle_float))
    profit_sell = area_reader.schema.field(default=0.0, native=NativeField(4, native_circle_float))
    buy_type = area_reader.schema.field(
        default=Factory(list), native=NativeField(5, native_circle_text_lines, suffix="-1\n")
    )
    messages = area_reader.schema.field(default=Factory(list), native=NativeField(6, native_circle_messages, suffix=""))
    temper = area_reader.schema.field(default=0, native=NativeField(7, native_number))
    bitvector = area_reader.schema.field(default=0, native=NativeField(8, native_number))
    keeper = area_reader.schema.field(default=0, native=NativeField(9, native_number))
    with_who = area_reader.schema.field(default=0, native=NativeField(10, native_number))
    rooms = area_reader.schema.field(
        default=Factory(list), native=NativeField(11, native_circle_number_lines, suffix="-1\n")
    )
    open_hour = area_reader.schema.field(default=0, native=NativeField(12, native_number))
    close_hour = area_reader.schema.field(default=0, native=NativeField(13, native_number))
    open_hour_2 = area_reader.schema.field(default=0, native=NativeField(14, native_number))
    close_hour_2 = area_reader.schema.field(default=0, native=NativeField(15, native_number))
    source_file = attr(default="", type=str)


@attributes
class CircleArea:
    NATIVE_COLLECTIONS = (
        ("zon", "zones", "$\n"),
        ("wld", "rooms", "$\n"),
        ("mob", "mobs", "$\n"),
        ("obj", "objects", "$\n"),
        ("shp", "shops", "$~\n"),
    )

    zones = attr(default=Factory(OrderedDict))
    rooms = attr(default=Factory(OrderedDict))
    mobs = attr(default=Factory(OrderedDict))
    objects = attr(default=Factory(OrderedDict))
    shops = attr(default=Factory(OrderedDict))
    indexes = attr(default=Factory(OrderedDict))
    shop_headers = attr(default=Factory(OrderedDict))
