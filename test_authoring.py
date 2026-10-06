import collections
import functools
import shutil
from pathlib import Path

import pytest

import area_reader.cli
import area_reader.dialects.rom
from area_reader import authoring
from area_reader.authoring import SourceError, tables
from area_reader.authoring.builder import first_difference, recommended
from area_reader.authoring.normal import reset_key
from area_reader.authoring.source import LOCK_NAME, load_yaml
from area_reader.constants import EXIT_FLAGS
from area_reader.model import Dice, Reset

ROM_CORPUS = tuple(sorted(Path("test/rom").glob("*.are")))
EXAMPLE = Path("test/authoring/saltworks")
HEADER = "area:\n  name: Test Area\n  levels: [1, 5]\n  vnums: {first: 100, size: 10}\n"
RESET_LETTERS = ("M", "O", "P", "G", "E", "D", "R")
# Every reset unbuild leaves raw over the stock set, and why.
STOCK_RAW_RESETS = {
    "arachnos.are": 6,  # a spider and its brood load in room 6134, which is not in the file
    "draconia.are": 5,  # one mob's E, E, G, E: worn and carried gear interleaved
    "grave.are": 1,  # a D reset for a door in midgaard
    "mahntor.are": 6,  # one mob's E, E, E, G, E
    "midgaard.are": 4,  # O resets into rooms of other areas
    "mirror.are": 7,  # one mob's G, E, G, G, G, G
    "newthalos.are": 1,  # an O reset whose if_flag is 1
    "sewer.are": 4,  # each of two doors is reset twice; the repeats stay raw
}


@functools.cache
def load_rom(path):
    area_file = area_reader.dialects.rom.RomAreaFile(path)
    area_file.load_sections()
    return area_file


@functools.cache
def unbuilt(path):
    area_file = load_rom(path)
    return authoring.unbuild(area_file.area, area_file.skipped_sections)


STOCK_AREAS = tuple(path for path in ROM_CORPUS if load_rom(path).area.rooms)


@pytest.fixture(scope="module", params=STOCK_AREAS, ids=lambda path: path.name)
def stock(request, tmp_path_factory):
    """A stock area, its source directory, and the area built from that directory."""
    path = request.param
    root = tmp_path_factory.mktemp(path.stem)
    authoring.write_files(root / "source", unbuilt(path))
    return load_rom(path).area, root / "source", authoring.build(root / "source", root / path.name)


def raw_resets(files):
    return (load_yaml(files.get("raw.yaml", ""), "raw.yaml") or {}).get("resets", [])


def group_keys(resets):
    return [tuple(reset_key(reset) for reset in group) for group in authoring.reset_groups(resets)]


def write_source(root, files):
    authoring.write_files(root, {"area.yaml": HEADER, **files})
    return root


def build_error(tmp_path, files):
    source = write_source(tmp_path / "source", files)
    with pytest.raises(SourceError) as caught:
        authoring.build(source, tmp_path / "out.are")
    error = caught.value
    assert error.file in str(error)
    assert error.key in str(error)
    return error


def copy_example(tmp_path):
    return shutil.copytree(EXAMPLE, tmp_path / "saltworks", ignore=shutil.ignore_patterns(LOCK_NAME))


@pytest.fixture(scope="module")
def saltworks(tmp_path_factory):
    root = tmp_path_factory.mktemp("example")
    return authoring.build(copy_example(root), root / "saltworks.are")


def vnum(built, family, identifier):
    return built.lock[family][identifier]


def exits(built, identifier):
    room = built.area.rooms[vnum(built, "rooms", identifier)]
    return {tables.DIRECTIONS[exit.door.value]: exit for exit in room.exits}


def resets_of(built, command):
    return [reset_key(reset) for reset in built.area.resets if reset.command == command]


def key(command, arg1, arg2, arg3=0, arg4=0):
    return reset_key(Reset(command, 1 if command in "PGE" else 0, arg1, arg2, arg3, arg4))


# The stock set: build(unbuild(x)) is x, modulo the declared normalizations.


def test_stock_area_round_trips_through_its_source_directory(stock) -> None:
    area, source, built = stock

    rebuilt, original = authoring.normalized(built.area), authoring.normalized(area)

    assert first_difference(rebuilt, original) is None
    assert rebuilt == original
    # Every record of an unbuilt area carries its vnum, so there is nothing to lock.
    assert not (source / LOCK_NAME).exists()


