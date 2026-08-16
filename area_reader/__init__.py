#! /usr/bin/env python3.11

import logging

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
from operator import setitem

from area_reader.constants import *
from area_reader.native import (
	NativeField,
	NativeSection,
	NativeWriteError,
	flag as native_flag,
	nested as native_nested,
	number as native_number,
	raw as native_raw,
	records as native_records,
	render_document,
	render_record,
	signed_number as native_signed_number,
	tilde_string as native_tilde_string,
	word as native_word,
)
import area_reader.serialization

logger = logging.getLogger('area_reader')
logging.basicConfig(level=logging.INFO)

def field(type=None, read=True, on_read=None, original_type=None, only_if=None, native=None, *args, **kwargs):
	metadata = dict(read=read)
	if on_read:
		metadata['on_read'] = on_read
	if original_type:
		metadata['original_type'] = original_type
	if only_if:
		metadata['only_if'] = only_if
	if native:
		metadata['native'] = native
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
		self.skipped_sections = []
		self.current_section_name = "N/A"
		self.readers = {
			Word: self.read_word,
			Letter: self.read_letter,
			VNum: self.read_number,
			str: self.read_string,
			int: self.read_number,
			VNum: self.read_number,
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
			if self.current_char != end:
				self.parse_fail("Unterminated quoted word")
			self.advance()
			return word
		while self.current_char != '\0' and not self.current_char.isspace():
			word += self.current_char
			self.advance()
		return word

	def read_string(self):
		self.skip_whitespace()
		res = self.read_until('~')
		if self.current_char != '~':
			self.parse_fail("Unterminated string")
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
		if not self.current_char.isdigit():
			self.parse_fail("Expected number")
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

	def read_smaug_programs(self):
		programs = []
		self.skip_whitespace()
		while self.current_char == '>':
			self.read_and_verify_letter('>')
			programs.append(
				SmaugProgram(
					trigger=self.read_word(),
					argument=self.read_string(),
					commands=self.read_string(),
				)
			)
			self.skip_whitespace()
		self.read_and_verify_letter('|')
		return programs

	def read_number_line(self):
		self.skip_whitespace()
		line = self.read_to_eol().strip()
		if not line:
			return []
		return [int(value) for value in line.split()]

	def read_until(self, endchar):
		ahead = self.data.find(endchar, self.index)
		if ahead == -1:
			ahead = len(self.data)
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
		words = []
		while True:
			components = []
			while True:
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
				components.append((negative, number))
				if self.current_char != '|':
					break
				self.advance()
			word = 0
			for negative, number in reversed(components):
				word += number
				if negative:
					word *= -1
			words.append(word)
			if self.current_char != '&':
				break
			self.advance()
		if len(words) == 1:
			return words[0]
		number = 0
		for index, word in enumerate(words):
			number |= (word & 0xFFFFFFFF) << (index * 32)
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
			'mobprogs': self.load_mobprogs,
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
				except ParseError:
					raise
				except Exception as error:
					self.parse_fail("Error reading section %r: %r" % (section_name, error))

	def load_mobprogs(self):
		while True:
			vnum = self.read_vnum()
			if vnum == 0:
				break
			self.area.mobprogs[vnum] = self.read_string()

	def skip_section(self, section_name):
		logger.debug("Skipping section %s", section_name)
		self.skipped_sections.append((section_name, self.read_until('#')))

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
			shop.comment = self.read_to_eol()

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
		return area_reader.serialization.EnumNameConverter().unstructure(self.area)

	def as_json(self, indent=None):
		return json.dumps(self.as_dict(), indent=indent)

	def save_as_json(self):
		fname = os.path.splitext(self.filename)[0] + '.json'
		with open(fname, 'w') as f:
			json.dump(self.as_dict(), f, indent=2)

class RomAreaFile(AreaFile):
	def dumps(self):
		return render_document(self.area, self.area.NATIVE_SECTIONS, self.skipped_sections)

	def write(self, path):
		with io.open(path, mode='wt', encoding='latin-1', newline='\n') as area_file:
			area_file.write(self.dumps())

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


def native_divide_by_ten(value, owner):
	del owner
	if value % 10:
		raise NativeWriteError("Armor class %r is not divisible by ten" % value)
	return str(value // 10)


def native_condition(value, owner):
	del owner
	conditions = {
		100: 'P',
		90: 'G',
		75: 'A',
		50: 'W',
		25: 'D',
		10: 'B',
		0: 'R',
	}
	try:
		return conditions[value]
	except KeyError:
		raise NativeWriteError("ROM condition %r has no native letter" % value)


def native_exit_lock(value, owner):
	del owner
	locks = {
		int(EXIT_FLAGS.NONE): 0,
		int(EXIT_FLAGS.ISDOOR): 1,
		int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF): 2,
		int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.NOPASS): 3,
		int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.NOPASS | EXIT_FLAGS.PICKPROOF): 4,
	}
	try:
		return str(locks[int(value)])
	except KeyError:
		raise NativeWriteError("ROM exit flags %r have no native lock code" % value)


def native_item_values(value, owner):
	if len(value) != 5:
		raise NativeWriteError("ROM object values must contain five entries")
	word_positions = {
		'weapon': {0, 3},
		'drink': {2},
		'fountain': {2},
		'wand': {3},
		'staff': {3},
		'potion': {1, 2, 3, 4},
		'pill': {1, 2, 3, 4},
		'scroll': {1, 2, 3, 4},
	}.get(owner.item_type, set())
	encoded = []
	for index, item in enumerate(value):
		encoder = native_word if index in word_positions else native_flag
		encoded.append(encoder(item, owner))
	return ' '.join(encoded)


def native_four_numbers(value, owner):
	if len(value) != 4:
		raise NativeWriteError("Merc object values must contain four entries")
	return ' '.join(native_number(item, owner) for item in value)


def native_merc_exit_lock(value, owner):
	del owner
	locks = {
		int(EXIT_FLAGS.NONE): 0,
		int(EXIT_FLAGS.ISDOOR): 1,
		int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF): 2,
	}
	try:
		return str(locks[int(value)])
	except KeyError:
		raise NativeWriteError("Merc exit flags %r have no native lock code" % value)


def native_trade_types(value, owner):
	del owner
	if len(value) != AreaFile.MAX_TRADES:
		raise NativeWriteError("ROM shops require exactly five trade types")
	return ' '.join(str(item) for item in value)


def native_numbers(value, owner):
	del owner
	return ' '.join(native_number(item, None) for item in value)


def native_words(value, owner):
	del owner
	return ' '.join(native_word(item, None) for item in value)


def native_number_lines(value, owner):
	del owner
	return '\n'.join(native_numbers(line, None) for line in value)


def native_smaug_programs(value, owner):
	del owner
	if not value:
		return ''
	return ''.join(render_record(program) for program in value) + '|\n'


def native_dice_inline(value, owner):
	del owner
	return '%dd%d%+d' % (value.number, value.sides, value.bonus)


def native_swr_unknown_value(value, owner):
	if owner.tilde:
		return native_tilde_string(value, owner)
	return native_raw(value, owner)


def native_swr_reset_arg2_suffix(owner):
	return '' if owner.command in ('G', 'R') else ' '


def native_swr_armor_class(value, owner):
	del owner
	classes = (value.pierce, value.bash, value.slash, value.exotic)
	if len(set(classes)) != 1:
		raise NativeWriteError("SWR mobiles require one armor class value")
	return native_number(value.pierce, None)


def native_swr_dice(value, owner):
	del owner
	return '%d %d %d' % (value.number, value.sides, value.bonus)


def native_reset_command(value, owner):
	del owner
	return '*' if value is None else str(value)


def native_comment(value, owner):
	del owner
	if not value:
		return ''
	return str(value)


def native_reset_command_suffix(owner):
	return '' if owner.command is None else ' '


def native_reset_arg2_suffix(owner):
	return '' if owner.command in ('G', 'R') else ' '


def native_reset_arg3_suffix(owner):
	return ' ' if owner.command in ('P', 'M') else ''


@attributes
class ExtraDescription(object):
	keyword = field(default='', type=str, native=NativeField(1, native_tilde_string, prefix='E\n'))
	description = field(default='', type=str, native=NativeField(2, native_tilde_string))

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
	type = attr(default=-1)
	duration = attr(default=-1)
	location = field(default=-1, native=NativeField(1, native_number, prefix='A\n'))
	modifier = field(default=-1, native=NativeField(2, native_number))
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

	vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(1, native_tilde_string))
	short_desc = field(default='', type=str, native=NativeField(2, native_tilde_string))
	description = field(default='', type=str, native=NativeField(3, native_tilde_string))
	material = field(default='', type=str, native=NativeField(4, native_tilde_string))
	item_type = field(default=-1, type=int, native=NativeField(5, native_word))
	extra_flags = field(default=0, type=int, native=NativeField(6, native_flag))
	wear_flags = field(default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS, native=NativeField(7, native_flag))
	value = field(default=Factory(list), type=List, native=NativeField(8, native_item_values))
	level = field(default=0, type=int, native=NativeField(9, native_number))
	weight = field(default=0, type=int, native=NativeField(10, native_number))
	cost = field(default=0, type=int, native=NativeField(11, native_number))
	condition = field(default=100, type=int, original_type=Letter, on_read=convert_condition, native=NativeField(12, native_condition))
	affected = field(default=Factory(list), native=NativeField(13, native_records, suffix=''))
	extra_descriptions = field(default=Factory(list), type=List[ExtraDescription], native=NativeField(14, native_records, suffix=''))

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
				af.where = 'TO_OBJECT'
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
					reader.parse_fail("Bad where on flag set")
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
	pierce = field(default=0, type=int, on_read=multiply_10, native=NativeField(1, native_divide_by_ten))
	bash = field(default=0, type=int, on_read=multiply_10, native=NativeField(2, native_divide_by_ten))
	slash = field(default=0, type=int, on_read=multiply_10, native=NativeField(3, native_divide_by_ten))
	exotic = field(default=0, type=int, on_read=multiply_10, native=NativeField(4, native_divide_by_ten))

@attributes
class Dice(object):
	number = field(default=0, type=int, native=NativeField(1, native_number, suffix=''))
	sides = field(default=0, type=int, native=NativeField(2, native_number, prefix='d', suffix=''))
	bonus = field(default=0, type=int, native=NativeField(3, native_signed_number))

	@classmethod
	def read(cls, reader, **kwargs):
		number = reader.read_number()
		reader.read_letter() #D
		sides = reader.read_number()
		bonus = reader.read_number()
		return cls(number=number, sides=sides, bonus=bonus, **kwargs)

	def roll(self):
		# ROM's dice() (src/db.c) returns 0 for size 0, and its
		# number_range() clamps a degenerate range to the low bound,
		# so negative sides roll 1 per die.
		if self.sides == 0:
			return self.bonus
		score = 0
		sides = max(self.sides, 1)
		for roll in range(self.number):
			score += random.randrange(1, sides + 1)
		score += self.bonus
		return score

@attributes
class RomMobprog(object):
	trig_type = field(default=None, type=Word, native=NativeField(1, native_word, prefix='M ', suffix=' '))
	vnum = field(default=-1, type=VNum, native=NativeField(2, native_number, suffix=' '))
	trig_phrase = field(default=None, type=str, native=NativeField(3, native_tilde_string))

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
	vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(1, native_tilde_string))
	short_desc = field(default='', type=str, native=NativeField(2, native_tilde_string))
	long_desc = field(default='', type=str, native=NativeField(3, native_tilde_string))
	description = field(default='', type=str, native=NativeField(4, native_tilde_string))
	race = field(default='', type=str, native=NativeField(5, native_tilde_string))
	act = field(default=0, type=ROM_ACT_TYPES, converter=ROM_ACT_TYPES, native=NativeField(6, native_flag))
	affected_by = field(default=0, type=AFFECTED_BY, converter=AFFECTED_BY, native=NativeField(7, native_flag))
	alignment = field(default=0, type=int, native=NativeField(8, native_number))
	group = field(default=0, type=int, native=NativeField(9, native_number))
	level = field(default=0, type=int, native=NativeField(10, native_number))
	hitroll = field(default=0, type=int, native=NativeField(11, native_number))
	hit = field(default=Factory(Dice), type=Dice, native=NativeField(12, native_nested))
	mana = field(default=Factory(Dice), type=Dice, native=NativeField(13, native_nested))
	damage = field(default=Factory(Dice), type=Dice, native=NativeField(14, native_nested))
	damtype = field(default='', type=Word, native=NativeField(15, native_word))
	ac = field(default=Factory(RomArmorClass), type=RomArmorClass, native=NativeField(16, native_nested))
	shop = field(default=None, read=False)
	off_flags = field(default=0, type=OFFENSE, converter=OFFENSE, native=NativeField(17, native_flag))
	imm_flags = field(default=0, type=IMM_FLAGS, converter=IMM_FLAGS, native=NativeField(18, native_flag))
	res_flags = field(default=0, type=IMM_FLAGS, converter=IMM_FLAGS, native=NativeField(19, native_flag))
	vuln_flags = field(default=0, type=IMM_FLAGS, converter=IMM_FLAGS, native=NativeField(20, native_flag))
	start_pos = field(default=None, type=Word, native=NativeField(21, native_word))
	default_pos = field(default=None, type=Word, native=NativeField(22, native_word))
	sex = field(default='', type=Word, native=NativeField(23, native_word))
	wealth = field(default=0, type=int, native=NativeField(24, native_number))
	form = field(default=0, type=FORMS, converter=FORMS, native=NativeField(25, native_flag))
	parts = field(default=0, type=PARTS, converter=PARTS, native=NativeField(26, native_flag))
	size = field(default=None, type=Word, native=NativeField(27, native_word))
	material = field(default='', type=str, native=NativeField(28, native_word))
	mprogs = field(default=Factory(list), type=Optional[List[RomMobprog]], native=NativeField(29, native_records))

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


