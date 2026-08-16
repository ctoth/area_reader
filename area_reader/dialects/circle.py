"""CircleMUD area models, codecs, and reader."""

import enum
import json
import os
from collections import OrderedDict

from attr import Factory, attr, attributes

import area_reader.dialects.rom
import area_reader.model
import area_reader.parser
import area_reader.schema
import area_reader.serialization
import area_reader.values
from area_reader.constants import EXIT_FLAGS, WEAR_FLAGS
from area_reader.native import NativeField, NativeWriteError, render_record
from area_reader.native import flag as native_flag
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string


class CircleAreaFile:
    NATIVE_NORMALIZATIONS = (
        "comments",
        "whitespace-and-line-endings",
        "numeric-versus-alphabetic-flags",
        "room-and-object-metadata-order",
        "optional-second-shop-window",
        "dice-zero-bonus-spelling",
    )

    def __init__(self, root):
        self.root = os.fspath(root)
        self.world_root = self.root
        if not os.path.exists(os.path.join(self.world_root, "zon", "index")):
            self.world_root = os.path.join(self.root, "lib", "world")
        self.area = CircleArea()
        self.filename = ""
        self.data = ""
        self.index = 0

    def dumps(self):
        tree = OrderedDict()
        for family, collection_name, file_end in self.area.NATIVE_COLLECTIONS:
            names = self.area.indexes.get(family, [])
            tree[f"{family}/index"] = "".join(f"{name}\n" for name in names) + "$\n"
            records = getattr(self.area, collection_name).values()
            for record in records:
                if not record.source_file:
                    raise NativeWriteError(f"{record.__class__.__name__} {record.vnum!r} has no indexed source file")
                if record.source_file not in names:
                    raise NativeWriteError(f"{record.source_file} is not present in the {family} index")
            for name in names:
                prefix = ""
                if family == "shp":
                    try:
                        prefix = native_tilde_string(self.area.shop_headers[name], None) + "\n"
                    except KeyError:
                        raise NativeWriteError(f"Shop file {name} has no version header")
                body = "".join(render_record(record) for record in records if record.source_file == name)
                tree[f"{family}/{name}"] = prefix + body + file_end
        return tree

    def write(self, root):
        root = os.fspath(root)
        world_root = root if os.path.basename(root) == "world" else os.path.join(root, "lib", "world")
        for relative_path, text in self.dumps().items():
            path = os.path.join(world_root, *relative_path.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, mode="wt", encoding="latin-1", newline="\n") as circle_file:
                circle_file.write(text)

    def load_sections(self):
        self.load_zones()
        self.load_rooms()
        self.load_mobiles()
        self.load_objects()
        self.load_shops()

    def load_zones(self):
        for path in self.indexed_paths("zon"):
            self.load_zone_file(path)

    def load_rooms(self):
        for path in self.indexed_paths("wld"):
            self.load_room_file(path)

    def load_mobiles(self):
        for path in self.indexed_paths("mob"):
            self.load_mobile_file(path)

    def load_objects(self):
        for path in self.indexed_paths("obj"):
            self.load_object_file(path)

    def load_shops(self):
        for path in self.indexed_paths("shp"):
            self.load_shop_file(path)

    def indexed_paths(self, family):
        index_path = os.path.join(self.world_root, family, "index")
        if not os.path.exists(index_path):
            self.area.indexes[family] = []
            return []
        base = os.path.dirname(index_path)
        with open(index_path, mode="rt", encoding="latin-1") as index_file:
            names = [line.strip() for line in index_file]
        names = [name for name in names if name and name != "$"]
        self.area.indexes[family] = names
        return [os.path.join(base, name) for name in names]

    def open_circle_file(self, filename):
        self.filename = filename
        with open(filename, mode="rt", encoding="latin-1") as circle_file:
            self.data = circle_file.read()
        self.index = 0

    @property
    def current_char(self):
        if self.index >= len(self.data):
            return "\0"
        return self.data[self.index]

    def skip_whitespace(self):
        while self.index < len(self.data) and self.current_char.isspace():
            self.index += 1

    def read_line(self):
        while self.current_char in ("\r", "\n"):
            self.index += 1
        if self.index >= len(self.data):
            return ""
        end = self.data.find("\n", self.index)
        if end == -1:
            line = self.data[self.index :]
            self.index = len(self.data)
        else:
            line = self.data[self.index : end]
            self.index = end + 1
        return line.rstrip("\r")

    def read_string(self):
        self.skip_whitespace()
        end = self.data.find("~", self.index)
        if end == -1:
            self.parse_fail("Unterminated string")
        result = self.data[self.index : end]
        self.index = end + 1
        return result

    def read_record_header(self):
        self.skip_whitespace()
        if self.current_char == "$":
            return None
        if self.current_char != "#":
            self.parse_fail("Expected record header")
        self.index += 1
        token = ""
        while self.current_char not in ("\0", "\n", "\r", "~") and not self.current_char.isspace():
            token += self.current_char
            self.index += 1
        if self.current_char == "~":
            self.index += 1
        try:
            return int(token)
        except ValueError:
            self.parse_fail(f"Expected numeric record header, got {token!r}")

    def read_int_list(self):
        line = self.read_line().strip()
        if not line:
            return []
        return [int(value) for value in line.split()]

    def read_tilde_or_line(self):
        self.skip_whitespace()
        if (
            "~"
            in self.data[
                self.index : self.data.find("\n", self.index)
                if self.data.find("\n", self.index) != -1
                else len(self.data)
            ]
        ):
            return self.read_string()
        return self.read_line().strip()

    def parse_fail(self, message):
        backwards = self.data[: self.index]
        lineno = backwards.count("\n") + 1
        col = backwards[::-1].find("\n")
        raise area_reader.parser.ParseError(f"{self.filename} line {lineno} col {col}: {message}")

    def parse_dice_token(self, token):
        number, rest = token.lower().split("d", 1)
        if "+" in rest:
            sides, bonus = rest.split("+", 1)
            bonus = int(bonus)
        elif "-" in rest:
            sides, bonus = rest.split("-", 1)
            bonus = -int(bonus)
        else:
            sides = rest
            bonus = 0
        return area_reader.model.Dice(number=int(number), sides=int(sides), bonus=bonus)

    def load_zone_file(self, path):
        self.open_circle_file(path)
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            name = self.read_string()
            bot, top, lifespan, reset_mode = self.read_int_list()
            zone = CircleZone(
                vnum=vnum,
                name=name,
                bot=bot,
                top=top,
                lifespan=lifespan,
                reset_mode=reset_mode,
                source_file=os.path.basename(path),
            )
            while True:
                line = self.read_line().strip()
                if not line and self.current_char == "\0":
                    self.parse_fail("premature end of file")
                if not line or line.startswith("*"):
                    continue
                command = line[0]
                if command in ("S", "$"):
                    break
                parts = line[1:].split()
                if command in ("M", "O", "E", "P", "D"):
                    if_flag, arg1, arg2, arg3 = [int(part) for part in parts[:4]]
                else:
                    if_flag, arg1, arg2 = [int(part) for part in parts[:3]]
                    arg3 = None
                zone.resets.append(CircleReset(command=command, if_flag=if_flag, arg1=arg1, arg2=arg2, arg3=arg3))
            self.area.zones[vnum] = zone

    def load_room_file(self, path):
        self.open_circle_file(path)
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            room = self.read_room(vnum)
            room.source_file = os.path.basename(path)
            self.area.rooms[vnum] = room

    def read_room(self, vnum):
        name = self.read_string()
        description = self.read_string()
        zone_number, flags, sector_type = self.read_line().split()
        room = CircleRoom(
            vnum=vnum,
            name=name,
            description=description,
            zone_number=int(zone_number),
            room_flags=circle_asciiflag_conv(flags),
            sector_type=int(sector_type),
        )
        while True:
            line = self.read_line().strip()
            if line == "S":
                return room
            if line.startswith("D"):
                exit = self.read_exit(int(line[1:]))
                room.exits[exit.door] = exit
            elif line == "E":
                room.extra_descriptions.append(
                    area_reader.model.ExtraDescription(keyword=self.read_string(), description=self.read_string())
                )
            else:
                self.parse_fail(f"Unknown room metadata {line!r}")

    def read_exit(self, door):
        description = self.read_string()
        keyword = self.read_string()
        locks, key, destination = self.read_int_list()
        if locks == 1:
            exit_info = EXIT_FLAGS.ISDOOR
        elif locks == 2:
            exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF
        else:
            exit_info = EXIT_FLAGS.NONE
        return CircleExit(
            door=door, description=description, keyword=keyword, exit_info=exit_info, key=key, destination=destination
        )

    def load_mobile_file(self, path):
        self.open_circle_file(path)
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            mob = self.read_mobile(vnum)
            mob.source_file = os.path.basename(path)
            self.area.mobs[vnum] = mob

    def read_mobile(self, vnum):
        name = self.read_string()
        short_desc = self.read_string()
        long_desc = self.read_string()
        description = self.read_string()
        act_flags, affected_flags, alignment, mob_type = self.read_line().split()
        act = circle_asciiflag_conv(act_flags) | CircleMobFlags.ISNPC
        affected_by = circle_asciiflag_conv(affected_flags)
        level, source_hitroll, source_ac, hit_token, damage_token = self.read_line().split()
        wealth, exp = self.read_int_list()
        start_pos, default_pos, sex = self.read_int_list()
        especs = {}
        if mob_type.upper() == "E":
            while True:
                line = self.read_line().strip()
                if line == "E":
                    break
                if ":" in line:
                    key, value = line.split(":", 1)
                    especs[key.strip()] = value.strip()
        return CircleMob(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            long_desc=long_desc,
            description=description,
            act=act,
            affected_by=affected_by,
            alignment=int(alignment),
            mob_type=mob_type.upper(),
            level=int(level),
            hitroll=20 - int(source_hitroll),
            ac=int(source_ac) * 10,
            hit=self.parse_dice_token(hit_token),
            damage=self.parse_dice_token(damage_token),
            wealth=wealth,
            exp=exp,
            default_pos=default_pos,
            start_pos=start_pos,
            sex=sex,
            especs=especs,
        )

    def load_object_file(self, path):
        self.open_circle_file(path)
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            item = self.read_item(vnum)
            item.source_file = os.path.basename(path)
            self.area.objects[vnum] = item

    def read_item(self, vnum):
        name = self.read_string()
        short_desc = self.read_string()
        description = self.read_string()
        action_description = self.read_string()
        item_type, extra_flags, wear_flags = self.read_line().split()
        value = self.read_int_list()
        weight, cost, rent = self.read_int_list()
        affected = []
        extra_descriptions = []
        while True:
            self.skip_whitespace()
            if self.current_char in ("#", "$", "\0"):
                break
            line = self.read_line().strip()
            if line == "E":
                extra_descriptions.append(
                    area_reader.model.ExtraDescription(keyword=self.read_string(), description=self.read_string())
                )
            elif line == "A":
                location, modifier = self.read_int_list()
                affected.append(CircleAffectData(location=location, modifier=modifier))
            else:
                self.parse_fail(f"Unknown object metadata {line!r}")
        return CircleItem(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            description=description,
            action_description=action_description,
            item_type=int(item_type),
            extra_flags=circle_asciiflag_conv(extra_flags),
            wear_flags=circle_asciiflag_conv(wear_flags),
            value=value,
            weight=weight,
            cost=cost,
            rent=rent,
            affected=affected,
            extra_descriptions=extra_descriptions,
        )

    def load_shop_file(self, path):
        self.open_circle_file(path)
        header = self.read_string()
        self.area.shop_headers[os.path.basename(path)] = header
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            shop = self.read_shop(vnum, header)
            shop.source_file = os.path.basename(path)
            self.area.shops[vnum] = shop

    def read_number_list_until_minus_one(self):
        values = []
        while True:
            value = int(self.read_line().strip())
            if value == -1:
                return values
            values.append(value)

    def read_word_list_until_minus_one(self):
        values = []
        while True:
            value = self.read_line().strip()
            if value == "-1":
                return values
            values.append(value)

    def read_shop(self, vnum, header):
        products = self.read_number_list_until_minus_one()
        profit_buy = float(self.read_line().strip())
        profit_sell = float(self.read_line().strip())
        buy_type = self.read_word_list_until_minus_one()
        messages = [self.read_string() for _ in range(7)]
        temper = int(self.read_line().strip())
        bitvector = int(self.read_line().strip())
        keeper = int(self.read_line().strip())
        with_who = int(self.read_line().strip())
        rooms = self.read_number_list_until_minus_one()
        open_hour = int(self.read_line().strip())
        close_hour = int(self.read_line().strip())
        open_hour_2 = 0
        close_hour_2 = 0
        while self.current_char in ("\r", "\n"):
            self.index += 1
        if self.current_char not in ("#", "$", "\0"):
            open_hour_2 = int(self.read_line().strip())
            close_hour_2 = int(self.read_line().strip())
        return CircleShop(
            vnum=vnum,
            products=products,
            profit_buy=profit_buy,
            profit_sell=profit_sell,
            buy_type=buy_type,
            messages=messages,
            temper=temper,
            bitvector=bitvector,
            keeper=keeper,
            with_who=with_who,
            rooms=rooms,
            open_hour=open_hour,
            close_hour=close_hour,
            open_hour_2=open_hour_2,
            close_hour_2=close_hour_2,
        )

    def as_dict(self):
        return area_reader.serialization.EnumNameConverter().unstructure(self.area)

    def as_json(self, indent=None):
        return json.dumps(self.as_dict(), indent=indent)


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
    start_pos = area_reader.schema.field(default=0, native=NativeField(17, native_number, suffix=" "))
    default_pos = area_reader.schema.field(default=0, native=NativeField(18, native_number, suffix=" "))
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
