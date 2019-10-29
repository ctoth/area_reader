import enum
from attr import attr, attributes

def flag_convert(letter):
	if len(letter) > 1:
		raise ValueError("Unable to convert flag " + letter)
	bitsum = 0
	start = None
	if letter >= 'A' and letter <= 'Z':
		bitsum = 1
		start = 'A'
	elif letter >= 'a' and letter <= 'z':
		bitsum = 67108864
		start = 'a'
	l2 = ord(letter)
	while l2 > ord(start):
		bitsum *= 2
		l2 -= 1
	return bitsum

def remove_bit(var, bit):
	return var & ~bit


BITFLAGS = dict(
	A = 1,
	B = 2,
	C = 4,
	D = 8,
	E = 16,
	F = 32,
	G = 64,
	H = 128,
	I = 256,
	J = 512,
	K = 1024,
	L = 2048,
	M = 4096,
	N = 8192,
	O = 16384,
	P = 32768,
	Q = 65536,
	R = 131072,
	S = 262144,
	T = 524288,
	U = 1048576,
	V = 2097152,
	W = 4194304,
	X = 8388608,
	Y = 16777216,
	Z = 33554432,
	AA = 67108864,
	BB = 134217728,
	CC = 268435456,
	DD = 536870912,
	EE = 1073741824,
)

class MERC_ACT_TYPES(enum.IntFlag):
	IS_NPC= BITFLAGS['A'] # Auto set for mobs
	SENTINEL_= BITFLAGS['B'] # Stays in one room
	SCAVENGER_= BITFLAGS['C'] # Picks  up objects
	UNUSED1 = BITFLAGS['D']
	UNUSED2 = BITFLAGS['E']
	AGGRESSIVE_= BITFLAGS['F'] # Attacks  PC s
	STAY_AREA= BITFLAGS['G'] # Won't leave area
	WIMPY = BITFLAGS['H'] 
	PET = BITFLAGS['I'] # Auto set for pets
	TRAIN = BITFLAGS['J'] # Can train PC s
	_PRACTICE = BITFLAGS['K'] # Can practice PC s
	UNUSED3 = BITFLAGS['L']
	UNUSED4 = BITFLAGS['M']


class ROM_ACT_TYPES(enum.IntFlag):
	IS_NPC = BITFLAGS['A'] # Auto set for mobs
	SENTINEL = BITFLAGS['B'] # Stays in one room
	SCAVENGER = BITFLAGS['C'] # Picks  up objects
	UNUSED1 = BITFLAGS['D']
	UNUSED2 = BITFLAGS['E']
	AGGRESSIVE = BITFLAGS['F'] # Attacks  PC s
	STAY_AREA = BITFLAGS['G'] # Won't leave area
	WIMPY = BITFLAGS['H'] #    
	PET = BITFLAGS['I'] # Auto set for pets
	TRAIN = BITFLAGS['J'] # Can train PC s
	_PRACTICE = BITFLAGS['K'] # Can practice PC s
	UNUSED3 = BITFLAGS['L'] 
	UNUSED4 = BITFLAGS['M']
	UNUSED5 = BITFLAGS['N']
	_UNDEAD = BITFLAGS['O'] #    
	UNUSED6 = BITFLAGS['P']
	_CLERIC = BITFLAGS['Q'] #    
	MAGE = BITFLAGS['R'] #    
	THIEF = BITFLAGS['S'] #    
	WARRIOR = BITFLAGS['T'] #    
	NOALIGN = BITFLAGS['U'] #    
	NOPURGE = BITFLAGS['V'] #    
	OUTDOORS = BITFLAGS['W'] #    
	UNUSED7 = BITFLAGS['X']
	INDOORS = BITFLAGS['Y'] #    
	UNUSED8 = BITFLAGS['Z']
	IS_HEALER = BITFLAGS['AA'] #    
	GAIN = BITFLAGS['BB'] #    
	UPDATE_ALWAYS = BITFLAGS['CC'] #    
	IS_CHANGER = BITFLAGS['DD'] #    
	UNUSED9 = BITFLAGS['EE']

