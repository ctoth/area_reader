"""ROM area models, codecs, and reader."""

import logging
from collections import OrderedDict

from attr import Factory, attr, attributes

import area_reader.model
import area_reader.schema
import area_reader.values
from area_reader.constants import (
    AFFECTED_BY,
    FORMS,
    IMM_FLAGS,
    OFFENSE,
    PARTS,
    ROM_ACT_TYPES,
    WEAR_FLAGS,
    remove_bit,
)
from area_reader.native import NativeField, NativeSection, NativeWriteError
from area_reader.native import flag as native_flag
from area_reader.native import nested as native_nested
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string
from area_reader.native import word as native_word

logger = logging.getLogger("area_reader")


def multiply_10(number):
    return number * 10


def native_divide_by_ten(value, owner):
    del owner
    if value % 10:
        raise NativeWriteError(f"Armor class {value!r} is not divisible by ten")
    return str(value // 10)


def native_condition(value, owner):
    del owner
    conditions = {
        100: "P",
        90: "G",
        75: "A",
        50: "W",
        25: "D",
        10: "B",
        0: "R",
    }
    try:
        return conditions[value]
    except KeyError:
        raise NativeWriteError(f"ROM condition {value!r} has no native letter")


def native_item_values(value, owner):
    if len(value) != 5:
        raise NativeWriteError("ROM object values must contain five entries")
    word_positions = {
        "weapon": {0, 3},
        "drink": {2},
        "fountain": {2},
        "wand": {3},
        "staff": {3},
        "potion": {1, 2, 3, 4},
        "pill": {1, 2, 3, 4},
        "scroll": {1, 2, 3, 4},
    }.get(owner.item_type, set())
    encoded = []
    for index, item in enumerate(value):
        encoder = native_word if index in word_positions else native_flag
        encoded.append(encoder(item, owner))
    return " ".join(encoded)


def native_affect_prefix(owner):
    if owner.where == "TO_OBJECT":
        return "A\n"
    letters = {
        "TO_AFFECTS": "A",
        "TO_IMMUNE": "I",
        "TO_RESIST": "R",
        "TO_VULN": "V",
    }
    try:
        return f"F{letters[owner.where]} "
    except KeyError:
        raise NativeWriteError(f"ROM affect target {owner.where!r} has no native tag")


def native_affect_modifier_suffix(owner):
    return "\n" if owner.where == "TO_OBJECT" else " "


@attributes
class RomAffectData:
    where = attr(default=None)
    type = attr(default=None)
    level = attr(default=None)
    duration = attr(default=None)
    location = area_reader.schema.field(
        default=None, native=NativeField(1, native_number, prefix=native_affect_prefix, suffix=" ")
    )
    modifier = area_reader.schema.field(
        default=None, native=NativeField(2, native_number, suffix=native_affect_modifier_suffix)
    )
    bitvector = area_reader.schema.field(
        default=0,
        native=NativeField(
            3,
            native_flag,
            when=lambda owner: owner.where != "TO_OBJECT",
        ),
    )


@attributes
class RomItem(area_reader.model.Item):
    @staticmethod
    def convert_condition(letter):
        condition = -1
        conditions = {
            "P": 100,
            "G": 90,
            "A": 75,
            "W": 50,
            "D": 25,
            "B": 10,
            "R": 0,
        }
        condition = conditions[letter]
        return condition

    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    material = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    item_type = area_reader.schema.field(default=-1, type=int, native=NativeField(5, native_word))
    extra_flags = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_flag))
    wear_flags = area_reader.schema.field(
        default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS, native=NativeField(7, native_flag)
    )
    value = area_reader.schema.field(default=Factory(list), type=list, native=NativeField(8, native_item_values))
    level = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number))
    weight = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number))
    cost = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number))
    condition = area_reader.schema.field(
        default=100,
        type=int,
        original_type=area_reader.values.Letter,
        on_read=convert_condition,
        native=NativeField(12, native_condition),
    )
    affected = area_reader.schema.field(default=Factory(list), native=NativeField(13, native_records, suffix=""))
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(14, native_records, suffix=""),
    )

    @classmethod
    def read(cls, reader, vnum=None, **kwargs):
        logger.debug("Reading object %d", vnum)
        name = reader.read_string()
        short_desc = reader.read_string()
        description = reader.read_string()
        material = reader.read_string()
        item_type = reader.read_word()
        extra_flags = reader.read_flag()
        wear_flags = reader.read_flag()
        if item_type == "weapon":
            value = [
                reader.read_word(),
                reader.read_number(),
                reader.read_number(),
                reader.read_word(),
                reader.read_flag(),
            ]
        elif item_type == "container":
            value = [
                reader.read_number(),
                reader.read_flag(),
                reader.read_number(),
                reader.read_number(),
                reader.read_number(),
            ]
        elif item_type == "drink" or item_type == "fountain":
            value = [
                reader.read_number(),
                reader.read_number(),
                reader.read_word(),
                reader.read_number(),
                reader.read_number(),
            ]
        elif item_type == "wand" or item_type == "staff":
            value = [
                reader.read_number(),
                reader.read_number(),
                reader.read_number(),
                reader.read_word(),
                reader.read_number(),
            ]
        elif item_type in ("potion", "pill", "scroll"):
            value = [
                reader.read_number(),
                reader.read_word(),
                reader.read_word(),
                reader.read_word(),
                reader.read_word(),
            ]
        else:
            value = [
                reader.read_flag(),
                reader.read_flag(),
                reader.read_flag(),
                reader.read_flag(),
                reader.read_flag(),
            ]
        level = reader.read_number()
        weight = reader.read_number()
        cost = reader.read_number()
        condition = cls.convert_condition(reader.read_letter())
        affected = []
        extra_descriptions = []
        while True:
            letter = reader.read_letter()
            if letter == "A":
                af = RomAffectData()
                af.where = "TO_OBJECT"
                af.type = -1
                af.level = level
                af.duration = -1
                af.location = reader.read_number()
                af.modifier = reader.read_number()
                affected.append(af)
            elif letter == "F":
                af = RomAffectData()
                letter = reader.read_letter()
                if letter == "A":
                    af.where = "TO_AFFECTS"
                elif letter == "I":
                    af.where = "TO_IMMUNE"
                elif letter == "R":
                    af.where = "TO_RESIST"
                elif letter == "V":
                    af.where = "TO_VULN"
                else:
                    reader.parse_fail("Bad where on flag set")
                af.type = -1
                af.level = level
                af.duration = -1
                af.location = reader.read_number()
                af.modifier = reader.read_number()
                af.bitvector = reader.read_flag()
                affected.append(af)
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
            material=material,
            item_type=item_type,
            extra_flags=extra_flags,
            wear_flags=wear_flags,
            value=value,
            level=level,
            weight=weight,
            cost=cost,
            condition=condition,
            affected=affected,
            extra_descriptions=extra_descriptions,
        )


