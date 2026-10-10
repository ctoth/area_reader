"""ROM 2.4b6 name tables for the area source format.

Every table here is copied from the ROM 2.4b6 distribution (``src/`` and ``doc/``); the comment on each names
the file. ``RACES`` and ``SKILLS`` are the output of ``scripts/extract_rom_tables.py``.
"""

from attr import attr, attributes

from area_reader.constants import ROM_LIQUIDS, flag_convert


def bits(letters):
    """Return the value of a ROM flag-letter string such as ``ABd``."""
    return sum(flag_convert(letter) for letter in letters)


def flag_table(**names):
    return {name: bits(letter) for name, letter in names.items()}


# src/tables.c act_flags. "npc" is always set by the reader and the engine.
ACT_FLAGS = flag_table(
    npc="A",
    sentinel="B",
    scavenger="C",
    aggressive="F",
    stay_area="G",
    wimpy="H",
    pet="I",
    train="J",
    practice="K",
    undead="O",
    cleric="Q",
    mage="R",
    thief="S",
    warrior="T",
    noalign="U",
    nopurge="V",
    outdoors="W",
    indoors="Y",
    healer="a",
    gain="b",
    update_always="c",
    changer="d",
)

# src/tables.c affect_flags.
AFFECT_FLAGS = flag_table(
    blind="A",
    invisible="B",
    detect_evil="C",
    detect_invis="D",
    detect_magic="E",
    detect_hidden="F",
    detect_good="G",
    sanctuary="H",
    faerie_fire="I",
    infrared="J",
    curse="K",
    poison="M",
    protect_evil="N",
    protect_good="O",
    sneak="P",
    hide="Q",
    sleep="R",
    charm="S",
    flying="T",
    pass_door="U",
    haste="V",
    calm="W",
    plague="X",
    weaken="Y",
    dark_vision="Z",
    berserk="a",
    swim="b",
    regeneration="c",
    slow="d",
)

# src/tables.c off_flags.
OFF_FLAGS = flag_table(
    area_attack="A",
    backstab="B",
    bash="C",
    berserk="D",
    disarm="E",
    dodge="F",
    fade="G",
    fast="H",
    kick="I",
    dirt_kick="J",
    parry="K",
    rescue="L",
    tail="M",
    trip="N",
    crush="O",
    assist_all="P",
    assist_align="Q",
    assist_race="R",
    assist_players="S",
    assist_guard="T",
    assist_vnum="U",
)

# src/tables.c imm_flags; the same bits serve immunity, resistance and vulnerability.
IMM_FLAGS = flag_table(
    summon="A",
    charm="B",
    magic="C",
    weapon="D",
    bash="E",
    pierce="F",
    slash="G",
    fire="H",
    cold="I",
    lightning="J",
    acid="K",
    poison="L",
    negative="M",
    holy="N",
    energy="O",
    mental="P",
    disease="Q",
    drowning="R",
    light="S",
    sound="T",
    wood="X",
    silver="Y",
    iron="Z",
)

# src/tables.c form_flags, with the FORM_* letters of src/merc.h.
FORM_FLAGS = flag_table(
    edible="A",
    poison="B",
    magical="C",
    instant_decay="D",
    other="E",
    animal="G",
    sentient="H",
    undead="I",
    construct="J",
    mist="K",
    intangible="L",
    biped="M",
    centaur="N",
    insect="O",
    spider="P",
    crustacean="Q",
    worm="R",
    blob="S",
    mammal="V",
    bird="W",
    reptile="X",
    snake="Y",
    dragon="Z",
    amphibian="a",
    fish="b",
    cold_blood="c",
)

# src/tables.c part_flags, with the PART_* letters of src/merc.h.
PART_FLAGS = flag_table(
    head="A",
    arms="B",
    legs="C",
    heart="D",
    brains="E",
    guts="F",
    hands="G",
    feet="H",
    fingers="I",
    ear="J",
    eye="K",
    long_tongue="L",
    eyestalks="M",
    tentacles="N",
    fins="O",
    wings="P",
    tail="Q",
    claws="U",
    fangs="V",
    horns="W",
    scales="X",
    tusks="Y",
)

# src/merc.h ROOM_*.
ROOM_FLAGS = flag_table(
    dark="A",
    no_mob="C",
    indoors="D",
    private="J",
    safe="K",
    solitary="L",
    pet_shop="M",
    no_recall="N",
    imp_only="O",
    gods_only="P",
    heroes_only="Q",
    newbies_only="R",
    law="S",
    nowhere="T",
)

