from logging import getLogger
logger = getLogger('area_reader')
from collections import OrderedDict
import io
import json
import os
from attr import asdict, attr, attributes, Factory
from operator import setitem


class ParseError(Exception): pass

class AreaFile(object):
	area_type = None
	MAX_TRADES = 5

	def __init__(self, filename):
		super(AreaFile, self).__init__()
		self.file = open(filename)
		self.index = 0
		self.data = self.file.read()
		self.filename = filename
		self.file.close()
		area_type = self.area_type or RomArea
		self.area = area_type()

	def read_letter(self):
		self.skip_whitespace()
		result = self.current_char
		self.advance()
		return result

	def read_word(self):
		self.skip_whitespace()
		word = ""
		end = ''
		if self.current_char == '\'' or self.current_char == '"':
			end = self.current_char
			self.advance()
			word = self.read_until(end)
			self.advance()
			return word
		while not self.current_char.isspace():
			word += self.current_char
			self.advance()
		return word

	def read_string(self):
		self.skip_whitespace()
		return self.read_until('~')

	def read_number(self):
		#self.skip_whitespace()
		while self.current_char.isspace():
			self.advance()
		number = 0
		sign = False
		while self.current_char.isspace():
			self.advance()
		if self.current_char == '+':
			self.advance()
		elif self.current_char == '-':
			sign = True
			self.advance()
		while self.current_char.isdigit():
			number = number * 10 + int(self.current_char)
			self.advance()
		if sign:
			number *= -1
		if self.current_char == '|':
			self.advance()
			number += self.read_number()
		return number

	def read_to_eol(self):
		return self.read_until('\n')

	def read_until(self, endchar):
		ahead = self.data.find(endchar, self.index)
		result = self.data[self.index:ahead]
		self.index = ahead
		self.advance()
		return result

	@property
	def current_char(self):
		return self.data[self.index]

	def advance(self):
		self.index += 1

	def skip_whitespace(self):
		while self.current_char.isspace():
			self.advance()

	def read_flag(self):
		negative = False
		self.skip_whitespace()
		if self.current_char == '+':
			self.advance()
		if self.current_char == '-':
			negative = True
			self.advance()
		number = 0
		if not self.current_char.isdigit():
			while self.current_char.isalpha():
				number += flag_convert(self.current_char)
				self.advance()
		while self.current_char.isdigit():
			number = number * 10 + int(self.current_char)
			self.advance()
		if self.current_char == '|':
			self.advance()
			number += self.read_flag()
		if negative:
			number *= -1
		return number


	def read_and_verify_letter(self, verification):
		letter = self.read_letter()
		if letter != verification:
			self.parse_fail("Expected %s got %s" % (verification, letter))
		return letter

	def load_section(self, object_loader):
		while True:
			vnum = self.read_vnum()
			if vnum == 0:
				break
			object_loader(vnum)

	def read_vnum(self):
		self.read_and_verify_letter('#')
		vnum = self.read_number()
		return vnum


	def load_mobiles(self):
		loader = lambda vnum: setitem(self.area.mobs, vnum, self.load_mob(vnum))
		self.load_section(object_loader=loader)

	def read_dice(self):
		dice = Dice()
		dice.number = self.read_number()
		self.read_letter()
		dice.type = self.read_number()
		dice.bonus = self.read_number()
		return dice

	def load_rooms(self):
		loader = lambda vnum: setitem(self.area.rooms, vnum, self.load_room(vnum))
		self.load_section(object_loader=loader)

	def load_room(self, vnum):
		logger.debug("Reading room %d" % vnum)
		room = Room(vnum=vnum)
		room.name = self.read_string()
		room.description = self.read_string()
		room.area_number = self.read_number()
		room.room_flags = self.read_flag()
		room.sector_type = self.read_number()
		self.read_room_data(room)
		return room

	def read_exit(self):
		exit = Exit()
		locks = 0
		exit.door = self.read_number()
		exit.description = self.read_string()
		exit.keyword = self.read_string()
		exit.exit_info = 0
		locks = self.read_number()
		exit.key = self.read_number()
		exit.destination = self.read_number()
		return exit

	def read_extra_descr(self):
		ed = ExtraDescription()
		ed.keyword = self.read_string()
		ed.description = self.read_string()
		return ed

	def load_objects(self):
		loader = lambda vnum: setitem(self.area.objects, vnum, self.load_object(vnum))
		self.load_section(object_loader=loader)


	def load_resets(self):
		while True:
			letter = self.read_letter()
			if letter == 'S':
				break
			if letter == '*':
				self.read_to_eol()
				continue
			reset = Reset()
			reset.command = letter
			self.read_number() #if_flag
			reset.arg1 = self.read_number()
			reset.arg2 = self.read_number()
			if letter == 'G' or letter == 'R':
				reset.arg3 = 0
			else:
				reset.arg3 = self.read_number()
			if letter == 'P' or letter == 'M':
				reset.arg4 = 0
			else:
				reset.arg4 = self.read_number()
			self.read_to_eol()
			self.area.resets.append(reset)
			if reset.command == 'M' or reset.command == 'O':
				r_vnum = reset.arg3
			if reset.command == 'P' or reset.command == 'G' or reset.command == 'E':
				continue
			if reset.command == 'R':
				r_vnum = reset.arg1

	def load_specials(self):
		while True:
			letter = self.read_letter()
			if letter == 'S':
				break
			if letter == '*':
				self.read_to_eol()
				continue
			special = RomSpecial()
			self.area.specials.append(special)
			special.command = letter
			special.arg1 = self.read_number()
			special.arg2 = self.read_word()
			self.read_to_eol()

	def read_area_metadata(self):
		raise NotImplementedError

	def load_sections(self):
		readers = {
			'area': self.read_area_metadata,
			'mobiles': self.load_mobiles,
			'rooms': self.load_rooms,
			'objects': self.load_objects,
			'helps': self.load_helps,
			'resets': self.load_resets,
			'shops': self.load_shops,
			'specials': self.load_specials,
		}
		while True:
			section_name = self.read_section_name()
			if section_name == '$':
				break
			logger.info("Processing section %s" % section_name)
			readers[section_name]()

	def read_section_name(self):
		self.read_and_verify_letter('#')
		name = self.read_word()
		return name.lower()

	def load_shops(self):
		while True:
			keeper = self.read_number()
			if keeper == 0:
				break
			shop = RomShop(keeper=keeper)
			self.area.shops.append(shop)
			for iTrade in range(self.MAX_TRADES):
				shop.buy_type.append(self.read_number())
			shop.profit_buy = self.read_number()
			shop.profit_sell = self.read_number()
			shop.h=open_hour = self.read_number()
			shop.close_hour = self.read_number()
			self.read_to_eol()

	def load_helps(self):
		while True:
			level = self.read_number()
			keyword = self.read_string()
			if keyword[0] == '$':
				break
			help = Help(level=level, keyword=keyword)
			self.area.helps.append(help)
			help.text = self.read_string()

	def jump_to_section(self, section_name):
		self.index = self.data.find('#'+section_name.upper()) + len(section_name) + 1

	def parse_fail(self, message):
		backwards = self.data[:self.index]
		lineno = backwards.count('\n') + 1
		col = backwards[::-1].find('\n')
		message = self.filename + " line " + str(lineno) + " col " + str(col) + ": " + message
		raise ParseError(message)

	def surrounding_text(self, window=50):
		return self.data[self.index-window:self.index+window]

	def as_dict(self):
		return asdict(self.area, dict_factory=OrderedDict)

	def save_as_json(self):
		fname = os.path.splitext(self.filename)[0] + '.json'
		with open(fname, 'w') as f:
			json.dump(self.as_dict(), f, indent=2)


