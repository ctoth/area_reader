"""tbaMUD area models, codecs, reader, and native writer."""

import os
from collections import OrderedDict

from attr import Factory, attr, attributes

import area_reader.dialects.circle
import area_reader.model
import area_reader.schema
import area_reader.values
from area_reader.constants import EXIT_FLAGS
from area_reader.native import NativeField, NativeWriteError
from area_reader.native import number as native_number
from area_reader.native import records as native_records


def combine_flag_banks(banks):
    return sum(bank << (32 * index) for index, bank in enumerate(banks))


def native_tilde_string(value, owner):
    del owner
    text = str(value)
    if any(line.rstrip("\r").endswith("~") for line in text.splitlines()):
        raise NativeWriteError("tbaMUD strings cannot contain a line-ending '~'")
    return text + "~"


def native_tba_flag_banks(value, owner):
    del owner
    if not isinstance(value, (list, tuple)) or len(value) != 4 or not all(isinstance(bank, int) for bank in value):
        raise NativeWriteError("tbaMUD flag banks require exactly four integers")
    return " ".join(str(bank) for bank in value)


def native_tba_zone_header(value, owner):
    del value
    base = f"{owner.bot} {owner.top} {owner.lifespan} {owner.reset_mode}"
    if owner.zone_flags == (0, 0, 0, 0) and owner.min_level == -1 and owner.max_level == -1:
        return base
    return f"{base} {native_tba_flag_banks(owner.zone_flags, owner)} {owner.min_level} {owner.max_level}"


def native_tba_reset(value, owner):
    del value
    if owner.command == "V":
        if owner.arg3 is None or not owner.sarg1 or owner.sarg2 is None:
            raise NativeWriteError("V resets require arg3, sarg1, and sarg2")
        return f"V {owner.if_flag} {owner.arg1} {owner.arg2} {owner.arg3} {owner.sarg1} {owner.sarg2}"
    if owner.command not in "MOPGERDTR":
        raise NativeWriteError(f"unsupported tbaMUD reset command {owner.command!r}")
    arg3 = -1 if owner.arg3 is None else owner.arg3
    return f"{owner.command} {owner.if_flag} {owner.arg1} {owner.arg2} {arg3}"


def native_tba_trigger_assignments(value, owner):
    del owner
    if not isinstance(value, (list, tuple)) or not all(isinstance(vnum, int) for vnum in value):
        raise NativeWriteError("trigger assignments require integer vnums")
    return "".join(f"T {vnum}\n" for vnum in value)


def native_tba_room_suffix(owner):
    return "S\n" + native_tba_trigger_assignments(owner.triggers, owner)


def native_tba_mobile_type(value, owner):
    if value not in ("S", "E"):
        raise NativeWriteError("tbaMUD mobile type must be 'S' or 'E'")
    if value == "S" and owner.especs:
        raise NativeWriteError("simple tbaMUD mobiles cannot contain especs")
    return value


def native_tba_mobile_especs(value, owner):
    del owner
    lines = []
    for key, item in value.items():
        if any(char in str(key) for char in ":\r\n") or any(char in str(item) for char in "\r\n"):
            raise NativeWriteError("invalid tbaMUD enhanced-mobile espec")
        lines.append(f"{key}: {item}\n")
    return "".join(lines)


def native_tba_mobile_suffix(owner):
    return native_tba_trigger_assignments(owner.triggers, owner)


def native_tba_dice(value, owner):
    del owner
    if not isinstance(value, area_reader.model.Dice):
        raise NativeWriteError("expected tbaMUD dice")
    return f"{value.number}d{value.sides}{value.bonus:+d}"


def native_tba_hitroll(value, owner):
    del owner
    if not isinstance(value, int):
        raise NativeWriteError("expected an integer hitroll")
    return str(20 - value)


def native_tba_armor_class(value, owner):
    del owner
    if not isinstance(value, int) or value % 10:
        raise NativeWriteError("tbaMUD armor class must be an integer divisible by ten")
    return str(value // 10)


def native_tba_numbers(value, owner):
    del owner
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, int) for item in value):
        raise NativeWriteError("expected a sequence of integers")
    return " ".join(str(item) for item in value)


