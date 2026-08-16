"""CoffeeMud area models, codecs, and reader."""

import html
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict

from attr import Factory, attr, attributes

import area_reader.dialects.rom
import area_reader.schema
import area_reader.serialization
from area_reader.native import NativeField, NativeWriteError, render_record
from area_reader.native import number as native_number
from area_reader.native import raw as native_raw


class CoffeeMudAreaFile:
    NATIVE_NORMALIZATIONS = (
        "xml-declaration-and-whitespace",
        "empty-element-spelling",
        "unquoted-attribute-repair",
        "bare-ampersand-repair",
        "split-entity-repair",
        "mob-rejuvenation-tag-spelling",
    )

    def __init__(self, filename):
        self.filename = os.fspath(filename)
        with open(filename, mode="rt", encoding="latin-1") as coffee_file:
            self.data = coffee_file.read()
            self.area = CoffeeMudArea()

    def dumps(self):
        top_level = self.area.top_level
        if top_level == "MOBS":
            document = "<MOBS>{}</MOBS>".format("".join(render_record(mob) for mob in self.area.mobs))
        elif top_level == "MOB":
            document = "".join(render_record(mob) for mob in self.area.mobs)
        elif top_level == "ITEMS":
            document = "<ITEMS>{}</ITEMS>".format("".join(render_record(item) for item in self.area.items))
        elif top_level == "ITEM":
            document = "".join(render_record(item) for item in self.area.items)
        elif top_level == "AREA":
            document = render_record(self.area)
        elif top_level == "AROOMS":
            document = "<AROOMS>{}</AROOMS>".format("".join(render_record(room) for room in self.area.rooms.values()))
        elif top_level == "AROOM":
            document = "".join(render_record(room) for room in self.area.rooms.values())
        else:
            raise NativeWriteError(f"Unsupported CoffeeMud top-level document {top_level!r}")
        return native_coffee_document(document) + "\n"

    def write(self, path):
        with open(path, mode="wt", encoding="latin-1", newline="\n") as coffee_file:
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
        return re.sub(r"<[^<>]+>", self.quote_tag_unquoted_attributes, text)

    def quote_tag_unquoted_attributes(self, match):
        return re.sub(r'(\s+[A-Za-z_:][A-Za-z0-9:_.-]*)=([^\s"\'=<>/]+)', r'\1="\2"', match.group(0))

    def escape_bare_ampersands(self, text):
        return re.sub(r"&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]*;)", "&amp;", text)

    def parse_escaped_xml(self, value):
        if not value:
            return None
        return self.parse_document(html.unescape(self.repair_split_entities(value)))

    def repair_split_entities(self, value):
        return re.sub(r"&\s+(lt|gt|amp|quot|apos);", r"&\1;", value)

    def load_root(self, root):
        tag = self.clean_tag(root.tag)
        if tag == "ROOT":
            for child in root:
                self.load_root(child)
            return
        if tag == "MOBS":
            self.area.top_level = "MOBS"
            self.area.mobs.extend(self.read_mobs(root))
        elif tag == "MOB":
            self.area.top_level = "MOB"
            self.area.mobs.append(self.read_mob(root))
        elif tag == "ITEMS":
            self.area.top_level = "ITEMS"
            self.area.items.extend(self.read_items(root))
            self.area.objects = self.area.items
        elif tag == "ITEM":
            self.area.top_level = "ITEM"
            item = self.read_item(root)
            self.area.items.append(item)
            self.area.objects = self.area.items
        elif tag == "AREA":
            area = self.read_area(root)
            area.top_level = "AREA"
            self.area = area
        elif tag == "AROOMS":
            self.area.top_level = "AROOMS"
            for room in self.read_rooms(root):
                self.area.rooms[room.room_id] = room
        elif tag == "AROOM":
            self.area.top_level = "AROOM"
            room = self.read_room(root)
            self.area.rooms[room.room_id] = room
        else:
            self.area.top_level = tag
            self.area.raw_data[tag] = self.element_to_data(root)

    def clean_tag(self, tag):
        if "}" in tag:
            return tag.rsplit("}", 1)[1]
        return tag

    def child(self, element, tag):
        for child in element:
            if self.clean_tag(child.tag).upper() == tag:
                return child
        return None

    def children(self, element, tag):
        return [child for child in element if self.clean_tag(child.tag).upper() == tag]

    def child_text(self, element, tag, default=""):
        child = self.child(element, tag)
        if (child is None or child.text is None) and (child is None or len(child) == 0):
            return default
        if len(child):
            return self.element_inner_xml(child)
        return child.text

    def child_int(self, element, tag, default=0):
        text = self.child_text(element, tag, "")
        if text == "":
            return default
        try:
            return int(text)
        except ValueError:
            return default

    def child_float(self, element, tag, default=0.0):
        text = self.child_text(element, tag, "")
        if text == "":
            return default
        try:
            return float(text)
        except ValueError:
            return default

    def element_to_data(self, element):
        if len(element) == 0:
            return element.text or ""
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
        if tag == "ROOT":
            return self.element_to_data(element)
        return OrderedDict([(tag, self.element_to_data(element))])

    def serialize_element(self, element):
        tail = element.tail
        element.tail = None
        try:
            return ET.tostring(element, encoding="unicode", short_empty_elements=True)
        finally:
            element.tail = tail

    def residual_elements(self, element, known_tags, document=False):
        if element is None:
            return []
        if document and self.clean_tag(element.tag).upper() != "ROOT":
            elements = [element]
        else:
            elements = list(element)
        known_tags = set(known_tags)
        return [
            self.serialize_element(child) for child in elements if self.clean_tag(child.tag).upper() not in known_tags
        ]

    def element_inner_xml(self, element):
        if element is None:
            return ""
        chunks = [html.escape(element.text or "", quote=False)]
        chunks.extend(self.serialize_element(child) for child in element)
        return "".join(chunks)

    def read_mobs(self, element, tag="MOB"):
        return [self.read_mob(child, native_tag=tag) for child in element if self.clean_tag(child.tag).upper() == tag]

    def read_mob(self, element, native_tag="MOB"):
        raw_text = self.child_text(element, "MTEXT")
        raw_data = {}
        text_root = self.parse_escaped_xml(raw_text)
        if text_root is not None:
            raw_data = self.document_to_data(text_root)
        return CoffeeMudMob(
            class_id=self.child_text(element, "MCLAS"),
            level=self.child_int(element, "MLEVL"),
            ability=self.child_int(element, "MABLE"),
            rejuv=self.child_int(element, "MREJV", self.child_int(element, "MREJUV")),
            name=self.value_from_data(raw_data, "NAME"),
            description=self.value_from_data(raw_data, "DESC"),
            display=self.value_from_data(raw_data, "DISP"),
            race=self.value_from_data(raw_data, "MRACE"),
            gender=self.value_from_data(raw_data, "GENDER"),
            money=self.int_from_data(raw_data, "MONEY"),
            variable_money=self.float_from_data(raw_data, "VARMONEY"),
            flag=self.int_from_data(raw_data, "FLAG"),
            behaviors=self.read_behaviors(text_root),
            affects=self.read_affects(text_root),
            factions=self.read_factions(text_root),
            abilities=self.read_abilities(text_root),
            raw_text=raw_text,
            raw_data=raw_data,
            native_tag=native_tag,
            outer_residual=self.residual_elements(
                element,
                ("MCLAS", "MLEVL", "MABLE", "MREJV", "MREJUV", "MTEXT"),
            ),
            inner_residual=self.residual_elements(
                text_root,
                (
                    "NAME",
                    "DESC",
                    "DISP",
                    "BEHAVES",
                    "AFFECS",
                    "FLAG",
                    "MONEY",
                    "VARMONEY",
                    "GENDER",
                    "MRACE",
                    "FACTIONS",
                    "ABLTYS",
                ),
                document=True,
            ),
        )

    def read_behaviors(self, text_root):
        if text_root is None:
            return []
        behaves = self.child(text_root, "BEHAVES")
        if behaves is None:
            return []
        return [
            CoffeeMudBehavior(
                class_id=self.child_text(behavior, "BCLASS"),
                parameters=self.child_text(behavior, "BPARMS"),
                residual=self.residual_elements(behavior, ("BCLASS", "BPARMS")),
            )
            for behavior in self.children(behaves, "BHAVE")
        ]

    def read_affects(self, text_root):
        if text_root is None:
            return []
        affects = self.child(text_root, "AFFECS")
        if affects is None:
            return []
        return [
            CoffeeMudAffect(
                class_id=self.child_text(affect, "ACLASS"),
                text=self.child_text(affect, "ATEXT"),
                residual=self.residual_elements(affect, ("ACLASS", "ATEXT")),
            )
            for affect in self.children(affects, "AFF")
        ]

    def read_factions(self, text_root):
        if text_root is None:
            return {}
        factions = self.child(text_root, "FACTIONS")
        if factions is None:
            return {}
        result = {}
        for faction in self.children(factions, "FCTN"):
            faction_id = faction.attrib.get("ID", "")
            if faction_id:
                result[faction_id] = self.int_text(faction.text)
        return result

    def read_abilities(self, text_root):
        if text_root is None:
            return []
        abilities = self.child(text_root, "ABLTYS")
        if abilities is None:
            return []
        result = []
        for ability in self.children(abilities, "ABLTY"):
            data_element = self.child(ability, "ADATA")
            result.append(
                CoffeeMudAbility(
                    class_id=self.child_text(ability, "ACLASS"),
                    proficiency=self.child_int(ability, "APROF"),
                    data=self.element_to_data(data_element) if data_element is not None else "",
                    data_xml=self.element_inner_xml(data_element),
                    residual=self.residual_elements(ability, ("ACLASS", "APROF", "ADATA")),
                )
            )
        return result

    def read_items(self, element, tag="ITEM"):
        return [self.read_item(child, native_tag=tag) for child in element if self.clean_tag(child.tag).upper() == tag]

    def read_item(self, element, native_tag="ITEM"):
        raw_text = self.child_text(element, "ITEXT")
        raw_data = {}
        text_root = self.parse_escaped_xml(raw_text)
        if text_root is not None:
            raw_data = self.document_to_data(text_root)
        nested_area = self.read_nested_area(text_root)
        return CoffeeMudItem(
            class_id=self.child_text(element, "ICLAS"),
            ident=self.child_text(element, "IIDEN"),
            location=self.child_text(element, "ILOCA"),
            count=self.int_text(element.attrib.get("COUNT"), 1),
            uses=self.child_int(element, "IUSES"),
            level=self.child_int(element, "ILEVL"),
            ability=self.child_int(element, "IABLE"),
            rejuv=self.child_int(element, "IREJV"),
            name=self.value_from_data(raw_data, "NAME"),
            description=self.value_from_data(raw_data, "DESC"),
            display=self.value_from_data(raw_data, "DISP"),
            prop=self.value_from_data(raw_data, "PROP"),
            flag=self.int_from_data(raw_data, "FLAG"),
            value=self.int_from_data(raw_data, "VALUE"),
            material=self.int_from_data(raw_data, "MTRAL"),
            read_text=self.value_from_data(raw_data, "READ"),
            worn_location=self.value_from_data(raw_data, "WORNL"),
            worn_bitmap=self.int_from_data(raw_data, "WORNB"),
            capacity=self.int_from_data(raw_data, "CAPA"),
            container_flags=self.int_from_data(raw_data, "CONT"),
            open_ticks=self.int_from_data(raw_data, "OPENTK"),
            affects=self.read_affects(text_root),
            raw_text=raw_text,
            raw_data=raw_data,
            nested_area=nested_area,
            native_tag=native_tag,
            outer_residual=self.residual_elements(
                element,
                ("ICLAS", "IIDEN", "ILOCA", "IUSES", "ILEVL", "IABLE", "IREJV", "ITEXT"),
            ),
            inner_residual=self.residual_elements(
                text_root,
                (
                    "NAME",
                    "DESC",
                    "DISP",
                    "PROP",
                    "AFFECS",
                    "FLAG",
                    "VALUE",
                    "MTRAL",
                    "READ",
                    "WORNL",
                    "WORNB",
                    "CAPA",
                    "CONT",
                    "OPENTK",
                    "SSAREA",
                ),
                document=True,
            ),
        )

    def read_nested_area(self, text_root):
        if text_root is None:
            return None
        ssarea = self.child(text_root, "SSAREA")
        if ssarea is None:
            return None
        area = self.child(ssarea, "AREA")
        if area is None:
            return None
        return self.read_area(area)

    def read_area(self, element):
        data_element = self.child(element, "ADATA")
        area = CoffeeMudArea(
            class_id=self.child_text(element, "ACLAS"),
            name=self.child_text(element, "ANAME"),
            description=self.child_text(element, "ADESC"),
            climate=self.child_int(element, "ACLIM"),
            sub_ops=self.child_text(element, "ASUBS"),
            theme=self.child_int(element, "ATECH"),
            raw_data=self.element_to_data(data_element) if data_element is not None else {},
            inner_residual=self.residual_elements(data_element, ()),
            outer_residual=self.residual_elements(
                element,
                ("ACLAS", "ANAME", "ADESC", "ACLIM", "ASUBS", "ATECH", "ADATA", "AROOMS"),
            ),
        )
        rooms = self.child(element, "AROOMS")
        if rooms is not None:
            for room in self.read_rooms(rooms):
                area.rooms[room.room_id] = room
        return area

    def read_rooms(self, element):
        return [self.read_room(child) for child in element if self.clean_tag(child.tag).upper() == "AROOM"]

    def read_room(self, element):
        raw_text = self.child_text(element, "RTEXT")
        raw_data = {}
        text_root = self.parse_escaped_xml(raw_text)
        if text_root is not None:
            raw_data = self.document_to_data(text_root)
        return CoffeeMudRoom(
            room_id=self.child_text(element, "ROOMID"),
            area=self.child_text(element, "RAREA"),
            class_id=self.child_text(element, "RCLAS"),
            display=self.child_text(element, "RDISP"),
            description=self.child_text(element, "RDESC"),
            climate=self.int_from_data(raw_data, "RCLIM"),
            atmosphere=self.int_from_data(raw_data, "RATMO"),
            exits=self.read_room_exits(element),
            mobs=self.read_room_mobs(element),
            items=self.read_room_items(element),
            raw_text=raw_text,
            raw_data=raw_data,
            outer_residual=self.residual_elements(
                element,
                ("ROOMID", "RAREA", "RCLAS", "RDISP", "RDESC", "RTEXT", "ROOMEXITS", "ROOMCONTENT"),
            ),
            inner_residual=self.residual_elements(
                text_root,
                ("RCLIM", "RATMO"),
                document=True,
            ),
        )

    def read_room_exits(self, room_element):
        exits = self.child(room_element, "ROOMEXITS")
        if exits is None:
            return []
        return [self.read_exit(exit_element) for exit_element in self.children(exits, "REXIT")]

    def read_exit(self, element):
        exit_element = self.child(element, "XEXIT")
        class_id = ""
        raw_data = {}
        inner_residual = []
        xexit_residual = []
        if exit_element is not None:
            class_id = self.child_text(exit_element, "EXID")
            raw_text = self.child_text(exit_element, "EXDAT")
            raw_root = self.parse_escaped_xml(raw_text)
            if raw_root is not None:
                raw_data = self.document_to_data(raw_root)
                inner_residual = self.residual_elements(raw_root, (), document=True)
            xexit_residual = self.residual_elements(exit_element, ("EXID", "EXDAT"))
        return CoffeeMudExit(
            direction=self.child_int(element, "XDIRE"),
            target_room_id=self.child_text(element, "XDOOR"),
            class_id=class_id,
            raw_data=raw_data,
            inner_residual=inner_residual,
            xexit_residual=xexit_residual,
            outer_residual=self.residual_elements(element, ("XDIRE", "XDOOR", "XEXIT")),
        )

    def read_room_mobs(self, room_element):
        content = self.child(room_element, "ROOMCONTENT")
        if content is None:
            return []
        mobs = self.child(content, "ROOMMOBS")
        if mobs is None:
            return []
        return self.read_mobs(mobs, tag="RMOB")

    def read_room_items(self, room_element):
        content = self.child(room_element, "ROOMCONTENT")
        if content is None:
            return []
        items = self.child(content, "ROOMITEMS")
        if items is None:
            return []
        return self.read_items(items, tag="RITEM")

    def value_from_data(self, data, key, default=""):
        value = data.get(key, default)
        if isinstance(value, list):
            return value[0] if value else default
        if value is None:
            return default
        return value

    def int_from_data(self, data, key, default=0):
        value = self.value_from_data(data, key, "")
        if value == "":
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def float_from_data(self, data, key, default=0.0):
        value = self.value_from_data(data, key, "")
        if value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def int_text(self, text, default=0):
        if text is None or text == "":
            return default
        try:
            return int(text)
        except ValueError:
            return default

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
        chunks.append(ET.tostring(element, encoding="unicode", short_empty_elements=True))
    return "".join(chunks)


