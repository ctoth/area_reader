import pytest

import area_reader.atlas
import area_reader.parser


def rom_exit(door, destination, description="", keyword="", locks=0, key=-1):
    return f"D{door}\n{description}~\n{keyword}~\n{locks} {key} {destination}\n"


def rom_room(vnum, name, *exits):
    return f"#{vnum}\n{name}~\nA room.\n~\n0 0 1\n{''.join(exits)}S\n"


def rom_mob(vnum, name, short_desc, *mprogs):
    programs = "".join(f"M {trigger} {program} {phrase}~\n" for trigger, program, phrase in mprogs)
    return (
        f"#{vnum}\n{name}~\n{short_desc}~\n{short_desc} is here.\n~\nA mob.\n~\nhuman~\n"
        "AB 0 0 0\n1 0 1d1+1 1d1+1 1d1+1 punch\n0 0 0 0\n0 0 0 0\n"
        f"stand stand none 0\n0 0 medium unknown\n{programs}"
    )


def rom_object(vnum, name, short_desc, item_type="trash", values="0 0 0 0 0"):
    return f"#{vnum}\n{name}~\n{short_desc}~\nIt lies here.~\nstuff~\n{item_type} 0 0\n{values}\n0 0 0 P\n"


def rom_area(name, first, last, rooms=(), mobs=(), objects=(), resets=(), shops=(), specials=(), programs=()):
    shop_lines = "".join(f"{keeper} 0 0 0 0 0 100 100 0 23\n" for keeper in shops)
    program_records = "".join(f"#{vnum}\n{code}~\n" for vnum, code in programs)
    return (
        f"#AREA\n{name}.are~\n{name.title()}~\n{{ 1  5}} Tester {name.title()}~\n{first} {last}\n"
        f"#MOBILES\n{''.join(mobs)}#0\n"
        f"#OBJECTS\n{''.join(objects)}#0\n"
        f"#ROOMS\n{''.join(rooms)}#0\n"
        f"#RESETS\n{''.join(line + chr(10) for line in resets)}S\n"
        f"#SHOPS\n{shop_lines}0\n"
        f"#SPECIALS\n{''.join(line + chr(10) for line in specials)}S\n"
        f"#MOBPROGS\n{program_records}#0\n"
        "#$\n"
    )


ALPHA_PROGRAM = "\n".join(
    [
        "mob transfer $n 201",
        "mob goto 9999",
        "mob mload 210",
        "mob oload 8888",
        "mob transfer $n",
        "mob at $n say hi",
        "say mob transfer $n 5",
    ]
)

ALPHA = rom_area(
    "alpha",
    100,
    199,
    rooms=[
        rom_room(
            100,
            "Alpha Square",
            rom_exit(0, 101),
            rom_exit(1, 200),
            rom_exit(5, -1, description="A painted trapdoor.", keyword="trapdoor"),
        ),
        rom_room(100 + 1, "Alpha Lane", rom_exit(2, 100), rom_exit(3, 102), rom_exit(0, 103, locks=1, key=250)),
        rom_room(102, "Alpha Pit"),
        rom_room(103, "Alpha Vault", rom_exit(2, 101), rom_exit(4, 999, locks=1, key=777)),
    ],
    mobs=[rom_mob(110, "alpha guard", "the Alpha guard", ("GREET", 500, "100"), ("SPEECH", 599, "hello"))],
    objects=[
        rom_object(150, "portal alpha", "an alpha portal", "portal", "0 0 0 300 0"),
        rom_object(151, "portal broken", "a broken portal", "portal", "0 0 0 7777 0"),
        rom_object(152, "portal dead", "a dead portal", "portal", "0 0 0 0 0"),
    ],
    resets=[
        "M 0 110 1 100 1",
        "G 0 250 0",
        "E 0 888 0 16",
        "O 0 150 0 102",
        "P 0 151 0 150 1",
        "P 0 151 0 4444 1",
        "D 0 101 0 2",
        "D 0 5555 0 1",
        "R 0 100 4",
        "M 0 6666 1 100 1",
        "M 0 210 1 3333 1",
    ],
    specials=["M 110 spec_guard", "M 6660 spec_thief"],
    programs=[(500, ALPHA_PROGRAM)],
)

BETA = rom_area(
    "beta",
    200,
    299,
    rooms=[
        rom_room(200, "Beta Gate", rom_exit(3, 100), rom_exit(0, 201)),
        rom_room(201, "Beta Hall", rom_exit(2, 200), rom_exit(1, 400)),
    ],
    mobs=[rom_mob(210, "beta keeper", "the Beta keeper", ("SPEECH", 500, "hi"))],
    objects=[rom_object(250, "key brass", "a brass key", "key")],
    resets=["M 0 210 1 200 1"],
    shops=[210, 666],
)

GAMMA = rom_area("gamma", 300, 399, rooms=[rom_room(300, "Gamma Cell", rom_exit(1, 100))])

