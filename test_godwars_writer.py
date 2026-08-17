from pathlib import Path

import pytest

import area_reader
import area_reader.cli
import area_reader.dialects.godwars

UPSTREAM_GODWARS_AREA = Path(r"C:\Users\Q\src\GodWars-Deluxe\area")


def godwars_paths() -> tuple[Path, ...]:
    if not UPSTREAM_GODWARS_AREA.exists():
        return ()
    return tuple(sorted((*UPSTREAM_GODWARS_AREA.glob("*.are"), *UPSTREAM_GODWARS_AREA.glob("*.hlp"))))


def load_godwars(path: Path) -> area_reader.dialects.godwars.GodWarsAreaFile:
    area_file = area_reader.dialects.godwars.GodWarsAreaFile(path)
    area_file.load_sections()
    return area_file


def parse_rendered_godwars(tmp_path: Path, text: str) -> area_reader.dialects.godwars.GodWarsAreaFile:
    path = tmp_path / "rendered.are"
    path.write_text(text, encoding="latin-1")
    return load_godwars(path)


@pytest.mark.parametrize("source_path", godwars_paths(), ids=lambda path: path.name)
def test_godwars_corpus_has_semantic_and_canonical_fixed_points(
    tmp_path: Path,
    source_path: Path,
) -> None:
    source = load_godwars(source_path)
    output = tmp_path / source_path.name

    source.write(output)
    rendered = output.read_text(encoding="latin-1")
    reparsed = load_godwars(output)

    assert not source.skipped_sections
    assert reparsed.area == source.area
    assert reparsed.skipped_sections == source.skipped_sections
    assert reparsed.dumps() == rendered


def test_godwars_corpus_inventory_and_extensions_are_non_vacuous() -> None:
    paths = godwars_paths()
    if not paths:
        pytest.skip("upstream GodWars-Deluxe corpus is unavailable")

    listed_names = {
        line.strip()
        for line in (UPSTREAM_GODWARS_AREA / "area.lst").read_text(encoding="latin-1").splitlines()
        if line.strip() != "$"
    }
    assert listed_names <= {path.name for path in paths}

    areas = [load_godwars(path).area for path in paths]
    assert any(area.header_format == "areadata" for area in areas)
    assert any(area.header_format == "area" for area in areas)
    assert any(area.header_format is None for area in areas)
    assert any(item.power is not None for area in areas for item in area.objects.values())
    assert any(room.texts for area in areas for room in area.rooms.values())
    assert sum(len(area.rooms) for area in areas) > 0
    assert sum(len(area.mobs) for area in areas) > 0
    assert sum(len(area.objects) for area in areas) > 0
    assert sum(len(area.resets) for area in areas) > 0


def test_godwars_metadata_object_power_and_room_text_are_editable(tmp_path: Path) -> None:
    path = tmp_path / "godwars.are"
    path.write_text(
        """#AREADATA
Name        GodWars test~
Builders    Builder~
VNUMs       1 2
Security    9
End
#OBJECTS
#1
object~
an object~
An object is here.~
An action.~
1 2 3
4 5 6 7
8 9 10
Q
wearer on~
wearer off~
wearer use~
victim on~
victim off~
victim use~
11 12
#0
#ROOMS
#2
A room~
A room description.~
0 0 0
T
input words~
room output~
character output~
all~
13 14 15
S
#0
#$
""",
        encoding="latin-1",
    )

    source = load_godwars(path)

    assert source.area.name == "GodWars test"
    assert source.area.builders == "Builder"
    assert (source.area.first_vnum, source.area.last_vnum, source.area.security) == (1, 2, 9)
    assert source.area.objects[1].power.spec_type == 11
    assert source.area.objects[1].power.spec_power == 12
    assert source.area.rooms[2].texts[0].input == "input words"
    assert source.area.rooms[2].texts[0].mob == 15

    source.area.builders = "New Builder"
    source.area.objects[1].power.victim_use = "changed victim use"
    source.area.rooms[2].texts[0].output = "changed room output"
    reparsed = parse_rendered_godwars(tmp_path, source.dumps())

    assert reparsed.area == source.area
    assert reparsed.area.builders == "New Builder"
    assert reparsed.area.objects[1].power.victim_use == "changed victim use"
    assert reparsed.area.rooms[2].texts[0].output == "changed room output"


def test_godwars_is_public_and_detects_olc_metadata(tmp_path: Path) -> None:
    path = tmp_path / "godwars.are"
    path.write_text(
        """#AREADATA
Name Test~
Builders Builder~
VNUMs 1 2
Security 1
End
#$
""",
        encoding="latin-1",
    )

    assert area_reader.GodWarsAreaFile is area_reader.dialects.godwars.GodWarsAreaFile
    assert area_reader.cli.detect_area_type(path) is area_reader.dialects.godwars.GodWarsAreaFile
