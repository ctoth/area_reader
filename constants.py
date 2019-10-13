import enum


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
	IS_HEALER= flag_convert('aa') #    
	GAIN_= flag_convert('bb') #    
	UPDATE_ALWAYS= flag_convert('cc') #    
	IS_CHANGER= flag_convert('dd') #    

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
	BERSERK = flag_convert('aa')
	SWIM = flag_convert('bb')
	REGENERATION = flag_convert('cc')
	SLOW = flag_convert('dd')


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

class AFFECTS(enum.Flag):
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
	AMPHIBIAN = flag_convert('aa')
	FISH = flag_convert('bb')
	COLD_BLOOD = flag_convert('cc')

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

class EXIT_DIRECTIONS(enum.Enum):
	NORTH = 0
	EAST = 1
	SOUTH = 2
	WEST = 3
	UP = 4
	DOWN = 5

class SECTOR_TYPES(enum.Enum):
	INSIDE = 0
	CITY = 1
	FIELD = 2
	FOREST = 3
	HILLS = 4
	MOUNTAIN = 5
	WATER_SWIM = 6
	NOSWIM = 7
	UNUSED = 8
	AIR = 9
	DESERT = 10
	MAX = 11