# src/merc.h ITEM_* extra flags.
EXTRA_FLAGS = flag_table(
    glow="A",
    hum="B",
    dark="C",
    lock="D",
    evil="E",
    invis="F",
    magic="G",
    nodrop="H",
    bless="I",
    anti_good="J",
    anti_evil="K",
    anti_neutral="L",
    noremove="M",
    inventory="N",
    nopurge="O",
    rot_death="P",
    vis_death="Q",
    nonmetal="S",
    nolocate="T",
    melt_drop="U",
    had_timer="V",
    sell_extract="W",
    burn_proof="Y",
    nouncurse="Z",
)

# src/merc.h ITEM_TAKE .. ITEM_WEAR_FLOAT.
WEAR_FLAGS = flag_table(
    take="A",
    finger="B",
    neck="C",
    body="D",
    head="E",
    legs="F",
    feet="G",
    hands="H",
    arms="I",
    shield="J",
    about="K",
    waist="L",
    wrist="M",
    wield="N",
    hold="O",
    no_sac="P",
    float="Q",
)

# src/merc.h WEAPON_FLAMING .. WEAPON_POISON.
WEAPON_FLAGS = flag_table(
    flaming="A",
    frost="B",
    vampiric="C",
    sharp="D",
    vorpal="E",
    two_hands="F",
    shocking="G",
    poison="H",
)

# src/merc.h CONT_*: 1, 2, 4, 8, 16.
CONTAINER_FLAGS = flag_table(closeable="A", pickproof="B", closed="C", locked="D", put_on="E")

# src/merc.h EX_*: a portal's value[1].
EXIT_FLAGS = flag_table(
    isdoor="A",
    closed="B",
    locked="C",
    pickproof="F",
    nopass="G",
    easy="H",
    hard="I",
    infuriating="J",
    noclose="K",
    nolock="L",
)

# src/merc.h GATE_*: a portal's value[2].
GATE_FLAGS = flag_table(normal_exit="A", nocurse="B", gowith="C", buggy="D", random="E")

# src/merc.h STAND_AT .. PUT_INSIDE: furniture's value[2].
FURNITURE_FLAGS = flag_table(
    stand_at="A",
    stand_on="B",
    stand_in="C",
    sit_at="D",
    sit_on="E",
    sit_in="F",
    rest_at="G",
    rest_on="H",
    rest_in="I",
    sleep_at="J",
    sleep_on="K",
    sleep_in="L",
    put_at="M",
    put_on="N",
    put_in="O",
    put_inside="P",
)

# Names the reader's enums use for the same bits are accepted as well as ROM's own. They come after ROM's
# in each table, so a bit's first name is the one ROM uses.
ACT_FLAGS.update(flag_table(is_npc="A", is_healer="a", is_changer="d"))
AFFECT_FLAGS.update(flag_table(evil="C", invis="D", magic="E", hidden="F", good="G", fire="I"))
OFF_FLAGS.update(flag_table(kick_dirt="J"))
WEAR_FLAGS.update(flag_table(sac="P"))
WEAPON_FLAGS.update(flag_table(hands="F"))

# src/const.c item_table names with the ITEM_* numbers of src/merc.h (a shop's buy types are these numbers).
ITEM_TYPES = {
    "light": 1,
    "scroll": 2,
    "wand": 3,
    "staff": 4,
    "weapon": 5,
    "treasure": 8,
    "armor": 9,
    "potion": 10,
    "clothing": 11,
    "furniture": 12,
    "trash": 13,
    "container": 15,
    "drink": 17,
    "key": 18,
    "food": 19,
    "money": 20,
    "boat": 22,
    "npc_corpse": 23,
    "pc_corpse": 24,
    "fountain": 25,
    "pill": 26,
    "protect": 27,
    "map": 28,
    "portal": 29,
    "warp_stone": 30,
    "room_key": 31,
    "gem": 32,
    "jewelry": 33,
    "jukebox": 34,
}

# src/const.c weapon_table names; src/handler.c weapon_type() reads any other word as exotic.
# "staff" is the table's name for WEAPON_SPEAR, and "spear" is not in the table.
WEAPON_CLASSES = ("exotic", "sword", "mace", "dagger", "axe", "staff", "flail", "whip", "polearm")