def native_affect_prefix(owner):
	if owner.where == 'TO_OBJECT':
		return 'A\n'
	letters = {
		'TO_AFFECTS': 'A',
		'TO_IMMUNE': 'I',
		'TO_RESIST': 'R',
		'TO_VULN': 'V',
	}
	try:
		return 'F%s ' % letters[owner.where]
	except KeyError:
		raise NativeWriteError("ROM affect target %r has no native tag" % owner.where)


def native_affect_modifier_suffix(owner):
	return '\n' if owner.where == 'TO_OBJECT' else ' '


@attributes
class RomAffectData(object):
	where = attr(default=None)
	type = attr(default=None)
	level = attr(default=None)
	duration = attr(default=None)
	location = field(default=None, native=NativeField(1, native_number, prefix=native_affect_prefix, suffix=' '))
	modifier = field(default=None, native=NativeField(2, native_number, suffix=native_affect_modifier_suffix))
	bitvector = field(
		default=0,
		native=NativeField(
			3,
			native_flag,
			when=lambda owner: owner.where != 'TO_OBJECT',
		),
	)


@attributes
class MercArea(object):
	NATIVE_SECTIONS = (
		NativeSection('AREA', owner_section='area'),
		NativeSection('HELPS', collection='helps', end='0 $~\n'),
		NativeSection('MOBILES', collection='mobs', end='#0\n', mapping=True),
		NativeSection('OBJECTS', collection='objects', end='#0\n', mapping=True),
		NativeSection('ROOMS', collection='rooms', end='#0\n', mapping=True),
		NativeSection('RESETS', collection='resets', end='S\n'),
		NativeSection('SHOPS', collection='shops', end='0\n'),
		NativeSection('SPECIALS', collection='specials', end='S\n'),
	)

	metadata = field(default='', native=NativeField(1, native_tilde_string, section='area'))
	helps = attr(default=Factory(list))
	rooms = attr(default=Factory(OrderedDict))
	mobs = attr(default=Factory(OrderedDict))
	objects = attr(default=Factory(OrderedDict))
	resets = attr(default=Factory(list))
	specials = attr(default=Factory(list))
	shops = attr(default=Factory(list))
	mobprogs = attr(default=Factory(OrderedDict))


@attributes
class Help(object):
	level = field(default=0, type=int, native=NativeField(1, native_number, suffix=' '))
	keyword = field(default='', type=Word, native=NativeField(2, native_tilde_string))
	text = field(default='', type=str, native=NativeField(3, native_tilde_string))

@attributes
class Exit(object):
	keyword = field(default='', type=Word, native=NativeField(3, native_tilde_string))
	description = field(default='', type=str, native=NativeField(2, native_tilde_string))
	door = field(
		default=None,
		type=Optional[EXIT_DIRECTIONS],
		converter=lambda value: None if value is None else EXIT_DIRECTIONS(value),
		native=NativeField(1, native_number, prefix='D'),
	)
	exit_info = field(default=0, type=EXIT_FLAGS, converter=EXIT_FLAGS, native=NativeField(4, native_exit_lock))
	rs_flags = attr(default=0, type=int)
	key = field(default=0, type=int, native=NativeField(5, native_number))
	destination = field(default=None, type=int, native=NativeField(6, native_number))

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
class MercExit(Exit):
	exit_info = field(
		default=0,
		type=EXIT_FLAGS,
		converter=EXIT_FLAGS,
		native=NativeField(4, native_merc_exit_lock),
	)


@attributes
class SmaugProgram(object):
	trigger = field(default='', type=Word, native=NativeField(1, native_word, prefix='> ', suffix=' '))
	argument = field(default='', type=str, native=NativeField(2, native_tilde_string))
	commands = field(default='', type=str, native=NativeField(3, native_tilde_string))


@attributes
class SmaugMap(object):
	vnum = field(default=0, type=int, native=NativeField(1, native_number, prefix='M ', suffix=' '))
	x = field(default=0, type=int, native=NativeField(2, native_number, suffix=' '))
	y = field(default=0, type=int, native=NativeField(3, native_number, suffix=' '))
	entry = field(default='', type=Letter, native=NativeField(4, native_word))


@attributes
class SmaugRepair(object):
	keeper = field(default=0, type=int, native=NativeField(1, native_number, suffix=' '))
	fix_type = field(default=Factory(list), type=list, native=NativeField(2, native_numbers, suffix=' '))
	profit_fix = field(default=0, type=int, native=NativeField(3, native_number, suffix=' '))
	shop_type = field(default=0, type=int, native=NativeField(4, native_number, suffix=' '))
	open_hour = field(default=0, type=int, native=NativeField(5, native_number, suffix=' '))
	close_hour = field(default=0, type=int, native=NativeField(6, native_number, suffix=''))
	comment = field(default='', type=str, native=NativeField(7, native_comment))


@attributes
class SmaugExit(Exit):
	door = field(default=None, type=int, native=NativeField(1, native_number, prefix='D'))
	description = field(default='', type=str, native=NativeField(2, native_tilde_string))
	keyword = field(default='', type=Word, native=NativeField(3, native_tilde_string))
	locks = field(default=0, type=int, native=NativeField(4, native_number, suffix=' '))
	exit_info = attr(default=0, type=EXIT_FLAGS, converter=EXIT_FLAGS)
	key = field(default=0, type=int, native=NativeField(5, native_number, suffix=' '))
	destination = field(default=None, type=int, native=NativeField(6, native_number, suffix=' '))
	distance = field(default=0, type=int, native=NativeField(7, native_number, suffix=' '))
	x = attr(default=0, type=int)
	y = attr(default=0, type=int)
	pulltype = field(default=0, type=int, native=NativeField(8, native_number, suffix=' '))
	pull = field(default=0, type=int, native=NativeField(9, native_number))

@attributes
class Room(MudBase):
	NATIVE_SUFFIX = 'S\n'

	vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(1, native_tilde_string))
	description = field(default='', type=str, native=NativeField(2, native_tilde_string))
	owner = field(
		default=None,
		type=str,
		native=NativeField(10, native_tilde_string, prefix='O ', when=lambda owner: bool(owner.owner)),
	)
	clan = field(
		default='',
		type=str,
		native=NativeField(7, native_tilde_string, prefix='C ', when=lambda owner: bool(owner.clan)),
	)
	area = attr(default=None)
	area_number = field(default=0, type=int, native=NativeField(3, native_number))
	room_flags = field(default=0, type=ROM_ROOM_FLAGS, converter=ROM_ROOM_FLAGS, native=NativeField(4, native_flag))
	sector_type = field(default=0, type=SECTOR_TYPES, converter=SECTOR_TYPES, native=NativeField(5, native_number)) #FIXME
	heal_rate = field(
		default=100,
		type=int,
		native=NativeField(6, native_number, prefix='H ', when=lambda owner: owner.heal_rate != 100),
	)
	mana_rate = field(
		default=100,
		type=int,
		native=NativeField(7, native_number, prefix='M ', when=lambda owner: owner.mana_rate != 100),
	)
	exits = field(default=Factory(list), type=List[Exit], native=NativeField(8, native_records, suffix=''))
	extra_descriptions = field(default=Factory(list), type=List[ExtraDescription], native=NativeField(9, native_records, suffix=''))

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
	command = field(default=None, native=NativeField(1, native_reset_command, suffix=native_reset_command_suffix))
	if_flag = field(
		default=0,
		native=NativeField(2, native_number, suffix=' ', when=lambda owner: owner.command is not None),
	)
	arg1 = field(
		default=None,
		type=Letter,
		native=NativeField(3, native_number, suffix=' ', when=lambda owner: owner.command is not None),
	)
	arg2 = field(
		default=None,
		native=NativeField(4, native_number, suffix=native_reset_arg2_suffix, when=lambda owner: owner.command is not None),
	)
	arg3 = field(
		default=None,
		native=NativeField(5, native_number, suffix=native_reset_arg3_suffix, when=lambda owner: owner.command not in (None, 'G', 'R')),
	)
	arg4 = field(
		default=None,
		native=NativeField(6, native_number, suffix='', when=lambda owner: owner.command in ('P', 'M')),
	)
	comment = field(default=None, type=str, native=NativeField(7, native_comment))

	@classmethod
	def read(cls, reader, letter):
		command = letter
		if_flag = reader.read_number()
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
		comment = reader.read_to_eol()
		return cls(command=command, if_flag=if_flag, arg1=arg1, arg2=arg2, arg3=arg3, arg4=arg4, comment=comment)

@attributes
class Special(object):
	command = field(default=None, native=NativeField(1, native_reset_command, suffix=native_reset_command_suffix))
	arg1 = field(
		default=None,
		native=NativeField(2, native_number, suffix=' ', when=lambda owner: owner.command is not None),
	)
	arg2 = field(
		default=None,
		native=NativeField(3, native_word, suffix='', when=lambda owner: owner.command is not None),
	)
	comment = field(default=None, type=str, native=NativeField(4, native_comment))

	@classmethod
	def read(cls, reader, letter, **kwargs):
		command = letter
		arg1 = reader.read_number()
		arg2 = reader.read_word()
		comment = reader.read_to_eol()
		return cls(command=command,arg1=arg1, arg2=arg2, comment=comment)

@attributes
class RomArea(object):
	NATIVE_SECTIONS = (
		NativeSection('AREA', owner_section='area'),
		NativeSection('HELPS', collection='helps', end='0 $~\n'),
		NativeSection('MOBILES', collection='mobs', end='#0\n', mapping=True),
		NativeSection('OBJECTS', collection='objects', end='#0\n', mapping=True),
		NativeSection('ROOMS', collection='rooms', end='#0\n', mapping=True),
		NativeSection('RESETS', collection='resets', end='S\n'),
		NativeSection('SHOPS', collection='shops', end='0\n'),
		NativeSection('SPECIALS', collection='specials', end='S\n'),
	)

	name = field(default='', native=NativeField(2, native_tilde_string, section='area'))
	metadata = field(default='', native=NativeField(3, native_tilde_string, section='area'))
	original_filename = field(default='', native=NativeField(1, native_tilde_string, section='area'))
	first_vnum = field(default=-1, native=NativeField(4, native_number, section='area'))
	last_vnum = field(default=-1, native=NativeField(5, native_number, section='area'))
	helps = attr(default=Factory(list), type=List[Help])
	rooms = attr(default=Factory(OrderedDict), type=Dict[int, Room])
	mobs = attr(default=Factory(OrderedDict))
	objects = attr(default=Factory(OrderedDict))
	resets = attr(default=Factory(list), type=List[Reset])
	specials = attr(default=Factory(list), type=List[Special])
	shops = attr(default=Factory(list))
	mobprogs = attr(default=Factory(OrderedDict))

@attributes
class MercRoom(Room):
	owner = attr(default=None, type=str)
	clan = attr(default='', type=str)
	room_flags = field(
		default=0,
		type=MERC_ROOM_FLAGS,
		converter=MERC_ROOM_FLAGS,
		native=NativeField(4, native_flag),
	)
	heal_rate = attr(default=100, type=int)
	mana_rate = attr(default=100, type=int)
	exits = field(default=Factory(list), type=List[MercExit], native=NativeField(8, native_records, suffix=''))

	def read_metadata(self, reader):
		logger.debug("Reading room data for %d" % self.vnum)
		while True:
			letter = reader.read_letter()
			if letter == 'S':
				break
			if letter == 'D':
				self.exits.append(MercExit.read(reader=reader))
			elif letter == 'E':
				self.extra_descriptions.append(reader.read_object(ExtraDescription))
			else:
				reader.parse_fail("room %d has flag %s not DES" % (self.vnum, letter))

@attributes
class RomShop(object):
	keeper = field(default=0, type=int, native=NativeField(1, native_number, suffix=' '))
	buy_type = field(default=Factory(list), type=list, native=NativeField(2, native_trade_types, suffix=' '))
	profit_buy = field(default=0, type=int, native=NativeField(3, native_number, suffix=' '))
	profit_sell = field(default=0, type=int, native=NativeField(4, native_number, suffix=' '))
	open_hour = field(default=0, type=int, native=NativeField(5, native_number, suffix=' '))
	close_hour = field(default=0, type=int, native=NativeField(6, native_number, suffix=''))
	comment = field(default='', type=str, native=NativeField(7, native_comment))

