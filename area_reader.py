#! /usr/bin/env python3.11

import logging
logger = logging.getLogger('area_reader')
logging.basicConfig(level=logging.INFO)

from collections import OrderedDict
import enum
import io
import json
import random
import os
import sys
from typing import List, Dict, Optional
from attr import attr, attributes, Factory, fields
from cattr import converters
from operator import setitem

from constants import *

def field(type=None, read=True, on_read=None, original_type=None, only_if=None, *args, **kwargs):
	metadata = dict(read=read)
	if on_read:
		metadata['on_read'] = on_read
	if original_type:
		metadata['original_type'] = original_type
	if only_if:
		metadata['only_if'] = only_if
	return attr(type=type, metadata=metadata, *args, **kwargs)

class ParseError(Exception): pass

class Letter(str):
	pass

class Word(str):
	pass

class VNum(int):
	pass

class AreaFile(object):
	area_type = None
	MAX_TRADES = 5

	def __init__(self, filename):
		super(AreaFile, self).__init__()
		self.file = io.open(filename, mode='rt', encoding='ascii')
		self.index = 0
		self.data = self.file.read()
		# Normalize Windows CRLF to Unix LF
		self.data = self.data.replace('\r\n', '\n').replace('\r', '\n')
		self.filename = filename
		self.file.close()
		area_type = self.area_type or RomArea
		self.area = area_type()
		self.current_section_name = "N/A"
		self.readers = {
			Word: self.read_word,
			Letter: self.read_letter,
			str: self.read_string,
			int: self.read_number,
			enum.IntFlag: self.read_flag,
			RomArmorClass: lambda: self.read_object_from_fields(RomArmorClass),
		}

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
		# Handle +, -, or +- (plus followed by minus)
		if self.current_char == '+':
			self.advance()
			# Check for +- pattern (negative number after plus)
			if self.current_char == '-':
				sign = True
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

	def read_dice_or_number(self):
		"""Read either a dice expression (NdN+N) or a simple number.
		Returns a Dice object. Simple numbers become Dice(0, 0, number)."""
		self.skip_whitespace()
		start_index = self.index
		# Read the first number
		number = self.read_number()
		# Check if next char is 'd' or 'D' (dice expression)
		if self.current_char.lower() == 'd':
			self.advance()  # consume 'd'
			sides = self.read_number()
			bonus = self.read_number()
			return Dice(number=number, sides=sides, bonus=bonus)
		else:
			# Simple number - return as Dice(0, 0, number)
			return Dice(number=0, sides=0, bonus=number)

	def read_to_eol(self):
		return self.read_until('\n')

	def read_to_blank_line(self):
		"""Read until a blank line (double newline). Used for multi-line descriptions."""
		lines = []
		while True:
			line = self.read_to_eol()
			if self.current_char == '\n':
				self.advance()  # Skip the newline
			# Check if next line is blank (or we're at section marker)
			if not line.strip() or self.current_char == '#' or self.current_char == '$':
				break
			lines.append(line)
		return '\n'.join(lines)

	def read_until(self, endchar):
		ahead = self.data.find(endchar, self.index)
		result = self.data[self.index:ahead]
		self.index = ahead
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
		if hasattr(object_type, 'read'):
			return object_type.read(reader=self, **kwargs)
		return self.read_object_by_fields(object_type, **kwargs)

	def read_object_by_fields(self, object_type, **kwargs):
		f = fields(object_type)
		read = {}
		always_read = lambda context: True
		unchanged = lambda value: value
		for field in f:
			field_type = field.metadata.get('original_type', field.type)
			if field.metadata.get('read') == False:
				continue
			if issubclass(field_type, enum.IntFlag):
				field_type = enum.IntFlag
			elif issubclass(field_type, int) and field_type is not int:
				# Handle int subclasses like VNum
				field_type = int
			reader = self.readers.get(field_type)
			if reader is None:
				self.parse_fail("Could not find a reader for field type %r" % field_type)
			only_if = field.metadata.get('only_if', always_read)
			should_read = only_if(context=read)
			if not should_read:
				continue
			on_read = field.metadata.get('on_read', unchanged)
			read[field.name] = on_read(reader())
		read.update(kwargs)
		return object_type(**read)

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
				comment = self.read_to_eol()
				yield object_type(comment=comment)
				continue
			yield object_type.read(reader=self, letter=letter)

	def read_area_metadata(self):
		raise NotImplementedError

	def load_economy(self):
		raise NotImplementedError

	def load_sections(self):
		readers = {
			'area': self.read_area_metadata,
			'areadata': self.load_areadata,
			'mobiles': self.load_mobiles,
			'rooms': self.load_rooms,
			'objects': self.load_objects,
			'helps': self.load_helps,
			'resets': self.load_resets,
			'shops': self.load_shops,
			'specials': self.load_specials,
			'economy': self.load_economy,
			'resetmsg': self.load_resetmsg,
			'author': self.load_author,
			'ranges': self.load_ranges,
			'flags': self.load_flags,
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
				try:
					readers[section_name]()
				except Exception:
					self.parse_fail("Error reading section %r" % section_name)

	def load_areadata(self):
		"""Default: skip areadata if not implemented."""
		self.skip_section('areadata')

	def load_resetmsg(self):
		"""Default: skip resetmsg if not implemented."""
		self.read_string()

	def load_author(self):
		"""Default: skip author if not implemented."""
		self.read_string()

	def load_ranges(self):
		"""Default: skip ranges if not implemented."""
		while True:
			self.skip_whitespace()
			if self.current_char == '$':
				self.advance()
				break
			elif self.current_char == '#':
				break
			self.read_to_eol()

	def load_flags(self):
		"""Default: skip flags if not implemented."""
		self.read_number()

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
		return EnumNameConverter().unstructure(self.area)

	def as_json(self, indent=None):
		return json.dumps(self.as_dict(), indent=indent)

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
class ExtraDescription(object):
	keyword = field(default='', type=str)
	description = field(default='', type=str)

@attributes
class MudBase(object):
	vnum = field(default=0, type=VNum, read=False)
	name = field(default="", type=str)
	description = field(default='', type=str)
	extra_descriptions = attr(default=Factory(list), type=List[ExtraDescription])

@attributes
class Item(MudBase):
	short_desc = field(default='', type=str)
	item_type = field(default=-1, type=int)
	extra_flags = field(default=0, type=int)
	wear_flags = field(default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS)
	cost = field(default=0, type=int)
	level = field(default=0, type=int)
	weight = field(default=0, type=int)
	affected = attr(default=Factory(list))
	value = attr(default=Factory(list), type=List)

@attributes
class MercAffectData(object):
	type = attr(default=--1)
	duration = attr(default=-1)
	location = attr(default=-1)
	modifier = attr(default=-1)
	bitvector = attr(default=0)

@attributes
class RomItem(Item):

	@staticmethod
	def convert_condition(letter):
		condition = -1
		conditions = {
			'P': 100,
			'G': 90,
			'A': 75,
			'W': 50,
			'D': 25,
			'B': 10,
			'R': 0,
		}
		condition = conditions[letter]
		return condition

	material = field(default='', type=str)
	condition = field(default=100, type=int, original_type=Letter, on_read=convert_condition)

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
		condition = cls.convert_condition(reader.read_letter())
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
				extra_descriptions.append(reader.read_object(ExtraDescription))
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, description=description, material=material, item_type=item_type, extra_flags=extra_flags, wear_flags=wear_flags, value=value, level=level, weight=weight, cost=cost, condition=condition, affected=affected, extra_descriptions=extra_descriptions)


