"""Medievia multi-file world models, reader, and native writer."""

import os
from collections import OrderedDict

from attr import Factory, attr, attributes

import area_reader.dialects.circle
import area_reader.model
import area_reader.parser
import area_reader.schema
import area_reader.values
from area_reader.native import NativeField, NativeWriteError, render_record
from area_reader.native import number as native_number
from area_reader.native import records as native_records
from area_reader.native import tilde_string as native_tilde_string

MOBILE_DENIAL_TAGS = ("!KIC", "!BAC", "!TRI", "!BAS", "!CHA", "!DIS", "!THR", "!SOL")
MOBILE_THREE_ARGUMENT_RESETS = frozenset("MOEPDW")


def present(attribute):
    return lambda owner: getattr(owner, attribute) is not None


def _single_line(value, label):
    text = str(value)
    if "\n" in text or "\r" in text:
        raise NativeWriteError(f"{label} cannot contain a newline")
    return text


def native_ints(value, owner):
    del owner
    if not all(isinstance(item, int) for item in value):
        raise NativeWriteError(f"Expected integers, got {value!r}")
    return " ".join(str(item) for item in value)


def native_fixed_ints(size):
    def encode(value, owner):
        del owner
        if len(value) != size:
            raise NativeWriteError(f"Expected exactly {size} integers, got {len(value)}")
        return native_ints(value, None)

    return encode


def native_float(value, owner):
    del owner
    if not isinstance(value, (int, float)):
        raise NativeWriteError(f"Expected a number, got {value!r}")
    return str(float(value))


def native_dice(value, owner):
    del owner
    if not isinstance(value, area_reader.model.Dice):
        raise NativeWriteError(f"Expected Dice, got {value!r}")
    if value.bonus < 0:
        raise NativeWriteError("Medievia dice require a non-negative +bonus")
    return f"{value.number}d{value.sides}+{value.bonus}"


def native_number_or_dice(value, owner):
    if isinstance(value, area_reader.model.Dice):
        return native_dice(value, owner)
    return native_number(value, owner)