def test_stock_area_source_is_a_fixed_point(stock) -> None:
    _area, source, built = stock

    again = authoring.unbuild(built.area)

    assert set(again) == {path.name for path in source.iterdir()}
    for name, text in again.items():
        assert text == (source / name).read_text(encoding="utf-8"), name


def test_reset_grouping_loses_nothing(stock) -> None:
    area, _source, built = stock
    resets = [reset for reset in area.resets if reset.command is not None]
    position = {id(reset): index for index, reset in enumerate(resets)}

    groups = authoring.reset_groups(area.resets)

    # The groups partition the resets, each keeping the order its resets had in the file.
    assert sorted(position[id(reset)] for group in groups for reset in group) == list(range(len(resets)))
    for group in groups:
        assert [position[id(reset)] for reset in group] == sorted(position[id(reset)] for reset in group)
    # The built area has the same groups, the same number of times, each as one unbroken run.
    assert collections.Counter(group_keys(built.area.resets)) == collections.Counter(group_keys(area.resets))
    assert [reset for group in authoring.reset_groups(built.area.resets) for reset in group] == built.area.resets


def test_reset_comments_are_kept_only_on_raw_resets(stock) -> None:
    area, _source, built = stock
    raw = raw_resets(unbuilt(next(path for path in STOCK_AREAS if load_rom(path).area is area)))

    assert collections.Counter(reset.comment for reset in built.area.resets if reset.comment) == collections.Counter(
        record["comment"] for record in raw if "comment" in record
    )
    assert all(reset.command is not None for reset in built.area.resets)


def test_stock_round_trip_is_not_vacuous() -> None:
    areas = [load_rom(path).area for path in STOCK_AREAS]
    files = [unbuilt(path) for path in STOCK_AREAS]
    rooms = "".join(source.get("rooms.yaml", "") for source in files)
    mobs = "".join(source.get("mobs.yaml", "") for source in files)
    objects = "".join(source.get("objects.yaml", "") for source in files)

    assert len(areas) == 48
    # What the stock files hold.
    written = collections.Counter(reset.command for area in areas for reset in area.resets)
    kept_raw = collections.Counter(record["command"] for source in files for record in raw_resets(source))
    for letter in RESET_LETTERS:
        assert written[letter] - kept_raw[letter] > 0, letter
    all_exits = [exit for area in areas for room in area.rooms.values() for exit in room.exits]
    assert sum(1 for exit in all_exits if exit.exit_info & EXIT_FLAGS.ISDOOR) > 0
    assert sum(1 for exit in all_exits if exit.exit_info & EXIT_FLAGS.PICKPROOF) > 0
    assert sum(1 for exit in all_exits if exit.exit_info & EXIT_FLAGS.ISDOOR and exit.key > 0) > 0
    assert sum(len(area.shops) for area in areas) > 0
    assert sum(len(area.specials) for area in areas) > 0
    affects = [affect for area in areas for item in area.objects.values() for affect in item.affected]
    assert {affect.where for affect in affects} == {"TO_OBJECT", "TO_AFFECTS"}
    # And that the source directories say it in the friendly forms rather than raw.
    for phrase in (
        "door: closed",
        "door: locked",
        "door: reset_open",
        "door: open",
        "key: ",
        "pickproof: true",
        "oneway: true",
        "look: ",
        "wears:",
        "carries:",
        "contains:",
        "count: ",
        "max_in_world: ",
        "random_exits: ",
        "objects:",
    ):
        assert phrase in rooms, phrase
    for phrase in ("shop:", "special: spec_", "buys: [", "position: {start: "):
        assert phrase in mobs, phrase
    for phrase in ("{apply: hitroll, modifier: ", "{to: affects, bits: [", "weapon: {class: ", "container: {", "values: ["):
        assert phrase in objects, phrase
    assert {path.name: len(raw_resets(unbuilt(path))) for path in STOCK_AREAS if raw_resets(unbuilt(path))} == (
        STOCK_RAW_RESETS
    )


