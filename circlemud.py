"""
CircleMUD area file parser.

Parses CircleMUD's split file format (.wld, .mob, .obj, .zon, .shp) into
structured Python objects compatible with area_reader's output format.
"""

import logging
import re
import json
import os
from collections import OrderedDict
from typing import List, Dict, Optional
from attr import attr, attrs, Factory

logger = logging.getLogger('circlemud')

# CircleMUD constants
ROOM_FLAGS = {
    1: 'DARK', 2: 'DEATH', 4: 'NO_MOB', 8: 'INDOORS', 16: 'PEACEFUL',
    32: 'SOUNDPROOF', 64: 'NO_TRACK', 128: 'NO_MAGIC', 256: 'TUNNEL',
    512: 'PRIVATE', 1024: 'GODROOM', 2048: 'HOUSE', 4096: 'HOUSE_CRASH',
    8192: 'ATRIUM', 16384: 'OLC', 32768: 'BFS_MARK',
}

SECTOR_TYPES = {
    0: 'INSIDE', 1: 'CITY', 2: 'FIELD', 3: 'FOREST', 4: 'HILLS',
    5: 'MOUNTAIN', 6: 'WATER_SWIM', 7: 'WATER_NOSWIM', 8: 'UNDERWATER',
    9: 'FLYING',
}

DOOR_FLAGS = {0: 'NO_DOOR', 1: 'DOOR', 2: 'PICKPROOF'}

EXIT_DIRS = {0: 'NORTH', 1: 'EAST', 2: 'SOUTH', 3: 'WEST', 4: 'UP', 5: 'DOWN'}

MOB_ACTION_FLAGS = {
    1: 'SPEC', 2: 'SENTINEL', 4: 'SCAVENGER', 8: 'ISNPC', 16: 'AWARE',
    32: 'AGGRESSIVE', 64: 'STAY_ZONE', 128: 'WIMPY', 256: 'AGGR_EVIL',
    512: 'AGGR_GOOD', 1024: 'AGGR_NEUTRAL', 2048: 'MEMORY', 4096: 'HELPER',
    8192: 'NO_CHARM', 16384: 'NO_SUMMON', 32768: 'NO_SLEEP', 65536: 'NO_BASH',
    131072: 'NO_BLIND',
}

MOB_AFFECT_FLAGS = {
    1: 'BLIND', 2: 'INVISIBLE', 4: 'DETECT_ALIGN', 8: 'DETECT_INVIS',
    16: 'DETECT_MAGIC', 32: 'SENSE_LIFE', 64: 'WATERWALK', 128: 'SANCTUARY',
    256: 'GROUP', 512: 'CURSE', 1024: 'INFRAVISION', 2048: 'POISON',
    4096: 'PROTECT_EVIL', 8192: 'PROTECT_GOOD', 16384: 'SLEEP', 32768: 'NO_TRACK',
    65536: 'FLYING', 262144: 'SNEAK', 524288: 'HIDE', 2097152: 'CHARM',
}

POSITIONS = {
    0: 'DEAD', 1: 'MORTALLY_WOUNDED', 2: 'INCAPACITATED', 3: 'STUNNED',
    4: 'SLEEPING', 5: 'RESTING', 6: 'SITTING', 7: 'FIGHTING', 8: 'STANDING',
}

GENDERS = {0: 'NEUTRAL', 1: 'MALE', 2: 'FEMALE'}

ITEM_TYPES = {
    1: 'LIGHT', 2: 'SCROLL', 3: 'WAND', 4: 'STAFF', 5: 'WEAPON',
    6: 'FIRE_WEAPON', 7: 'MISSILE', 8: 'TREASURE', 9: 'ARMOR', 10: 'POTION',
    11: 'WORN', 12: 'OTHER', 13: 'TRASH', 14: 'TRAP', 15: 'CONTAINER',
    16: 'NOTE', 17: 'DRINKCON', 18: 'KEY', 19: 'FOOD', 20: 'MONEY',
    21: 'PEN', 22: 'BOAT', 23: 'FOUNTAIN',
}

