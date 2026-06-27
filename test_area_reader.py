import area_reader
import os
import pytest
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
swr_source_dir = Path(r"C:\Users\Q\src\swrfuss")
circle_source_dir = Path(r"C:\Users\Q\src\circlemud")
coffeemud_source_dir = Path(r"C:\Users\Q\src\coffeemud")

def write_coffeemud_file(directory, text):
	path = Path(directory) / "area.cmare"
	path.write_text(text, encoding="utf-8")
	return path

def write_circle_world(directory, *, zon=None, wld=None, mob=None, obj=None, shp=None):
	root = Path(directory)
	world = root / "lib" / "world"
	for family, text in {
		"zon": zon,
		"wld": wld,
		"mob": mob,
		"obj": obj,
		"shp": shp,
	}.items():
		family_dir = world / family
		family_dir.mkdir(parents=True, exist_ok=True)
		index = family_dir / "index"
		if text is None:
			index.write_text("$\n", encoding="ascii")
			continue
		filename = f"1.{family}"
		(family_dir / filename).write_text(text, encoding="ascii")
		index.write_text(f"{filename}\n$\n", encoding="ascii")
	return root

def swr_are_paths():
	if not swr_source_dir.exists():
		return []
	return sorted(swr_source_dir.rglob("*.are"))

def circle_indexed_paths(family):
	index = circle_source_dir / "lib" / "world" / family / "index"
	if not index.exists():
		return []
	base = index.parent
	paths = []
	for line in index.read_text(encoding="ascii").splitlines():
		name = line.strip()
		if not name or name == "$":
			continue
		paths.append(base / name)
	return paths

def test_loading_rom_area(rom_path):
	af = area_reader.RomAreaFile(rom_path)
	af.load_sections()
	assert af.area
	assert af.as_dict()

def test_loading_merc_area(merc_path):
	af = area_reader.MercAreaFile(merc_path)
	af.load_sections()
	assert af.area


def test_coffeemud_top_level_mobs_parse_as_dict_and_json():
	with tempfile.TemporaryDirectory() as directory:
		path = write_coffeemud_file(directory, """<MOBS><MOB><MCLAS>GenMob</MCLAS><MLEVL>8</MLEVL><MABLE>11</MABLE><MREJV>90</MREJV><MTEXT>&lt;NAME&gt;the death dog&lt;/NAME&gt;</MTEXT></MOB></MOBS>""")

		af = area_reader.CoffeeMudAreaFile(path)
		af.load_sections()

		assert af.area.top_level == "MOBS"
		assert len(af.area.mobs) == 1
		assert af.area.mobs[0].class_id == "GenMob"
		assert af.as_dict()["mobs"][0]["class_id"] == "GenMob"
		assert "GenMob" in af.as_json()


def test_coffeemud_top_level_items_parse():
	with tempfile.TemporaryDirectory() as directory:
		path = write_coffeemud_file(directory, """<ITEMS><ITEM><ICLAS>GenItem</ICLAS><IUSES>2147483647</IUSES><ILEVL>68</ILEVL><IABLE>0</IABLE><IREJV>0</IREJV><ITEXT>&lt;NAME&gt;an iron sifter&lt;/NAME&gt;</ITEXT></ITEM></ITEMS>""")

		af = area_reader.CoffeeMudAreaFile(path)
		af.load_sections()

		assert af.area.top_level == "ITEMS"
		assert len(af.area.items) == 1
		assert af.area.items[0].class_id == "GenItem"


def test_coffeemud_top_level_area_parses_metadata():
	with tempfile.TemporaryDirectory() as directory:
		path = write_coffeemud_file(directory, """<AREA><ACLAS>StdArea</ACLAS><ANAME>Test Area</ANAME><ADESC>A test area.</ADESC><ACLIM>1</ACLIM><ASUBS /><ATECH>2</ATECH><ADATA /><AROOMS /></AREA>""")

		af = area_reader.CoffeeMudAreaFile(path)
		af.load_sections()

		assert af.area.top_level == "AREA"
		assert af.area.class_id == "StdArea"
		assert af.area.name == "Test Area"
		assert af.area.description == "A test area."