class RomAreaFile(AreaFile):

	def load_mob(self, vnum):
		logger.debug("Reading mob %d" % vnum)
		mob = RomMob(vnum=vnum)
		mob.name = self.read_string()
		mob.short_desc = self.read_string()
		mob.long_desc = self.read_string()
		mob.description = self.read_string()
		mob.race = self.read_string()
		mob.act = self.read_flag()
		mob.affected_by = self.read_flag()
		mob.alignment = self.read_number()
		mob.group = self.read_number()
		mob.level = self.read_number()
		mob.hitroll = self.read_number()
		mob.hit = self.read_dice()
		mob.mana = self.read_dice()
		mob.damage = self.read_dice()
		mob.damtype = self.read_word()
		mob.ac = self.read_armor_class()
		mob.off_flags = self.read_flag()
		mob.imm_flags = self.read_flag()
		mob.res_flags = self.read_flag()
		mob.vuln_flags = self.read_flag()
		mob.start_pos = self.read_word()
		mob.default_pos = self.read_word()
		mob.sex = self.read_word()
		mob.wealth = self.read_number()
		mob.form = self.read_flag()
		mob.parts = self.read_flag()
		mob.size = self.read_word()
		mob.material = self.read_word()
		while True:
			letter = self.read_letter()
			if letter == 'F':
				word = self.read_word()
				vect = self.read_flag()
			elif letter == 'M':
				mob.mprogs.append(self.read_mprog())
			else:
				self.index -= 1
				break
		return mob

	def read_armor_class(self):
		ac = RomArmorClass()
		ac.pierce = self.read_number()
		ac.bash = self.read_number()
		ac.slash = self.read_number()
		ac.exotic = self.read_number()
		return ac

	def read_mprog(self):
		mprog = RomMobprog()
		mprog.trig_type = self.read_word()
		mprog.vnum = self.read_number()
		mprog.trig_phrase = self.read_string()
		return mprog


	def read_room_data(self, room):
		while True:
			letter = self.read_letter()
			if letter == 'S':
				break
			if letter == 'H':
				room.heal_rate = self.read_number()
			elif letter == 'M':
				room.mana_rate = self.read_number()
			elif letter == 'C':
				room.clan = self.read_string()
			elif letter == 'D':
				room.exits.append(self.read_exit())
			elif letter == 'E':
				room.extra_descriptions.append(self.read_extra_descr())
			elif letter == 'O':
				room.owner = self.read_string()
			else:
				self.parse_fail("Don't know how to process room attribute: %s" % letter)
		return room


	def load_object(self, vnum):
		logger.debug("Reading object %d" % vnum)
		obj = RomObject(vnum=vnum)
		obj.name = self.read_string()
		obj.short_desc = self.read_string()
		obj.description = self.read_string()
		obj.material = self.read_string()
		obj.item_type = self.read_word()
		obj.extra_flags = self.read_flag()
		obj.wear_flags = self.read_flag()
		if obj.item_type == 'weapon':
			obj.value = [self.read_word(), self.read_number(), self.read_number(), self.read_word(), self.read_flag(), ]
		elif obj.item_type == 'container':
			obj.value = [self.read_number(), self.read_flag(), self.read_number(), self.read_number(), self.read_number(), ]
		elif obj.item_type == 'drink' or obj.item_type == 'fountain':
			obj.value = [self.read_number(), self.read_number(), self.read_word(), self.read_number(), self.read_number(), ]
		elif obj.item_type == 'wand' or obj.item_type == 'staff':
			obj.value = [self.read_number(), self.read_number(), self.read_number(), self.read_word(), self.read_number(), ]
		elif obj.item_type in ('potion', 'pill', 'scroll'):
			obj.value = [self.read_number(), self.read_word(), self.read_word(), self.read_word(), self.read_word(), ]
		else:
			obj.value = [self.read_flag(), self.read_flag(), self.read_flag(), self.read_flag(), self.read_flag(), ]
		obj.level = self.read_number()
		obj.weight = self.read_number()
		obj.cost = self.read_number()
		letter = self.read_letter()
		if letter == 'P':
			obj.condition = 100
		elif letter == 'G':
			obj.condition = 90
		elif letter == 'A':
			obj.condition = 75
		elif letter == 'W':
			obj.condition = 50
		elif letter == 'D':
			obj.condition = 25
		elif letter == 'B':
			obj.condition = 10
		elif letter == 'R':
			obj.condition = 0
		else:
			self.parse_fail("Unknown condition for object: %s" % letter)
		while True:
			letter = self.read_letter()
			if letter == 'A':
				af = RomAffectData()
				af.where = 'TO_OBJECT',
				af.type = -1
				af.level = obj.level
				af.duration = -1
				af.location = self.read_number()
				af.modifier = self.read_number()
				obj.affected.append(af)
			elif letter == 'F':
				af = RomAffectData()
				letter = self.read_letter()
				if letter == 'A':
					af.where = 'TO_AFFECTS'
				elif letter == 'I':
					af.where = 'TO_IMMUNE'
				elif letter == 'R':
					af.where = 'TO_RESIST'
				elif letter == 'V':
					af.where = 'TO_VULN'
				else:
					self.parse_fail("Bad where on flag set")
				af.type = -1
				af.level = obj.level
				af.duration = -1
				af.location = self.read_number()
				af.modifier = self.read_number()
				af.bitvector = self.read_flag()
			elif letter == 'E':
				obj.extra_descriptions.append(self.read_extra_descr())
			else:
				self.index -= 1
				break
		return obj

	def read_area_metadata(self):
		self.area.original_filename = self.read_string()
		self.area.name = self.read_string()
		self.area.metadata = self.read_string()
		self.area.first_vnum = self.read_number()
		self.area.last_vnum = self.read_number()