WEAR_FLAGS = {
    1: 'TAKE', 2: 'FINGER', 4: 'NECK', 8: 'BODY', 16: 'HEAD', 32: 'LEGS',
    64: 'FEET', 128: 'HANDS', 256: 'ARMS', 512: 'SHIELD', 1024: 'ABOUT',
    2048: 'WAIST', 4096: 'WRIST', 8192: 'WIELD', 16384: 'HOLD',
}

EXTRA_FLAGS = {
    1: 'GLOW', 2: 'HUM', 4: 'NO_RENT', 8: 'NO_DONATE', 16: 'NO_INVIS',
    32: 'INVISIBLE', 64: 'MAGIC', 128: 'NO_DROP', 256: 'BLESS',
    512: 'ANTI_GOOD', 1024: 'ANTI_EVIL', 2048: 'ANTI_NEUTRAL',
    4096: 'ANTI_MAGIC_USER', 8192: 'ANTI_CLERIC', 16384: 'ANTI_THIEF',
    32768: 'ANTI_WARRIOR', 65536: 'NO_SELL',
}

APPLY_TYPES = {
    0: 'NONE', 1: 'STR', 2: 'DEX', 3: 'INT', 4: 'WIS', 5: 'CON', 6: 'CHA',
    7: 'CLASS', 8: 'LEVEL', 9: 'AGE', 10: 'CHAR_WEIGHT', 11: 'CHAR_HEIGHT',
    12: 'MANA', 13: 'HIT', 14: 'MOVE', 15: 'GOLD', 16: 'EXP', 17: 'AC',
    18: 'HITROLL', 19: 'DAMROLL', 20: 'SAVING_PARA', 21: 'SAVING_ROD',
    22: 'SAVING_PETRI', 23: 'SAVING_BREATH', 24: 'SAVING_SPELL',
}


def bitvector_to_flags(value, flag_dict):
    """Convert a numeric bitvector to list of flag names."""
    if value == 0:
        return []
    flags = []
    for bit, name in flag_dict.items():
        if value & bit:
            flags.append(name)
    return flags


def parse_bitvector(text):
    """Parse a bitvector that may be numeric or letter-coded."""
    text = text.strip()
    if not text or text == '0':
        return 0

    # Check if it's purely numeric
    try:
        return int(text)
    except ValueError:
        pass

    # Letter-coded bitvector (a=1, b=2, c=4, etc.)
    value = 0
    for char in text:
        if 'a' <= char <= 'z':
            value |= (1 << (ord(char) - ord('a')))
        elif 'A' <= char <= 'Z':
            value |= (1 << (ord(char) - ord('A')))
    return value


def parse_dice(text):
    """Parse a dice string like '3d8+10' into dict."""
    text = text.strip()
    if '+' in text:
        dice_part, bonus = text.split('+')
    elif '-' in text:
        dice_part, bonus = text.split('-')
        bonus = '-' + bonus
    else:
        dice_part = text
        bonus = '0'

    if 'd' in dice_part.lower():
        num, sides = dice_part.lower().split('d')
        return {'number': int(num), 'sides': int(sides), 'bonus': int(bonus)}
    return {'number': 0, 'sides': 0, 'bonus': int(dice_part)}


@attrs
class CircleMudExit:
    direction = attr(default=0)
    description = attr(default='')
    keywords = attr(default=Factory(list))
    door_flags = attr(default=0)
    key_vnum = attr(default=-1)
    destination = attr(default=-1)


@attrs
class CircleMudExtraDesc:
    keywords = attr(default=Factory(list))
    description = attr(default='')


@attrs
class CircleMudRoom:
    vnum = attr(default='')
    name = attr(default='')
    description = attr(default='')
    zone_number = attr(default='')
    room_flags = attr(default=0)
    sector_type = attr(default=0)
    exits = attr(default=Factory(list))
    extra_descriptions = attr(default=Factory(list))


@attrs
class CircleMudMobile:
    vnum = attr(default='')
    aliases = attr(default=Factory(list))
    short_desc = attr(default='')
    long_desc = attr(default='')
    description = attr(default='')
    action_flags = attr(default=0)
    affect_flags = attr(default=0)
    alignment = attr(default=0)
    mob_type = attr(default='S')
    level = attr(default=1)
    thac0 = attr(default=20)
    ac = attr(default=10)
    hit_dice = attr(default=Factory(dict))
    damage_dice = attr(default=Factory(dict))
    gold = attr(default=0)
    xp = attr(default=0)
    load_position = attr(default=8)
    default_position = attr(default=8)
    sex = attr(default=0)
    extra_specs = attr(default=Factory(dict))