def test_coffeemud_direct_room_parses_as_room_record():
	with tempfile.TemporaryDirectory() as directory:
		path = write_coffeemud_file(directory, """<AROOM><ROOMID>Test Area#1</ROOMID><RAREA>Test Area</RAREA><RCLAS>StoneRoom</RCLAS><RDISP>A quiet room</RDISP><RDESC>A plain room.</RDESC><RTEXT /><ROOMEXITS /><ROOMCONTENT><ROOMMOBS /><ROOMITEMS /></ROOMCONTENT></AROOM>""")

		af = area_reader.CoffeeMudAreaFile(path)
		af.load_sections()

		assert af.area.top_level == "AROOM"
	assert "Test Area#1" in af.area.rooms
	assert af.area.rooms["Test Area#1"].class_id == "StoneRoom"


def test_coffeemud_mob_reads_nested_common_fields_and_collections():
	with tempfile.TemporaryDirectory() as directory:
		path = write_coffeemud_file(directory, """<MOBS><MOB><MCLAS>GenMob</MCLAS><MLEVL>8</MLEVL><MABLE>11</MABLE><MREJV>90</MREJV><MTEXT>&lt;NAME&gt;the death dog&lt;/NAME&gt;&lt;DESC&gt;A large two-headed hound barks at you viciously.&lt;/DESC&gt;&lt;DISP&gt;The death dog stands here.&lt;/DISP&gt;&lt;PROP&gt;11|76|8|8|0|8|90|1.0|19|23|0|&lt;/PROP&gt;&lt;BEHAVES&gt;&lt;BHAVE&gt;&lt;BCLASS&gt;CombatAbilities&lt;/BCLASS&gt;&lt;BPARMS /&gt;&lt;/BHAVE&gt;&lt;BHAVE&gt;&lt;BCLASS&gt;MobileAggressive&lt;/BCLASS&gt;&lt;BPARMS&gt;WANDER&lt;/BPARMS&gt;&lt;/BHAVE&gt;&lt;/BEHAVES&gt;&lt;AFFECS&gt;&lt;AFF&gt;&lt;ACLASS&gt;Skill_Dodge&lt;/ACLASS&gt;&lt;ATEXT /&gt;&lt;/AFF&gt;&lt;/AFFECS&gt;&lt;FLAG&gt;0&lt;/FLAG&gt;&lt;MONEY&gt;14&lt;/MONEY&gt;&lt;VARMONEY&gt;0.0&lt;/VARMONEY&gt;&lt;GENDER&gt;N&lt;/GENDER&gt;&lt;MRACE&gt;Dog&lt;/MRACE&gt;&lt;FACTIONS&gt;&lt;FCTN ID="ALIGNMENT.INI"&gt;1&lt;/FCTN&gt;&lt;FCTN ID="INCLINATION.INI"&gt;0&lt;/FCTN&gt;&lt;/FACTIONS&gt;&lt;ABLTYS&gt;&lt;ABLTY&gt;&lt;ACLASS&gt;Skill_Disarm&lt;/ACLASS&gt;&lt;APROF&gt;100&lt;/APROF&gt;&lt;ADATA&gt;&lt;AWRAP /&gt;&lt;/ADATA&gt;&lt;/ABLTY&gt;&lt;/ABLTYS&gt;</MTEXT></MOB></MOBS>""")

		af = area_reader.CoffeeMudAreaFile(path)
		af.load_sections()

		mob = af.area.mobs[0]
		assert mob.class_id == "GenMob"
		assert mob.level == 8
		assert mob.ability == 11
		assert mob.rejuv == 90
		assert mob.name == "the death dog"
		assert mob.description == "A large two-headed hound barks at you viciously."
		assert mob.display == "The death dog stands here."
		assert mob.race == "Dog"
		assert mob.gender == "N"
		assert mob.money == 14
		assert [behavior.class_id for behavior in mob.behaviors] == ["CombatAbilities", "MobileAggressive"]
		assert mob.behaviors[1].parameters == "WANDER"
		assert mob.affects[0].class_id == "Skill_Dodge"
		assert mob.factions["ALIGNMENT.INI"] == 1
		assert mob.factions["INCLINATION.INI"] == 0
		assert mob.abilities[0].class_id == "Skill_Disarm"
		assert mob.abilities[0].proficiency == 100
		assert mob.raw_data["PROP"] == "11|76|8|8|0|8|90|1.0|19|23|0|"