class AFFECTED_BY(enum.IntFlag):
	BLIND = BITFLAGS['A']
	INVISIBLE = BITFLAGS['B']
	EVIL = BITFLAGS['C']
	INVIS = BITFLAGS['D']
	MAGIC = BITFLAGS['E']
	HIDDEN = BITFLAGS['F']
	GOOD = BITFLAGS['G']
	SANCTUARY = BITFLAGS['H']
	FIRE = BITFLAGS['I']
	INFRARED = BITFLAGS['J']
	CURSE = BITFLAGS['K']
	UNUSED_FLAG = BITFLAGS['L'] # Unused
	POISON = BITFLAGS['M']
	PROTECT_EVIL = BITFLAGS['N']
	PROTECT_GOOD = BITFLAGS['O']
	SNEAK = BITFLAGS['P']
	HIDE = BITFLAGS['Q']
	SLEEP = BITFLAGS['R']
	CHARM = BITFLAGS['S']
	FLYING = BITFLAGS['T']
	PASS_DOOR = BITFLAGS['U']
	HASTE = BITFLAGS['V']
	CALM = BITFLAGS['W']
	PLAGUE = BITFLAGS['X']
	WEAKEN = BITFLAGS['Y']
	DARK_VISION = BITFLAGS['Z']
	BERSERK = BITFLAGS['AA']
	SWIM = BITFLAGS['BB']
	REGENERATION = BITFLAGS['CC']
	SLOW = BITFLAGS['DD']

class WEAR_FLAGS(enum.IntFlag):
	FINGER = BITFLAGS['B']
	NECK = BITFLAGS['C']
	BODY = BITFLAGS['D']
	HEAD = BITFLAGS['E']
	LEGS = BITFLAGS['F']
	FEET = BITFLAGS['G']
	HANDS = BITFLAGS['H']
	ARMS = BITFLAGS['I']
	SHIELD = BITFLAGS['J']
	ABOUT = BITFLAGS['K']
	WAIST = BITFLAGS['L']
	WRIST = BITFLAGS['M']
	WIELD = BITFLAGS['N']
	HOLD = BITFLAGS['O']
	SAC = BITFLAGS['P']
	FLOAT = BITFLAGS['Q']

class OFFENSE(enum.IntFlag):
	AREA_ATTACK = BITFLAGS['A']
	BACKSTAB = BITFLAGS['B']
	BASH = BITFLAGS['C']
	BERSERK = BITFLAGS['D']
	DISARM = BITFLAGS['E']
	DODGE = BITFLAGS['F']
	FADE = BITFLAGS['G']
	FAST = BITFLAGS['H']
	KICK = BITFLAGS['I']
	KICK_DIRT = BITFLAGS['J']
	PARRY = BITFLAGS['K']
	RESCUE = BITFLAGS['L']
	TAIL_ = BITFLAGS['M']
	TRIP_ = BITFLAGS['N']
	CRUSH_ = BITFLAGS['O']
	ASSIST_ALL = BITFLAGS['P']
	ASSIST_ALIGN = BITFLAGS['Q']
	ASSIST_RACE = BITFLAGS['R']
	ASSIST_PLAYERS = BITFLAGS['S']
	ASSIST_GUARD = BITFLAGS['T']
	ASSIST_VNUM = BITFLAGS['U']