@attrs
class CircleMudObject:
    vnum = attr(default='')
    aliases = attr(default=Factory(list))
    short_desc = attr(default='')
    long_desc = attr(default='')
    action_desc = attr(default='')
    item_type = attr(default=0)
    extra_flags = attr(default=0)
    wear_flags = attr(default=0)
    values = attr(default=Factory(list))
    weight = attr(default=0)
    cost = attr(default=0)
    rent = attr(default=0)
    affects = attr(default=Factory(list))
    extra_descriptions = attr(default=Factory(list))


@attrs
class CircleMudReset:
    command = attr(default='')
    if_flag = attr(default=0)
    arg1 = attr(default=0)
    arg2 = attr(default=0)
    arg3 = attr(default=0)
    comment = attr(default='')


@attrs
class CircleMudZone:
    vnum = attr(default='')
    name = attr(default='')
    top_room = attr(default=0)
    lifespan = attr(default=30)
    reset_mode = attr(default=2)
    resets = attr(default=Factory(list))


@attrs
class CircleMudShop:
    vnum = attr(default='')
    products = attr(default=Factory(list))
    buy_types = attr(default=Factory(list))
    profit_buy = attr(default=1.0)
    profit_sell = attr(default=1.0)
    keeper = attr(default=0)
    shop_flags = attr(default=0)
    rooms = attr(default=Factory(list))
    open_hour1 = attr(default=0)
    close_hour1 = attr(default=28)
    open_hour2 = attr(default=0)
    close_hour2 = attr(default=0)


@attrs
class CircleMudArea:
    """Container for all CircleMUD zone data."""
    name = attr(default='')
    zone_vnum = attr(default='')
    rooms = attr(default=Factory(OrderedDict))
    mobs = attr(default=Factory(OrderedDict))
    objects = attr(default=Factory(OrderedDict))
    zone = attr(default=None)
    shops = attr(default=Factory(list))


