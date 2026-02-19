"""
Normalization logic for converting format-specific area data to unified schema.

This module provides normalizers for each supported MUD format that convert
format-specific data structures into the normalized schema while preserving
the original data for lossless round-trip.
"""

import enum
import json
from typing import Dict, List, Any, Optional

from normalized import (
    NormalizedArea, NormalizedMob, NormalizedItem, NormalizedRoom,
    NormalizedDice, NormalizedArmorClass, NormalizedExit
)

# ============================================================================
# Mapping Tables
# ============================================================================

# Position mappings: various format representations -> normalized string
POSITION_MAP = {
    # Numeric positions (Merc/Circle)
    0: 'dead',
    1: 'mortally_wounded',
    2: 'incapacitated',
    3: 'stunned',
    4: 'sleeping',
    5: 'resting',
    6: 'sitting',
    7: 'fighting',
    8: 'standing',
    # Word positions (ROM)
    'dead': 'dead',
    'mort': 'mortally_wounded',
    'incap': 'incapacitated',
    'stun': 'stunned',
    'sleep': 'sleeping',
    'rest': 'resting',
    'sit': 'sitting',
    'fight': 'fighting',
    'stand': 'standing',
}

SEX_MAP = {
    # Numeric (Merc/Circle)
    0: 'none',
    1: 'male',
    2: 'female',
    # Word (ROM)
    'none': 'none',
    'neutral': 'none',
    'male': 'male',
    'female': 'female',
    'either': 'either',
    'random': 'either',
}

SECTOR_MAP = {
    # Numeric values
    0: 'inside',
    1: 'city',
    2: 'field',
    3: 'forest',
    4: 'hills',
    5: 'mountain',
    6: 'water_swim',
    7: 'water_noswim',
    8: 'unused',
    9: 'air',
    10: 'desert',
    # CircleMUD additions
    'INSIDE': 'inside',
    'CITY': 'city',
    'FIELD': 'field',
    'FOREST': 'forest',
    'HILLS': 'hills',
    'MOUNTAIN': 'mountain',
    'WATER_SWIM': 'water_swim',
    'WATER_NOSWIM': 'water_noswim',
    'UNDERWATER': 'underwater',
    'FLYING': 'air',
}

DIRECTION_MAP = {
    0: 'north',
    1: 'east',
    2: 'south',
    3: 'west',
    4: 'up',
    5: 'down',
    6: 'somewhere',
    7: 'northeast',
    8: 'northwest',
    9: 'southeast',
    10: 'southwest',
    'NORTH': 'north',
    'EAST': 'east',
    'SOUTH': 'south',
    'WEST': 'west',
    'UP': 'up',
    'DOWN': 'down',
    'SOMEWHERE': 'somewhere',
    'NORTHEAST': 'northeast',
    'NORTHWEST': 'northwest',
    'SOUTHEAST': 'southeast',
    'SOUTHWEST': 'southwest',
}

# Item type mapping (numeric -> string)
ITEM_TYPE_MAP = {
    # ROM/Merc numeric types
    0: 'none',
    1: 'light',
    2: 'scroll',
    3: 'wand',
    4: 'staff',
    5: 'weapon',
    6: 'treasure',
    7: 'armor',
    8: 'potion',
    9: 'clothing',
    10: 'furniture',
    11: 'trash',
    12: 'container',
    13: 'drink',
    14: 'key',
    15: 'food',
    16: 'money',
    17: 'boat',
    18: 'npc_corpse',
    19: 'pc_corpse',
    20: 'fountain',
    21: 'pill',
    22: 'protect',
    23: 'map',
    24: 'portal',
    25: 'warp_stone',
    26: 'room_key',
    27: 'gem',
    28: 'jewelry',
    29: 'jukebox',
    # CircleMUD types (different numbering)
    'LIGHT': 'light',
    'SCROLL': 'scroll',
    'WAND': 'wand',
    'STAFF': 'staff',
    'WEAPON': 'weapon',
    'FIRE_WEAPON': 'fire_weapon',
    'MISSILE': 'missile',
    'TREASURE': 'treasure',
    'ARMOR': 'armor',
    'POTION': 'potion',
    'WORN': 'worn',
    'OTHER': 'other',
    'TRASH': 'trash',
    'TRAP': 'trap',
    'CONTAINER': 'container',
    'NOTE': 'note',
    'DRINKCON': 'drink',
    'KEY': 'key',
    'FOOD': 'food',
    'MONEY': 'money',
    'PEN': 'pen',
    'BOAT': 'boat',
    'FOUNTAIN': 'fountain',
}