class IMM_FLAGS(enum.IntFlag):
	SUMMON = BITFLAGS['A']
	CHARM = BITFLAGS['B']
	MAGIC = BITFLAGS['C']
	WEAPON = BITFLAGS['D']
	BASH = BITFLAGS['E']
	PIERCE = BITFLAGS['F']
	SLASH = BITFLAGS['G']
	FIRE = BITFLAGS['H']
	COLD = BITFLAGS['I']
	LIGHTNING = BITFLAGS['J']
	ACID = BITFLAGS['K']
	POISON = BITFLAGS['L']
	NEGATIVE = BITFLAGS['M']
	HOLY = BITFLAGS['N']
	ENERGY = BITFLAGS['O']
	MENTAL = BITFLAGS['P']
	DISEASE = BITFLAGS['Q']
	DROWNING = BITFLAGS['R']
	LIGHT = BITFLAGS['S']
	SOUND = BITFLAGS['T']
	WOOD = BITFLAGS['X']
	SILVER = BITFLAGS['Y']
	IRON = BITFLAGS['Z']

class FORMS(enum.IntFlag):
	EDIBLE = BITFLAGS['A']
	POISON = BITFLAGS['B']
	MAGICAL = BITFLAGS['C']
	OTHER = BITFLAGS['E'] # defined by material bit
	UNUSED1 = enum.auto()
	# actual form
	ANIMAL = BITFLAGS['G']
	SENTIENT = BITFLAGS['H']
	UNDEAD = BITFLAGS['I']
	CONSTRUCT = BITFLAGS['J']
	MIST = BITFLAGS['K']
	INTANGIBLE = BITFLAGS['L']

	BIPED = BITFLAGS['M']
	CENTAUR = BITFLAGS['N']
	INSECT = BITFLAGS['O']
	SPIDER = BITFLAGS['P']
	CRUSTACEAN = BITFLAGS['Q']
	WORM = BITFLAGS['R']
	BLOB = BITFLAGS['S']
	UNUSED2 = enum.auto()
	UNUSED3 = enum.auto()
	MAMMAL = BITFLAGS['V']
	BIRD = BITFLAGS['W']
	REPTILE = BITFLAGS['X']
	SNAKE = BITFLAGS['Y']
	DRAGON = BITFLAGS['Z']
	AMPHIBIAN = BITFLAGS['AA']
	FISH = BITFLAGS['BB']
	COLD_BLOOD = BITFLAGS['CC']
	UNUSED4 = BITFLAGS['DD']
	UNUSED5 = BITFLAGS['EE']

class PARTS(enum.IntFlag):
	HEAD = BITFLAGS['A']
	ARMS = BITFLAGS['B']
	LEGS = BITFLAGS['C']
	HEART = BITFLAGS['D']
	BRAINS = BITFLAGS['E']
	GUTS = BITFLAGS['F']
	HANDS = BITFLAGS['G']
	FEET = BITFLAGS['H']
	FINGERS = BITFLAGS['I']
	EAR = BITFLAGS['J']
	EYE = BITFLAGS['K']
	LONG_TONGUE = BITFLAGS['L']
	EYESTALKS = BITFLAGS['M']
	TENTACLES = BITFLAGS['N']
	FINS = BITFLAGS['O']
	WINGS = BITFLAGS['P']
	TAIL = BITFLAGS['Q']
	# for combat
	CLAWS = BITFLAGS['U']
	FANGS = BITFLAGS['V']
	HORNS = BITFLAGS['W']
	SCALES = BITFLAGS['X']
	TUSKS = BITFLAGS['Y']

class WEAR_LOCATIONS(enum.Enum):
	NONE = -1
	LIGHT = 0
	FINGER_L = 1
	FINGER_R = 2
	NECK_1 = 3
	NECK_2 = 4
	BODY = 5
	HEAD = 6
	LEGS = 7
	FEET = 8
	HANDS = 9
	ARMS = 10
	SHIELD = 11
	ABOUT = 12
	WAIST = 13
	RIST_L = 14
	WRIST_R = 15
	WIELD = 16
	HOLD = 17
	FLOAT = 18
	MAX = 19