@attributes
class RomArmorClass:
    pierce = area_reader.schema.field(
        default=0, type=int, on_read=multiply_10, native=NativeField(1, native_divide_by_ten)
    )
    bash = area_reader.schema.field(
        default=0, type=int, on_read=multiply_10, native=NativeField(2, native_divide_by_ten)
    )
    slash = area_reader.schema.field(
        default=0, type=int, on_read=multiply_10, native=NativeField(3, native_divide_by_ten)
    )
    exotic = area_reader.schema.field(
        default=0, type=int, on_read=multiply_10, native=NativeField(4, native_divide_by_ten)
    )


@attributes
class RomMobprog:
    trig_type = area_reader.schema.field(
        default=None, type=area_reader.values.Word, native=NativeField(1, native_word, prefix="M ", suffix=" ")
    )
    vnum = area_reader.schema.field(
        default=-1, type=area_reader.values.VNum, native=NativeField(2, native_number, suffix=" ")
    )
    trig_phrase = area_reader.schema.field(default=None, type=str, native=NativeField(3, native_tilde_string))


@attributes
class RomCharacter(area_reader.model.MudBase):
    short_desc = area_reader.schema.field(default="", type=str)
    long_desc = attr(default="", type=str)
    level = area_reader.schema.field(default=0, type=int)
    race = attr(default="", type=str)
    group = attr(default=0, type=int)
    hitroll = attr(default=0, type=int)
    hit = attr(default=Factory(area_reader.model.Dice), type=area_reader.model.Dice)
    mana = attr(default=Factory(area_reader.model.Dice), type=area_reader.model.Dice)
    material = area_reader.schema.field(default="", type=str)
    damage = attr(default=Factory(area_reader.model.Dice), type=area_reader.model.Dice)
    damtype = attr(default="", type=area_reader.values.Word)
    ac = attr(default=Factory(RomArmorClass), type=RomArmorClass)
    act = attr(default=ROM_ACT_TYPES.IS_NPC.value, type=ROM_ACT_TYPES, converter=ROM_ACT_TYPES)
    affected_by = attr(default=0, type=AFFECTED_BY, converter=AFFECTED_BY)