def native_coffee_payload(value, owner):
    del value
    return render_record(owner, section="inner")


def native_coffee_document(value):
    root = ET.fromstring(value)
    payload_tags = {"MTEXT", "ITEXT", "RTEXT", "EXDAT"}

    def collapse_payloads(element):
        for child in element:
            if child.tag.upper() in payload_tags:
                inner = child.text or ""
                inner += "".join(ET.tostring(part, encoding="unicode") for part in child)
                child.clear()
                child.text = inner
            else:
                collapse_payloads(child)

    collapse_payloads(root)
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)


def native_coffee_records(value, owner):
    del owner
    return "".join(render_record(record) for record in value)


def native_coffee_room_records(value, owner):
    del owner
    return "".join(render_record(record) for record in value.values())


def native_coffee_behaviors(value, owner):
    del owner
    records = "".join(render_record(record) for record in value)
    return f"<BEHAVES>{records}</BEHAVES>"


def native_coffee_affects(value, owner):
    del owner
    records = "".join(render_record(record) for record in value)
    return f"<AFFECS>{records}</AFFECS>"


def native_coffee_factions(value, owner):
    del owner
    chunks = []
    for faction_id, amount in value.items():
        if not isinstance(amount, int):
            raise NativeWriteError("CoffeeMud faction values must be integers")
        escaped_id = html.escape(str(faction_id), quote=True)
        chunks.append(f'<FCTN ID="{escaped_id}">{amount}</FCTN>')
    return f"<FACTIONS>{''.join(chunks)}</FACTIONS>"