def test_unbuild_pins_vnums_and_slugs_ids_from_names() -> None:
    midgaard = next(path for path in STOCK_AREAS if path.name == "midgaard.are")
    files = unbuilt(midgaard)
    rooms = load_yaml(files["rooms.yaml"], "rooms.yaml")["rooms"]
    mobs = load_yaml(files["mobs.yaml"], "mobs.yaml")["mobs"]

    assert rooms["temple-of-mota"]["vnum"] == 3001
    assert rooms["temple-of-mota"]["exits"]["up"]["to"] == 3700
    assert rooms["temple-of-mota"]["exits"]["south"]["to"] == "temple-square"
    assert {"guildmaster", "guildmaster-2"} <= set(mobs)
    assert all("vnum" in record for record in (*rooms.values(), *mobs.values()))


def test_reset_groups_keep_dependent_resets_together() -> None:
    mob = Reset("M", 0, 10, 1, 100, 1)
    sword = Reset("E", 1, 20, -1, 16, 0)
    bag = Reset("G", 1, 21, -1, 0, 0)
    coin = Reset("P", 1, 22, -1, 21, 1)
    door = Reset("D", 0, 100, 1, 1, 0)
    chest = Reset("O", 0, 30, -1, 100, 0)
    other = Reset("M", 0, 11, 1, 100, 1)
    late = Reset("P", 1, 22, -1, 30, 1)
    stray = Reset("P", 1, 22, -1, 99, 1)
    comment = Reset(comment=" a note")

    groups = authoring.reset_groups([mob, sword, bag, coin, comment, door, chest, other, late, stray])

    assert groups == [[mob, sword, bag, coin], [door], [chest, late], [other], [stray]]


def test_unbuild_refuses_a_reset_that_regrouping_would_reattach(tmp_path: Path) -> None:
    path = tmp_path / "orphan.are"
    path.write_text(
        """#AREA
orphan.are~
Orphan~
{ 1  5} Test    Orphan~
100 109
#MOBILES
#0
#OBJECTS
#0
#ROOMS
#100
A room~
~
0 0 0
S
#0
#RESETS
G 1 100 -1
M 0 100 1 100 1
S
#$
""",
        encoding="latin-1",
    )

    with pytest.raises(SourceError, match="has no earlier reset to belong to"):
        authoring.unbuild(load_rom(path).area)


# The example area.


def test_example_area_is_split_across_files() -> None:
    source = authoring.load_source(EXAMPLE)

    assert source.rooms["causeway"][1].file.endswith("rooms/gate.yaml")
    assert source.rooms["yard"][1].file.endswith("rooms/works.yaml")
    assert len(source.rooms) == 10
    assert source.mobs["foreman"][1].file.endswith("mobs.yaml")


def test_example_area_lock_keeps_vnums_when_a_room_is_added(tmp_path: Path) -> None:
    source = copy_example(tmp_path)
    first = authoring.build(source, tmp_path / "first.are")

    assert (source / LOCK_NAME).read_text(encoding="utf-8") == (EXAMPLE / LOCK_NAME).read_text(encoding="utf-8")

    # "annex" sorts before every other room file, so it is defined first.
    authoring.write_files(source, {"rooms/annex.yaml": "rooms:\n  annex:\n    name: The Annex\n"})
    second = authoring.build(source, tmp_path / "second.are")

    for family in ("rooms", "mobs", "objects"):
        assert {identifier: second.lock[family][identifier] for identifier in first.lock[family]} == first.lock[family]
    assert second.lock["rooms"]["annex"] == 30010
    assert {number: room.name for number, room in first.area.rooms.items()}.items() <= {
        number: room.name for number, room in second.area.rooms.items()
    }.items()

    # Without the lock the new room takes the first number and every other room moves.
    (source / LOCK_NAME).unlink()
    unlocked = authoring.build(source, tmp_path / "unlocked.are")
    assert unlocked.lock["rooms"]["annex"] == 30000
    assert unlocked.lock["rooms"]["causeway"] != first.lock["rooms"]["causeway"]