DELTA = rom_area(
    "delta",
    400,
    499,
    rooms=[rom_room(400, "Delta Drop", rom_exit(0, 0))],
    mobs=[rom_mob(410, "delta ghost", "the Delta ghost", ("GREET", 501, "100"))],
    resets=["M 0 410 1 400 1"],
    programs=[(501, "mob transfer $n 100")],
)

NOTES = "#HELPS\n0 TOPIC~\nSome help.\n~\n0 $~\n#$\n"

EPSILON = rom_area(
    "epsilon",
    100,
    150,
    rooms=[rom_room(102, "Epsilon Copy"), rom_room(150, "Epsilon Edge")],
    mobs=[rom_mob(110, "epsilon guard", "the Epsilon guard")],
)


def write_areas(directory, **areas):
    for name, text in areas.items():
        (directory / f"{name}.are").write_text(text, encoding="ascii")
    return directory


@pytest.fixture
def world_dir(tmp_path):
    return write_areas(tmp_path, alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA, notes=NOTES)


@pytest.fixture
def world(world_dir):
    return area_reader.atlas.load([world_dir])


def by_file(rows):
    return {row["file"]: row for row in rows}


def test_load_expands_a_directory_to_its_area_files_in_name_order(world):
    assert [entry.label for entry in world.areas] == ["alpha.are", "beta.are", "delta.are", "gamma.are", "notes.are"]


def test_load_accepts_individual_files(world_dir):
    atlas = area_reader.atlas.load([world_dir / "gamma.are", world_dir / "alpha.are"])

    assert [entry.label for entry in atlas.areas] == ["gamma.are", "alpha.are"]
    assert sorted(atlas.rooms) == [100, 101, 102, 103, 300]


def test_load_lets_a_parse_error_propagate(world_dir):
    (world_dir / "broken.are").write_text("#AREA Metadata~\n#MOBILES\n#3000\nguard~\nA guard\n", encoding="ascii")

    with pytest.raises(area_reader.parser.ParseError, match="Unterminated string"):
        area_reader.atlas.load([world_dir])


def test_summary_counts_each_area(world):
    result = area_reader.atlas.summary(world)

    areas = by_file(result["areas"])
    assert areas["alpha.are"] == {
        "file": "alpha.are",
        "name": "Alpha",
        "room_vnums": [100, 103],
        "rooms": 4,
        "exits": 8,
        "mobs": 1,
        "objects": 3,
        "resets": 11,
        "shops": 0,
        "mob_programs": 1,
    }
    assert areas["beta.are"]["shops"] == 2
    assert areas["notes.are"]["rooms"] == 0
    assert areas["notes.are"]["room_vnums"] is None
    assert result["totals"] == {
        "files": 5,
        "rooms": 8,
        "exits": 14,
        "mobs": 3,
        "objects": 4,
        "resets": 13,
        "shops": 2,
        "mob_programs": 2,
    }
    assert result["areas_without_rooms"] == ["notes.are"]
    assert result["overlaps"] == {"rooms": [], "mobs": [], "objects": []}


def test_summary_reports_overlapping_vnum_ranges(tmp_path):
    atlas = area_reader.atlas.load([write_areas(tmp_path, alpha=ALPHA, beta=BETA, epsilon=EPSILON)])

    overlaps = area_reader.atlas.summary(atlas)["overlaps"]

    assert overlaps["rooms"] == [
        {
            "first": "alpha.are",
            "first_vnums": [100, 103],
            "second": "epsilon.are",
            "second_vnums": [102, 150],
            "shared_vnums": [102],
        }
    ]
    assert overlaps["mobs"] == [
        {
            "first": "alpha.are",
            "first_vnums": [110, 110],
            "second": "epsilon.are",
            "second_vnums": [110, 110],
            "shared_vnums": [110],
        }
    ]
    assert overlaps["objects"] == []


def test_find_matches_names_and_short_descriptions_case_insensitively(world):
    result = area_reader.atlas.find(world, "ALPHA")

    assert [(row["vnum"], row["name"], row["area"]) for row in result["rooms"]] == [
        (100, "Alpha Square", "alpha.are"),
        (101, "Alpha Lane", "alpha.are"),
        (102, "Alpha Pit", "alpha.are"),
        (103, "Alpha Vault", "alpha.are"),
    ]
    assert result["mobs"] == [
        {"vnum": 110, "name": "alpha guard", "short_desc": "the Alpha guard", "area": "alpha.are"}
    ]
    assert result["objects"] == [
        {"vnum": 150, "name": "portal alpha", "short_desc": "an alpha portal", "area": "alpha.are"}
    ]


def test_find_matches_the_short_description_alone(world):
    result = area_reader.atlas.find(world, "brass KEY")

    assert result["rooms"] == []
    assert result["mobs"] == []
    assert [row["vnum"] for row in result["objects"]] == [250]