multiply_10 = lambda n: n * 10

@attributes
class RomArmorClass(object):
	pierce = field(default=0, type=int, on_read = multiply_10)
	bash = field(default=0, type=int, on_read=multiply_10)
	slash = field(default=0, type=int, on_read=multiply_10)
	exotic = field(default=0, type=int, on_read=multiply_10)

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
	trig_type = attr(default=None, type=Word)
	vnum = attr(default=-1, type=VNum)
	trig_phrase = attr(default=None, type=str)

@attributes
class RomCharacter(MudBase):
	short_desc = field(default='', type=str)
	long_desc = attr(default="", type=str)
	level = field(default=0, type=int)
	race = attr(default="", type=str)
	group = attr(default=0, type=int)
	hitroll = attr(default=0, type=int)
	hit = attr(default=Factory(Dice), type=Dice)
	mana = attr(default=Factory(Dice), type=Dice)
	material = field(default='', type=str)
	damage = attr(default=Factory(Dice), type=Dice)
	damtype = attr(default='', type=Word)
	ac = attr(default=Factory(RomArmorClass), type=RomArmorClass)
	act = attr(default=ROM_ACT_TYPES.IS_NPC.value, type=ROM_ACT_TYPES, converter=ROM_ACT_TYPES)
	affected_by = attr(default=0, type=AFFECTED_BY, converter=AFFECTED_BY)

mark_as_npc = lambda act_flags: ROM_ACT_TYPES(act_flags) | ROM_ACT_TYPES.IS_NPC

@attributes
class RomMob(RomCharacter):
	shop = field(default=None, read=False)
	act = field(default=0, type=ROM_ACT_TYPES, converter=ROM_ACT_TYPES)
	alignment = field(default=0, type=int)
	off_flags = attr(default=0, type=OFFENSE, converter=OFFENSE)
	imm_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	res_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	vuln_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	start_pos = attr(default=None, type=Word)
	default_pos = attr(default=None, type=Word)
	sex = attr(default='', type=Word)
	wealth = attr(default=0, type=int)
	form = attr(default=0, type=FORMS, converter=FORMS)
	parts = attr(default=0, type=PARTS, converter=PARTS)
	size = attr(default=None, type=Word)
	mprogs = field(default=Factory(list), type=Optional[List[RomMobprog]])

	@classmethod
	def read(cls, reader, vnum, **kwargs):
		logger.debug("Reading mob %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		long_desc = reader.read_string()
		description = reader.read_string()
		race = reader.read_string()
		act = ROM_ACT_TYPES(reader.read_flag()) | ROM_ACT_TYPES.IS_NPC
		affected_by = reader.read_flag()
		alignment = reader.read_number()
		group = reader.read_number()
		level = reader.read_number()
		hitroll = reader.read_number()
		hit = Dice.read(reader=reader)
		mana = Dice.read(reader=reader)
		damage = Dice.read(reader=reader)
		damtype = reader.read_word()
		ac = reader.read_object(RomArmorClass)
		off_flags = reader.read_flag()
		imm_flags = reader.read_flag()
		res_flags = reader.read_flag()
		vuln_flags = reader.read_flag()
		start_pos = reader.read_word()
		default_pos = reader.read_word()
		sex = reader.read_word()
		wealth = int(reader.read_number() / 20)
		form = reader.read_flag()
		parts = reader.read_flag()
		size = reader.read_word()
		material = reader.read_word()
		mprogs = []
		while True:
			letter = reader.read_letter()
			if letter == 'F':
				word = reader.read_word()
				vector = reader.read_flag()
				if word.startswith('act'):
					act = remove_bit(act, vector)
				elif word.startswith('aff'):
					affected_by = remove_bit(affected_by, vector)
				elif word.startswith('off'):
					off_flags = remove_bit(off_flags, vector)
				elif word.startswith('imm'):
					imm_flags = remove_bit(imm_flags, vector)
				elif word.startswith('res'):
					res_flags = remove_bit(res_flags, vector)
				elif word.startswith('vul'):
					vuln_flags = remove_bit(vuln_flags, vector)
				elif word.startswith('for'):
					form = remove_bit(form, vector)
				elif word.startswith('par'):
					parts = remove_bit(parts, vector)
				else:
					reader.parse_fail("Flag remove: flag not found: %s" % word)
			elif letter == 'M':
				mprogs.append(reader.read_object_by_fields(RomMobprog))
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc, description=description, race=race, act=act, affected_by=affected_by, alignment=alignment, group=group, level=level, hitroll=hitroll, hit=hit, mana=mana, damage=damage, damtype=damtype, ac=ac, off_flags=off_flags, imm_flags=imm_flags, res_flags=res_flags, vuln_flags=vuln_flags, start_pos=start_pos, default_pos=default_pos, sex=sex, wealth=wealth, form=form, parts=parts, size=size, material=material, mprogs=mprogs)

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
class Help(object):
	level = attr(default=0, type=int)
	keyword = attr(default='', type=Word)
	text = attr(default='', type=str)