def test_example_area_header(saltworks) -> None:
    area = saltworks.area

    assert area.header_format == "areadata"
    assert (area.name, area.original_filename, area.builders, area.security) == (
        "The Salt Works",
        "saltworks.are",
        "Claude",
        9,
    )
    assert area.metadata == "{ 5 15} Claude  The Salt Works"
    assert (area.first_vnum, area.last_vnum) == (30000, 30099)
    assert authoring.parse(saltworks.text).area == area
    assert saltworks.output.read_text(encoding="latin-1") == saltworks.text


def test_example_area_exits(saltworks) -> None:
    room = functools.partial(vnum, saltworks, "rooms")

    # A two-way exit written on one side.
    assert exits(saltworks, "gatehouse")["north"].destination == room("yard")
    assert exits(saltworks, "yard")["south"].destination == room("gatehouse")
    # One-way exits make nothing on the other side.
    assert exits(saltworks, "brine-pans")["down"].destination == room("outfall")
    assert "up" not in exits(saltworks, "outfall")
    assert exits(saltworks, "outfall")["east"].destination == room("causeway")
    assert "west" not in exits(saltworks, "causeway")
    # An exit into a stock area, by vnum.
    assert exits(saltworks, "causeway")["east"].destination == 3001
    # A look-only exit.
    look = exits(saltworks, "gatehouse")["up"]
    assert look.destination == -1
    assert look.description.startswith("The towers go up into the smoke.")
    assert look.description.endswith("burning in the western one.\n")


def test_example_area_doors(saltworks) -> None:
    room = functools.partial(vnum, saltworks, "rooms")
    doors = resets_of(saltworks, "D")

    office = exits(saltworks, "gatehouse")["east"]
    back = exits(saltworks, "tally-office")["west"]
    assert office.exit_info == back.exit_info == EXIT_FLAGS.ISDOOR
    assert (office.keyword, back.keyword) == ("door oak", "door oak")
    assert office.description == "A door of salt-bleached oak, its latch polished by hands.\n"
    assert back.description == "The gate tunnel lies beyond the door.\n"
    assert (office.key, back.key) == (-1, -1)
    assert key("D", room("gatehouse"), 1, 1) in doors
    assert key("D", room("tally-office"), 3, 1) in doors

    store = exits(saltworks, "yard")["east"]
    inside = exits(saltworks, "store")["west"]
    assert store.exit_info == inside.exit_info == EXIT_FLAGS.ISDOOR | EXIT_FLAGS.PICKPROOF
    assert store.key == inside.key == vnum(saltworks, "objects", "store-key")
    assert store.description != inside.description
    assert key("D", room("yard"), 1, 2) in doors
    assert key("D", room("store"), 3, 2) in doors
    assert len(doors) == 4


def test_example_area_rooms(saltworks) -> None:
    gatehouse = saltworks.area.rooms[vnum(saltworks, "rooms", "gatehouse")]
    boiling_house = saltworks.area.rooms[vnum(saltworks, "rooms", "boiling-house")]

    assert gatehouse.sector_type.name == "CITY"
    assert gatehouse.room_flags == tables.ROOM_FLAGS["indoors"] | tables.ROOM_FLAGS["law"]
    assert [extra.keyword for extra in gatehouse.extra_descriptions] == ["tariff board figures"]
    assert gatehouse.extra_descriptions[0].description.endswith("No credit.\n")
    assert gatehouse.description.endswith("onto the causeway.\n")
    assert (boiling_house.heal_rate, boiling_house.mana_rate) == (80, 100)


def test_example_area_mob_placements(saltworks) -> None:
    room = functools.partial(vnum, saltworks, "rooms")
    mob = functools.partial(vnum, saltworks, "mobs")
    item = functools.partial(vnum, saltworks, "objects")
    resets = [reset_key(reset) for reset in saltworks.area.resets]

    def after(load, count):
        index = resets.index(load)
        return resets[index + 1 : index + 1 + count]

    # A mob with equipment.
    warden = key("M", mob("gate-warden"), 1, room("gatehouse"), 1)
    assert after(warden, 2) == [key("E", item("boat-hook"), -1, 16), key("E", item("leather-apron"), -1, 5)]
    # A shopkeeper is given his stock.
    tallyman = key("M", mob("tallyman"), 1, room("tally-office"), 1)
    assert after(tallyman, 3) == [
        key("G", item("salt-fish"), -1),
        key("G", item("water-flask"), -1),
        key("G", item("tallow-lantern"), -1),
    ]
    shop = saltworks.area.shops[0]
    assert (shop.keeper, shop.buy_type) == (mob("tallyman"), [19, 17, 1, 0, 0])
    assert (shop.profit_buy, shop.profit_sell, shop.open_hour, shop.close_hour) == (120, 60, 6, 20)
    # count: 2 is two loads, each equipped, limited to the two.
    boiler = key("M", mob("salt-boiler"), 2, room("boiling-house"), 2)
    assert resets.count(boiler) == 2
    assert resets.count(key("E", item("leather-apron"), -1, 5)) == 3
    assert after(key("M", mob("foreman"), 1, room("yard"), 1), 1) == [key("G", item("store-key"), -1)]
    assert [(special.arg1, special.arg2) for special in saltworks.area.specials] == [
        (mob("gate-warden"), "spec_guard"),
        (mob("yard-dog"), "spec_fido"),
    ]