def test_coffeemud_item_reads_nested_common_fields_container_fields_and_affects():
	with tempfile.TemporaryDirectory() as directory:
		path = write_coffeemud_file(directory, """<ITEMS><ITEM><ICLAS>GenContainer</ICLAS><IUSES>2147483647</IUSES><ILEVL>42</ILEVL><IABLE>0</IABLE><IREJV>0</IREJV><ITEXT>&lt;NAME&gt;an iron potion rack&lt;/NAME&gt;&lt;DESC&gt;an iron potion rack.  &lt;/DESC&gt;&lt;DISP&gt;an iron potion rack lies here&lt;/DISP&gt;&lt;PROP&gt;0|0|0|0|0|42|0|1.0|21|0|0|&lt;/PROP&gt;&lt;IMG /&gt;&lt;BEHAVES /&gt;&lt;AFFECS&gt;&lt;AFF&gt;&lt;ACLASS&gt;Prop_NoPurge&lt;/ACLASS&gt;&lt;ATEXT /&gt;&lt;/AFF&gt;&lt;/AFFECS&gt;&lt;FLAG&gt;27&lt;/FLAG&gt;&lt;IDENT /&gt;&lt;VALUE&gt;105&lt;/VALUE&gt;&lt;MTRAL&gt;801&lt;/MTRAL&gt;&lt;READ /&gt;&lt;WORNL&gt;false&lt;/WORNL&gt;&lt;WORNB&gt;512&lt;/WORNB&gt;&lt;CAPA&gt;120&lt;/CAPA&gt;&lt;CONT&gt;2048&lt;/CONT&gt;&lt;OPENTK&gt;30&lt;/OPENTK&gt;</ITEXT></ITEM></ITEMS>""")

		af = area_reader.CoffeeMudAreaFile(path)
		af.load_sections()

		item = af.area.items[0]
		assert item.class_id == "GenContainer"
		assert item.uses == 2147483647
		assert item.level == 42
		assert item.name == "an iron potion rack"
		assert item.description == "an iron potion rack.  "
		assert item.display == "an iron potion rack lies here"
		assert item.prop == "0|0|0|0|0|42|0|1.0|21|0|0|"
		assert item.flag == 27
		assert item.value == 105
		assert item.material == 801
		assert item.read_text == ""
		assert item.worn_location == "false"
		assert item.worn_bitmap == 512
		assert item.capacity == 120
		assert item.container_flags == 2048
		assert item.open_ticks == 30
		assert item.affects[0].class_id == "Prop_NoPurge"


def test_coffeemud_area_reads_rooms_exits_and_room_content():
	with tempfile.TemporaryDirectory() as directory:
		path = write_coffeemud_file(directory, """<AREA><ACLAS>StdArea</ACLAS><ANAME>Test Area</ANAME><ADESC>A test area.</ADESC><ACLIM>1</ACLIM><ASUBS>builder</ASUBS><ATECH>2</ATECH><ADATA><AUTHOR>Builder</AUTHOR></ADATA><AROOMS><AROOM><ROOMID>Test Area#1</ROOMID><RAREA>Test Area</RAREA><RCLAS>StoneRoom</RCLAS><RDISP>A quiet room</RDISP><RDESC>A plain room.</RDESC><RTEXT>&lt;RCLIM&gt;3&lt;/RCLIM&gt;&lt;RATMO&gt;4&lt;/RATMO&gt;</RTEXT><ROOMEXITS><REXIT><XDIRE>0</XDIRE><XDOOR>Test Area#2</XDOOR><XEXIT><EXID>StdOpenDoorway</EXID><EXDAT>&lt;NAME&gt;a doorway&lt;/NAME&gt;</EXDAT></XEXIT></REXIT></ROOMEXITS><ROOMCONTENT><ROOMMOBS><RMOB><MCLAS>GenMob</MCLAS><MLEVL>5</MLEVL><MABLE>1</MABLE><MREJV>10</MREJV><MTEXT>&lt;NAME&gt;a room mob&lt;/NAME&gt;&lt;MONEY&gt;7&lt;/MONEY&gt;</MTEXT></RMOB></ROOMMOBS><ROOMITEMS><RITEM COUNT=2><ICLAS>GenItem</ICLAS><IIDEN>item1</IIDEN><ILOCA>container1</ILOCA><IUSES>1</IUSES><ILEVL>2</ILEVL><IABLE>3</IABLE><IREJV>4</IREJV><ITEXT>&lt;NAME&gt;a room item&lt;/NAME&gt;&lt;VALUE&gt;9&lt;/VALUE&gt;</ITEXT></RITEM></ROOMITEMS></ROOMCONTENT></AROOM></AROOMS></AREA>""")

		af = area_reader.CoffeeMudAreaFile(path)
		af.load_sections()

		assert af.area.class_id == "StdArea"
		assert af.area.name == "Test Area"
		assert af.area.raw_data["AUTHOR"] == "Builder"
		room = af.area.rooms["Test Area#1"]
		assert room.class_id == "StoneRoom"
		assert room.display == "A quiet room"
		assert room.climate == 3
		assert room.atmosphere == 4
		assert room.exits[0].direction == 0
		assert room.exits[0].target_room_id == "Test Area#2"
		assert room.exits[0].class_id == "StdOpenDoorway"
		assert room.exits[0].raw_data["NAME"] == "a doorway"
		assert room.mobs[0].name == "a room mob"
		assert room.mobs[0].money == 7
		assert room.items[0].class_id == "GenItem"
		assert room.items[0].count == 2
		assert room.items[0].ident == "item1"
		assert room.items[0].location == "container1"
		assert room.items[0].name == "a room item"
		assert room.items[0].value == 9