@attributes
class Exit(object):
	keyword = attr(default='', type=Word)
	description = attr(default="", type=str)
	door = attr(default=None, type=EXIT_DIRECTIONS, converter=EXIT_DIRECTIONS)
	exit_info = attr(default=0, type=EXIT_FLAGS, converter=EXIT_FLAGS)
	rs_flags = attr(default=0, type=int)
	key = attr(default=0, type=int)
	destination = attr(default=None, type=int)

	@classmethod
	def read(cls, reader, **kwargs):
		logger.debug("Reading exit")
		locks = 0
		door = reader.read_number()
		description = reader.read_string()
		keyword = reader.read_string()
		exit_info = 0
		locks = reader.read_number()
		key = reader.read_number()
		destination = reader.read_number()
		if locks == 1:
			exit_info = EXIT_FLAGS.ISDOOR
		elif locks == 2:
			exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF
		elif locks == 3:
			exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.NOPASS
		elif locks == 4:
			exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.NOPASS | EXIT_FLAGS.PICKPROOF
		return cls(door=door, description=description, keyword=keyword, exit_info=exit_info, key=key, destination=destination)

@attributes
class Room(MudBase):
	owner = attr(default=None, type=str)
	area = attr(default=None)
	area_number = attr(default=0, type=int)
	room_flags = attr(default=0, type=ROM_ROOM_FLAGS, converter=ROM_ROOM_FLAGS)
	sector_type = attr(default=0, type=SECTOR_TYPES, converter=SECTOR_TYPES) #FIXME
	heal_rate = attr(default=100, type=int)
	mana_rate = attr(default=100, type=int)
	exits = attr(default=Factory(list), type=List[Exit])

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading room with vnum %d", vnum)
		name = reader.read_string()
		description = reader.read_string()
		area_number = reader.read_number()
		room_flags = reader.read_flag()
		sector_type = reader.read_number()
		if sector_type == -1:
			sector_type = 0
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
				self.extra_descriptions.append(reader.read_object(ExtraDescription))
			elif letter == 'O':
				self.owner = reader.read_string()
			else:
				reader.parse_fail("Don't know how to process room attribute: %s" % letter)


@attributes
class Reset(object):
	command = attr(default=None)
	arg1 = attr(default=None, type=Letter)
	arg2 = attr(default=None)
	arg3 = attr(default=None)
	arg4 = attr(default=None)
	comment = attr(default=None, type=str)

	@classmethod
	def read(cls, reader, letter):
		command = letter
		reader.read_number() #if_flag
		arg1 = reader.read_number()
		arg2 = reader.read_number()
		if letter == 'G' or letter == 'R':
			arg3 = 0
			arg4 = 0
		else:
			arg3 = reader.read_number()
			# M and P resets have a 4th argument (room_limit for M, container_limit for P)
			if letter == 'M' or letter == 'P':
				arg4 = reader.read_number()
			else:
				arg4 = 0
		reader.index -= 1
		comment = reader.read_to_eol()
		return cls(command=command, arg1=arg1, arg2=arg2, arg3=arg3, arg4=arg4, comment=comment)

@attributes
class Special(object):
	command = attr(default=None)
	arg1 = attr(default=None)
	arg2 = attr(default=None)
	comment = attr(default=None, type=str)

	@classmethod
	def read(cls, reader, letter, **kwargs):
		command = letter
		arg1 = reader.read_number()
		arg2 = reader.read_word()
		comment = reader.read_to_eol()
		return cls(command=command,arg1=arg1, arg2=arg2, comment=comment)

@attributes
class RomArea(object):
	name = attr(default="")
	metadata = attr(default="")
	original_filename = attr(default="")
	first_vnum = attr(default=-1)
	last_vnum = attr(default=-1)
	helps = attr(default=Factory(list), type=List[Help])
	rooms = attr(default=Factory(OrderedDict), type=Dict[int, Room])
	mobs = attr(default=Factory(OrderedDict))
	objects = attr(default=Factory(OrderedDict))
	resets = attr(default=Factory(list), type=List[Reset])
	specials = attr(default=Factory(list), type=List[Special])
	shops = attr(default=Factory(list))

