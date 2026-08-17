from pathlib import Path

import area_reader
import area_reader.cli
from area_reader.dialects.medievia import MedieviaAreaFile
from area_reader.model import Dice

ZONE = """#1
Test Zone~
100 30 2 1
12 34 100
M 0 10 1 100 spawn the keeper
W 1 20 1 5 75 sometimes equip
E 1 21 1 malformed source reset
S
#199
$~
"""

WORLD = """#100
The Test Room~
A compact Medievia room fixture.
~
1 16 2 3
4 5 6 7
8 9 10
D0
A carved northern arch.~
arch north~
leaves through the arch~
arrives through the arch~
3 42 101
E
wall carving~
An old carving covers the wall.~
S
#19999
$~
"""

MOBILES = """#10
keeper~
the keeper~
The keeper waits here.
~
The keeper watches the room.
~
ACT 2 AFF 40 ALI -100 CLA M
LEV 12 HRO 3 ARM -5 HIT 2d8+20 DAM 3d4+6
GOL 4d10+1 POS 8 DPOS 8 SEX 1
!BAC !TRI MOUNT MOV 300 STA 90 FLY DRAGON
#19000
$~
"""

OBJECTS = """#20
key iron~
an iron key~
An iron key lies here.~
The key is cold.~
TYP 18 EXT 4 WEA 16385
VAL 1 2 3 4
WGT 1 COS 50 CPD 2
DET 7
LOO key iron~
The key bears a tiny crest.~
AFF 8 12
AFF 18 3
#21
map legacy~
a legacy map~
A legacy map hangs here.~
~
13 4096 0
0 0 0 0
1 583 3
LOO map~
The native loader ignores the old numeric header.~
#19999
$~
"""

SHOPS = """#1~
-1 -1 -1 -1 -1 -1
1.1
0.9
1 2 3 4 5
keeper has no item~
player has no item~
keeper does not buy~
keeper has no cash~
player has no cash~
buy message~
sell message~
0
0
10
0
100
8
20
0
0
#1~
-1 -1 -1 -1 -1 -1
1.0
1.0
0 0 0 0 0
one~
two~
three~
four~
five~
six~
seven~
0
0
10
0
100
0
24
0
0
$~
"""


def write_fixture(root: Path) -> Path:
    lib = root / "lib"
    world = lib / "wld"
    world.mkdir(parents=True)
    (lib / "medievia.zon").write_text(ZONE, encoding="latin-1")
    (world / "Test_Zone").write_text(WORLD, encoding="latin-1")
    (lib / "medievia.mob").write_text(MOBILES, encoding="latin-1")
    (lib / "medievia.obj").write_text(OBJECTS, encoding="latin-1")
    (lib / "medievia.shp").write_text(SHOPS, encoding="latin-1")
    return root


def load_fixture(root: Path) -> MedieviaAreaFile:
    reader = MedieviaAreaFile(root)
    reader.load_sections()
    return reader


def test_reads_medievia_native_fields(tmp_path):
    reader = load_fixture(write_fixture(tmp_path / "Medievia"))

    assert list(reader.area.zones) == [1]
    assert reader.area.zones[1].resets[1].arg4 == 75
    assert reader.area.zones[1].resets[2].arg3 is None

    room = reader.area.rooms[100]
    assert (room.class_restriction, room.move_modifier) == (4, 8)
    assert room.exits[0].entrance_message == "arrives through the arch"
    assert room.extra_descriptions[0].keyword == "wall carving"

    mob = reader.area.mobs[10]
    assert mob.ac == -50
    assert mob.hit == Dice(number=2, sides=8, bonus=20)
    assert mob.exp is None
    assert mob.denied_actions == ("!BAC", "!TRI")
    assert mob.native_residual_tokens == ("DRAGON",)

    item = reader.area.objects[20]
    assert item.deterioration_days == 7
    assert item.eq_level == 12
    assert item.affected[0].location == 18
    assert reader.area.objects[21].native_residual_tokens == (
        "13",
        "4096",
        "0",
        "0",
        "0",
        "0",
        "0",
        "1",
        "583",
        "3",
    )

    assert [shop.vnum for shop in reader.area.shops] == [1, 1]
    assert " EXP " not in reader.dumps()["medievia.mob"]


def test_medievia_native_write_round_trip(tmp_path):
    source = load_fixture(write_fixture(tmp_path / "source"))
    destination = tmp_path / "destination"

    source.write(destination)
    rewritten = load_fixture(destination)

    assert rewritten.area == source.area
    assert rewritten.dumps() == source.dumps()
    assert (destination / "lib" / "wld" / "Test_Zone").is_file()


def test_detects_medievia_game_and_lib_roots(tmp_path):
    root = write_fixture(tmp_path / "Medievia")

    assert area_reader.cli.detect_area_type(root) is MedieviaAreaFile
    assert area_reader.cli.detect_area_type(root / "lib") is MedieviaAreaFile
    assert area_reader.MedieviaAreaFile is MedieviaAreaFile


def test_loads_standalone_medievia_world_file(tmp_path):
    root = write_fixture(tmp_path / "Medievia")
    world_path = root / "lib" / "wld" / "Test_Zone"

    reader = MedieviaAreaFile(world_path)
    reader.load_sections()

    assert list(reader.area.rooms) == [100]
    assert reader.area.rooms[100].source_file == "Test_Zone"
    assert reader.area.room_terminals == {"Test_Zone": 19999}
    assert not reader.area.zones
    assert not reader.area.mobs
    assert not reader.area.objects
    assert not reader.area.shops

    detected = area_reader.cli.load_area(world_path)
    assert isinstance(detected, MedieviaAreaFile)
    assert list(detected.area.rooms) == [100]


def test_loads_standalone_medievia_monolithic_files(tmp_path):
    lib = write_fixture(tmp_path / "Medievia") / "lib"
    expected = {
        "medievia.zon": ("zones", [1]),
        "medievia.mob": ("mobs", [10]),
        "medievia.obj": ("objects", [20, 21]),
        "medievia.shp": ("shops", [1, 1]),
    }

    for filename, (collection_name, identifiers) in expected.items():
        path = lib / filename
        reader = MedieviaAreaFile(path)
        reader.load_sections()
        collection = getattr(reader.area, collection_name)
        actual = [record.vnum for record in collection] if collection_name == "shops" else list(collection)

        assert actual == identifiers
        assert area_reader.cli.detect_area_type(path) is MedieviaAreaFile