def test_example_area_object_placements(saltworks) -> None:
    room = functools.partial(vnum, saltworks, "rooms")
    item = functools.partial(vnum, saltworks, "objects")
    resets = [reset_key(reset) for reset in saltworks.area.resets]

    chest = resets.index(key("O", item("salt-chest"), -1, room("store")))
    # A container with contents; the block written twice is one reset loading two.
    assert resets[chest + 1 : chest + 3] == [
        key("P", item("coin-purse"), -1, item("salt-chest"), 1),
        key("P", item("salt-block"), -1, item("salt-chest"), 2),
    ]
    assert key("O", item("brine-pump"), -1, room("pump-house")) in resets
    assert key("O", item("salt-fish"), -1, room("drying-loft")) in resets


def test_example_area_objects(saltworks) -> None:
    def item(identifier):
        return saltworks.area.objects[vnum(saltworks, "objects", identifier)]

    hook = item("boat-hook")
    assert (hook.item_type, hook.value) == ("weapon", ["polearm", 2, 5, "pierce", tables.WEAPON_FLAGS["two_hands"]])
    assert hook.wear_flags == tables.WEAR_FLAGS["take"] | tables.WEAR_FLAGS["wield"]
    assert [extra.keyword for extra in hook.extra_descriptions] == ["hook boat-hook boathook"]

    apron = item("leather-apron")
    assert (apron.item_type, apron.value) == ("armor", [4, 5, 4, 1, 0])
    stat, resistance = apron.affected
    assert (stat.where, stat.location, stat.modifier, stat.level) == ("TO_OBJECT", tables.APPLIES["con"], 1, 6)
    assert (resistance.where, resistance.bitvector) == ("TO_RESIST", tables.IMM_FLAGS["fire"])

    chest = item("salt-chest")
    locked = tables.CONTAINER_FLAGS["closeable"] | tables.CONTAINER_FLAGS["closed"] | tables.CONTAINER_FLAGS["locked"]
    assert chest.value == [200, locked, vnum(saltworks, "objects", "store-key"), 100, 100]
    assert chest.wear_flags == 0

    assert (item("brine-pump").item_type, item("brine-pump").value) == ("fountain", [0, 0, "salt water", 0, 0])
    assert (item("water-flask").item_type, item("water-flask").value) == ("drink", [20, 20, "water", 0, 0])
    assert (item("tallow-lantern").item_type, item("tallow-lantern").value) == ("light", [0, 0, 48, 0, 0])
    assert (item("salt-fish").item_type, item("salt-fish").value) == ("food", [6, 8, 0, 0, 0])
    assert (item("coin-purse").item_type, item("coin-purse").value) == ("money", [240, 3, 0, 0, 0])
    assert (item("store-key").item_type, item("store-key").value) == ("key", [0, 0, 0, 0, 0])
    assert (item("salt-block").item_type, item("salt-block").value) == ("treasure", [0, 0, 0, 0, 0])