@attributes
class SmaugMob(RomMob):
	vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(1, native_tilde_string))
	short_desc = field(default='', type=str, native=NativeField(2, native_tilde_string))
	long_desc = field(default='', type=str, native=NativeField(3, native_tilde_string))
	description = field(default='', type=str, native=NativeField(4, native_tilde_string))
	race = attr(default='', type=str)
	act = field(default=SMAUG_ACT_TYPES.IS_NPC.value, type=SMAUG_ACT_TYPES, converter=SMAUG_ACT_TYPES, native=NativeField(5, native_flag, suffix=' '))
	affected_by = field(default=0, type=SMAUG_AFFECTED_BY, converter=SMAUG_AFFECTED_BY, native=NativeField(6, native_flag, suffix=' '))
	alignment = field(default=0, type=int, native=NativeField(7, native_number, suffix=' '))
	native_type = field(default='S', type=Letter, native=NativeField(8, native_word))
	group = attr(default=0, type=int)
	level = field(default=0, type=int, native=NativeField(9, native_number, suffix=' '))
	hitroll = field(default=0, type=int, native=NativeField(10, native_number, suffix=' '))
	ac = field(default=0, type=int, native=NativeField(11, native_number, suffix=' '))
	hit = field(default=Factory(Dice), type=Dice, native=NativeField(12, native_dice_inline, suffix=' '))
	mana = attr(default=Factory(Dice), type=Dice)
	damage = field(default=Factory(Dice), type=Dice, native=NativeField(13, native_dice_inline))
	damtype = attr(default='', type=Word)
	economy_lines = field(default=Factory(list), type=list, native=NativeField(14, native_number_lines, when=lambda owner: bool(owner.economy_lines)))
	position_line = field(default=Factory(list), type=list, native=NativeField(15, native_numbers))
	complex_lines = field(default=Factory(list), type=list, native=NativeField(16, native_number_lines, when=lambda owner: bool(owner.complex_lines)))
	wealth = attr(default=0, type=int)
	start_pos = attr(default=0, type=int)
	default_pos = attr(default=0, type=int)
	sex = attr(default=0, type=int)
	off_flags = attr(default=0, type=OFFENSE, converter=OFFENSE)
	imm_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	res_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	vuln_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	form = attr(default=0, type=FORMS, converter=FORMS)
	parts = attr(default=0, type=PARTS, converter=PARTS)
	size = attr(default=None, type=Word)
	material = attr(default='', type=str)
	mprogs = attr(default=Factory(list), type=Optional[List[RomMobprog]])
	programs = field(default=Factory(list), type=List[SmaugProgram], native=NativeField(17, native_smaug_programs, suffix=''))

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading SMAUG mob %d", vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		long_desc = reader.read_string()
		description = reader.read_string()
		act = reader.read_flag() | SMAUG_ACT_TYPES.IS_NPC
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
		economy_lines = numeric_lines[:position_index]
		complex_lines = numeric_lines[position_index + 1:]
		programs = reader.read_smaug_programs() if reader.current_char == '>' else []
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc, description=description, act=act, affected_by=affected_by, alignment=alignment, native_type=letter, level=level, hitroll=hitroll, ac=ac, hit=hit, damage=damage, economy_lines=economy_lines, position_line=position_line, complex_lines=complex_lines, wealth=wealth, start_pos=start_pos, default_pos=default_pos, sex=sex, programs=programs)

@attributes
class SmaugItem(Item):
	vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(1, native_tilde_string))
	short_desc = field(default='', type=str, native=NativeField(2, native_tilde_string))
	description = field(default='', type=str, native=NativeField(3, native_tilde_string))
	action_description = field(default='', type=str, native=NativeField(4, native_tilde_string))
	item_type = field(default=-1, type=int, native=NativeField(5, native_number, suffix=' '))
	extra_flags = field(default=0, type=int, native=NativeField(6, native_flag, suffix=' '))
	wear_flags = field(default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS, native=NativeField(7, native_flag, suffix=' '))
	header_tail = field(default=Factory(list), type=list, native=NativeField(8, native_numbers))
	layers = attr(default=0, type=int)
	level = attr(default=0, type=int)
	value = field(default=Factory(list), type=List, native=NativeField(9, native_numbers))
	weight = field(default=0, type=int, native=NativeField(10, native_number, suffix=' '))
	cost = field(default=0, type=int, native=NativeField(11, native_number, suffix=' '))
	cost_tail = field(default=Factory(list), type=list, native=NativeField(12, native_numbers))
	spell_words = field(default=Factory(list), type=list, native=NativeField(13, native_words, when=lambda owner: bool(owner.spell_words)))
	affected = field(default=Factory(list), native=NativeField(14, native_records, suffix=''))
	extra_descriptions = field(default=Factory(list), type=List[ExtraDescription], native=NativeField(15, native_records, suffix=''))
	programs = field(default=Factory(list), type=List[SmaugProgram], native=NativeField(16, native_smaug_programs, suffix=''))

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading SMAUG object %d", vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		description = reader.read_string()
		action_description = reader.read_string()
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
		cost_tail = cost_line[2:]
		reader.skip_whitespace()
		spell_words = []
		if reader.current_char not in ('A', 'E', '>', '#'):
			spell_words = reader.read_to_eol().split()
		affected = []
		extra_descriptions = []
		programs = []
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
				programs = reader.read_smaug_programs()
			else:
				reader.index -= 1
				break
		return cls(vnum=vnum, name=name, short_desc=short_desc, description=description, action_description=action_description, item_type=item_type, extra_flags=extra_flags, wear_flags=wear_flags, header_tail=header, value=value, level=level, weight=weight, cost=cost, cost_tail=cost_tail, spell_words=spell_words, affected=affected, extra_descriptions=extra_descriptions, layers=layers, programs=programs)

@attributes
class SmaugArea(RomArea):
	NATIVE_SECTIONS = (
		NativeSection('AREA', owner_section='area'),
		NativeSection('VERSION', owner_section='version', when=lambda area: area.version != 0),
		NativeSection('AUTHOR', owner_section='author', when=lambda area: bool(area.author)),
		NativeSection('CREDITS', owner_section='credits', when=lambda area: bool(area.credits)),
		NativeSection('RANGES', owner_section='ranges'),
		NativeSection('RESETMSG', owner_section='resetmsg', when=lambda area: bool(area.resetmsg)),
		NativeSection('FLAGS', owner_section='flags'),
		NativeSection('ECONOMY', owner_section='economy'),
		NativeSection('CONTINENT', owner_section='continent', when=lambda area: bool(area.continent)),
		NativeSection('CLIMATE', owner_section='climate', when=lambda area: bool(area.climate)),
		NativeSection('SPELLLIMIT', owner_section='spelllimit', when=lambda area: area.spelllimit != 0),
		NativeSection('HELPS', collection='helps', end='0 $~\n'),
		NativeSection('MOBILES', collection='mobs', end='#0\n', mapping=True),
		NativeSection('OBJECTS', collection='objects', end='#0\n', mapping=True),
		NativeSection('ROOMS', collection='rooms', end='#0\n', mapping=True),
		NativeSection('RESETS', collection='resets', end='S\n'),
		NativeSection('SHOPS', collection='shops', end='0\n'),
		NativeSection('REPAIRS', collection='repairs', end='0\n'),
		NativeSection('SPECIALS', collection='specials', end='S\n'),
	)

	name = field(default='', type=str, native=NativeField(1, native_tilde_string, section='area'))
	metadata = attr(default='', type=str)
	original_filename = attr(default='', type=str)
	first_vnum = attr(default=-1, type=int)
	last_vnum = attr(default=-1, type=int)
	version = field(default=0, type=int, native=NativeField(1, native_number, section='version'))
	author = field(default='', type=str, native=NativeField(1, native_tilde_string, section='author'))
	credits = field(default='', type=str, native=NativeField(1, native_tilde_string, section='credits'))
	low_soft_range = field(default=0, type=int, native=NativeField(1, native_number, suffix=' ', section='ranges'))
	high_soft_range = field(default=0, type=int, native=NativeField(2, native_number, suffix=' ', section='ranges'))
	low_hard_range = field(default=0, type=int, native=NativeField(3, native_number, suffix=' ', section='ranges'))
	high_hard_range = field(default=0, type=int, native=NativeField(4, native_number, suffix='\n$\n', section='ranges'))
	resetmsg = field(default='', type=str, native=NativeField(1, native_tilde_string, section='resetmsg'))
	flags = field(default=0, type=int, native=NativeField(1, native_number, suffix=' ', section='flags'))
	reset_frequency = field(default=0, type=int, native=NativeField(2, native_number, section='flags'))
	high_economy = field(default=0, type=int, native=NativeField(1, native_number, suffix=' ', section='economy'))
	low_economy = field(default=0, type=int, native=NativeField(2, native_number, section='economy'))
	continent = field(default='', type=str, native=NativeField(1, native_tilde_string, section='continent'))
	climate = field(default=Factory(list), type=list, native=NativeField(1, native_numbers, section='climate'))
	spelllimit = field(default=0, type=int, native=NativeField(1, native_number, section='spelllimit'))
	helps = attr(default=Factory(list), type=List[Help])
	rooms = attr(default=Factory(OrderedDict))
	mobs = attr(default=Factory(OrderedDict))
	objects = attr(default=Factory(OrderedDict))
	resets = attr(default=Factory(list))
	specials = attr(default=Factory(list))
	shops = attr(default=Factory(list))
	repairs = attr(default=Factory(list), type=List[SmaugRepair])

@attributes
class SmaugRoom(Room):
	vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(1, native_tilde_string))
	description = field(default='', type=str, native=NativeField(2, native_tilde_string))
	owner = attr(default=None, type=str)
	clan = attr(default='', type=str)
	area_number = field(default=0, type=int, native=NativeField(3, native_number, suffix=' '))
	room_flags = field(default=0, type=int, native=NativeField(4, native_flag, suffix=' '))
	sector_type = field(default=0, type=int, native=NativeField(5, native_number, suffix=' '))
	heal_rate = attr(default=100, type=int)
	mana_rate = attr(default=100, type=int)
	tele_delay = field(default=0, type=int, native=NativeField(6, native_number, suffix=' '))
	tele_vnum = field(default=0, type=int, native=NativeField(7, native_number, suffix=' '))
	tunnel = field(default=0, type=int, native=NativeField(8, native_number, suffix=' '))
	max_weight = field(default=0, type=int, native=NativeField(9, native_number))
	exits = field(default=Factory(list), type=List[SmaugExit], native=NativeField(10, native_records, suffix=''))
	extra_descriptions = field(default=Factory(list), type=List[ExtraDescription], native=NativeField(11, native_records, suffix=''))
	maps = field(default=Factory(list), type=List[SmaugMap], native=NativeField(12, native_records, suffix=''))
	programs = field(default=Factory(list), type=List[SmaugProgram], native=NativeField(13, native_smaug_programs, suffix=''))
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
				self.maps.append(SmaugMap(vnum=reader.read_number(), x=reader.read_number(), y=reader.read_number(), entry=reader.read_letter()))
			elif letter == '>':
				reader.index -= 1
				self.programs = reader.read_smaug_programs()
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
		return SmaugExit(door=door, description=description, keyword=keyword, locks=locks, exit_info=exit_info, key=key, destination=destination, distance=distance, pulltype=pulltype, pull=pull)

@attributes
class SwrUnknown(object):
	key = field(default='', type=Word, native=NativeField(1, native_word, suffix=' '))
	value = field(default='', type=str, native=NativeField(2, native_swr_unknown_value))
	tilde = attr(default=False, type=bool)


@attributes
class SwrProgram(object):
	NATIVE_PREFIX = '#MUDPROG\n'
	NATIVE_SUFFIX = '#ENDPROG\n\n'

	progtype = field(default='', type=str, native=NativeField(1, native_tilde_string, prefix='Progtype  '))
	argument = field(default='', type=str, native=NativeField(2, native_tilde_string, prefix='Arglist   '))
	commands = field(default='', type=str, native=NativeField(3, native_tilde_string, prefix='Comlist   ', when=lambda owner: bool(owner.commands)))
	unknown = field(default=Factory(list), type=List[SwrUnknown], native=NativeField(4, native_records, suffix=''))


@attributes
class SwrExtraDescription(object):
	NATIVE_PREFIX = '#EXDESC\n'
	NATIVE_SUFFIX = '#ENDEXDESC\n\n'

	keyword = field(default='', type=str, native=NativeField(1, native_tilde_string, prefix='ExDescKey '))
	description = field(default='', type=str, native=NativeField(2, native_tilde_string, prefix='ExDesc    ', when=lambda owner: bool(owner.description)))
	unknown = field(default=Factory(list), type=List[SwrUnknown], native=NativeField(3, native_records, suffix=''))


@attributes
class SwrExit(object):
	NATIVE_PREFIX = '#EXIT\n'
	NATIVE_SUFFIX = '#ENDEXIT\n\n'

	door = field(default='', type=str, native=NativeField(1, native_tilde_string, prefix='Direction '))
	destination = field(default=0, type=int, native=NativeField(2, native_number, prefix='ToRoom    '))
	key = field(default=0, type=int, native=NativeField(3, native_number, prefix='Key       ', when=lambda owner: owner.key > 0))
	distance = field(default=0, type=int, native=NativeField(4, native_number, prefix='Distance  ', when=lambda owner: owner.distance != 0))
	description = field(default='', type=str, native=NativeField(5, native_tilde_string, prefix='Desc      ', when=lambda owner: bool(owner.description)))
	keyword = field(default='', type=str, native=NativeField(6, native_tilde_string, prefix='Keywords  ', when=lambda owner: bool(owner.keyword)))
	flags = field(default='', type=str, native=NativeField(7, native_tilde_string, prefix='Flags     ', when=lambda owner: bool(owner.flags)))
	unknown = field(default=Factory(list), type=List[SwrUnknown], native=NativeField(8, native_records, suffix=''))


@attributes
class SwrReset(object):
	NATIVE_PREFIX = 'Reset '

	command = field(default='', type=Letter, native=NativeField(1, native_word, suffix=' '))
	if_flag = field(default=0, type=int, native=NativeField(2, native_number, suffix=' '))
	arg1 = field(default=0, type=int, native=NativeField(3, native_number, suffix=' '))
	arg2 = field(default=0, type=int, native=NativeField(4, native_number, suffix=native_swr_reset_arg2_suffix))
	arg3 = field(default=0, type=int, native=NativeField(5, native_number, suffix='', when=lambda owner: owner.command not in ('G', 'R')))
	comment = field(default='', type=str, native=NativeField(6, native_comment))

	@classmethod
	def read(cls, reader, letter):
		if_flag = reader.read_number()
		arg1 = reader.read_number()
		arg2 = reader.read_number()
		arg3 = 0 if letter in ('G', 'R') else reader.read_number()
		return cls(command=letter, if_flag=if_flag, arg1=arg1, arg2=arg2, arg3=arg3, comment=reader.read_to_eol())


