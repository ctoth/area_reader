"""CoffeeMud area models, codecs, and reader."""

import html
import xml.etree.ElementTree as ET
from collections import OrderedDict

from attr import Factory, attr, attributes

import area_reader.schema
from area_reader.native import NativeField, NativeWriteError, render_record
from area_reader.native import number as native_number
from area_reader.native import raw as native_raw


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
