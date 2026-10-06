import json

import pytest

import area_reader.atlas
import area_reader.cli
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


ALPHA_PROGRAM = """mob transfer $n 201
mob goto 9999
mob mload 210
mob oload 8888
mob transfer $n
mob at $n say hi
say mob transfer $n 5"""

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


def vnums(rows):
    return [row["vnum"] for row in rows]


def test_reach_walks_exits_only_by_default(world):
    result = area_reader.atlas.reach(world, 100)

    assert result["start"] == {"vnum": 100, "name": "Alpha Square", "area": "alpha.are"}
    assert result["links"] == ["exits"]
    assert result["totals"] == {"rooms": 8, "reachable": 7, "can_return": 6, "both": 5}
    assert result["areas"] == [
        {"file": "alpha.are", "rooms": 4, "reachable": 4, "can_return": 3, "both": 3},
        {"file": "beta.are", "rooms": 2, "reachable": 2, "can_return": 2, "both": 2},
        {"file": "delta.are", "rooms": 1, "reachable": 1, "can_return": 0, "both": 0},
        {"file": "gamma.are", "rooms": 1, "reachable": 0, "can_return": 1, "both": 0},
    ]
    assert result["areas_not_reached"] == ["gamma.are"]
    assert result["areas_nothing_leads_into"] == ["gamma.are"]
    assert result["areas_with_no_way_out"] == ["delta.are"]
    assert result["areas_without_rooms"] == ["notes.are"]
    assert result["unreachable_rooms"] == [{"vnum": 300, "name": "Gamma Cell", "area": "gamma.are"}]
    assert vnums(result["no_return_rooms"]) == [102, 400]
    assert "walking_totals" not in result


def test_reach_with_portals_follows_portals_placed_in_rooms(world):
    result = area_reader.atlas.reach(world, 100, portals=True)

    assert result["links"] == ["exits", "portals"]
    assert result["totals"] == {"rooms": 8, "reachable": 8, "can_return": 7, "both": 7}
    assert result["walking_totals"] == {"rooms": 8, "reachable": 7, "can_return": 6, "both": 5}
    assert vnums(result["gained"]["reachable"]) == [300]
    assert vnums(result["gained"]["can_return"]) == [102]
    assert result["extra_links"] == [{"from": 102, "to": 300, "via": "portal 150"}]
    assert result["areas_not_reached"] == []
    assert result["areas_nothing_leads_into"] == []


def test_reach_with_progs_follows_transfers_from_the_room_a_mob_resets_in(world):
    result = area_reader.atlas.reach(world, 100, progs=True)

    assert result["links"] == ["exits", "programs"]
    assert result["totals"] == {"rooms": 8, "reachable": 7, "can_return": 7, "both": 6}
    assert result["gained"] == {
        "reachable": [],
        "can_return": [{"vnum": 400, "name": "Delta Drop", "area": "delta.are"}],
    }
    assert result["extra_links"] == [
        {"from": 100, "to": 201, "via": "program 500"},
        {"from": 200, "to": 201, "via": "program 500"},
        {"from": 400, "to": 100, "via": "program 501"},
    ]
    assert result["areas_with_no_way_out"] == []


def test_reach_from_a_room_outside_the_set_reaches_nothing(world):
    result = area_reader.atlas.reach(world, 4242)

    assert result["start"] == {"vnum": 4242, "name": None, "area": None}
    assert result["totals"] == {"rooms": 8, "reachable": 0, "can_return": 0, "both": 0}


def test_links_lists_the_area_graph(world):
    result = area_reader.atlas.links(world)

    areas = by_file(result["areas"])
    assert list(areas) == ["alpha.are", "beta.are", "delta.are", "gamma.are"]
    assert areas["alpha.are"]["to"] == [
        {"area": "beta.are", "exits": 1, "room_pairs": [{"from": 100, "direction": "east", "to": 200}]}
    ]
    assert [(link["area"], link["exits"]) for link in areas["alpha.are"]["from"]] == [
        ("beta.are", 1),
        ("gamma.are", 1),
    ]
    assert [(link["area"], link["exits"]) for link in areas["beta.are"]["to"]] == [("alpha.are", 1), ("delta.are", 1)]
    assert areas["delta.are"]["to"] == []
    assert areas["gamma.are"]["from"] == []
    assert result["one_way"] == [
        {"from": "beta.are", "to": "delta.are", "exits": 1},
        {"from": "gamma.are", "to": "alpha.are", "exits": 1},
    ]


