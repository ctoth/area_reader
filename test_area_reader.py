import area_reader
import os
from pathlib import Path
import tempfile
from hypothesis import given, settings, strategies as st


def write_area(directory, text):
	path = Path(directory) / "area.are"
	path.write_text(text, encoding="ascii")
	return path


reset_command = st.sampled_from(["M", "O", "P", "G", "E", "D", "R"])
small_int = st.integers(min_value=0, max_value=9999)
rom_source_dir = Path(r"C:\Users\Q\src\Rom24b6\area")
merc_source_dir = Path(r"C:\Users\Q\src\merc-mud\area")
smaug_source_dir = Path(r"C:\Users\Q\src\_smaug_\db\area")

def test_loading_rom_area(rom_path):
	af = area_reader.RomAreaFile(rom_path)
	af.load_sections()
	assert af.area
	assert af.as_dict()

def test_loading_merc_area(merc_path):
	af = area_reader.MercAreaFile(merc_path)
	af.load_sections()
	assert af.area


@given(arg1=small_int, arg2=small_int, arg3=small_int, arg4=small_int)
@settings(max_examples=30, deadline=None)
def test_rom_reset_reads_arg4_for_mobile_resets(arg1, arg2, arg3, arg4):
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#AREA
file.are~
Test~
{{ All }} Test~
1 99
#RESETS
M 0 {arg1} {arg2} {arg3} {arg4}
S
#$
""")

		af = area_reader.RomAreaFile(path)
		af.load_sections()

		reset = af.area.resets[0]
		assert reset.command == "M"
		assert reset.arg1 == arg1
		assert reset.arg2 == arg2
		assert reset.arg3 == arg3
		assert reset.arg4 == arg4


@given(command=reset_command, arg1=small_int, arg2=small_int, arg3=small_int)
@settings(max_examples=30, deadline=None)
def test_merc_resets_follow_three_argument_loader(command, arg1, arg2, arg3):
	line_arg3 = "" if command in ("G", "R") else f" {arg3}"
	expected_arg3 = 0 if command in ("G", "R") else arg3
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#AREA
Test~
#RESETS
{command} 0 {arg1} {arg2}{line_arg3}
S
#$
""")

		af = area_reader.MercAreaFile(path)
		af.load_sections()

		reset = af.area.resets[0]
		assert reset.command == command
		assert reset.arg1 == arg1
		assert reset.arg2 == arg2
		assert reset.arg3 == expected_arg3
		assert reset.arg4 is None
		assert reset.arg5 is None


@given(wealth=st.integers(min_value=0, max_value=2_000_000))
@settings(max_examples=30, deadline=None)
def test_rom_mobile_wealth_is_read_raw(wealth):
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#AREA
file.are~
Test~
{{ All }} Test~
1 99
#MOBILES
#1
mob~
a mob~
A mob stands here.
~
A plain mobile.
~
human~
0 0 0 0
1 2 1d1+1 1d1+1 1d1+1 bite
0 0 0 0
0 0 0 0
standing standing neutral {wealth}
0 0 medium none
#0
#$
""")

		af = area_reader.RomAreaFile(path)
		af.load_sections()

		assert af.area.mobs[1].wealth == wealth


@given(room_flags=st.integers(min_value=0, max_value=255), sector_type=st.integers(min_value=0, max_value=9))
@settings(max_examples=30, deadline=None)
def test_merc_rooms_use_merc_room_flag_type(room_flags, sector_type):
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#AREA
Test~
#ROOMS
#1
Room~
Description.
~
0 {room_flags} {sector_type}
S
#0
#$
""")

		af = area_reader.MercAreaFile(path)
		af.load_sections()

		room = af.area.rooms[1]
	assert isinstance(room, area_reader.MercRoom)
	assert isinstance(room.room_flags, area_reader.MERC_ROOM_FLAGS)


