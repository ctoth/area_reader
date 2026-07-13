import enum
import json
from typing import get_args

import pytest
from attr import fields, has

import area_reader
import area_reader.constants as constants


def enum_types():
	types = {
		value
		for module in (area_reader, constants)
		for value in vars(module).values()
		if isinstance(value, type) and issubclass(value, enum.Enum)
	}
	return sorted(types, key=lambda enum_type: enum_type.__name__)


def enum_members():
	return [
		(enum_type, member_name, member)
		for enum_type in enum_types()
		for member_name, member in enum_type.__members__.items()
	]


def int_flag_types():
	return [
		enum_type
		for enum_type in enum_types()
		if issubclass(enum_type, enum.IntFlag)
	]


def enum_type_in(annotation):
	if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
		return annotation
	for argument in get_args(annotation):
		nested_enum_type = enum_type_in(argument)
		if nested_enum_type is not None:
			return nested_enum_type
	return None


def attrs_enum_fields():
	classes = {
		value
		for value in vars(area_reader).values()
		if isinstance(value, type) and has(value)
	}
	return [
		(owner, attribute, enum_type_in(attribute.type))
		for owner in sorted(classes, key=lambda cls: cls.__name__)
		for attribute in fields(owner)
		if enum_type_in(attribute.type) is not None
	]


ENUM_MEMBERS = enum_members()
INT_FLAG_TYPES = int_flag_types()
ATTRS_ENUM_FIELDS = attrs_enum_fields()


@pytest.mark.parametrize(
	("enum_type", "member_name", "member"),
	ENUM_MEMBERS,
	ids=[
		f"{enum_type.__name__}.{member_name}"
		for enum_type, member_name, _ in ENUM_MEMBERS
	],
)
def test_every_enum_member_unstructures_to_its_qualified_name(
	enum_type,
	member_name,
	member,
):
	result = area_reader.EnumNameConverter().unstructure(member)

	assert result == f"{enum_type.__name__}.{member.name}"
	assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize(
	"flag_type",
	INT_FLAG_TYPES,
	ids=lambda flag_type: flag_type.__name__,
)
def test_every_int_flag_type_jsonifies_zero(flag_type):
	result = area_reader.EnumNameConverter().unstructure(flag_type(0))

	assert result == f"{flag_type.__name__}.{flag_type(0).name or 0}"
	assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize(
	"flag_type",
	INT_FLAG_TYPES,
	ids=lambda flag_type: flag_type.__name__,
)
def test_every_int_flag_type_jsonifies_named_combinations(flag_type):
	members = list(flag_type)
	if len(members) < 2:
		pytest.skip("flag type has fewer than two iterable members")
	value = members[0] | members[1]

	result = area_reader.EnumNameConverter().unstructure(value)

	assert result == f"{flag_type.__name__}.{value.name}"
	assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize(
	"flag_type",
	INT_FLAG_TYPES,
	ids=lambda flag_type: flag_type.__name__,
)
def test_every_int_flag_type_preserves_an_unnamed_value(flag_type):
	unknown_value = 1 << max(member.value.bit_length() for member in flag_type)
	value = flag_type(unknown_value)

	result = area_reader.EnumNameConverter().unstructure(value)

	assert result == f"{flag_type.__name__}.{unknown_value}"
	assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize(
	("owner", "attribute", "enum_type"),
	ATTRS_ENUM_FIELDS,
	ids=[
		f"{owner.__name__}.{attribute.name}"
		for owner, attribute, _ in ATTRS_ENUM_FIELDS
	],
)
def test_every_enum_typed_attrs_field_jsonifies_recursively(
	owner,
	attribute,
	enum_type,
):
	member = next(iter(enum_type))
	instance = owner()
	setattr(instance, attribute.name, member)

	result = area_reader.EnumNameConverter().unstructure(instance)

	assert result[attribute.name] == (
		f"{enum_type.__name__}.{member.name}"
	)
	assert json.loads(json.dumps(result)) == result


def test_enums_jsonify_recursively_in_mixed_containers_and_mapping_keys():
	payload = {
		area_reader.EXIT_DIRECTIONS.NORTH: [
			area_reader.ROM_ACT_TYPES.IS_NPC | area_reader.ROM_ACT_TYPES.SENTINEL,
			{"wear": area_reader.WEAR_FLAGS.TAKE},
		],
	}

	result = area_reader.EnumNameConverter().unstructure(payload)

	assert result == {
		"EXIT_DIRECTIONS.NORTH": [
			"ROM_ACT_TYPES.IS_NPC|SENTINEL",
			{"wear": "WEAR_FLAGS.TAKE"},
		],
	}
	assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize("mob_type", [area_reader.MercMob, area_reader.SmaugMob])
def test_scalar_armor_class_jsonifies_through_its_attrs_model(mob_type):
	mob = mob_type(ac=-37)

	result = area_reader.EnumNameConverter().unstructure(mob)

	assert result["ac"] == -37
	assert json.loads(json.dumps(result)) == result


def test_smaug_area_uses_smaug_room_and_exit_json_shapes():
	area = area_reader.SmaugArea(
		rooms={
			1: area_reader.SmaugRoom(
			sector_type=7,
			exits=[area_reader.SmaugExit(door=5)],
			),
		},
	)

	result = area_reader.EnumNameConverter().unstructure(area)
	json_result = json.loads(json.dumps(result))

	assert result["rooms"][1]["sector_type"] == 7
	assert result["rooms"][1]["exits"][0]["door"] == 5
	assert json_result["rooms"]["1"]["sector_type"] == 7
	assert json_result["rooms"]["1"]["exits"][0]["door"] == 5


def test_save_as_json_uses_the_same_enum_safe_representation(tmp_path):
	area_file = object.__new__(area_reader.AreaFile)
	area_file.filename = str(tmp_path / "enum-area.are")
	area_file.area = area_reader.RomArea(
		mobs={
			1: area_reader.RomMob(
			act=(
				area_reader.ROM_ACT_TYPES.IS_NPC
				| area_reader.ROM_ACT_TYPES.SENTINEL
			),
			),
		},
	)

	area_file.save_as_json()

	saved = json.loads((tmp_path / "enum-area.json").read_text())
	assert saved == json.loads(json.dumps(area_file.as_dict()))
	assert saved["mobs"]["1"]["act"] == "ROM_ACT_TYPES.IS_NPC|SENTINEL"