def test_path_returns_the_shortest_exit_path(world):
    result = area_reader.atlas.path(world, 300, 201)

    assert result["missing"] == []
    assert result["steps"] == [
        {"vnum": 300, "name": "Gamma Cell", "area": "gamma.are", "direction": "east"},
        {"vnum": 100, "name": "Alpha Square", "area": "alpha.are", "direction": "east"},
        {"vnum": 200, "name": "Beta Gate", "area": "beta.are", "direction": "north"},
        {"vnum": 201, "name": "Beta Hall", "area": "beta.are", "direction": None},
    ]


def test_path_from_a_room_to_itself_is_one_step(world):
    assert area_reader.atlas.path(world, 100, 100)["steps"] == [
        {"vnum": 100, "name": "Alpha Square", "area": "alpha.are", "direction": None}
    ]


def test_path_reports_no_path(world):
    result = area_reader.atlas.path(world, 100, 300)

    assert result["steps"] is None
    assert result["missing"] == []


def test_path_can_use_portals(world):
    result = area_reader.atlas.path(world, 101, 300, portals=True)

    assert [(step["vnum"], step["direction"]) for step in result["steps"]] == [
        (101, "west"),
        (102, "portal 150"),
        (300, None),
    ]


def test_path_names_rooms_missing_from_the_set(world):
    result = area_reader.atlas.path(world, 100, 4242)

    assert result["steps"] is None
    assert result["missing"] == [4242]


def references(result, kind):
    return [(reference["area"], reference["vnum"]) for reference in result["references"][kind]]


def test_dangling_lists_references_to_vnums_no_file_defines(world):
    result = area_reader.atlas.dangling(world)

    assert references(result, "exit_destination") == [("alpha.are", 999)]
    assert references(result, "exit_key") == [("alpha.are", 777)]
    assert references(result, "reset_mob") == [("alpha.are", 6666)]
    assert references(result, "reset_object") == [("alpha.are", 888)]
    assert references(result, "reset_container") == [("alpha.are", 4444)]
    assert references(result, "reset_room") == [("alpha.are", 5555), ("alpha.are", 3333)]
    assert references(result, "shop_keeper") == [("beta.are", 666)]
    assert references(result, "special_mob") == [("alpha.are", 6660)]
    assert references(result, "mob_program") == [("alpha.are", 599)]
    assert references(result, "portal_destination") == [("alpha.are", 7777)]
    assert references(result, "program_room") == [("alpha.are", 9999)]
    assert references(result, "program_mob") == []
    assert references(result, "program_object") == [("alpha.are", 8888)]
    assert result["counts"]["reset_room"] == 2
    assert result["counts"]["program_mob"] == 0
    assert result["references"]["exit_destination"][0]["where"] == "room 103 up"
    assert result["references"]["program_room"][0]["where"] == "program 500 line 2: mob goto 9999"


def test_dangling_describes_exits_without_a_destination(world):
    result = area_reader.atlas.dangling(world)["exits_without_destination"]

    assert {key: result[key] for key in ("count", "with_description", "with_keyword", "with_neither")} == {
        "count": 2,
        "with_description": 1,
        "with_keyword": 1,
        "with_neither": 1,
    }
    assert result["exits"] == [
        {
            "area": "alpha.are",
            "room": 100,
            "direction": "down",
            "destination": -1,
            "description": "A painted trapdoor.",
            "keyword": "trapdoor",
        },
        {"area": "delta.are", "room": 400, "direction": "north", "destination": 0, "description": "", "keyword": ""},
    ]


def test_dangling_reports_what_it_did_not_resolve(world):
    result = area_reader.atlas.dangling(world)

    assert result["portals_without_destination"] == [{"area": "alpha.are", "vnum": 152, "destination": 0}]
    assert result["program_lines_skipped"] == [
        {"area": "alpha.are", "program": 500, "line": 5, "text": "mob transfer $n", "reason": "no vnum argument"},
        {
            "area": "alpha.are",
            "program": 500,
            "line": 6,
            "text": "mob at $n say hi",
            "reason": "argument is not a bare integer",
        },
    ]


def test_depends_counts_references_resolved_by_another_area(world):
    result = area_reader.atlas.depends(world)

    areas = by_file(result["areas"])
    assert list(areas) == ["alpha.are", "beta.are", "delta.are", "gamma.are", "notes.are"]
    assert areas["alpha.are"]["needs"] == [
        {
            "area": "beta.are",
            "counts": {
                "exit_destination": 1,
                "exit_key": 1,
                "reset_mob": 1,
                "reset_object": 1,
                "program_room": 1,
                "program_mob": 1,
            },
            "vnums": {
                "exit_destination": [200],
                "exit_key": [250],
                "reset_mob": [210],
                "reset_object": [250],
                "program_room": [201],
                "program_mob": [210],
            },
        },
        {"area": "gamma.are", "counts": {"portal_destination": 1}, "vnums": {"portal_destination": [300]}},
    ]
    assert areas["beta.are"]["needs"] == [
        {
            "area": "alpha.are",
            "counts": {"exit_destination": 1, "mob_program": 1},
            "vnums": {"exit_destination": [100], "mob_program": [500]},
        },
        {"area": "delta.are", "counts": {"exit_destination": 1}, "vnums": {"exit_destination": [400]}},
    ]
    assert areas["delta.are"]["needs"] == [
        {"area": "alpha.are", "counts": {"program_room": 1}, "vnums": {"program_room": [100]}}
    ]
    assert areas["notes.are"]["needs"] == []