def native_tba_exit_lock(value, owner):
    del value
    flags = int(owner.exit_info)
    known = int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF)
    if flags & ~known:
        raise NativeWriteError(f"exit flags {owner.exit_info!r} have no tbaMUD lock code")
    if not flags & int(EXIT_FLAGS.ISDOOR):
        if owner.hidden or flags:
            raise NativeWriteError("a hidden or flagged tbaMUD exit must be a door")
        return "0"
    code = 2 if flags & int(EXIT_FLAGS.PICKPROOF) else 1
    if owner.hidden:
        code += 2
    return str(code)


@attributes
class TbaExit:
    door = area_reader.schema.field(default=0, native=NativeField(1, native_number, prefix="D"))
    description = area_reader.schema.field(default="", native=NativeField(2, native_tilde_string))
    keyword = area_reader.schema.field(default="", native=NativeField(3, native_tilde_string))
    exit_info = area_reader.schema.field(
        default=EXIT_FLAGS.NONE,
        type=EXIT_FLAGS,
        converter=EXIT_FLAGS,
        native=NativeField(4, native_tba_exit_lock, suffix=" "),
    )
    hidden = attr(default=False, type=bool)
    key = area_reader.schema.field(default=-1, native=NativeField(5, native_number, suffix=" "))
    destination = area_reader.schema.field(default=-1, native=NativeField(6, native_number))


@attributes
class TbaRoom(area_reader.model.MudBase):
    NATIVE_SUFFIX = native_tba_room_suffix

    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    zone_number = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_number, suffix=" "))
    room_flags = area_reader.schema.field(
        default=(0, 0, 0, 0), type=tuple[int, int, int, int], native=NativeField(5, native_tba_flag_banks, suffix=" ")
    )
    sector_type = area_reader.schema.field(default=0, type=int, native=NativeField(6, native_number))
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(7, native_records, suffix=""),
    )
    exits = area_reader.schema.field(
        default=Factory(dict),
        native=NativeField(8, area_reader.dialects.circle.native_circle_mapping_records, suffix=""),
    )
    triggers = attr(default=Factory(list), type=list[int])
    source_file = attr(default="", type=str)


@attributes
class TbaMob(area_reader.model.MudBase):
    NATIVE_SUFFIX = native_tba_mobile_suffix

    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    long_desc = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(5, native_tilde_string))
    act_flags = area_reader.schema.field(
        default=(8, 0, 0, 0), type=tuple[int, int, int, int], native=NativeField(6, native_tba_flag_banks, suffix=" ")
    )
    affected_flags = area_reader.schema.field(
        default=(0, 0, 0, 0), type=tuple[int, int, int, int], native=NativeField(7, native_tba_flag_banks, suffix=" ")
    )
    alignment = area_reader.schema.field(default=0, type=int, native=NativeField(8, native_number, suffix=" "))
    mob_type = area_reader.schema.field(default="E", type=str, native=NativeField(9, native_tba_mobile_type))
    level = area_reader.schema.field(default=0, type=int, native=NativeField(10, native_number, suffix=" "))
    hitroll = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_tba_hitroll, suffix=" "))
    ac = area_reader.schema.field(default=0, type=int, native=NativeField(12, native_tba_armor_class, suffix=" "))
    hit = area_reader.schema.field(
        default=Factory(area_reader.model.Dice),
        type=area_reader.model.Dice,
        native=NativeField(13, native_tba_dice, suffix=" "),
    )
    damage = area_reader.schema.field(
        default=Factory(area_reader.model.Dice), type=area_reader.model.Dice, native=NativeField(14, native_tba_dice)
    )
    wealth = area_reader.schema.field(default=0, type=int, native=NativeField(15, native_number, suffix=" "))
    exp = area_reader.schema.field(default=0, type=int, native=NativeField(16, native_number))
    start_pos = area_reader.schema.field(default=0, type=int, native=NativeField(17, native_number, suffix=" "))
    default_pos = area_reader.schema.field(default=0, type=int, native=NativeField(18, native_number, suffix=" "))
    sex = area_reader.schema.field(default=0, type=int, native=NativeField(19, native_number))
    especs = area_reader.schema.field(
        default=Factory(dict),
        native=NativeField(20, native_tba_mobile_especs, suffix="E\n", when=lambda owner: owner.mob_type == "E"),
    )
    triggers = attr(default=Factory(list), type=list[int])
    source_file = attr(default="", type=str)

    @property
    def act(self):
        return combine_flag_banks(self.act_flags)

    @property
    def affected_by(self):
        return combine_flag_banks(self.affected_flags)