@attributes
class SwrMobile(RomCharacter):
	NATIVE_PREFIX = '#MOBILE\n'
	NATIVE_SUFFIX = '#ENDMOBILE\n\n'

	vnum = field(default=0, type=VNum, read=False, native=NativeField(1, native_number, prefix='Vnum       '))
	name = field(default='', type=str, native=NativeField(2, native_tilde_string, prefix='Keywords   '))
	short_desc = field(default='', type=str, native=NativeField(3, native_tilde_string, prefix='Short      '))
	long_desc = field(default='', type=str, native=NativeField(4, native_tilde_string, prefix='Long       ', when=lambda owner: bool(owner.long_desc)))
	description = field(default='', type=str, native=NativeField(5, native_tilde_string, prefix='Desc       ', when=lambda owner: bool(owner.description)))
	race = field(default='', type=str, native=NativeField(6, native_tilde_string, prefix='Race       '))
	position = field(default='', type=str, native=NativeField(7, native_tilde_string, prefix='Position   '))
	default_position = field(default='', type=str, native=NativeField(8, native_tilde_string, prefix='DefPos     '))
	specfun = field(default='', type=str, native=NativeField(9, native_tilde_string, prefix='Specfun    ', when=lambda owner: bool(owner.specfun)))
	specfun2 = field(default='', type=str, native=NativeField(10, native_tilde_string, prefix='Specfun2   ', when=lambda owner: bool(owner.specfun2)))
	gender = field(default='', type=str, native=NativeField(11, native_tilde_string, prefix='Gender     '))
	actflags = field(default='', type=str, native=NativeField(12, native_tilde_string, prefix='Actflags   '))
	affected = field(default='', type=str, native=NativeField(13, native_tilde_string, prefix='Affected   ', when=lambda owner: bool(owner.affected)))
	stats1 = attr(default=Factory(list), type=list, eq=False)
	stats2 = attr(default=Factory(list), type=list, eq=False)
	stats3 = attr(default=Factory(list), type=list, eq=False)
	stats4 = attr(default=Factory(list), type=list, eq=False)
	alignment = field(default=0, type=int, native=NativeField(14, native_number, prefix='Stats1     ', suffix=' '))
	level = field(default=0, type=int, native=NativeField(15, native_number, suffix=' '))
	thac0 = field(default=0, type=int, native=NativeField(16, native_number, suffix=' '))
	ac = field(default=Factory(RomArmorClass), type=RomArmorClass, native=NativeField(17, native_swr_armor_class, suffix=' '))
	wealth = field(default=0, type=int, native=NativeField(18, native_number, suffix=' '))
	experience = field(default=0, type=int, native=NativeField(19, native_number))
	hit = field(default=Factory(Dice), type=Dice, native=NativeField(20, native_swr_dice, prefix='Stats2     '))
	damage = field(default=Factory(Dice), type=Dice, native=NativeField(21, native_swr_dice, prefix='Stats3     '))
	height = field(default=0, type=int, native=NativeField(22, native_number, prefix='Stats4     ', suffix=' '))
	weight = field(default=0, type=int, native=NativeField(23, native_number, suffix=' '))
	numattacks = field(default=0, type=int, native=NativeField(24, native_number, suffix=' '))
	hitroll = field(default=0, type=int, native=NativeField(25, native_number, suffix=' '))
	damroll = field(default=0, type=int, native=NativeField(26, native_number))
	attribs = field(default=Factory(list), type=list, native=NativeField(27, native_numbers, prefix='Attribs    ', when=lambda owner: bool(owner.attribs)))
	saves = field(default=Factory(list), type=list, native=NativeField(28, native_numbers, prefix='Saves      ', when=lambda owner: bool(owner.saves)))
	speaks = field(default='', type=str, native=NativeField(29, native_tilde_string, prefix='Speaks     ', when=lambda owner: bool(owner.speaks)))
	speaking = field(default='', type=str, native=NativeField(30, native_tilde_string, prefix='Speaking   ', when=lambda owner: bool(owner.speaking)))
	bodyparts = field(default='', type=str, native=NativeField(31, native_tilde_string, prefix='Bodyparts  ', when=lambda owner: bool(owner.bodyparts)))
	resist = field(default='', type=str, native=NativeField(32, native_tilde_string, prefix='Resist     ', when=lambda owner: bool(owner.resist)))
	immune = field(default='', type=str, native=NativeField(33, native_tilde_string, prefix='Immune     ', when=lambda owner: bool(owner.immune)))
	suscept = field(default='', type=str, native=NativeField(34, native_tilde_string, prefix='Suscept    ', when=lambda owner: bool(owner.suscept)))
	attacks = field(default='', type=str, native=NativeField(35, native_tilde_string, prefix='Attacks    ', when=lambda owner: bool(owner.attacks)))
	defenses = field(default='', type=str, native=NativeField(36, native_tilde_string, prefix='Defenses   ', when=lambda owner: bool(owner.defenses)))
	vip_flags = field(default='', type=str, native=NativeField(37, native_tilde_string, prefix='VIPFlags   ', when=lambda owner: bool(owner.vip_flags)))
	shop_data = field(default=Factory(list), type=list, native=NativeField(38, native_numbers, prefix='ShopData   ', when=lambda owner: bool(owner.shop_data)))
	repair_data = field(default=Factory(list), type=list, native=NativeField(39, native_numbers, prefix='RepairData ', when=lambda owner: bool(owner.repair_data)))
	programs = field(default=Factory(list), type=List[SwrProgram], native=NativeField(40, native_records, suffix=''))
	unknown = field(default=Factory(list), type=List[SwrUnknown], native=NativeField(41, native_records, suffix=''))
	start_pos = attr(default='', type=str)
	default_pos = attr(default='', type=str)
	sex = attr(default='', type=str)


@attributes
class SwrObject(Item):
	NATIVE_PREFIX = '#OBJECT\n'
	NATIVE_SUFFIX = '#ENDOBJECT\n\n'

	vnum = field(default=0, type=VNum, read=False, native=NativeField(1, native_number, prefix='Vnum     '))
	name = field(default='', type=str, native=NativeField(2, native_tilde_string, prefix='Keywords '))
	type_name = field(default='', type=str, native=NativeField(3, native_tilde_string, prefix='Type     ', when=lambda owner: bool(owner.type_name)))
	short_desc = field(default='', type=str, native=NativeField(4, native_tilde_string, prefix='Short    '))
	description = field(default='', type=str, native=NativeField(5, native_tilde_string, prefix='Long     ', when=lambda owner: bool(owner.description)))
	action_description = field(default='', type=str, native=NativeField(6, native_tilde_string, prefix='Action   ', when=lambda owner: bool(owner.action_description)))
	flags = field(default='', type=str, native=NativeField(7, native_tilde_string, prefix='Flags    ', when=lambda owner: bool(owner.flags)))
	wflags = field(default='', type=str, native=NativeField(8, native_tilde_string, prefix='WFlags   ', when=lambda owner: bool(owner.wflags)))
	value = field(default=Factory(list), type=List, native=NativeField(9, native_numbers, prefix='Values   '))
	stats = attr(default=Factory(list), type=list, eq=False)
	weight = field(default=0, type=int, native=NativeField(10, native_number, prefix='Stats    ', suffix=' '))
	cost = field(default=0, type=int, native=NativeField(11, native_number, suffix=' '))
	rent = field(default=0, type=int, native=NativeField(12, native_number, suffix=' '))
	level = field(default=0, type=int, native=NativeField(13, native_number, suffix=' '))
	layers = field(default=0, type=int, native=NativeField(14, native_number))
	spells = field(default='', type=str, native=NativeField(15, native_raw, prefix='Spells   ', when=lambda owner: bool(owner.spells)))
	extra_descriptions = field(default=Factory(list), type=List[SwrExtraDescription], native=NativeField(16, native_records, suffix=''))
	programs = field(default=Factory(list), type=List[SwrProgram], native=NativeField(17, native_records, suffix=''))
	unknown = field(default=Factory(list), type=List[SwrUnknown], native=NativeField(18, native_records, suffix=''))


@attributes
class SwrRoom(MudBase):
	NATIVE_PREFIX = '#ROOM\n'
	NATIVE_SUFFIX = '#ENDROOM\n\n'

	vnum = field(default=0, type=VNum, read=False, native=NativeField(1, native_number, prefix='Vnum     '))
	name = field(default='', type=str, native=NativeField(2, native_tilde_string, prefix='Name     '))
	sector = field(default='', type=str, native=NativeField(3, native_tilde_string, prefix='Sector   '))
	flags = field(default='', type=str, native=NativeField(4, native_tilde_string, prefix='Flags    ', when=lambda owner: bool(owner.flags)))
	stats = attr(default=Factory(list), type=list, eq=False)
	tele_delay = field(default=0, type=int, native=NativeField(5, native_number, prefix='Stats    ', suffix=' ', when=lambda owner: any((owner.tele_delay, owner.tele_vnum, owner.tunnel))))
	tele_vnum = field(default=0, type=int, native=NativeField(6, native_number, suffix=' ', when=lambda owner: any((owner.tele_delay, owner.tele_vnum, owner.tunnel))))
	tunnel = field(default=0, type=int, native=NativeField(7, native_number, when=lambda owner: any((owner.tele_delay, owner.tele_vnum, owner.tunnel))))
	description = field(default='', type=str, native=NativeField(8, native_tilde_string, prefix='Desc     ', when=lambda owner: bool(owner.description)))
	exits = field(default=Factory(list), type=List[SwrExit], native=NativeField(9, native_records, suffix=''))
	resets = field(default=Factory(list), type=List[SwrReset], native=NativeField(10, native_records, suffix=''))
	extra_descriptions = field(default=Factory(list), type=List[SwrExtraDescription], native=NativeField(11, native_records, suffix=''))
	programs = field(default=Factory(list), type=List[SwrProgram], native=NativeField(12, native_records, suffix=''))
	unknown = field(default=Factory(list), type=List[SwrUnknown], native=NativeField(13, native_records, suffix=''))


@attributes
class SwrArea(SmaugArea):
	NATIVE_END = '#ENDAREA\n'
	NATIVE_SECTIONS = (
		NativeSection('FUSSAREA', owner_section='fuss_header'),
		NativeSection('AREADATA', owner_section='area', end='#ENDAREADATA\n\n'),
		NativeSection('MOBILE', collection='mobs', mapping=True, emit_header=False),
		NativeSection('OBJECT', collection='objects', mapping=True, emit_header=False),
		NativeSection('ROOM', collection='rooms', mapping=True, emit_header=False),
	)

	version = field(default=0, type=int, native=NativeField(1, native_number, prefix='Version    ', section='area'))
	name = field(default='', type=str, native=NativeField(2, native_tilde_string, prefix='Name       ', section='area'))
	author = field(default='', type=str, native=NativeField(3, native_tilde_string, prefix='Author     ', section='area'))
	low_soft_range = field(default=0, type=int, native=NativeField(4, native_number, prefix='Ranges     ', suffix=' ', section='area'))
	high_soft_range = field(default=0, type=int, native=NativeField(5, native_number, suffix=' ', section='area'))
	low_hard_range = field(default=0, type=int, native=NativeField(6, native_number, suffix=' ', section='area'))
	high_hard_range = field(default=0, type=int, native=NativeField(7, native_number, section='area'))
	high_economy = field(default=0, type=int, native=NativeField(8, native_number, prefix='Economy    ', suffix=' ', section='area'))
	low_economy = field(default=0, type=int, native=NativeField(9, native_number, section='area'))
	resetmsg = field(default='', type=str, native=NativeField(10, native_tilde_string, prefix='ResetMsg   ', section='area', when=lambda owner: bool(owner.resetmsg)))
	reset_frequency = field(default=0, type=int, native=NativeField(11, native_number, prefix='ResetFreq  ', section='area', when=lambda owner: owner.reset_frequency != 0))
	flags = field(default='', native=NativeField(12, native_tilde_string, prefix='Flags      ', section='area', when=lambda owner: bool(owner.flags)))
	unknown = field(default=Factory(list), type=List[SwrUnknown], native=NativeField(13, native_records, section='area', suffix=''))
	mobs = attr(default=Factory(OrderedDict), type=Dict[int, SwrMobile])
	objects = attr(default=Factory(OrderedDict), type=Dict[int, SwrObject])
	rooms = attr(default=Factory(OrderedDict), type=Dict[int, SwrRoom])


def native_merc_reset_arg2_suffix(owner):
	return '' if owner.command in ('G', 'R') else ' '


@attributes
class MercReset(object):
	command = field(default=None, native=NativeField(1, native_reset_command, suffix=native_reset_command_suffix))
	if_flag = field(
		default=0,
		native=NativeField(2, native_number, suffix=' ', when=lambda owner: owner.command is not None),
	)
	arg1 = field(
		default=None,
		native=NativeField(3, native_number, suffix=' ', when=lambda owner: owner.command is not None),
	)
	arg2 = field(
		default=None,
		native=NativeField(4, native_number, suffix=native_merc_reset_arg2_suffix, when=lambda owner: owner.command is not None),
	)
	arg3 = field(
		default=None,
		native=NativeField(5, native_number, suffix='', when=lambda owner: owner.command not in (None, 'G', 'R')),
	)
	arg4 = attr(default=None)
	arg5 = attr(default=None)
	comment = field(default=None, native=NativeField(6, native_comment))

	@classmethod
	def read(cls, reader, letter):
		command = letter
		if_flag = reader.read_number()
		arg1 = reader.read_number()
		arg2 = reader.read_number()
		if letter == 'G' or letter == 'R':
			arg3 = 0
		else:
			arg3 = reader.read_number()
		comment = reader.read_to_eol()
		return cls(command=command, if_flag=if_flag, arg1=arg1, arg2=arg2, arg3=arg3, comment=comment)