def native_coffee_abilities(value, owner):
    del owner
    records = "".join(render_record(record) for record in value)
    return f"<ABLTYS>{records}</ABLTYS>"


def native_coffee_nested_area(value, owner):
    del owner
    return f"<SSAREA>{render_record(value)}</SSAREA>"


def native_coffee_exits(value, owner):
    del owner
    records = "".join(render_record(record) for record in value)
    return f"<ROOMEXITS>{records}</ROOMEXITS>"


def native_coffee_content(value, owner):
    del value
    mobs = "".join(render_record(record) for record in owner.mobs)
    items = "".join(render_record(record) for record in owner.items)
    return f"<ROOMCONTENT><ROOMMOBS>{mobs}</ROOMMOBS><ROOMITEMS>{items}</ROOMITEMS></ROOMCONTENT>"


def native_coffee_exit_data(value, owner):
    del value
    inner = native_coffee_residuals(owner.inner_residual, owner)
    xexit_residual = native_coffee_residuals(owner.xexit_residual, owner)
    class_id = html.escape(owner.class_id, quote=False)
    return f"<XEXIT><EXID>{class_id}</EXID><EXDAT>{inner}</EXDAT>{xexit_residual}</XEXIT>"


def native_coffee_area_data(value, owner):
    del value
    residuals = native_coffee_residuals(owner.inner_residual, owner)
    return f"<ADATA>{residuals}</ADATA>"