# ============================================================================
# Flag Normalization Functions
# ============================================================================

def _clean_flag_name(name: str) -> str:
    """Clean up a single flag name."""
    clean_name = name.lower().strip()
    # Remove leading prefixes
    for prefix in ('is_', '_'):
        if clean_name.startswith(prefix):
            clean_name = clean_name[len(prefix):]
    # Remove trailing underscores
    clean_name = clean_name.rstrip('_')
    return clean_name


def normalize_flags(value, enum_class=None) -> List[str]:
    """
    Convert IntFlag enum or numeric value to list of lowercase flag names.

    ROM_ACT_TYPES.IS_NPC|SENTINEL -> ["npc", "sentinel"]
    """
    if value is None or value == 0:
        return []

    flags = []

    # If it's an IntFlag enum
    if isinstance(value, enum.IntFlag):
        # Get the string representation and parse it
        name = value.name
        if name:
            # name could be "IS_NPC|SENTINEL" for composite flags
            if '|' in name:
                for part in name.split('|'):
                    clean = _clean_flag_name(part)
                    if clean and clean not in flags and not clean.startswith('unused'):
                        flags.append(clean)
            else:
                # Single flag
                clean = _clean_flag_name(name)
                if clean and not clean.startswith('unused'):
                    flags.append(clean)
        else:
            # Composite flag - iterate through members
            for member in type(value):
                if member.value and (value & member.value) == member.value:
                    if member.value != 0:  # Skip NONE
                        clean = _clean_flag_name(member.name)
                        if clean and clean not in flags and not clean.startswith('unused'):
                            flags.append(clean)
    elif isinstance(value, int) and enum_class:
        # Numeric value with enum class provided
        try:
            enum_val = enum_class(value)
            return normalize_flags(enum_val)
        except ValueError:
            # Handle composite flags
            for member in enum_class:
                if member.value and (value & member.value) == member.value:
                    if member.value != 0:
                        clean = _clean_flag_name(member.name)
                        if clean and clean not in flags and not clean.startswith('unused'):
                            flags.append(clean)
    elif isinstance(value, str):
        # Already a string representation like "ROM_ACT_TYPES.IS_NPC|SENTINEL"
        # Parse the enum string
        if '.' in value:
            parts = value.split('.')[-1]  # Get after the last dot
        else:
            parts = value
        # Split by | if composite
        for part in parts.split('|'):
            name = part.strip().lower()
            for prefix in ('is_', '_'):
                if name.startswith(prefix):
                    name = name[len(prefix):]
            if name and not name.startswith('unused'):
                flags.append(name)

    return flags


def normalize_room_flags(value) -> List[str]:
    """Normalize room flags to lowercase names."""
    return normalize_flags(value)


def normalize_exit_flags(value) -> List[str]:
    """Normalize exit/door flags to lowercase names."""
    flags = []
    if isinstance(value, int):
        # Common flag bits
        if value & 1:  # ISDOOR
            flags.append('door')
        if value & 2:  # CLOSED
            flags.append('closed')
        if value & 4:  # LOCKED
            flags.append('locked')
        if value & 32:  # PICKPROOF
            flags.append('pickproof')
        if value & 64:  # NOPASS
            flags.append('nopass')
    else:
        flags = normalize_flags(value)
    return flags


def thac0_to_hitroll(thac0: int) -> int:
    """Convert CircleMUD THAC0 to ROM-style hitroll."""
    return 20 - thac0


# ============================================================================
# Converter for attrs objects to dicts
# ============================================================================