def test_coffeemud_item_parses_nested_ssarea():
	with tempfile.TemporaryDirectory() as directory:
		path = write_coffeemud_file(directory, """<ITEMS><ITEM><ICLAS>GenBoardable</ICLAS><IUSES>100</IUSES><ILEVL>1</ILEVL><IABLE>0</IABLE><IREJV>0</IREJV><ITEXT>&lt;NAME&gt;a skiff&lt;/NAME&gt;&lt;DESC&gt;a small skiff&lt;/DESC&gt;&lt;DISP&gt;a skiff is here&lt;/DISP&gt;&lt;SSAREA&gt;&lt;AREA&gt;&lt;ACLAS&gt;StdBoardableShip&lt;/ACLAS&gt;&lt;ANAME&gt;Skiff&lt;/ANAME&gt;&lt;ADESC /&gt;&lt;ACLIM&gt;0&lt;/ACLIM&gt;&lt;ASUBS /&gt;&lt;ATECH&gt;0&lt;/ATECH&gt;&lt;ADATA /&gt;&lt;AROOMS&gt;&lt;AROOM&gt;&lt;ROOMID&gt;Skiff#0&lt;/ROOMID&gt;&lt;RAREA&gt;Skiff&lt;/RAREA&gt;&lt;RCLAS&gt;ShipDeck&lt;/RCLAS&gt;&lt;RDISP&gt;The Deck&lt;/RDISP&gt;&lt;RDESC /&gt;&lt;RTEXT /&gt;&lt;ROOMEXITS /&gt;&lt;ROOMCONTENT&gt;&lt;ROOMMOBS /&gt;&lt;ROOMITEMS /&gt;&lt;/ROOMCONTENT&gt;&lt;/AROOM&gt;&lt;/AROOMS&gt;&lt;/AREA&gt;&lt;/SSAREA&gt;</ITEXT></ITEM></ITEMS>""")

		af = area_reader.CoffeeMudAreaFile(path)
		af.load_sections()

		item = af.area.items[0]
		assert "SSAREA" in item.raw_data
		assert item.nested_area.name == "Skiff"
		assert item.nested_area.class_id == "StdBoardableShip"
		assert "Skiff#0" in item.nested_area.rooms


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