class CircleMudFile:
    """Parser for CircleMUD split-file format."""

    def __init__(self, directory):
        """Initialize with a directory containing .wld, .mob, .obj, .zon, .shp files."""
        self.directory = directory
        self.area = CircleMudArea()
        self.files = {}
        self._discover_files()

    def _discover_files(self):
        """Find all parseable files in the directory."""
        for filename in os.listdir(self.directory):
            filepath = os.path.join(self.directory, filename)
            if not os.path.isfile(filepath):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext in ('.wld', '.mob', '.obj', '.zon', '.shp'):
                if ext not in self.files:
                    self.files[ext] = []
                self.files[ext].append(filepath)

    def load_sections(self):
        """Load all available sections."""
        if '.zon' in self.files:
            for f in self.files['.zon']:
                self._load_zone(f)
        if '.wld' in self.files:
            for f in self.files['.wld']:
                self._load_rooms(f)
        if '.mob' in self.files:
            for f in self.files['.mob']:
                self._load_mobiles(f)
        if '.obj' in self.files:
            for f in self.files['.obj']:
                self._load_objects(f)
        if '.shp' in self.files:
            for f in self.files['.shp']:
                self._load_shops(f)

    def _read_file(self, filepath):
        """Read file with flexible encoding."""
        for encoding in ('utf-8', 'latin-1', 'ascii'):
            try:
                with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        return ''

    def _split_records(self, text, terminator='#99999'):
        """Split file into records by # delimiter."""
        # Remove terminator and anything after
        if terminator in text:
            text = text.split(terminator)[0]
        if '$~' in text:
            text = text.split('$~')[0]
        if '$' in text and text.strip().endswith('$'):
            text = text.rsplit('$', 1)[0]

        # Split by # but keep the vnum
        records = []
        parts = re.split(r'\n#', text)
        for i, part in enumerate(parts):
            if i == 0:
                # First part might start with #
                if part.startswith('#'):
                    part = part[1:]
                elif not part.strip():
                    continue
            part = part.strip()
            if part and not part.startswith('$'):
                records.append(part)
        return records

    def _load_zone(self, filepath):
        """Load zone file."""
        text = self._read_file(filepath)
        lines = text.strip().split('\n')

        zone = CircleMudZone()

        # Parse header
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#'):
                zone.vnum = line[1:].strip()
                i += 1
                break
            i += 1

        if i < len(lines):
            zone.name = lines[i].rstrip('~').strip()
            i += 1

        if i < len(lines):
            parts = lines[i].split()
            if len(parts) >= 3:
                zone.top_room = parts[0]
                zone.lifespan = int(parts[1]) if parts[1].isdigit() else 30
                zone.reset_mode = int(parts[2]) if parts[2].isdigit() else 2
            i += 1

        # Parse reset commands
        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if not line or line.startswith('*'):
                continue
            if line == 'S' or line == '$':
                break

            parts = line.split()
            if not parts:
                continue

            cmd = parts[0]
            if cmd not in 'MOGEPDRT':
                continue

            reset = CircleMudReset(command=cmd)

            # Extract comment (after tab or multiple spaces)
            comment = ''
            if '\t' in line:
                comment = line.split('\t', 1)[-1].strip()

            try:
                if cmd in 'MOEPD':
                    reset.if_flag = int(parts[1]) if len(parts) > 1 else 0
                    reset.arg1 = parts[2] if len(parts) > 2 else ''
                    reset.arg2 = parts[3] if len(parts) > 3 else ''
                    reset.arg3 = parts[4] if len(parts) > 4 else ''
                elif cmd == 'G':
                    reset.if_flag = int(parts[1]) if len(parts) > 1 else 0
                    reset.arg1 = parts[2] if len(parts) > 2 else ''
                    reset.arg2 = parts[3] if len(parts) > 3 else ''
                elif cmd == 'R':
                    reset.if_flag = int(parts[1]) if len(parts) > 1 else 0
                    reset.arg1 = parts[2] if len(parts) > 2 else ''
                    reset.arg2 = parts[3] if len(parts) > 3 else ''
            except (ValueError, IndexError):
                pass

            reset.comment = comment
            zone.resets.append(reset)

        self.area.zone = zone
        self.area.zone_vnum = zone.vnum
        self.area.name = zone.name

    def _load_rooms(self, filepath):
        """Load world/room file."""
        text = self._read_file(filepath)
        records = self._split_records(text)

        for record in records:
            try:
                room = self._parse_room(record)
                if room:
                    self.area.rooms[room.vnum] = room
            except Exception as e:
                logger.debug(f"Error parsing room: {e}")

    def _parse_room(self, text):
        """Parse a single room record."""
        parts = text.split('~')
        if len(parts) < 3:
            return None

        room = CircleMudRoom()

        # First part: vnum and name
        first = parts[0].strip()
        if '\n' in first:
            vnum, name = first.split('\n', 1)
        else:
            vnum = first
            name = ''

        room.vnum = vnum.strip()
        room.name = name.strip()
        room.description = parts[1].strip()

        # Third part: zone flags sector (and possibly more)
        flags_line = parts[2].strip().split('\n')[0].strip()
        flags_parts = flags_line.split()

        if len(flags_parts) >= 1:
            room.zone_number = flags_parts[0]
        if len(flags_parts) >= 2:
            room.room_flags = parse_bitvector(flags_parts[1])
        if len(flags_parts) >= 3:
            try:
                room.sector_type = int(flags_parts[2])
            except ValueError:
                room.sector_type = 0

        # Parse exits (D0-D5)
        bottom = '~'.join(parts[2:])
        exit_pattern = re.compile(r'D(\d+)\n(.*?)~\n(.*?)~\n(\S+)\s+(\S+)\s+(\S+)', re.DOTALL)
        for match in exit_pattern.finditer(bottom):
            direction, desc, keywords, door_flag, key, dest = match.groups()
            exit_obj = CircleMudExit(
                direction=int(direction),
                description=desc.strip(),
                keywords=keywords.split() if keywords.strip() else [],
                door_flags=int(door_flag) if door_flag.lstrip('-').isdigit() else 0,
                key_vnum=key,
                destination=dest
            )
            room.exits.append(exit_obj)

        # Parse extra descriptions (E)
        extra_pattern = re.compile(r'\nE\n(.*?)~\n(.*?)~', re.DOTALL)
        for match in extra_pattern.finditer(bottom):
            keywords, desc = match.groups()
            extra = CircleMudExtraDesc(
                keywords=keywords.split(),
                description=desc.strip()
            )
            room.extra_descriptions.append(extra)

        return room

    def _load_mobiles(self, filepath):
        """Load mobile file."""
        text = self._read_file(filepath)
        records = self._split_records(text)

        for record in records:
            try:
                mob = self._parse_mobile(record)
                if mob:
                    self.area.mobs[mob.vnum] = mob
            except Exception as e:
                logger.debug(f"Error parsing mobile: {e}")

    def _parse_mobile(self, text):
        """Parse a single mobile record."""
        parts = text.split('~')
        if len(parts) < 5:
            return None

        mob = CircleMudMobile()

        # Parse vnum and aliases
        first = parts[0].strip()
        if '\n' in first:
            vnum, aliases = first.split('\n', 1)
        else:
            vnum = first
            aliases = ''

        mob.vnum = vnum.strip()
        mob.aliases = aliases.split() if aliases.strip() else []
        mob.short_desc = parts[1].strip()
        mob.long_desc = parts[2].strip()
        mob.description = parts[3].strip()

        # Parse stats from after the 4th tilde
        bottom = parts[4] if len(parts) > 4 else ''
        lines = [l.strip() for l in bottom.strip().split('\n') if l.strip()]

        if not lines:
            return mob

        # Line 1: action_flags affect_flags alignment mob_type
        stats1 = lines[0].split()
        if len(stats1) >= 4:
            mob.action_flags = parse_bitvector(stats1[0])
            mob.affect_flags = parse_bitvector(stats1[1])
            try:
                mob.alignment = int(stats1[2])
            except ValueError:
                mob.alignment = 0
            mob.mob_type = stats1[3]

        # Line 2: level thac0 ac hit_dice damage_dice
        if len(lines) > 1:
            stats2 = lines[1].split()
            if len(stats2) >= 5:
                try:
                    mob.level = int(stats2[0])
                    mob.thac0 = int(stats2[1])
                    mob.ac = int(stats2[2])
                    mob.hit_dice = parse_dice(stats2[3])
                    mob.damage_dice = parse_dice(stats2[4])
                except (ValueError, IndexError):
                    pass

        # Line 3: gold xp
        if len(lines) > 2:
            stats3 = lines[2].split()
            if len(stats3) >= 2:
                try:
                    mob.gold = int(stats3[0])
                    mob.xp = int(stats3[1])
                except ValueError:
                    pass

        # Line 4: load_pos default_pos sex
        if len(lines) > 3:
            stats4 = lines[3].split()
            if len(stats4) >= 3:
                try:
                    mob.load_position = int(stats4[0])
                    mob.default_position = int(stats4[1])
                    mob.sex = int(stats4[2])
                except ValueError:
                    pass

        # Extended specs for E-type mobs
        if mob.mob_type == 'E' and len(lines) > 4:
            for line in lines[4:]:
                if line == 'E':
                    break
                if ':' in line:
                    key, val = line.split(':', 1)
                    try:
                        mob.extra_specs[key.strip()] = int(val.strip())
                    except ValueError:
                        mob.extra_specs[key.strip()] = val.strip()

        return mob

    def _load_objects(self, filepath):
        """Load object file."""
        text = self._read_file(filepath)
        records = self._split_records(text)

        for record in records:
            try:
                obj = self._parse_object(record)
                if obj:
                    self.area.objects[obj.vnum] = obj
            except Exception as e:
                logger.debug(f"Error parsing object: {e}")

    def _parse_object(self, text):
        """Parse a single object record."""
        parts = text.split('~')
        if len(parts) < 5:
            return None

        obj = CircleMudObject()

        # Parse vnum and aliases
        first = parts[0].strip()
        if '\n' in first:
            vnum, aliases = first.split('\n', 1)
        else:
            vnum = first
            aliases = ''

        obj.vnum = vnum.strip()
        obj.aliases = aliases.split() if aliases.strip() else []
        obj.short_desc = parts[1].strip()
        obj.long_desc = parts[2].strip()
        obj.action_desc = parts[3].strip()

        # Parse type/flags/values from after 4th tilde
        bottom = parts[4] if len(parts) > 4 else ''
        lines = [l.strip() for l in bottom.strip().split('\n') if l.strip()]

        if not lines:
            return obj

        # Line 1: type extra_flags wear_flags
        type_line = lines[0].split()
        if len(type_line) >= 1:
            try:
                obj.item_type = int(type_line[0])
            except ValueError:
                obj.item_type = 0
        if len(type_line) >= 2:
            obj.extra_flags = parse_bitvector(type_line[1])
        if len(type_line) >= 3:
            obj.wear_flags = parse_bitvector(type_line[2])

        # Line 2: values
        if len(lines) > 1:
            obj.values = lines[1].split()

        # Line 3: weight cost rent
        if len(lines) > 2:
            wc_line = lines[2].split()
            if len(wc_line) >= 1:
                try:
                    obj.weight = int(wc_line[0])
                except ValueError:
                    pass
            if len(wc_line) >= 2:
                try:
                    obj.cost = int(wc_line[1])
                except ValueError:
                    pass
            if len(wc_line) >= 3:
                try:
                    obj.rent = int(wc_line[2])
                except ValueError:
                    pass

        # Parse affects (A) and extra descs (E) from remaining content
        remaining = '\n'.join(lines[3:]) if len(lines) > 3 else ''
        remaining = '~'.join(parts[5:]) if len(parts) > 5 else remaining

        # Affects
        affect_pattern = re.compile(r'\nA\n(\S+)\s+(\S+)')
        for match in affect_pattern.finditer('\n' + remaining):
            try:
                loc = int(match.group(1))
                mod = int(match.group(2))
                obj.affects.append({'location': loc, 'modifier': mod})
            except ValueError:
                pass

        # Extra descriptions
        extra_pattern = re.compile(r'\nE\n(.*?)~\n(.*?)~', re.DOTALL)
        for match in extra_pattern.finditer('\n' + remaining):
            keywords, desc = match.groups()
            obj.extra_descriptions.append(CircleMudExtraDesc(
                keywords=keywords.split(),
                description=desc.strip()
            ))

        return obj

    def _load_shops(self, filepath):
        """Load shop file."""
        text = self._read_file(filepath)

        # CircleMUD shop format varies significantly
        # Try to parse both old and new formats
        records = re.split(r'\n#', text)

        for record in records:
            try:
                shop = self._parse_shop(record)
                if shop:
                    self.area.shops.append(shop)
            except Exception as e:
                logger.debug(f"Error parsing shop: {e}")

    def _parse_shop(self, text):
        """Parse a single shop record."""
        if not text.strip():
            return None

        shop = CircleMudShop()
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]

        if not lines:
            return None

        # First line: vnum (possibly with "NEW~")
        first = lines[0].lstrip('#').rstrip('~').strip()
        if ' ' in first:
            first = first.split()[0]
        shop.vnum = first

        # This format varies a lot - just capture what we can
        return shop

    def as_dict(self):
        """Convert to dictionary for JSON serialization."""
        def convert(obj):
            if hasattr(obj, '__attrs_attrs__'):
                d = {}
                for a in obj.__attrs_attrs__:
                    val = getattr(obj, a.name)
                    d[a.name] = convert(val)
                return d
            elif isinstance(obj, (OrderedDict, dict)):
                return {k: convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert(v) for v in obj]
            else:
                return obj

        return convert(self.area)

    def as_json(self, indent=2):
        """Convert to JSON string."""
        return json.dumps(self.as_dict(), indent=indent)


def load_circlemud_area(directory):
    """Convenience function to load a CircleMUD area directory."""
    area = CircleMudFile(directory)
    area.load_sections()
    return area


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python circlemud.py <area_directory>")
        sys.exit(1)

    area = load_circlemud_area(sys.argv[1])
    print(area.as_json())
