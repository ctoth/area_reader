from pathlib import Path

import pytest

import area_reader.dialects.rom
import area_reader.model
from area_reader.native import NativeWriteError, render_record

ROM_CORPUS = tuple(sorted(Path("test/rom").glob("*.are")))
UPSTREAM_ROM_CORPUS = Path(r"C:\Users\Q\src\Rom24b6\area")


def load_rom(path: Path) -> area_reader.RomAreaFile:
    area_file = area_reader.RomAreaFile(path)
    area_file.load_sections()
    return area_file


def parse_rendered_rom(tmp_path: Path, text: str) -> area_reader.RomAreaFile:
    path = tmp_path / "rendered.are"
    path.write_text(text, encoding="latin-1")
    return load_rom(path)


@pytest.mark.parametrize("source_path", ROM_CORPUS, ids=lambda path: path.name)
def test_rom_corpus_has_semantic_and_canonical_fixed_points(
    tmp_path: Path,
    source_path: Path,
) -> None:
    source = load_rom(source_path)

    rendered = source.dumps()
    reparsed = parse_rendered_rom(tmp_path, rendered)

    assert len(reparsed.area.resets) == len(source.area.resets)
    for index, (actual, expected) in enumerate(zip(reparsed.area.resets, source.area.resets)):
        assert actual == expected, (index, actual, expected)
    assert reparsed.area == source.area
    assert reparsed.skipped_sections == source.skipped_sections
    assert reparsed.dumps() == rendered


def test_rom_corpus_round_trip_is_non_vacuous() -> None:
    areas = [load_rom(path).area for path in ROM_CORPUS]

    assert any(area.name for area in areas)
    assert sum(len(area.helps) for area in areas) > 0
    assert sum(len(area.rooms) for area in areas) > 0
    assert sum(len(area.mobs) for area in areas) > 0
    assert sum(len(area.objects) for area in areas) > 0
    assert sum(len(area.resets) for area in areas) > 0


def test_upstream_rom_corpus_has_semantic_fixed_point_when_available(
    tmp_path: Path,
) -> None:
    if not UPSTREAM_ROM_CORPUS.exists():
        pytest.skip("upstream ROM corpus is unavailable")

    paths = [path for path in sorted(UPSTREAM_ROM_CORPUS.glob("*.are")) if path.name != "proto.are"]
    assert paths
    for index, source_path in enumerate(paths):
        source = load_rom(source_path)
        rendered = source.dumps()
        output = tmp_path / f"{index}.are"
        output.write_text(rendered, encoding="latin-1")
        reparsed = load_rom(output)
        assert reparsed.area == source.area, source_path
        assert reparsed.skipped_sections == source.skipped_sections, source_path


def test_rom_write_uses_the_canonical_rendering(tmp_path: Path) -> None:
    source = load_rom(ROM_CORPUS[0])
    output = tmp_path / "written.are"

    source.write(output)

    assert output.read_text(encoding="latin-1") == source.dumps()
    assert load_rom(output).area == source.area


def test_rom_reset_preserves_if_flag_and_comment(tmp_path: Path) -> None:
    path = tmp_path / "reset.are"
    path.write_text(
        """#AREA
reset.are~
Reset test~
Builder~
1 1
#RESETS
M 7 1 2 1 3\t* keep this
S
#$
""",
        encoding="latin-1",
    )

    area_file = load_rom(path)
    reset = area_file.area.resets[0]

    assert reset.if_flag == 7
    assert reset.comment == "\t* keep this"
    assert parse_rendered_rom(tmp_path, area_file.dumps()).area.resets == [reset]


def test_rom_room_clan_is_part_of_the_model(tmp_path: Path) -> None:
    path = tmp_path / "clan.are"
    path.write_text(
        """#AREA
clan.are~
Clan test~
Builder~
1 1
#ROOMS
#1
Clan hall~
A hall.~
0 0 0
C builders~
S
#0
#$
""",
        encoding="latin-1",
    )

    area_file = load_rom(path)

    assert area_file.area.rooms[1].clan == "builders"
    assert area_file.as_dict()["rooms"][1]["clan"] == "builders"
    assert parse_rendered_rom(tmp_path, area_file.dumps()).area == area_file.area


def test_rom_shop_preserves_trailing_comment(tmp_path: Path) -> None:
    path = tmp_path / "shop.are"
    path.write_text(
        """#AREA
shop.are~
Shop test~
Builder~
1 1
#SHOPS
1 0 0 0 0 0 100 90 0 23\t* always open
0
#$
""",
        encoding="latin-1",
    )

    area_file = load_rom(path)

    assert area_file.area.shops[0].comment == "\t* always open"
    assert parse_rendered_rom(tmp_path, area_file.dumps()).area == area_file.area


def test_rom_unknown_sections_are_preserved_as_native_sections(
    tmp_path: Path,
) -> None:
    path = tmp_path / "native.are"
    path.write_text(
        """#AREA
native.are~
Native section test~
Builder~
1 1
#SOCIALS
wave wildly~
#$
""",
        encoding="latin-1",
    )

    area_file = load_rom(path)

    assert area_file.skipped_sections == [("socials", "\nwave wildly~\n")]
    reparsed = parse_rendered_rom(tmp_path, area_file.dumps())
    assert reparsed.skipped_sections == area_file.skipped_sections
    assert reparsed.area == area_file.area


def test_rom_mobprog_annotations_are_bidirectional(tmp_path: Path) -> None:
    path = tmp_path / "mobprog.txt"
    path.write_text("act_prog 123 greet~", encoding="latin-1")
    reader = area_reader.AreaFile(path)

    program = reader.read_object_by_fields(area_reader.dialects.rom.RomMobprog)

    assert program == area_reader.dialects.rom.RomMobprog(
        trig_type="act_prog",
        vnum=123,
        trig_phrase="greet",
    )
    assert render_record(program) == "M act_prog 123 greet~\n"


@pytest.mark.parametrize(
    "record",
    [
        area_reader.dialects.rom.RomItem(item_type="trash", value=[0, 0, 0, 0, 0], condition=57),
        area_reader.dialects.rom.RomArmorClass(pierce=7, bash=0, slash=0, exotic=0),
        area_reader.model.Exit(door=0, exit_info=area_reader.EXIT_FLAGS.CLOSED),
    ],
)
def test_rom_annotations_reject_unrepresentable_models(record: object) -> None:
    with pytest.raises(NativeWriteError):
        render_record(record)
