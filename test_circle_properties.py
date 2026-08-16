import string
import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st

import area_reader.model


def circle_reader_with_data(text: str) -> area_reader.CircleAreaFile:
	reader = area_reader.CircleAreaFile("unused")
	reader.filename = "generated"
	reader.data = text
	return reader


@given(flags=st.text(alphabet=string.ascii_letters, min_size=0, max_size=20))
@settings(max_examples=40, deadline=None)
def test_circle_ascii_flags_map_letters_to_engine_bit_positions(flags):
	expected = 0
	for flag in flags:
		index = ord(flag) - ord("a") if flag.islower() else 26 + ord(flag) - ord("A")
		expected |= 1 << index

	assert area_reader.circle_asciiflag_conv(flags) == expected


@given(value=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=30, deadline=None)
def test_circle_ascii_flags_preserve_numeric_bitvectors(value):
	assert area_reader.circle_asciiflag_conv(str(value)) == value


@given(
	number=st.integers(min_value=0, max_value=1000),
	sides=st.integers(min_value=1, max_value=1000),
	bonus=st.integers(min_value=0, max_value=1000),
	style=st.sampled_from(("plus", "minus", "none")),
)
@settings(max_examples=50, deadline=None)
def test_circle_dice_parser_preserves_every_supported_token_form(
	number,
	sides,
	bonus,
	style,
):
	if style == "plus":
		token = f"{number}d{sides}+{bonus}"
		expected_bonus = bonus
	elif style == "minus":
		token = f"{number}d{sides}-{bonus}"
		expected_bonus = -bonus
	else:
		token = f"{number}d{sides}"
		expected_bonus = 0

	reader = circle_reader_with_data("")

	assert reader.parse_dice_token(token) == area_reader.model.Dice(
		number=number,
		sides=sides,
		bonus=expected_bonus,
	)


@given(
	vnum=st.integers(min_value=0, max_value=2**31 - 1),
	shop_terminator=st.booleans(),
	leading_whitespace=st.sampled_from(("", " ", "\n", "\r\n\t")),
)
@settings(max_examples=40, deadline=None)
def test_circle_record_headers_accept_world_and_shop_forms(
	vnum,
	shop_terminator,
	leading_whitespace,
):
	terminator = "~" if shop_terminator else "\n"
	reader = circle_reader_with_data(f"{leading_whitespace}#{vnum}{terminator}")

	assert reader.read_record_header() == vnum


@given(line=st.text(alphabet=string.printable.replace("\r", "").replace("\n", ""), max_size=100))
@settings(max_examples=30, deadline=None)
def test_circle_read_line_accepts_a_final_line_without_newline(line):
	reader = circle_reader_with_data(line)

	assert reader.read_line() == line
	assert reader.current_char == "\0"


circle_reset_command = st.sampled_from(("M", "O", "E", "P", "D", "G", "R"))


@given(
	command=circle_reset_command,
	if_flag=st.integers(min_value=0, max_value=1),
	arg1=st.integers(min_value=-1, max_value=50_000),
	arg2=st.integers(min_value=-1, max_value=50_000),
	arg3=st.integers(min_value=-1, max_value=50_000),
)
@settings(max_examples=35, deadline=None)
def test_circle_zone_reset_arity_matches_db_loader(
	command,
	if_flag,
	arg1,
	arg2,
	arg3,
):
	four_argument_command = command in "MOEPD"
	command_line = f"{command} {if_flag} {arg1} {arg2}"
	if four_argument_command:
		command_line += f" {arg3}"
	with tempfile.TemporaryDirectory() as directory:
		zone_root = Path(directory) / "zon"
		zone_root.mkdir()
		zone_path = zone_root / "1.zon"
		zone_path.write_text(
			f"#1\nGenerated zone~\n0 99 30 2\n{command_line}\nS\n$",
			encoding="latin-1",
		)
		reader = area_reader.CircleAreaFile(directory)
		reader.load_zone_file(zone_path)

	reset = reader.area.zones[1].resets[0]
	assert (reset.command, reset.if_flag, reset.arg1, reset.arg2) == (
		command,
		if_flag,
		arg1,
		arg2,
	)
	assert reset.arg3 == (arg3 if four_argument_command else None)


@given(
	level=st.integers(min_value=0, max_value=100),
	hitroll=st.integers(min_value=-100, max_value=100),
	source_ac=st.integers(min_value=-100, max_value=100),
	hit_number=st.integers(min_value=0, max_value=100),
	hit_sides=st.integers(min_value=1, max_value=100),
	hit_bonus=st.integers(min_value=-1000, max_value=1000),
	damage_number=st.integers(min_value=0, max_value=100),
	damage_sides=st.integers(min_value=1, max_value=100),
	damage_bonus=st.integers(min_value=-1000, max_value=1000),
)
@settings(max_examples=40, deadline=None)
def test_circle_mobile_native_transform_is_bijective(
	level,
	hitroll,
	source_ac,
	hit_number,
	hit_sides,
	hit_bonus,
	damage_number,
	damage_sides,
	damage_bonus,
):
	mob = area_reader.CircleMob(
		vnum=1,
		name="generated",
		short_desc="a generated mobile",
		long_desc="A generated mobile is here.",
		description="A generated mobile.",
		act=area_reader.CircleMobFlags.ISNPC,
		mob_type="S",
		level=level,
		hitroll=hitroll,
		ac=source_ac * 10,
		hit=area_reader.model.Dice(number=hit_number, sides=hit_sides, bonus=hit_bonus),
		damage=area_reader.model.Dice(
			number=damage_number,
			sides=damage_sides,
			bonus=damage_bonus,
		),
	)
	reader = circle_reader_with_data(area_reader.render_record(mob))

	assert reader.read_record_header() == mob.vnum
	assert reader.read_mobile(mob.vnum) == mob