def native_medievia_armor(value, owner):
    del owner
    if not isinstance(value, int) or value % 10:
        raise NativeWriteError(f"Medievia armor class must be divisible by 10, got {value!r}")
    return str(value // 10)


def native_medievia_exit_lock(value, owner):
    del owner
    if value not in range(6):
        raise NativeWriteError(f"Unknown Medievia exit lock code {value!r}")
    return str(value)


def native_medievia_resets(value, owner):
    del owner
    return "".join(render_record(reset) for reset in value)


def native_medievia_reset_arg2_suffix(owner):
    return " " if owner.command in MOBILE_THREE_ARGUMENT_RESETS else ""


def native_medievia_reset_arg3_suffix(owner):
    return " " if owner.command == "W" else ""


def native_medievia_reset_comment(value, owner):
    del owner
    if not value:
        return ""
    return _single_line(value, "Reset comment")


def native_medievia_looks(value, owner):
    del owner
    return "".join(
        f"LOO {native_tilde_string(item.keyword, None)}\n{native_tilde_string(item.description, None)}\n"
        for item in value
    )


def native_medievia_affects(value, owner):
    del owner
    return "".join(f"AFF {item.location} {item.modifier}\n" for item in value)


def native_medievia_level(value, owner):
    del owner
    return "" if not value else f"AFF 8 {value}\n"


def native_medievia_denials(value, owner):
    del owner
    unknown = set(value).difference(MOBILE_DENIAL_TAGS)
    if unknown:
        raise NativeWriteError(f"Unknown mobile denial tags: {sorted(unknown)!r}")
    return " ".join(tag for tag in MOBILE_DENIAL_TAGS if tag in value)


def native_residual_tokens(value, owner):
    del owner
    return " ".join(_single_line(token, "Residual mobile token") for token in value)


def native_medievia_bool_tag(tag):
    def encode(value, owner):
        del owner
        if value is not True:
            raise NativeWriteError(f"{tag} must be true when emitted")
        return tag

    return encode


def native_shop_messages(value, owner):
    del owner
    if len(value) != 7:
        raise NativeWriteError(f"Medievia shops require exactly seven messages, got {len(value)}")
    return "\n".join(native_tilde_string(message, None) for message in value)


def native_room_mapping(value, owner):
    del owner
    return "".join(render_record(record) for record in value.values())


@attributes
class MedieviaExit:
    door = area_reader.schema.field(default=0, native=NativeField(1, native_number, prefix="D"))
    description = area_reader.schema.field(default="", native=NativeField(2, native_tilde_string))
    keyword = area_reader.schema.field(default="", native=NativeField(3, native_tilde_string))
    exit_message = area_reader.schema.field(default="", native=NativeField(4, native_tilde_string))
    entrance_message = area_reader.schema.field(default="", native=NativeField(5, native_tilde_string))
    lock = area_reader.schema.field(default=0, native=NativeField(6, native_medievia_exit_lock, suffix=" "))
    key = area_reader.schema.field(default=0, native=NativeField(7, native_number, suffix=" "))
    destination = area_reader.schema.field(default=0, native=NativeField(8, native_number))


@attributes
class MedieviaRoom(area_reader.model.MudBase):
    NATIVE_SUFFIX = "S\n"

    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    zone_number = area_reader.schema.field(default=0, native=NativeField(4, native_number, suffix=" "))
    room_flags = area_reader.schema.field(default=0, native=NativeField(5, native_number, suffix=" "))
    sector_type = area_reader.schema.field(default=0, native=NativeField(6, native_number, suffix=" "))
    extra_flags = area_reader.schema.field(default=0, native=NativeField(7, native_number))
    class_restriction = area_reader.schema.field(default=0, native=NativeField(8, native_number, suffix=" "))
    level_restriction = area_reader.schema.field(default=0, native=NativeField(9, native_number, suffix=" "))
    alignment_restriction = area_reader.schema.field(default=0, native=NativeField(10, native_number, suffix=" "))
    mount_restriction = area_reader.schema.field(default=0, native=NativeField(11, native_number))
    move_modifier = area_reader.schema.field(default=0, native=NativeField(12, native_number, suffix=" "))
    pressure_modifier = area_reader.schema.field(default=0, native=NativeField(13, native_number, suffix=" "))
    temperature_modifier = area_reader.schema.field(default=0, native=NativeField(14, native_number))
    exits = area_reader.schema.field(
        default=Factory(OrderedDict), native=NativeField(15, native_room_mapping, suffix="")
    )
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(16, native_records, suffix=""),
    )
    source_file = attr(default="", type=str)


@attributes
class MedieviaReset:
    command = area_reader.schema.field(default="", native=NativeField(1, lambda value, owner: str(value), suffix=" "))
    if_flag = area_reader.schema.field(default=0, native=NativeField(2, native_number, suffix=" "))
    arg1 = area_reader.schema.field(default=0, native=NativeField(3, native_number, suffix=" "))
    arg2 = area_reader.schema.field(
        default=0, native=NativeField(4, native_number, suffix=native_medievia_reset_arg2_suffix)
    )
    arg3 = area_reader.schema.field(
        default=None,
        native=NativeField(
            5, native_number, suffix=native_medievia_reset_arg3_suffix, when=lambda owner: owner.arg3 is not None
        ),
    )
    arg4 = area_reader.schema.field(
        default=None, native=NativeField(6, native_number, suffix="", when=lambda owner: owner.arg4 is not None)
    )
    comment = area_reader.schema.field(default="", native=NativeField(7, native_medievia_reset_comment, prefix=" "))