# src/const.c attack_table names.
ATTACKS = (
    "none",
    "slice",
    "stab",
    "slash",
    "whip",
    "claw",
    "blast",
    "pound",
    "crush",
    "grep",
    "bite",
    "pierce",
    "suction",
    "beating",
    "digestion",
    "charge",
    "slap",
    "punch",
    "wrath",
    "magic",
    "divine",
    "cleave",
    "scratch",
    "peck",
    "peckb",
    "chop",
    "sting",
    "smash",
    "shbite",
    "flbite",
    "frbite",
    "acbite",
    "chomp",
    "drain",
    "thrust",
    "slime",
    "shock",
    "thwack",
    "flame",
    "chill",
)

# src/const.c liq_table, already kept by the reader.
LIQUIDS = tuple(ROM_LIQUIDS)

# src/merc.h APPLY_*. APPLY_SAVING_PARA shares 20 with APPLY_SAVES.
APPLIES = {
    "none": 0,
    "str": 1,
    "dex": 2,
    "int": 3,
    "wis": 4,
    "con": 5,
    "sex": 6,
    "class": 7,
    "level": 8,
    "age": 9,
    "height": 10,
    "weight": 11,
    "mana": 12,
    "hit": 13,
    "move": 14,
    "gold": 15,
    "exp": 16,
    "ac": 17,
    "hitroll": 18,
    "damroll": 19,
    "saves": 20,
    "saving_rod": 21,
    "saving_petri": 22,
    "saving_breath": 23,
    "saving_spell": 24,
    "spell_affect": 25,
}
APPLY_ALIASES = {"saving_para": "saves"}

# src/merc.h TO_AFFECTS, TO_IMMUNE, TO_RESIST, TO_VULN as the reader names them, with the flag table each sets.
AFFECT_TARGETS = {
    "affects": ("TO_AFFECTS", AFFECT_FLAGS),
    "immune": ("TO_IMMUNE", IMM_FLAGS),
    "resist": ("TO_RESIST", IMM_FLAGS),
    "vulnerable": ("TO_VULN", IMM_FLAGS),
}

# src/tables.c position_table short names; position_lookup() matches a prefix of the long name.
POSITIONS = ("dead", "mort", "incap", "stun", "sleep", "rest", "sit", "fight", "stand")

# src/tables.c sex_table.
SEXES = ("none", "male", "female", "either")

# src/tables.c size_table.
SIZES = ("tiny", "small", "medium", "large", "huge", "giant")

# src/merc.h WEAR_LIGHT .. WEAR_FLOAT: the third argument of an E reset.
WEAR_LOCATIONS = {
    "light": 0,
    "finger_l": 1,
    "finger_r": 2,
    "neck_1": 3,
    "neck_2": 4,
    "body": 5,
    "head": 6,
    "legs": 7,
    "feet": 8,
    "hands": 9,
    "arms": 10,
    "shield": 11,
    "about": 12,
    "waist": 13,
    "wrist_l": 14,
    "wrist_r": 15,
    "wield": 16,
    "hold": 17,
    "float": 18,
}

# src/merc.h DIR_* and rev_dir in src/act_move.c.
DIRECTIONS = ("north", "east", "south", "west", "up", "down")
REVERSE = (2, 3, 0, 1, 5, 4)

# src/merc.h SECT_*.
SECTORS = {
    "inside": 0,
    "city": 1,
    "field": 2,
    "forest": 3,
    "hills": 4,
    "mountain": 5,
    "water_swim": 6,
    "water_noswim": 7,
    "unused": 8,
    "air": 9,
    "desert": 10,
}

# src/db2.c load_objects: the seven condition letters.
CONDITIONS = (100, 90, 75, 50, 25, 10, 0)

# Mob program trigger words. Stock ROM 2.4b6 has no mob programs; this is src/tables.c mprog_flags of
# QuickMUD (ROM 2.4b6 with OLC and MOBprograms), https://github.com/avinson/rom24-quickmud at commit
# 364c26f1b124e238156e3d11b4e72a8992c66b74. Its src/db2.c load_mobiles() exits on a word not in the table.
MPROG_TRIGGERS = (
    "act",
    "bribe",
    "death",
    "entry",
    "fight",
    "give",
    "greet",
    "grall",
    "kill",
    "hpcnt",
    "random",
    "speech",
    "exit",
    "exall",
    "delay",
    "surr",
)

