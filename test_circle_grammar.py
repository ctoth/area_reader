from pathlib import Path

import pytest

import area_reader.dialects.circle
import area_reader.parser


def write_circle_family(
	tmp_path: Path,
	family: str,
	text: str,
	*,
	direct_world_root: bool = False,
) -> Path:
	root = tmp_path / "world"
	world_root = root if direct_world_root else root / "lib" / "world"
	family_root = world_root / family
	family_root.mkdir(parents=True)
	filename = f"1.{family}"
	(family_root / filename).write_text(text, encoding="latin-1")
	(family_root / "index").write_text(f"{filename}\n$\n", encoding="ascii")
	return root


def test_circle_reader_accepts_a_direct_world_root(tmp_path):
	root = write_circle_family(
		tmp_path,
		"wld",
		"""#100
Direct root~
The direct world root is accepted.~
1 0 0
S
$""",
		direct_world_root=True,
	)
	(root / "zon").mkdir()
	(root / "zon" / "index").write_text("$\n", encoding="ascii")

	reader = area_reader.CircleAreaFile(root)
	reader.load_sections()

	assert reader.world_root == str(root)
	assert reader.area.rooms[100].name == "Direct root"


@pytest.mark.parametrize(
	("locks", "expected"),
	[
		(0, area_reader.EXIT_FLAGS.NONE),
		(1, area_reader.EXIT_FLAGS.ISDOOR),
		(
			2,
			area_reader.EXIT_FLAGS.ISDOOR | area_reader.EXIT_FLAGS.PICKPROOF,
		),
	],
)
def test_circle_exit_lock_values_match_setup_dir(tmp_path, locks, expected):
	path = tmp_path / "exit.wld"
	path.write_text(
		f"An exit.~\ngate~\n{locks} 123 456\n",
		encoding="latin-1",
	)
	reader = area_reader.CircleAreaFile(tmp_path)
	reader.open_circle_file(path)

	exit_record = reader.read_exit(3)

	assert exit_record.door == 3
	assert exit_record.exit_info == expected
	assert exit_record.key == 123
	assert exit_record.destination == 456


def test_circle_zone_loader_skips_comments_and_blank_lines(tmp_path):
	root = write_circle_family(
		tmp_path,
		"zon",
		"""#30
Commented zone~
3000 3099 30 2

* builders may annotate reset files
G 0 3010 1

S
$""",
	)

	reader = area_reader.CircleAreaFile(root)
	reader.load_zones()

	assert [(reset.command, reset.arg1, reset.arg2, reset.arg3) for reset in reader.area.zones[30].resets] == [
		("G", 3010, 1, None),
	]


def test_circle_object_affects_preserve_location_and_modifier(tmp_path):
	root = write_circle_family(
		tmp_path,
		"obj",
		"""#10
ring~
a ring~
A ring lies here.~
~
9 0 1
0 0 0 0
1 50 5
A
17 -3
$""",
	)

	reader = area_reader.CircleAreaFile(root)
	reader.load_objects()

	assert reader.area.objects[10].affected == [
		area_reader.dialects.circle.CircleAffectData(location=17, modifier=-3),
	]


def test_circle_v3_shop_reads_both_opening_windows(tmp_path):
	root = write_circle_family(
		tmp_path,
		"shp",
		"""CircleMUD v3.0 Shop File~
#3000~
3050
-1
1.15
0.15
SCROLL
-1
no item one~
no item two~
do not buy~
cash one~
cash two~
buy message~
sell message~
0
2
3000
2
3033
-1
9
17
18
22
$""",
	)

	reader = area_reader.CircleAreaFile(root)
	reader.load_shops()

	shop = reader.area.shops[3000]
	assert (shop.open_hour, shop.close_hour) == (9, 17)
	assert (shop.open_hour_2, shop.close_hour_2) == (18, 22)


def test_circle_room_rejects_unknown_metadata(tmp_path):
	root = write_circle_family(
		tmp_path,
		"wld",
		"""#100
Bad room~
Bad metadata follows.~
1 0 0
X
$""",
	)
	reader = area_reader.CircleAreaFile(root)

	with pytest.raises(area_reader.parser.ParseError, match="Unknown room metadata 'X'"):
		reader.load_rooms()


def test_circle_object_rejects_unknown_metadata(tmp_path):
	root = write_circle_family(
		tmp_path,
		"obj",
		"""#10
ring~
a ring~
A ring lies here.~
~
9 0 1
0 0 0 0
1 50 5
X
$""",
	)
	reader = area_reader.CircleAreaFile(root)

	with pytest.raises(area_reader.parser.ParseError, match="Unknown object metadata 'X'"):
		reader.load_objects()


def test_circle_unterminated_string_reports_parse_location(tmp_path):
	path = tmp_path / "broken.wld"
	path.write_text("unterminated", encoding="latin-1")
	reader = area_reader.CircleAreaFile(tmp_path)
	reader.open_circle_file(path)

	with pytest.raises(area_reader.parser.ParseError, match=r"broken\.wld line 1 col -1: Unterminated string"):
		reader.read_string()