@attributes
class MedieviaZone:
    NATIVE_SUFFIX = "S\n"

    vnum = area_reader.schema.field(default=0, native=NativeField(1, native_number, prefix="#"))
    name = area_reader.schema.field(default="", native=NativeField(2, native_tilde_string))
    top = area_reader.schema.field(default=0, native=NativeField(3, native_number, suffix=" "))
    lifespan = area_reader.schema.field(default=0, native=NativeField(4, native_number, suffix=" "))
    reset_mode = area_reader.schema.field(default=0, native=NativeField(5, native_number, suffix=" "))
    social_restricted = area_reader.schema.field(default=0, native=NativeField(6, native_number))
    x = area_reader.schema.field(default=0, native=NativeField(7, native_number, suffix=" "))
    y = area_reader.schema.field(default=0, native=NativeField(8, native_number, suffix=" "))
    recall_room = area_reader.schema.field(default=0, native=NativeField(9, native_number))
    resets = area_reader.schema.field(default=Factory(list), native=NativeField(10, native_medievia_resets, suffix=""))
    source_file = attr(default="", type=str)


@attributes
class MedieviaMob(area_reader.model.MudBase):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", native=NativeField(2, native_tilde_string))
    short_desc = area_reader.schema.field(default="", native=NativeField(3, native_tilde_string))
    long_desc = area_reader.schema.field(default="", native=NativeField(4, native_tilde_string))
    description = area_reader.schema.field(default="", native=NativeField(5, native_tilde_string))
    act = area_reader.schema.field(
        default=None, native=NativeField(6, native_number_or_dice, prefix="ACT ", suffix=" ", when=present("act"))
    )
    affected_by = area_reader.schema.field(
        default=None,
        native=NativeField(7, native_number_or_dice, prefix="AFF ", suffix=" ", when=present("affected_by")),
    )
    alignment = area_reader.schema.field(
        default=None,
        native=NativeField(8, native_number_or_dice, prefix="ALI ", suffix=" ", when=present("alignment")),
    )
    character_class = area_reader.schema.field(
        default=None,
        native=NativeField(9, lambda value, owner: str(value), prefix="CLA ", when=present("character_class")),
    )
    level = area_reader.schema.field(
        default=None,
        native=NativeField(10, native_number_or_dice, prefix="LEV ", suffix=" ", when=present("level")),
    )
    hitroll = area_reader.schema.field(
        default=None,
        native=NativeField(11, native_number_or_dice, prefix="HRO ", suffix=" ", when=present("hitroll")),
    )
    ac = area_reader.schema.field(
        default=None, native=NativeField(12, native_medievia_armor, prefix="ARM ", suffix=" ", when=present("ac"))
    )
    hit = area_reader.schema.field(
        default=None,
        native=NativeField(13, native_number_or_dice, prefix="HIT ", suffix=" ", when=present("hit")),
    )
    damage = area_reader.schema.field(
        default=None, native=NativeField(14, native_dice, prefix="DAM ", when=present("damage"))
    )
    wealth = area_reader.schema.field(
        default=None,
        native=NativeField(15, native_number_or_dice, prefix="GOL ", suffix=" ", when=present("wealth")),
    )
    exp = area_reader.schema.field(
        default=None, native=NativeField(16, native_number_or_dice, prefix="EXP ", when=present("exp"))
    )
    start_pos = area_reader.schema.field(
        default=None,
        native=NativeField(17, native_number_or_dice, prefix="POS ", suffix=" ", when=present("start_pos")),
    )
    default_pos = area_reader.schema.field(
        default=None,
        native=NativeField(18, native_number_or_dice, prefix="DPOS ", suffix=" ", when=present("default_pos")),
    )
    sex = area_reader.schema.field(
        default=None, native=NativeField(19, native_number_or_dice, prefix="SEX ", when=present("sex"))
    )
    denied_actions = area_reader.schema.field(
        default=Factory(tuple),
        native=NativeField(20, native_medievia_denials, when=lambda owner: bool(owner.denied_actions)),
    )
    mount = area_reader.schema.field(
        default=False,
        native=NativeField(21, native_medievia_bool_tag("MOUNT"), prefix=" ", when=lambda owner: owner.mount),
    )
    fly = area_reader.schema.field(
        default=False, native=NativeField(22, native_medievia_bool_tag("FLY"), prefix=" ", when=lambda owner: owner.fly)
    )
    move = area_reader.schema.field(
        default=None,
        native=NativeField(23, native_number_or_dice, prefix=" MOV ", when=present("move")),
    )
    strength = area_reader.schema.field(
        default=None,
        native=NativeField(24, native_number_or_dice, prefix=" STR ", when=present("strength")),
    )
    intelligence = area_reader.schema.field(
        default=None,
        native=NativeField(25, native_number_or_dice, prefix=" INT ", when=present("intelligence")),
    )
    wisdom = area_reader.schema.field(
        default=None,
        native=NativeField(26, native_number_or_dice, prefix=" WIS ", when=present("wisdom")),
    )
    dexterity = area_reader.schema.field(
        default=None,
        native=NativeField(27, native_number_or_dice, prefix=" DEX ", when=present("dexterity")),
    )
    constitution = area_reader.schema.field(
        default=None,
        native=NativeField(28, native_number_or_dice, prefix=" CON ", when=present("constitution")),
    )
    stamina = area_reader.schema.field(
        default=None,
        native=NativeField(29, native_number_or_dice, prefix=" STA ", when=present("stamina")),
    )
    native_residual_tokens = area_reader.schema.field(
        default=Factory(tuple),
        native=NativeField(
            30, native_residual_tokens, prefix=" ", when=lambda owner: bool(owner.native_residual_tokens)
        ),
    )
    source_file = attr(default="medievia.mob", type=str)


