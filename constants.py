import enum
from attr import attr, attributes

def flag_convert(letter):
	if len(letter) > 1:
		return flag_convert(letter[0]) + flag_convert(letter[1:])
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
	
class MERC_ACT_TYPES(enum.Flag):
	IS_NPC= flag_convert('A') # Auto set for mobs
	SENTINEL_= flag_convert('B') # Stays in one room
	SCAVENGER_= flag_convert('C') # Picks  up objects
	AGGRESSIVE_= flag_convert('F') # Attacks  PC s
	STAY_AREA= flag_convert('G') # Won't leave area
	WIMPY_= flag_convert('H') 
	PET_= flag_convert('I') # Auto set for pets
	TRAIN_= flag_convert('J') # Can train PC s
	_PRACTICE= flag_convert('K') # Can practice PC s

class ROM_ACT_TYPES(enum.Flag):
	IS_NPC= flag_convert('A') # Auto set for mobs
	SENTINEL_= flag_convert('B') # Stays in one room
	SCAVENGER_= flag_convert('C') # Picks  up objects
	AGGRESSIVE_= flag_convert('F') # Attacks  PC s
	STAY_AREA= flag_convert('G') # Won't leave area
	WIMPY_= flag_convert('H') #    
	PET_= flag_convert('I') # Auto set for pets
	TRAIN_= flag_convert('J') # Can train PC s
	_PRACTICE= flag_convert('K') # Can practice PC s
	_UNDEAD= flag_convert('O') #    
	_CLERIC= flag_convert('Q') #    
	MAGE_= flag_convert('R') #    
	THIEF_= flag_convert('S') #    
	WARRIOR_= flag_convert('T') #    
	_NOALIGN= flag_convert('U') #    
	_NOPURGE= flag_convert('V') #    
	OUTDOORS_= flag_convert('W') #    
	INDOORS_= flag_convert('Y') #    
	IS_HEALER= flag_convert('AA') #    
	GAIN_= flag_convert('BB') #    
	UPDATE_ALWAYS= flag_convert('CC') #    
	IS_CHANGER= flag_convert('DD') #    

class AFFECTED_BY(enum.Flag):
	BLIND = flag_convert('A')
	INVISIBLE = flag_convert('B')
	EVIL = flag_convert('C')
	INVIS = flag_convert('D')
	MAGIC = flag_convert('E')
	HIDDEN = flag_convert('F')
	GOOD = flag_convert('G')
	SANCTUARY = flag_convert('H')
	FIRE = flag_convert('I')
	INFRARED = flag_convert('J')
	CURSE = flag_convert('K')
	UNUSED_FLAG = flag_convert('L') # Unused
	POISON = flag_convert('M')
	PROTECT_EVIL = flag_convert('N')
	PROTECT_GOOD = flag_convert('O')
	SNEAK = flag_convert('P')
	HIDE = flag_convert('Q')
	SLEEP = flag_convert('R')
	CHARM = flag_convert('S')
	FLYING = flag_convert('T')
	PASS_DOOR = flag_convert('U')
	HASTE = flag_convert('V')
	CALM = flag_convert('W')
	PLAGUE = flag_convert('X')
	WEAKEN = flag_convert('Y')
	DARK_VISION = flag_convert('Z')
	BERSERK = flag_convert('AA')
	SWIM = flag_convert('BB')
	REGENERATION = flag_convert('CC')
	SLOW = flag_convert('DD')

class WEAR_FLAGS(enum.Flag):
	FINGER = flag_convert('B')
	NECK = flag_convert('C')
	BODY = flag_convert('D')
	HEAD = flag_convert('E')
	LEGS = flag_convert('F')
	FEET = flag_convert('G')
	HANDS = flag_convert('H')
	ARMS = flag_convert('I')
	SHIELD = flag_convert('J')
	ABOUT = flag_convert('K')
	WAIST = flag_convert('L')
	WRIST = flag_convert('M')
	WIELD = flag_convert('N')
	HOLD = flag_convert('O')
	SAC = flag_convert('P')
	FLOAT = flag_convert('Q')

class OFFENSE(enum.Flag):
	AREA_ATTACK = flag_convert('A')
	BACKSTAB = flag_convert('B')
	BASH_ = flag_convert('C')
	BERSERK = flag_convert('D')
	DISARM_ = flag_convert('E')
	DODGE_ = flag_convert('F')
	FADE_ = flag_convert('G')
	FAST = flag_convert('H')
	KICK = flag_convert('I')
	KICK_DIRT = flag_convert('J')
	PARRY_ = flag_convert('K')
	RESCUE_ = flag_convert('L')
	TAIL_ = flag_convert('M')
	TRIP_ = flag_convert('N')
	CRUSH_ = flag_convert('O')
	ASSIST_ALL = flag_convert('P')
	ASSIST_ALIGN = flag_convert('Q')
	ASSIST_RACE = flag_convert('R')
	ASSIST_PLAYERS = flag_convert('S')
	ASSIST_GUARD = flag_convert('T')
	ASSIST_VNUM = flag_convert('U')