# src/special.c spec_table. load_specials() exits when a name is not in it.
SPECIALS = (
    "spec_breath_any",
    "spec_breath_acid",
    "spec_breath_fire",
    "spec_breath_frost",
    "spec_breath_gas",
    "spec_breath_lightning",
    "spec_cast_adept",
    "spec_cast_cleric",
    "spec_cast_judge",
    "spec_cast_mage",
    "spec_cast_undead",
    "spec_executioner",
    "spec_fido",
    "spec_guard",
    "spec_janitor",
    "spec_mayor",
    "spec_poison",
    "spec_thief",
    "spec_nasty",
    "spec_troll_member",
    "spec_ogre_member",
    "spec_patrolman",
)


@attributes(frozen=True)
class Race:
    """The flag letters src/db2.c load_mobiles() ORs into every mobile of a race."""

    act = attr()
    affected_by = attr()
    offense = attr()
    immune = attr()
    resist = attr()
    vulnerable = attr()
    form = attr()
    parts = attr()


# src/const.c race_table.
RACES = {
    "unique": Race("", "", "", "", "", "", "", ""),
    "human": Race("", "", "", "", "", "", "AHMV", "ABCDEFGHIJK"),
    "elf": Race("", "J", "", "", "B", "Z", "AHMV", "ABCDEFGHIJK"),
    "dwarf": Race("", "J", "", "", "LQ", "R", "AHMV", "ABCDEFGHIJK"),
    "giant": Race("", "", "", "", "HI", "JP", "AHMV", "ABCDEFGHIJK"),
    "bat": Race("", "TZ", "FH", "", "", "S", "AGV", "ACDEFHJKP"),
    "bear": Race("", "", "DEO", "", "EI", "", "AGV", "ABCDEFHJKUV"),
    "cat": Race("", "Z", "FH", "", "", "", "AGV", "ACDEFHJKQUV"),
    "centipede": Race("", "Z", "", "", "FI", "E", "ABGO", "ACK"),
    "dog": Race("", "", "H", "", "", "", "AGV", "ACDEFHJKUV"),
    "doll": Race("", "", "", "ILMNPQR", "ES", "GHJKO", "EJMc", "ABCGHK"),
    "dragon": Race("", "JT", "", "", "BEH", "FI", "AHZ", "ACDEFGHIJKPQUVX"),
    "fido": Race("", "", "FR", "", "", "C", "ABGV", "ACDEFHJKQV"),
    "fox": Race("", "Z", "FH", "", "", "", "AGV", "ACDEFHJKQV"),
    "goblin": Race("", "J", "", "", "Q", "C", "AHMV", "ABCDEFGHIJK"),
    "hobgoblin": Race("", "J", "", "", "LQ", "", "AHMV", "ABCDEFGHIJKY"),
    "kobold": Race("", "J", "", "", "L", "C", "ABHMV", "ABCDEFGHIJKQ"),
    "lizard": Race("", "", "", "", "L", "I", "AGXc", "ACDEFHKQV"),
    "modron": Race("", "J", "QR", "BMNPQ", "HIK", "", "H", "ABCGHJK"),
    "orc": Race("", "J", "", "", "Q", "S", "AHMV", "ABCDEFGHIJK"),
    "pig": Race("", "", "", "", "", "", "AGV", "ACDEFHJK"),
    "rabbit": Race("", "", "FH", "", "", "", "AGV", "ACDEFHJK"),
    "school monster": Race("U", "", "", "AB", "", "C", "AMV", "ABCDEFHJKQU"),
    "snake": Race("", "", "", "", "L", "I", "AGXYc", "ADEFKLQVX"),
    "song bird": Race("", "T", "FH", "", "", "", "AGW", "ACDEFHKP"),
    "troll": Race("", "FJc", "D", "", "BE", "HK", "ABHMV", "ABCDEFGHIJKUV"),
    "water fowl": Race("", "Tb", "", "", "R", "", "AGW", "ACDEFHKP"),
    "wolf": Race("", "Z", "FH", "", "", "", "AGV", "ACDEFJKQV"),
    "wyvern": Race("", "DFT", "CFH", "L", "", "S", "ABGZ", "ACDEFHJKQVX"),
}