def native_coffee_item_prefix(owner):
    if owner.native_tag == "ITEM":
        return "<ITEM>"
    if owner.native_tag == "RITEM":
        return f'<RITEM COUNT="{owner.count}">'
    else:
        raise NativeWriteError("CoffeeMud item tag must be ITEM or RITEM")


def native_coffee_item_suffix(owner):
    return f"</{owner.native_tag}>"


def native_coffee_mob_prefix(owner):
    if owner.native_tag not in ("MOB", "RMOB"):
        raise NativeWriteError("CoffeeMud mob tag must be MOB or RMOB")
    return f"<{owner.native_tag}>"


def native_coffee_mob_suffix(owner):
    return f"</{owner.native_tag}>"


@attributes
class CoffeeMudBehavior:
    NATIVE_PREFIX = "<BHAVE>"
    NATIVE_SUFFIX = "</BHAVE>"

    class_id = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<BCLASS>", suffix="</BCLASS>")
    )
    parameters = area_reader.schema.field(
        default="", native=NativeField(2, native_xml_text, prefix="<BPARMS>", suffix="</BPARMS>")
    )
    residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(3, native_coffee_residuals, suffix="")
    )


@attributes
class CoffeeMudAffect:
    NATIVE_PREFIX = "<AFF>"
    NATIVE_SUFFIX = "</AFF>"

    class_id = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<ACLASS>", suffix="</ACLASS>")
    )
    text = area_reader.schema.field(
        default="", native=NativeField(2, native_xml_text, prefix="<ATEXT>", suffix="</ATEXT>")
    )
    residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(3, native_coffee_residuals, suffix="")
    )