def test_example_area_mob_programs(saltworks) -> None:
    area = saltworks.area
    warden = area.mobs[vnum(saltworks, "mobs", "gate-warden")]
    foreman = area.mobs[vnum(saltworks, "mobs", "foreman")]

    (greet,) = warden.mprogs
    (speech,) = foreman.mprogs
    assert (greet.trig_type, greet.trig_phrase, greet.vnum) == ("greet", "100", 30000)
    assert (speech.trig_type, speech.trig_phrase, speech.vnum) == ("speech", "pans", 30001)
    # An inline program.
    assert area.mobprogs[greet.vnum].startswith("if ispc $n\n  say Carts to the yard")
    # A program from a file, with @room: replaced by the room's vnum.
    brine_pans = vnum(saltworks, "rooms", "brine-pans")
    assert area.mobprogs[speech.vnum].endswith(f"mob transfer $n {brine_pans}\n")
    assert "@room" not in saltworks.text
    assert "@room:brine-pans" in (EXAMPLE / "progs" / "foreman-pans.mprog").read_text(encoding="utf-8")


def test_example_area_defaulted_mob_stats(saltworks) -> None:
    area = saltworks.area
    boiler = area.mobs[vnum(saltworks, "mobs", "salt-boiler")]
    dog = area.mobs[vnum(saltworks, "mobs", "yard-dog")]
    tallyman = area.mobs[vnum(saltworks, "mobs", "tallyman")]
    foreman = area.mobs[vnum(saltworks, "mobs", "foreman")]

    # Rom2.4.doc Appendix A, level 8: 2d7+96, armor class 3, 1d7+2.
    assert (boiler.hit, boiler.damage) == (Dice(2, 7, 96), Dice(1, 7, 2))
    assert (boiler.ac.pierce, boiler.ac.bash, boiler.ac.slash, boiler.ac.exotic) == (30, 30, 30, 90)
    assert boiler.mana == Dice(4, 9, 100)
    assert (boiler.damtype, boiler.hitroll, boiler.material, boiler.size) == ("none", 0, "0", "medium")
    # Form and parts come from the race.
    assert boiler.form == tables.bits(tables.RACES["human"].form)
    assert (dog.form, dog.parts) == (tables.bits(tables.RACES["dog"].form), tables.bits(tables.RACES["dog"].parts))
    # A warrior reads its hit points one level higher: level 15's 3d9+208 for a level 14 mob.
    assert foreman.hit == Dice(3, 9, 208)
    # Written numbers are used as written.
    assert (tallyman.hit, tallyman.ac.exotic) == (Dice(3, 9, 333), 70)

    shown = {name: value for name, value, _origin in saltworks.defaults}
    assert shown["mobs.salt-boiler.hit"] == "2d7+96"
    assert shown["mobs.salt-boiler.mana"] == "4d9+100"
    assert "mobs.tallyman.hit" not in shown
    assert "mobs.tallyman.form" in shown


def test_example_area_help(saltworks) -> None:
    (entry,) = saltworks.area.helps

    assert (entry.level, entry.keyword) == (0, "SALTWORKS 'SALT WORKS'")
    assert entry.text.startswith("The Salt Works stand on the flats")


def test_example_area_unbuilds_to_a_source_that_builds_the_same_area(saltworks, tmp_path: Path) -> None:
    authoring.unbuild_file(saltworks.output, tmp_path / "source")
    again = authoring.build(tmp_path / "source", tmp_path / "again.are")

    assert authoring.normalized(again.area) == authoring.normalized(saltworks.area)
    assert load_yaml((tmp_path / "source" / "mobs.yaml").read_text(encoding="utf-8"), "mobs.yaml")["mobs"][
        "gate-warden"
    ]["programs"][0]["code"].startswith("if ispc $n")


def test_recommended_values_follow_the_rom_appendix() -> None:
    plain = tables.ACT_FLAGS["npc"]

    assert recommended(1, plain) == ("2d6+10", (9, 9, 9, 10), "1d4+0")
    assert recommended(30, plain) == ("6d12+853", (-9, -9, -9, 6), "4d6+8")
    assert recommended(60, plain) == ("50d10+9500", (-30, -30, -30, 0), "8d6+28")
    # A mage reads hit points and armor class one level lower and damage three lower; magic divisor 2.
    assert recommended(30, plain | tables.ACT_FLAGS["mage"]) == ("6d12+778", (-9, -9, -9, 1), "5d4+7")
    # Levels outside the table read its first and last rows.
    assert recommended(0, plain) == recommended(1, plain)
    assert recommended(75, plain) == recommended(60, plain)