class ROM_ROOM_FLAGS(enum.IntFlag):
	DARK = BITFLAGS['A']
	unused1 = enum.auto()
	NO_MOB = BITFLAGS['C']
	INDOORS = BITFLAGS['D']
	unused2 = enum.auto()
	UNUSED3 = enum.auto()
	unused4 = enum.auto()
	unused5 = enum.auto()
	unused6 = enum.auto()
	PRIVATE = BITFLAGS['J']
	SAFE = BITFLAGS['K']
	SOLITARY = BITFLAGS['L']
	PET_SHOP = BITFLAGS['M']
	NO_RECALL = BITFLAGS['N']
	IMP_ONLY = BITFLAGS['O']
	GODS_ONLY = BITFLAGS['P']
	HEROES_ONLY = BITFLAGS['Q']
	NEWBIES_ONLY = BITFLAGS['R']
	LAW = BITFLAGS['S']
	NOWHERE = BITFLAGS['T']

class MERC_ROOM_FLAGS(enum.Enum):
	DARK = 1
	NO_MOB = 4
	INDOORS = 8
	PRIVATE = 512
	SAFE = 1024
	SOLITARY = 2048
	PETSHOP = 4096
	NO_RECALL = 8192
	
class EXIT_DIRECTIONS(enum.Enum):
	NORTH = 0
	EAST = 1
	SOUTH = 2
	WEST = 3
	UP = 4
	DOWN = 5

class EXIT_FLAGS(enum.IntFlag):
	ISDOOR = BITFLAGS['A']
	CLOSED = BITFLAGS['B']
	LOCKED = BITFLAGS['C']
	PICKPROOF = BITFLAGS['F']
	NOPASS = BITFLAGS['G']
	EASY = BITFLAGS['H']
	HARD = BITFLAGS['I']
	INFURIATING = BITFLAGS['J']
	NOCLOSE = BITFLAGS['K']
	NOLOCK = BITFLAGS['L']

class SECTOR_TYPES(enum.Enum):
	INSIDE = 0
	CITY = 1
	FIELD = 2
	FOREST = 3
	HILLS = 4
	MOUNTAIN = 5
	WATER_SWIM = 6
	WATER_NOSWIM = 7
	UNUSED = 8
	AIR = 9
	DESERT = 10
	MAX = 11

class SMAUG_AFFECTED_BY(enum.IntFlag):
	BLIND = 1
	INVISIBLE = 2
	DETECT_EVIL = 3
	DETECT_INVIS = 4
	DETECT_MAGIC = 5
	DETECT_HIDDEN = 6
	HOLD = 7
	SANCTUARY = 8
	FAERIE_FIRE = 9
	INFRARED = 10
	CURSE = 11
	FLAMING = 12
	POISON = 13
	PROTECT = 14
	PARALYSIS = 15
	SNEAK = 16
	HIDE = 17
	SLEEP = 18
	CHARM = 19
	FLYING = 20
	PASS_DOOR = 21
	FLOATING = 22
	TRUESIGHT = 23
	DETECTTRAPS = 24
	SCRYING = 25
	FIRESHIELD = 26
	SHOCKSHIELD = 27
	HAUS1 = 28
	ICESHIELD = 29
	POSSESS = 30
	BERSERK = 31
	AQUA_BREATH = 32
	RECURRINGSPELL = 33
	CONTAGIOUS = 34
	ACIDMIST = 35
	VENOMSHIELD = 36
	ITEM_AURAS = 37
	PEOPLE_AURAS = 38
	SENSE_DEAD = 39
	HEAR_DEAD = 40
	SEE_DEAD = 41
	FADE = 42
	CHAIN_AGONY = 43
	INFEST = 44
	GRAPPLE = 45
	MAX = 46


SMAUG_TRAP_TYPES = enum.Enum('SMAUG_TRAP_TYPES', 'POISON_DART POISON_NEEDLE POISON_DAGGER POISON_ARROW BLINDNESS_GAS SLEEPING_GAS FLAME EXPLOSION ACID_SPRAY ELECTRIC_SHOCK BLADE SEX_CHANGE')