@attributes
class CoffeeMudAbility:
    NATIVE_PREFIX = "<ABLTY>"
    NATIVE_SUFFIX = "</ABLTY>"

    class_id = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<ACLASS>", suffix="</ACLASS>")
    )
    proficiency = area_reader.schema.field(
        default=0, native=NativeField(2, native_xml_number, prefix="<APROF>", suffix="</APROF>")
    )
    data_xml = area_reader.schema.field(
        default="", native=NativeField(3, native_raw, prefix="<ADATA>", suffix="</ADATA>")
    )
    data = attr(default="", eq=False)
    residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(4, native_coffee_residuals, suffix="")
    )


@attributes
class CoffeeMudMob:
    NATIVE_PREFIX = native_coffee_mob_prefix
    NATIVE_SUFFIX = native_coffee_mob_suffix

    class_id = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<MCLAS>", suffix="</MCLAS>")
    )
    level = area_reader.schema.field(
        default=0, native=NativeField(2, native_xml_number, prefix="<MLEVL>", suffix="</MLEVL>")
    )
    ability = area_reader.schema.field(
        default=0, native=NativeField(3, native_xml_number, prefix="<MABLE>", suffix="</MABLE>")
    )
    rejuv = area_reader.schema.field(
        default=0, native=NativeField(4, native_xml_number, prefix="<MREJV>", suffix="</MREJV>")
    )
    raw_text = area_reader.schema.field(
        default="", eq=False, native=NativeField(5, native_coffee_payload, prefix="<MTEXT>", suffix="</MTEXT>")
    )
    outer_residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(6, native_coffee_residuals, suffix="")
    )
    name = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<NAME>", suffix="</NAME>", section="inner")
    )
    description = area_reader.schema.field(
        default="", native=NativeField(2, native_xml_text, prefix="<DESC>", suffix="</DESC>", section="inner")
    )
    display = area_reader.schema.field(
        default="", native=NativeField(3, native_xml_text, prefix="<DISP>", suffix="</DISP>", section="inner")
    )
    behaviors = area_reader.schema.field(
        default=Factory(list), native=NativeField(4, native_coffee_behaviors, section="inner")
    )
    affects = area_reader.schema.field(
        default=Factory(list), native=NativeField(5, native_coffee_affects, section="inner")
    )
    flag = area_reader.schema.field(
        default=0, native=NativeField(6, native_xml_number, prefix="<FLAG>", suffix="</FLAG>", section="inner")
    )
    money = area_reader.schema.field(
        default=0, native=NativeField(7, native_xml_number, prefix="<MONEY>", suffix="</MONEY>", section="inner")
    )
    variable_money = area_reader.schema.field(
        default=0.0, native=NativeField(8, native_xml_float, prefix="<VARMONEY>", suffix="</VARMONEY>", section="inner")
    )
    gender = area_reader.schema.field(
        default="", native=NativeField(9, native_xml_text, prefix="<GENDER>", suffix="</GENDER>", section="inner")
    )
    race = area_reader.schema.field(
        default="", native=NativeField(10, native_xml_text, prefix="<MRACE>", suffix="</MRACE>", section="inner")
    )
    factions = area_reader.schema.field(
        default=Factory(dict), native=NativeField(11, native_coffee_factions, section="inner")
    )
    abilities = area_reader.schema.field(
        default=Factory(list), native=NativeField(12, native_coffee_abilities, section="inner")
    )
    inner_residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(13, native_coffee_residuals, section="inner", suffix="")
    )
    raw_data = attr(default=Factory(dict), eq=False)
    native_tag = attr(default="MOB", type=str)