@attributes
class MudBase(object):
	name = attr(default="")
	vnum = attr(default=0)
	description = attr(default="")
	extra_descriptions = attr(default=Factory(list))

@attributes
class MercObject(MudBase):
	short_desc = attr(default="")
	item_type = attr(default=-1)
	extra_flags = attr(default=0)
	wear_flags = attr(default=0)
	cost = attr(default=0)
	level = attr(default=0)
	weight = attr(default=0)
	affected = attr(default=Factory(list))
	value = attr(default=Factory(list))

@attributes
class MercAffectData(object):
	type = attr(default=--1)
	duration = attr(default=-1)
	location = attr(default=-1)
	modifier = attr(default=-1)
	bitvector = attr(default=0)

@attributes
class RomObject(MudBase):
	short_desc = attr(default="")
	material = attr(default="")
	item_type = attr(default=None)
	level = attr(default=0)
	weight = attr(default=0)
	condition = attr(default=100)
	cost = attr(default=0)
	extra_flags = attr(default=0)
	wear_flags = attr(default=0)
	affected = attr(default=Factory(list))
	value = attr(default=Factory(list))



@attributes
class RomArmorClass(object):
	pierce = attr(default=0)
	bash = attr(default=0)
	slash = attr(default=0)
	exotic = attr(default=0)