@attributes
class MercMob(RomMob):
	vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(1, native_tilde_string))
	short_desc = field(default='', type=str, native=NativeField(2, native_tilde_string))
	long_desc = field(default='', type=str, native=NativeField(3, native_tilde_string))
	description = field(default='', type=str, native=NativeField(4, native_tilde_string))
	extra_descriptions = attr(default=Factory(list), type=List[ExtraDescription])
	race = attr(default='', type=str)
	group = attr(default=0, type=int)
	act = field(
		default=MERC_ACT_TYPES.IS_NPC.value,
		type=MERC_ACT_TYPES,
		converter=MERC_ACT_TYPES,
		native=NativeField(5, native_flag),
	)
	affected_by = field(default=0, type=AFFECTED_BY, converter=AFFECTED_BY, native=NativeField(6, native_flag))
	alignment = field(default=0, type=int, native=NativeField(7, native_number))
	level = field(default=0, type=int, native=NativeField(8, native_number, prefix='S\n'))
	hitroll = field(default=0, type=int, native=NativeField(9, native_number))
	ac = field(default=0, type=int, native=NativeField(10, native_number))
	hit = field(default=Factory(Dice), type=Dice, native=NativeField(11, native_nested))
	damage = field(default=Factory(Dice), type=Dice, native=NativeField(12, native_nested))
	mana = attr(default=Factory(Dice), type=Dice)
	damtype = attr(default='', type=Word)
	material = attr(default='', type=str)
	wealth = field(default=0, type=int, native=NativeField(13, native_number))
	xp = field(default=0, type=int, native=NativeField(14, native_number))
	default_pos = field(default=0, type=int, native=NativeField(15, native_number))
	start_pos = field(default=0, type=int, native=NativeField(16, native_number))
	sex = field(default=0, type=int, native=NativeField(17, native_number))
	off_flags = attr(default=0, type=OFFENSE, converter=OFFENSE)
	imm_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	res_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	vuln_flags = attr(default=0, type=IMM_FLAGS, converter=IMM_FLAGS)
	form = attr(default=0, type=FORMS, converter=FORMS)
	parts = attr(default=0, type=PARTS, converter=PARTS)
	size = attr(default=None, type=Word)
	mprogs = field(default=Factory(list), type=Optional[List[RomMobprog]])

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
		xp = reader.read_number()
		default_pos = reader.read_number() # position
		start_pos = reader.read_number() # start pos
		sex = reader.read_number()
		if letter != 'S':
			reader.parse_fail("Reading MOB vnum %d non S: %s" % (vnum, letter))
		return cls(vnum=vnum, name=name, short_desc=short_desc, long_desc=long_desc, description=description, act=act, affected_by=affected_by, alignment=alignment, level=level, hitroll=hitroll, ac=ac, hit=hit, damage=damage, wealth=wealth, xp=xp, start_pos=start_pos, default_pos=default_pos, sex=sex)