@attributes
class TbaAffectData(area_reader.dialects.circle.CircleAffectData):
    pass


@attributes
class TbaItem(area_reader.model.MudBase):
    vnum = area_reader.schema.field(
        default=0, type=area_reader.values.VNum, read=False, native=NativeField(1, native_number, prefix="#")
    )
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    short_desc = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    action_description = area_reader.schema.field(default="", type=str, native=NativeField(5, native_tilde_string))
    item_type = area_reader.schema.field(default=-1, type=int, native=NativeField(6, native_number, suffix=" "))
    extra_flag_banks = area_reader.schema.field(
        default=(0, 0, 0, 0), type=tuple[int, int, int, int], native=NativeField(7, native_tba_flag_banks, suffix=" ")
    )
    wear_flag_banks = area_reader.schema.field(
        default=(0, 0, 0, 0), type=tuple[int, int, int, int], native=NativeField(8, native_tba_flag_banks, suffix=" ")
    )
    affect_flag_banks = area_reader.schema.field(
        default=(0, 0, 0, 0), type=tuple[int, int, int, int], native=NativeField(9, native_tba_flag_banks)
    )
    value = area_reader.schema.field(default=Factory(list), type=list[int], native=NativeField(10, native_tba_numbers))
    weight = area_reader.schema.field(default=0, type=int, native=NativeField(11, native_number, suffix=" "))
    cost = area_reader.schema.field(default=0, type=int, native=NativeField(12, native_number, suffix=" "))
    rent = area_reader.schema.field(default=0, type=int, native=NativeField(13, native_number, suffix=" "))
    level = area_reader.schema.field(default=0, type=int, native=NativeField(14, native_number, suffix=" "))
    timer = area_reader.schema.field(default=0, type=int, native=NativeField(15, native_number))
    triggers = area_reader.schema.field(
        default=Factory(list), type=list[int], native=NativeField(16, native_tba_trigger_assignments, suffix="")
    )
    extra_descriptions = area_reader.schema.field(
        default=Factory(list),
        type=list[area_reader.model.ExtraDescription],
        native=NativeField(17, native_records, suffix=""),
    )
    affected = area_reader.schema.field(
        default=Factory(list), type=list[TbaAffectData], native=NativeField(18, native_records, suffix="")
    )
    source_file = attr(default="", type=str)

    @property
    def extra_flags(self):
        return combine_flag_banks(self.extra_flag_banks)

    @property
    def wear_flags(self):
        return combine_flag_banks(self.wear_flag_banks)

    @property
    def affected_by(self):
        return combine_flag_banks(self.affect_flag_banks)


@attributes
class TbaReset:
    command = area_reader.schema.field(default="", type=str, native=NativeField(1, native_tba_reset))
    if_flag = attr(default=0, type=int)
    arg1 = attr(default=0, type=int)
    arg2 = attr(default=0, type=int)
    arg3 = attr(default=None, type=int | None)
    sarg1 = attr(default=None, type=str | None)
    sarg2 = attr(default=None, type=str | None)


@attributes
class TbaZone:
    NATIVE_SUFFIX = "S\n"

    vnum = area_reader.schema.field(default=0, type=int, native=NativeField(1, native_number, prefix="#"))
    builders = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    name = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    bot = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_tba_zone_header))
    top = attr(default=0, type=int)
    lifespan = attr(default=0, type=int)
    reset_mode = attr(default=0, type=int)
    zone_flags = attr(default=(0, 0, 0, 0), type=tuple[int, int, int, int])
    min_level = attr(default=-1, type=int)
    max_level = attr(default=-1, type=int)
    resets = area_reader.schema.field(
        default=Factory(list), type=list[TbaReset], native=NativeField(5, native_records, suffix="")
    )
    source_file = attr(default="", type=str)