@attributes
class Dice(object):
	number = attr(default=0)
	type = attr(default=0)
	bonus = attr(default=0)

@attributes
class RomMobprog(object):
	trig_type = attr(default=None)
	vnum = attr(default=-1)
	trig_phrase = attr(default=None)


@attributes
class RomCharacter(RomObject):
	long_desc = attr(default="")
	race = attr(default="")
	group = attr(default=0)
	hitrol = attr(default=0)
	hit = attr(default=Factory(Dice))
	mana = attr(default=Factory(Dice))
	damage = attr(default=Factory(Dice))
	damtype = attr(default="")
	ac = attr(default=Factory(RomArmorClass))

@attributes
class RomMob(RomCharacter, RomObject):
	shop = attr(default=None)
	alignment = attr(default=0)
	off_flags = attr(default=0)
	imm_flags = attr(default=0)
	res_flags = attr(default=0)
	vuln_flags = attr(default=0)
	start_pos = attr(default=None)
	default_pos = attr(default=None)
	sex = attr(default=0)
	wealth = attr(default=0)
	form = attr(default=None)
	parts = attr(default=0)
	size = attr(default=None)
	mprogs = attr(default=Factory(list))

@attributes
class RomAffectData(object):
	where = attr(default=None)
	type = attr(default=None)
	level = attr(default=None)
	duration = attr(default=None)
	location = attr(default=None)
	modifier = attr(default=None)
	bitvector = attr(default=0)

@attributes
class MercArea(object):
	metadata = attr(default="")
	helps = attr(default=Factory(list))
	rooms = attr(default=Factory(OrderedDict))
	mobs = attr(default=Factory(OrderedDict))
	objects = attr(default=Factory(OrderedDict))
	resets = attr(default=Factory(list))
	specials = attr(default=Factory(list))
	shops = attr(default=Factory(list))



@attributes
class RomArea(object):
	name = attr(default="")
	metadata = attr(default="")
	original_filename = attr(default="")
	first_vnum = attr(default=-1)
	last_vnum = attr(default=-1)
	helps = attr(default=Factory(list))
	rooms = attr(default=Factory(OrderedDict))
	mobs = attr(default=Factory(OrderedDict))
	objects = attr(default=Factory(OrderedDict))
	resets = attr(default=Factory(list))
	specials = attr(default=Factory(list))
	shops = attr(default=Factory(list))

@attributes
class Room(MudBase):
	owner = attr(default=None)
	area = attr(default=None)
	area_number = attr(default=0, repr=False)
	room_flags = attr(default=0)
	sector_type = attr(default=0)
	heal_rate = attr(default=100)
	mana_rate = attr(default=100)
	exits = attr(default=Factory(list))

@attributes
class ExtraDescription(object):
	keyword = attr(default="")
	description = attr(default="")

@attributes
class RomShop(object):
	keeper = attr(default=0)
	buy_type = attr(default=Factory(list))
	profit_buy = attr(default=0)
	profit_sell = attr(default=0)
	open_hour = attr(default=0)
	close_hour = attr(default=0)