@attributes
class MercItem(Item):
	vnum = field(default=0, type=VNum, read=False, native=NativeField(0, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(1, native_tilde_string))
	short_desc = field(default='', type=str, native=NativeField(2, native_tilde_string))
	description = field(default='', type=str, native=NativeField(3, native_tilde_string))
	action_description = field(default='', type=str, native=NativeField(4, native_tilde_string))
	item_type = field(default=-1, type=int, native=NativeField(5, native_number))
	extra_flags = field(default=0, type=int, native=NativeField(6, native_number))
	wear_flags = field(default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS, native=NativeField(7, native_number))
	value = field(default=Factory(list), type=List, native=NativeField(8, native_four_numbers))
	weight = field(default=0, type=int, native=NativeField(9, native_number))
	cost = field(default=0, type=int, native=NativeField(10, native_number))
	cost_per_day = field(default=0, type=int, native=NativeField(11, native_number))
	level = attr(default=0, type=int)
	affected = field(default=Factory(list), native=NativeField(12, native_records, suffix=''))
	extra_descriptions = field(default=Factory(list), type=List[ExtraDescription], native=NativeField(13, native_records, suffix=''))

	@classmethod
	def read(cls, reader, vnum):
		logger.debug("Reading object %d" % vnum)
		name = reader.read_string()
		short_desc = reader.read_string()
		description = reader.read_string()
		action_description = reader.read_string()
		item_type = reader.read_number()
		extra_flags = reader.read_flag()
		wear_flags = reader.read_flag()
		value = [reader.read_number(), reader.read_number(), reader.read_number(), reader.read_number()]
		weight = reader.read_number()
		cost = reader.read_number()
		cost_per_day = reader.read_number()
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
		return cls(vnum=vnum, name=name, short_desc=short_desc, description=description, action_description=action_description, item_type=item_type, extra_flags=extra_flags, wear_flags=wear_flags, value=value, weight=weight, cost=cost, cost_per_day=cost_per_day, affected=affected, extra_descriptions=extra_descriptions)

class MercAreaFile(AreaFile):
	area_type = MercArea

	def dumps(self):
		return render_document(self.area, self.area.NATIVE_SECTIONS, self.skipped_sections)

	def write(self, path):
		with io.open(path, mode='wt', encoding='latin-1', newline='\n') as area_file:
			area_file.write(self.dumps())

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
	MAX_FIX = 3

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
			'continent': self.load_continent,
			'climate': self.load_climate,
			'spelllimit': self.load_spelllimit,
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
				except ParseError:
					raise
				except Exception as error:
					self.parse_fail("Error reading section %r: %r" % (section_name, error))

	def read_area_metadata(self):
		self.area.name = self.read_string()

	def load_author(self):
		self.area.author = self.read_string()

	def load_credits(self):
		self.area.credits = self.read_string()

	def load_flags(self):
		self.area.flags = self.read_number()
		line = self.read_to_eol().strip()
		self.area.reset_frequency = int(line.split()[0]) if line else 0

	def load_ranges(self):
		self.area.low_soft_range = self.read_number()
		self.area.high_soft_range = self.read_number()
		self.area.low_hard_range = self.read_number()
		self.area.high_hard_range = self.read_number()
		self.read_word() # $

	def load_version(self):
		self.area.version = self.read_number()

	def load_continent(self):
		self.area.continent = self.read_string()

	def load_climate(self):
		self.area.climate = self.read_number_line()

	def load_spelllimit(self):
		self.area.spelllimit = self.read_number()

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
			next_char = self.data[self.index + 1:self.index + 2]
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
			fix_type = [self.read_number() for _ in range(self.MAX_FIX)]
			profit_fix = self.read_number()
			shop_type = self.read_number()
			open_hour = self.read_number()
			close_hour = self.read_number()
			comment = self.read_to_eol()
			self.area.repairs.append(SmaugRepair(keeper=keeper, fix_type=fix_type, profit_fix=profit_fix, shop_type=shop_type, open_hour=open_hour, close_hour=close_hour, comment=comment))

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
	area_type = SwrArea

	def __init__(self, filename):
		super().__init__(filename)
		if not self.data.lstrip().startswith('#FUSSAREA'):
			self.area = SmaugArea()

	def dumps(self):
		return render_document(self.area, self.area.NATIVE_SECTIONS, self.skipped_sections)

	def write(self, path):
		with io.open(path, mode='wt', encoding='latin-1', newline='\n') as area_file:
			area_file.write(self.dumps())

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
			next_char = self.data[self.index + 1:self.index + 2]
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

	def read_fuss_unknown(self, key):
		line_end = self.data.find('\n', self.index)
		if line_end == -1:
			line_end = len(self.data)
		if '~' in self.data[self.index:line_end]:
			return SwrUnknown(key=key, value=self.read_string(), tilde=True)
		return SwrUnknown(key=key, value=self.read_to_eol().strip(), tilde=False)

	def skip_fuss_value(self):
		return self.read_fuss_unknown('')

	def read_fuss_numbers(self):
		return [int(value) for value in self.read_to_eol().split()]

	def read_fuss_program(self):
		program = SwrProgram()
		while True:
			word = self.read_word()
			if word == '#ENDPROG':
				return program
			if word == 'Progtype':
				program.progtype = self.read_string()
			elif word == 'Arglist':
				program.argument = self.read_string()
			elif word == 'Comlist':
				program.commands = self.read_string()
			else:
				program.unknown.append(self.read_fuss_unknown(word))

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
				self.area.flags = self.read_string()
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
				self.area.reset_frequency = self.read_number()
			elif word == "Version":
				self.area.version = self.read_number()
			else:
				self.area.unknown.append(self.read_fuss_unknown(word))

	def read_fuss_mobile(self):
		mob = SwrMobile()
		while True:
			word = self.read_word()
			if word == "#ENDMOBILE":
				break
			if word == "#MUDPROG":
				mob.programs.append(self.read_fuss_program())
			elif word == "Vnum":
				mob.vnum = self.read_number()
			elif word == "Keywords":
				mob.name = self.read_string()
			elif word == "Short":
				mob.short_desc = self.read_string()
			elif word == "Long":
				mob.long_desc = self.read_string()
			elif word == "Desc":
				mob.description = self.read_string()
			elif word == "Race":
				mob.race = self.read_string()
			elif word == "Position":
				mob.position = self.read_string()
			elif word == "DefPos":
				mob.default_position = self.read_string()
			elif word == "Gender":
				mob.gender = self.read_string()
			elif word == "Stats1":
				mob.stats1 = self.read_fuss_numbers()
			elif word == "Stats2":
				mob.stats2 = self.read_fuss_numbers()
			elif word == "Stats3":
				mob.stats3 = self.read_fuss_numbers()
			elif word == "Stats4":
				mob.stats4 = self.read_fuss_numbers()
			elif word == 'Attribs':
				mob.attribs = self.read_fuss_numbers()
			elif word == 'Saves':
				mob.saves = self.read_fuss_numbers()
			elif word == 'ShopData':
				mob.shop_data = self.read_fuss_numbers()
			elif word == 'RepairData':
				mob.repair_data = self.read_fuss_numbers()
			elif word in ('Specfun', 'Specfun2', 'Actflags', 'Affected', 'Speaks', 'Speaking', 'Bodyparts', 'Resist', 'Immune', 'Suscept', 'Attacks', 'Defenses', 'VIPFlags'):
				attribute = {
					'Specfun': 'specfun',
					'Specfun2': 'specfun2',
					'Actflags': 'actflags',
					'Affected': 'affected',
					'Speaks': 'speaks',
					'Speaking': 'speaking',
					'Bodyparts': 'bodyparts',
					'Resist': 'resist',
					'Immune': 'immune',
					'Suscept': 'suscept',
					'Attacks': 'attacks',
					'Defenses': 'defenses',
					'VIPFlags': 'vip_flags',
				}[word]
				setattr(mob, attribute, self.read_string())
			else:
				mob.unknown.append(self.read_fuss_unknown(word))
		stats1 = list(mob.stats1)
		stats2 = list(mob.stats2)
		stats3 = list(mob.stats3)
		stats4 = list(mob.stats4)
		while len(stats1) < 6:
			stats1.append(0)
		while len(stats2) < 3:
			stats2.append(0)
		while len(stats3) < 3:
			stats3.append(0)
		while len(stats4) < 5:
			stats4.append(0)
		mob.alignment = stats1[0]
		mob.level = stats1[1]
		mob.thac0 = stats1[2]
		mob.ac = RomArmorClass(pierce=stats1[3], bash=stats1[3], slash=stats1[3], exotic=stats1[3])
		mob.wealth = stats1[4]
		mob.experience = stats1[5]
		mob.hit = Dice(number=stats2[0], sides=stats2[1], bonus=stats2[2])
		mob.damage = Dice(number=stats3[0], sides=stats3[1], bonus=stats3[2])
		mob.height = stats4[0]
		mob.weight = stats4[1]
		mob.numattacks = stats4[2]
		mob.hitroll = stats4[3]
		mob.damroll = stats4[4]
		mob.start_pos = mob.position
		mob.default_pos = mob.default_position
		mob.sex = mob.gender
		return mob

	def read_fuss_object(self):
		item = SwrObject()
		while True:
			word = self.read_word()
			if word == "#ENDOBJECT":
				break
			if word == "#EXDESC":
				item.extra_descriptions.append(self.read_fuss_extra_description())
			elif word == "#MUDPROG":
				item.programs.append(self.read_fuss_program())
			elif word == "Vnum":
				item.vnum = self.read_number()
			elif word == "Keywords":
				item.name = self.read_string()
			elif word == "Short":
				item.short_desc = self.read_string()
			elif word == "Long":
				item.description = self.read_string()
			elif word == 'Type':
				item.type_name = self.read_string()
			elif word == 'Action':
				item.action_description = self.read_string()
			elif word == 'Flags':
				item.flags = self.read_string()
			elif word == 'WFlags':
				item.wflags = self.read_string()
			elif word == "Values":
				item.value = self.read_fuss_numbers()
			elif word == "Stats":
				item.stats = self.read_fuss_numbers()
			elif word == 'Spells':
				item.spells = self.read_to_eol().strip()
			else:
				item.unknown.append(self.read_fuss_unknown(word))
		if len(item.stats) > 0:
			item.weight = item.stats[0]
		if len(item.stats) > 1:
			item.cost = item.stats[1]
		if len(item.stats) > 2:
			item.rent = item.stats[2]
		if len(item.stats) > 3:
			item.level = item.stats[3]
		if len(item.stats) > 4:
			item.layers = item.stats[4]
		return item

	def read_fuss_room(self):
		room = SwrRoom()
		while True:
			word = self.read_word()
			if word == "#ENDROOM":
				break
			if word == "#EXIT":
				room.exits.append(self.read_fuss_exit())
			elif word == "#EXDESC":
				room.extra_descriptions.append(self.read_fuss_extra_description())
			elif word == "#MUDPROG":
				room.programs.append(self.read_fuss_program())
			elif word == "Vnum":
				room.vnum = self.read_number()
			elif word == "Name":
				room.name = self.read_string()
			elif word == "Desc":
				room.description = self.read_string()
			elif word == "Sector":
				room.sector = self.read_string()
			elif word == "Stats":
				room.stats = self.read_fuss_numbers()
			elif word == "Reset":
				letter = self.read_letter()
				room.resets.append(SwrReset.read(reader=self, letter=letter))
			elif word == "Flags":
				room.flags = self.read_string()
			else:
				room.unknown.append(self.read_fuss_unknown(word))
		if len(room.stats) > 0:
			room.tele_delay = room.stats[0]
		if len(room.stats) > 1:
			room.tele_vnum = room.stats[1]
		if len(room.stats) > 2:
			room.tunnel = room.stats[2]
		return room

	def read_fuss_exit(self):
		exit = SwrExit()
		while True:
			word = self.read_word()
			if word == "#ENDEXIT":
				return exit
			if word == "Desc":
				exit.description = self.read_string()
			elif word == "Direction":
				exit.door = self.read_string()
			elif word == "Distance":
				exit.distance = self.read_number()
			elif word == "Key":
				exit.key = self.read_number()
			elif word == "Keywords":
				exit.keyword = self.read_string()
			elif word == "ToRoom":
				exit.destination = self.read_number()
			elif word == "Flags":
				exit.flags = self.read_string()
			else:
				exit.unknown.append(self.read_fuss_unknown(word))

	def read_fuss_extra_description(self):
		extra = SwrExtraDescription()
		while True:
			word = self.read_word()
			if word == "#ENDEXDESC":
				return extra
			if word == "ExDescKey":
				extra.keyword = self.read_string()
			elif word == "ExDesc":
				extra.description = self.read_string()
			else:
				extra.unknown.append(self.read_fuss_unknown(word))

	def skip_fuss_program(self):
		self.read_fuss_program()


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


def native_circle_numbers(value, owner):
	del owner
	if (
		not isinstance(value, (list, tuple))
		or len(value) != 4
		or not all(isinstance(item, int) for item in value)
	):
		raise NativeWriteError("Circle object values require exactly four integers")
	return ' '.join(str(item) for item in value)


def native_circle_number_lines(value, owner):
	del owner
	if not isinstance(value, (list, tuple)) or not all(isinstance(item, int) for item in value):
		raise NativeWriteError("Expected a sequence of integers")
	return ''.join('%d\n' % item for item in value)


def native_circle_text_lines(value, owner):
	del owner
	if not isinstance(value, (list, tuple)):
		raise NativeWriteError("Expected a sequence of lines")
	lines = []
	for item in value:
		text = str(item)
		if '\n' in text or '\r' in text:
			raise NativeWriteError("A native line cannot contain a newline")
		lines.append(text + '\n')
	return ''.join(lines)


def native_circle_messages(value, owner):
	del owner
	if len(value) != 7:
		raise NativeWriteError("Circle shops require exactly seven messages")
	return ''.join(native_tilde_string(message, None) + '\n' for message in value)


def native_circle_dice(value, owner):
	del owner
	if not isinstance(value, Dice):
		raise NativeWriteError("Expected Circle dice")
	return '%dd%d%+d' % (value.number, value.sides, value.bonus)


def native_circle_hitroll(value, owner):
	del owner
	if not isinstance(value, int):
		raise NativeWriteError("Expected an integer hitroll")
	return str(20 - value)


def native_circle_armor_class(value, owner):
	del owner
	if not isinstance(value, int):
		raise NativeWriteError("Expected an integer armor class")
	if value % 10:
		raise NativeWriteError("Armor class %r is not divisible by ten" % value)
	return str(value // 10)


def native_circle_exit_lock(value, owner):
	del owner
	locks = {
		int(EXIT_FLAGS.NONE): 0,
		int(EXIT_FLAGS.ISDOOR): 1,
		int(EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF): 2,
	}
	try:
		return str(locks[int(value)])
	except (KeyError, TypeError, ValueError):
		raise NativeWriteError("Exit flags %r have no Circle lock code" % value)


def native_circle_mobile_type(value, owner):
	if value not in ('S', 'E'):
		raise NativeWriteError("Circle mobile type must be 'S' or 'E'")
	if value == 'S' and owner.especs:
		raise NativeWriteError("Simple Circle mobiles cannot contain especs")
	return value


def native_circle_especs(value, owner):
	del owner
	lines = []
	for key, item in value.items():
		if any(char in str(key) for char in ':\r\n') or any(char in str(item) for char in '\r\n'):
			raise NativeWriteError("Invalid Circle enhanced-mobile espec")
		lines.append('%s: %s\n' % (key, item))
	return ''.join(lines)


def native_circle_reset_command(value, owner):
	if value not in ('M', 'O', 'E', 'P', 'D', 'G', 'R'):
		raise NativeWriteError("unsupported Circle reset command %r" % value)
	if value in ('G', 'R') and owner.arg3 is not None:
		raise NativeWriteError("%s resets must omit arg3" % value)
	if value not in ('G', 'R') and owner.arg3 is None:
		raise NativeWriteError("%s resets requires arg3" % value)
	return value


def native_circle_float(value, owner):
	del owner
	if not isinstance(value, (int, float)) or isinstance(value, bool):
		raise NativeWriteError("Expected a number")
	return str(float(value))


def native_circle_mapping_records(value, owner):
	del owner
	return ''.join(render_record(record) for record in value.values())


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
	door = field(default=0, native=NativeField(1, native_number, prefix='D'))
	description = field(default='', native=NativeField(2, native_tilde_string))
	keyword = field(default='', native=NativeField(3, native_tilde_string))
	exit_info = field(default=EXIT_FLAGS.NONE, type=EXIT_FLAGS, converter=EXIT_FLAGS, native=NativeField(4, native_circle_exit_lock, suffix=' '))
	key = field(default=-1, native=NativeField(5, native_number, suffix=' '))
	destination = field(default=-1, native=NativeField(6, native_number))


@attributes
class CircleRoom(MudBase):
	NATIVE_SUFFIX = 'S\n'

	vnum = field(default=0, type=VNum, read=False, native=NativeField(1, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(2, native_tilde_string))
	description = field(default='', type=str, native=NativeField(3, native_tilde_string))
	zone_number = field(default=0, native=NativeField(4, native_number, suffix=' '))
	room_flags = field(default=0, native=NativeField(5, native_flag, suffix=' '))
	sector_type = field(default=0, native=NativeField(6, native_number))
	extra_descriptions = field(default=Factory(list), type=List[ExtraDescription], native=NativeField(7, native_records, suffix=''))
	exits = field(default=Factory(dict), native=NativeField(8, native_circle_mapping_records, suffix=''))
	source_file = attr(default='', type=str)


@attributes
class CircleMob(RomCharacter):
	vnum = field(default=0, type=VNum, read=False, native=NativeField(1, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(2, native_tilde_string))
	short_desc = field(default='', type=str, native=NativeField(3, native_tilde_string))
	long_desc = field(default='', type=str, native=NativeField(4, native_tilde_string))
	description = field(default='', type=str, native=NativeField(5, native_tilde_string))
	act = field(default=CircleMobFlags.ISNPC.value, type=CircleMobFlags, converter=CircleMobFlags, native=NativeField(6, native_flag, suffix=' '))
	affected_by = field(default=0, native=NativeField(7, native_flag, suffix=' '))
	alignment = field(default=0, native=NativeField(8, native_number, suffix=' '))
	mob_type = field(default='S', type=str, native=NativeField(9, native_circle_mobile_type))
	level = field(default=0, type=int, native=NativeField(10, native_number, suffix=' '))
	hitroll = field(default=0, type=int, native=NativeField(11, native_circle_hitroll, suffix=' '))
	ac = field(default=0, native=NativeField(12, native_circle_armor_class, suffix=' '))
	hit = field(default=Factory(Dice), type=Dice, native=NativeField(13, native_circle_dice, suffix=' '))
	damage = field(default=Factory(Dice), type=Dice, native=NativeField(14, native_circle_dice))
	wealth = field(default=0, native=NativeField(15, native_number, suffix=' '))
	exp = field(default=0, native=NativeField(16, native_number))
	default_pos = field(default=0, native=NativeField(17, native_number, suffix=' '))
	start_pos = field(default=0, native=NativeField(18, native_number, suffix=' '))
	sex = field(default=0, native=NativeField(19, native_number))
	especs = field(default=Factory(dict), native=NativeField(20, native_circle_especs, suffix='E\n', when=lambda owner: owner.mob_type == 'E'))
	source_file = attr(default='', type=str)


@attributes
class CircleAffectData(object):
	NATIVE_PREFIX = 'A\n'

	location = field(default=0, native=NativeField(1, native_number, suffix=' '))
	modifier = field(default=0, native=NativeField(2, native_number))


@attributes
class CircleItem(Item):
	vnum = field(default=0, type=VNum, read=False, native=NativeField(1, native_number, prefix='#'))
	name = field(default='', type=str, native=NativeField(2, native_tilde_string))
	short_desc = field(default='', type=str, native=NativeField(3, native_tilde_string))
	description = field(default='', type=str, native=NativeField(4, native_tilde_string))
	action_description = field(default='', native=NativeField(5, native_tilde_string))
	item_type = field(default=-1, type=int, native=NativeField(6, native_number, suffix=' '))
	extra_flags = field(default=0, type=int, native=NativeField(7, native_flag, suffix=' '))
	wear_flags = field(default=0, type=WEAR_FLAGS, converter=WEAR_FLAGS, native=NativeField(8, native_flag))
	value = field(default=Factory(list), type=List, native=NativeField(9, native_circle_numbers))
	weight = field(default=0, type=int, native=NativeField(10, native_number, suffix=' '))
	cost = field(default=0, type=int, native=NativeField(11, native_number, suffix=' '))
	rent = field(default=0, native=NativeField(12, native_number))
	extra_descriptions = field(default=Factory(list), type=List[ExtraDescription], native=NativeField(13, native_records, suffix=''))
	affected = field(default=Factory(list), native=NativeField(14, native_records, suffix=''))
	level = attr(default=0, type=int)
	source_file = attr(default='', type=str)


@attributes
class CircleReset(object):
	command = field(default='', native=NativeField(1, native_circle_reset_command, suffix=' '))
	if_flag = field(default=0, native=NativeField(2, native_number, suffix=' '))
	arg1 = field(default=0, native=NativeField(3, native_number, suffix=' '))
	arg2 = field(default=0, native=NativeField(4, native_number, suffix=lambda owner: '\n' if owner.command in ('G', 'R') else ' '))
	arg3 = field(default=None, native=NativeField(5, native_number, when=lambda owner: owner.command not in ('G', 'R')))


@attributes
class CircleZone(object):
	NATIVE_SUFFIX = 'S\n'

	vnum = field(default=0, native=NativeField(1, native_number, prefix='#'))
	name = field(default='', native=NativeField(2, native_tilde_string))
	bot = field(default=0, native=NativeField(3, native_number, suffix=' '))
	top = field(default=0, native=NativeField(4, native_number, suffix=' '))
	lifespan = field(default=0, native=NativeField(5, native_number, suffix=' '))
	reset_mode = field(default=0, native=NativeField(6, native_number))
	resets = field(default=Factory(list), native=NativeField(7, native_records, suffix=''))
	source_file = attr(default='', type=str)


@attributes
class CircleShop(object):
	vnum = field(default=0, native=NativeField(1, native_number, prefix='#', suffix='~\n'))
	products = field(default=Factory(list), native=NativeField(2, native_circle_number_lines, suffix='-1\n'))
	profit_buy = field(default=0.0, native=NativeField(3, native_circle_float))
	profit_sell = field(default=0.0, native=NativeField(4, native_circle_float))
	buy_type = field(default=Factory(list), native=NativeField(5, native_circle_text_lines, suffix='-1\n'))
	messages = field(default=Factory(list), native=NativeField(6, native_circle_messages, suffix=''))
	temper = field(default=0, native=NativeField(7, native_number))
	bitvector = field(default=0, native=NativeField(8, native_number))
	keeper = field(default=0, native=NativeField(9, native_number))
	with_who = field(default=0, native=NativeField(10, native_number))
	rooms = field(default=Factory(list), native=NativeField(11, native_circle_number_lines, suffix='-1\n'))
	open_hour = field(default=0, native=NativeField(12, native_number))
	close_hour = field(default=0, native=NativeField(13, native_number))
	open_hour_2 = field(default=0, native=NativeField(14, native_number))
	close_hour_2 = field(default=0, native=NativeField(15, native_number))
	source_file = attr(default='', type=str)


@attributes
class CircleArea(object):
	NATIVE_COLLECTIONS = (
		('zon', 'zones', '$\n'),
		('wld', 'rooms', '$\n'),
		('mob', 'mobs', '$\n'),
		('obj', 'objects', '$\n'),
		('shp', 'shops', '$~\n'),
	)

	zones = attr(default=Factory(OrderedDict))
	rooms = attr(default=Factory(OrderedDict))
	mobs = attr(default=Factory(OrderedDict))
	objects = attr(default=Factory(OrderedDict))
	shops = attr(default=Factory(OrderedDict))
	indexes = attr(default=Factory(OrderedDict))
	shop_headers = attr(default=Factory(OrderedDict))


class CircleAreaFile(object):
	NATIVE_NORMALIZATIONS = (
		'comments',
		'whitespace-and-line-endings',
		'numeric-versus-alphabetic-flags',
		'room-and-object-metadata-order',
		'optional-second-shop-window',
		'dice-zero-bonus-spelling',
	)

	def __init__(self, root):
		self.root = os.fspath(root)
		self.world_root = self.root
		if not os.path.exists(os.path.join(self.world_root, 'zon', 'index')):
			self.world_root = os.path.join(self.root, 'lib', 'world')
		self.area = CircleArea()
		self.filename = ''
		self.data = ''
		self.index = 0

	def dumps(self):
		tree = OrderedDict()
		for family, collection_name, file_end in self.area.NATIVE_COLLECTIONS:
			names = self.area.indexes.get(family, [])
			tree['%s/index' % family] = ''.join('%s\n' % name for name in names) + '$\n'
			records = getattr(self.area, collection_name).values()
			for record in records:
				if not record.source_file:
					raise NativeWriteError(
						'%s %r has no indexed source file' % (record.__class__.__name__, record.vnum)
					)
				if record.source_file not in names:
					raise NativeWriteError(
						'%s is not present in the %s index' % (record.source_file, family)
					)
			for name in names:
				prefix = ''
				if family == 'shp':
					try:
						prefix = native_tilde_string(self.area.shop_headers[name], None) + '\n'
					except KeyError:
						raise NativeWriteError('Shop file %s has no version header' % name)
				body = ''.join(
					render_record(record)
					for record in records
					if record.source_file == name
				)
				tree['%s/%s' % (family, name)] = prefix + body + file_end
		return tree

	def write(self, root):
		root = os.fspath(root)
		world_root = root if os.path.basename(root) == 'world' else os.path.join(root, 'lib', 'world')
		for relative_path, text in self.dumps().items():
			path = os.path.join(world_root, *relative_path.split('/'))
			os.makedirs(os.path.dirname(path), exist_ok=True)
			with io.open(path, mode='wt', encoding='latin-1', newline='\n') as circle_file:
				circle_file.write(text)

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
			self.area.indexes[family] = []
			return []
		base = os.path.dirname(index_path)
		with io.open(index_path, mode='rt', encoding='latin-1') as index_file:
			names = [line.strip() for line in index_file]
		names = [name for name in names if name and name != '$']
		self.area.indexes[family] = names
		return [os.path.join(base, name) for name in names]

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
		try:
			return int(token)
		except ValueError:
			self.parse_fail("Expected numeric record header, got %r" % token)

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
			zone = CircleZone(vnum=vnum, name=name, bot=bot, top=top, lifespan=lifespan, reset_mode=reset_mode, source_file=os.path.basename(path))
			while True:
				line = self.read_line().strip()
				if not line and self.current_char == '\0':
					self.parse_fail("premature end of file")
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
			room.source_file = os.path.basename(path)
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
			mob = self.read_mobile(vnum)
			mob.source_file = os.path.basename(path)
			self.area.mobs[vnum] = mob

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
			mob_type=mob_type.upper(),
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
			item = self.read_item(vnum)
			item.source_file = os.path.basename(path)
			self.area.objects[vnum] = item

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
		self.area.shop_headers[os.path.basename(path)] = header
		while True:
			vnum = self.read_record_header()
			if vnum is None:
				return
			shop = self.read_shop(vnum, header)
			shop.source_file = os.path.basename(path)
			self.area.shops[vnum] = shop

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
		return area_reader.serialization.EnumNameConverter().unstructure(self.area)

	def as_json(self, indent=None):
		return json.dumps(self.as_dict(), indent=indent)


def native_xml_text(value, owner):
	del owner
	return html.escape(str(value), quote=False)


def native_xml_number(value, owner):
	return native_xml_text(native_number(value, owner), owner)


def native_xml_float(value, owner):
	del owner
	if not isinstance(value, (int, float)) or isinstance(value, bool):
		raise NativeWriteError("Expected an XML number")
	return html.escape(str(float(value)), quote=False)


def native_coffee_residuals(value, owner):
	del owner
	chunks = []
	for fragment in value:
		try:
			element = ET.fromstring(fragment)
		except ET.ParseError as error:
			raise NativeWriteError("Malformed CoffeeMud residual XML") from error
		chunks.append(ET.tostring(element, encoding='unicode', short_empty_elements=True))
	return ''.join(chunks)


def native_coffee_payload(value, owner):
	del value
	return render_record(owner, section='inner')


def native_coffee_document(value):
	root = ET.fromstring(value)
	payload_tags = {'MTEXT', 'ITEXT', 'RTEXT', 'EXDAT'}

	def collapse_payloads(element):
		for child in element:
			if child.tag.upper() in payload_tags:
				inner = child.text or ''
				inner += ''.join(ET.tostring(part, encoding='unicode') for part in child)
				child.clear()
				child.text = inner
			else:
				collapse_payloads(child)

	collapse_payloads(root)
	return ET.tostring(root, encoding='unicode', short_empty_elements=True)


def native_coffee_records(value, owner):
	del owner
	return ''.join(render_record(record) for record in value)


def native_coffee_room_records(value, owner):
	del owner
	return ''.join(render_record(record) for record in value.values())


def native_coffee_behaviors(value, owner):
	del owner
	return '<BEHAVES>%s</BEHAVES>' % ''.join(render_record(record) for record in value)


def native_coffee_affects(value, owner):
	del owner
	return '<AFFECS>%s</AFFECS>' % ''.join(render_record(record) for record in value)


def native_coffee_factions(value, owner):
	del owner
	chunks = []
	for faction_id, amount in value.items():
		if not isinstance(amount, int):
			raise NativeWriteError("CoffeeMud faction values must be integers")
		chunks.append('<FCTN ID="%s">%d</FCTN>' % (html.escape(str(faction_id), quote=True), amount))
	return '<FACTIONS>%s</FACTIONS>' % ''.join(chunks)


def native_coffee_abilities(value, owner):
	del owner
	return '<ABLTYS>%s</ABLTYS>' % ''.join(render_record(record) for record in value)


def native_coffee_nested_area(value, owner):
	del owner
	return '<SSAREA>%s</SSAREA>' % render_record(value)


def native_coffee_exits(value, owner):
	del owner
	return '<ROOMEXITS>%s</ROOMEXITS>' % ''.join(render_record(record) for record in value)


def native_coffee_content(value, owner):
	del value
	mobs = ''.join(render_record(record) for record in owner.mobs)
	items = ''.join(render_record(record) for record in owner.items)
	return '<ROOMCONTENT><ROOMMOBS>%s</ROOMMOBS><ROOMITEMS>%s</ROOMITEMS></ROOMCONTENT>' % (mobs, items)


def native_coffee_exit_data(value, owner):
	del value
	inner = native_coffee_residuals(owner.inner_residual, owner)
	xexit_residual = native_coffee_residuals(owner.xexit_residual, owner)
	return '<XEXIT><EXID>%s</EXID><EXDAT>%s</EXDAT>%s</XEXIT>' % (
		html.escape(owner.class_id, quote=False),
		inner,
		xexit_residual,
	)


def native_coffee_area_data(value, owner):
	del value
	return '<ADATA>%s</ADATA>' % native_coffee_residuals(owner.inner_residual, owner)


def native_coffee_mob_prefix(owner):
	if owner.native_tag not in ('MOB', 'RMOB'):
		raise NativeWriteError("CoffeeMud mob tag must be MOB or RMOB")
	return '<%s>' % owner.native_tag


def native_coffee_mob_suffix(owner):
	return '</%s>' % owner.native_tag


def native_coffee_item_prefix(owner):
	if owner.native_tag == 'ITEM':
		return '<ITEM>'
	if owner.native_tag == 'RITEM':
		return '<RITEM COUNT="%d">' % owner.count
	else:
		raise NativeWriteError("CoffeeMud item tag must be ITEM or RITEM")


def native_coffee_item_suffix(owner):
	return '</%s>' % owner.native_tag


@attributes
class CoffeeMudBehavior(object):
	NATIVE_PREFIX = '<BHAVE>'
	NATIVE_SUFFIX = '</BHAVE>'

	class_id = field(default='', native=NativeField(1, native_xml_text, prefix='<BCLASS>', suffix='</BCLASS>'))
	parameters = field(default='', native=NativeField(2, native_xml_text, prefix='<BPARMS>', suffix='</BPARMS>'))
	residual = field(default=Factory(list), native=NativeField(3, native_coffee_residuals, suffix=''))


@attributes
class CoffeeMudAffect(object):
	NATIVE_PREFIX = '<AFF>'
	NATIVE_SUFFIX = '</AFF>'

	class_id = field(default='', native=NativeField(1, native_xml_text, prefix='<ACLASS>', suffix='</ACLASS>'))
	text = field(default='', native=NativeField(2, native_xml_text, prefix='<ATEXT>', suffix='</ATEXT>'))
	residual = field(default=Factory(list), native=NativeField(3, native_coffee_residuals, suffix=''))


@attributes
class CoffeeMudAbility(object):
	NATIVE_PREFIX = '<ABLTY>'
	NATIVE_SUFFIX = '</ABLTY>'

	class_id = field(default='', native=NativeField(1, native_xml_text, prefix='<ACLASS>', suffix='</ACLASS>'))
	proficiency = field(default=0, native=NativeField(2, native_xml_number, prefix='<APROF>', suffix='</APROF>'))
	data_xml = field(default='', native=NativeField(3, native_raw, prefix='<ADATA>', suffix='</ADATA>'))
	data = attr(default='', eq=False)
	residual = field(default=Factory(list), native=NativeField(4, native_coffee_residuals, suffix=''))


@attributes
class CoffeeMudMob(object):
	NATIVE_PREFIX = native_coffee_mob_prefix
	NATIVE_SUFFIX = native_coffee_mob_suffix

	class_id = field(default='', native=NativeField(1, native_xml_text, prefix='<MCLAS>', suffix='</MCLAS>'))
	level = field(default=0, native=NativeField(2, native_xml_number, prefix='<MLEVL>', suffix='</MLEVL>'))
	ability = field(default=0, native=NativeField(3, native_xml_number, prefix='<MABLE>', suffix='</MABLE>'))
	rejuv = field(default=0, native=NativeField(4, native_xml_number, prefix='<MREJV>', suffix='</MREJV>'))
	raw_text = field(default='', eq=False, native=NativeField(5, native_coffee_payload, prefix='<MTEXT>', suffix='</MTEXT>'))
	outer_residual = field(default=Factory(list), native=NativeField(6, native_coffee_residuals, suffix=''))
	name = field(default='', native=NativeField(1, native_xml_text, prefix='<NAME>', suffix='</NAME>', section='inner'))
	description = field(default='', native=NativeField(2, native_xml_text, prefix='<DESC>', suffix='</DESC>', section='inner'))
	display = field(default='', native=NativeField(3, native_xml_text, prefix='<DISP>', suffix='</DISP>', section='inner'))
	behaviors = field(default=Factory(list), native=NativeField(4, native_coffee_behaviors, section='inner'))
	affects = field(default=Factory(list), native=NativeField(5, native_coffee_affects, section='inner'))
	flag = field(default=0, native=NativeField(6, native_xml_number, prefix='<FLAG>', suffix='</FLAG>', section='inner'))
	money = field(default=0, native=NativeField(7, native_xml_number, prefix='<MONEY>', suffix='</MONEY>', section='inner'))
	variable_money = field(default=0.0, native=NativeField(8, native_xml_float, prefix='<VARMONEY>', suffix='</VARMONEY>', section='inner'))
	gender = field(default='', native=NativeField(9, native_xml_text, prefix='<GENDER>', suffix='</GENDER>', section='inner'))
	race = field(default='', native=NativeField(10, native_xml_text, prefix='<MRACE>', suffix='</MRACE>', section='inner'))
	factions = field(default=Factory(dict), native=NativeField(11, native_coffee_factions, section='inner'))
	abilities = field(default=Factory(list), native=NativeField(12, native_coffee_abilities, section='inner'))
	inner_residual = field(default=Factory(list), native=NativeField(13, native_coffee_residuals, section='inner', suffix=''))
	raw_data = attr(default=Factory(dict), eq=False)
	native_tag = attr(default='MOB', type=str)


@attributes
class CoffeeMudItem(object):
	NATIVE_PREFIX = native_coffee_item_prefix
	NATIVE_SUFFIX = native_coffee_item_suffix

	class_id = field(default='', native=NativeField(1, native_xml_text, prefix='<ICLAS>', suffix='</ICLAS>'))
	ident = field(default='', native=NativeField(2, native_xml_text, prefix='<IIDEN>', suffix='</IIDEN>'))
	location = field(default='', native=NativeField(3, native_xml_text, prefix='<ILOCA>', suffix='</ILOCA>'))
	uses = field(default=0, native=NativeField(4, native_xml_number, prefix='<IUSES>', suffix='</IUSES>'))
	level = field(default=0, native=NativeField(5, native_xml_number, prefix='<ILEVL>', suffix='</ILEVL>'))
	ability = field(default=0, native=NativeField(6, native_xml_number, prefix='<IABLE>', suffix='</IABLE>'))
	rejuv = field(default=0, native=NativeField(7, native_xml_number, prefix='<IREJV>', suffix='</IREJV>'))
	raw_text = field(default='', eq=False, native=NativeField(8, native_coffee_payload, prefix='<ITEXT>', suffix='</ITEXT>'))
	outer_residual = field(default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix=''))
	name = field(default='', native=NativeField(1, native_xml_text, prefix='<NAME>', suffix='</NAME>', section='inner'))
	description = field(default='', native=NativeField(2, native_xml_text, prefix='<DESC>', suffix='</DESC>', section='inner'))
	display = field(default='', native=NativeField(3, native_xml_text, prefix='<DISP>', suffix='</DISP>', section='inner'))
	prop = field(default='', native=NativeField(4, native_xml_text, prefix='<PROP>', suffix='</PROP>', section='inner'))
	affects = field(default=Factory(list), native=NativeField(5, native_coffee_affects, section='inner'))
	flag = field(default=0, native=NativeField(6, native_xml_number, prefix='<FLAG>', suffix='</FLAG>', section='inner'))
	value = field(default=0, native=NativeField(7, native_xml_number, prefix='<VALUE>', suffix='</VALUE>', section='inner'))
	material = field(default=0, native=NativeField(8, native_xml_number, prefix='<MTRAL>', suffix='</MTRAL>', section='inner'))
	read_text = field(default='', native=NativeField(9, native_xml_text, prefix='<READ>', suffix='</READ>', section='inner'))
	worn_location = field(default='', native=NativeField(10, native_xml_text, prefix='<WORNL>', suffix='</WORNL>', section='inner'))
	worn_bitmap = field(default=0, native=NativeField(11, native_xml_number, prefix='<WORNB>', suffix='</WORNB>', section='inner'))
	capacity = field(default=0, native=NativeField(12, native_xml_number, prefix='<CAPA>', suffix='</CAPA>', section='inner'))
	container_flags = field(default=0, native=NativeField(13, native_xml_number, prefix='<CONT>', suffix='</CONT>', section='inner'))
	open_ticks = field(default=0, native=NativeField(14, native_xml_number, prefix='<OPENTK>', suffix='</OPENTK>', section='inner'))
	nested_area = field(default=None, native=NativeField(15, native_coffee_nested_area, section='inner', when=lambda owner: owner.nested_area is not None))
	inner_residual = field(default=Factory(list), native=NativeField(16, native_coffee_residuals, section='inner', suffix=''))
	count = attr(default=1)
	raw_data = attr(default=Factory(dict), eq=False)
	native_tag = attr(default='ITEM', type=str)


@attributes
class CoffeeMudExit(object):
	NATIVE_PREFIX = '<REXIT>'
	NATIVE_SUFFIX = '</REXIT>'

	direction = field(default=0, native=NativeField(1, native_xml_number, prefix='<XDIRE>', suffix='</XDIRE>'))
	target_room_id = field(default='', native=NativeField(2, native_xml_text, prefix='<XDOOR>', suffix='</XDOOR>'))
	class_id = field(default='', native=NativeField(3, native_coffee_exit_data, suffix=''))
	outer_residual = field(default=Factory(list), native=NativeField(4, native_coffee_residuals, suffix=''))
	inner_residual = attr(default=Factory(list))
	xexit_residual = attr(default=Factory(list))
	raw_data = attr(default=Factory(dict), eq=False)


@attributes
class CoffeeMudRoom(object):
	NATIVE_PREFIX = '<AROOM>'
	NATIVE_SUFFIX = '</AROOM>'

	room_id = field(default='', native=NativeField(1, native_xml_text, prefix='<ROOMID>', suffix='</ROOMID>'))
	area = field(default='', native=NativeField(2, native_xml_text, prefix='<RAREA>', suffix='</RAREA>'))
	class_id = field(default='', native=NativeField(3, native_xml_text, prefix='<RCLAS>', suffix='</RCLAS>'))
	display = field(default='', native=NativeField(4, native_xml_text, prefix='<RDISP>', suffix='</RDISP>'))
	description = field(default='', native=NativeField(5, native_xml_text, prefix='<RDESC>', suffix='</RDESC>'))
	raw_text = field(default='', eq=False, native=NativeField(6, native_coffee_payload, prefix='<RTEXT>', suffix='</RTEXT>'))
	exits = field(default=Factory(list), native=NativeField(7, native_coffee_exits, suffix=''))
	items = field(default=Factory(list), native=NativeField(8, native_coffee_content, suffix=''))
	outer_residual = field(default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix=''))
	climate = field(default=0, native=NativeField(1, native_xml_number, prefix='<RCLIM>', suffix='</RCLIM>', section='inner'))
	atmosphere = field(default=0, native=NativeField(2, native_xml_number, prefix='<RATMO>', suffix='</RATMO>', section='inner'))
	inner_residual = field(default=Factory(list), native=NativeField(3, native_coffee_residuals, section='inner', suffix=''))
	mobs = attr(default=Factory(list))
	raw_data = attr(default=Factory(dict), eq=False)


@attributes
class CoffeeMudArea(object):
	NATIVE_PREFIX = '<AREA>'
	NATIVE_SUFFIX = '</AREA>'

	top_level = attr(default='')
	class_id = field(default='', native=NativeField(1, native_xml_text, prefix='<ACLAS>', suffix='</ACLAS>'))
	name = field(default='', native=NativeField(2, native_xml_text, prefix='<ANAME>', suffix='</ANAME>'))
	description = field(default='', native=NativeField(3, native_xml_text, prefix='<ADESC>', suffix='</ADESC>'))
	climate = field(default=0, native=NativeField(4, native_xml_number, prefix='<ACLIM>', suffix='</ACLIM>'))
	sub_ops = field(default='', native=NativeField(5, native_xml_text, prefix='<ASUBS>', suffix='</ASUBS>'))
	theme = field(default=0, native=NativeField(6, native_xml_number, prefix='<ATECH>', suffix='</ATECH>'))
	raw_data = field(default=Factory(dict), eq=False, native=NativeField(7, native_coffee_area_data, suffix=''))
	rooms = field(default=Factory(OrderedDict), native=NativeField(8, native_coffee_room_records, prefix='<AROOMS>', suffix='</AROOMS>'))
	outer_residual = field(default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix=''))
	inner_residual = attr(default=Factory(list))
	mobs = attr(default=Factory(list))
	items = attr(default=Factory(list))
	objects = attr(default=Factory(list))


class CoffeeMudAreaFile(object):
	NATIVE_NORMALIZATIONS = (
		'xml-declaration-and-whitespace',
		'empty-element-spelling',
		'unquoted-attribute-repair',
		'bare-ampersand-repair',
		'split-entity-repair',
		'mob-rejuvenation-tag-spelling',
	)

	def __init__(self, filename):
		self.filename = os.fspath(filename)
		with io.open(filename, mode='rt', encoding='latin-1') as coffee_file:
			self.data = coffee_file.read()
			self.area = CoffeeMudArea()

	def dumps(self):
		top_level = self.area.top_level
		if top_level == 'MOBS':
			document = '<MOBS>%s</MOBS>' % ''.join(render_record(mob) for mob in self.area.mobs)
		elif top_level == 'MOB':
			document = ''.join(render_record(mob) for mob in self.area.mobs)
		elif top_level == 'ITEMS':
			document = '<ITEMS>%s</ITEMS>' % ''.join(render_record(item) for item in self.area.items)
		elif top_level == 'ITEM':
			document = ''.join(render_record(item) for item in self.area.items)
		elif top_level == 'AREA':
			document = render_record(self.area)
		elif top_level == 'AROOMS':
			document = '<AROOMS>%s</AROOMS>' % ''.join(render_record(room) for room in self.area.rooms.values())
		elif top_level == 'AROOM':
			document = ''.join(render_record(room) for room in self.area.rooms.values())
		else:
			raise NativeWriteError("Unsupported CoffeeMud top-level document %r" % top_level)
		return native_coffee_document(document) + '\n'

	def write(self, path):
		with io.open(path, mode='wt', encoding='latin-1', newline='\n') as coffee_file:
			coffee_file.write(self.dumps())

	def load_sections(self):
		root = self.parse_document(self.data)
		self.load_root(root)

	def parse_document(self, text):
		text = self.quote_unquoted_attributes(text)
		text = self.escape_bare_ampersands(text)
		try:
			return ET.fromstring(text)
		except ET.ParseError:
			return ET.fromstring("<ROOT>" + text + "</ROOT>")

	def quote_unquoted_attributes(self, text):
		return re.sub(r'<[^<>]+>', self.quote_tag_unquoted_attributes, text)

	def quote_tag_unquoted_attributes(self, match):
		return re.sub(r'(\s+[A-Za-z_:][A-Za-z0-9:_.-]*)=([^\s"\'=<>/]+)', r'\1="\2"', match.group(0))

	def escape_bare_ampersands(self, text):
		return re.sub(r'&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]*;)', '&amp;', text)

	def parse_escaped_xml(self, value):
		if not value:
			return None
		return self.parse_document(html.unescape(self.repair_split_entities(value)))

	def repair_split_entities(self, value):
		return re.sub(r'&\s+(lt|gt|amp|quot|apos);', r'&\1;', value)

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
			if child is None or len(child) == 0:
				return default
		if len(child):
			return self.element_inner_xml(child)
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

	def serialize_element(self, element):
		tail = element.tail
		element.tail = None
		try:
			return ET.tostring(element, encoding='unicode', short_empty_elements=True)
		finally:
			element.tail = tail

	def residual_elements(self, element, known_tags, document=False):
		if element is None:
			return []
		if document and self.clean_tag(element.tag).upper() != 'ROOT':
			elements = [element]
		else:
			elements = list(element)
		known_tags = set(known_tags)
		return [
			self.serialize_element(child)
			for child in elements
			if self.clean_tag(child.tag).upper() not in known_tags
		]

	def element_inner_xml(self, element):
		if element is None:
			return ''
		chunks = [html.escape(element.text or '', quote=False)]
		chunks.extend(self.serialize_element(child) for child in element)
		return ''.join(chunks)

	def read_mobs(self, element, tag='MOB'):
		return [self.read_mob(child, native_tag=tag) for child in element if self.clean_tag(child.tag).upper() == tag]

	def read_mob(self, element, native_tag='MOB'):
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
			native_tag=native_tag,
			outer_residual=self.residual_elements(
				element,
				('MCLAS', 'MLEVL', 'MABLE', 'MREJV', 'MREJUV', 'MTEXT'),
			),
			inner_residual=self.residual_elements(
				text_root,
				('NAME', 'DESC', 'DISP', 'BEHAVES', 'AFFECS', 'FLAG', 'MONEY', 'VARMONEY', 'GENDER', 'MRACE', 'FACTIONS', 'ABLTYS'),
				document=True,
			),
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
				residual=self.residual_elements(behavior, ('BCLASS', 'BPARMS')),
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
				residual=self.residual_elements(affect, ('ACLASS', 'ATEXT')),
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
		result = []
		for ability in self.children(abilities, 'ABLTY'):
			data_element = self.child(ability, 'ADATA')
			result.append(CoffeeMudAbility(
				class_id=self.child_text(ability, 'ACLASS'),
				proficiency=self.child_int(ability, 'APROF'),
				data=self.element_to_data(data_element) if data_element is not None else '',
				data_xml=self.element_inner_xml(data_element),
				residual=self.residual_elements(ability, ('ACLASS', 'APROF', 'ADATA')),
			))
		return result

	def read_items(self, element, tag='ITEM'):
		return [self.read_item(child, native_tag=tag) for child in element if self.clean_tag(child.tag).upper() == tag]

	def read_item(self, element, native_tag='ITEM'):
		raw_text = self.child_text(element, 'ITEXT')
		raw_data = {}
		text_root = self.parse_escaped_xml(raw_text)
		if text_root is not None:
			raw_data = self.document_to_data(text_root)
		nested_area = self.read_nested_area(text_root)
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
			nested_area=nested_area,
			native_tag=native_tag,
			outer_residual=self.residual_elements(
				element,
				('ICLAS', 'IIDEN', 'ILOCA', 'IUSES', 'ILEVL', 'IABLE', 'IREJV', 'ITEXT'),
			),
			inner_residual=self.residual_elements(
				text_root,
				('NAME', 'DESC', 'DISP', 'PROP', 'AFFECS', 'FLAG', 'VALUE', 'MTRAL', 'READ', 'WORNL', 'WORNB', 'CAPA', 'CONT', 'OPENTK', 'SSAREA'),
				document=True,
			),
		)

	def read_nested_area(self, text_root):
		if text_root is None:
			return None
		ssarea = self.child(text_root, 'SSAREA')
		if ssarea is None:
			return None
		area = self.child(ssarea, 'AREA')
		if area is None:
			return None
		return self.read_area(area)

	def read_area(self, element):
		data_element = self.child(element, 'ADATA')
		area = CoffeeMudArea(
			class_id=self.child_text(element, 'ACLAS'),
			name=self.child_text(element, 'ANAME'),
			description=self.child_text(element, 'ADESC'),
			climate=self.child_int(element, 'ACLIM'),
			sub_ops=self.child_text(element, 'ASUBS'),
			theme=self.child_int(element, 'ATECH'),
			raw_data=self.element_to_data(data_element) if data_element is not None else {},
			inner_residual=self.residual_elements(data_element, ()),
			outer_residual=self.residual_elements(
				element,
				('ACLAS', 'ANAME', 'ADESC', 'ACLIM', 'ASUBS', 'ATECH', 'ADATA', 'AROOMS'),
			),
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
			outer_residual=self.residual_elements(
				element,
				('ROOMID', 'RAREA', 'RCLAS', 'RDISP', 'RDESC', 'RTEXT', 'ROOMEXITS', 'ROOMCONTENT'),
			),
			inner_residual=self.residual_elements(
				text_root,
				('RCLIM', 'RATMO'),
				document=True,
			),
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
		inner_residual = []
		xexit_residual = []
		if exit_element is not None:
			class_id = self.child_text(exit_element, 'EXID')
			raw_text = self.child_text(exit_element, 'EXDAT')
			raw_root = self.parse_escaped_xml(raw_text)
			if raw_root is not None:
				raw_data = self.document_to_data(raw_root)
				inner_residual = self.residual_elements(raw_root, (), document=True)
			xexit_residual = self.residual_elements(exit_element, ('EXID', 'EXDAT'))
		return CoffeeMudExit(
			direction=self.child_int(element, 'XDIRE'),
			target_room_id=self.child_text(element, 'XDOOR'),
			class_id=class_id,
			raw_data=raw_data,
			inner_residual=inner_residual,
			xexit_residual=xexit_residual,
			outer_residual=self.residual_elements(element, ('XDIRE', 'XDOOR', 'XEXIT')),
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
		return area_reader.serialization.EnumNameConverter().unstructure(self.area)

	def as_json(self, indent=None):
		return json.dumps(self.as_dict(), indent=indent)


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
