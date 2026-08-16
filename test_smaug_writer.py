from pathlib import Path

import pytest

import area_reader.dialects.smaug

UPSTREAM_SMAUG_CORPUS = Path(r"C:\Users\Q\src\_smaug_\db\area")


def smaug_paths() -> tuple[Path, ...]:
    if not UPSTREAM_SMAUG_CORPUS.exists():
        return ()
    return tuple(sorted(UPSTREAM_SMAUG_CORPUS.glob("*.are")))


def load_smaug(path: Path) -> area_reader.dialects.smaug.SmaugAreaFile:
    area_file = area_reader.dialects.smaug.SmaugAreaFile(path)
    area_file.load_sections()
    return area_file


def parse_rendered_smaug(tmp_path: Path, text: str) -> area_reader.dialects.smaug.SmaugAreaFile:
    path = tmp_path / "rendered.are"
    path.write_text(text, encoding="latin-1")
    return load_smaug(path)


@pytest.mark.parametrize("source_path", smaug_paths(), ids=lambda path: path.name)
def test_smaug_corpus_has_semantic_and_canonical_fixed_points(
    tmp_path: Path,
    source_path: Path,
) -> None:
    source = load_smaug(source_path)

    rendered = source.dumps()
    reparsed = parse_rendered_smaug(tmp_path, rendered)

    assert reparsed.area == source.area
    assert reparsed.skipped_sections == source.skipped_sections
    assert reparsed.dumps() == rendered


def test_smaug_corpus_round_trip_is_non_vacuous() -> None:
    paths = smaug_paths()
    if not paths:
        pytest.skip("upstream SMAUG corpus is unavailable")

    areas = [load_smaug(path).area for path in paths]

    assert any(area.name for area in areas)
    assert sum(len(area.rooms) for area in areas) > 0
    assert sum(len(area.mobs) for area in areas) > 0
    assert sum(len(area.objects) for area in areas) > 0
    assert sum(len(area.resets) for area in areas) > 0
    assert any(area.reset_frequency for area in areas)
    assert any(area.continent for area in areas)
    assert any(area.climate for area in areas)
    assert any(area.repairs for area in areas)
    assert any(mob.programs for area in areas for mob in area.mobs.values())
    assert any(item.programs for area in areas for item in area.objects.values())
    assert any(room.programs for area in areas for room in area.rooms.values())
    assert any(room.maps for area in areas for room in area.rooms.values())
    assert any(mob.complex_lines for area in areas for mob in area.mobs.values())
    assert any(item.cost_tail for area in areas for item in area.objects.values())


def test_smaug_write_uses_the_canonical_rendering(tmp_path: Path) -> None:
    paths = smaug_paths()
    if not paths:
        pytest.skip("upstream SMAUG corpus is unavailable")
    source = load_smaug(paths[0])
    output = tmp_path / "written.are"

    source.write(output)

    assert output.read_text(encoding="latin-1") == source.dumps()
    assert load_smaug(output).area == source.area


def test_smaug_native_fields_are_editable_declaratively(tmp_path: Path) -> None:
    path = tmp_path / "native.are"
    path.write_text(
        """#AREA Editable~
#VERSION 3
#AUTHOR Builder~
#RANGES
1 10 0 20
$
#FLAGS
4 12
#ECONOMY 3 400
#CONTINENT continent2~
#CLIMATE 1 2 3
#MOBILES
#1
mob~
a mob~
A mob is here.~
A mob.~
1 2 3 C
4 5 6 1d2+3 2d3+4
7 8
9 10 1
11 12 13 14 15 16 17
18 19 20 21 22
23 24 25 26 27 28 29
30 31 32 33 34 35 36 37
> greet_prog 100~
say hello
~
|
#0
#OBJECTS
#2
object~
an object~
An object is here.~
An action occurs.~
9 10 11 12 13
1 2 3 4 5 6
7 8 9
> use_prog 100~
say used
~
|
#0
#ROOMS
#3
A room~
A room is here.~
0 1 2 3 4 5 6
M 7 8 9 X
> rand_prog 50~
say random
~
|
S
#0
#REPAIRS
4 1 2 3 120 1 0 23
0
#$
""",
        encoding="latin-1",
    )

    area_file = load_smaug(path)
    area_file.area.author = "A New Builder"
    area_file.area.climate = [3, 2, 1]
    area_file.area.mobs[1].programs[0].argument = "75"
    area_file.area.objects[2].action_description = "A changed action."
    area_file.area.rooms[3].maps[0].entry = "Y"
    area_file.area.repairs[0].profit_fix = 130

    reparsed = parse_rendered_smaug(tmp_path, area_file.dumps())

    assert reparsed.area == area_file.area