@given(
	version=st.integers(min_value=1, max_value=99),
	low_soft=st.integers(min_value=0, max_value=60),
	high_soft=st.integers(min_value=60, max_value=103),
	low_hard=st.integers(min_value=0, max_value=60),
	high_hard=st.integers(min_value=60, max_value=103),
	mob_vnum=st.integers(min_value=1, max_value=50000),
	object_vnum=st.integers(min_value=1, max_value=50000),
	room_vnum=st.integers(min_value=1, max_value=50000),
	gold=st.integers(min_value=0, max_value=1_000_000),
)
@settings(max_examples=20, deadline=None)
def test_swr_fuss_area_reads_keyed_records(version, low_soft, high_soft, low_hard, high_hard, mob_vnum, object_vnum, room_vnum, gold):
	with tempfile.TemporaryDirectory() as directory:
		path = write_area(directory, f"""#FUSSAREA
#AREADATA
Version      {version}
Name         SWR Test~
Author       Builder~
Ranges       {low_soft} {high_soft} {low_hard} {high_hard}
Economy      123 456
ResetFreq    15
#ENDAREADATA

#MOBILE
Vnum       {mob_vnum}
Keywords   test mob~
Short      a test mob~
Long       A test mob waits here.
~
Desc       A plain SWR mobile.
~
Race       Human~
Position   standing~
DefPos     standing~
Gender     neuter~
Actflags   npc sentinel~
Stats1     0 50 0 0 {gold} 0
Stats2     5 10 25
Stats3     1 4 2
Stats4     0 0 0 3 3
Attribs    10 10 10 10 10 10 10 0
Saves      0 0 0 0 0
Speaks     common~
Speaking   common~
#ENDMOBILE

#OBJECT
Vnum     {object_vnum}
Keywords test object~
Type     trash~
Short    a test object~
Long     A test object lies here.~
WFlags   take~
Values   1 2 3 4 5 6
Stats    7 8 9 10 11
#ENDOBJECT

#ROOM
Vnum     {room_vnum}
Name     Test Room~
Sector   city~
Flags    nomob indoors~
Stats    1 2 3
Desc     A plain SWR room.
~
Reset M 0 {mob_vnum} 1 {room_vnum}
#ENDROOM

#ENDAREA
""")

		af = area_reader.SwrAreaFile(path)
		af.load_sections()

		assert af.area.name == "SWR Test"
		assert af.area.version == version
		assert af.area.author == "Builder"
		assert af.area.low_soft_range == low_soft
		assert af.area.high_soft_range == high_soft
		assert af.area.low_hard_range == low_hard
		assert af.area.high_hard_range == high_hard
		assert af.area.high_economy == 123
		assert af.area.low_economy == 456
		assert af.area.mobs[mob_vnum].wealth == gold
		assert af.area.objects[object_vnum].weight == 7
		assert af.area.objects[object_vnum].cost == 8
		assert af.area.rooms[room_vnum].name == "Test Room"
		assert af.area.rooms[room_vnum].resets[0].command == "M"


def test_circle_rooms_read_flags_exits_and_extra_descriptions():
	with tempfile.TemporaryDirectory() as directory:
		root = write_circle_world(directory, wld="""#3001
Temple~
The temple is quiet.
~
30 dJ 0
D0
A northern road.
~
gate~
2 3010 3002
E
altar~
The altar is worn smooth.
~
S
$
""")

		af = area_reader.CircleAreaFile(root)
		af.load_sections()

		room = af.area.rooms[3001]
		assert room.name == "Temple"
		assert room.room_flags == area_reader.circle_asciiflag_conv("dJ")
		assert room.sector_type == 0
		assert room.exits[0].description == "A northern road.\n"
		assert room.exits[0].keyword == "gate"
		assert room.exits[0].exit_info == area_reader.EXIT_FLAGS.ISDOOR | area_reader.EXIT_FLAGS.PICKPROOF
		assert room.exits[0].key == 3010
		assert room.exits[0].destination == 3002
		assert room.extra_descriptions[0].keyword == "altar"


def test_circle_simple_mobile_uses_circle_transforms():
	with tempfile.TemporaryDirectory() as directory:
		root = write_circle_world(directory, mob="""#10
clone~
the clone~
A boring old clone is standing here.
~
This clone is nothing to look at.
~
b 0 -25 S
7 3 4 2d8+11 1d4+2
50 125
8 5 1
$
""")

		af = area_reader.CircleAreaFile(root)
		af.load_sections()

		mob = af.area.mobs[10]
		assert mob.name == "clone"
		assert mob.act == area_reader.circle_asciiflag_conv("b") | area_reader.CircleMobFlags.ISNPC
		assert mob.affected_by == 0
		assert mob.alignment == -25
		assert mob.level == 7
		assert mob.hitroll == 17
		assert mob.ac == 40
		assert mob.hit == area_reader.Dice(number=2, sides=8, bonus=11)
		assert mob.damage == area_reader.Dice(number=1, sides=4, bonus=2)
		assert mob.wealth == 50
		assert mob.exp == 125
		assert mob.default_pos == 8
		assert mob.start_pos == 5
		assert mob.sex == 1


