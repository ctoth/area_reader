#! /usr/bin/env python3.11

import logging

from collections import OrderedDict
import enum
import html
import io
import json
import re
import os
import sys
import xml.etree.ElementTree as ET
from attr import attr, attributes, Factory, fields
from operator import setitem

from area_reader.constants import *
from area_reader.native import NativeField, NativeWriteError, number as native_number, raw as native_raw, render_document, render_record, tilde_string as native_tilde_string
import area_reader.serialization
import area_reader.model
import area_reader.schema
import area_reader.values
import area_reader.dialects.rom
import area_reader.dialects.merc
import area_reader.dialects.smaug
import area_reader.dialects.swr
import area_reader.dialects.circle

logger = logging.getLogger('area_reader')
logging.basicConfig(level=logging.INFO)

class ParseError(Exception): pass

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
		area_type = self.area_type or area_reader.dialects.rom.RomArea
		self.area = area_type()
		self.skipped_sections = []
		self.current_section_name = "N/A"
		self.readers = {
			area_reader.values.Word: self.read_word,
			area_reader.values.Letter: self.read_letter,
			area_reader.values.VNum: self.read_number,
			str: self.read_string,
			int: self.read_number,
			area_reader.values.VNum: self.read_number,
			enum.IntFlag: self.read_flag,
			area_reader.dialects.rom.RomArmorClass: lambda: self.read_object_from_fields(area_reader.dialects.rom.RomArmorClass),
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
				area_reader.dialects.smaug.SmaugProgram(
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
		for item in self.load_vnum_section(area_reader.model.Room):
			setitem(self.area.rooms, item.vnum, item)

	def load_objects(self):
		for item in self.load_vnum_section(area_reader.model.Item):
			setitem(self.area.objects, item.vnum, item)

	def load_resets(self):
		for reset in self.read_flat_section(area_reader.model.Reset):
			self.area.resets.append(reset)

	def load_specials(self):
		for special in self.read_flat_section(area_reader.model.Special):
			self.area.specials.append(special)

	def load_shops(self):
		while True:
			keeper = self.read_number()
			if keeper == 0:
				break
			logger.debug("Reading shop with keeper %d", keeper)
			shop = area_reader.model.RomShop(keeper=keeper)
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
			help = area_reader.model.Help(level=level, keyword=keyword)
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
		for mob in self.load_vnum_section(area_reader.dialects.rom.RomMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for item in self.load_vnum_section(area_reader.dialects.rom.RomItem):
			setitem(self.area.objects, item.vnum, item)

	def read_area_metadata(self):
		self.area.original_filename = self.read_string()
		self.area.name = self.read_string()
		self.area.metadata = self.read_string()
		self.area.first_vnum = self.read_number()
		self.area.last_vnum = self.read_number()


class MercAreaFile(AreaFile):
	area_type = area_reader.dialects.merc.MercArea

	def dumps(self):
		return render_document(self.area, self.area.NATIVE_SECTIONS, self.skipped_sections)

	def write(self, path):
		with io.open(path, mode='wt', encoding='latin-1', newline='\n') as area_file:
			area_file.write(self.dumps())

	def load_mobiles(self):
		for mob in self.load_vnum_section(area_reader.dialects.merc.MercMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for item in self.load_vnum_section(area_reader.dialects.merc.MercItem):
			setitem(self.area.objects, item.vnum, item)

	def load_rooms(self):
		for room in self.load_vnum_section(area_reader.dialects.merc.MercRoom):
			setitem(self.area.rooms, room.vnum, room)

	def load_resets(self):
		for reset in self.read_flat_section(area_reader.dialects.merc.MercReset):
			self.area.resets.append(reset)

	def read_area_metadata(self):
		self.area.metadata = self.read_string()

class SmaugAreaFile(RomAreaFile):
	area_type = area_reader.dialects.smaug.SmaugArea
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
		for mob in self.load_smaug_vnum_section(area_reader.dialects.smaug.SmaugMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for item in self.load_smaug_vnum_section(area_reader.dialects.smaug.SmaugItem):
			setitem(self.area.objects, item.vnum, item)

	def load_rooms(self):
		for room in self.load_smaug_vnum_section(area_reader.dialects.smaug.SmaugRoom):
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
		for reset in self.read_flat_section(area_reader.dialects.merc.MercReset):
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
			self.area.repairs.append(area_reader.dialects.smaug.SmaugRepair(keeper=keeper, fix_type=fix_type, profit_fix=profit_fix, shop_type=shop_type, open_hour=open_hour, close_hour=close_hour, comment=comment))

	def load_resetmsg(self):
		self.area.resetmsg = self.read_string()

	def load_economy(self):
		self.area.high_economy = self.read_number()
		self.area.low_economy = self.read_number()

	def load_room(self, vnum):
		logger.debug("Reading room %d" % vnum)
		room = area_reader.model.Room(vnum=vnum)
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
	area_type = area_reader.dialects.swr.SwrArea

	def __init__(self, filename):
		super().__init__(filename)
		if not self.data.lstrip().startswith('#FUSSAREA'):
			self.area = area_reader.dialects.smaug.SmaugArea()

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
				for mob in self.load_smaug_vnum_section(area_reader.dialects.smaug.SmaugMob):
					setitem(self.area.mobs, mob.vnum, mob)
				return
		super().load_sections()

	def load_mobiles(self):
		for mob in self.load_swr_vnum_section(area_reader.dialects.smaug.SmaugMob):
			setitem(self.area.mobs, mob.vnum, mob)

	def load_objects(self):
		for item in self.load_swr_vnum_section(area_reader.dialects.smaug.SmaugItem):
			setitem(self.area.objects, item.vnum, item)

	def load_rooms(self):
		for room in self.load_swr_vnum_section(area_reader.dialects.smaug.SmaugRoom):
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
			return area_reader.dialects.swr.SwrUnknown(key=key, value=self.read_string(), tilde=True)
		return area_reader.dialects.swr.SwrUnknown(key=key, value=self.read_to_eol().strip(), tilde=False)

	def skip_fuss_value(self):
		return self.read_fuss_unknown('')

	def read_fuss_numbers(self):
		return [int(value) for value in self.read_to_eol().split()]

	def read_fuss_program(self):
		program = area_reader.dialects.swr.SwrProgram()
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
		mob = area_reader.dialects.swr.SwrMobile()
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
		mob.ac = area_reader.dialects.rom.RomArmorClass(pierce=stats1[3], bash=stats1[3], slash=stats1[3], exotic=stats1[3])
		mob.wealth = stats1[4]
		mob.experience = stats1[5]
		mob.hit = area_reader.model.Dice(number=stats2[0], sides=stats2[1], bonus=stats2[2])
		mob.damage = area_reader.model.Dice(number=stats3[0], sides=stats3[1], bonus=stats3[2])
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
		item = area_reader.dialects.swr.SwrObject()
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
		room = area_reader.dialects.swr.SwrRoom()
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
				room.resets.append(area_reader.dialects.swr.SwrReset.read(reader=self, letter=letter))
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
		exit = area_reader.dialects.swr.SwrExit()
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
		extra = area_reader.dialects.swr.SwrExtraDescription()
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
		self.area = area_reader.dialects.circle.CircleArea()
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
		return area_reader.model.Dice(number=int(number), sides=int(sides), bonus=bonus)

	def load_zone_file(self, path):
		self.open_circle_file(path)
		while True:
			vnum = self.read_record_header()
			if vnum is None:
				return
			name = self.read_string()
			bot, top, lifespan, reset_mode = self.read_int_list()
			zone = area_reader.dialects.circle.CircleZone(vnum=vnum, name=name, bot=bot, top=top, lifespan=lifespan, reset_mode=reset_mode, source_file=os.path.basename(path))
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
				zone.resets.append(area_reader.dialects.circle.CircleReset(command=command, if_flag=if_flag, arg1=arg1, arg2=arg2, arg3=arg3))
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
		room = area_reader.dialects.circle.CircleRoom(vnum=vnum, name=name, description=description, zone_number=int(zone_number), room_flags=area_reader.dialects.circle.circle_asciiflag_conv(flags), sector_type=int(sector_type))
		while True:
			line = self.read_line().strip()
			if line == 'S':
				return room
			if line.startswith('D'):
				exit = self.read_exit(int(line[1:]))
				room.exits[exit.door] = exit
			elif line == 'E':
				room.extra_descriptions.append(area_reader.model.ExtraDescription(keyword=self.read_string(), description=self.read_string()))
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
		return area_reader.dialects.circle.CircleExit(door=door, description=description, keyword=keyword, exit_info=exit_info, key=key, destination=destination)

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
		act = area_reader.dialects.circle.circle_asciiflag_conv(act_flags) | area_reader.dialects.circle.CircleMobFlags.ISNPC
		affected_by = area_reader.dialects.circle.circle_asciiflag_conv(affected_flags)
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
		return area_reader.dialects.circle.CircleMob(
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
				extra_descriptions.append(area_reader.model.ExtraDescription(keyword=self.read_string(), description=self.read_string()))
			elif line == 'A':
				location, modifier = self.read_int_list()
				affected.append(area_reader.dialects.circle.CircleAffectData(location=location, modifier=modifier))
			else:
				self.parse_fail("Unknown object metadata %r" % line)
		return area_reader.dialects.circle.CircleItem(
			vnum=vnum,
			name=name,
			short_desc=short_desc,
			description=description,
			action_description=action_description,
			item_type=int(item_type),
			extra_flags=area_reader.dialects.circle.circle_asciiflag_conv(extra_flags),
			wear_flags=area_reader.dialects.circle.circle_asciiflag_conv(wear_flags),
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
		return area_reader.dialects.circle.CircleShop(vnum=vnum, products=products, profit_buy=profit_buy, profit_sell=profit_sell, buy_type=buy_type, messages=messages, temper=temper, bitvector=bitvector, keeper=keeper, with_who=with_who, rooms=rooms, open_hour=open_hour, close_hour=close_hour, open_hour_2=open_hour_2, close_hour_2=close_hour_2)

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

	class_id = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<BCLASS>', suffix='</BCLASS>'))
	parameters = area_reader.schema.field(default='', native=NativeField(2, native_xml_text, prefix='<BPARMS>', suffix='</BPARMS>'))
	residual = area_reader.schema.field(default=Factory(list), native=NativeField(3, native_coffee_residuals, suffix=''))


@attributes
class CoffeeMudAffect(object):
	NATIVE_PREFIX = '<AFF>'
	NATIVE_SUFFIX = '</AFF>'

	class_id = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<ACLASS>', suffix='</ACLASS>'))
	text = area_reader.schema.field(default='', native=NativeField(2, native_xml_text, prefix='<ATEXT>', suffix='</ATEXT>'))
	residual = area_reader.schema.field(default=Factory(list), native=NativeField(3, native_coffee_residuals, suffix=''))


@attributes
class CoffeeMudAbility(object):
	NATIVE_PREFIX = '<ABLTY>'
	NATIVE_SUFFIX = '</ABLTY>'

	class_id = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<ACLASS>', suffix='</ACLASS>'))
	proficiency = area_reader.schema.field(default=0, native=NativeField(2, native_xml_number, prefix='<APROF>', suffix='</APROF>'))
	data_xml = area_reader.schema.field(default='', native=NativeField(3, native_raw, prefix='<ADATA>', suffix='</ADATA>'))
	data = attr(default='', eq=False)
	residual = area_reader.schema.field(default=Factory(list), native=NativeField(4, native_coffee_residuals, suffix=''))


@attributes
class CoffeeMudMob(object):
	NATIVE_PREFIX = native_coffee_mob_prefix
	NATIVE_SUFFIX = native_coffee_mob_suffix

	class_id = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<MCLAS>', suffix='</MCLAS>'))
	level = area_reader.schema.field(default=0, native=NativeField(2, native_xml_number, prefix='<MLEVL>', suffix='</MLEVL>'))
	ability = area_reader.schema.field(default=0, native=NativeField(3, native_xml_number, prefix='<MABLE>', suffix='</MABLE>'))
	rejuv = area_reader.schema.field(default=0, native=NativeField(4, native_xml_number, prefix='<MREJV>', suffix='</MREJV>'))
	raw_text = area_reader.schema.field(default='', eq=False, native=NativeField(5, native_coffee_payload, prefix='<MTEXT>', suffix='</MTEXT>'))
	outer_residual = area_reader.schema.field(default=Factory(list), native=NativeField(6, native_coffee_residuals, suffix=''))
	name = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<NAME>', suffix='</NAME>', section='inner'))
	description = area_reader.schema.field(default='', native=NativeField(2, native_xml_text, prefix='<DESC>', suffix='</DESC>', section='inner'))
	display = area_reader.schema.field(default='', native=NativeField(3, native_xml_text, prefix='<DISP>', suffix='</DISP>', section='inner'))
	behaviors = area_reader.schema.field(default=Factory(list), native=NativeField(4, native_coffee_behaviors, section='inner'))
	affects = area_reader.schema.field(default=Factory(list), native=NativeField(5, native_coffee_affects, section='inner'))
	flag = area_reader.schema.field(default=0, native=NativeField(6, native_xml_number, prefix='<FLAG>', suffix='</FLAG>', section='inner'))
	money = area_reader.schema.field(default=0, native=NativeField(7, native_xml_number, prefix='<MONEY>', suffix='</MONEY>', section='inner'))
	variable_money = area_reader.schema.field(default=0.0, native=NativeField(8, native_xml_float, prefix='<VARMONEY>', suffix='</VARMONEY>', section='inner'))
	gender = area_reader.schema.field(default='', native=NativeField(9, native_xml_text, prefix='<GENDER>', suffix='</GENDER>', section='inner'))
	race = area_reader.schema.field(default='', native=NativeField(10, native_xml_text, prefix='<MRACE>', suffix='</MRACE>', section='inner'))
	factions = area_reader.schema.field(default=Factory(dict), native=NativeField(11, native_coffee_factions, section='inner'))
	abilities = area_reader.schema.field(default=Factory(list), native=NativeField(12, native_coffee_abilities, section='inner'))
	inner_residual = area_reader.schema.field(default=Factory(list), native=NativeField(13, native_coffee_residuals, section='inner', suffix=''))
	raw_data = attr(default=Factory(dict), eq=False)
	native_tag = attr(default='MOB', type=str)


@attributes
class CoffeeMudItem(object):
	NATIVE_PREFIX = native_coffee_item_prefix
	NATIVE_SUFFIX = native_coffee_item_suffix

	class_id = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<ICLAS>', suffix='</ICLAS>'))
	ident = area_reader.schema.field(default='', native=NativeField(2, native_xml_text, prefix='<IIDEN>', suffix='</IIDEN>'))
	location = area_reader.schema.field(default='', native=NativeField(3, native_xml_text, prefix='<ILOCA>', suffix='</ILOCA>'))
	uses = area_reader.schema.field(default=0, native=NativeField(4, native_xml_number, prefix='<IUSES>', suffix='</IUSES>'))
	level = area_reader.schema.field(default=0, native=NativeField(5, native_xml_number, prefix='<ILEVL>', suffix='</ILEVL>'))
	ability = area_reader.schema.field(default=0, native=NativeField(6, native_xml_number, prefix='<IABLE>', suffix='</IABLE>'))
	rejuv = area_reader.schema.field(default=0, native=NativeField(7, native_xml_number, prefix='<IREJV>', suffix='</IREJV>'))
	raw_text = area_reader.schema.field(default='', eq=False, native=NativeField(8, native_coffee_payload, prefix='<ITEXT>', suffix='</ITEXT>'))
	outer_residual = area_reader.schema.field(default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix=''))
	name = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<NAME>', suffix='</NAME>', section='inner'))
	description = area_reader.schema.field(default='', native=NativeField(2, native_xml_text, prefix='<DESC>', suffix='</DESC>', section='inner'))
	display = area_reader.schema.field(default='', native=NativeField(3, native_xml_text, prefix='<DISP>', suffix='</DISP>', section='inner'))
	prop = area_reader.schema.field(default='', native=NativeField(4, native_xml_text, prefix='<PROP>', suffix='</PROP>', section='inner'))
	affects = area_reader.schema.field(default=Factory(list), native=NativeField(5, native_coffee_affects, section='inner'))
	flag = area_reader.schema.field(default=0, native=NativeField(6, native_xml_number, prefix='<FLAG>', suffix='</FLAG>', section='inner'))
	value = area_reader.schema.field(default=0, native=NativeField(7, native_xml_number, prefix='<VALUE>', suffix='</VALUE>', section='inner'))
	material = area_reader.schema.field(default=0, native=NativeField(8, native_xml_number, prefix='<MTRAL>', suffix='</MTRAL>', section='inner'))
	read_text = area_reader.schema.field(default='', native=NativeField(9, native_xml_text, prefix='<READ>', suffix='</READ>', section='inner'))
	worn_location = area_reader.schema.field(default='', native=NativeField(10, native_xml_text, prefix='<WORNL>', suffix='</WORNL>', section='inner'))
	worn_bitmap = area_reader.schema.field(default=0, native=NativeField(11, native_xml_number, prefix='<WORNB>', suffix='</WORNB>', section='inner'))
	capacity = area_reader.schema.field(default=0, native=NativeField(12, native_xml_number, prefix='<CAPA>', suffix='</CAPA>', section='inner'))
	container_flags = area_reader.schema.field(default=0, native=NativeField(13, native_xml_number, prefix='<CONT>', suffix='</CONT>', section='inner'))
	open_ticks = area_reader.schema.field(default=0, native=NativeField(14, native_xml_number, prefix='<OPENTK>', suffix='</OPENTK>', section='inner'))
	nested_area = area_reader.schema.field(default=None, native=NativeField(15, native_coffee_nested_area, section='inner', when=lambda owner: owner.nested_area is not None))
	inner_residual = area_reader.schema.field(default=Factory(list), native=NativeField(16, native_coffee_residuals, section='inner', suffix=''))
	count = attr(default=1)
	raw_data = attr(default=Factory(dict), eq=False)
	native_tag = attr(default='ITEM', type=str)


@attributes
class CoffeeMudExit(object):
	NATIVE_PREFIX = '<REXIT>'
	NATIVE_SUFFIX = '</REXIT>'

	direction = area_reader.schema.field(default=0, native=NativeField(1, native_xml_number, prefix='<XDIRE>', suffix='</XDIRE>'))
	target_room_id = area_reader.schema.field(default='', native=NativeField(2, native_xml_text, prefix='<XDOOR>', suffix='</XDOOR>'))
	class_id = area_reader.schema.field(default='', native=NativeField(3, native_coffee_exit_data, suffix=''))
	outer_residual = area_reader.schema.field(default=Factory(list), native=NativeField(4, native_coffee_residuals, suffix=''))
	inner_residual = attr(default=Factory(list))
	xexit_residual = attr(default=Factory(list))
	raw_data = attr(default=Factory(dict), eq=False)


@attributes
class CoffeeMudRoom(object):
	NATIVE_PREFIX = '<AROOM>'
	NATIVE_SUFFIX = '</AROOM>'

	room_id = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<ROOMID>', suffix='</ROOMID>'))
	area = area_reader.schema.field(default='', native=NativeField(2, native_xml_text, prefix='<RAREA>', suffix='</RAREA>'))
	class_id = area_reader.schema.field(default='', native=NativeField(3, native_xml_text, prefix='<RCLAS>', suffix='</RCLAS>'))
	display = area_reader.schema.field(default='', native=NativeField(4, native_xml_text, prefix='<RDISP>', suffix='</RDISP>'))
	description = area_reader.schema.field(default='', native=NativeField(5, native_xml_text, prefix='<RDESC>', suffix='</RDESC>'))
	raw_text = area_reader.schema.field(default='', eq=False, native=NativeField(6, native_coffee_payload, prefix='<RTEXT>', suffix='</RTEXT>'))
	exits = area_reader.schema.field(default=Factory(list), native=NativeField(7, native_coffee_exits, suffix=''))
	items = area_reader.schema.field(default=Factory(list), native=NativeField(8, native_coffee_content, suffix=''))
	outer_residual = area_reader.schema.field(default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix=''))
	climate = area_reader.schema.field(default=0, native=NativeField(1, native_xml_number, prefix='<RCLIM>', suffix='</RCLIM>', section='inner'))
	atmosphere = area_reader.schema.field(default=0, native=NativeField(2, native_xml_number, prefix='<RATMO>', suffix='</RATMO>', section='inner'))
	inner_residual = area_reader.schema.field(default=Factory(list), native=NativeField(3, native_coffee_residuals, section='inner', suffix=''))
	mobs = attr(default=Factory(list))
	raw_data = attr(default=Factory(dict), eq=False)


@attributes
class CoffeeMudArea(object):
	NATIVE_PREFIX = '<AREA>'
	NATIVE_SUFFIX = '</AREA>'

	top_level = attr(default='')
	class_id = area_reader.schema.field(default='', native=NativeField(1, native_xml_text, prefix='<ACLAS>', suffix='</ACLAS>'))
	name = area_reader.schema.field(default='', native=NativeField(2, native_xml_text, prefix='<ANAME>', suffix='</ANAME>'))
	description = area_reader.schema.field(default='', native=NativeField(3, native_xml_text, prefix='<ADESC>', suffix='</ADESC>'))
	climate = area_reader.schema.field(default=0, native=NativeField(4, native_xml_number, prefix='<ACLIM>', suffix='</ACLIM>'))
	sub_ops = area_reader.schema.field(default='', native=NativeField(5, native_xml_text, prefix='<ASUBS>', suffix='</ASUBS>'))
	theme = area_reader.schema.field(default=0, native=NativeField(6, native_xml_number, prefix='<ATECH>', suffix='</ATECH>'))
	raw_data = area_reader.schema.field(default=Factory(dict), eq=False, native=NativeField(7, native_coffee_area_data, suffix=''))
	rooms = area_reader.schema.field(default=Factory(OrderedDict), native=NativeField(8, native_coffee_room_records, prefix='<AROOMS>', suffix='</AROOMS>'))
	outer_residual = area_reader.schema.field(default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix=''))
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
