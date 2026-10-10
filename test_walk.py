from pathlib import Path

import pytest

import area_reader.atlas
import area_reader.cli
from area_reader import authoring, walk

EXAMPLE = Path("test/authoring/saltworks")
STOCK = Path("test/rom")
STOCK_AREAS = [
    path for path in sorted(STOCK.glob("*.are")) if path.name not in ("group.are", "help.are", "rom.are", "social.are")
]


@pytest.fixture(scope="module")
def saltworks(tmp_path_factory):
    root = tmp_path_factory.mktemp("walk")
    built = root / "saltworks.are"
    authoring.build(EXAMPLE, built)
    atlas = area_reader.atlas.load([built, STOCK / "midgaard.are"], "rom")
    return atlas


def text_of(atlas, **options):
    return "\n".join(walk.walk(atlas, atlas.areas[0], **options))


def test_walk_starts_at_the_room_that_leaves_the_area(saltworks) -> None:
    text = text_of(saltworks)

    assert "The walk starts at [1] The Shingle Causeway." in text
    assert "east: The Temple Of Mota (another area: midgaard.are)" in text


def test_walk_numbers_every_room_once(saltworks) -> None:
    area = saltworks.areas[0].area
    headings = [line for line in text_of(saltworks).splitlines() if line.startswith("## [")]

    assert len(headings) == len(area.rooms)
    assert [heading.split("]")[0] for heading in headings] == [f"## [{n}" for n in range(1, len(area.rooms) + 1)]


def test_walk_shows_doors_with_their_reset_state_and_key(saltworks) -> None:
    text = text_of(saltworks)

    assert 'east: [4] The Tally Office  [door "door oak", closed]' in text
    assert 'door "door iron", locked, key: the key to the salt store' in text


def test_walk_shows_look_only_exits_and_extras(saltworks) -> None:
    text = text_of(saltworks)

    assert "up: (cannot be walked; look only)" in text
    assert 'Look "tariff board figures":' in text


def test_walk_shows_who_is_in_a_room_and_what_they_have(saltworks) -> None:
    text = text_of(saltworks)

    assert "The gate warden leans on a boat-hook, counting carts." in text
    assert "wears on wield: a long boat-hook (weapon, level 10)" in text
    assert "carries: the key to the salt store (key, level 0)" in text
    assert "special: spec_guard" in text
    assert "program on greet '100':" in text


def test_walk_names_the_room_a_program_sends_someone_to(saltworks) -> None:
    area = saltworks.areas[0].area
    lines = [line for line in text_of(saltworks).splitlines() if "mob transfer $n" in line]

    assert lines
    for line in lines:
        vnum = int(line.split("mob transfer $n")[1].split()[0])
        assert f"<- {vnum} is [" in line
        assert line.rstrip().endswith(area.rooms[vnum].name)


def test_walk_shows_what_a_container_holds(saltworks) -> None:
    lines = text_of(saltworks).splitlines()
    inside = [position for position, line in enumerate(lines) if line.lstrip().startswith("inside: ")]

    assert inside
    assert all(lines[position].startswith("      ") for position in inside)


def test_anonymous_walk_leaves_out_the_credits(saltworks) -> None:
    assert "Credits:" in text_of(saltworks)
    assert "Credits:" not in text_of(saltworks, anonymous=True)
    assert "Claude" not in text_of(saltworks, anonymous=True).split("## [1]")[0]


def test_walk_from_another_room_lists_what_it_cannot_reach(tmp_path) -> None:
    built = tmp_path / "saltworks.are"
    authoring.build(EXAMPLE, built)
    atlas = area_reader.atlas.load([built], "rom")
    area = atlas.areas[0].area
    dead_end = next(vnum for vnum, room in area.rooms.items() if not room.exits or len(room.exits) == 1)

    text = text_of(atlas, start=dead_end)

    assert f"The walk starts at [1] {area.rooms[dead_end].name}." in text


@pytest.mark.parametrize("path", STOCK_AREAS, ids=lambda path: path.name)
def test_every_stock_area_can_be_walked(path) -> None:
    atlas = area_reader.atlas.load([path, *(other for other in STOCK_AREAS if other != path)], "rom")
    area = atlas.areas[0].area

    lines = walk.walk(atlas, atlas.areas[0])

    assert sum(1 for line in lines if line.startswith("## [")) == len(area.rooms)


def test_walk_command_prints_the_walk(saltworks, capsys) -> None:
    status = area_reader.cli.main(["walk", "--anonymous", str(saltworks.areas[0].path)])

    assert status == 0
    assert capsys.readouterr().out.startswith("# The Salt Works\n")