class IMM_FLAGS(enum.Flag):
	SUMMON = flag_convert('A')
	CHARM = flag_convert('B')
	MAGIC = flag_convert('C')
	WEAPON = flag_convert('D')
	BASH = flag_convert('E')
	PIERCE = flag_convert('F')
	SLASH = flag_convert('G')
	FIRE = flag_convert('H')
	COLD = flag_convert('I')
	LIGHTNING = flag_convert('J')
	ACID = flag_convert('K')
	POISON = flag_convert('L')
	NEGATIVE = flag_convert('M')
	HOLY = flag_convert('N')
	ENERGY = flag_convert('O')
	MENTAL = flag_convert('P')
	DISEASE = flag_convert('Q')
	DROWNING = flag_convert('R')
	LIGHT = flag_convert('S')
	SOUND = flag_convert('T')
	WOOD = flag_convert('X')
	SILVER = flag_convert('Y')
	IRON = flag_convert('Z')

class FORMS(enum.Flag):
	EDIBLE = flag_convert('A')
	POISON = flag_convert('B')
	MAGICAL = flag_convert('C')
	OTHER = flag_convert('E') # defined by material bit
	# actual form
	ANIMAL = flag_convert('G')
	SENTIENT = flag_convert('H')
	UNDEAD = flag_convert('I')
	CONSTRUCT = flag_convert('J')
	MIST = flag_convert('K')
	INTANGIBLE = flag_convert('L')

	BIPED = flag_convert('M')
	CENTAUR = flag_convert('N')
	INSECT = flag_convert('O')
	SPIDER = flag_convert('P')
	CRUSTACEAN = flag_convert('Q')
	WORM = flag_convert('R')
	BLOB = flag_convert('S')

	MAMMAL = flag_convert('V')
	BIRD = flag_convert('W')
	REPTILE = flag_convert('X')
	SNAKE = flag_convert('Y')
	DRAGON = flag_convert('Z')
	AMPHIBIAN = flag_convert('AA')
	FISH = flag_convert('BB')
	COLD_BLOOD = flag_convert('CC')

class PARTS(enum.Flag):
	HEAD = flag_convert('A')
	ARMS = flag_convert('B')
	LEGS = flag_convert('C')
	HEART = flag_convert('D')
	BRAINS = flag_convert('E')
	GUTS = flag_convert('F')
	HANDS = flag_convert('G')
	FEET = flag_convert('H')
	FINGERS = flag_convert('I')
	EAR = flag_convert('J')
	EYE = flag_convert('K')
	LONG_TONGUE = flag_convert('L')
	EYESTALKS = flag_convert('M')
	TENTACLES = flag_convert('N')
	FINS = flag_convert('O')
	WINGS = flag_convert('P')
	TAIL = flag_convert('Q')
	# for combat
	CLAWS = flag_convert('U')
	FANGS = flag_convert('V')
	HORNS = flag_convert('W')
	SCALES = flag_convert('X')
	TUSKS = flag_convert('Y')

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

class ROM_ROOM_FLAGS(enum.Flag):
	DARK = flag_convert('A')
	NO_MOB = flag_convert('C')
	INDOORS = flag_convert('D')
	PRIVATE = flag_convert('J')
	SAFE = flag_convert('K')
	SOLITARY = flag_convert('L')
	PET_SHOP = flag_convert('M')
	NO_RECALL = flag_convert('N')
	IMP_ONLY = flag_convert('O')
	GODS_ONLY = flag_convert('P')
	HEROES_ONLY = flag_convert('Q')
	NEWBIES_ONLY = flag_convert('R')
	LAW = flag_convert('S')
	NOWHERE = flag_convert('T')

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

class EXIT_FLAGS(enum.Flag):
	ISDOOR = flag_convert('A')
	CLOSED = flag_convert('B')
	LOCKED = flag_convert('C')
	PICKPROOF = flag_convert('F')
	NOPASS = flag_convert('G')
	EASY = flag_convert('H')
	HARD = flag_convert('I')
	INFURIATING = flag_convert('J')
	NOCLOSE = flag_convert('K')
	NOLOCK = flag_convert('L')

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

class SMAUG_AFFECTED_BY(enum.Flag):
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

class WEAPON_TYPES(enum.Flag):
	FLAMING = flag_convert('A')
	FROST = flag_convert('B')
	VAMPIRIC = flag_convert('C')
	SHARP = flag_convert('D')
	VORPAL = flag_convert('E')
	HANDS = flag_convert('F')
	SHOCKING = flag_convert('G')

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