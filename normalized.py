"""
Normalized data classes for unified MUD area representation.

These classes provide a common schema across ROM, Merc, CircleMUD, and SMAUG formats,
while preserving the original data in the _original field for lossless round-trip.
"""

from typing import List, Dict, Optional, Any
from attr import attr, attrs, Factory


@attrs
class NormalizedDice:
    """Normalized dice representation (NdS+B)."""
    num: int = attr(default=0)
    size: int = attr(default=0)
    bonus: int = attr(default=0)

    @classmethod
    def from_dict(cls, d):
        """Create from dict with number/sides/bonus or num/size/bonus."""
        if not d:
            return cls()
        return cls(
            num=d.get('num', d.get('number', 0)),
            size=d.get('size', d.get('sides', 0)),
            bonus=d.get('bonus', 0)
        )


@attrs
class NormalizedArmorClass:
    """Normalized 4-value armor class (ROM style)."""
    pierce: int = attr(default=0)
    bash: int = attr(default=0)
    slash: int = attr(default=0)
    exotic: int = attr(default=0)

    @classmethod
    def from_single(cls, ac_value):
        """Create from a single AC value (Merc/Circle style)."""
        return cls(pierce=ac_value, bash=ac_value, slash=ac_value, exotic=ac_value)

    @classmethod
    def from_rom(cls, ac_obj):
        """Create from ROM's RomArmorClass object."""
        if hasattr(ac_obj, 'pierce'):
            return cls(
                pierce=ac_obj.pierce,
                bash=ac_obj.bash,
                slash=ac_obj.slash,
                exotic=ac_obj.exotic
            )
        # If it's a dict
        if isinstance(ac_obj, dict):
            return cls(
                pierce=ac_obj.get('pierce', 0),
                bash=ac_obj.get('bash', 0),
                slash=ac_obj.get('slash', 0),
                exotic=ac_obj.get('exotic', 0)
            )
        # Single value
        if isinstance(ac_obj, (int, float)):
            return cls.from_single(int(ac_obj))
        return cls()


@attrs
class NormalizedMob:
    """Normalized mobile/NPC representation."""
    vnum: int = attr(default=0)
    keywords: List[str] = attr(factory=list)
    short_desc: str = attr(default='')
    long_desc: str = attr(default='')
    description: str = attr(default='')
    level: int = attr(default=1)
    alignment: int = attr(default=0)
    sex: str = attr(default='none')  # "none"/"male"/"female"
    race: str = attr(default='human')
    act_flags: List[str] = attr(factory=list)  # lowercase, no prefix
    affect_flags: List[str] = attr(factory=list)
    hitroll: int = attr(default=0)
    ac: NormalizedArmorClass = attr(factory=NormalizedArmorClass)
    hit_dice: NormalizedDice = attr(factory=NormalizedDice)
    mana_dice: NormalizedDice = attr(factory=NormalizedDice)
    damage_dice: NormalizedDice = attr(factory=NormalizedDice)
    damage_type: str = attr(default='')
    gold: int = attr(default=0)
    position: Dict[str, str] = attr(factory=lambda: {'default': 'standing', 'load': 'standing'})
    resistances: Dict[str, List[str]] = attr(factory=lambda: {'immune': [], 'resist': [], 'vuln': []})
    body: Dict[str, Any] = attr(factory=lambda: {'form': [], 'parts': [], 'size': 'medium'})
    offense_flags: List[str] = attr(factory=list)
    programs: List[Dict] = attr(factory=list)  # mprogs
    original: Dict = attr(factory=dict)  # original format-specific data


@attrs
class NormalizedItem:
    """Normalized object/item representation."""
    vnum: int = attr(default=0)
    keywords: List[str] = attr(factory=list)
    short_desc: str = attr(default='')
    long_desc: str = attr(default='')
    item_type: str = attr(default='')  # normalized string
    extra_flags: List[str] = attr(factory=list)
    wear_flags: List[str] = attr(factory=list)
    weight: int = attr(default=0)
    cost: int = attr(default=0)
    level: int = attr(default=0)
    condition: int = attr(default=100)
    material: str = attr(default='')
    values: List[Any] = attr(factory=list)
    affects: List[Dict] = attr(factory=list)
    extra_descriptions: List[Dict] = attr(factory=list)
    original: Dict = attr(factory=dict)  # original format-specific data


@attrs
class NormalizedExit:
    """Normalized room exit."""
    direction: str = attr(default='')  # "north", "east", etc.
    destination: int = attr(default=-1)
    description: str = attr(default='')
    keywords: List[str] = attr(factory=list)
    flags: List[str] = attr(factory=list)  # "door", "locked", "pickproof", etc.
    key_vnum: int = attr(default=-1)


@attrs
class NormalizedRoom:
    """Normalized room representation."""
    vnum: int = attr(default=0)
    name: str = attr(default='')
    description: str = attr(default='')
    room_flags: List[str] = attr(factory=list)
    sector_type: str = attr(default='inside')
    exits: List[NormalizedExit] = attr(factory=list)
    extra_descriptions: List[Dict] = attr(factory=list)
    heal_rate: int = attr(default=100)
    mana_rate: int = attr(default=100)
    original: Dict = attr(factory=dict)  # original format-specific data


@attrs
class NormalizedArea:
    """Normalized area container."""
    name: str = attr(default='')
    builders: str = attr(default='')
    level_range: List[int] = attr(factory=lambda: [0, 0])
    vnum_range: List[int] = attr(factory=lambda: [0, 0])
    mobs: Dict[int, NormalizedMob] = attr(factory=dict)
    objects: Dict[int, NormalizedItem] = attr(factory=dict)
    rooms: Dict[int, NormalizedRoom] = attr(factory=dict)
    resets: List[Dict] = attr(factory=list)
    shops: List[Dict] = attr(factory=list)
    specials: List[Dict] = attr(factory=list)
    helps: List[Dict] = attr(factory=list)
    meta: Dict = attr(factory=lambda: {'source_format': '', 'source_file': ''})