@attributes
class MedieviaAffect:
    location = attr(default=0, type=int)
    modifier = attr(default=0, type=int)


@attributes
class MedieviaItem(area_reader.model.Item):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", native=NativeField(2, native_tilde_string))
    short_desc = area_reader.schema.field(default="", native=NativeField(3, native_tilde_string))
    description = area_reader.schema.field(default="", native=NativeField(4, native_tilde_string))
    action_description = area_reader.schema.field(default="", native=NativeField(5, native_tilde_string))
    item_type = area_reader.schema.field(default=0, native=NativeField(6, native_number, prefix="TYP ", suffix=" "))
    extra_flags = area_reader.schema.field(default=0, native=NativeField(7, native_number, prefix="EXT ", suffix=" "))
    wear_flags = area_reader.schema.field(default=0, native=NativeField(8, native_number, prefix="WEA "))
    value = area_reader.schema.field(
        default=Factory(lambda: [0, 0, 0, 0]), native=NativeField(9, native_ints, prefix="VAL ")
    )
    weight = area_reader.schema.field(default=0, native=NativeField(10, native_number, prefix="WGT ", suffix=" "))
    cost = area_reader.schema.field(default=0, native=NativeField(11, native_number, prefix="COS ", suffix=" "))
    cost_per_day = area_reader.schema.field(default=0, native=NativeField(12, native_number, prefix="CPD "))
    deterioration_days = area_reader.schema.field(
        default=None,
        native=NativeField(13, native_number, prefix="DET ", when=lambda owner: owner.deterioration_days is not None),
    )
    native_residual_tokens = area_reader.schema.field(
        default=Factory(tuple),
        native=NativeField(14, native_residual_tokens, when=lambda owner: bool(owner.native_residual_tokens)),
    )
    extra_descriptions = area_reader.schema.field(
        default=Factory(list), native=NativeField(15, native_medievia_looks, suffix="")
    )
    eq_level = area_reader.schema.field(default=0, native=NativeField(16, native_medievia_level, suffix=""))
    affected = area_reader.schema.field(
        default=Factory(list), native=NativeField(17, native_medievia_affects, suffix="")
    )
    source_file = attr(default="medievia.obj", type=str)


