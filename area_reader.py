import logging
logger = logging.getLogger('area_reader')
logging.basicConfig(level=logging.INFO)

from collections import OrderedDict
import enum
import io
import json
import random
import os
from attr import asdict, attr, attributes, Factory
from operator import setitem

from constants import *

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
		self.current_section_name = "N/A"

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
		res = self.read_until('~')
		self.advance()
		return res
		
	def read_number(self):
		self.skip_whitespace()
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
		#self.advance()
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

	def load_vnum_section(self, section_object_type):
		while True:
			vnum = self.read_vnum()
			if vnum == 0:
				break
			yield self.read_object(section_object_type, vnum=vnum)

	def read_object(self, object_type, **kwargs):
		return object_type.read(reader=self, **kwargs)

	def read_vnum(self):
		self.skip_whitespace()
		self.read_and_verify_letter('#')
		vnum = self.read_number()
		return vnum

	def read_flat_section(self, object_type):
		while True:
			letter = self.read_letter()
			if letter == 'S':
				break
			if letter == '*': # Comment
				self.read_to_eol()
				continue
			yield object_type.read(reader=self, letter=letter)

	def read_area_metadata(self):
		raise NotImplementedError

	def load_economy(self):
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
			'economy': self.load_economy,
		}
		while True:
			section_name = self.read_section_name()
			self.current_section_name = section_name
			if section_name == '$':
				return
			reader = readers.get(section_name)
			if reader is None:
				self.skip_section(section_name)
			else:
				logger.info("Processing section %s" % section_name)
				readers[section_name]()

	def skip_section(self, section_name):
		logger.debug("Skipping section %s", section_name)
		self.read_until('#')

	def read_section_name(self):
		self.read_and_verify_letter('#')
		name = self.read_word()
		return name.lower()

	def load_rooms(self):
		for item in self.load_vnum_section(Room):
			setitem(self.area.rooms, item.vnum, item)

	def load_objects(self):
		for item in self.load_vnum_section(Item):
			setitem(self.area.objects, item.vnum, item)

	def load_resets(self):
		for reset in self.read_flat_section(Reset):
			self.area.resets.append(reset)
			
	def load_specials(self):
		for special in self.read_flat_section(Special):
			self.area.specials.append(special)

	def load_shops(self):
		while True:
			keeper = self.read_number()
			if keeper == 0:
				break
			logger.debug("Reading shop with keeper %d", keeper)
			shop = RomShop(keeper=keeper)
			for iTrade in range(self.MAX_TRADES):
				shop.buy_type.append(self.read_number())
			shop.profit_buy = self.read_number()
			shop.profit_sell = self.read_number()
			shop.open_hour = self.read_number()
			shop.close_hour = self.read_number()
			self.area.shops.append(shop)
			self.read_to_eol()

	def load_helps(self):
		while True:
			level = self.read_number()
			keyword = self.read_string()
			if keyword[0] == '$':
				break
			logger.debug("Reading help with keyword %s", keyword)
			help = Help(level=level, keyword=keyword)
			help.text = self.read_string()
			self.area.helps.append(help)

	def jump_to_section(self, section_name):
		self.index = self.data.find('#'+section_name.upper()) + len(section_name) + 1

	def parse_fail(self, message):
		backwards = self.data[:self.index]
		lineno = backwards.count('\n') + 1
		col = backwards[::-1].find('\n')
		message = str(self.filename) + " line " + str(lineno) + " col " + str(col) + " in section " + self.current_section_name + ": " + message
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

	def load_mobiles(self):
		for mob in self.load_vnum_section(RomMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for item in self.load_vnum_section(RomItem):
			setitem(self.area.objects, item.vnum, item)

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
class Item(MudBase):
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
class RomItem(Item):
	material = attr(default="")
	condition = attr(default=100)

	@classmethod
	def read(cls, reader, vnum=None, **kwargs):
		logger.debug("Reading object %d", vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		description = reader.read_string()
		material = reader.read_string()
		item_type = reader.read_word()
		extra_flags = reader.read_flag()
		wear_flags = reader.read_flag()
		if item_type == 'weapon':
			value = [reader.read_word(), reader.read_number(), reader.read_number(), reader.read_word(), reader.read_flag(), ]
		elif item_type == 'container':
			value = [reader.read_number(), reader.read_flag(), reader.read_number(), reader.read_number(), reader.read_number(), ]
		elif item_type == 'drink' or item_type == 'fountain':
			value = [reader.read_number(), reader.read_number(), reader.read_word(), reader.read_number(), reader.read_number(), ]
		elif item_type == 'wand' or item_type == 'staff':
			value = [reader.read_number(), reader.read_number(), reader.read_number(), reader.read_word(), reader.read_number(), ]
		elif item_type in ('potion', 'pill', 'scroll'):
			value = [reader.read_number(), reader.read_word(), reader.read_word(), reader.read_word(), reader.read_word(), ]
		else:
			value = [reader.read_flag(), reader.read_flag(), reader.read_flag(), reader.read_flag(), reader.read_flag(), ]
		level = reader.read_number()
		weight = reader.read_number()
		cost = reader.read_number()
		letter = reader.read_letter()
		if letter == 'P':
			condition = 100
		elif letter == 'G':
			condition = 90
		elif letter == 'A':
			condition = 75
		elif letter == 'W':
			condition = 50
		elif letter == 'D':
			condition = 25
		elif letter == 'B':
			condition = 10
		elif letter == 'R':
			condition = 0
		else:
			reader.parse_fail("Unknown condition for object: %s" % letter)
		affected = []
		extra_descriptions = []
		while True:
			letter = reader.read_letter()
			if letter == 'A':
				af = RomAffectData()
				af.where = 'TO_OBJECT',
				af.type = -1
				af.level = level
				af.duration = -1
				af.location = reader.read_number()
				af.modifier = reader.read_number()
				affected.append(af)
			elif letter == 'F':
				af = RomAffectData()
				letter = reader.read_letter()
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
				af.level = level
				af.duration = -1
				af.location = reader.read_number()
				af.modifier = reader.read_number()
				af.bitvector = reader.read_flag()
				affected.append(af)
			elif letter == 'E':
				extra_descriptions.append(ExtraDescription.read(reader=reader))
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, description=description, material=material, item_type=item_type, extra_flags=extra_flags, wear_flags=wear_flags, value=value, level=level, weight=weight, cost=cost, condition=condition, affected=affected, extra_descriptions=extra_descriptions)


@attributes
class RomArmorClass(object):
	pierce = attr(default=0)
	bash = attr(default=0)
	slash = attr(default=0)
	exotic = attr(default=0)

	@classmethod
	def read(cls, reader, **kw):
		pierce = reader.read_number()
		bash = reader.read_number()
		slash = reader.read_number()
		exotic = reader.read_number()
		return cls(pierce=pierce, bash=bash, slash=slash, exotic=exotic, **kw)

@attributes
class Dice(object):
	number = attr(default=0, type=int)
	sides = attr(default=0, type=int)
	bonus = attr(default=0, type=int)

	@classmethod
	def read(cls, reader, **kwargs):
		number = reader.read_number()
		reader.read_letter() #D
		sides = reader.read_number()
		bonus = reader.read_number()
		return cls(number=number, sides=sides, bonus=bonus, **kwargs)

	def roll(self):
		score = 0
		for roll in range(self.number):
			score += random.randrange(1, self.sides)
		score += self.bonus
		return score
		
@attributes
class RomMobprog(object):
	trig_type = attr(default=None)
	vnum = attr(default=-1)
	trig_phrase = attr(default=None)

	@classmethod
	def read(cls, reader, **kwargs):
		trig_type = self.read_word()
		vnum = self.read_number()
		trig_phrase = self.read_string()
		return cls(trig_type=trig_type, vnum=vnum, trig_phrase=trig_phrase)


@attributes
class RomCharacter(RomItem):
	long_desc = attr(default="", type=str)
	race = attr(default="", type=str)
	group = attr(default=0)
	hitrol = attr(default=0)
	hit = attr(default=Factory(Dice), type=Dice)
	mana = attr(default=Factory(Dice), type=Dice)
	damage = attr(default=Factory(Dice), type=Dice)
	damtype = attr(default="")
	ac = attr(default=Factory(RomArmorClass), type=RomArmorClass)
	act = attr(default=0, type=ROM_ACT_TYPES, converter=ROM_ACT_TYPES)
	affected_by = attr(default=0, type=AFFECTED_BY, converter=AFFECTED_BY)
	hitroll = attr(default=0)


@attributes
class RomMob(RomCharacter, RomItem):
	shop = attr(default=None)
	alignment = attr(default=0)
	off_flags = attr(default=0, type=AFFECTS, converter=AFFECTS)
	imm_flags = attr(default=0, type=AFFECTS, converter=AFFECTS)
	res_flags = attr(default=0, type=AFFECTS, converter=AFFECTS)
	vuln_flags = attr(default=0, type=AFFECTS, converter=AFFECTS)
	start_pos = attr(default=None)
	default_pos = attr(default=None)
	sex = attr(default=0)
	wealth = attr(default=0)
	form = attr(default=0, type=FORMS, converter=FORMS)
	parts = attr(default=0, type=PARTS, converter=PARTS)
	size = attr(default=None)
	mprogs = attr(default=Factory(list))

	@classmethod
	def read(cls, reader, vnum, **kwargs):
		logger.debug("Reading mob %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		long_desc = reader.read_string()
		description = reader.read_string()
		race = reader.read_string()
		act = reader.read_flag()
		affected_by = reader.read_flag()
		alignment = reader.read_number()
		group = reader.read_number()
		level = reader.read_number()
		hitroll = reader.read_number()
		hit = Dice.read(reader=reader)
		mana = Dice.read(reader=reader)
		damage = Dice.read(reader=reader)
		damtype = reader.read_word()
		ac = RomArmorClass.read(reader=reader)
		off_flags = reader.read_flag()
		imm_flags = reader.read_flag()
		res_flags = reader.read_flag()
		vuln_flags = reader.read_flag()
		start_pos = reader.read_word()
		default_pos = reader.read_word()
		sex = reader.read_word()
		wealth = reader.read_number()
		form = reader.read_flag()
		parts = reader.read_flag()
		size = reader.read_word()
		material = reader.read_word()
		mprogs = []
		while True:
			letter = reader.read_letter()
			if letter == 'F':
				word = reader.read_word()
				vect = reader.read_flag()
			elif letter == 'M':
				mprogs.append(RomMobprog.read(reader=reader)())
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc, description=description, race=race, affected_by=affected_by, alignment=alignment, group=group, level=level, hitroll=hitroll, hit=hit, mana=mana, damage=damage, damtype=damtype, ac=ac, off_flags=off_flags, imm_flags=imm_flags, res_flags=res_flags, start_pos=start_pos, default_pos=default_pos, sex=sex, wealth=wealth, form=form, parts=parts, size=size, material=material, mprogs=mprogs)

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
	sector_type = attr(default=0, type=SECTOR_TYPES) #FIXME
	heal_rate = attr(default=100, type=int)
	mana_rate = attr(default=100, type=int)
	exits = attr(default=Factory(list))

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading room with vnum %d", vnum)
		name = reader.read_string()
		description = reader.read_string()
		area_number = reader.read_number()
		room_flags = reader.read_flag()
		sector_type = reader.read_number()
		room = cls(vnum=vnum, name=name, description=description, area_number=area_number, room_flags=room_flags, sector_type=sector_type)
		room.read_metadata(reader)
		return room

	def read_metadata(self, reader):
		while True:
			letter = reader.read_letter()
			if letter == 'S':
				break
			if letter == 'H':
				self.heal_rate = reader.read_number()
			elif letter == 'M':
				self.mana_rate = reader.read_number()
			elif letter == 'C':
				self.clan = reader.read_string()
			elif letter == 'D':
				self.exits.append(Exit.read(reader=reader))
			elif letter == 'E':
				self.extra_descriptions.append(ExtraDescription.read(reader=reader))
			elif letter == 'O':
				self.owner = reader.read_string()
			else:
				reader.parse_fail("Don't know how to process room attribute: %s" % letter)

@attributes
class MercRoom(Room):

	@classmethod
	def read_metadata(cls, reader):
		logger.debug("Reading room data for %d" % cls.vnum)
		while True:
			letter = reader.read_letter()
			if letter == 'S':
				break
			if letter == 'D':
				cls.exits.append(Exit.read(reader=reader))
			elif letter == 'E':
				cls.extra_descriptions.append(ExtraDescription.read(reader=reader))
			else:
				reader.parse_fail("cls %d has flag %s not DES" % (cls.vnum, letter))

@attributes
class ExtraDescription(object):
	keyword = attr(default="")
	description = attr(default="")

	@classmethod
	def read(cls, reader, **kwargs):
		logger.debug("Reading extra description")
		keyword = reader.read_string()
		description = reader.read_string()
		return cls(keyword=keyword, description=description, **kwargs)

@attributes
class RomShop(object):
	keeper = attr(default=0)
	buy_type = attr(default=Factory(list))
	profit_buy = attr(default=0)
	profit_sell = attr(default=0)
	open_hour = attr(default=0)
	close_hour = attr(default=0)

@attributes
class Special(object):
	command = attr(default=None)
	arg1 = attr(default=None)
	arg2 = attr(default=None)
	comment = attr(default=None)

	@classmethod
	def read(cls, reader, letter, **kwargs):
		command = letter
		arg1 = reader.read_number()
		arg2 = reader.read_word()
		comment = reader.read_to_eol()
		return cls(command=command,arg1=arg1, arg2=arg2)

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
	door = attr(default=None, type=EXIT_DIRECTIONS)
	exit_info = attr(default=0)
	rs_flags = attr(default=0)
	key = attr(default=0)
	destination = attr(default=None)

	@classmethod
	def read(cls, reader, **kwargs):
		logger.debug("Reading exit")
		locks = 0
		door = EXIT_DIRECTIONS(reader.read_number())
		description = reader.read_string()
		keyword = reader.read_string()
		exit_info = 0
		locks = reader.read_number()
		key = reader.read_number()
		destination = reader.read_number()
		return cls(door=door, description=description, keyword=keyword, key=key, destination=destination)

@attributes
class Reset(object):
	command = attr(default=None)
	arg1 = attr(default=None)
	arg2 = attr(default=None)
	arg3 = attr(default=None)
	arg4 = attr(default=None)
	comment = attr(default=None)

	@classmethod
	def read(cls, reader, letter):
		command = letter
		reader.read_number() #if_flag
		arg1 = reader.read_number()
		arg2 = reader.read_number()
		if letter == 'G' or letter == 'R':
			arg3 = 0
		else:
			arg3 = reader.read_number()
		if letter == 'P' or letter == 'M':
			arg4 = 0
		else:
			arg4 = reader.read_number()
		reader.index -= 1
		comment = reader.read_to_eol()
		return cls(command=command, arg1=arg1, arg2=arg2, arg3=arg3, arg4=arg4, comment=comment)

@attributes
class MercReset(object):
	command = attr(default=None)
	arg1 = attr(default=None)
	arg2 = attr(default=None)
	arg3 = attr(default=None)
	arg4 = attr(default=None)
	arg5 = attr(default=None)
	comment = attr(default=None)

	@classmethod
	def read(cls, reader, letter):
		command = letter
		reader.read_number() #if_flag
		arg1 = reader.read_number()
		arg2 = reader.read_number()
		if letter == 'G' or letter == 'R':
			arg3 = 0
		else:
			arg3 = reader.read_number()
		if letter == 'P' or letter == 'M':
			arg4 = 0
		else:
			arg4 = reader.read_number()
		arg5 = reader.read_number()
		reader.index -= 1
		comment = reader.read_to_eol()
		return cls(command=command, arg1=arg1, arg2=arg2, arg3=arg3, arg4=arg4, arg5=arg5, comment=comment)


@attributes
class Help(object):
	level = attr(default=0)
	keyword = attr(default="")
	text = attr(default="")

@attributes
class MercMob(RomMob):
	act = attr(default=0, type=MERC_ACT_TYPES)

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading Mob %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		long_desc = reader.read_string()
		description = reader.read_string()
		act = reader.read_flag()
		affected_by = reader.read_flag()
		alignment = reader.read_flag()
		letter = reader.read_letter()
		level = reader.read_number()
		hitroll = reader.read_number()
		ac = reader.read_number()
		hit = Dice.read(reader=reader)
		damage = Dice.read(reader=reader)
		wealth = reader.read_number()
		reader.read_number() #xp can't be used!
		default_pos = reader.read_number() # position
		start_pos = reader.read_number() # start pos
		sex = reader.read_number()
		if letter != 'S':
			reader.parse_fail("Reading MOB vnum %d non S: %s" % (vnum, letter))
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc, description=description, act=act, affected_by=affected_by, alignment=alignment, level=level, hitroll=hitroll, ac=ac, hit=hit, damage=damage, wealth=wealth, start_pos=start_pos, default_pos=default_pos, sex=sex)