@attributes
class RomMob(RomCharacter):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(0, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    long_desc = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    race = area_reader.schema.field(default="", type=str, native=NativeField(5, native_tilde_string))
    act = area_reader.schema.field(
        default=0, type=ROM_ACT_TYPES, converter=ROM_ACT_TYPES, native=NativeField(6, native_flag)
    )
    affected_by = area_reader.schema.field(
        default=0, type=AFFECTED_BY, converter=AFFECTED_BY, native=NativeField(7, native_flag)
    )
    alignment = area_reader.schema.field(default=0, type=int, native=NativeField(8, native_number))
    group = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number))
    level = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number))
    hitroll = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number))
    hit = area_reader.schema.field(
        default=Factory(area_reader.model.Dice), type=area_reader.model.Dice, native=NativeField(12, native_nested)
    )
    mana = area_reader.schema.field(
        default=Factory(area_reader.model.Dice), type=area_reader.model.Dice, native=NativeField(13, native_nested)
    )
    damage = area_reader.schema.field(
        default=Factory(area_reader.model.Dice), type=area_reader.model.Dice, native=NativeField(14, native_nested)
    )
    damtype = area_reader.schema.field(default="", type=area_reader.values.Word, native=NativeField(15, native_word))
    ac = area_reader.schema.field(
        default=Factory(RomArmorClass), type=RomArmorClass, native=NativeField(16, native_nested)
    )
    shop = area_reader.schema.field(default=None, read=False)
    off_flags = area_reader.schema.field(
        default=0, type=OFFENSE, converter=OFFENSE, native=NativeField(17, native_flag)
    )
    imm_flags = area_reader.schema.field(
        default=0, type=IMM_FLAGS, converter=IMM_FLAGS, native=NativeField(18, native_flag)
    )
    res_flags = area_reader.schema.field(
        default=0, type=IMM_FLAGS, converter=IMM_FLAGS, native=NativeField(19, native_flag)
    )
    vuln_flags = area_reader.schema.field(
        default=0, type=IMM_FLAGS, converter=IMM_FLAGS, native=NativeField(20, native_flag)
    )
    start_pos = area_reader.schema.field(
        default=None, type=area_reader.values.Word, native=NativeField(21, native_word)
    )
    default_pos = area_reader.schema.field(
        default=None, type=area_reader.values.Word, native=NativeField(22, native_word)
    )
    sex = area_reader.schema.field(default="", type=area_reader.values.Word, native=NativeField(23, native_word))
    wealth = area_reader.schema.field(default=0, type=int, native=NativeField(24, native_number))
    form = area_reader.schema.field(default=0, type=FORMS, converter=FORMS, native=NativeField(25, native_flag))
    parts = area_reader.schema.field(default=0, type=PARTS, converter=PARTS, native=NativeField(26, native_flag))
    size = area_reader.schema.field(default=None, type=area_reader.values.Word, native=NativeField(27, native_word))
    material = area_reader.schema.field(default="", type=str, native=NativeField(28, native_word))
    mprogs = area_reader.schema.field(
        default=Factory(list), type=list[RomMobprog] | None, native=NativeField(29, native_records)
    )

    @classmethod
    def read(cls, reader, vnum, **kwargs):
        logger.debug("Reading mob %d", vnum)
        name = reader.read_string()
        short_desc = reader.read_string()
        long_desc = reader.read_string()
        description = reader.read_string()
        race = reader.read_string()
        act = ROM_ACT_TYPES(reader.read_flag()) | ROM_ACT_TYPES.IS_NPC
        affected_by = reader.read_flag()
        alignment = reader.read_number()
        group = reader.read_number()
        level = reader.read_number()
        hitroll = reader.read_number()
        hit = area_reader.model.Dice.read(reader=reader)
        mana = area_reader.model.Dice.read(reader=reader)
        damage = area_reader.model.Dice.read(reader=reader)
        damtype = reader.read_word()
        ac = reader.read_object(RomArmorClass)
        off_flags = reader.read_flag()
        imm_flags = reader.read_flag()
        res_flags = reader.read_flag()
        vuln_flags = reader.read_flag()
        start_pos = reader.read_word()
        default_pos = reader.read_word()
        sex = reader.read_word()
        wealth = reader.read_number()
        form = reader.read_flag()
        parts = reader.read_flag()
        size = reader.read_word()
        material = reader.read_word()
        mprogs = []
        while True:
            letter = reader.read_letter()
            if letter == "F":
                word = reader.read_word()
                vector = reader.read_flag()
                if word.startswith("act"):
                    act = remove_bit(act, vector)
                elif word.startswith("aff"):
                    affected_by = remove_bit(affected_by, vector)
                elif word.startswith("off"):
                    off_flags = remove_bit(off_flags, vector)
                elif word.startswith("imm"):
                    imm_flags = remove_bit(imm_flags, vector)
                elif word.startswith("res"):
                    res_flags = remove_bit(res_flags, vector)
                elif word.startswith("vul"):
                    vuln_flags = remove_bit(vuln_flags, vector)
                elif word.startswith("for"):
                    form = remove_bit(form, vector)
                elif word.startswith("par"):
                    parts = remove_bit(parts, vector)
                else:
                    reader.parse_fail(f"Flag remove: flag not found: {word}")
            elif letter == "M":
                mprogs.append(reader.read_object_by_fields(RomMobprog))
            else:
                reader.index -= 1
                break
        return cls(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            long_desc=long_desc,
            description=description,
            race=race,
            act=act,
            affected_by=affected_by,
            alignment=alignment,
            group=group,
            level=level,
            hitroll=hitroll,
            hit=hit,
            mana=mana,
            damage=damage,
            damtype=damtype,
            ac=ac,
            off_flags=off_flags,
            imm_flags=imm_flags,
            res_flags=res_flags,
            vuln_flags=vuln_flags,
            start_pos=start_pos,
            default_pos=default_pos,
            sex=sex,
            wealth=wealth,
            form=form,
            parts=parts,
            size=size,
            material=material,
            mprogs=mprogs,
        )


@attributes
class RomArea:
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

    name = area_reader.schema.field(default="", native=NativeField(2, native_tilde_string, section="area"))
    metadata = area_reader.schema.field(default="", native=NativeField(3, native_tilde_string, section="area"))
    original_filename = area_reader.schema.field(default="", native=NativeField(1, native_tilde_string, section="area"))
    first_vnum = area_reader.schema.field(default=-1, native=NativeField(4, native_number, section="area"))
    last_vnum = area_reader.schema.field(default=-1, native=NativeField(5, native_number, section="area"))
    helps = attr(default=Factory(list), type=list[area_reader.model.Help])
    rooms = attr(default=Factory(OrderedDict), type=dict[int, area_reader.model.Room])
    mobs = attr(default=Factory(OrderedDict))
    objects = attr(default=Factory(OrderedDict))
    resets = attr(default=Factory(list), type=list[area_reader.model.Reset])
    specials = attr(default=Factory(list), type=list[area_reader.model.Special])
    shops = attr(default=Factory(list))
    mobprogs = attr(default=Factory(OrderedDict))
