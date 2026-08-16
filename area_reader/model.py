"""Shared semantic models for Diku-family area formats."""

import logging
import random

from attr import Factory, attr, attributes

from area_reader.constants import EXIT_DIRECTIONS, EXIT_FLAGS, ROM_ROOM_FLAGS, SECTOR_TYPES, WEAR_FLAGS
from area_reader.native import (
    NativeField,
    NativeWriteError,
)
from area_reader.native import (
    flag as native_flag,
)
from area_reader.native import (
    number as native_number,
)
from area_reader.native import (
    records as native_records,
)
from area_reader.native import (
    signed_number as native_signed_number,
)
from area_reader.native import (
    tilde_string as native_tilde_string,
)
from area_reader.native import (
    word as native_word,
)
from area_reader.schema import field
from area_reader.values import Letter, VNum, Word

logger = logging.getLogger("area_reader")


def native_reset_arg3_suffix(owner):
    return " " if owner.command in ("P", "M") else ""


def native_reset_arg2_suffix(owner):
    return "" if owner.command in ("G", "R") else " "


def native_reset_command_suffix(owner):
    return "" if owner.command is None else " "


def native_comment(value, owner):
    del owner
    if not value:
        return ""
    return str(value)


def native_reset_command(value, owner):
    del owner
    return "*" if value is None else str(value)


def native_exit_lock(value, owner):
    del owner
    locks = {
        int(EXIT_FLAGS.NONE): 0,
        int(EXIT_FLAGS.ISDOOR): 1,
        int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF): 2,
        int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.NOPASS): 3,
        int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.NOPASS | EXIT_FLAGS.PICKPROOF): 4,
    }
    try:
        return str(locks[int(value)])
    except KeyError:
        raise NativeWriteError(f"ROM exit flags {value!r} have no native lock code")


@attributes
class ExtraDescription:
    keyword = field(default="", type=str, native=NativeField(1, native_tilde_string, prefix="E\n"))
    description = field(default="", type=str, native=NativeField(2, native_tilde_string))


@attributes
class MudBase:
    vnum = field(default=0, type=VNum, read=False)
    name = field(default="", type=str)
    description = field(default="", type=str)
    extra_descriptions = attr(default=Factory(list), type=list[ExtraDescription])


@attributes
class Item(MudBase):
    short_desc = field(default="", type=str)
    item_type = field(default=-1, type=int)
    extra_flags = field(default=0, type=int)
    wear_flags = field(default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS)
    cost = field(default=0, type=int)
    level = field(default=0, type=int)
    weight = field(default=0, type=int)
    affected = attr(default=Factory(list))
    value = attr(default=Factory(list), type=list)


@attributes
class Dice:
    number = field(default=0, type=int, native=NativeField(1, native_number, suffix=""))
    sides = field(default=0, type=int, native=NativeField(2, native_number, prefix="d", suffix=""))
    bonus = field(default=0, type=int, native=NativeField(3, native_signed_number))

    @classmethod
    def read(cls, reader, **kwargs):
        number = reader.read_number()
        reader.read_letter()  # D
        sides = reader.read_number()
        bonus = reader.read_number()
        return cls(number=number, sides=sides, bonus=bonus, **kwargs)

    def roll(self):
        if self.sides == 0:
            return self.bonus
        score = 0
        sides = max(self.sides, 1)
        for _roll in range(self.number):
            score += random.randrange(1, sides + 1)
        score += self.bonus
        return score


@attributes
class Help:
    level = field(default=0, type=int, native=NativeField(1, native_number, suffix=" "))
    keyword = field(default="", type=Word, native=NativeField(2, native_tilde_string))
    text = field(default="", type=str, native=NativeField(3, native_tilde_string))


@attributes
class Exit:
    keyword = field(default="", type=Word, native=NativeField(3, native_tilde_string))
    description = field(default="", type=str, native=NativeField(2, native_tilde_string))
    door = field(
        default=None,
        type=EXIT_DIRECTIONS | None,
        converter=lambda value: None if value is None else EXIT_DIRECTIONS(value),
        native=NativeField(1, native_number, prefix="D"),
    )
    exit_info = field(default=0, type=EXIT_FLAGS, converter=EXIT_FLAGS, native=NativeField(4, native_exit_lock))
    rs_flags = attr(default=0, type=int)
    key = field(default=0, type=int, native=NativeField(5, native_number))
    destination = field(default=None, type=int, native=NativeField(6, native_number))

    @classmethod
    def read(cls, reader, **kwargs):
        logger.debug("Reading exit")
        door = reader.read_number()
        description = reader.read_string()
        keyword = reader.read_string()
        locks = reader.read_number()
        key = reader.read_number()
        destination = reader.read_number()
        exit_info = EXIT_FLAGS.NONE
        if locks == 1:
            exit_info = EXIT_FLAGS.ISDOOR
        elif locks == 2:
            exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF
        elif locks == 3:
            exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.NOPASS
        elif locks == 4:
            exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.NOPASS | EXIT_FLAGS.PICKPROOF
        return cls(
            door=door,
            description=description,
            keyword=keyword,
            exit_info=exit_info,
            key=key,
            destination=destination,
        )