def run(capsys, *arguments):
    assert area_reader.cli.main(["atlas", *map(str, arguments)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    return captured.out


def test_cli_summary_prints_text(world_dir, capsys):
    lines = run(capsys, "summary", world_dir).splitlines()

    assert (
        "alpha.are: Alpha. Room vnums 100 to 103. 4 rooms, 8 exits, 1 mobs, 3 objects, 11 resets, 0 shops, "
        "1 mob programs."
    ) in lines
    assert (
        "notes.are: (no name). No rooms. 0 rooms, 0 exits, 0 mobs, 0 objects, 0 resets, 0 shops, 0 mob programs."
        in lines
    )
    assert "Totals: 5 files, 8 rooms, 14 exits, 3 mobs, 4 objects, 13 resets, 2 shops, 2 mob programs." in lines
    assert "Files without rooms: notes.are" in lines
    assert "Overlapping rooms vnum ranges: none" in lines


def test_cli_summary_prints_overlaps(tmp_path, capsys):
    write_areas(tmp_path, alpha=ALPHA, epsilon=EPSILON)

    lines = run(capsys, "summary", tmp_path).splitlines()

    assert "Overlapping rooms vnum ranges: 1" in lines
    assert "  alpha.are 100 to 103 and epsilon.are 102 to 150; both define: 102" in lines


def test_cli_json_is_the_question_result(world_dir, world, capsys):
    assert json.loads(run(capsys, "summary", "--json", world_dir)) == area_reader.atlas.summary(world)
    assert json.loads(run(capsys, "dangling", "--json", world_dir)) == area_reader.atlas.dangling(world)
    assert json.loads(run(capsys, "depends", "--json", world_dir)) == area_reader.atlas.depends(world)
    assert json.loads(run(capsys, "find", "--json", "alpha", world_dir)) == area_reader.atlas.find(world, "alpha")
    assert json.loads(run(capsys, "path", "--json", "300", "201", world_dir)) == area_reader.atlas.path(world, 300, 201)


def test_cli_accepts_several_files(world_dir, capsys):
    result = json.loads(run(capsys, "summary", "--json", world_dir / "beta.are", world_dir / "alpha.are"))

    assert [row["file"] for row in result["areas"]] == ["beta.are", "alpha.are"]


def test_cli_reach_prints_counts_and_keeps_room_lists_behind_a_flag(world_dir, capsys):
    lines = run(capsys, "reach", "--from", "100", world_dir).splitlines()

    assert lines[0] == "From room 100 Alpha Square (alpha.are), following exits."
    assert "Rooms: 8. Reachable: 7. Can walk back: 6. Both: 5." in lines
    assert "delta.are: 1 rooms, 1 reachable, 0 can walk back, 0 both." in lines
    assert "Areas with no room reachable: gamma.are" in lines
    assert "Areas nothing leads into: gamma.are" in lines
    assert "Areas with no way out: delta.are" in lines
    assert "Files without rooms: notes.are" in lines
    assert "Unreachable rooms: 1 (list them with --rooms)" in lines
    assert "No-return rooms (reachable, cannot walk back): 2 (list them with --rooms)" in lines
    assert not any("Gamma Cell" in line for line in lines)

    lines = run(capsys, "reach", "--from", "100", "--rooms", world_dir).splitlines()

    assert "Unreachable rooms: 1" in lines
    assert "  300 Gamma Cell (gamma.are)" in lines
    assert "  102 Alpha Pit (alpha.are)" in lines


def test_cli_reach_json_keeps_room_lists_behind_the_flag(world_dir, world, capsys):
    result = json.loads(run(capsys, "reach", "--from", "100", "--json", world_dir))

    assert "unreachable_rooms" not in result
    assert "no_return_rooms" not in result
    assert result["totals"] == {"rooms": 8, "reachable": 7, "can_return": 6, "both": 5}
    assert json.loads(run(capsys, "reach", "--from", "100", "--json", "--rooms", world_dir)) == area_reader.atlas.reach(
        world, 100
    )


def test_cli_reach_shows_what_non_walking_links_add(world_dir, capsys):
    lines = run(capsys, "reach", "--from", "100", "--with-portals", "--with-progs", "--rooms", world_dir).splitlines()

    assert lines[0] == "From room 100 Alpha Square (alpha.are), following exits, portals and programs."
    assert "Rooms: 8. Reachable: 8. Can walk back: 8. Both: 8." in lines
    assert "Exits only: Reachable: 7. Can walk back: 6. Both: 5." in lines
    assert "Rooms gained as reachable: 1" in lines
    assert "Rooms gained as able to walk back: 2" in lines
    assert "Links added: 4" in lines
    assert "  102 to 300 by portal 150" in lines
    assert "  400 to 100 by program 501" in lines


def test_cli_reach_from_a_room_outside_the_set(world_dir, capsys):
    lines = run(capsys, "reach", "--from", "4242", world_dir).splitlines()

    assert lines[0] == "Room 4242 is not in the set."


def test_cli_links_prints_the_area_graph(world_dir, capsys):
    lines = run(capsys, "links", world_dir).splitlines()

    assert "alpha.are" in lines
    assert "  to beta.are: 1 exits" in lines
    assert "  from gamma.are: 1 exits" in lines
    assert "delta.are" in lines
    assert "  to no other area" in lines
    assert "One-way area links: 2" in lines
    assert "  beta.are to delta.are: 1 exits, none back" in lines
    assert not any("100 east to 200" in line for line in lines)

    lines = run(capsys, "links", "--rooms", world_dir).splitlines()

    assert "    100 east to 200" in lines


def test_cli_links_json_keeps_room_pairs_behind_the_flag(world_dir, world, capsys):
    result = json.loads(run(capsys, "links", "--json", world_dir))

    assert result["areas"][0]["to"] == [{"area": "beta.are", "exits": 1}]
    assert json.loads(run(capsys, "links", "--json", "--rooms", world_dir)) == area_reader.atlas.links(world)


def test_cli_path_prints_each_step(world_dir, capsys):
    assert run(capsys, "path", "300", "201", world_dir).splitlines() == [
        "Path from 300 to 201: 3 moves.",
        "300 Gamma Cell (gamma.are), go east",
        "100 Alpha Square (alpha.are), go east",
        "200 Beta Gate (beta.are), go north",
        "201 Beta Hall (beta.are)",
    ]


def test_cli_path_states_that_there_is_none(world_dir, capsys):
    assert run(capsys, "path", "100", "300", world_dir) == "No path from 100 to 300.\n"
    assert run(capsys, "path", "100", "4242", world_dir) == "No path from 100 to 4242: room 4242 is not in the set.\n"


def test_cli_find_prints_matches(world_dir, capsys):
    assert run(capsys, "find", "guard", world_dir).splitlines() == [
        "Rooms: 0",
        "Mobs: 1",
        "  110 the Alpha guard [alpha guard] (alpha.are)",
        "Objects: 0",
    ]


def test_cli_dangling_prints_each_kind(world_dir, capsys):
    lines = run(capsys, "dangling", world_dir).splitlines()

    assert "exit_destination: 1" in lines
    assert "  alpha.are: room 103 up refers to 999" in lines
    assert "program_mob: 0" in lines
    assert (
        "Exits with a destination of 0 or less: 2. With a description: 1. With a keyword: 1. With neither: 1." in lines
    )
    assert "  alpha.are: room 100 down, destination -1, description 'A painted trapdoor.', keyword 'trapdoor'" in lines
    assert "Portals without a fixed destination: 1" in lines
    assert "  alpha.are: object 152, destination 0" in lines
    assert "Program lines not read as a vnum: 2" in lines
    assert "  alpha.are: program 500 line 5: mob transfer $n (no vnum argument)" in lines


def test_cli_depends_prints_what_each_area_needs(world_dir, capsys):
    lines = run(capsys, "depends", world_dir).splitlines()

    assert "delta.are needs alpha.are: program_room 1 (100)" in lines
    assert "alpha.are needs gamma.are: portal_destination 1 (300)" in lines
    assert "gamma.are needs alpha.are: exit_destination 1 (100)" in lines
    assert "notes.are needs no other area." in lines


def test_cli_lets_a_parse_error_propagate(world_dir):
    (world_dir / "broken.are").write_text("#AREA Metadata~\n#MOBILES\n#3000\nguard~\nA guard\n", encoding="ascii")

    with pytest.raises(area_reader.parser.ParseError, match="Unterminated string"):
        area_reader.cli.main(["atlas", "summary", str(world_dir)])


def test_cli_without_atlas_still_prints_one_area_as_json(world_dir, capsys):
    assert area_reader.cli.main([str(world_dir / "gamma.are")]) == 0

    assert list(json.loads(capsys.readouterr().out)["rooms"]) == ["300"]