@attributes
class CoffeeMudItem:
    NATIVE_PREFIX = native_coffee_item_prefix
    NATIVE_SUFFIX = native_coffee_item_suffix

    class_id = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<ICLAS>", suffix="</ICLAS>")
    )
    ident = area_reader.schema.field(
        default="", native=NativeField(2, native_xml_text, prefix="<IIDEN>", suffix="</IIDEN>")
    )
    location = area_reader.schema.field(
        default="", native=NativeField(3, native_xml_text, prefix="<ILOCA>", suffix="</ILOCA>")
    )
    uses = area_reader.schema.field(
        default=0, native=NativeField(4, native_xml_number, prefix="<IUSES>", suffix="</IUSES>")
    )
    level = area_reader.schema.field(
        default=0, native=NativeField(5, native_xml_number, prefix="<ILEVL>", suffix="</ILEVL>")
    )
    ability = area_reader.schema.field(
        default=0, native=NativeField(6, native_xml_number, prefix="<IABLE>", suffix="</IABLE>")
    )
    rejuv = area_reader.schema.field(
        default=0, native=NativeField(7, native_xml_number, prefix="<IREJV>", suffix="</IREJV>")
    )
    raw_text = area_reader.schema.field(
        default="", eq=False, native=NativeField(8, native_coffee_payload, prefix="<ITEXT>", suffix="</ITEXT>")
    )
    outer_residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix="")
    )
    name = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<NAME>", suffix="</NAME>", section="inner")
    )
    description = area_reader.schema.field(
        default="", native=NativeField(2, native_xml_text, prefix="<DESC>", suffix="</DESC>", section="inner")
    )
    display = area_reader.schema.field(
        default="", native=NativeField(3, native_xml_text, prefix="<DISP>", suffix="</DISP>", section="inner")
    )
    prop = area_reader.schema.field(
        default="", native=NativeField(4, native_xml_text, prefix="<PROP>", suffix="</PROP>", section="inner")
    )
    affects = area_reader.schema.field(
        default=Factory(list), native=NativeField(5, native_coffee_affects, section="inner")
    )
    flag = area_reader.schema.field(
        default=0, native=NativeField(6, native_xml_number, prefix="<FLAG>", suffix="</FLAG>", section="inner")
    )
    value = area_reader.schema.field(
        default=0, native=NativeField(7, native_xml_number, prefix="<VALUE>", suffix="</VALUE>", section="inner")
    )
    material = area_reader.schema.field(
        default=0, native=NativeField(8, native_xml_number, prefix="<MTRAL>", suffix="</MTRAL>", section="inner")
    )
    read_text = area_reader.schema.field(
        default="", native=NativeField(9, native_xml_text, prefix="<READ>", suffix="</READ>", section="inner")
    )
    worn_location = area_reader.schema.field(
        default="", native=NativeField(10, native_xml_text, prefix="<WORNL>", suffix="</WORNL>", section="inner")
    )
    worn_bitmap = area_reader.schema.field(
        default=0, native=NativeField(11, native_xml_number, prefix="<WORNB>", suffix="</WORNB>", section="inner")
    )
    capacity = area_reader.schema.field(
        default=0, native=NativeField(12, native_xml_number, prefix="<CAPA>", suffix="</CAPA>", section="inner")
    )
    container_flags = area_reader.schema.field(
        default=0, native=NativeField(13, native_xml_number, prefix="<CONT>", suffix="</CONT>", section="inner")
    )
    open_ticks = area_reader.schema.field(
        default=0, native=NativeField(14, native_xml_number, prefix="<OPENTK>", suffix="</OPENTK>", section="inner")
    )
    nested_area = area_reader.schema.field(
        default=None,
        native=NativeField(
            15, native_coffee_nested_area, section="inner", when=lambda owner: owner.nested_area is not None
        ),
    )
    inner_residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(16, native_coffee_residuals, section="inner", suffix="")
    )
    count = attr(default=1)
    raw_data = attr(default=Factory(dict), eq=False)
    native_tag = attr(default="ITEM", type=str)