class WEAPON_TYPES(enum.IntFlag):
	FLAMING = BITFLAGS['A']
	FROST = BITFLAGS['B']
	VAMPIRIC = BITFLAGS['C']
	SHARP = BITFLAGS['D']
	VORPAL = BITFLAGS['E']
	HANDS = BITFLAGS['F']
	SHOCKING = BITFLAGS['G']

class APPLY_TYPES(enum.Enum):
	NONE = 0
	STR = 1
	DEX = 2
	INT = 3
	WIS = 4
	CON = 5
	SEX = 6
	CLASS = 7
	LEVEL = 8
	AGE = 9
	HEIGHT = 10
	WEIGHT = 11
	MANA = 12
	HIT = 13
	MOVE = 14
	GOLD = 15
	EXP = 16
	AC = 17
	HITROLL = 18
	DAMROLL = 19
	SAVES = 20
	SAVING_PARA = 20
	SAVING_ROD = 21
	SAVING_PETRI = 22
	SAVING_BREATH = 23
	SAVING_SPELL = 24
	AFFECT = 25

@attributes
class Liquid(object):
	color = attr(default='', type=str)
	proof = attr(default=0, type=int)
	full = attr(default=0, type=int)
	thurst = attr(default=0, type=int)
	food = attr(default=0, type=int)
	size = attr(default=0, type=int)

ROM_LIQUIDS = {
	'water': Liquid('clear', 0, 1, 10, 0, 16),
	'beer': Liquid('amber', 12, 1, 8, 1, 12),
	"red wine": Liquid("burgundy", 30, 1, 8, 1, 5),
	'ale': Liquid("brown", 15, 1, 8, 1, 12),
	'dark ale': Liquid("dark", 16, 1, 8, 1, 12),
	'whisky': Liquid("golden", 120, 1, 5, 0, 2),
	'lemonade': Liquid("pink", 0, 1, 9, 2, 12),
	'firebreather': Liquid("boiling", 190, 0, 4, 0, 2),
	'local specialty': Liquid("clear", 151, 1, 3, 0, 2),
	'slime mold juice': Liquid("green", 0, 2, -8, 1, 2),
	'milk': Liquid("white", 0, 2, 9, 3, 12),
	'tea': Liquid("tan", 0, 1, 8, 0, 6),
	'coffee': Liquid("black", 0, 1, 8, 0, 6),
	'blood': Liquid("red", 0, 2, -1, 2, 6),
	'salt water': Liquid("clear", 0, 1, -2, 0, 1),
	'coke': Liquid("brown", 0, 2, 9, 2, 12),
	'root beer': Liquid("brown", 0, 2, 9, 2, 12),
	'elvish wine': Liquid("green", 35, 2, 8, 1, 5),
	'white wine': Liquid("golden", 28, 1, 8, 1, 5),
	'champagne': Liquid("golden", 32, 1, 8, 1, 5),
	'mead': Liquid("honey-colored", 34, 2, 8, 2, 12),
	'rose wine': Liquid("pink", 26, 1, 8, 1, 5),
	'benedictine wine': Liquid("burgundy", 40, 1, 8, 1, 5),
	'vodka': Liquid("clear", 130, 1, 5, 0, 2),
	'cranberry juice': Liquid("red", 0, 1, 9, 2, 12),
	'orange juice': Liquid("orange", 0, 2, 9, 3, 12),
	'absinthe': Liquid("green", 200, 1, 4, 0, 2),
	'brandy': Liquid("golden", 80, 1, 5, 0, 4),
	'aquavit': Liquid("clear", 140, 1, 5, 0, 2),
	'schnapps': Liquid("clear", 90, 1, 5, 0, 2),
	'icewine': Liquid("purple", 50, 2, 6, 1, 5),
	'amontillado': Liquid("burgundy", 35, 2, 8, 1, 5),
	'sherry': Liquid("red", 38, 2, 7, 1, 5),
	'framboise': Liquid("red", 50, 1, 7, 1, 5),
	'rum': Liquid("amber", 151, 1, 4, 0, 2),
	'cordial': Liquid("clear", 100, 1, 5, 0, 2),
}