@attributes
class RomSpecial(object):
	command = attr(default=None)
	arg1 = attr(default=None)
	arg2 = attr(default=None)

@attributes
class SmaugArea(RomArea):
	resetmsg = attr(default="")
	high_economy = attr(default=0)
	low_economy = attr(default=0)


@attributes
class SmaugRoom(Room):
	tele_delay = attr(default=0)
	tele_vnum = attr(default=0)
	tunnel = attr(default=None)
	max_weight = attr(default=None)
	light = attr(default=0)


@attributes
class Exit(object):
	keyword = attr(default="")
	description = attr(default="")
	door = attr(default=None)
	exit_info = attr(default=0)
	rs_flags = attr(default=0)
	key = attr(default=0)
	destination = attr(default=None)

@attributes
class Reset(object):
	command = attr(default=None)
	arg1 = attr(default=None)
	arg2 = attr(default=None)
	arg3 = attr(default=None)
	arg4 = attr(default=None)

@attributes
class Help(object):
	level = attr(default=0)
	keyword = attr(default="")
	text = attr(default="")



class MercAreaFile(AreaFile):
	area_type = MercArea

	def load_mob(self, vnum):
		logger.debug("Reading object %d" % vnum)
		mob = RomMob(vnum=vnum)
		mob.name = self.read_string()
		mob.short_desc = self.read_string()
		mob.long_desc = self.read_string()
		mob.description = self.read_string()
		mob.act = self.read_number()
		mob.affected_by = self.read_number()
		mob.alignment = self.read_number()
		letter = self.read_letter()
		mob.level = self.read_number()
		mob.hitroll = self.read_number()
		mob.ac = self.read_number()
		mob.hit = self.read_dice()
		mob.dam = self.read_dice()
		mob.gold = self.read_number()
		self.read_number() #xp can't be used!
		self.read_number() # position
		self.read_number() # start pos
		mob.sex = self.read_number()
		if letter != 'S':
			self.parse_faile("Vnum %d non S" % vnum)
		return mob

	def read_room_data(self, room):
		logger.debug("Reading room data for room %d" % room.vnum)
		while True:
			letter = self.read_letter()
			if letter == 'S':
				break
			if letter == 'D':
				room.exits.append(self.read_exit())
			elif letter == 'E':
				room.extra_descriptions.append(self.read_extra_descr())
			else:
				self.parse_fail("Room %d has flag %s not DES" % (room.vnum, letter))

	def load_object(self, vnum):
		logger.debug("Reading object %d" % vnum)
		obj = MercObject(vnum=vnum)
		obj.name = self.read_string()
		obj.short_desc = self.read_string()
		obj.description = self.read_string()
		self.read_string() # Action Description, unused
		obj.item_type = self.read_number()
		obj.extra_flags = self.read_flag()
		obj.wear_flags = self.read_flag()
		obj.value = [self.read_number(), self.read_number(), self.read_number(), self.read_number()]
		obj.weight = self.read_number()
		obj.cost = self.read_number()
		self.read_number() # cost per day
		while True:
			letter = self.read_letter()
			if letter == 'A':
				aff = MercAffectData()
				obj.affected.append(aff)
				aff.type = -1
				aff.duration = -1
				aff.location = self.read_number()
				aff.modifier = self.read_number()
			elif letter == 'E':
				obj.extra_descriptions.append(self.read_extra_descr())
			else:
				self.index -= 1
				break
		return obj

	def read_area_metadata(self):
		self.area.metadata = self.read_string()


class SmaugAreaFile(RomAreaFile):
	area_type = SmaugArea

	def load_resetmsg(self):
		self.area.resetmsg = self.read_string()

	def load_economy(self):
		self.area.high_economy = self.read_number()
		self.area.low_economy = self.read_number()

	def load_room(self, vnum):
		logger.debug("Reading room %d" % vnum)
		room = Room(vnum=vnum)
		room.name = self.read_string()
		room.description = self.read_string()
		room.area_number = self.read_number()
		room.room_flags = self.read_flag()
		line = self.read_line()
		#room.sector_type, room.tele_delay, room.tele_vnum, room.tunnel, room.max_weight = map(int, line.split())
		self.read_room_data(room)
		return room

	def read_line(self):
		return self.read_to_eol()



def flag_convert(letter):
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

if __name__ == '__main__':
	area_file = MercAreaFile('cloudymt.are')
	area_file.load_sections()
	area = area_file.area
	import pprint
	from attr import asdict
	pprint.pprint(asdict(area))

