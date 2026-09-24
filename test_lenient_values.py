from pathlib import Path

import area_reader.dialects.rom
from area_reader.constants import SECTOR_TYPES

ROM_AREA_WITH_UNKNOWN_SECTOR = """#AREA
animal.are~
Animal Kingdom~
{ 1 20} Builder Animal Kingdom~
100 199
#ROOMS
#100
A Burrow~
A snug burrow.
~
0 0 15
S
#101
A Field~
An open field.
~
0 0 2
S
#0
#$
"""


ROM_AREA_WITH_ODD_CONDITIONS = """#AREA
isles.are~
The Isles~
{ 1 20} Builder The Isles~
100 199
#OBJECTS
#100
fur coat~
a fur coat~
A fur coat lies here.~
fur~
armor 0 AK
26 26 26 20 0
80 7 2000 p
#101
silver ingot~
a large silver ingot~
A large bar of silver lies here.~
silver~
treasure 0 AO
0 0 0 0 0
0 350 5000 10
#102
yew bow~
a yew bow~
A longbow lies here.~
yew~
5 0 AN
0 4 2 11 0
0 5 250 W
#0
#$
"""


def test_unknown_object_condition_defaults_to_perfect_like_rom(tmp_path: Path) -> None:
    objects = load_rom_text(tmp_path, ROM_AREA_WITH_ODD_CONDITIONS).area.objects

    assert [objects[vnum].condition for vnum in (100, 101, 102)] == [100, 100, 50]
    assert objects[101].cost == 5000


def load_rom_text(tmp_path: Path, text: str) -> area_reader.dialects.rom.RomAreaFile:
    path = tmp_path / "area.are"
    path.write_text(text, encoding="latin-1")
    area_file = area_reader.dialects.rom.RomAreaFile(path)
    area_file.load_sections()
    return area_file


def test_unknown_room_sector_number_is_kept_raw(tmp_path: Path) -> None:
    area_file = load_rom_text(tmp_path, ROM_AREA_WITH_UNKNOWN_SECTOR)

    assert area_file.area.rooms[100].sector_type == 15
    assert not isinstance(area_file.area.rooms[100].sector_type, SECTOR_TYPES)
    assert area_file.area.rooms[101].sector_type is SECTOR_TYPES.FIELD
    assert area_file.as_dict()["rooms"][100]["sector_type"] == 15


def test_unknown_room_sector_number_round_trips(tmp_path: Path) -> None:
    source = load_rom_text(tmp_path, ROM_AREA_WITH_UNKNOWN_SECTOR)
    output = tmp_path / "written.are"

    source.write(output)
    reparsed = area_reader.dialects.rom.RomAreaFile(output)
    reparsed.load_sections()

    assert reparsed.area == source.area