# src/const.c skill_table names: the spells a potion, pill, scroll, wand or staff may name.
SKILLS = (
    "reserved",
    "acid blast",
    "armor",
    "bless",
    "blindness",
    "burning hands",
    "call lightning",
    "calm",
    "cancellation",
    "cause critical",
    "cause light",
    "cause serious",
    "chain lightning",
    "change sex",
    "charm person",
    "chill touch",
    "colour spray",
    "continual light",
    "control weather",
    "create food",
    "create rose",
    "create spring",
    "create water",
    "cure blindness",
    "cure critical",
    "cure disease",
    "cure light",
    "cure poison",
    "cure serious",
    "curse",
    "demonfire",
    "detect evil",
    "detect good",
    "detect hidden",
    "detect invis",
    "detect magic",
    "detect poison",
    "dispel evil",
    "dispel good",
    "dispel magic",
    "earthquake",
    "enchant armor",
    "enchant weapon",
    "energy drain",
    "faerie fire",
    "faerie fog",
    "farsight",
    "fireball",
    "fireproof",
    "flamestrike",
    "fly",
    "floating disc",
    "frenzy",
    "gate",
    "giant strength",
    "harm",
    "haste",
    "heal",
    "heat metal",
    "holy word",
    "identify",
    "infravision",
    "invisibility",
    "know alignment",
    "lightning bolt",
    "locate object",
    "magic missile",
    "mass healing",
    "mass invis",
    "nexus",
    "pass door",
    "plague",
    "poison",
    "portal",
    "protection evil",
    "protection good",
    "ray of truth",
    "recharge",
    "refresh",
    "remove curse",
    "sanctuary",
    "shield",
    "shocking grasp",
    "sleep",
    "slow",
    "stone skin",
    "summon",
    "teleport",
    "ventriloquate",
    "weaken",
    "word of recall",
    "acid breath",
    "fire breath",
    "frost breath",
    "gas breath",
    "lightning breath",
    "general purpose",
    "high explosive",
    "axe",
    "dagger",
    "flail",
    "mace",
    "polearm",
    "shield block",
    "spear",
    "sword",
    "whip",
    "backstab",
    "bash",
    "berserk",
    "dirt kicking",
    "disarm",
    "dodge",
    "enhanced damage",
    "envenom",
    "hand to hand",
    "kick",
    "parry",
    "rescue",
    "trip",
    "second attack",
    "third attack",
    "fast healing",
    "haggle",
    "hide",
    "lore",
    "meditation",
    "peek",
    "pick lock",
    "sneak",
    "steal",
    "scrolls",
    "staves",
    "wands",
    "recall",
)