@attributes
class MedieviaShop:
    vnum = area_reader.schema.field(default=0, native=NativeField(1, native_number, prefix="#", suffix="~\n"))
    producing = area_reader.schema.field(default=Factory(lambda: [-1] * 6), native=NativeField(2, native_fixed_ints(6)))
    profit_buy = area_reader.schema.field(default=1.0, native=NativeField(3, native_float))
    profit_sell = area_reader.schema.field(default=1.0, native=NativeField(4, native_float))
    buy_types = area_reader.schema.field(default=Factory(lambda: [0] * 5), native=NativeField(5, native_fixed_ints(5)))
    messages = area_reader.schema.field(default=Factory(lambda: [""] * 7), native=NativeField(6, native_shop_messages))
    temper_1 = area_reader.schema.field(default=0, native=NativeField(7, native_number))
    temper_2 = area_reader.schema.field(default=0, native=NativeField(8, native_number))
    keeper = area_reader.schema.field(default=0, native=NativeField(9, native_number))
    with_who = area_reader.schema.field(default=0, native=NativeField(10, native_number))
    room = area_reader.schema.field(default=0, native=NativeField(11, native_number))
    open_1 = area_reader.schema.field(default=0, native=NativeField(12, native_number))
    close_1 = area_reader.schema.field(default=0, native=NativeField(13, native_number))
    open_2 = area_reader.schema.field(default=0, native=NativeField(14, native_number))
    close_2 = area_reader.schema.field(default=0, native=NativeField(15, native_number))
    source_file = attr(default="medievia.shp", type=str)


@attributes
class MedieviaArea:
    zones = attr(default=Factory(OrderedDict))
    rooms = attr(default=Factory(OrderedDict))
    mobs = attr(default=Factory(OrderedDict))
    objects = attr(default=Factory(OrderedDict))
    shops = attr(default=Factory(list))
    zone_terminal = attr(default=199, type=int)
    mobile_terminal = attr(default=19000, type=int)
    object_terminal = attr(default=19999, type=int)
    room_terminals = attr(default=Factory(OrderedDict))