@attributes
class Special:
    command = field(default=None, native=NativeField(1, native_reset_command, suffix=native_reset_command_suffix))
    arg1 = field(
        default=None,
        native=NativeField(2, native_number, suffix=" ", when=lambda owner: owner.command is not None),
    )
    arg2 = field(
        default=None,
        native=NativeField(3, native_word, suffix="", when=lambda owner: owner.command is not None),
    )
    comment = field(default=None, type=str, native=NativeField(4, native_comment))

    @classmethod
    def read(cls, reader, letter, **kwargs):
        command = letter
        arg1 = reader.read_number()
        arg2 = reader.read_word()
        comment = reader.read_to_eol()
        return cls(command=command, arg1=arg1, arg2=arg2, comment=comment)


@attributes
class Reset:
    command = field(default=None, native=NativeField(1, native_reset_command, suffix=native_reset_command_suffix))
    if_flag = field(
        default=0,
        native=NativeField(2, native_number, suffix=" ", when=lambda owner: owner.command is not None),
    )
    arg1 = field(
        default=None,
        type=Letter,
        native=NativeField(3, native_number, suffix=" ", when=lambda owner: owner.command is not None),
    )
    arg2 = field(
        default=None,
        native=NativeField(4, native_number, suffix=native_reset_arg2_suffix, when=lambda owner: owner.command is not None),
    )
    arg3 = field(
        default=None,
        native=NativeField(
            5,
            native_number,
            suffix=native_reset_arg3_suffix,
            when=lambda owner: owner.command not in (None, "G", "R"),
        ),
    )
    arg4 = field(
        default=None,
        native=NativeField(6, native_number, suffix="", when=lambda owner: owner.command in ("P", "M")),
    )
    comment = field(default=None, type=str, native=NativeField(7, native_comment))

    @classmethod
    def read(cls, reader, letter):
        command = letter
        if_flag = reader.read_number()
        arg1 = reader.read_number()
        arg2 = reader.read_number()
        arg3 = 0 if letter in ("G", "R") else reader.read_number()
        arg4 = reader.read_number() if letter in ("P", "M") else 0
        comment = reader.read_to_eol()
        return cls(
            command=command,
            if_flag=if_flag,
            arg1=arg1,
            arg2=arg2,
            arg3=arg3,
            arg4=arg4,
            comment=comment,
        )


@attributes
class Room(MudBase):
    NATIVE_SUFFIX = "S\n"

    vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix="#"))
    name = field(default="", type=str, native=NativeField(1, native_tilde_string))
    description = field(default="", type=str, native=NativeField(2, native_tilde_string))
    owner = field(
        default=None,
        type=str,
        native=NativeField(10, native_tilde_string, prefix="O ", when=lambda owner: bool(owner.owner)),
    )
    clan = field(
        default="",
        type=str,
        native=NativeField(7, native_tilde_string, prefix="C ", when=lambda owner: bool(owner.clan)),
    )
    area = attr(default=None)
    area_number = field(default=0, type=int, native=NativeField(3, native_number))
    room_flags = field(default=0, type=ROM_ROOM_FLAGS, converter=ROM_ROOM_FLAGS, native=NativeField(4, native_flag))
    sector_type = field(default=0, type=SECTOR_TYPES, converter=SECTOR_TYPES, native=NativeField(5, native_number))
    heal_rate = field(
        default=100,
        type=int,
        native=NativeField(6, native_number, prefix="H ", when=lambda owner: owner.heal_rate != 100),
    )
    mana_rate = field(
        default=100,
        type=int,
        native=NativeField(7, native_number, prefix="M ", when=lambda owner: owner.mana_rate != 100),
    )
    exits = field(default=Factory(list), type=list[Exit], native=NativeField(8, native_records, suffix=""))
    extra_descriptions = field(
        default=Factory(list),
        type=list[ExtraDescription],
        native=NativeField(9, native_records, suffix=""),
    )

    @classmethod
    def read(cls, reader, vnum):
        logger.debug("Reading room with vnum %d", vnum)
        name = reader.read_string()
        description = reader.read_string()
        area_number = reader.read_number()
        room_flags = reader.read_flag()
        sector_type = reader.read_number()
        if sector_type == -1:
            sector_type = 0
        room = cls(
            vnum=vnum,
            name=name,
            description=description,
            area_number=area_number,
            room_flags=room_flags,
            sector_type=sector_type,
        )
        room.read_metadata(reader)
        return room

    def read_metadata(self, reader):
        while True:
            letter = reader.read_letter()
            if letter == "S":
                break
            if letter == "H":
                self.heal_rate = reader.read_number()
            elif letter == "M":
                self.mana_rate = reader.read_number()
            elif letter == "C":
                self.clan = reader.read_string()
            elif letter == "D":
                self.exits.append(Exit.read(reader=reader))
            elif letter == "E":
                self.extra_descriptions.append(reader.read_object(ExtraDescription))
            elif letter == "O":
                self.owner = reader.read_string()
            else:
                reader.parse_fail(f"Don't know how to process room attribute: {letter}")