@attributes
class TbaTrigger:
    vnum = area_reader.schema.field(default=0, type=int, native=NativeField(1, native_number, prefix="#"))
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    attach_type = area_reader.schema.field(default=0, type=int, native=NativeField(3, native_number, suffix=" "))
    trigger_type = area_reader.schema.field(default=0, type=int, native=NativeField(4, native_number, suffix=" "))
    narg = area_reader.schema.field(default=0, type=int, native=NativeField(5, native_number))
    arglist = area_reader.schema.field(default="", type=str, native=NativeField(6, native_tilde_string))
    commands = area_reader.schema.field(default="", type=str, native=NativeField(7, native_tilde_string))
    source_file = attr(default="", type=str)


@attributes
class TbaQuest:
    NATIVE_SUFFIX = "S\n"

    vnum = area_reader.schema.field(default=0, type=int, native=NativeField(1, native_number, prefix="#"))
    name = area_reader.schema.field(default="", type=str, native=NativeField(2, native_tilde_string))
    description = area_reader.schema.field(default="", type=str, native=NativeField(3, native_tilde_string))
    information = area_reader.schema.field(default="", type=str, native=NativeField(4, native_tilde_string))
    completion = area_reader.schema.field(default="", type=str, native=NativeField(5, native_tilde_string))
    quit_message = area_reader.schema.field(default="", type=str, native=NativeField(6, native_tilde_string))
    quest_type = area_reader.schema.field(default=-1, type=int, native=NativeField(7, native_number, suffix=" "))
    quest_master = area_reader.schema.field(default=-1, type=int, native=NativeField(8, native_number, suffix=" "))
    flags = area_reader.schema.field(default=0, type=int, native=NativeField(9, native_number, suffix=" "))
    target = area_reader.schema.field(default=-1, type=int, native=NativeField(10, native_number, suffix=" "))
    previous = area_reader.schema.field(default=-1, type=int, native=NativeField(11, native_number, suffix=" "))
    next = area_reader.schema.field(default=-1, type=int, native=NativeField(12, native_number, suffix=" "))
    prerequisite = area_reader.schema.field(default=-1, type=int, native=NativeField(13, native_number))
    values = area_reader.schema.field(
        default=(0, 0, 0, 0, 0, 0, 0),
        type=tuple[int, int, int, int, int, int, int],
        native=NativeField(14, native_tba_numbers),
    )
    gold_reward = area_reader.schema.field(default=0, type=int, native=NativeField(15, native_number, suffix=" "))
    experience_reward = area_reader.schema.field(default=0, type=int, native=NativeField(16, native_number, suffix=" "))
    object_reward = area_reader.schema.field(default=-1, type=int, native=NativeField(17, native_number))
    source_file = attr(default="", type=str)


@attributes
class TbaArea:
    NATIVE_COLLECTIONS = (
        ("zon", "zones", "$\n"),
        ("trg", "triggers", "$~\n"),
        ("wld", "rooms", "$~\n"),
        ("mob", "mobs", "$\n"),
        ("obj", "objects", "$~\n"),
        ("shp", "shops", "$~\n"),
        ("qst", "quests", "$~\n"),
    )

    zones = attr(default=Factory(OrderedDict))
    triggers = attr(default=Factory(OrderedDict))
    rooms = attr(default=Factory(OrderedDict))
    mobs = attr(default=Factory(OrderedDict))
    objects = attr(default=Factory(OrderedDict))
    shops = attr(default=Factory(OrderedDict))
    quests = attr(default=Factory(OrderedDict))
    indexes = attr(default=Factory(OrderedDict))
    shop_headers = attr(default=Factory(OrderedDict))