@attributes
class MercRoom(Room):
	room_flags = attr(default=0, type=MERC_ROOM_FLAGS, converter=MERC_ROOM_FLAGS)

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
				cls.extra_descriptions.append(reader.read_object(ExtraDescription))
			else:
				reader.parse_fail("cls %d has flag %s not DES" % (cls.vnum, letter))

@attributes
class RomShop(object):
	keeper = attr(default=0, type=int)
	buy_type = attr(default=Factory(list), type=list)
	profit_buy = attr(default=0, type=int)
	profit_sell = attr(default=0, type=int)
	open_hour = attr(default=0, type=int)
	close_hour = attr(default=0, type=int)

@attributes
class SmaugMob(RomMob):
	affected_by = attr(default=0, type=SMAUG_AFFECTED_BY, converter=SMAUG_AFFECTED_BY)


@attributes
class RotMob(RomMob):
	"""ROT (Realms of Thera) mob format - has 5 values after race instead of 4."""
	extra_flag = attr(default=0, type=int)

	@classmethod
	def read(cls, reader, vnum, **kwargs):
		logger.debug("Reading ROT mob %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		long_desc = reader.read_string()
		description = reader.read_string()
		race = reader.read_string()
		# ROT format: act affected extra_flag alignment group (5 values)
		act = ROM_ACT_TYPES(reader.read_flag()) | ROM_ACT_TYPES.IS_NPC
		affected_by = reader.read_flag()
		extra_flag = reader.read_flag()  # Extra flag field in ROT
		alignment = reader.read_number()
		group = reader.read_number()
		level = reader.read_number()
		hitroll = reader.read_number()
		hit = Dice.read(reader=reader)
		mana = Dice.read(reader=reader)
		damage = Dice.read(reader=reader)
		damtype = reader.read_word()
		ac = reader.read_object(RomArmorClass)
		# ROT uses letter flags for off/imm/res/vuln
		off_flags = reader.read_flag()
		imm_flags = reader.read_flag()
		res_flags = reader.read_flag()
		vuln_flags = reader.read_flag()
		start_pos = reader.read_word()
		default_pos = reader.read_word()
		sex = reader.read_word()
		wealth = int(reader.read_number() / 20)
		form = reader.read_flag()
		parts = reader.read_flag()
		size = reader.read_word()
		material = reader.read_word()
		mprogs = []
		while True:
			letter = reader.read_letter()
			if letter == 'F':
				word = reader.read_word()
				vector = reader.read_flag()
				if word.startswith('act'):
					act = remove_bit(act, vector)
				elif word.startswith('aff'):
					affected_by = remove_bit(affected_by, vector)
				elif word.startswith('off'):
					off_flags = remove_bit(off_flags, vector)
				elif word.startswith('imm'):
					imm_flags = remove_bit(imm_flags, vector)
				elif word.startswith('res'):
					res_flags = remove_bit(res_flags, vector)
				elif word.startswith('vul'):
					vuln_flags = remove_bit(vuln_flags, vector)
				elif word.startswith('for'):
					form = remove_bit(form, vector)
				elif word.startswith('par'):
					parts = remove_bit(parts, vector)
			elif letter == 'M':
				mprogs.append(reader.read_object_by_fields(RomMobprog))
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc, description=description,
				  race=race, act=act, affected_by=affected_by, extra_flag=extra_flag, alignment=alignment,
				  group=group, level=level, hitroll=hitroll, hit=hit, mana=mana, damage=damage, damtype=damtype,
				  ac=ac, off_flags=off_flags, imm_flags=imm_flags, res_flags=res_flags, vuln_flags=vuln_flags,
				  start_pos=start_pos, default_pos=default_pos, sex=sex, wealth=wealth, form=form, parts=parts,
				  size=size, material=material, mprogs=mprogs)


@attributes
class SmaugArea(RomArea):
	resetmsg = attr(default='', type=str)
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
			arg4 = 0
			arg5 = 0
		else:
			arg3 = reader.read_number()
			# M and P resets have a 4th argument
			if letter == 'M' or letter == 'P':
				arg4 = reader.read_number()
			else:
				arg4 = 0
			arg5 = 0
		reader.index -= 1
		comment = reader.read_to_eol()
		return cls(command=command, arg1=arg1, arg2=arg2, arg3=arg3, arg4=arg4, arg5=arg5, comment=comment)

@attributes
class MercMob(RomMob):
	act = field(default=MERC_ACT_TYPES.IS_NPC.value, type=MERC_ACT_TYPES, converter=MERC_ACT_TYPES)
	ac = attr(default=0, type=int)  # Merc uses single int AC, not 4-value RomArmorClass

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading Mob %d", vnum)
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
				extra_descriptions.append(reader.read_object(ExtraDescription))
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


class RotAreaFile(RomAreaFile):
	"""ROT (Realms of Thera) format - uses 5-value mob header."""

	def load_mobiles(self):
		for mob in self.load_vnum_section(RotMob):
			setitem(self.area.mobs, mob.vnum, mob)