@attributes
class CoffeeMudExit:
    NATIVE_PREFIX = "<REXIT>"
    NATIVE_SUFFIX = "</REXIT>"

    direction = area_reader.schema.field(
        default=0, native=NativeField(1, native_xml_number, prefix="<XDIRE>", suffix="</XDIRE>")
    )
    target_room_id = area_reader.schema.field(
        default="", native=NativeField(2, native_xml_text, prefix="<XDOOR>", suffix="</XDOOR>")
    )
    class_id = area_reader.schema.field(default="", native=NativeField(3, native_coffee_exit_data, suffix=""))
    outer_residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(4, native_coffee_residuals, suffix="")
    )
    inner_residual = attr(default=Factory(list))
    xexit_residual = attr(default=Factory(list))
    raw_data = attr(default=Factory(dict), eq=False)


@attributes
class CoffeeMudRoom:
    NATIVE_PREFIX = "<AROOM>"
    NATIVE_SUFFIX = "</AROOM>"

    room_id = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<ROOMID>", suffix="</ROOMID>")
    )
    area = area_reader.schema.field(
        default="", native=NativeField(2, native_xml_text, prefix="<RAREA>", suffix="</RAREA>")
    )
    class_id = area_reader.schema.field(
        default="", native=NativeField(3, native_xml_text, prefix="<RCLAS>", suffix="</RCLAS>")
    )
    display = area_reader.schema.field(
        default="", native=NativeField(4, native_xml_text, prefix="<RDISP>", suffix="</RDISP>")
    )
    description = area_reader.schema.field(
        default="", native=NativeField(5, native_xml_text, prefix="<RDESC>", suffix="</RDESC>")
    )
    raw_text = area_reader.schema.field(
        default="", eq=False, native=NativeField(6, native_coffee_payload, prefix="<RTEXT>", suffix="</RTEXT>")
    )
    exits = area_reader.schema.field(default=Factory(list), native=NativeField(7, native_coffee_exits, suffix=""))
    items = area_reader.schema.field(default=Factory(list), native=NativeField(8, native_coffee_content, suffix=""))
    outer_residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix="")
    )
    climate = area_reader.schema.field(
        default=0, native=NativeField(1, native_xml_number, prefix="<RCLIM>", suffix="</RCLIM>", section="inner")
    )
    atmosphere = area_reader.schema.field(
        default=0, native=NativeField(2, native_xml_number, prefix="<RATMO>", suffix="</RATMO>", section="inner")
    )
    inner_residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(3, native_coffee_residuals, section="inner", suffix="")
    )
    mobs = attr(default=Factory(list))
    raw_data = attr(default=Factory(dict), eq=False)