class MedieviaAreaFile(area_reader.dialects.circle.CircleAreaFile):
    """Read and write the native Medievia world rooted at a game or lib directory."""

    NATIVE_NORMALIZATIONS = (
        "comments-and-whitespace",
        "line-endings",
        "mobile-tag-spelling-and-order",
        "object-tag-order",
        "duplicate-object-scalar-tags",
    )

    def __init__(self, root):
        self.root = os.fspath(root)
        self.lib_root = (
            self.root if os.path.isfile(os.path.join(self.root, "medievia.zon")) else os.path.join(self.root, "lib")
        )
        self.world_root = self.lib_root
        self.area = MedieviaArea()
        self.filename = ""
        self.data = ""
        self.index = 0

    def load_sections(self):
        self.load_zones()
        self.load_rooms()
        self.load_mobiles()
        self.load_objects()
        self.load_shops()

    def open_native_file(self, relative_path):
        path = os.path.join(self.lib_root, *relative_path.split("/"))
        self.open_circle_file(path)
        return path

    def read_token(self):
        self.skip_whitespace()
        start = self.index
        while self.current_char != "\0" and not self.current_char.isspace():
            self.index += 1
        if self.index == start:
            self.parse_fail("Expected a token")
        return self.data[start : self.index]

    def read_int(self):
        token = self.read_token()
        try:
            return int(token)
        except ValueError:
            self.parse_fail(f"Expected an integer, got {token!r}")

    def read_number_or_dice(self):
        token = self.read_token()
        if "d" in token.lower() and "+" in token:
            try:
                return self.parse_dice_token(token)
            except (TypeError, ValueError):
                self.parse_fail(f"Expected a Medievia number or dice token, got {token!r}")
        try:
            return int(token)
        except ValueError:
            self.parse_fail(f"Expected a Medievia number or dice token, got {token!r}")

    def load_zones(self):
        self.open_native_file("medievia.zon")
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                self.parse_fail("Medievia zone file ended without a $~ terminator")
            name = self.read_string()
            if name == "$":
                self.area.zone_terminal = vnum
                return
            header = self.read_int_list()
            coordinates = self.read_int_list()
            if len(header) != 4 or len(coordinates) != 3:
                self.parse_fail("Expected four zone header fields and three coordinate fields")
            zone = MedieviaZone(
                vnum=vnum,
                name=name,
                top=header[0],
                lifespan=header[1],
                reset_mode=header[2],
                social_restricted=header[3],
                x=coordinates[0],
                y=coordinates[1],
                recall_room=coordinates[2],
                source_file=name.replace(" ", "_"),
            )
            while True:
                line = self.read_line().strip()
                if not line:
                    if self.current_char == "\0":
                        self.parse_fail("Premature end of Medievia zone file")
                    continue
                if line.startswith("*"):
                    continue
                command = line[0]
                if command == "S":
                    break
                parts = line[1:].split()
                maximum = 5 if command == "W" else 4 if command in MOBILE_THREE_ARGUMENT_RESETS else 3
                numeric = []
                for part in parts[:maximum]:
                    try:
                        numeric.append(int(part))
                    except ValueError:
                        break
                if len(numeric) < 3:
                    self.parse_fail(f"Invalid {command!r} Medievia zone reset")
                zone.resets.append(
                    MedieviaReset(
                        command=command,
                        if_flag=numeric[0],
                        arg1=numeric[1],
                        arg2=numeric[2],
                        arg3=numeric[3] if len(numeric) >= 4 else None,
                        arg4=numeric[4] if len(numeric) == 5 else None,
                        comment=" ".join(parts[len(numeric) :]),
                    )
                )
            self.area.zones[vnum] = zone

    def load_rooms(self):
        seen_files = set()
        for zone in self.area.zones.values():
            if zone.source_file in seen_files:
                continue
            seen_files.add(zone.source_file)
            self.open_native_file(f"wld/{zone.source_file}")
            while True:
                vnum = self.read_record_header()
                if vnum is None:
                    self.parse_fail("Medievia room file ended without a $~ terminator")
                name = self.read_string()
                if name == "$":
                    self.area.room_terminals[zone.source_file] = vnum
                    break
                room = self.read_room(vnum)
                room.name = name
                room.source_file = zone.source_file
                if vnum in self.area.rooms:
                    self.parse_fail(f"Duplicate Medievia room vnum {vnum}")
                self.area.rooms[vnum] = room

    def read_room(self, vnum):
        description = self.read_string()
        header = self.read_int_list()
        restrictions = self.read_int_list()
        modifiers = self.read_int_list()
        if len(header) != 4 or len(restrictions) != 4 or len(modifiers) != 3:
            self.parse_fail("Invalid Medievia room numeric fields")
        room = MedieviaRoom(
            vnum=vnum,
            description=description,
            zone_number=header[0],
            room_flags=header[1],
            sector_type=header[2],
            extra_flags=header[3],
            class_restriction=restrictions[0],
            level_restriction=restrictions[1],
            alignment_restriction=restrictions[2],
            mount_restriction=restrictions[3],
            move_modifier=modifiers[0],
            pressure_modifier=modifiers[1],
            temperature_modifier=modifiers[2],
        )
        while True:
            metadata = self.read_token()
            if metadata == "S":
                return room
            if metadata == "E":
                room.extra_descriptions.append(
                    area_reader.model.ExtraDescription(keyword=self.read_string(), description=self.read_string())
                )
            elif metadata.startswith("D"):
                try:
                    door = int(metadata[1:])
                except ValueError:
                    self.parse_fail(f"Invalid Medievia exit tag {metadata!r}")
                exit_record = MedieviaExit(
                    door=door,
                    description=self.read_string(),
                    keyword=self.read_string(),
                    exit_message=self.read_string(),
                    entrance_message=self.read_string(),
                    lock=self.read_int(),
                    key=self.read_int(),
                    destination=self.read_int(),
                )
                if door in room.exits:
                    self.parse_fail(f"Duplicate Medievia exit direction {door}")
                room.exits[door] = exit_record
            else:
                self.parse_fail(f"Unknown Medievia room metadata {metadata!r}")

    def load_mobiles(self):
        self.open_native_file("medievia.mob")
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                self.parse_fail("Medievia mobile file ended without a $~ terminator")
            name = self.read_string()
            if name == "$":
                self.area.mobile_terminal = vnum
                return
            mob = self.read_mobile(vnum, name)
            self.area.mobs[vnum] = mob

    def read_mobile(self, vnum, name=None):
        values = {
            "vnum": vnum,
            "name": self.read_string() if name is None else name,
            "short_desc": self.read_string(),
            "long_desc": self.read_string(),
            "description": self.read_string(),
        }
        denied = []
        residual_tokens = []
        number_tags = {
            "ACT": "act",
            "AFF": "affected_by",
            "ALI": "alignment",
            "LEV": "level",
            "HRO": "hitroll",
            "HIT": "hit",
            "GOL": "wealth",
            "EXP": "exp",
            "POS": "start_pos",
            "DPO": "default_pos",
            "SEX": "sex",
            "MOV": "move",
            "STR": "strength",
            "INT": "intelligence",
            "WIS": "wisdom",
            "DEX": "dexterity",
            "CON": "constitution",
            "STA": "stamina",
        }
        while True:
            self.skip_whitespace()
            if self.current_char in ("#", "$", "\0"):
                values["denied_actions"] = tuple(tag for tag in MOBILE_DENIAL_TAGS if tag in denied)
                values["native_residual_tokens"] = tuple(residual_tokens)
                return MedieviaMob(**values)
            tag = self.read_token().upper()
            prefix = tag[:3]
            if prefix in number_tags:
                values[number_tags[prefix]] = self.read_number_or_dice()
            elif prefix == "CLA":
                character_class = self.read_token().upper()
                if len(character_class) != 1:
                    self.parse_fail(f"Invalid Medievia mobile class {character_class!r}")
                values["character_class"] = character_class
            elif prefix == "ARM":
                values["ac"] = self.read_int() * 10
            elif prefix == "DAM":
                damage = self.read_number_or_dice()
                if not isinstance(damage, area_reader.model.Dice):
                    self.parse_fail("Medievia mobile damage must use dice notation")
                values["damage"] = damage
            elif tag[:4] in MOBILE_DENIAL_TAGS:
                denied.append(tag[:4])
            elif prefix == "MOU":
                values["mount"] = True
            elif prefix == "FLY":
                values["fly"] = True
            else:
                # The native loader silently ignores unrecognized tokens. Keep
                # them as residual native payload so writing remains lossless.
                residual_tokens.append(tag)

    def load_objects(self):
        self.open_native_file("medievia.obj")
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                self.parse_fail("Medievia object file ended without a $~ terminator")
            name = self.read_string()
            if name == "$":
                self.area.object_terminal = vnum
                return
            self.area.objects[vnum] = self.read_item(vnum, name)

    def read_item(self, vnum, name=None):
        values = {
            "vnum": vnum,
            "name": self.read_string() if name is None else name,
            "short_desc": self.read_string(),
            "description": self.read_string(),
            "action_description": self.read_string(),
        }
        extra_descriptions = []
        affected = []
        residual_tokens = []
        while True:
            self.skip_whitespace()
            if self.current_char in ("#", "$", "\0"):
                values["extra_descriptions"] = extra_descriptions
                values["affected"] = affected
                values["native_residual_tokens"] = tuple(residual_tokens)
                return MedieviaItem(**values)
            token = self.read_token().upper()
            tag = token[:3]
            if tag == "TYP":
                values["item_type"] = self.read_int()
            elif tag == "EXT":
                values["extra_flags"] = self.read_int()
            elif tag == "WEA":
                values["wear_flags"] = self.read_int()
            elif tag == "VAL":
                value_tokens = self.read_line().split()
                if not 1 <= len(value_tokens) <= 4:
                    self.parse_fail(f"Expected one to four Medievia object values, got {len(value_tokens)}")
                try:
                    values["value"] = [int(token) for token in value_tokens]
                except ValueError:
                    self.parse_fail("Invalid Medievia object value line")
            elif tag == "WGT":
                values["weight"] = self.read_int()
            elif tag == "COS":
                values["cost"] = self.read_int()
            elif tag == "CPD":
                values["cost_per_day"] = self.read_int()
            elif tag == "DET":
                values["deterioration_days"] = self.read_int()
            elif tag == "LOO":
                extra_descriptions.append(
                    area_reader.model.ExtraDescription(keyword=self.read_string(), description=self.read_string())
                )
            elif tag == "AFF":
                location = self.read_int()
                modifier = self.read_int()
                if location == 8:
                    values["eq_level"] = modifier
                else:
                    affected.append(MedieviaAffect(location=location, modifier=modifier))
            else:
                # The C loader also ignores unknown object tokens. A few
                # historical records contain an entire legacy numeric header;
                # retain it as native residual payload instead of assigning it
                # semantics that the Medievia runtime does not.
                residual_tokens.append(token)

    def load_shops(self):
        self.open_native_file("medievia.shp")
        while True:
            header = self.read_string()
            if header == "$":
                return
            if not header.startswith("#"):
                self.parse_fail(f"Expected a Medievia shop header, got {header!r}")
            try:
                vnum = int(header[1:])
            except ValueError:
                self.parse_fail(f"Expected a numeric Medievia shop header, got {header!r}")
            self.area.shops.append(
                MedieviaShop(
                    vnum=vnum,
                    producing=[self.read_int() for _ in range(6)],
                    profit_buy=float(self.read_token()),
                    profit_sell=float(self.read_token()),
                    buy_types=[self.read_int() for _ in range(5)],
                    messages=[self.read_string() for _ in range(7)],
                    temper_1=self.read_int(),
                    temper_2=self.read_int(),
                    keeper=self.read_int(),
                    with_who=self.read_int(),
                    room=self.read_int(),
                    open_1=self.read_int(),
                    close_1=self.read_int(),
                    open_2=self.read_int(),
                    close_2=self.read_int(),
                )
            )

    def dumps(self):
        tree = OrderedDict()
        tree["medievia.zon"] = "".join(render_record(zone) for zone in self.area.zones.values())
        tree["medievia.zon"] += f"#{self.area.zone_terminal}\n$~\n"

        source_files = [zone.source_file for zone in self.area.zones.values()]
        if len(source_files) != len(set(source_files)):
            raise NativeWriteError("Medievia zone names do not map to unique world filenames")
        known_files = set(source_files)
        for room in self.area.rooms.values():
            if not room.source_file:
                raise NativeWriteError(f"MedieviaRoom {room.vnum!r} has no source_file")
            if room.source_file not in known_files:
                raise NativeWriteError(f"MedieviaRoom {room.vnum!r} uses unknown world file {room.source_file!r}")
        for source_file in source_files:
            terminal = self.area.room_terminals.get(source_file, 19999)
            body = "".join(render_record(room) for room in self.area.rooms.values() if room.source_file == source_file)
            tree[f"wld/{source_file}"] = body + f"#{terminal}\n$~\n"

        tree["medievia.mob"] = "".join(render_record(mob) for mob in self.area.mobs.values())
        tree["medievia.mob"] += f"#{self.area.mobile_terminal}\n$~\n"
        tree["medievia.obj"] = "".join(render_record(item) for item in self.area.objects.values())
        tree["medievia.obj"] += f"#{self.area.object_terminal}\n$~\n"
        tree["medievia.shp"] = "".join(render_record(shop) for shop in self.area.shops) + "$~\n"
        return tree

    def write(self, root):
        root = os.fspath(root)
        lib_root = root if os.path.basename(os.path.normpath(root)).lower() == "lib" else os.path.join(root, "lib")
        for relative_path, text in self.dumps().items():
            path = os.path.join(lib_root, *relative_path.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, mode="wt", encoding="latin-1", newline="\n") as medievia_file:
                medievia_file.write(text)