@attributes
class EnvyMob(RomMob):
	"""Envy MUD mob format - like ROM but with S mob type letter and numeric dam_type."""
	dam_type_num = attr(default=0, type=int)

	@classmethod
	def read(cls, reader, vnum, **kwargs):
		logger.debug("Reading Envy mob %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		long_desc = reader.read_string()
		description = reader.read_string()
		race = reader.read_string()
		# Envy: act affected alignment MOB_TYPE(S) or group_number
		act = ROM_ACT_TYPES(reader.read_flag()) | ROM_ACT_TYPES.IS_NPC
		affected_by = reader.read_flag()
		alignment = reader.read_number()
		# Some variants have S letter, others have group number
		reader.skip_whitespace()
		if reader.current_char == 'S':
			reader.advance()  # consume S
			group = 0
		else:
			group = reader.read_number()  # read group number
		# level hitroll hit_dice mana_or_bonus dam_dice dam_type_num
		# Note: Some Envy files have 3 dice (hit, mana, dam), others have number instead of mana
		level = reader.read_number()
		hitroll = reader.read_number()
		hit = reader.read_dice_or_number()
		mana = reader.read_dice_or_number()  # can be dice or number
		damage = reader.read_dice_or_number()
		dam_type_num = reader.read_number()
		# 4-value AC
		ac = reader.read_object(RomArmorClass)
		# off imm res vuln flags
		off_flags = reader.read_flag()
		imm_flags = reader.read_flag()
		res_flags = reader.read_flag()
		vuln_flags = reader.read_flag()
		# start_pos default_pos sex wealth
		start_pos = reader.read_number()
		default_pos = reader.read_number()
		sex = reader.read_number()
		# Wealth can sometimes be a dice expression in malformed files
		reader.skip_whitespace()
		if reader.current_char.isdigit() or reader.current_char == '-':
			wealth_str = reader.read_word()
			# Try to parse as number, otherwise take numeric prefix
			try:
				wealth = int(wealth_str)
			except ValueError:
				# Extract leading digits
				import re
				match = re.match(r'-?\d+', wealth_str)
				wealth = int(match.group()) if match else 0
		else:
			wealth = 0
		# form parts size material
		form = reader.read_flag()
		parts = reader.read_flag()
		size = reader.read_word()
		material = reader.read_word()
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc,
				  description=description, race=race, act=act, affected_by=affected_by,
				  alignment=alignment, level=level, hitroll=hitroll, hit=hit, mana=mana,
				  damage=damage, dam_type_num=dam_type_num, ac=ac, off_flags=off_flags,
				  imm_flags=imm_flags, res_flags=res_flags, vuln_flags=vuln_flags,
				  start_pos=start_pos, default_pos=default_pos, sex=sex, wealth=wealth,
				  form=form, parts=parts, size=size)


@attributes
class EnvyItem(Item):
	"""Envy MUD object format."""
	material = attr(default='', type=str)
	condition = attr(default='', type=str)

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading Envy object %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		description = reader.read_string()
		material = reader.read_string()
		item_type = reader.read_number()
		extra_flags = reader.read_flag()
		wear_flags = reader.read_flag()
		value = [reader.read_number() for _ in range(5)]
		weight = reader.read_number()
		level = reader.read_number()
		cost = reader.read_number()
		condition = reader.read_letter()
		affected = []
		extra_descriptions = []
		while True:
			letter = reader.read_letter()
			if letter == 'A':
				loc = reader.read_number()
				mod = reader.read_number()
				affected.append({'location': loc, 'modifier': mod})
			elif letter == 'E':
				keyword = reader.read_string()
				# Envy extra descriptions can be multi-line, ending at blank line
				# Skip the newline after keyword before reading description
				if reader.current_char == '\n':
					reader.advance()
				desc = reader.read_to_blank_line()
				extra_descriptions.append(ExtraDescription(keyword=keyword, description=desc))
			elif letter == '#' or letter == '$':
				reader.index -= 1
				break
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, description=description,
				  material=material, item_type=item_type, extra_flags=extra_flags,
				  wear_flags=wear_flags, value=value, weight=weight, level=level,
				  cost=cost, condition=condition, affected=affected,
				  extra_descriptions=extra_descriptions)


@attributes
class EnvyRoom(Room):
	"""Envy MUD room format."""
	area_flags = attr(default=0, type=int)

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading Envy room %d" % vnum)
		name = reader.read_string()
		description = reader.read_string()
		area_flags = reader.read_number()
		room_flags = reader.read_flag()
		sector_type = reader.read_number()
		exits = OrderedDict()
		extra_descriptions = []
		while True:
			letter = reader.read_letter()
			if letter == 'S':
				break
			elif letter == 'D':
				door = reader.read_number()
				exit_desc = reader.read_string()
				keyword = reader.read_string()
				exit_info = reader.read_number()
				key = reader.read_number()
				destination = reader.read_number()
				exits[door] = Exit(door=door, description=exit_desc,
								  keyword=keyword, exit_info=exit_info, key=key, destination=destination)
			elif letter == 'E':
				keyword = reader.read_string()
				# Room extra descriptions use standard ~ terminator
				desc = reader.read_string()
				extra_descriptions.append(ExtraDescription(keyword=keyword, description=desc))
			elif letter == 'S':
				# S marks end of room
				break
			elif letter == '#' or letter == '$':
				reader.index -= 1
				break
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, description=description, area_flags=area_flags,
				  room_flags=room_flags, sector_type=sector_type, exits=list(exits.values()),
				  extra_descriptions=extra_descriptions)