def test_build_and_unbuild_commands(tmp_path: Path, capsys) -> None:
    source = copy_example(tmp_path)
    output = tmp_path / "saltworks.are"

    assert area_reader.cli.main(["build", str(source), "-o", str(output), "--show-defaults"]) == 0
    printed = capsys.readouterr().out
    assert "10 rooms, 5 mobs, 10 objects" in printed
    assert "mobs.salt-boiler.hit: 2d7+96  (Rom2.4.doc Appendix A, level 8)" in printed
    assert "mobs.yard-dog.form: [edible, animal, mammal]  (race dog)" in printed

    assert area_reader.cli.main(["unbuild", str(output), "-o", str(tmp_path / "unbuilt")]) == 0
    assert (tmp_path / "unbuilt" / "area.yaml").is_file()
    assert "rooms.yaml" in capsys.readouterr().out


def test_ids_of_another_source_area_are_referenced_by_its_directory_name(tmp_path: Path) -> None:
    write_source(tmp_path / "there", {"rooms.yaml": "rooms:\n  quay:\n    name: The Quay\n    vnum: 107\n"})
    here = write_source(
        tmp_path / "here", {"rooms.yaml": "rooms:\n  lane:\n    name: The Lane\n    exits:\n      east: there:quay\n"}
    )

    built = authoring.build(here, tmp_path / "here.are", sets=[tmp_path / "there"])

    (east,) = built.area.rooms[100].exits
    assert east.destination == 107
    assert build_error(tmp_path / "unset", {"rooms.yaml": "rooms:\n  lane:\n    name: Lane\n    exits:\n      east: there:quay\n"}).key == (
        "rooms.lane.exits.east"
    )


def test_included_file_is_merged(tmp_path: Path) -> None:
    authoring.write_files(tmp_path / "shared", {"mobs.yaml": "mobs:\n  rat:\n    keywords: rat\n    short: a rat\n    long: A rat.\n    race: unique\n    level: 1\n"})
    source = write_source(tmp_path / "source", {"rooms.yaml": "include: [../shared/mobs.yaml]\nrooms:\n  hall:\n    name: Hall\n    mobs: [rat]\n"})

    built = authoring.build(source, tmp_path / "out.are")

    assert [reset.command for reset in built.area.resets] == ["M"]
    assert built.area.mobs[100].short_desc == "a rat"


# Errors: each names the file and the key path.

RAT = "mobs:\n  rat:\n    keywords: rat\n    short: a rat\n    long: A rat.\n    race: unique\n    level: 1\n"


def test_error_unknown_id(tmp_path: Path) -> None:
    error = build_error(
        tmp_path,
        {
            "rooms.yaml": "rooms:\n  gatehouse:\n    name: The Gatehouse\n    exits:\n"
            "      east: {to: gatehouse, oneway: true, door: locked, key: guardroom-key}\n"
        },
    )

    assert error.file.endswith("source/rooms.yaml")
    assert error.key == "rooms.gatehouse.exits.east.key"
    assert "unknown object id 'guardroom-key'" in error.reason


def test_error_duplicate_id_across_files(tmp_path: Path) -> None:
    error = build_error(
        tmp_path,
        {"a/keep.yaml": "rooms:\n  hall:\n    name: Hall\n", "b/yard.yaml": "rooms:\n  hall:\n    name: Other hall\n"},
    )

    assert error.file.endswith("source/b/yard.yaml")
    assert error.key == "rooms.hall"
    assert "source/a/keep.yaml" in error.reason


def test_error_duplicate_id_in_one_file(tmp_path: Path) -> None:
    error = build_error(tmp_path, {"rooms.yaml": "rooms:\n  hall:\n    name: Hall\n  hall:\n    name: Other hall\n"})

    assert error.file.endswith("source/rooms.yaml")
    assert "'hall' is written twice (line 4)" in error.reason


def test_error_unknown_flag_name(tmp_path: Path) -> None:
    error = build_error(tmp_path, {"rooms.yaml": "rooms:\n  hall:\n    name: Hall\n    flags: [indoors, cosy]\n"})

    assert error.file.endswith("source/rooms.yaml")
    assert error.key == "rooms.hall.flags.1"
    assert "unknown flag name 'cosy'" in error.reason
    assert "no_recall" in error.reason