def test_circle_enhanced_mobile_reads_espec_section():
	with tempfile.TemporaryDirectory() as directory:
		root = write_circle_world(directory, mob="""#1
Puff dragon fractal~
Puff~
Puff the Fractal Dragon is here.
~
Puff considers a higher reality.
~
anopqr dkp 1000 E
26 1 -1 5d10+550 4d6+3
10000 155000
8 8 2
BareHandAttack: 12
Str: 18
E
$
""")

		af = area_reader.CircleAreaFile(root)
		af.load_sections()

		mob = af.area.mobs[1]
		assert mob.level == 26
		assert mob.especs["BareHandAttack"] == "12"
		assert mob.especs["Str"] == "18"


def test_circle_objects_end_at_next_record():
	with tempfile.TemporaryDirectory() as directory:
		root = write_circle_world(directory, obj="""#10
waybread bread~
a waybread~
Some waybread has been put here.~
~
19 g 1
24 0 0 0
1 50 50
E
waybread bread~
The waybread is traditional travelling food.
~
#11
coin~
a coin~
A coin lies here.~
~
20 0 1
1 2 3 4
1 2 3
$
""")

		af = area_reader.CircleAreaFile(root)
		af.load_sections()

		assert sorted(af.area.objects) == [10, 11]
		item = af.area.objects[10]
		assert item.item_type == 19
		assert item.extra_flags == area_reader.circle_asciiflag_conv("g")
		assert item.wear_flags == 1
		assert item.value == [24, 0, 0, 0]
		assert item.weight == 1
		assert item.cost == 50
		assert item.rent == 50
		assert item.extra_descriptions[0].keyword == "waybread bread"


def test_circle_zones_follow_circle_reset_command_arity():
	with tempfile.TemporaryDirectory() as directory:
		root = write_circle_world(directory, zon="""#30
Midgaard~
3000 3099 30 2
M 0 3000 1 3001
G 1 3010 2
E 1 3011 1 16
R 0 3001 3012
D 0 3001 0 2
S
$
""")

		af = area_reader.CircleAreaFile(root)
		af.load_sections()

		zone = af.area.zones[30]
		assert zone.name == "Midgaard"
		assert zone.bot == 3000
		assert zone.top == 3099
		assert zone.lifespan == 30
		assert zone.reset_mode == 2
		assert [(reset.command, reset.if_flag, reset.arg1, reset.arg2, reset.arg3) for reset in zone.resets] == [
			("M", 0, 3000, 1, 3001),
			("G", 1, 3010, 2, None),
			("E", 1, 3011, 1, 16),
			("R", 0, 3001, 3012, None),
			("D", 0, 3001, 0, 2),
		]


def test_circle_v3_shop_records_parse_core_fields():
	with tempfile.TemporaryDirectory() as directory:
		root = write_circle_world(directory, shp="""CircleMUD v3.0 Shop File~
#3000~
3050
3051
-1
1.15
0.15
SCROLL
WAND
-1
%s Sorry, I haven't got exactly that item.~
%s You don't seem to have that.~
%s I don't buy such items.~
%s That is too expensive for me!~
%s You can't afford it!~
%s That'll be %d coins, please.~
%s You'll get %d coins for it!~
0
2
3000
2
3033
-1
0
28
$
""")

		af = area_reader.CircleAreaFile(root)
		af.load_sections()

		shop = af.area.shops[3000]
		assert shop.products == [3050, 3051]
		assert shop.profit_buy == 1.15
		assert shop.profit_sell == 0.15
		assert shop.buy_type == ["SCROLL", "WAND"]
		assert shop.keeper == 3000
		assert shop.rooms == [3033]
		assert shop.open_hour == 0
		assert shop.close_hour == 28
		assert shop.messages[0] == "%s Sorry, I haven't got exactly that item."


def test_loading_actual_circle_zones_when_available():
	if not circle_source_dir.exists():
		return

	af = area_reader.CircleAreaFile(circle_source_dir)
	af.load_zones()

	assert len(af.area.zones) == len(circle_indexed_paths("zon"))
	assert 0 in af.area.zones


def test_loading_actual_circle_rooms_when_available():
	if not circle_source_dir.exists():
		return

	af = area_reader.CircleAreaFile(circle_source_dir)
	af.load_rooms()

	assert af.area.rooms
	assert 0 in af.area.rooms


def test_loading_actual_circle_mobiles_when_available():
	if not circle_source_dir.exists():
		return

	af = area_reader.CircleAreaFile(circle_source_dir)
	af.load_mobiles()

	assert af.area.mobs
	assert 1 in af.area.mobs