@given(
	version=st.integers(min_value=0, max_value=9),
	low_soft=st.integers(min_value=0, max_value=60),
	high_soft=st.integers(min_value=0, max_value=60),
	low_hard=st.integers(min_value=0, max_value=60),
	high_hard=st.integers(min_value=0, max_value=60),
)
@settings(max_examples=20, deadline=None)
def test_smaug_reads_real_top_level_metadata(version, low_soft, high_soft, low_hard, high_hard):
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#AREA
SMAUG Test~
#VERSION {version}
#AUTHOR Builder~
#RANGES
{low_soft} {high_soft} {low_hard} {high_hard}
$
#FLAGS 7
#ECONOMY 123 456
#MOBILES
#0
#ROOMS
#0
#$
""")

		af = area_reader.SmaugAreaFile(path)
		af.load_sections()

		assert af.area.name == "SMAUG Test"
		assert af.area.version == version
		assert af.area.author == "Builder"
		assert af.area.low_soft_range == low_soft
		assert af.area.high_soft_range == high_soft
		assert af.area.low_hard_range == low_hard
		assert af.area.high_hard_range == high_hard
		assert af.area.flags == 7
		assert af.area.high_economy == 123
		assert af.area.low_economy == 456


@given(
	act=st.integers(min_value=0, max_value=2_000_000),
	affected=st.integers(min_value=0, max_value=2_000_000),
	alignment=st.integers(min_value=-1000, max_value=1000),
	level=st.integers(min_value=1, max_value=100),
	gold=st.integers(min_value=0, max_value=1_000_000),
	exp=st.integers(min_value=0, max_value=1_000_000),
)
@settings(max_examples=20, deadline=None)
def test_smaug_basic_mobile_uses_smaug_mobile_layout(act, affected, alignment, level, gold, exp):
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#AREA
SMAUG Test~
#MOBILES
#1
mob~
a mob~
A mob stands here.
~
A plain mobile.
~
{act} {affected} {alignment} S
{level} 2 3 1d4+5 2d6+7
{gold} {exp}
8 5 1
#0
#ROOMS
#0
#$
""")

		af = area_reader.SmaugAreaFile(path)
		af.load_sections()

		mob = af.area.mobs[1]
		assert mob.act == act | area_reader.ROM_ACT_TYPES.IS_NPC
		assert mob.affected_by == affected
		assert mob.alignment == alignment
		assert mob.level == level
		assert mob.hitroll == 2
		assert mob.ac == 3
		assert mob.hit.number == 1
		assert mob.hit.sides == 4
		assert mob.hit.bonus == 5
		assert mob.damage.number == 2
		assert mob.damage.sides == 6
		assert mob.damage.bonus == 7
		assert mob.wealth == gold


@given(
	sector_type=st.integers(min_value=0, max_value=10),
	tele_delay=st.integers(min_value=0, max_value=100),
	tele_vnum=st.integers(min_value=0, max_value=50000),
	tunnel=st.integers(min_value=0, max_value=100),
	max_weight=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=20, deadline=None)
def test_smaug_rooms_read_tail_fields(sector_type, tele_delay, tele_vnum, tunnel, max_weight):
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#AREA
SMAUG Test~
#MOBILES
#0
#ROOMS
#1
Room~
Description.
~
0 0 {sector_type} {tele_delay} {tele_vnum} {tunnel} {max_weight}
S
#0
#$
""")

		af = area_reader.SmaugAreaFile(path)
		af.load_sections()

		room = af.area.rooms[1]
		assert isinstance(room, area_reader.SmaugRoom)
		assert room.sector_type == sector_type
		assert room.tele_delay == tele_delay
		assert room.tele_vnum == tele_vnum
		assert room.tunnel == tunnel
		assert room.max_weight == max_weight


@given(
	left_flag=st.sampled_from([1, 2, 4, 8, 16, 32]),
	right_flag=st.sampled_from([64, 128, 256, 512]),
	weight=st.integers(min_value=1, max_value=1000),
	cost=st.integers(min_value=0, max_value=100000),
)
@settings(max_examples=20, deadline=None)
def test_smaug_objects_read_pipe_composed_wear_flags(left_flag, right_flag, weight, cost):
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#AREA
SMAUG Test~
#MOBILES
#0
#OBJECTS
#1
object~
an object~
An object is here.~
~
9 0 {left_flag}|{right_flag}
0 0 0 0
{weight} {cost} 0
#0
#ROOMS
#0
#$
""")

		af = area_reader.SmaugAreaFile(path)
		af.load_sections()

		item = af.area.objects[1]
		assert isinstance(item, area_reader.SmaugItem)
		assert item.wear_flags == left_flag | right_flag
		assert item.weight == weight
		assert item.cost == cost


def test_loading_smaug_map1_source_area_when_available():
	path = smaug_source_dir / "map1.are"
	if not path.exists():
		return

	af = area_reader.SmaugAreaFile(path)
	af.load_sections()

	assert af.area.name == "Continent 1"
	assert 30000 in af.area.mobs
	assert 30000 in af.area.rooms


def test_smaug_vnum_section_can_end_at_eof():
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, """#AREA
SMAUG Test~
#MOBILES
#0
#ROOMS
#1
Room~
Description.
~
0 0 0
S
""")

		af = area_reader.SmaugAreaFile(path)
		af.load_sections()

		assert 1 in af.area.rooms


def test_loading_actual_rom_source_areas_when_available():
	if not rom_source_dir.exists():
		return

	for path in sorted(rom_source_dir.glob("*.are")):
		if path.name == "proto.are":
			continue
		af = area_reader.RomAreaFile(path)
		af.load_sections()
		assert af.area


def test_loading_actual_merc_source_areas_when_available():
	if not merc_source_dir.exists():
		return

	for path in sorted(merc_source_dir.glob("*.are")):
		af = area_reader.MercAreaFile(path)
		af.load_sections()
		assert af.area


def test_loading_actual_smaug_source_areas_when_available():
	if not smaug_source_dir.exists():
		return

	for path in sorted(smaug_source_dir.glob("*.are")):
		af = area_reader.SmaugAreaFile(path)
		af.load_sections()
		assert af.area
