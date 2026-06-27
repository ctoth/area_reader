#! /usr/bin/env python3.11

import logging
logger = logging.getLogger('area_reader')
logging.basicConfig(level=logging.INFO)

from collections import OrderedDict
import enum
import html
import io
import json
import random
import re
import os
import sys
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from attr import attr, attributes, Factory, fields
from cattr import converters
from operator import setitem

from area_reader.constants import *

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
		self.file = io.open(filename, mode='rt', encoding='latin-1')
		self.index = 0
		self.data = self.file.read()
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

	def skip_smaug_programs(self):
		self.skip_whitespace()
		while self.current_char == '>':
			program_end = self.data.find('\n|\n', self.index)
			if program_end == -1:
				program_end = self.data.find('\r\n|\r\n', self.index)
			if program_end != -1:
				self.index = program_end + 3
				self.skip_whitespace()
				continue
			next_record = self.data.find('\n#', self.index)
			if next_record == -1:
				self.index = len(self.data) - 1
				return
			self.index = next_record + 1

	def read_number_line(self):
		self.skip_whitespace()
		line = self.read_to_eol().strip()
		if not line:
			return []
		return [int(value) for value in line.split()]

	def read_until(self, endchar):
		ahead = self.data.find(endchar, self.index)
		result = self.data[self.index:ahead]
		self.index = ahead
		return result

	@property
	def current_char(self):
		if self.index >= len(self.data):
			return '\0'
		return self.data[self.index]

	def advance(self):
		self.index += 1

	def skip_whitespace(self):
		while self.index < len(self.data) and self.current_char.isspace():
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
		if self.current_char == '|' or self.current_char == '&':
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
				try:
					readers[section_name]()
				except Exception:
					self.parse_fail("Error reading section %r" % section_name)

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
class SmaugExit(Exit):
	door = attr(default=None, type=int)
	distance = attr(default=0, type=int)
	pulltype = attr(default=0, type=int)
	pull = attr(default=0, type=int)
	x = attr(default=0, type=int)
	y = attr(default=0, type=int)

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
		else:
			arg3 = reader.read_number()
		if letter == 'P' or letter == 'M':
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

	def read_metadata(self, reader):
		logger.debug("Reading room data for %d" % self.vnum)
		while True:
			letter = reader.read_letter()
			if letter == 'S':
				break
			if letter == 'D':
				self.exits.append(Exit.read(reader=reader))
			elif letter == 'E':
				self.extra_descriptions.append(reader.read_object(ExtraDescription))
			else:
				reader.parse_fail("room %d has flag %s not DES" % (self.vnum, letter))

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

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading SMAUG mob %d", vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		long_desc = reader.read_string()
		description = reader.read_string()
		act = reader.read_flag() | ROM_ACT_TYPES.IS_NPC
		affected_by = reader.read_flag()
		alignment = reader.read_number()
		letter = reader.read_letter()
		level = reader.read_number()
		hitroll = reader.read_number()
		ac = reader.read_number()
		hit = Dice.read(reader=reader)
		damage = Dice.read(reader=reader)
		if letter not in ('S', 'C', 'V'):
			reader.parse_fail("Reading SMAUG MOB vnum %d unexpected type %s" % (vnum, letter))
		numeric_lines = []
		while True:
			reader.skip_whitespace()
			if reader.current_char == '#' or reader.current_char == '>':
				break
			numeric_lines.append(reader.read_number_line())
		complex_line_count = 0
		if letter in ('C', 'V'):
			complex_line_count = 4
		if letter == 'V':
			complex_line_count = 5
		position_index = len(numeric_lines) - complex_line_count - 1
		if position_index < 0:
			reader.parse_fail("SMAUG MOB vnum %d missing position line" % vnum)
		position_line = numeric_lines[position_index]
		if len(position_line) < 3:
			reader.parse_fail("SMAUG MOB vnum %d malformed position line" % vnum)
		money_values = []
		for line in numeric_lines[:position_index]:
			money_values.extend(line)
		wealth = money_values[0] if money_values else 0
		start_pos = position_line[0]
		default_pos = position_line[1]
		sex = position_line[2]
		reader.skip_smaug_programs()
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc, description=description, act=act, affected_by=affected_by, alignment=alignment, level=level, hitroll=hitroll, ac=ac, hit=hit, damage=damage, wealth=wealth, start_pos=start_pos, default_pos=default_pos, sex=sex)

@attributes
class SmaugItem(Item):
	layers = attr(default=0, type=int)

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading SMAUG object %d", vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		description = reader.read_string()
		reader.read_string() # action description
		item_type = reader.read_number()
		extra_flags = reader.read_flag()
		wear_flags = reader.read_flag()
		header = [int(value) for value in reader.read_to_eol().split()]
		layers = header[0] if len(header) > 0 else 0
		level = header[1] if len(header) > 1 else 0
		reader.skip_whitespace()
		value = [int(value) for value in reader.read_to_eol().split()]
		reader.skip_whitespace()
		cost_line = [int(value) for value in reader.read_to_eol().split()]
		weight = cost_line[0] if len(cost_line) > 0 else 0
		cost = cost_line[1] if len(cost_line) > 1 else 0
		reader.skip_whitespace()
		if reader.current_char not in ('A', 'E', '>', '#'):
			reader.read_to_eol()
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
			elif letter == '>':
				reader.index -= 1
				reader.skip_smaug_programs()
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, description=description, item_type=item_type, extra_flags=extra_flags, wear_flags=wear_flags, value=value, level=level, weight=weight, cost=cost, affected=affected, extra_descriptions=extra_descriptions, layers=layers)

@attributes
class SmaugArea(RomArea):
	author = attr(default='', type=str)
	credits = attr(default='', type=str)
	flags = attr(default=0, type=int)
	version = attr(default=0, type=int)
	low_soft_range = attr(default=0, type=int)
	high_soft_range = attr(default=0, type=int)
	low_hard_range = attr(default=0, type=int)
	high_hard_range = attr(default=0, type=int)
	resetmsg = attr(default='', type=str)
	high_economy = attr(default=0)
	low_economy = attr(default=0)