class NormalizedConverter:
    """Converter for unstructuring normalized objects to dictionaries."""

    def unstructure(self, obj):
        """Convert an object to a dictionary representation."""
        if hasattr(obj, '__attrs_attrs__'):
            result = {}
            for a in obj.__attrs_attrs__:
                val = getattr(obj, a.name)
                result[a.name] = self.unstructure(val)
            return result
        elif isinstance(obj, dict):
            return {k: self.unstructure(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.unstructure(v) for v in obj]
        elif isinstance(obj, enum.Enum):
            return obj.name
        elif isinstance(obj, enum.IntFlag):
            if obj.name:
                return obj.name
            return str(obj)
        else:
            return obj


# ============================================================================
# Original Data Converter
# ============================================================================

class OriginalConverter:
    """Converter for unstructuring original format objects to dicts."""

    def unstructure(self, obj):
        """Convert an object to dictionary, handling enums specially."""
        if hasattr(obj, '__attrs_attrs__'):
            result = {}
            for a in obj.__attrs_attrs__:
                val = getattr(obj, a.name)
                result[a.name] = self.unstructure(val)
            return result
        elif isinstance(obj, dict):
            return {k: self.unstructure(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.unstructure(v) for v in obj]
        elif isinstance(obj, enum.IntFlag):
            # Return both the string representation and numeric value
            if obj.name:
                return f"{type(obj).__name__}.{obj.name}"
            return str(obj)
        elif isinstance(obj, enum.Enum):
            return f"{type(obj).__name__}.{obj.name}"
        else:
            return obj


# ============================================================================
# Format-Specific Normalizers
# ============================================================================

class BaseMobNormalizer:
    """Base class for mob normalizers."""

    def __init__(self, converter=None):
        self.converter = converter or OriginalConverter()

    def normalize(self, mob) -> NormalizedMob:
        raise NotImplementedError


class PartialMobNormalizer(BaseMobNormalizer):
    """Normalizer for partially parsed mobs (PartialMudObject)."""

    def normalize(self, mob) -> NormalizedMob:
        name = getattr(mob, 'name', '')
        keywords = name.split() if name else []

        return NormalizedMob(
            vnum=getattr(mob, 'vnum', 0),
            keywords=keywords,
            short_desc=getattr(mob, 'short_desc', ''),
            long_desc=getattr(mob, 'long_desc', ''),
            description=getattr(mob, 'description', ''),
            level=0,
            alignment=0,
            sex='none',
            race='unknown',
            act_flags=[],
            affect_flags=[],
            hitroll=0,
            ac=NormalizedArmorClass(),
            hit_dice=NormalizedDice(),
            mana_dice=NormalizedDice(),
            damage_dice=NormalizedDice(),
            damage_type='',
            gold=0,
            position={'default': 'standing', 'load': 'standing'},
            resistances={'immune': [], 'resist': [], 'vuln': []},
            body={'form': [], 'parts': [], 'size': 'medium'},
            offense_flags=[],
            programs=[],
            original={
                'vnum': getattr(mob, 'vnum', 0),
                'name': name,
                'short_desc': getattr(mob, 'short_desc', ''),
                'long_desc': getattr(mob, 'long_desc', ''),
                'description': getattr(mob, 'description', ''),
                '_partial': True,
                '_parse_error': getattr(mob, '_parse_error', ''),
                '_object_type': getattr(mob, '_object_type', '')
            }
        )


class PartialItemNormalizer:
    """Normalizer for partially parsed items (PartialMudObject)."""

    def __init__(self, converter=None):
        self.converter = converter or OriginalConverter()

    def normalize(self, item) -> NormalizedItem:
        name = getattr(item, 'name', '')
        keywords = name.split() if name else []

        return NormalizedItem(
            vnum=getattr(item, 'vnum', 0),
            keywords=keywords,
            short_desc=getattr(item, 'short_desc', ''),
            long_desc=getattr(item, 'description', ''),  # For items, description is often the long_desc
            item_type='unknown',
            extra_flags=[],
            wear_flags=[],
            weight=0,
            cost=0,
            level=0,
            condition=100,
            material='',
            values=[],
            affects=[],
            extra_descriptions=[],
            original={
                'vnum': getattr(item, 'vnum', 0),
                'name': name,
                'short_desc': getattr(item, 'short_desc', ''),
                'long_desc': getattr(item, 'long_desc', ''),
                'description': getattr(item, 'description', ''),
                '_partial': True,
                '_parse_error': getattr(item, '_parse_error', ''),
                '_object_type': getattr(item, '_object_type', '')
            }
        )


class RomMobNormalizer(BaseMobNormalizer):
    """Normalizer for ROM format mobs."""

    def normalize(self, mob) -> NormalizedMob:
        # Parse keywords from name field
        name = getattr(mob, 'name', '')
        keywords = name.split() if name else []

        # Get position values
        start_pos = getattr(mob, 'start_pos', 'stand')
        default_pos = getattr(mob, 'default_pos', 'stand')

        # Normalize positions
        load_pos = POSITION_MAP.get(start_pos, str(start_pos).lower() if start_pos else 'standing')
        def_pos = POSITION_MAP.get(default_pos, str(default_pos).lower() if default_pos else 'standing')

        # Normalize sex
        sex_raw = getattr(mob, 'sex', 'none')
        sex = SEX_MAP.get(sex_raw, str(sex_raw).lower() if sex_raw else 'none')

        # Normalize size
        size_raw = getattr(mob, 'size', 'medium')
        size = str(size_raw).lower() if size_raw else 'medium'

        # Get dice values
        hit_dice = getattr(mob, 'hit', None)
        mana_dice = getattr(mob, 'mana', None)
        damage_dice = getattr(mob, 'damage', None)

        # Get AC (ROM has 4-value AC)
        ac_obj = getattr(mob, 'ac', None)

        # Get resistance flags
        imm_flags = normalize_flags(getattr(mob, 'imm_flags', 0))
        res_flags = normalize_flags(getattr(mob, 'res_flags', 0))
        vuln_flags = normalize_flags(getattr(mob, 'vuln_flags', 0))

        # Get body flags
        form_flags = normalize_flags(getattr(mob, 'form', 0))
        parts_flags = normalize_flags(getattr(mob, 'parts', 0))

        # Get mprogs
        mprogs = getattr(mob, 'mprogs', [])
        programs = []
        for mp in mprogs:
            programs.append(self.converter.unstructure(mp))

        return NormalizedMob(
            vnum=getattr(mob, 'vnum', 0),
            keywords=keywords,
            short_desc=getattr(mob, 'short_desc', ''),
            long_desc=getattr(mob, 'long_desc', ''),
            description=getattr(mob, 'description', ''),
            level=getattr(mob, 'level', 1),
            alignment=getattr(mob, 'alignment', 0),
            sex=sex,
            race=getattr(mob, 'race', 'human') or 'human',
            act_flags=normalize_flags(getattr(mob, 'act', 0)),
            affect_flags=normalize_flags(getattr(mob, 'affected_by', 0)),
            hitroll=getattr(mob, 'hitroll', 0),
            ac=NormalizedArmorClass.from_rom(ac_obj) if ac_obj else NormalizedArmorClass(),
            hit_dice=NormalizedDice(
                num=getattr(hit_dice, 'number', 0) if hit_dice else 0,
                size=getattr(hit_dice, 'sides', 0) if hit_dice else 0,
                bonus=getattr(hit_dice, 'bonus', 0) if hit_dice else 0
            ),
            mana_dice=NormalizedDice(
                num=getattr(mana_dice, 'number', 0) if mana_dice else 0,
                size=getattr(mana_dice, 'sides', 0) if mana_dice else 0,
                bonus=getattr(mana_dice, 'bonus', 0) if mana_dice else 0
            ),
            damage_dice=NormalizedDice(
                num=getattr(damage_dice, 'number', 0) if damage_dice else 0,
                size=getattr(damage_dice, 'sides', 0) if damage_dice else 0,
                bonus=getattr(damage_dice, 'bonus', 0) if damage_dice else 0
            ),
            damage_type=getattr(mob, 'damtype', ''),
            gold=getattr(mob, 'wealth', 0),
            position={'default': def_pos, 'load': load_pos},
            resistances={'immune': imm_flags, 'resist': res_flags, 'vuln': vuln_flags},
            body={'form': form_flags, 'parts': parts_flags, 'size': size},
            offense_flags=normalize_flags(getattr(mob, 'off_flags', 0)),
            programs=programs,
            original=self.converter.unstructure(mob)
        )


class MercMobNormalizer(BaseMobNormalizer):
    """Normalizer for Merc format mobs."""

    def normalize(self, mob) -> NormalizedMob:
        name = getattr(mob, 'name', '')
        keywords = name.split() if name else []

        # Merc uses numeric positions
        start_pos = getattr(mob, 'start_pos', 8)
        default_pos = getattr(mob, 'default_pos', 8)
        load_pos = POSITION_MAP.get(start_pos, 'standing')
        def_pos = POSITION_MAP.get(default_pos, 'standing')

        # Merc uses numeric sex
        sex_raw = getattr(mob, 'sex', 0)
        sex = SEX_MAP.get(sex_raw, 'none')

        # Merc has single-value AC
        ac_val = getattr(mob, 'ac', 0)

        # Get dice
        hit_dice = getattr(mob, 'hit', None)
        damage_dice = getattr(mob, 'damage', None)

        return NormalizedMob(
            vnum=getattr(mob, 'vnum', 0),
            keywords=keywords,
            short_desc=getattr(mob, 'short_desc', ''),
            long_desc=getattr(mob, 'long_desc', ''),
            description=getattr(mob, 'description', ''),
            level=getattr(mob, 'level', 1),
            alignment=getattr(mob, 'alignment', 0),
            sex=sex,
            race='human',  # Merc doesn't have race
            act_flags=normalize_flags(getattr(mob, 'act', 0)),
            affect_flags=normalize_flags(getattr(mob, 'affected_by', 0)),
            hitroll=getattr(mob, 'hitroll', 0),
            ac=NormalizedArmorClass.from_single(ac_val),
            hit_dice=NormalizedDice(
                num=getattr(hit_dice, 'number', 0) if hit_dice else 0,
                size=getattr(hit_dice, 'sides', 0) if hit_dice else 0,
                bonus=getattr(hit_dice, 'bonus', 0) if hit_dice else 0
            ),
            mana_dice=NormalizedDice(),  # Merc doesn't have mana dice
            damage_dice=NormalizedDice(
                num=getattr(damage_dice, 'number', 0) if damage_dice else 0,
                size=getattr(damage_dice, 'sides', 0) if damage_dice else 0,
                bonus=getattr(damage_dice, 'bonus', 0) if damage_dice else 0
            ),
            damage_type='',
            gold=getattr(mob, 'wealth', 0),
            position={'default': def_pos, 'load': load_pos},
            resistances={'immune': [], 'resist': [], 'vuln': []},
            body={'form': [], 'parts': [], 'size': 'medium'},
            offense_flags=[],
            programs=[],
            original=self.converter.unstructure(mob)
        )


class CircleMudMobNormalizer(BaseMobNormalizer):
    """Normalizer for CircleMUD format mobs."""

    def normalize(self, mob) -> NormalizedMob:
        aliases = getattr(mob, 'aliases', [])
        keywords = aliases if isinstance(aliases, list) else aliases.split() if aliases else []

        # CircleMUD uses numeric positions
        load_pos = POSITION_MAP.get(getattr(mob, 'load_position', 8), 'standing')
        def_pos = POSITION_MAP.get(getattr(mob, 'default_position', 8), 'standing')

        # CircleMUD uses numeric sex
        sex_raw = getattr(mob, 'sex', 0)
        sex = SEX_MAP.get(sex_raw, 'none')

        # CircleMUD uses THAC0 instead of hitroll
        thac0 = getattr(mob, 'thac0', 20)
        hitroll = thac0_to_hitroll(thac0)

        # Single AC value
        ac_val = getattr(mob, 'ac', 10)

        # Get dice (CircleMUD uses dicts)
        hit_dice = getattr(mob, 'hit_dice', {})
        damage_dice = getattr(mob, 'damage_dice', {})

        return NormalizedMob(
            vnum=int(getattr(mob, 'vnum', 0)) if getattr(mob, 'vnum', 0) else 0,
            keywords=keywords,
            short_desc=getattr(mob, 'short_desc', ''),
            long_desc=getattr(mob, 'long_desc', ''),
            description=getattr(mob, 'description', ''),
            level=getattr(mob, 'level', 1),
            alignment=getattr(mob, 'alignment', 0),
            sex=sex,
            race='human',  # CircleMUD doesn't have race in base format
            act_flags=self._normalize_circle_flags(getattr(mob, 'action_flags', 0)),
            affect_flags=self._normalize_circle_flags(getattr(mob, 'affect_flags', 0)),
            hitroll=hitroll,
            ac=NormalizedArmorClass.from_single(ac_val),
            hit_dice=NormalizedDice.from_dict(hit_dice),
            mana_dice=NormalizedDice(),
            damage_dice=NormalizedDice.from_dict(damage_dice),
            damage_type='',
            gold=getattr(mob, 'gold', 0),
            position={'default': def_pos, 'load': load_pos},
            resistances={'immune': [], 'resist': [], 'vuln': []},
            body={'form': [], 'parts': [], 'size': 'medium'},
            offense_flags=[],
            programs=[],
            original=self.converter.unstructure(mob)
        )

    def _normalize_circle_flags(self, value) -> List[str]:
        """Normalize CircleMUD bitvector flags."""
        if not value:
            return []

        # CircleMUD flag mappings
        from circlemud import MOB_ACTION_FLAGS, MOB_AFFECT_FLAGS

        flags = []
        for bit, name in MOB_ACTION_FLAGS.items():
            if value & bit:
                flags.append(name.lower())
        return flags


class BaseItemNormalizer:
    """Base class for item normalizers."""

    def __init__(self, converter=None):
        self.converter = converter or OriginalConverter()

    def normalize(self, item) -> NormalizedItem:
        raise NotImplementedError


class RomItemNormalizer(BaseItemNormalizer):
    """Normalizer for ROM format items."""

    def normalize(self, item) -> NormalizedItem:
        name = getattr(item, 'name', '')
        keywords = name.split() if name else []

        # Normalize item type (ROM uses strings)
        item_type = getattr(item, 'item_type', '')
        if isinstance(item_type, str):
            item_type_norm = item_type.lower()
        else:
            item_type_norm = ITEM_TYPE_MAP.get(item_type, str(item_type))

        # Get extra descriptions
        extra_descs = []
        for ed in getattr(item, 'extra_descriptions', []):
            extra_descs.append({
                'keywords': getattr(ed, 'keyword', '').split() if hasattr(ed, 'keyword') else [],
                'description': getattr(ed, 'description', '')
            })

        # Get affects
        affects = []
        for af in getattr(item, 'affected', []):
            affects.append(self.converter.unstructure(af))

        return NormalizedItem(
            vnum=getattr(item, 'vnum', 0),
            keywords=keywords,
            short_desc=getattr(item, 'short_desc', ''),
            long_desc=getattr(item, 'description', ''),
            item_type=item_type_norm,
            extra_flags=normalize_flags(getattr(item, 'extra_flags', 0)),
            wear_flags=normalize_flags(getattr(item, 'wear_flags', 0)),
            weight=getattr(item, 'weight', 0),
            cost=getattr(item, 'cost', 0),
            level=getattr(item, 'level', 0),
            condition=getattr(item, 'condition', 100),
            material=getattr(item, 'material', ''),
            values=list(getattr(item, 'value', [])),
            affects=affects,
            extra_descriptions=extra_descs,
            original=self.converter.unstructure(item)
        )


class MercItemNormalizer(BaseItemNormalizer):
    """Normalizer for Merc format items."""

    def normalize(self, item) -> NormalizedItem:
        name = getattr(item, 'name', '')
        keywords = name.split() if name else []

        # Merc uses numeric item types
        item_type = getattr(item, 'item_type', 0)
        item_type_norm = ITEM_TYPE_MAP.get(item_type, str(item_type))

        # Get extra descriptions
        extra_descs = []
        for ed in getattr(item, 'extra_descriptions', []):
            extra_descs.append({
                'keywords': getattr(ed, 'keyword', '').split() if hasattr(ed, 'keyword') else [],
                'description': getattr(ed, 'description', '')
            })

        # Get affects
        affects = []
        for af in getattr(item, 'affected', []):
            affects.append(self.converter.unstructure(af))

        return NormalizedItem(
            vnum=getattr(item, 'vnum', 0),
            keywords=keywords,
            short_desc=getattr(item, 'short_desc', ''),
            long_desc=getattr(item, 'description', ''),
            item_type=item_type_norm,
            extra_flags=normalize_flags(getattr(item, 'extra_flags', 0)),
            wear_flags=normalize_flags(getattr(item, 'wear_flags', 0)),
            weight=getattr(item, 'weight', 0),
            cost=getattr(item, 'cost', 0),
            level=getattr(item, 'level', 0),
            condition=100,  # Merc doesn't have condition
            material='',  # Merc doesn't have material
            values=list(getattr(item, 'value', [])),
            affects=affects,
            extra_descriptions=extra_descs,
            original=self.converter.unstructure(item)
        )


class CircleMudItemNormalizer(BaseItemNormalizer):
    """Normalizer for CircleMUD format items."""

    def normalize(self, item) -> NormalizedItem:
        aliases = getattr(item, 'aliases', [])
        keywords = aliases if isinstance(aliases, list) else aliases.split() if aliases else []

        # CircleMUD uses numeric item types
        item_type = getattr(item, 'item_type', 0)
        # Map CircleMUD item types
        from circlemud import ITEM_TYPES
        item_type_norm = ITEM_TYPES.get(item_type, str(item_type)).lower()

        # Get extra descriptions
        extra_descs = []
        for ed in getattr(item, 'extra_descriptions', []):
            extra_descs.append({
                'keywords': getattr(ed, 'keywords', []),
                'description': getattr(ed, 'description', '')
            })

        # Get affects
        affects = list(getattr(item, 'affects', []))

        return NormalizedItem(
            vnum=int(getattr(item, 'vnum', 0)) if getattr(item, 'vnum', 0) else 0,
            keywords=keywords,
            short_desc=getattr(item, 'short_desc', ''),
            long_desc=getattr(item, 'long_desc', ''),
            item_type=item_type_norm,
            extra_flags=self._normalize_circle_flags(getattr(item, 'extra_flags', 0)),
            wear_flags=self._normalize_circle_flags(getattr(item, 'wear_flags', 0)),
            weight=getattr(item, 'weight', 0),
            cost=getattr(item, 'cost', 0),
            level=0,  # CircleMUD doesn't have item level in base format
            condition=100,
            material='',
            values=list(getattr(item, 'values', [])),
            affects=affects,
            extra_descriptions=extra_descs,
            original=self.converter.unstructure(item)
        )

    def _normalize_circle_flags(self, value) -> List[str]:
        """Normalize CircleMUD bitvector flags to list of names."""
        if not value:
            return []

        from circlemud import EXTRA_FLAGS, WEAR_FLAGS

        flags = []
        # Try both flag dicts
        for flag_dict in [EXTRA_FLAGS, WEAR_FLAGS]:
            for bit, name in flag_dict.items():
                if value & bit:
                    if name.lower() not in flags:
                        flags.append(name.lower())
        return flags


class BaseRoomNormalizer:
    """Base class for room normalizers."""

    def __init__(self, converter=None):
        self.converter = converter or OriginalConverter()

    def normalize(self, room) -> NormalizedRoom:
        raise NotImplementedError


class RomRoomNormalizer(BaseRoomNormalizer):
    """Normalizer for ROM format rooms."""

    def normalize(self, room) -> NormalizedRoom:
        # Normalize exits
        exits = []
        for ex in getattr(room, 'exits', []):
            direction = getattr(ex, 'door', 0)
            if hasattr(direction, 'value'):
                direction = direction.value
            dir_name = DIRECTION_MAP.get(direction, str(direction))

            exits.append(NormalizedExit(
                direction=dir_name,
                destination=getattr(ex, 'destination', -1),
                description=getattr(ex, 'description', ''),
                keywords=getattr(ex, 'keyword', '').split() if getattr(ex, 'keyword', '') else [],
                flags=normalize_exit_flags(getattr(ex, 'exit_info', 0)),
                key_vnum=getattr(ex, 'key', -1)
            ))

        # Normalize sector type
        sector = getattr(room, 'sector_type', 0)
        if hasattr(sector, 'value'):
            sector = sector.value
        if hasattr(sector, 'name'):
            sector_name = sector.name.lower()
        else:
            sector_name = SECTOR_MAP.get(sector, str(sector))

        # Get extra descriptions
        extra_descs = []
        for ed in getattr(room, 'extra_descriptions', []):
            extra_descs.append({
                'keywords': getattr(ed, 'keyword', '').split() if hasattr(ed, 'keyword') else [],
                'description': getattr(ed, 'description', '')
            })

        return NormalizedRoom(
            vnum=getattr(room, 'vnum', 0),
            name=getattr(room, 'name', ''),
            description=getattr(room, 'description', ''),
            room_flags=normalize_room_flags(getattr(room, 'room_flags', 0)),
            sector_type=sector_name,
            exits=[self.converter.unstructure(e) for e in exits],
            extra_descriptions=extra_descs,
            heal_rate=getattr(room, 'heal_rate', 100),
            mana_rate=getattr(room, 'mana_rate', 100),
            original=self.converter.unstructure(room)
        )


class CircleMudRoomNormalizer(BaseRoomNormalizer):
    """Normalizer for CircleMUD format rooms."""

    def normalize(self, room) -> NormalizedRoom:
        # Normalize exits
        exits = []
        for ex in getattr(room, 'exits', []):
            direction = getattr(ex, 'direction', 0)
            dir_name = DIRECTION_MAP.get(direction, str(direction))

            exits.append(NormalizedExit(
                direction=dir_name,
                destination=int(getattr(ex, 'destination', -1)) if getattr(ex, 'destination', -1) != '' else -1,
                description=getattr(ex, 'description', ''),
                keywords=getattr(ex, 'keywords', []),
                flags=normalize_exit_flags(getattr(ex, 'door_flags', 0)),
                key_vnum=int(getattr(ex, 'key_vnum', -1)) if getattr(ex, 'key_vnum', -1) != '' else -1
            ))

        # Normalize sector type
        sector = getattr(room, 'sector_type', 0)
        sector_name = SECTOR_MAP.get(sector, str(sector))

        # Normalize room flags
        from circlemud import ROOM_FLAGS
        flags = []
        room_flags_val = getattr(room, 'room_flags', 0)
        for bit, name in ROOM_FLAGS.items():
            if room_flags_val & bit:
                flags.append(name.lower())

        # Get extra descriptions
        extra_descs = []
        for ed in getattr(room, 'extra_descriptions', []):
            extra_descs.append({
                'keywords': getattr(ed, 'keywords', []),
                'description': getattr(ed, 'description', '')
            })

        return NormalizedRoom(
            vnum=int(getattr(room, 'vnum', 0)) if getattr(room, 'vnum', 0) else 0,
            name=getattr(room, 'name', ''),
            description=getattr(room, 'description', ''),
            room_flags=flags,
            sector_type=sector_name,
            exits=[self.converter.unstructure(e) for e in exits],
            extra_descriptions=extra_descs,
            heal_rate=100,
            mana_rate=100,
            original=self.converter.unstructure(room)
        )


# ============================================================================
# Main Normalizer
# ============================================================================

class AreaNormalizer:
    """Main normalizer that converts an area file to normalized format."""

    def __init__(self, area_file):
        self.area_file = area_file
        self.format = self._detect_format()
        self.converter = OriginalConverter()

        # Select appropriate normalizers based on format
        self._setup_normalizers()

    def _detect_format(self) -> str:
        """Detect the format of the area file."""
        class_name = type(self.area_file).__name__

        if 'CircleMud' in class_name:
            return 'circlemud'
        elif 'Merc' in class_name:
            return 'merc'
        elif 'Smaug' in class_name:
            return 'smaug'
        elif 'Rot' in class_name:
            return 'rot'
        elif 'Envy' in class_name:
            return 'envy'
        else:
            return 'rom'

    def _setup_normalizers(self):
        """Set up the appropriate normalizers for the detected format."""
        if self.format == 'circlemud':
            self.mob_normalizer = CircleMudMobNormalizer(self.converter)
            self.item_normalizer = CircleMudItemNormalizer(self.converter)
            self.room_normalizer = CircleMudRoomNormalizer(self.converter)
        elif self.format == 'merc':
            self.mob_normalizer = MercMobNormalizer(self.converter)
            self.item_normalizer = MercItemNormalizer(self.converter)
            self.room_normalizer = RomRoomNormalizer(self.converter)  # Merc rooms are similar to ROM
        else:
            # ROM, SMAUG, ROT, Envy all use similar structures
            self.mob_normalizer = RomMobNormalizer(self.converter)
            self.item_normalizer = RomItemNormalizer(self.converter)
            self.room_normalizer = RomRoomNormalizer(self.converter)

    def normalize(self) -> NormalizedArea:
        """Convert the area file to normalized format."""
        area = self.area_file.area

        # Extract metadata
        name = getattr(area, 'name', '')
        builders = getattr(area, 'metadata', '')

        # Get vnum range
        first_vnum = getattr(area, 'first_vnum', 0)
        last_vnum = getattr(area, 'last_vnum', 0)
        if first_vnum == -1:
            first_vnum = 0
        if last_vnum == -1:
            last_vnum = 0

        # Normalize mobs
        mobs = {}
        area_mobs = getattr(area, 'mobs', {})
        partial_mob_normalizer = PartialMobNormalizer(self.converter)
        for vnum, mob in area_mobs.items():
            try:
                # Check if this is a partially parsed object
                if getattr(mob, '_partial', False):
                    mobs[int(vnum)] = partial_mob_normalizer.normalize(mob)
                else:
                    mobs[int(vnum)] = self.mob_normalizer.normalize(mob)
            except Exception as e:
                # Log but continue
                pass

        # Normalize objects
        objects = {}
        area_objects = getattr(area, 'objects', {})
        partial_item_normalizer = PartialItemNormalizer(self.converter)
        for vnum, obj in area_objects.items():
            try:
                # Check if this is a partially parsed object
                if getattr(obj, '_partial', False):
                    objects[int(vnum)] = partial_item_normalizer.normalize(obj)
                else:
                    objects[int(vnum)] = self.item_normalizer.normalize(obj)
            except Exception as e:
                pass

        # Normalize rooms
        rooms = {}
        area_rooms = getattr(area, 'rooms', {})
        for vnum, room in area_rooms.items():
            try:
                rooms[int(vnum)] = self.room_normalizer.normalize(room)
            except Exception as e:
                pass

        # Convert resets, shops, specials, helps
        resets = [self.converter.unstructure(r) for r in getattr(area, 'resets', [])]
        shops = [self.converter.unstructure(s) for s in getattr(area, 'shops', [])]
        specials = [self.converter.unstructure(s) for s in getattr(area, 'specials', [])]
        helps = [self.converter.unstructure(h) for h in getattr(area, 'helps', [])]

        # Get source file
        source_file = getattr(self.area_file, 'filename', '')
        if not source_file:
            source_file = getattr(self.area_file, 'directory', '')

        return NormalizedArea(
            name=name,
            builders=builders,
            level_range=[0, 0],  # Not always available
            vnum_range=[first_vnum, last_vnum],
            mobs=mobs,
            objects=objects,
            rooms=rooms,
            resets=resets,
            shops=shops,
            specials=specials,
            helps=helps,
            meta={
                'source_format': self.format,
                'source_file': source_file
            }
        )