class EnvyAreaFile(AreaFile):
	"""Envy MUD format - Merc derivative with extended mob/obj/room formats."""
	area_type = MercArea

	def read_area_metadata(self):
		# Envy format: #AREA {levels} Author Name~
		self.area.metadata = self.read_string()

	def load_mobiles(self):
		for mob in self.load_vnum_section(EnvyMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for obj in self.load_vnum_section(EnvyItem):
			setitem(self.area.objects, obj.vnum, obj)

	def load_rooms(self):
		for room in self.load_vnum_section(EnvyRoom):
			setitem(self.area.rooms, room.vnum, room)

	def load_resets(self):
		while True:
			letter = self.read_letter()
			if letter == 'S' or letter == '$':
				break
			if letter == '*':
				self.read_to_eol()
				continue
			if letter in ('M', 'O', 'P', 'G', 'E', 'D', 'R'):
				reset = MercReset.read(self, letter)
				self.area.resets.append(reset)
			else:
				self.read_to_eol()

	def load_shops(self):
		while True:
			self.skip_whitespace()
			keeper = self.read_number()
			if keeper == 0:
				break
			buy_types = [self.read_number() for _ in range(self.MAX_TRADES)]
			profit_buy = self.read_number()
			profit_sell = self.read_number()
			open_hour = self.read_number()
			close_hour = self.read_number()
			self.read_to_eol()
			self.area.shops.append({
				'keeper': keeper,
				'buy_type': buy_types,
				'profit_buy': profit_buy,
				'profit_sell': profit_sell,
				'open_hour': open_hour,
				'close_hour': close_hour
			})

	def load_specials(self):
		while True:
			self.skip_whitespace()
			if self.index >= len(self.data):
				break
			letter = self.read_letter()
			if letter == 'S' or letter == '$' or letter == '#':
				if letter == '#':
					self.index -= 1
				break
			if letter == '*':
				self.read_to_eol()
				continue
			if letter == 'M':
				vnum = self.read_number()
				spec_fun = self.read_word()
				self.area.specials.append({'mob_vnum': vnum, 'spec_fun': spec_fun})
				self.read_to_eol()
			elif letter == 'D':
				# Some files have Door resets in SPECIALS section
				self.read_to_eol()
			else:
				self.read_to_eol()

	def load_economy(self):
		# Skip economy section if present
		self.read_to_eol()

	def load_helps(self):
		while True:
			level = self.read_number()
			keyword = self.read_string()
			if keyword.startswith('$'):
				break
			text = self.read_string()
			self.area.helps.append(Help(level=level, keyword=keyword, text=text))


class SmaugAreaFile(RomAreaFile):
	area_type = SmaugArea

	def load_mobiles(self):
		for mob in self.load_vnum_section(SmaugMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_resetmsg(self):
		self.area.resetmsg = self.read_string()

	def load_economy(self):
		self.area.high_economy = self.read_number()
		self.area.low_economy = self.read_number()

	def read_area_metadata(self):
		"""Read #AREA section - detect ROM style vs SMAUG-WD style."""
		# Read first string
		first_str = self.read_string()

		# Check if next char is a letter (SMAUG-WD key-value format)
		# or another string/number (ROM format)
		self.skip_whitespace()
		next_char = self.current_char

		if next_char.isupper() and self.data[self.index+1].isspace():
			# SMAUG-WD format: name~ followed by key-value pairs
			self.area.name = first_str
			self._read_smaug_wd_area_keys()
		else:
			# ROM format: filename~ name~ metadata~ first_vnum last_vnum
			self.area.original_filename = first_str
			self.area.name = self.read_string()
			self.area.metadata = self.read_string()
			self.area.first_vnum = self.read_number()
			self.area.last_vnum = self.read_number()

	def _read_smaug_wd_area_keys(self):
		"""Read SMAUG-WD style key-value pairs after area name."""
		while True:
			self.skip_whitespace()
			if self.current_char == '#':
				break  # Next section
			if self.current_char == '$':
				break  # End of file

			key = self.read_letter()
			if key == '\n' or key == '\r':
				continue

			# Read value based on key
			if key in ('K', 'L', 'U', 'O', 'R', 'W'):
				# String value
				self.read_string()
			elif key in ('N', 'X', 'F', 'S'):
				# Number value
				self.read_number()
			elif key == 'I' or key == 'V':
				# Two numbers (level range or vnum range)
				n1 = self.read_number()
				n2 = self.read_number()
				if key == 'V':
					self.area.first_vnum = n1
					self.area.last_vnum = n2
			else:
				# Unknown key, skip to end of line
				self.read_to_eol()

	def load_areadata(self):
		"""Parse SMAUG #AREADATA key-value format."""
		while True:
			self.skip_whitespace()
			word = self.read_word()
			word_lower = word.lower()
			if word_lower == 'end':
				break
			elif word_lower == 'name':
				self.area.name = self.read_string()
			elif word_lower == 'builders' or word_lower == 'author':
				self.area.metadata = self.read_string()
			elif word_lower == 'vnums':
				self.area.first_vnum = self.read_number()
				self.area.last_vnum = self.read_number()
			elif word_lower == 'credits':
				credits = self.read_string()
				if credits and credits != '(null)':
					self.area.metadata = credits
			elif word_lower == 'security':
				self.read_number()  # Discard
			elif word_lower == 'flags':
				self.read_number()  # Discard
			elif word_lower == 'resetmsg':
				self.area.resetmsg = self.read_string()
			elif word_lower == 'resetfreq':
				self.read_number()  # Discard
			else:
				# Skip unknown key-value pairs
				self.read_to_eol()

	def load_author(self):
		self.area.metadata = self.read_string()

	def load_ranges(self):
		# Skip ranges section - read until $ or next section
		while True:
			self.skip_whitespace()
			if self.current_char == '$':
				self.advance()
				break
			elif self.current_char == '#':
				break
			self.read_to_eol()

	def load_flags(self):
		self.read_number()  # Discard area flags

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

@attributes
class SmaugWdMob(object):
	"""SMAUG-WD format mob - simpler than ROM."""
	vnum = attr(default=0)
	name = attr(default='')
	short_desc = attr(default='')
	long_desc = attr(default='')
	description = attr(default='')
	act = attr(default=0, type=int)
	affected_by = attr(default=0, type=int)
	alignment = attr(default=0, type=int)
	mob_type = attr(default='S')
	level = attr(default=1, type=int)
	hitroll = attr(default=0, type=int)
	ac = attr(default=Factory(list), type=list)  # 3 AC values
	# Extended data from ! line
	extended = attr(default=Factory(list), type=list)

	@classmethod
	def read(cls, reader, vnum, **kwargs):
		logger.debug("Reading SMAUG-WD mob %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		long_desc = reader.read_string()
		description = reader.read_string()
		# act affected alignment mob_type
		act = reader.read_number()
		affected_by = reader.read_number()
		alignment = reader.read_number()
		mob_type = reader.read_letter()
		# level hitroll
		level = reader.read_number()
		hitroll = reader.read_number()
		# 3 AC values
		ac = [reader.read_number(), reader.read_number(), reader.read_number()]
		# Extended data line starting with !
		extended = []
		reader.skip_whitespace()
		if reader.current_char == '!':
			reader.advance()
			# Read extended values until newline or next section
			while True:
				reader.skip_whitespace()
				if reader.current_char in ('\n', '\r', '#'):
					break
				try:
					extended.append(reader.read_number())
				except:
					break
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc,
				  description=description, act=act, affected_by=affected_by,
				  alignment=alignment, mob_type=mob_type, level=level, hitroll=hitroll,
				  ac=ac, extended=extended)


@attributes
class SmaugWdItem(object):
	"""SMAUG-WD format item."""
	vnum = attr(default=0)
	name = attr(default='')
	short_desc = attr(default='')
	description = attr(default='')
	item_type = attr(default=0, type=int)
	extra_flags = attr(default=0, type=int)
	wear_flags = attr(default=0, type=int)
	level = attr(default=0, type=int)
	value = attr(default=Factory(list), type=list)
	weight = attr(default=0, type=int)
	affected = attr(default=Factory(list), type=list)
	extra_descriptions = attr(default=Factory(list), type=list)

	@classmethod
	def read(cls, reader, vnum=None, **kwargs):
		logger.debug("Reading SMAUG-WD object %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		description = reader.read_string()
		# item_type extra_flags wear_flags level (4 numbers)
		item_type = reader.read_number()
		extra_flags = reader.read_number()
		wear_flags = reader.read_number()
		level_or_unknown = reader.read_number()
		# 4 values
		value = [reader.read_number(), reader.read_number(), reader.read_number(), reader.read_number()]
		# weight
		weight = reader.read_number()
		# Parse affects, level, and extra descriptions
		affected = []
		extra_descriptions = []
		obj_level = level_or_unknown  # May be overwritten by L line
		while True:
			reader.skip_whitespace()
			letter = reader.read_letter()
			if letter == 'A':
				# Affect: location modifier
				loc = reader.read_number()
				mod = reader.read_number()
				affected.append({'location': loc, 'modifier': mod})
			elif letter == 'L':
				# Level restriction
				obj_level = reader.read_number()
			elif letter == 'E':
				# Extra description
				keyword = reader.read_string()
				desc = reader.read_string()
				extra_descriptions.append(ExtraDescription(keyword=keyword, description=desc))
			elif letter == '#' or letter == '$':
				# Next object or end of section
				reader.index -= 1
				break
			else:
				# Unknown, probably end of object
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, description=description,
				  item_type=item_type, extra_flags=extra_flags, wear_flags=wear_flags,
				  level=obj_level, value=value, weight=weight, affected=affected,
				  extra_descriptions=extra_descriptions)


@attributes
class SmaugWdExit(object):
	"""SMAUG-WD format exit."""
	direction = attr(default=0, type=int)
	description = attr(default='')
	keyword = attr(default='')
	exit_flags = attr(default=0, type=int)
	key = attr(default=-1, type=int)
	destination = attr(default=0, type=int)

	@classmethod
	def read(cls, reader, direction):
		description = reader.read_string()
		keyword = reader.read_string()
		exit_flags = reader.read_number()
		key = reader.read_number()
		destination = reader.read_number()
		return cls(direction=direction, description=description, keyword=keyword,
				  exit_flags=exit_flags, key=key, destination=destination)


@attributes
class SmaugWdRoom(object):
	"""SMAUG-WD format room."""
	vnum = attr(default=0)
	name = attr(default='')
	description = attr(default='')
	room_flags = attr(default=0, type=int)
	sector_type = attr(default=0, type=int)
	exits = attr(default=Factory(list), type=list)
	extra_descriptions = attr(default=Factory(list), type=list)

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading SMAUG-WD room %d" % vnum)
		name = reader.read_string()
		description = reader.read_string()
		# room_flags sector_type (2 numbers, no area_number)
		room_flags = reader.read_number()
		sector_type = reader.read_number()
		exits = []
		extra_descriptions = []
		while True:
			reader.skip_whitespace()
			letter = reader.read_letter()
			if letter == 'S':
				break
			elif letter == 'D':
				# Direction is appended to D (e.g., D0, D1, D2...)
				direction = reader.read_number()
				exits.append(SmaugWdExit.read(reader, direction))
			elif letter == 'E':
				keyword = reader.read_string()
				desc = reader.read_string()
				extra_descriptions.append(ExtraDescription(keyword=keyword, description=desc))
			elif letter == 'M':
				# Mana rate - skip
				reader.read_number()
			elif letter == 'H':
				# Heal rate - skip
				reader.read_number()
			else:
				# Unknown, skip to next line or back up
				reader.index -= 1
				reader.read_to_eol()
		return cls(vnum=vnum, name=name, description=description, room_flags=room_flags,
				  sector_type=sector_type, exits=exits, extra_descriptions=extra_descriptions)


@attributes
class SmaugWdReset(object):
	"""SMAUG-WD format reset."""
	command = attr(default=None)
	arg1 = attr(default=0)
	arg2 = attr(default=0)
	arg3 = attr(default=0)
	arg4 = attr(default=0)
	comment = attr(default='')

	@classmethod
	def read(cls, reader, letter):
		command = letter
		reader.read_number()  # if_flag (always 0)
		arg1 = reader.read_number()
		arg2 = reader.read_number()
		if letter in ('M', 'O', 'P', 'E', 'D'):
			arg3 = reader.read_number()
			if letter == 'M':
				arg4 = reader.read_number()
			else:
				arg4 = 0
		else:
			arg3 = 0
			arg4 = 0
		# Read comment (usually "(null)" or mob/obj name)
		comment = reader.read_to_eol().strip()
		return cls(command=command, arg1=arg1, arg2=arg2, arg3=arg3, arg4=arg4, comment=comment)


@attributes
class SmaugWdArea(object):
	"""SMAUG-WD area data container."""
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


class SmaugWdAreaFile(AreaFile):
	"""Parser for SMAUG-WD format area files."""
	area_type = SmaugWdArea

	def read_section_name(self):
		"""Read section name - handle AREA without # prefix."""
		self.skip_whitespace()
		if self.current_char == '#':
			self.advance()
			name = self.read_word()
			return name.lower()
		elif self.current_char == '$':
			self.advance()
			return '$'
		else:
			# Check for bare "AREA" section name (no # prefix)
			name = self.read_word()
			return name.lower()

	def load_mobiles(self):
		while True:
			self.skip_whitespace()
			if self.current_char != '#':
				break
			self.advance()  # Skip #
			vnum = self.read_number()
			if vnum == 0:
				break
			mob = SmaugWdMob.read(self, vnum)
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		while True:
			self.skip_whitespace()
			if self.current_char != '#':
				break
			self.advance()  # Skip #
			vnum = self.read_number()
			if vnum == 0:
				break
			obj = SmaugWdItem.read(self, vnum)
			setitem(self.area.objects, obj.vnum, obj)

	def load_rooms(self):
		while True:
			self.skip_whitespace()
			if self.current_char != '#':
				break
			self.advance()  # Skip #
			vnum = self.read_number()
			if vnum == 0:
				break
			room = SmaugWdRoom.read(self, vnum)
			setitem(self.area.rooms, room.vnum, room)

	def load_resets(self):
		while True:
			self.skip_whitespace()
			letter = self.read_letter()
			if letter == 'S' or letter == '$':
				break
			if letter == '*':
				self.read_to_eol()
				continue
			if letter in ('M', 'O', 'P', 'G', 'E', 'D', 'R', 'T'):
				reset = SmaugWdReset.read(self, letter)
				self.area.resets.append(reset)
			else:
				self.read_to_eol()

	def load_shops(self):
		while True:
			self.skip_whitespace()
			keeper = self.read_number()
			if keeper == 0:
				break
			# SMAUG-WD shop format: keeper buy_types[5] profit_buy profit_sell open close
			buy_types = [self.read_number() for _ in range(5)]
			profit_buy = self.read_number()
			profit_sell = self.read_number()
			open_hour = self.read_number()
			close_hour = self.read_number()
			self.area.shops.append({
				'keeper': keeper,
				'buy_type': buy_types,
				'profit_buy': profit_buy,
				'profit_sell': profit_sell,
				'open_hour': open_hour,
				'close_hour': close_hour
			})

	def load_specials(self):
		while True:
			self.skip_whitespace()
			letter = self.read_letter()
			if letter == 'S' or letter == '$':
				break
			if letter == '*':
				self.read_to_eol()
				continue
			if letter == 'M':
				mob_vnum = self.read_number()
				spec_name = self.read_word()
				comment = self.read_to_eol()
				self.area.specials.append({
					'command': 'M',
					'arg1': mob_vnum,
					'arg2': spec_name,
					'comment': comment
				})
			else:
				self.read_to_eol()

	def read_area_metadata(self):
		"""Read #AREA section - SMAUG-WD format with key-value pairs."""
		# First line is area name
		self.area.name = self.read_string()
		# Read key-value pairs
		while True:
			self.skip_whitespace()
			if self.current_char == '#':
				break
			if self.current_char == '$':
				break
			key = self.read_letter()
			if key in ('\n', '\r'):
				continue
			# Read value based on key
			if key in ('K', 'L', 'U', 'O', 'R', 'W'):
				# String value
				val = self.read_string()
				if key == 'O':
					self.area.metadata = val
			elif key in ('N', 'X', 'F', 'S'):
				# Number value
				self.read_number()
			elif key == 'I' or key == 'V':
				# Two numbers
				n1 = self.read_number()
				n2 = self.read_number()
				if key == 'V':
					self.area.first_vnum = n1
					self.area.last_vnum = n2
			else:
				# Unknown key, skip to end of line
				self.read_to_eol()


class EnumNameConverter(converters.Converter):
	def _unstructure_enum(self, obj):
		# Handle IntFlags that may have undefined bits set
		name = obj.name
		if name is None:
			# Fall back to string representation for undefined values
			return str(obj)
		return obj.__class__.__name__ + "." + name


def print_area(area_file_path, area_type=RomAreaFile):
	area_file = area_type(area_file_path)
	area_file.load_sections()
	print(area_file.as_json())

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print("Must supply an area")
		sys.exit(1)
	print_area(sys.argv[1])