@attributes
class SmaugRoom(Room):
	sector_type = attr(default=0, type=int)
	tele_delay = attr(default=0)
	tele_vnum = attr(default=0)
	tunnel = attr(default=None)
	max_weight = attr(default=None)
	light = attr(default=0)

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading SMAUG room with vnum %d", vnum)
		name = reader.read_string()
		description = reader.read_string()
		area_number = reader.read_number()
		room_flags = reader.read_flag()
		line = reader.read_to_eol()
		values = [int(value) for value in line.split()]
		while len(values) < 5:
			values.append(0)
		room = cls(vnum=vnum, name=name, description=description, area_number=area_number, room_flags=room_flags, sector_type=values[0], tele_delay=values[1], tele_vnum=values[2], tunnel=values[3], max_weight=values[4])
		room.read_metadata(reader)
		return room

	def read_metadata(self, reader):
		while True:
			letter = reader.read_letter()
			if letter == 'S':
				break
			if letter == 'D':
				self.exits.append(self.read_exit(reader))
			elif letter == 'E':
				self.extra_descriptions.append(reader.read_object(ExtraDescription))
			elif letter == 'M':
				reader.read_number()
				reader.read_number()
				reader.read_number()
				reader.read_letter()
			elif letter == '>':
				reader.index -= 1
				reader.skip_smaug_programs()
			else:
				reader.parse_fail("SMAUG room %d has unknown flag %s" % (self.vnum, letter))

	def read_exit(self, reader):
		door = reader.read_number()
		description = reader.read_string()
		keyword = reader.read_string()
		reader.skip_whitespace()
		line = reader.read_to_eol()
		values = [int(value) for value in line.split()]
		while len(values) < 6:
			values.append(0)
		locks, key, destination, distance, pulltype, pull = values[:6]
		if locks == 1:
			exit_info = EXIT_FLAGS.ISDOOR
		elif locks == 2:
			exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF
		else:
			exit_info = locks
		return SmaugExit(door=door, description=description, keyword=keyword, exit_info=exit_info, key=key, destination=destination, distance=distance, pulltype=pulltype, pull=pull)


@attributes
class SwrRoom(SmaugRoom):
	sector = attr(default='', type=str)
	resets = attr(default=Factory(list))


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
		comment = reader.read_to_eol()
		return cls(command=command, arg1=arg1, arg2=arg2, arg3=arg3, comment=comment)

@attributes
class MercMob(RomMob):
	act = field(default=MERC_ACT_TYPES.IS_NPC.value, type=MERC_ACT_TYPES, converter=MERC_ACT_TYPES)

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

	def load_rooms(self):
		for room in self.load_vnum_section(MercRoom):
			setitem(self.area.rooms, room.vnum, room)

	def load_resets(self):
		for reset in self.read_flat_section(MercReset):
			self.area.resets.append(reset)

	def read_area_metadata(self):
		self.area.metadata = self.read_string()