@attributes
class MercItem(Item):

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading object %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		description = reader.read_string()
		reader.read_string() # Action Description, unused
		item_type = reader.read_number()
		extra_flags = reader.read_flag()
		wear_flags = reader.read_flag()
		value = [reader.read_number(), reader.read_number(), reader.read_number(), reader.read_number()]
		weight = reader.read_number()
		cost = reader.read_number()
		reader.read_number() # cost per day
		affected = []
		extra_descriptions = []
		while True:
			letter = reader.read_letter()
			if letter == 'A':
				aff = MercAffectData()
				affected.append(aff)
				aff.type = -1
				aff.duration = -1
				aff.location = reader.read_number()
				aff.modifier = reader.read_number()
			elif letter == 'E':
				extra_descriptions.append(ExtraDescription.read(reader=reader))
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, description=description, item_type=item_type, extra_flags=extra_flags, wear_flags=wear_flags, value=value, weight=weight, cost=cost, affected=affected, extra_descriptions=extra_descriptions)

class MercAreaFile(AreaFile):
	area_type = MercArea

	def load_mobiles(self):
		for mob in self.load_vnum_section(MercMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for item in self.load_vnum_section(MercItem):
			setitem(self.area.objects, item.vnum, item)

	def load_resets(self):
		for reset in self.read_flat_section(MercReset):
			self.area.resets.append(reset)

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

if __name__ == '__main__':
	area_file = RomAreaFile('under2.are')
	area_file.load_sections()
	area = area_file.area
	import pprint
	from attr import asdict
#	pprint.pprint(asdict(area))