# doc/Rom2.4.doc, "Appendix A: Recommended Values": level -> (hit points, armor class, damage).
# Armor class is in file units; the reader's model holds ten times this.
RECOMMENDED_BY_LEVEL = {
    1: ("2d6+10", 9, "1d4+0"),
    2: ("2d7+21", 8, "1d5+0"),
    3: ("2d6+35", 7, "1d6+0"),
    4: ("2d7+46", 6, "1d5+1"),
    5: ("2d6+60", 5, "1d6+1"),
    6: ("2d7+71", 4, "1d7+1"),
    7: ("2d6+85", 4, "1d8+1"),
    8: ("2d7+96", 3, "1d7+2"),
    9: ("2d6+110", 2, "1d8+2"),
    10: ("2d7+121", 1, "2d4+2"),
    11: ("2d8+134", 1, "1d10+2"),
    12: ("2d10+150", 0, "1d10+3"),
    13: ("2d10+170", -1, "2d5+3"),
    14: ("2d10+190", -1, "1d12+3"),
    15: ("3d9+208", -2, "2d6+3"),
    16: ("3d9+233", -2, "2d6+4"),
    17: ("3d9+258", -3, "3d4+4"),
    18: ("3d9+283", -3, "2d7+4"),
    19: ("3d9+308", -4, "2d7+5"),
    20: ("3d9+333", -4, "2d8+5"),
    21: ("4d10+360", -5, "4d4+5"),
    22: ("5d10+400", -5, "4d4+6"),
    23: ("5d10+450", -6, "3d6+6"),
    24: ("5d10+500", -6, "2d10+6"),
    25: ("5d10+550", -7, "2d10+7"),
    26: ("5d10+600", -7, "3d7+7"),
    27: ("5d10+650", -8, "5d4+7"),
    28: ("6d12+703", -8, "2d12+8"),
    29: ("6d12+778", -9, "2d12+8"),
    30: ("6d12+853", -9, "4d6+8"),
    31: ("6d12+928", -10, "4d6+9"),
    32: ("10d10+1000", -10, "6d4+9"),
    33: ("10d10+1100", -11, "6d4+10"),
    34: ("10d10+1200", -11, "4d7+10"),
    35: ("10d10+1300", -11, "4d7+11"),
    36: ("10d10+1400", -12, "3d10+11"),
    37: ("10d10+1500", -12, "3d10+12"),
    38: ("10d10+1600", -13, "5d6+12"),
    39: ("15d10+1700", -13, "5d6+13"),
    40: ("15d10+1850", -13, "4d8+13"),
    41: ("25d10+2000", -14, "4d8+14"),
    42: ("25d10+2250", -14, "3d12+14"),
    43: ("25d10+2500", -15, "3d12+15"),
    44: ("25d10+2750", -15, "8d4+15"),
    45: ("25d10+3000", -15, "8d4+16"),
    46: ("25d10+3250", -16, "6d6+16"),
    47: ("25d10+3500", -17, "6d6+17"),
    48: ("25d10+3750", -18, "6d6+18"),
    49: ("50d10+4000", -19, "4d10+18"),
    50: ("50d10+4500", -20, "5d8+19"),
    51: ("50d10+5000", -21, "5d8+20"),
    52: ("50d10+5500", -22, "6d7+20"),
    53: ("50d10+6000", -23, "6d7+21"),
    54: ("50d10+6500", -24, "7d6+22"),
    55: ("50d10+7000", -25, "10d4+23"),
    56: ("50d10+7500", -26, "10d4+24"),
    57: ("50d10+8000", -27, "6d8+24"),
    58: ("50d10+8500", -28, "5d10+25"),
    59: ("50d10+9000", -29, "8d6+26"),
    60: ("50d10+9500", -30, "8d6+28"),
}

# The same appendix: which level's row a class-flagged mobile reads, as (hit points, armor class, damage)
# offsets, and the divisor n of its armor class against magic, (ac - 10) / n + 10.
CLASS_ADJUSTMENTS = {
    "thief": ((-1, -1, -1), 3),
    "mage": ((-1, -1, -3), 2),
    "cleric": ((0, 0, -2), 3),
    "warrior": ((1, 0, 0), 4),
}
DEFAULT_MAGIC_AC_DIVISOR = 4

# Appendix A has no mana column. These are measured from the stock areas in test/rom by
# scripts/derive_rom_mob_defaults.py: the mana dice of the median stock mobile of each level.
STOCK_MANA_BY_LEVEL = {
    1: "0d9+100",
    2: "1d9+100",
    3: "1d9+100",
    4: "2d9+100",
    5: "2d9+100",
    6: "3d9+100",
    7: "3d9+100",
    8: "4d9+100",
    9: "4d9+100",
    10: "5d9+100",
    11: "5d9+100",
    12: "6d9+100",
    13: "6d9+100",
    14: "7d9+100",
    15: "7d9+100",
    16: "8d9+100",
    17: "8d9+100",
    18: "9d9+100",
    19: "9d9+100",
    20: "10d9+100",
    21: "10d9+100",
    22: "22d9+100",
    23: "11d9+100",
    24: "12d9+100",
    25: "12d9+100",
    26: "13d9+100",
    27: "27d9+100",
    28: "14d9+100",
    29: "14d9+100",
    30: "15d9+100",
    31: "31d9+100",
    32: "32d9+100",
    33: "16d9+100",
    34: "17d9+100",
    35: "17d9+100",
    36: "40d20+50",
    37: "18d9+100",
    38: "19d9+100",
    39: "19d9+100",
    40: "20d9+100",
    41: "20d9+100",
    42: "21d9+100",
    43: "21d9+100",
    44: "22d9+100",
    45: "22d9+100",
    46: "23d9+100",
    47: "23d9+100",
    48: "24d9+100",
    49: "24d9+100",
    50: "25d9+100",
    51: "25d9+100",
    52: "26d9+100",
    53: "26d9+100",
    54: "27d9+100",
    55: "27d9+100",
    56: "28d9+100",
    57: "1d1+499",
    58: "29d9+100",
    59: "59d9+100",
    60: "30d9+100",
}