class SmaugAreaFile(RomAreaFile):
	area_type = SmaugArea

	def load_sections(self):
		readers = {
			'area': self.read_area_metadata,
			'author': self.load_author,
			'credits': self.load_credits,
			'flags': self.load_flags,
			'ranges': self.load_ranges,
			'version': self.load_version,
			'resetmsg': self.load_resetmsg,
			'economy': self.load_economy,
			'helps': self.load_helps,
			'mobiles': self.load_mobiles,
			'objects': self.load_objects,
			'rooms': self.load_rooms,
			'resets': self.load_resets,
			'shops': self.load_shops,
			'specials': self.load_specials,
			'repairs': self.load_repairs,
			'continent': self.load_ignored_string,
			'climate': self.load_ignored_line,
			'neighbor': self.load_ignored_line,
			'spelllimit': self.load_ignored_line,
		}
		while True:
			self.skip_whitespace()
			if self.index >= len(self.data):
				return
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
					reader()
				except Exception:
					self.parse_fail("Error reading section %r" % section_name)

	def read_area_metadata(self):
		self.area.name = self.read_string()

	def load_author(self):
		self.area.author = self.read_string()

	def load_credits(self):
		self.area.credits = self.read_string()

	def load_flags(self):
		self.area.flags = self.read_number()
		self.read_to_eol()

	def load_ranges(self):
		self.area.low_soft_range = self.read_number()
		self.area.high_soft_range = self.read_number()
		self.area.low_hard_range = self.read_number()
		self.area.high_hard_range = self.read_number()
		self.read_word() # $

	def load_version(self):
		self.area.version = self.read_number()

	def load_ignored_string(self):
		self.read_string()

	def load_ignored_line(self):
		self.read_to_eol()

	def load_mobiles(self):
		for mob in self.load_smaug_vnum_section(SmaugMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for item in self.load_smaug_vnum_section(SmaugItem):
			setitem(self.area.objects, item.vnum, item)

	def load_rooms(self):
		for room in self.load_smaug_vnum_section(SmaugRoom):
			setitem(self.area.rooms, room.vnum, room)

	def load_smaug_vnum_section(self, section_object_type):
		while True:
			self.skip_whitespace()
			if self.index >= len(self.data):
				break
			if self.current_char != '#':
				self.parse_fail("Expected # got %s" % self.current_char)
			next_char = self.data[self.index + 1]
			if not (next_char.isdigit() or next_char == '-'):
				break
			vnum = self.read_vnum()
			if vnum == 0:
				break
			yield self.read_object(section_object_type, vnum=vnum)

	def load_resets(self):
		for reset in self.read_flat_section(MercReset):
			self.area.resets.append(reset)

	def load_repairs(self):
		while True:
			keeper = self.read_number()
			if keeper == 0:
				break
			for _ in range(self.MAX_TRADES):
				self.read_number()
			self.read_number()
			self.read_number()
			self.read_number()
			self.read_number()
			self.read_to_eol()

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


class SwrAreaFile(SmaugAreaFile):

	def load_sections(self):
		self.skip_whitespace()
		if self.data.startswith("#FUSSAREA", self.index):
			self.read_section_name()
			self.load_fuss_area()
			return
		if self.current_char == '#':
			start = self.index
			self.advance()
			word = self.read_word()
			self.index = start
			if word.isdigit():
				for mob in self.load_smaug_vnum_section(SmaugMob):
					setitem(self.area.mobs, mob.vnum, mob)
				return
		super().load_sections()

	def load_mobiles(self):
		for mob in self.load_swr_vnum_section(SmaugMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for item in self.load_swr_vnum_section(SmaugItem):
			setitem(self.area.objects, item.vnum, item)

	def load_rooms(self):
		for room in self.load_swr_vnum_section(SmaugRoom):
			setitem(self.area.rooms, room.vnum, room)

	def load_swr_vnum_section(self, section_object_type):
		while True:
			self.skip_whitespace()
			if self.index >= len(self.data):
				break
			if self.current_char != '#':
				self.parse_fail("Expected # got %s" % self.current_char)
			next_char = self.data[self.index + 1]
			if not (next_char.isdigit() or next_char == '-'):
				break
			vnum = self.read_vnum()
			self.skip_whitespace()
			if vnum == 0 and (self.index >= len(self.data) or self.current_char == '#'):
				break
			yield self.read_object(section_object_type, vnum=vnum)

	def load_fuss_area(self):
		while True:
			self.skip_whitespace()
			if self.index >= len(self.data):
				return
			section_name = self.read_section_name()
			self.current_section_name = section_name
			if section_name == 'areadata':
				self.load_fuss_areadata()
			elif section_name == 'mobile':
				mob = self.read_fuss_mobile()
				setitem(self.area.mobs, mob.vnum, mob)
			elif section_name == 'object':
				item = self.read_fuss_object()
				setitem(self.area.objects, item.vnum, item)
			elif section_name == 'room':
				room = self.read_fuss_room()
				setitem(self.area.rooms, room.vnum, room)
				self.area.resets.extend(room.resets)
			elif section_name == 'endarea':
				return
			else:
				self.skip_fuss_value()

	def skip_fuss_value(self):
		line_end = self.data.find('\n', self.index)
		if line_end == -1:
			self.index = len(self.data)
			return
		if '~' in self.data[self.index:line_end]:
			self.read_string()
		else:
			self.read_to_eol()

	def read_fuss_numbers(self):
		return [int(value) for value in self.read_to_eol().split()]

	def load_fuss_areadata(self):
		while True:
			word = self.read_word()
			if word == "#ENDAREADATA":
				return
			if word == "Author":
				self.area.author = self.read_string()
			elif word == "Economy":
				self.area.high_economy = self.read_number()
				self.area.low_economy = self.read_number()
			elif word == "Flags":
				self.area.flags = 0
				self.read_string()
			elif word == "Name":
				self.area.name = self.read_string()
			elif word == "Ranges":
				values = self.read_fuss_numbers()
				if len(values) >= 4:
					self.area.low_soft_range = values[0]
					self.area.high_soft_range = values[1]
					self.area.low_hard_range = values[2]
					self.area.high_hard_range = values[3]
			elif word == "ResetMsg":
				self.area.resetmsg = self.read_string()
			elif word == "ResetFreq":
				self.read_number()
			elif word == "Version":
				self.area.version = self.read_number()
			else:
				self.skip_fuss_value()

	def read_fuss_mobile(self):
		vnum = 0
		name = ''
		short_desc = ''
		long_desc = ''
		description = ''
		race = ''
		position = ''
		default_position = ''
		sex = ''
		stats1 = [0, 0, 0, 0, 0, 0]
		stats2 = [0, 0, 0]
		stats3 = [0, 0, 0]
		stats4 = [0, 0, 0, 0, 0]
		while True:
			word = self.read_word()
			if word == "#ENDMOBILE":
				break
			if word == "#MUDPROG":
				self.skip_fuss_program()
			elif word == "Vnum":
				vnum = self.read_number()
			elif word == "Keywords":
				name = self.read_string()
			elif word == "Short":
				short_desc = self.read_string()
			elif word == "Long":
				long_desc = self.read_string()
			elif word == "Desc":
				description = self.read_string()
			elif word == "Race":
				race = self.read_string()
			elif word == "Position":
				position = self.read_string()
			elif word == "DefPos":
				default_position = self.read_string()
			elif word == "Gender":
				sex = self.read_string()
			elif word == "Stats1":
				stats1 = self.read_fuss_numbers()
			elif word == "Stats2":
				stats2 = self.read_fuss_numbers()
			elif word == "Stats3":
				stats3 = self.read_fuss_numbers()
			elif word == "Stats4":
				stats4 = self.read_fuss_numbers()
			elif word in ("Actflags", "Affected", "Attacks", "Attribs", "Bodyparts", "Defenses", "Immune", "RepairData", "Resist", "Saves", "ShopData", "Speaks", "Speaking", "Specfun", "Specfun2", "Suscept", "VIPFlags"):
				self.skip_fuss_value()
			else:
				self.skip_fuss_value()
		while len(stats1) < 6:
			stats1.append(0)
		while len(stats2) < 3:
			stats2.append(0)
		while len(stats3) < 3:
			stats3.append(0)
		while len(stats4) < 5:
			stats4.append(0)
		return RomMob(
			vnum=vnum,
			name=name,
			short_desc=short_desc,
			long_desc=long_desc,
			description=description,
			race=race,
			alignment=stats1[0],
			level=stats1[1],
			hitroll=stats4[3],
			hit=Dice(number=stats2[0], sides=stats2[1], bonus=stats2[2]),
			damage=Dice(number=stats3[0], sides=stats3[1], bonus=stats3[2]),
			ac=RomArmorClass(pierce=stats1[3], bash=stats1[3], slash=stats1[3], exotic=stats1[3]),
			wealth=stats1[4],
			start_pos=position,
			default_pos=default_position,
			sex=sex,
		)

	def read_fuss_object(self):
		vnum = 0
		name = ''
		short_desc = ''
		description = ''
		value = []
		weight = 0
		cost = 0
		level = 0
		layers = 0
		extra_descriptions = []
		while True:
			word = self.read_word()
			if word == "#ENDOBJECT":
				break
			if word == "#EXDESC":
				extra_descriptions.append(self.read_fuss_extra_description())
			elif word == "#MUDPROG":
				self.skip_fuss_program()
			elif word == "Vnum":
				vnum = self.read_number()
			elif word == "Keywords":
				name = self.read_string()
			elif word == "Short":
				short_desc = self.read_string()
			elif word == "Long":
				description = self.read_string()
			elif word == "Values":
				value = self.read_fuss_numbers()
			elif word == "Stats":
				stats = self.read_fuss_numbers()
				if len(stats) > 0:
					weight = stats[0]
				if len(stats) > 1:
					cost = stats[1]
				if len(stats) > 3:
					level = stats[3]
				if len(stats) > 4:
					layers = stats[4]
			elif word in ("Action", "Affect", "AffectData", "Flags", "Spells", "Type", "WFlags"):
				self.skip_fuss_value()
			else:
				self.skip_fuss_value()
		return SmaugItem(vnum=vnum, name=name, short_desc=short_desc, description=description, value=value, weight=weight, cost=cost, level=level, layers=layers, extra_descriptions=extra_descriptions)

	def read_fuss_room(self):
		vnum = 0
		name = ''
		description = ''
		sector = ''
		tele_delay = 0
		tele_vnum = 0
		tunnel = 0
		exits = []
		extra_descriptions = []
		resets = []
		while True:
			word = self.read_word()
			if word == "#ENDROOM":
				break
			if word == "#EXIT":
				exits.append(self.read_fuss_exit())
			elif word == "#EXDESC":
				extra_descriptions.append(self.read_fuss_extra_description())
			elif word == "#MUDPROG":
				self.skip_fuss_program()
			elif word == "Vnum":
				vnum = self.read_number()
			elif word == "Name":
				name = self.read_string()
			elif word == "Desc":
				description = self.read_string()
			elif word == "Sector":
				sector = self.read_string()
			elif word == "Stats":
				stats = self.read_fuss_numbers()
				if len(stats) > 0:
					tele_delay = stats[0]
				if len(stats) > 1:
					tele_vnum = stats[1]
				if len(stats) > 2:
					tunnel = stats[2]
			elif word == "Reset":
				letter = self.read_letter()
				resets.append(MercReset.read(reader=self, letter=letter))
			elif word == "Flags":
				self.skip_fuss_value()
			else:
				self.skip_fuss_value()
		return SwrRoom(vnum=vnum, name=name, description=description, sector=sector, tele_delay=tele_delay, tele_vnum=tele_vnum, tunnel=tunnel, exits=exits, extra_descriptions=extra_descriptions, resets=resets)

	def read_fuss_exit(self):
		door = None
		description = ''
		keyword = ''
		key = 0
		destination = 0
		distance = 0
		while True:
			word = self.read_word()
			if word == "#ENDEXIT":
				return SmaugExit(door=door, description=description, keyword=keyword, key=key, destination=destination, distance=distance)
			if word == "Desc":
				description = self.read_string()
			elif word == "Direction":
				door = self.read_string()
			elif word == "Distance":
				distance = self.read_number()
			elif word == "Key":
				key = self.read_number()
			elif word == "Keywords":
				keyword = self.read_string()
			elif word == "ToRoom":
				destination = self.read_number()
			elif word == "Flags":
				self.skip_fuss_value()
			else:
				self.skip_fuss_value()

	def read_fuss_extra_description(self):
		keyword = ''
		description = ''
		while True:
			word = self.read_word()
			if word == "#ENDEXDESC":
				return ExtraDescription(keyword=keyword, description=description)
			if word == "ExDescKey":
				keyword = self.read_string()
			elif word == "ExDesc":
				description = self.read_string()
			else:
				self.skip_fuss_value()

	def skip_fuss_program(self):
		while True:
			word = self.read_word()
			if word == "#ENDPROG":
				return
			if word in ("Arglist", "Comlist", "Progtype"):
				self.read_string()
			else:
				self.skip_fuss_value()


def circle_asciiflag_conv(flag):
	flag = str(flag)
	if flag.isdigit():
		return int(flag)
	flags = 0
	for char in flag:
		if char.islower():
			flags |= 1 << (ord(char) - ord('a'))
		elif char.isupper():
			flags |= 1 << (26 + ord(char) - ord('A'))
	return flags


class CircleMobFlags(enum.IntFlag):
	SPEC = 1 << 0
	SENTINEL = 1 << 1
	SCAVENGER = 1 << 2
	ISNPC = 1 << 3
	AWARE = 1 << 4
	AGGRESSIVE = 1 << 5
	STAY_ZONE = 1 << 6
	WIMPY = 1 << 7
	AGGR_EVIL = 1 << 8
	AGGR_GOOD = 1 << 9
	AGGR_NEUTRAL = 1 << 10
	MEMORY = 1 << 11
	HELPER = 1 << 12
	NOCHARM = 1 << 13
	NOSUMMON = 1 << 14
	NOSLEEP = 1 << 15
	NOBASH = 1 << 16
	NOBLIND = 1 << 17
	NOTDEADYET = 1 << 18


@attributes
class CircleExit(object):
	door = attr(default=0)
	description = attr(default='')
	keyword = attr(default='')
	exit_info = attr(default=EXIT_FLAGS.NONE, type=EXIT_FLAGS, converter=EXIT_FLAGS)
	key = attr(default=-1)
	destination = attr(default=-1)


@attributes
class CircleRoom(MudBase):
	zone_number = attr(default=0)
	room_flags = attr(default=0)
	sector_type = attr(default=0)
	exits = attr(default=Factory(dict))


@attributes
class CircleMob(RomCharacter):
	act = field(default=CircleMobFlags.ISNPC.value, type=CircleMobFlags, converter=CircleMobFlags)
	ac = attr(default=0)
	alignment = attr(default=0)
	affected_by = attr(default=0)
	exp = attr(default=0)
	wealth = attr(default=0)
	start_pos = attr(default=0)
	default_pos = attr(default=0)
	sex = attr(default=0)
	especs = attr(default=Factory(dict))


@attributes
class CircleAffectData(object):
	location = attr(default=0)
	modifier = attr(default=0)


@attributes
class CircleItem(Item):
	action_description = attr(default='')
	rent = attr(default=0)


@attributes
class CircleReset(object):
	command = attr(default='')
	if_flag = attr(default=0)
	arg1 = attr(default=0)
	arg2 = attr(default=0)
	arg3 = attr(default=None)


@attributes
class CircleZone(object):
	vnum = attr(default=0)
	name = attr(default='')
	bot = attr(default=0)
	top = attr(default=0)
	lifespan = attr(default=0)
	reset_mode = attr(default=0)
	resets = attr(default=Factory(list))


@attributes
class CircleShop(object):
	vnum = attr(default=0)
	products = attr(default=Factory(list))
	profit_buy = attr(default=0.0)
	profit_sell = attr(default=0.0)
	buy_type = attr(default=Factory(list))
	messages = attr(default=Factory(list))
	temper = attr(default=0)
	bitvector = attr(default=0)
	keeper = attr(default=0)
	with_who = attr(default=0)
	rooms = attr(default=Factory(list))
	open_hour = attr(default=0)
	close_hour = attr(default=0)
	open_hour_2 = attr(default=0)
	close_hour_2 = attr(default=0)


@attributes
class CircleArea(object):
	zones = attr(default=Factory(OrderedDict))
	rooms = attr(default=Factory(OrderedDict))
	mobs = attr(default=Factory(OrderedDict))
	objects = attr(default=Factory(OrderedDict))
	shops = attr(default=Factory(OrderedDict))


class CircleAreaFile(object):

	def __init__(self, root):
		self.root = os.fspath(root)
		self.world_root = self.root
		if not os.path.exists(os.path.join(self.world_root, 'zon', 'index')):
			self.world_root = os.path.join(self.root, 'lib', 'world')
		self.area = CircleArea()
		self.filename = ''
		self.data = ''
		self.index = 0

	def load_sections(self):
		self.load_zones()
		self.load_rooms()
		self.load_mobiles()
		self.load_objects()
		self.load_shops()

	def load_zones(self):
		for path in self.indexed_paths('zon'):
			self.load_zone_file(path)

	def load_rooms(self):
		for path in self.indexed_paths('wld'):
			self.load_room_file(path)

	def load_mobiles(self):
		for path in self.indexed_paths('mob'):
			self.load_mobile_file(path)

	def load_objects(self):
		for path in self.indexed_paths('obj'):
			self.load_object_file(path)

	def load_shops(self):
		for path in self.indexed_paths('shp'):
			self.load_shop_file(path)

	def indexed_paths(self, family):
		index_path = os.path.join(self.world_root, family, 'index')
		if not os.path.exists(index_path):
			return []
		base = os.path.dirname(index_path)
		with io.open(index_path, mode='rt', encoding='latin-1') as index_file:
			names = [line.strip() for line in index_file]
		return [os.path.join(base, name) for name in names if name and name != '$']

	def open_circle_file(self, filename):
		self.filename = filename
		with io.open(filename, mode='rt', encoding='latin-1') as circle_file:
			self.data = circle_file.read()
		self.index = 0

	@property
	def current_char(self):
		if self.index >= len(self.data):
			return '\0'
		return self.data[self.index]

	def skip_whitespace(self):
		while self.index < len(self.data) and self.current_char.isspace():
			self.index += 1

	def read_line(self):
		while self.current_char in ('\r', '\n'):
			self.index += 1
		if self.index >= len(self.data):
			return ''
		end = self.data.find('\n', self.index)
		if end == -1:
			line = self.data[self.index:]
			self.index = len(self.data)
		else:
			line = self.data[self.index:end]
			self.index = end + 1
		return line.rstrip('\r')

	def read_string(self):
		self.skip_whitespace()
		end = self.data.find('~', self.index)
		if end == -1:
			self.parse_fail("Unterminated string")
		result = self.data[self.index:end]
		self.index = end + 1
		return result

	def read_record_header(self):
		self.skip_whitespace()
		if self.current_char == '$':
			return None
		if self.current_char != '#':
			self.parse_fail("Expected record header")
		self.index += 1
		token = ''
		while self.current_char not in ('\0', '\n', '\r', '~') and not self.current_char.isspace():
			token += self.current_char
			self.index += 1
		if self.current_char == '~':
			self.index += 1
		return int(token)

	def read_int_list(self):
		line = self.read_line().strip()
		if not line:
			return []
		return [int(value) for value in line.split()]

	def read_tilde_or_line(self):
		self.skip_whitespace()
		if '~' in self.data[self.index:self.data.find('\n', self.index) if self.data.find('\n', self.index) != -1 else len(self.data)]:
			return self.read_string()
		return self.read_line().strip()

	def parse_fail(self, message):
		backwards = self.data[:self.index]
		lineno = backwards.count('\n') + 1
		col = backwards[::-1].find('\n')
		raise ParseError("%s line %s col %s: %s" % (self.filename, lineno, col, message))

	def parse_dice_token(self, token):
		number, rest = token.lower().split('d', 1)
		if '+' in rest:
			sides, bonus = rest.split('+', 1)
			bonus = int(bonus)
		elif '-' in rest:
			sides, bonus = rest.split('-', 1)
			bonus = -int(bonus)
		else:
			sides = rest
			bonus = 0
		return Dice(number=int(number), sides=int(sides), bonus=bonus)

	def load_zone_file(self, path):
		self.open_circle_file(path)
		while True:
			vnum = self.read_record_header()
			if vnum is None:
				return
			name = self.read_string()
			bot, top, lifespan, reset_mode = self.read_int_list()
			zone = CircleZone(vnum=vnum, name=name, bot=bot, top=top, lifespan=lifespan, reset_mode=reset_mode)
			while True:
				line = self.read_line().strip()
				if not line or line.startswith('*'):
					continue
				command = line[0]
				if command in ('S', '$'):
					break
				parts = line[1:].split()
				if command in ('M', 'O', 'E', 'P', 'D'):
					if_flag, arg1, arg2, arg3 = [int(part) for part in parts[:4]]
				else:
					if_flag, arg1, arg2 = [int(part) for part in parts[:3]]
					arg3 = None
				zone.resets.append(CircleReset(command=command, if_flag=if_flag, arg1=arg1, arg2=arg2, arg3=arg3))
			self.area.zones[vnum] = zone

	def load_room_file(self, path):
		self.open_circle_file(path)
		while True:
			vnum = self.read_record_header()
			if vnum is None:
				return
			room = self.read_room(vnum)
			self.area.rooms[vnum] = room

	def read_room(self, vnum):
		name = self.read_string()
		description = self.read_string()
		zone_number, flags, sector_type = self.read_line().split()
		room = CircleRoom(vnum=vnum, name=name, description=description, zone_number=int(zone_number), room_flags=circle_asciiflag_conv(flags), sector_type=int(sector_type))
		while True:
			line = self.read_line().strip()
			if line == 'S':
				return room
			if line.startswith('D'):
				exit = self.read_exit(int(line[1:]))
				room.exits[exit.door] = exit
			elif line == 'E':
				room.extra_descriptions.append(ExtraDescription(keyword=self.read_string(), description=self.read_string()))
			else:
				self.parse_fail("Unknown room metadata %r" % line)

	def read_exit(self, door):
		description = self.read_string()
		keyword = self.read_string()
		locks, key, destination = self.read_int_list()
		if locks == 1:
			exit_info = EXIT_FLAGS.ISDOOR
		elif locks == 2:
			exit_info = EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF
		else:
			exit_info = EXIT_FLAGS.NONE
		return CircleExit(door=door, description=description, keyword=keyword, exit_info=exit_info, key=key, destination=destination)

	def load_mobile_file(self, path):
		self.open_circle_file(path)
		while True:
			vnum = self.read_record_header()
			if vnum is None:
				return
			self.area.mobs[vnum] = self.read_mobile(vnum)

	def read_mobile(self, vnum):
		name = self.read_string()
		short_desc = self.read_string()
		long_desc = self.read_string()
		description = self.read_string()
		act_flags, affected_flags, alignment, mob_type = self.read_line().split()
		act = circle_asciiflag_conv(act_flags) | CircleMobFlags.ISNPC
		affected_by = circle_asciiflag_conv(affected_flags)
		level, source_hitroll, source_ac, hit_token, damage_token = self.read_line().split()
		wealth, exp = self.read_int_list()
		default_pos, start_pos, sex = self.read_int_list()
		especs = {}
		if mob_type.upper() == 'E':
			while True:
				line = self.read_line().strip()
				if line == 'E':
					break
				if ':' in line:
					key, value = line.split(':', 1)
					especs[key.strip()] = value.strip()
		return CircleMob(
			vnum=vnum,
			name=name,
			short_desc=short_desc,
			long_desc=long_desc,
			description=description,
			act=act,
			affected_by=affected_by,
			alignment=int(alignment),
			level=int(level),
			hitroll=20 - int(source_hitroll),
			ac=int(source_ac) * 10,
			hit=self.parse_dice_token(hit_token),
			damage=self.parse_dice_token(damage_token),
			wealth=wealth,
			exp=exp,
			default_pos=default_pos,
			start_pos=start_pos,
			sex=sex,
			especs=especs,
		)

	def load_object_file(self, path):
		self.open_circle_file(path)
		while True:
			vnum = self.read_record_header()
			if vnum is None:
				return
			self.area.objects[vnum] = self.read_item(vnum)

	def read_item(self, vnum):
		name = self.read_string()
		short_desc = self.read_string()
		description = self.read_string()
		action_description = self.read_string()
		item_type, extra_flags, wear_flags = self.read_line().split()
		value = self.read_int_list()
		weight, cost, rent = self.read_int_list()
		affected = []
		extra_descriptions = []
		while True:
			self.skip_whitespace()
			if self.current_char in ('#', '$', '\0'):
				break
			line = self.read_line().strip()
			if line == 'E':
				extra_descriptions.append(ExtraDescription(keyword=self.read_string(), description=self.read_string()))
			elif line == 'A':
				location, modifier = self.read_int_list()
				affected.append(CircleAffectData(location=location, modifier=modifier))
			else:
				self.parse_fail("Unknown object metadata %r" % line)
		return CircleItem(
			vnum=vnum,
			name=name,
			short_desc=short_desc,
			description=description,
			action_description=action_description,
			item_type=int(item_type),
			extra_flags=circle_asciiflag_conv(extra_flags),
			wear_flags=circle_asciiflag_conv(wear_flags),
			value=value,
			weight=weight,
			cost=cost,
			rent=rent,
			affected=affected,
			extra_descriptions=extra_descriptions,
		)

	def load_shop_file(self, path):
		self.open_circle_file(path)
		header = self.read_string()
		while True:
			vnum = self.read_record_header()
			if vnum is None:
				return
			self.area.shops[vnum] = self.read_shop(vnum, header)

	def read_number_list_until_minus_one(self):
		values = []
		while True:
			value = int(self.read_line().strip())
			if value == -1:
				return values
			values.append(value)

	def read_word_list_until_minus_one(self):
		values = []
		while True:
			value = self.read_line().strip()
			if value == '-1':
				return values
			values.append(value)

	def read_shop(self, vnum, header):
		products = self.read_number_list_until_minus_one()
		profit_buy = float(self.read_line().strip())
		profit_sell = float(self.read_line().strip())
		buy_type = self.read_word_list_until_minus_one()
		messages = [self.read_string() for _ in range(7)]
		temper = int(self.read_line().strip())
		bitvector = int(self.read_line().strip())
		keeper = int(self.read_line().strip())
		with_who = int(self.read_line().strip())
		rooms = self.read_number_list_until_minus_one()
		open_hour = int(self.read_line().strip())
		close_hour = int(self.read_line().strip())
		open_hour_2 = 0
		close_hour_2 = 0
		while self.current_char in ('\r', '\n'):
			self.index += 1
		if self.current_char not in ('#', '$', '\0'):
			open_hour_2 = int(self.read_line().strip())
			close_hour_2 = int(self.read_line().strip())
		return CircleShop(vnum=vnum, products=products, profit_buy=profit_buy, profit_sell=profit_sell, buy_type=buy_type, messages=messages, temper=temper, bitvector=bitvector, keeper=keeper, with_who=with_who, rooms=rooms, open_hour=open_hour, close_hour=close_hour, open_hour_2=open_hour_2, close_hour_2=close_hour_2)

	def as_dict(self):
		return EnumNameConverter().unstructure(self.area)

	def as_json(self, indent=None):
		return json.dumps(self.as_dict(), indent=indent)


@attributes
class CoffeeMudBehavior(object):
	class_id = attr(default='')
	parameters = attr(default='')


@attributes
class CoffeeMudAffect(object):
	class_id = attr(default='')
	text = attr(default='')


@attributes
class CoffeeMudAbility(object):
	class_id = attr(default='')
	proficiency = attr(default=0)
	data = attr(default='')


@attributes
class CoffeeMudMob(object):
	class_id = attr(default='')
	level = attr(default=0)
	ability = attr(default=0)
	rejuv = attr(default=0)
	name = attr(default='')
	description = attr(default='')
	display = attr(default='')
	race = attr(default='')
	gender = attr(default='')
	money = attr(default=0)
	variable_money = attr(default=0.0)
	flag = attr(default=0)
	behaviors = attr(default=Factory(list))
	affects = attr(default=Factory(list))
	factions = attr(default=Factory(dict))
	abilities = attr(default=Factory(list))
	raw_text = attr(default='')
	raw_data = attr(default=Factory(dict))


@attributes
class CoffeeMudItem(object):
	class_id = attr(default='')
	ident = attr(default='')
	location = attr(default='')
	count = attr(default=1)
	uses = attr(default=0)
	level = attr(default=0)
	ability = attr(default=0)
	rejuv = attr(default=0)
	name = attr(default='')
	description = attr(default='')
	display = attr(default='')
	prop = attr(default='')
	flag = attr(default=0)
	value = attr(default=0)
	material = attr(default=0)
	read_text = attr(default='')
	worn_location = attr(default='')
	worn_bitmap = attr(default=0)
	capacity = attr(default=0)
	container_flags = attr(default=0)
	open_ticks = attr(default=0)
	affects = attr(default=Factory(list))
	raw_text = attr(default='')
	raw_data = attr(default=Factory(dict))
	nested_area = attr(default=None)


@attributes
class CoffeeMudExit(object):
	direction = attr(default=0)
	target_room_id = attr(default='')
	class_id = attr(default='')
	raw_data = attr(default=Factory(dict))


@attributes
class CoffeeMudRoom(object):
	room_id = attr(default='')
	area = attr(default='')
	class_id = attr(default='')
	display = attr(default='')
	description = attr(default='')
	climate = attr(default=0)
	atmosphere = attr(default=0)
	exits = attr(default=Factory(list))
	mobs = attr(default=Factory(list))
	items = attr(default=Factory(list))
	raw_text = attr(default='')
	raw_data = attr(default=Factory(dict))


@attributes
class CoffeeMudArea(object):
	top_level = attr(default='')
	class_id = attr(default='')
	name = attr(default='')
	description = attr(default='')
	climate = attr(default=0)
	sub_ops = attr(default='')
	theme = attr(default=0)
	raw_data = attr(default=Factory(dict))
	rooms = attr(default=Factory(OrderedDict))
	mobs = attr(default=Factory(list))
	items = attr(default=Factory(list))
	objects = attr(default=Factory(list))


class CoffeeMudAreaFile(object):

	def __init__(self, filename):
		self.filename = os.fspath(filename)
		with io.open(filename, mode='rt', encoding='latin-1') as coffee_file:
			self.data = coffee_file.read()
		self.area = CoffeeMudArea()

	def load_sections(self):
		root = self.parse_document(self.data)
		self.load_root(root)

	def parse_document(self, text):
		text = self.escape_bare_ampersands(text)
		try:
			return ET.fromstring(text)
		except ET.ParseError:
			return ET.fromstring("<ROOT>" + text + "</ROOT>")

	def escape_bare_ampersands(self, text):
		return re.sub(r'&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]*;)', '&amp;', text)

	def parse_escaped_xml(self, value):
		if not value:
			return None
		return self.parse_document(html.unescape(value))

	def load_root(self, root):
		tag = self.clean_tag(root.tag)
		if tag == 'ROOT':
			for child in root:
				self.load_root(child)
			return
		if tag == 'MOBS':
			self.area.top_level = 'MOBS'
			self.area.mobs.extend(self.read_mobs(root))
		elif tag == 'MOB':
			self.area.top_level = 'MOB'
			self.area.mobs.append(self.read_mob(root))
		elif tag == 'ITEMS':
			self.area.top_level = 'ITEMS'
			self.area.items.extend(self.read_items(root))
			self.area.objects = self.area.items
		elif tag == 'ITEM':
			self.area.top_level = 'ITEM'
			item = self.read_item(root)
			self.area.items.append(item)
			self.area.objects = self.area.items
		elif tag == 'AREA':
			area = self.read_area(root)
			area.top_level = 'AREA'
			self.area = area
		elif tag == 'AROOMS':
			self.area.top_level = 'AROOMS'
			for room in self.read_rooms(root):
				self.area.rooms[room.room_id] = room
		elif tag == 'AROOM':
			self.area.top_level = 'AROOM'
			room = self.read_room(root)
			self.area.rooms[room.room_id] = room
		else:
			self.area.top_level = tag
			self.area.raw_data[tag] = self.element_to_data(root)

	def clean_tag(self, tag):
		if '}' in tag:
			return tag.rsplit('}', 1)[1]
		return tag

	def child(self, element, tag):
		for child in element:
			if self.clean_tag(child.tag).upper() == tag:
				return child
		return None

	def children(self, element, tag):
		return [child for child in element if self.clean_tag(child.tag).upper() == tag]

	def child_text(self, element, tag, default=''):
		child = self.child(element, tag)
		if child is None or child.text is None:
			return default
		return child.text

	def child_int(self, element, tag, default=0):
		text = self.child_text(element, tag, '')
		if text == '':
			return default
		try:
			return int(text)
		except ValueError:
			return default

	def child_float(self, element, tag, default=0.0):
		text = self.child_text(element, tag, '')
		if text == '':
			return default
		try:
			return float(text)
		except ValueError:
			return default

	def element_to_data(self, element):
		if len(element) == 0:
			return element.text or ''
		data = OrderedDict()
		for child in element:
			tag = self.clean_tag(child.tag)
			value = self.element_to_data(child)
			if tag in data:
				if not isinstance(data[tag], list):
					data[tag] = [data[tag]]
				data[tag].append(value)
			else:
				data[tag] = value
		return data

	def document_to_data(self, element):
		tag = self.clean_tag(element.tag)
		if tag == 'ROOT':
			return self.element_to_data(element)
		return OrderedDict([(tag, self.element_to_data(element))])

	def read_mobs(self, element, tag='MOB'):
		return [self.read_mob(child) for child in element if self.clean_tag(child.tag).upper() == tag]

	def read_mob(self, element):
		raw_text = self.child_text(element, 'MTEXT')
		raw_data = {}
		text_root = self.parse_escaped_xml(raw_text)
		if text_root is not None:
			raw_data = self.document_to_data(text_root)
		return CoffeeMudMob(
			class_id=self.child_text(element, 'MCLAS'),
			level=self.child_int(element, 'MLEVL'),
			ability=self.child_int(element, 'MABLE'),
			rejuv=self.child_int(element, 'MREJV', self.child_int(element, 'MREJUV')),
			name=self.value_from_data(raw_data, 'NAME'),
			description=self.value_from_data(raw_data, 'DESC'),
			display=self.value_from_data(raw_data, 'DISP'),
			race=self.value_from_data(raw_data, 'MRACE'),
			gender=self.value_from_data(raw_data, 'GENDER'),
			money=self.int_from_data(raw_data, 'MONEY'),
			variable_money=self.float_from_data(raw_data, 'VARMONEY'),
			flag=self.int_from_data(raw_data, 'FLAG'),
			behaviors=self.read_behaviors(text_root),
			affects=self.read_affects(text_root),
			factions=self.read_factions(text_root),
			abilities=self.read_abilities(text_root),
			raw_text=raw_text,
			raw_data=raw_data,
		)

	def read_behaviors(self, text_root):
		if text_root is None:
			return []
		behaves = self.child(text_root, 'BEHAVES')
		if behaves is None:
			return []
		return [
			CoffeeMudBehavior(
				class_id=self.child_text(behavior, 'BCLASS'),
				parameters=self.child_text(behavior, 'BPARMS'),
			)
			for behavior in self.children(behaves, 'BHAVE')
		]

	def read_affects(self, text_root):
		if text_root is None:
			return []
		affects = self.child(text_root, 'AFFECS')
		if affects is None:
			return []
		return [
			CoffeeMudAffect(
				class_id=self.child_text(affect, 'ACLASS'),
				text=self.child_text(affect, 'ATEXT'),
			)
			for affect in self.children(affects, 'AFF')
		]

	def read_factions(self, text_root):
		if text_root is None:
			return {}
		factions = self.child(text_root, 'FACTIONS')
		if factions is None:
			return {}
		result = {}
		for faction in self.children(factions, 'FCTN'):
			faction_id = faction.attrib.get('ID', '')
			if faction_id:
				result[faction_id] = self.int_text(faction.text)
		return result

	def read_abilities(self, text_root):
		if text_root is None:
			return []
		abilities = self.child(text_root, 'ABLTYS')
		if abilities is None:
			return []
		return [
			CoffeeMudAbility(
				class_id=self.child_text(ability, 'ACLASS'),
				proficiency=self.child_int(ability, 'APROF'),
				data=self.element_to_data(self.child(ability, 'ADATA')) if self.child(ability, 'ADATA') is not None else '',
			)
			for ability in self.children(abilities, 'ABLTY')
		]

	def read_items(self, element, tag='ITEM'):
		return [self.read_item(child) for child in element if self.clean_tag(child.tag).upper() == tag]

	def read_item(self, element):
		raw_text = self.child_text(element, 'ITEXT')
		raw_data = {}
		text_root = self.parse_escaped_xml(raw_text)
		if text_root is not None:
			raw_data = self.document_to_data(text_root)
		return CoffeeMudItem(
			class_id=self.child_text(element, 'ICLAS'),
			ident=self.child_text(element, 'IIDEN'),
			location=self.child_text(element, 'ILOCA'),
			count=self.int_text(element.attrib.get('COUNT'), 1),
			uses=self.child_int(element, 'IUSES'),
			level=self.child_int(element, 'ILEVL'),
			ability=self.child_int(element, 'IABLE'),
			rejuv=self.child_int(element, 'IREJV'),
			name=self.value_from_data(raw_data, 'NAME'),
			description=self.value_from_data(raw_data, 'DESC'),
			display=self.value_from_data(raw_data, 'DISP'),
			prop=self.value_from_data(raw_data, 'PROP'),
			flag=self.int_from_data(raw_data, 'FLAG'),
			value=self.int_from_data(raw_data, 'VALUE'),
			material=self.int_from_data(raw_data, 'MTRAL'),
			read_text=self.value_from_data(raw_data, 'READ'),
			worn_location=self.value_from_data(raw_data, 'WORNL'),
			worn_bitmap=self.int_from_data(raw_data, 'WORNB'),
			capacity=self.int_from_data(raw_data, 'CAPA'),
			container_flags=self.int_from_data(raw_data, 'CONT'),
			open_ticks=self.int_from_data(raw_data, 'OPENTK'),
			affects=self.read_affects(text_root),
			raw_text=raw_text,
			raw_data=raw_data,
		)

	def read_area(self, element):
		area = CoffeeMudArea(
			class_id=self.child_text(element, 'ACLAS'),
			name=self.child_text(element, 'ANAME'),
			description=self.child_text(element, 'ADESC'),
			climate=self.child_int(element, 'ACLIM'),
			sub_ops=self.child_text(element, 'ASUBS'),
			theme=self.child_int(element, 'ATECH'),
			raw_data=self.element_to_data(self.child(element, 'ADATA')) if self.child(element, 'ADATA') is not None else {},
		)
		rooms = self.child(element, 'AROOMS')
		if rooms is not None:
			for room in self.read_rooms(rooms):
				area.rooms[room.room_id] = room
		return area

	def read_rooms(self, element):
		return [self.read_room(child) for child in element if self.clean_tag(child.tag).upper() == 'AROOM']

	def read_room(self, element):
		raw_text = self.child_text(element, 'RTEXT')
		raw_data = {}
		text_root = self.parse_escaped_xml(raw_text)
		if text_root is not None:
			raw_data = self.document_to_data(text_root)
		return CoffeeMudRoom(
			room_id=self.child_text(element, 'ROOMID'),
			area=self.child_text(element, 'RAREA'),
			class_id=self.child_text(element, 'RCLAS'),
			display=self.child_text(element, 'RDISP'),
			description=self.child_text(element, 'RDESC'),
			climate=self.int_from_data(raw_data, 'RCLIM'),
			atmosphere=self.int_from_data(raw_data, 'RATMO'),
			exits=self.read_room_exits(element),
			mobs=self.read_room_mobs(element),
			items=self.read_room_items(element),
			raw_text=raw_text,
			raw_data=raw_data,
		)

	def read_room_exits(self, room_element):
		exits = self.child(room_element, 'ROOMEXITS')
		if exits is None:
			return []
		return [self.read_exit(exit_element) for exit_element in self.children(exits, 'REXIT')]

	def read_exit(self, element):
		exit_element = self.child(element, 'XEXIT')
		class_id = ''
		raw_data = {}
		if exit_element is not None:
			class_id = self.child_text(exit_element, 'EXID')
			raw_text = self.child_text(exit_element, 'EXDAT')
			raw_root = self.parse_escaped_xml(raw_text)
			if raw_root is not None:
				raw_data = self.document_to_data(raw_root)
		return CoffeeMudExit(
			direction=self.child_int(element, 'XDIRE'),
			target_room_id=self.child_text(element, 'XDOOR'),
			class_id=class_id,
			raw_data=raw_data,
		)

	def read_room_mobs(self, room_element):
		content = self.child(room_element, 'ROOMCONTENT')
		if content is None:
			return []
		mobs = self.child(content, 'ROOMMOBS')
		if mobs is None:
			return []
		return self.read_mobs(mobs, tag='RMOB')

	def read_room_items(self, room_element):
		content = self.child(room_element, 'ROOMCONTENT')
		if content is None:
			return []
		items = self.child(content, 'ROOMITEMS')
		if items is None:
			return []
		return self.read_items(items, tag='RITEM')

	def value_from_data(self, data, key, default=''):
		value = data.get(key, default)
		if isinstance(value, list):
			return value[0] if value else default
		if value is None:
			return default
		return value

	def int_from_data(self, data, key, default=0):
		value = self.value_from_data(data, key, '')
		if value == '':
			return default
		try:
			return int(value)
		except (TypeError, ValueError):
			return default

	def float_from_data(self, data, key, default=0.0):
		value = self.value_from_data(data, key, '')
		if value == '':
			return default
		try:
			return float(value)
		except (TypeError, ValueError):
			return default

	def int_text(self, text, default=0):
		if text is None or text == '':
			return default
		try:
			return int(text)
		except ValueError:
			return default

	def as_dict(self):
		return EnumNameConverter().unstructure(self.area)

	def as_json(self, indent=None):
		return json.dumps(self.as_dict(), indent=indent)


class EnumNameConverter(converters.Converter):
	def _unstructure_enum(self, obj):
		return obj.__class__.__name__ + "." + obj.name


def print_area(area_file_path, area_type=RomAreaFile):
	area_file = area_type(area_file_path)
	area_file.load_sections()
	print(area_file.as_json())

def main():
	if len(sys.argv) < 2:
		print("Must supply an area")
		sys.exit(1)
	print_area(sys.argv[1])

if __name__ == '__main__':
	main()
