"""Shared parsing mechanics for text area formats."""

import enum
import json
import logging
import os
from operator import setitem

from attr import fields

import area_reader.model
import area_reader.serialization
import area_reader.values
from area_reader.constants import flag_convert

logger = logging.getLogger("area_reader")


class ParseError(Exception):
    pass


class AreaFile:
    MAX_TRADES = 5

    def __init__(self, filename):
        super().__init__()
        with open(filename, mode="rt", encoding="latin-1") as area_file:
            self.data = area_file.read()
        self.index = 0
        self.filename = filename
        self.area = self.create_area()
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
        }

    def create_area(self):
        return None

    def read_letter(self):
        self.skip_whitespace()
        result = self.current_char
        self.advance()
        return result

    def read_word(self):
        self.skip_whitespace()
        word = ""
        end = ""
        if self.current_char == "'" or self.current_char == '"':
            end = self.current_char
            self.advance()
            word = self.read_until(end)
            if self.current_char != end:
                self.parse_fail("Unterminated quoted word")
            self.advance()
            return word
        while self.current_char != "\0" and not self.current_char.isspace():
            word += self.current_char
            self.advance()
        return word

    def read_string(self):
        self.skip_whitespace()
        res = self.read_until("~")
        if self.current_char != "~":
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
        if self.current_char == "+":
            self.advance()
        elif self.current_char == "-":
            sign = True
            self.advance()
        if not self.current_char.isdigit():
            self.parse_fail("Expected number")
        while self.current_char.isdigit():
            number = number * 10 + int(self.current_char)
            self.advance()
        if sign:
            number *= -1
        if self.current_char == "|":
            self.advance()
            number += self.read_number()
        return number

    def read_to_eol(self):
        return self.read_until("\n")

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
        result = self.data[self.index : ahead]
        self.index = ahead
        return result

    @property
    def current_char(self):
        if self.index >= len(self.data):
            return "\0"
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
                if self.current_char == "+":
                    self.advance()
                if self.current_char == "-":
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
                if self.current_char != "|":
                    break
                self.advance()
            word = 0
            for negative, number in reversed(components):
                word += number
                if negative:
                    word *= -1
            words.append(word)
            if self.current_char != "&":
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
            self.parse_fail(f"Expected {verification} got {letter}")
        return letter

    def load_vnum_section(self, section_object_type):
        while True:
            vnum = self.read_vnum()
            if vnum == 0:
                break
            yield self.read_object(section_object_type, vnum=vnum)

    def read_object(self, object_type, **kwargs):
        if hasattr(object_type, "read"):
            return object_type.read(reader=self, **kwargs)
        return self.read_object_by_fields(object_type, **kwargs)

    def read_object_by_fields(self, object_type, **kwargs):
        f = fields(object_type)
        read = {}

        def always_read(**_context):
            return True

        def unchanged(value):
            return value

        for field in f:
            field_type = field.metadata.get("original_type", field.type)
            if field.metadata.get("read") == False:
                continue
            if issubclass(field_type, enum.IntFlag):
                field_type = enum.IntFlag
            reader = self.readers.get(field_type)
            if reader is None:
                self.parse_fail(f"Could not find a reader for field type {field_type!r}")
            only_if = field.metadata.get("only_if", always_read)
            should_read = only_if(context=read)
            if not should_read:
                continue
            on_read = field.metadata.get("on_read", unchanged)
            read[field.name] = on_read(reader())
        read.update(kwargs)
        return object_type(**read)

    def read_vnum(self):
        self.skip_whitespace()
        self.read_and_verify_letter("#")
        vnum = self.read_number()
        return vnum

    def read_flat_section(self, object_type):
        while True:
            letter = self.read_letter()
            if letter == "S":
                break
            if letter == "*":  # Comment
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
            "area": self.read_area_metadata,
            "mobiles": self.load_mobiles,
            "rooms": self.load_rooms,
            "objects": self.load_objects,
            "helps": self.load_helps,
            "resets": self.load_resets,
            "shops": self.load_shops,
            "specials": self.load_specials,
            "economy": self.load_economy,
            "mobprogs": self.load_mobprogs,
        }
        while True:
            section_name = self.read_section_name()
            self.current_section_name = section_name
            if section_name == "$":
                return
            reader = readers.get(section_name)
            if reader is None:
                self.skip_section(section_name)
            else:
                logger.info("Processing section %s", section_name)
                try:
                    readers[section_name]()
                except ParseError:
                    raise
                except Exception as error:  # noqa: BLE001 - add parser source context to arbitrary model errors
                    self.parse_fail(f"Error reading section {section_name!r}: {error!r}")

    def load_mobprogs(self):
        while True:
            vnum = self.read_vnum()
            if vnum == 0:
                break
            self.area.mobprogs[vnum] = self.read_string()

    def skip_section(self, section_name):
        logger.debug("Skipping section %s", section_name)
        self.skipped_sections.append((section_name, self.read_until("#")))

    def read_section_name(self):
        self.read_and_verify_letter("#")
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
            if keyword[0] == "$":
                break
            logger.debug("Reading help with keyword %s", keyword)
            help = area_reader.model.Help(level=level, keyword=keyword)
            help.text = self.read_string()
            self.area.helps.append(help)

    def jump_to_section(self, section_name):
        self.index = self.data.find("#" + section_name.upper()) + len(section_name) + 1

    def parse_fail(self, message):
        backwards = self.data[: self.index]
        lineno = backwards.count("\n") + 1
        col = backwards[::-1].find("\n")
        message = (
            str(self.filename)
            + " line "
            + str(lineno)
            + " col "
            + str(col)
            + " in section "
            + self.current_section_name
            + ": "
            + message
        )
        raise ParseError(message)

    def surrounding_text(self, window=50):
        return self.data[self.index - window : self.index + window]

    def as_dict(self):
        return area_reader.serialization.EnumNameConverter().unstructure(self.area)

    def as_json(self, indent=None):
        return json.dumps(self.as_dict(), indent=indent)

    def save_as_json(self):
        fname = os.path.splitext(self.filename)[0] + ".json"
        with open(fname, "w") as f:
            json.dump(self.as_dict(), f, indent=2)