def test_error_exit_pair_disagreement(tmp_path: Path) -> None:
    error = build_error(
        tmp_path,
        {
            "rooms.yaml": "rooms:\n  hall:\n    name: Hall\n    exits:\n      east: {to: cell, door: closed}\n"
            "  cell:\n    name: Cell\n    exits:\n      west: hall\n"
        },
    )

    assert error.file.endswith("source/rooms.yaml")
    assert error.key == "rooms.hall.exits.east"
    assert "rooms.cell.exits.west" in error.reason
    assert "agree on destination, door and key" in error.reason


def test_error_vnum_block_exhausted(tmp_path: Path) -> None:
    rooms = "".join(f"  room-{letter}:\n    name: Room\n" for letter in "abcdefghijk")
    error = build_error(tmp_path, {"rooms.yaml": "rooms:\n" + rooms})

    assert error.file.endswith("source/rooms.yaml")
    assert error.key == "rooms.room-k"
    assert "100..109 is exhausted" in error.reason


def test_error_tilde_in_text(tmp_path: Path) -> None:
    error = build_error(tmp_path, {"rooms.yaml": "rooms:\n  hall:\n    name: Hall\n    description: About ~40 paces.\n"})

    assert error.file.endswith("source/rooms.yaml")
    assert error.key == "rooms.hall.description"
    assert "'~'" in error.reason


def test_error_unknown_item_type(tmp_path: Path) -> None:
    error = build_error(tmp_path, {"objects.yaml": "objects:\n  thing:\n    keywords: thing\n    short: a thing\n    type: gizmo\n"})

    assert error.file.endswith("source/objects.yaml")
    assert error.key == "objects.thing.type"
    assert "unknown item type 'gizmo'" in error.reason


def test_error_wrong_wear_location(tmp_path: Path) -> None:
    error = build_error(
        tmp_path,
        {
            "mobs.yaml": RAT,
            "rooms.yaml": "rooms:\n  hall:\n    name: Hall\n    mobs:\n      - mob: rat\n        wears: {tail: 3001}\n",
        },
    )

    assert error.file.endswith("source/rooms.yaml")
    assert error.key == "rooms.hall.mobs.0.wears.tail"
    assert "wield" in error.reason


def test_error_bad_dice(tmp_path: Path) -> None:
    error = build_error(tmp_path, {"mobs.yaml": RAT + "    hit: plenty\n"})

    assert error.file.endswith("source/mobs.yaml")
    assert error.key == "mobs.rat.hit"
    assert "NdS+B" in error.reason


def test_error_unknown_key(tmp_path: Path) -> None:
    error = build_error(tmp_path, {"rooms.yaml": "rooms:\n  hall:\n    name: Hall\n    desciption: A hall.\n"})

    assert error.key == "rooms.hall.desciption"
    assert "unknown key" in error.reason


def test_error_character_outside_latin_1(tmp_path: Path) -> None:
    error = build_error(tmp_path, {"rooms.yaml": "rooms:\n  hall:\n    name: The Mage’s Hall\n"})

    assert error.key == "rooms.hall.name"
    assert "U+2019" in error.reason


def test_error_two_exits_into_one_slot(tmp_path: Path) -> None:
    error = build_error(
        tmp_path,
        {
            "rooms.yaml": "rooms:\n  hall:\n    name: Hall\n    exits: {east: cell}\n"
            "  yard:\n    name: Yard\n    exits: {east: cell}\n  cell:\n    name: Cell\n"
        },
    )

    assert error.key == "rooms.yard.exits.east"
    assert "oneway" in error.reason


def test_build_fails_when_the_reader_parses_something_else_back(tmp_path: Path) -> None:
    # A raw reset's comment is written straight after its last number, so this one reads back as M ... 17.
    source = write_source(
        tmp_path / "source",
        {"raw.yaml": "resets:\n  - {command: M, arg1: 3000, arg2: 1, arg3: 3001, arg4: 1, comment: 7 dwarves}\n"},
    )

    with pytest.raises(SourceError, match="does not read back as it was written"):
        authoring.build(source, tmp_path / "out.are")
    assert not (tmp_path / "out.are").exists()