class TbaAreaFile(area_reader.dialects.circle.CircleAreaFile):
    NATIVE_NORMALIZATIONS = area_reader.dialects.circle.CircleAreaFile.NATIVE_NORMALIZATIONS + (
        "zone-reset-comments",
        "unused-zone-reset-arguments",
        "empty-shop-headers",
    )

    def __init__(self, root):
        super().__init__(root)
        self.area = TbaArea()

    def load_sections(self):
        self.load_zones()
        self.load_triggers()
        self.load_rooms()
        self.load_mobiles()
        self.load_objects()
        self.load_shops()
        self.load_quests()

    def read_string(self):
        while self.current_char in ("\r", "\n"):
            self.index += 1
        start = self.index
        line_start = self.index
        while line_start < len(self.data):
            line_end = self.data.find("\n", line_start)
            if line_end == -1:
                line_end = len(self.data)
                next_line = len(self.data)
            else:
                next_line = line_end + 1
            content_end = line_end
            if content_end > line_start and self.data[content_end - 1] == "\r":
                content_end -= 1
            if content_end > line_start and self.data[content_end - 1] == "~":
                result = self.data[start : content_end - 1]
                self.index = next_line
                return result
            line_start = next_line
        self.index = len(self.data)
        self.parse_fail("Unterminated string")

    def read_flag_banks(self, values):
        if len(values) != 4:
            self.parse_fail(f"Expected four flag banks, got {len(values)}")
        return tuple(area_reader.dialects.circle.circle_asciiflag_conv(value) for value in values)

    def read_trigger_assignments(self):
        triggers = []
        while True:
            self.skip_whitespace()
            if self.current_char != "T":
                return triggers
            line = self.read_line().strip().split()
            if len(line) != 2 or line[0] != "T":
                self.parse_fail("Expected a T trigger assignment followed by one vnum")
            try:
                triggers.append(int(line[1]))
            except ValueError:
                self.parse_fail(f"Expected a numeric trigger vnum, got {line[1]!r}")

    def load_zone_file(self, path):
        self.open_circle_file(path)
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            builders = self.read_string()
            name = self.read_string()
            header = self.read_line().split()
            if len(header) == 4:
                bot, top, lifespan, reset_mode = map(int, header)
                zone_flags = (0, 0, 0, 0)
                min_level = max_level = -1
            elif len(header) == 10:
                bot, top, lifespan, reset_mode = map(int, header[:4])
                zone_flags = self.read_flag_banks(header[4:8])
                min_level, max_level = map(int, header[8:])
            else:
                self.parse_fail(f"Expected 4 or 10 zone header fields, got {len(header)}")
            zone = TbaZone(
                vnum=vnum,
                builders=builders,
                name=name,
                bot=bot,
                top=top,
                lifespan=lifespan,
                reset_mode=reset_mode,
                zone_flags=zone_flags,
                min_level=min_level,
                max_level=max_level,
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
                try:
                    if command == "V":
                        if_flag, arg1, arg2, arg3 = map(int, parts[:4])
                        sarg1 = parts[4]
                        sarg2 = " ".join(parts[5:])
                    elif command in "MOGEPDT":
                        if_flag, arg1, arg2, arg3 = map(int, parts[:4])
                        sarg1 = sarg2 = None
                    else:
                        if_flag, arg1, arg2 = map(int, parts[:3])
                        arg3 = None
                        sarg1 = sarg2 = None
                except (IndexError, ValueError):
                    self.parse_fail(f"Invalid {command!r} zone reset")
                zone.resets.append(
                    TbaReset(
                        command=command,
                        if_flag=if_flag,
                        arg1=arg1,
                        arg2=arg2,
                        arg3=arg3,
                        sarg1=sarg1,
                        sarg2=sarg2,
                    )
                )
            self.area.zones[vnum] = zone

    def read_room(self, vnum):
        name = self.read_string()
        description = self.read_string()
        header = self.read_line().split()
        if len(header) != 6:
            self.parse_fail(f"Expected six tbaMUD room fields, got {len(header)}")
        room = TbaRoom(
            vnum=vnum,
            name=name,
            description=description,
            zone_number=int(header[0]),
            room_flags=self.read_flag_banks(header[1:5]),
            sector_type=int(header[5]),
        )
        while True:
            line = self.read_line().strip()
            if line == "S":
                room.triggers = self.read_trigger_assignments()
                return room
            if line.startswith("D"):
                exit_record = self.read_exit(int(line[1:]))
                room.exits[exit_record.door] = exit_record
            elif line == "E":
                room.extra_descriptions.append(
                    area_reader.model.ExtraDescription(keyword=self.read_string(), description=self.read_string())
                )
            else:
                self.parse_fail(f"Unknown room metadata {line!r}")

    def read_exit(self, door):
        description = self.read_string()
        keyword = self.read_string()
        values = self.read_int_list()
        if len(values) != 3:
            self.parse_fail(f"Expected three tbaMUD exit fields, got {len(values)}")
        locks, key, destination = values
        if locks not in range(5):
            self.parse_fail(f"Unknown tbaMUD exit lock code {locks}")
        exit_info = EXIT_FLAGS.NONE
        if locks:
            exit_info |= EXIT_FLAGS.ISDOOR
        if locks in (2, 4):
            exit_info |= EXIT_FLAGS.PICKPROOF
        return TbaExit(
            door=door,
            description=description,
            keyword=keyword,
            exit_info=exit_info,
            hidden=locks in (3, 4),
            key=key,
            destination=destination,
        )

    def read_mobile(self, vnum):
        name = self.read_string()
        short_desc = self.read_string()
        long_desc = self.read_string()
        description = self.read_string()
        header = self.read_line().split()
        if len(header) != 10:
            self.parse_fail(f"Expected ten tbaMUD mobile fields, got {len(header)}")
        act_flags = list(self.read_flag_banks(header[:4]))
        act_flags[0] |= area_reader.dialects.circle.CircleMobFlags.ISNPC.value
        affected_flags = self.read_flag_banks(header[4:8])
        numeric = self.read_line().split()
        if len(numeric) != 5:
            self.parse_fail(f"Expected five tbaMUD mobile combat fields, got {len(numeric)}")
        wealth_exp = self.read_int_list()
        positions = self.read_int_list()
        if len(wealth_exp) != 2 or len(positions) != 3:
            self.parse_fail("Invalid tbaMUD mobile numeric tail")
        especs = {}
        mob_type = header[9].upper()
        if mob_type == "E":
            while True:
                line = self.read_line().strip()
                if line == "E":
                    break
                if ":" in line:
                    key, value = line.split(":", 1)
                    especs[key.strip()] = value.strip()
                else:
                    self.parse_fail(f"Invalid enhanced-mobile espec {line!r}")
        elif mob_type != "S":
            self.parse_fail(f"Unsupported tbaMUD mobile type {mob_type!r}")
        triggers = self.read_trigger_assignments()
        return TbaMob(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            long_desc=long_desc,
            description=description,
            act_flags=tuple(act_flags),
            affected_flags=affected_flags,
            alignment=int(header[8]),
            mob_type=mob_type,
            level=int(numeric[0]),
            hitroll=20 - int(numeric[1]),
            ac=int(numeric[2]) * 10,
            hit=self.parse_dice_token(numeric[3]),
            damage=self.parse_dice_token(numeric[4]),
            wealth=wealth_exp[0],
            exp=wealth_exp[1],
            start_pos=positions[0],
            default_pos=positions[1],
            sex=positions[2],
            especs=especs,
            triggers=triggers,
        )

    def read_item(self, vnum):
        name = self.read_string()
        short_desc = self.read_string()
        description = self.read_string()
        action_description = self.read_string()
        header = self.read_line().split()
        if len(header) != 13:
            self.parse_fail(f"Expected thirteen tbaMUD object fields, got {len(header)}")
        values = self.read_int_list()
        if len(values) != 4:
            self.parse_fail(f"Expected four tbaMUD object values, got {len(values)}")
        numeric = self.read_int_list()
        if len(numeric) not in (3, 4, 5):
            self.parse_fail(f"Expected three to five tbaMUD object tail fields, got {len(numeric)}")
        numeric += [0] * (5 - len(numeric))
        affected = []
        extra_descriptions = []
        triggers = []
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
                location_modifier = self.read_int_list()
                if len(location_modifier) != 2:
                    self.parse_fail("Expected two tbaMUD object affect fields")
                affected.append(TbaAffectData(location=location_modifier[0], modifier=location_modifier[1]))
            elif line.startswith("T "):
                try:
                    triggers.append(int(line.split()[1]))
                except (IndexError, ValueError):
                    self.parse_fail(f"Invalid object trigger assignment {line!r}")
            else:
                self.parse_fail(f"Unknown object metadata {line!r}")
        return TbaItem(
            vnum=vnum,
            name=name,
            short_desc=short_desc,
            description=description,
            action_description=action_description,
            item_type=int(header[0]),
            extra_flag_banks=self.read_flag_banks(header[1:5]),
            wear_flag_banks=self.read_flag_banks(header[5:9]),
            affect_flag_banks=self.read_flag_banks(header[9:13]),
            value=values,
            weight=numeric[0],
            cost=numeric[1],
            rent=numeric[2],
            level=numeric[3],
            timer=numeric[4],
            triggers=triggers,
            extra_descriptions=extra_descriptions,
            affected=affected,
        )

    def load_shop_file(self, path):
        self.open_circle_file(path)
        self.skip_whitespace()
        if self.current_char == "$":
            self.area.shop_headers[os.path.basename(path)] = "CircleMUD v3.0 Shop File"
            return
        header = self.read_string()
        self.area.shop_headers[os.path.basename(path)] = header
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            shop = self.read_shop(vnum, header)
            shop.source_file = os.path.basename(path)
            self.area.shops[vnum] = shop

    def load_triggers(self):
        for path in self.indexed_paths("trg"):
            self.load_trigger_file(path)

    def load_trigger_file(self, path):
        self.open_circle_file(path)
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            name = self.read_string()
            header = self.read_line().split()
            if len(header) not in (2, 3):
                self.parse_fail(f"Expected two or three tbaMUD trigger fields, got {len(header)}")
            attach_type = int(header[0])
            trigger_type = area_reader.dialects.circle.circle_asciiflag_conv(header[1])
            narg = int(header[2]) if len(header) == 3 else 0
            self.area.triggers[vnum] = TbaTrigger(
                vnum=vnum,
                name=name,
                attach_type=attach_type,
                trigger_type=trigger_type,
                narg=narg,
                arglist=self.read_string(),
                commands=self.read_string(),
                source_file=os.path.basename(path),
            )

    def load_quests(self):
        for path in self.indexed_paths("qst"):
            self.load_quest_file(path)

    def load_quest_file(self, path):
        self.open_circle_file(path)
        while True:
            vnum = self.read_record_header()
            if vnum is None:
                return
            name = self.read_string()
            description = self.read_string()
            information = self.read_string()
            completion = self.read_string()
            quit_message = self.read_string()
            header = self.read_line().split()
            values = self.read_int_list()
            rewards = self.read_int_list()
            if len(header) != 7 or len(values) != 7 or len(rewards) != 3:
                self.parse_fail("Invalid tbaMUD quest numeric fields")
            end = self.read_line().strip()
            if end != "S":
                self.parse_fail(f"Expected quest terminator 'S', got {end!r}")
            self.area.quests[vnum] = TbaQuest(
                vnum=vnum,
                name=name,
                description=description,
                information=information,
                completion=completion,
                quit_message=quit_message,
                quest_type=int(header[0]),
                quest_master=int(header[1]),
                flags=area_reader.dialects.circle.circle_asciiflag_conv(header[2]),
                target=int(header[3]),
                previous=int(header[4]),
                next=int(header[5]),
                prerequisite=int(header[6]),
                values=tuple(values),
                gold_reward=rewards[0],
                experience_reward=rewards[1],
                object_reward=rewards[2],
                source_file=os.path.basename(path),
            )