def test_loading_actual_circle_objects_when_available():
	if not circle_source_dir.exists():
		return

	af = area_reader.CircleAreaFile(circle_source_dir)
	af.load_objects()

	assert af.area.objects
	assert 0 in af.area.objects


def test_loading_actual_circle_shops_when_available():
	if not circle_source_dir.exists():
		return

	af = area_reader.CircleAreaFile(circle_source_dir)
	af.load_shops()

	assert af.area.shops
	assert 3000 in af.area.shops


def test_loading_actual_circle_world_when_available():
	if not circle_source_dir.exists():
		return

	af = area_reader.CircleAreaFile(circle_source_dir)
	af.load_sections()

	assert af.area.zones
	assert af.area.rooms
	assert af.area.mobs
	assert af.area.objects
	assert af.area.shops


def test_loading_actual_coffeemud_monsters_when_available():
	path = coffeemud_source_dir / "resources" / "examples" / "monsters.cmare"
	if not path.exists():
		return

	af = area_reader.CoffeeMudAreaFile(path)
	af.load_sections()

	expected_mobs = path.read_text(encoding="latin-1").count("<MOB>")
	assert len(af.area.mobs) == expected_mobs
	assert af.area.mobs[0].name == "the death dog"
	assert af.area.mobs[0].behaviors
	assert af.area.mobs[0].abilities


def test_loading_actual_coffeemud_deities_when_available():
	path = coffeemud_source_dir / "resources" / "examples" / "deities.cmare"
	if not path.exists():
		return

	af = area_reader.CoffeeMudAreaFile(path)
	af.load_sections()

	expected_mobs = path.read_text(encoding="latin-1").count("<MOB>")
	assert len(af.area.mobs) == expected_mobs
	assert af.area.mobs[0].class_id == "GenDeity"
	assert af.area.mobs[0].rejuv == 0
	assert af.area.mobs[0].raw_data["CLEREQ"] == "-class +cleric +necromancer +doomsayer +templar"


def test_loading_actual_coffeemud_junk_items_when_available():
	path = coffeemud_source_dir / "resources" / "examples" / "junk.cmare"
	if not path.exists():
		return

	af = area_reader.CoffeeMudAreaFile(path)
	af.load_sections()

	expected_items = path.read_text(encoding="latin-1").count("<ITEM>")
	assert len(af.area.items) == expected_items
	assert af.area.items[0].name == "an iron sifter"
	assert af.area.items[0].value == 26
	assert af.area.items[1].capacity == 37
	assert af.area.items[2].affects[0].class_id == "Prop_NoPurge"


def test_loading_actual_coffeemud_shipbuilding_nested_areas_when_available():
	path = coffeemud_source_dir / "resources" / "skills" / "shipbuilding.cmare"
	if not path.exists():
		return

	af = area_reader.CoffeeMudAreaFile(path)
	af.load_sections()

	assert af.area.items
	assert af.area.items[0].nested_area is not None
	assert af.area.items[0].nested_area.rooms
	first_room = next(iter(af.area.items[0].nested_area.rooms.values()))
	assert first_room.exits


def test_loading_actual_coffeemud_caravanbuilding_nested_contents_when_available():
	path = coffeemud_source_dir / "resources" / "skills" / "caravanbuilding.cmare"
	if not path.exists():
		return

	af = area_reader.CoffeeMudAreaFile(path)
	af.load_sections()

	nested_areas = [item.nested_area for item in af.area.items if item.nested_area is not None]
	assert nested_areas
	assert any(room.items for area in nested_areas for room in area.rooms.values())


def test_loading_actual_coffeemud_clancastles_nested_rooms_and_exits_when_available():
	path = coffeemud_source_dir / "resources" / "skills" / "clancastles.cmare"
	if not path.exists():
		return

	af = area_reader.CoffeeMudAreaFile(path)
	af.load_sections()

	nested_areas = [item.nested_area for item in af.area.items if item.nested_area is not None]
	assert nested_areas
	assert any(len(area.rooms) > 1 for area in nested_areas)
	assert any(room.exits for area in nested_areas for room in area.rooms.values())


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


@pytest.mark.parametrize("swr_path", swr_are_paths(), ids=lambda path: str(path.relative_to(swr_source_dir)))
def test_loading_actual_swr_are_file_when_available(swr_path):
	af = area_reader.SwrAreaFile(swr_path)
	af.load_sections()
	assert af.area