@attributes
class CoffeeMudArea:
    NATIVE_PREFIX = "<AREA>"
    NATIVE_SUFFIX = "</AREA>"

    top_level = attr(default="")
    class_id = area_reader.schema.field(
        default="", native=NativeField(1, native_xml_text, prefix="<ACLAS>", suffix="</ACLAS>")
    )
    name = area_reader.schema.field(
        default="", native=NativeField(2, native_xml_text, prefix="<ANAME>", suffix="</ANAME>")
    )
    description = area_reader.schema.field(
        default="", native=NativeField(3, native_xml_text, prefix="<ADESC>", suffix="</ADESC>")
    )
    climate = area_reader.schema.field(
        default=0, native=NativeField(4, native_xml_number, prefix="<ACLIM>", suffix="</ACLIM>")
    )
    sub_ops = area_reader.schema.field(
        default="", native=NativeField(5, native_xml_text, prefix="<ASUBS>", suffix="</ASUBS>")
    )
    theme = area_reader.schema.field(
        default=0, native=NativeField(6, native_xml_number, prefix="<ATECH>", suffix="</ATECH>")
    )
    raw_data = area_reader.schema.field(
        default=Factory(dict), eq=False, native=NativeField(7, native_coffee_area_data, suffix="")
    )
    rooms = area_reader.schema.field(
        default=Factory(OrderedDict),
        native=NativeField(8, native_coffee_room_records, prefix="<AROOMS>", suffix="</AROOMS>"),
    )
    outer_residual = area_reader.schema.field(
        default=Factory(list), native=NativeField(9, native_coffee_residuals, suffix="")
    )
    inner_residual = attr(default=Factory(list))
    mobs = attr(default=Factory(list))
    items = attr(default=Factory(list))
    objects = attr(default=Factory(list))
