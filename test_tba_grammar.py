import json
from pathlib import Path

import area_reader
import area_reader.cli
import area_reader.dialects.tba


def write_tba_world(tmp_path: Path) -> Path:
    world_root = tmp_path / "lib" / "world"
    sources = {
        "zon": """#1
Builder~
TBA test zone~
100 199 30 2 a 0 B 0 1 34
T 0 2 900 101 \t(a room trigger)
V 1 2 7 101 variable a value with spaces
R 0 101 120 -1 \t(an ignored canonical argument)
S
$
""",
        "wld": """#101
TBA room~
A room using four flag banks.~
1 a 0 B 0 3
D0
A hidden exit.~
gate~
3 120 102
E
wall~
Writing covers the wall.~
S
T 900
$~
""",
        "mob": """#110
test mobile~
a test mobile~
A test mobile waits here.~
It is thoroughly tested.~
a 0 B 0 c 0 D 0 -25 E
5 18 -3 2d4+1 1d6+2
10 20
8 8 1
Str: 14
E
T 900
$
""",
        "obj": """#120
test object~
a test object~
A test object lies here.~
~
9 a 0 B 0 c 0 D 0 e 0 F 0
1 2 3 4
5 6 7 8 9
T 900
E
object~
It has an inscription.~
A
17 -3
$~
""",
        "shp": """CircleMUD v3.0 Shop File~
#130~
120
-1
1.20
0.90
-1
no item~
no item two~
not bought~
no cash~
no cash two~
bought~
sold~
0
0
110
0
101
-1
0
28
0
0
$~
""",
        "trg": """#900
Test trigger~
0 g 100
argument~
say hello
~
$~
""",
        "qst": """#150
Test quest~
keywords~
Quest information.~
Quest complete.~
Quest abandoned.~
3 110 a 120 -1 -1 -1
1 2 3 4 5 6 7
8 9 120
S
$~
""",
    }
    for family, text in sources.items():
        family_root = world_root / family
        family_root.mkdir(parents=True)
        filename = f"1.{family}"
        (family_root / filename).write_text(text, encoding="latin-1")
        (family_root / "index").write_text(f"{filename}\n$\n", encoding="ascii")
    return tmp_path


def test_tba_reader_loads_all_native_families(tmp_path):
    root = write_tba_world(tmp_path)

    reader = area_reader.TbaAreaFile(root)
    reader.load_sections()

    assert reader.area.zones[1].builders == "Builder"
    assert reader.area.zones[1].zone_flags == (1, 0, 1 << 27, 0)
    assert reader.area.zones[1].min_level == 1
    assert reader.area.zones[1].max_level == 34
    assert reader.area.zones[1].resets[1].sarg1 == "variable"
    assert reader.area.zones[1].resets[1].sarg2 == "a value with spaces"
    assert reader.area.zones[1].resets[2].arg3 is None

    room = reader.area.rooms[101]
    assert room.room_flags == (1, 0, 1 << 27, 0)
    assert room.triggers == [900]
    assert room.exits[0].hidden is True

    mob = reader.area.mobs[110]
    assert mob.act_flags == (9, 0, 1 << 27, 0)
    assert mob.affected_flags == (4, 0, 1 << 29, 0)
    assert mob.especs == {"Str": "14"}
    assert mob.triggers == [900]

    item = reader.area.objects[120]
    assert item.extra_flag_banks == (1, 0, 1 << 27, 0)
    assert item.wear_flag_banks == (4, 0, 1 << 29, 0)
    assert item.affect_flag_banks == (16, 0, 1 << 31, 0)
    assert item.level == 8
    assert item.timer == 9
    assert item.triggers == [900]

    assert reader.area.shops[130].products == [120]
    assert reader.area.triggers[900].commands == "say hello\n"
    assert reader.area.quests[150].values == (1, 2, 3, 4, 5, 6, 7)
    assert reader.as_dict()["triggers"][900]["name"] == "Test trigger"
    assert json.loads(reader.as_json())["triggers"]["900"]["name"] == "Test trigger"


def test_tba_native_writer_round_trips_every_family(tmp_path):
    reader = area_reader.TbaAreaFile(write_tba_world(tmp_path / "source"))
    reader.load_sections()

    destination = tmp_path / "destination"
    reader.write(destination)
    reparsed = area_reader.TbaAreaFile(destination)
    reparsed.load_sections()

    assert reparsed.area == reader.area


def test_tba_reader_accepts_an_indexed_empty_shop_file(tmp_path):
    root = write_tba_world(tmp_path)
    (root / "lib" / "world" / "shp" / "1.shp").write_text("$~\n", encoding="ascii")

    reader = area_reader.TbaAreaFile(root)
    reader.load_shops()

    assert reader.area.shops == {}


def test_cli_distinguishes_tba_from_circle_world_trees(tmp_path):
    root = write_tba_world(tmp_path)

    assert area_reader.cli.detect_area_type(root) is area_reader.TbaAreaFile


def test_loading_actual_tba_world_when_available():
    source = Path(r"C:\Users\Q\src\tbamud")
    if not source.exists():
        return

    reader = area_reader.TbaAreaFile(source)
    reader.load_sections()

    assert reader.area.zones
    assert reader.area.rooms
    assert reader.area.mobs
    assert reader.area.objects
    assert reader.area.shops
    assert reader.area.triggers
    assert reader.area.quests
