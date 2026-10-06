import copy
import json
from collections import Counter

import pytest

import area_reader.atlas
import area_reader.cli
import area_reader.lint

SQUARE = "The cobbles of the square are swept clean and the fountain at its heart\nruns clear over pale stone.\n"
VAULT = "Iron shelves line the walls of this dry little vault, each one labelled\nin a careful clerk's hand.\n"
SHOP = "Bolts of cloth and coils of rope hang from pegs above a long counter\nworn smooth by many elbows.\n"
GREETING = "if ispc $n\n  say Welcome.\n  mob echo The guard nods.\nelse\n  mob echoat $n The guard stares.\nendif\n"


def way(door, destination, locks=0, key=-1, description=""):
    return {"door": door, "destination": destination, "locks": locks, "key": key, "description": description}


def room(name, description, exits=(), flags="0"):
    return {"name": name, "description": description, "exits": list(exits), "flags": flags}


def mob(name, short_desc, long_desc, description, **fields):
    record = {
        "name": name,
        "short_desc": short_desc,
        "long_desc": long_desc,
        "description": description,
        "race": "human",
        "level": 3,
        "hit": "2d6+35",
        "damage": "1d6+0",
        "damtype": "punch",
        "ac": 7,
        "start_pos": "stand",
        "default_pos": "stand",
        "sex": "male",
        "size": "medium",
        "programs": [],
    }
    record.update(fields)
    return record


def item(name, short_desc, description, item_type="trash", values="0 0 0 0 0", level=0):
    return {
        "name": name,
        "short_desc": short_desc,
        "description": description,
        "item_type": item_type,
        "values": values,
        "level": level,
    }


def tidy():
    """An area no rule fires on."""
    return {
        "name": "tidy",
        "credits": "{ 1  5} Tester Tidy",
        "first": 100,
        "last": 199,
        "rooms": {
            100: room("Tidy Square", SQUARE, [way(0, 101, locks=1, key=150), way(1, 102)]),
            101: room("Tidy Vault", VAULT, [way(2, 100, locks=1, key=150)]),
            102: room("Tidy Shop", SHOP, [way(3, 100)]),
        },
        "mobs": {
            110: mob(
                "guard tidy",
                "the tidy guard",
                "A tidy guard stands here.\n",
                "He looks neat and alert.\n",
                programs=[("GREET", 120, "100")],
            ),
            111: mob("clerk", "the clerk", "A clerk waits behind the counter.\n", "She is counting coins.\n"),
        },
        "objects": {
            150: item("key brass", "a brass key", "A brass key lies here.", "key"),
            151: item("sword short", "a short sword", "A short sword lies here.", "weapon", "sword 1 6 slash 0", 3),
            152: item("waterskin skin", "a waterskin", "A waterskin lies here.", "drink", "10 10 'water' 0 0"),
            153: item("chest oak", "an oak chest", "An oak chest stands here.", "container", "10 0 150 0 0"),
        },
        "resets": [
            "M 0 110 1 100 1",
            "E 0 151 0 16",
            "G 0 150 0",
            "M 0 111 1 102 1",
            "G 0 152 0",
            "O 0 153 0 101",
            "P 0 152 1 153 1",
            "D 0 100 0 1",
            "D 0 101 2 1",
        ],
        "shops": [111],
        "specials": ["M 110 spec_guard"],
        "programs": {120: GREETING},
        "raw_rooms": "",
        "sections": "",
    }


def room_text(vnum, record):
    exits = "".join(
        "D{door}\n{description}~\n~\n{locks} {key} {destination}\n".format(**room_exit) for room_exit in record["exits"]
    )
    return f"#{vnum}\n{record['name']}~\n{record['description']}~\n0 {record['flags']} 1\n{exits}S\n"


def mob_text(vnum, record):
    programs = "".join(f"M {trigger} {program} {phrase}~\n" for trigger, program, phrase in record["programs"])
    return (
        "#{vnum}\n{name}~\n{short_desc}~\n{long_desc}~\n{description}~\n{race}~\n"
        "AB 0 0 0\n{level} 0 {hit} 1d1+1 {damage} {damtype}\n{ac} {ac} {ac} {ac}\n0 0 0 0\n"
        "{start_pos} {default_pos} {sex} 0\n0 0 {size} unknown\n"
    ).format(vnum=vnum, **record) + programs


def item_text(vnum, record):
    return (
        "#{vnum}\n{name}~\n{short_desc}~\n{description}~\nstuff~\n{item_type} 0 0\n{values}\n{level} 1 1 P\n"
    ).format(vnum=vnum, **record)


def area_text(spec):
    def records(family, text):
        return "".join(text(vnum, record) for vnum, record in spec[family].items())

    def lines(key):
        return "".join(line + "\n" for line in spec[key])

    return (
        f"#AREA\n{spec['name']}.are~\n{spec['name'].title()}~\n{spec['credits']}~\n{spec['first']} {spec['last']}\n"
        f"#MOBILES\n{records('mobs', mob_text)}#0\n"
        f"#OBJECTS\n{records('objects', item_text)}#0\n"
        f"#ROOMS\n{records('rooms', room_text)}{spec['raw_rooms']}#0\n"
        f"#RESETS\n{lines('resets')}S\n"
        f"#SHOPS\n{''.join(f'{keeper} 0 0 0 0 0 100 100 0 23' + chr(10) for keeper in spec['shops'])}0\n"
        f"#SPECIALS\n{lines('specials')}S\n"
        f"#MOBPROGS\n{''.join(f'#{vnum}' + chr(10) + f'{code}~' + chr(10) for vnum, code in spec['programs'].items())}#0\n"
        f"{spec['sections']}#$\n"
    )


def write(directory, spec):
    path = directory / f"{spec['name']}.are"
    path.write_text(area_text(spec), encoding="latin-1", newline="\n")
    return path


def judge(directory, spec, *context):
    """Lint ``spec`` with the ``context`` specs loaded beside it."""
    paths = [write(directory, each) for each in (spec, *context)]
    atlas = area_reader.atlas.load(paths, "rom")
    return area_reader.lint.lint(atlas, atlas.areas[:1])


def fired(result):
    return {row["rule"] for row in result["findings"]}


def change(family, vnum, **fields):
    return lambda spec: spec[family][vnum].update(fields)


def put(family, vnum, record):
    return lambda spec: spec[family].__setitem__(vnum, record)


def more(key, *items):
    return lambda spec: spec[key].extend(items)


def less(key, *items):
    return lambda spec: [spec[key].remove(each) for each in items]


def first(key, entry):
    return lambda spec: spec[key].insert(0, entry)


def setting(key, value):
    return lambda spec: spec.__setitem__(key, value)


def exits(vnum, *ways):
    return change("rooms", vnum, exits=list(ways))


def program(code):
    return put("programs", 120, code)


def guard(**fields):
    return change("mobs", 110, **fields)


LOOSE_MOB = mob("stray", "a stray", "A stray wanders here.\n", "It has no home.\n")
LOOSE_ITEM = item("pebble", "a pebble", "A pebble lies here.")
LOOSE_ROOM = room(
    "Tidy Attic",
    "Dust lies thick on the boards of this attic and the rafters creak\nwhenever the wind leans on the roof.\n",
)

# Each rule with one change to the tidy area that makes it fire.
FIRING = [
    ("dangling-exit-destination", exits(102, way(3, 100), way(2, 999))),
    ("dangling-exit-key", exits(102, way(3, 100, key=998))),
    ("dangling-reset-mob", more("resets", "M 0 997 1 100 1")),
    ("dangling-reset-object", more("resets", "O 0 996 0 100")),
    ("dangling-reset-room", more("resets", "O 0 153 0 995")),
    ("dangling-reset-container", more("resets", "P 0 152 1 994 1")),
    ("dangling-shop-keeper", more("shops", 993)),
    ("dangling-special-mob", more("specials", "M 992 spec_guard")),
    ("dangling-mob-program", guard(programs=[("GREET", 120, "100"), ("GREET", 991, "100")])),
    ("dangling-portal-destination", put("objects", 154, item("gate", "a gate", "A gate.", "portal", "0 0 0 990 0"))),
    ("dangling-program-room", program("mob goto 989\n")),
    ("dangling-program-mob", program("mob mload 988\n")),
    ("dangling-program-object", program("mob oload 987\n")),
    ("exit-no-destination", exits(102, way(3, 100), way(5, -1, description="A painted trapdoor.\n"))),
    ("vnum-out-of-range", put("rooms", 300, room("Tidy Annex", VAULT.replace("vault", "annex"), [way(3, 100)]))),
    ("duplicate-vnum", setting("raw_rooms", "#102\nTidy Shop~\n" + SHOP + "~\n0 0 1\nD3\n~\n~\n0 -1 100\nS\n")),
    ("unknown-section", setting("sections", "#BOGUS\nnothing\n")),
    ("section-not-checked", setting("sections", "#MOBOLD\n#0\n")),
    ("duplicate-exit", exits(102, way(3, 100), way(3, 101))),
    ("reset-no-mob", first("resets", "G 0 150 0")),
    ("reset-container-not-loaded", less("resets", "O 0 153 0 101")),
    ("reset-door-invalid", more("resets", "D 0 102 3 1")),
    ("reset-door-invalid", more("resets", "D 0 102 0 1")),
    ("reset-door-invalid", more("resets", "D 0 100 0 5")),
    ("reset-door-invalid", more("resets", "D 0 100 9 1")),
    ("reset-limit", more("resets", "M 0 110 0 100 1")),
    ("reset-limit", more("resets", "M 0 110 1 100 0")),
    ("reset-limit", more("resets", "P 0 152 1 153 0")),
    ("exit-one-way", exits(102)),
    ("exit-reverse-mismatch", exits(102, way(3, 101))),
    ("door-one-sided", exits(101, way(2, 100))),
    ("door-key-mismatch", exits(101, way(2, 100, locks=1, key=153))),
    ("room-unreachable", put("rooms", 103, LOOSE_ROOM)),
    ("room-no-exit", put("rooms", 103, LOOSE_ROOM)),
    ("key-not-key-type", exits(102, way(3, 100, key=151))),
    ("key-never-loaded", less("resets", "G 0 150 0")),
    ("mob-never-loaded", put("mobs", 112, LOOSE_MOB)),
    ("object-never-loaded", put("objects", 154, LOOSE_ITEM)),
    ("program-unused", put("programs", 121, "say Nobody calls me.\n")),
    ("shop-keeper-never-loaded", less("resets", "M 0 111 1 102 1", "G 0 152 0")),
    ("shop-no-stock", less("resets", "G 0 152 0")),
    ("special-unknown", more("specials", "M 111 spec_bogus")),
    ("program-trigger-unknown", guard(programs=[("BOGUS", 120, "100")])),
    ("program-unbalanced-if", program("if ispc $n\n  say Hello.\n")),
    ("program-unbalanced-if", program("say Hello.\nendif\n")),
    ("program-unbalanced-if", program("say Hello.\nelse\n")),
    ("program-unbalanced-if", program("if ispc $n\n  say Hello.\n  or isgood $n\nendif\n")),
    ("program-unbalanced-if", program("if rand 1\n" * 12 + "endif\n" * 12)),
    ("program-command-unknown", program("mob dance\n")),
    ("program-command-unknown", program("mob\n")),
    ("program-check-unknown", program("if isbogus $n\nendif\n")),
    ("program-check-unknown", program("if ispc $n\nand wibble $n\nendif\n")),
    ("item-type-unknown", change("objects", 150, item_type="gadget")),
    ("mob-race-unknown", guard(race="martian")),
    ("mob-position-unknown", guard(start_pos="floating")),
    ("mob-position-unknown", guard(default_pos="floating")),
    ("mob-sex-unknown", guard(sex="robot")),
    ("mob-size-unknown", guard(size="enormous")),
    ("mob-damtype-unknown", guard(damtype="tickle")),
    ("weapon-class-unknown", change("objects", 151, values="spear 1 6 slash 0")),
    ("weapon-damtype-unknown", change("objects", 151, values="sword 1 6 tickle 0")),
    ("liquid-unknown", change("objects", 152, values="10 10 'nectar' 0 0")),
    ("mob-hit-dice-off-level", guard(hit="1d1+999")),
    ("mob-hit-dice-off-level", guard(hit="1d1+1")),
    ("mob-damage-dice-off-level", guard(damage="9d9+50")),
    ("mob-ac-off-level", guard(ac=-20)),
    ("mob-level-outside-area-range", guard(level=30)),
    ("object-level-outside-area-range", change("objects", 151, level=40)),
    ("room-name-empty", change("rooms", 102, name="")),
    ("room-description-empty", change("rooms", 102, description="")),
    ("mob-name-empty", guard(name="")),
    ("mob-short-desc-empty", guard(short_desc="")),
    ("mob-long-desc-empty", guard(long_desc="")),
    ("mob-description-empty", guard(description="")),
    ("object-name-empty", change("objects", 150, name="")),
    ("object-short-desc-empty", change("objects", 150, short_desc="")),
    ("object-description-empty", change("objects", 150, description="")),
    ("room-description-short", change("rooms", 102, description="A shop.\n")),
    ("room-description-short", change("rooms", 102, description="x" * 79 + "\n")),
    ("line-too-long", change("rooms", 102, description=SHOP + "x" * 80 + "\n")),
    ("line-too-long", guard(description="x" * 80 + "\n")),
    ("line-too-long", exits(102, way(3, 100, description="x" * 80 + "\n"))),
    ("room-description-no-newline", change("rooms", 102, description=SHOP.rstrip("\n"))),
    ("mob-long-desc-not-one-line", guard(long_desc="A tidy guard stands here,\nwatching the square.\n")),
    ("mob-long-desc-not-one-line", guard(long_desc="A tidy guard stands here.")),
    ("room-description-duplicate", change("rooms", 102, description=SQUARE)),
    ("mob-description-duplicate", guard(description="She is counting coins.\n")),
    ("short-desc-period", guard(short_desc="the tidy guard.")),
    ("short-desc-capital-article", guard(short_desc="The tidy guard")),
    ("short-desc-capital-article", change("objects", 150, short_desc="A brass key")),
    ("short-desc-no-keyword", guard(name="sentinel")),
    ("description-direction-no-exit", change("rooms", 102, description=SHOP + "A passage leads north.\n")),
]

# Changes that look like a defect to one rule and are not.
QUIET = [
    ("exit-no-destination", exits(102, way(3, 100), way(2, 999))),
    ("vnum-out-of-range", setting("last", 100 + 99)),
    ("reset-limit", more("resets", "O 0 153 0 102")),
    ("reset-limit", more("resets", "G 0 152 -1")),
    ("room-unreachable", lambda spec: (spec["rooms"][102].update(flags="M"), spec["rooms"].update({103: LOOSE_ROOM}))),
    ("room-no-exit", lambda spec: (spec["rooms"][102].update(flags="M"), spec["rooms"].update({103: LOOSE_ROOM}))),
    ("room-no-exit", exits(102, way(3, 100), way(5, -1))),
    (
        "mob-never-loaded",
        lambda spec: (spec["mobs"].update({112: LOOSE_MOB}), spec["programs"].update({120: "mob mload 112\n"})),
    ),
    (
        "object-never-loaded",
        lambda spec: (spec["objects"].update({154: LOOSE_ITEM}), spec["programs"].update({120: "mob oload 154\n"})),
    ),
    ("object-never-loaded", less("resets", "G 0 150 0")),
    ("program-unused", lambda spec: spec["programs"].update({120: "mob call 121\n", 121: "say Called.\n"})),
    ("shop-no-stock", lambda spec: (spec["resets"].remove("G 0 152 0"), spec["rooms"][102].update(flags="M"))),
    ("special-unknown", setting("specials", ["M 110 spec_gu", "* a comment"])),
    ("program-trigger-unknown", guard(programs=[("gree", 120, "100")])),
    ("program-unbalanced-if", program("if ispc $n\n  if isgood $n\n    say Hello.\n  endif\nelse\n  say Hm.\nendif\n")),
    ("program-unbalanced-if", program("if ispc $n\nor isnpc $n\nand isgood $n\n  say Hello.\nendif\n* endif\n")),
    ("program-command-unknown", program("mob echoar $n The guard nods.\nsay mob dance\n* mob dance\n")),
    ("program-check-unknown", program("if LEVEL $n > 3\nendif\n")),
    ("mob-position-unknown", guard(start_pos="sleep", default_pos="mort")),
    ("mob-sex-unknown", guard(sex="either")),
    ("weapon-class-unknown", change("objects", 151, values="exotic 1 6 slash 0")),
    ("weapon-damtype-unknown", change("objects", 150, values="0 0 0 tickle 0")),
    ("liquid-unknown", change("objects", 152, item_type="fountain", values="0 0 'red wine' 0 0")),
    ("mob-hit-dice-off-level", guard(hit="2d6+60")),
    ("mob-hit-dice-off-level", guard(level=61, hit="1d1+1")),
    ("mob-ac-off-level", guard(ac=2)),
    (
        "mob-level-outside-area-range",
        lambda spec: (spec.update(credits="{ All } Tester Tidy"), spec["mobs"][110].update(level=30)),
    ),
    ("object-level-outside-area-range", change("objects", 151, level=0)),
    ("room-description-short", change("rooms", 102, description="x" * 40 + "\n" + "y" * 39 + "\n")),
    ("line-too-long", change("rooms", 102, description=SHOP + "x" * 79 + "\n")),
    ("room-description-duplicate", change("rooms", 102, description="")),
    ("short-desc-capital-article", guard(short_desc="Thea the tidy guard")),
    ("short-desc-no-keyword", guard(name="sentinel GUARD")),
    ("description-direction-no-exit", change("rooms", 102, description=SHOP + "A passage leads west.\n")),
    ("description-direction-no-exit", change("rooms", 102, description=SHOP + "The hills lie to the north-east.\n")),
]


def test_no_rule_fires_on_a_tidy_area(tmp_path):
    result = judge(tmp_path, tidy())

    assert result["findings"] == []
    assert result["counts"] == {"error": 0, "warning": 0, "info": 0}


@pytest.mark.parametrize(("rule", "alter"), FIRING, ids=lambda value: value if isinstance(value, str) else "")
def test_rule_fires(tmp_path, rule, alter):
    spec = tidy()
    alter(spec)

    result = judge(tmp_path, spec)

    assert rule in fired(result)
    assert all(row["severity"] == area_reader.lint.RULES[row["rule"]][0] for row in result["findings"])


@pytest.mark.parametrize(("rule", "alter"), QUIET, ids=lambda value: value if isinstance(value, str) else "")
def test_rule_stays_quiet(tmp_path, rule, alter):
    spec = tidy()
    alter(spec)

    assert rule not in fired(judge(tmp_path, spec))


def test_every_rule_has_a_firing_case():
    assert {rule for rule, _alter in FIRING} | {"vnum-collision"} == set(area_reader.lint.RULES)


def neighbour():
    spec = tidy()
    spec.update(name="other", first=200, last=299, mobs={}, objects={}, resets=[], shops=[], specials=[], programs={})
    spec["rooms"] = {200: room("Other Lane", VAULT.replace("vault", "lane"), [way(3, 102)])}
    return spec


def test_context_areas_resolve_references_and_get_no_findings(tmp_path):
    spec = tidy()
    spec["rooms"][102]["exits"].append(way(1, 200))

    alone = judge(tmp_path, spec)
    together = judge(tmp_path, spec, neighbour())

    assert "dangling-exit-destination" in fired(alone)
    assert together["findings"] == []
    assert list(together["metrics"]) == ["tidy.are"]


def test_vnum_collision_names_the_other_file(tmp_path):
    other = neighbour()
    other["rooms"][102] = copy.deepcopy(tidy()["rooms"][102])

    result = judge(tmp_path, tidy(), other)

    assert [(row["rule"], row["kind"], row["vnum"]) for row in result["findings"]] == [("vnum-collision", "room", 102)]
    assert "other.are" in result["findings"][0]["message"]


def test_findings_name_their_place(tmp_path):
    spec = tidy()
    spec["resets"].append("M 0 997 1 100 1")
    spec["shops"].append(993)
    spec["specials"].append("M 111 spec_bogus")
    spec["programs"][120] = "mob dance\n"
    spec["rooms"][102]["exits"].append(way(2, 999))

    rows = {row["rule"]: row for row in judge(tmp_path, spec)["findings"]}

    assert rows["dangling-reset-mob"] == {
        "rule": "dangling-reset-mob",
        "severity": "error",
        "file": "tidy.are",
        "kind": "reset",
        "vnum": None,
        "index": 9,
        "message": "M reset refers to mob 997, which no file defines",
    }
    assert (rows["dangling-shop-keeper"]["kind"], rows["dangling-shop-keeper"]["vnum"]) == ("shop", 993)
    assert (rows["special-unknown"]["kind"], rows["special-unknown"]["vnum"]) == ("special", 111)
    assert (rows["program-command-unknown"]["kind"], rows["program-command-unknown"]["vnum"]) == ("program", 120)
    assert (rows["dangling-exit-destination"]["kind"], rows["dangling-exit-destination"]["vnum"]) == ("room", 102)


def test_duplicate_descriptions_are_one_finding_listing_the_vnums(tmp_path):
    spec = tidy()
    spec["rooms"][101]["description"] = SQUARE
    spec["rooms"][102]["description"] = SQUARE

    rows = [row for row in judge(tmp_path, spec)["findings"] if row["rule"] == "room-description-duplicate"]

    assert [(row["vnum"], row["message"]) for row in rows] == [(100, "3 rooms share one description: 100, 101, 102")]


def test_unreachable_rooms_are_those_outside_the_largest_group(tmp_path):
    spec = tidy()
    spec["rooms"][103] = room("Tidy Attic", LOOSE_ROOM["description"], [way(0, 104)])
    spec["rooms"][104] = room("Tidy Loft", LOOSE_ROOM["description"].replace("attic", "loft"), [way(2, 103)])

    rows = [row for row in judge(tmp_path, spec)["findings"] if row["rule"] == "room-unreachable"]

    assert [row["vnum"] for row in rows] == [103, 104]


def test_rom_lookup_matches_prefixes_without_case():
    assert area_reader.lint.rom_lookup("STAND", area_reader.lint.POSITIONS) == "standing"
    assert area_reader.lint.rom_lookup("mort", area_reader.lint.POSITIONS) == "mortally wounded"
    assert area_reader.lint.rom_lookup("", area_reader.lint.POSITIONS) is None
    assert area_reader.lint.rom_lookup("standings", area_reader.lint.POSITIONS) is None


def test_recommended_values_follow_the_class_flags():
    plain = type("Mob", (), {"level": 10, "act": area_reader.lint.ROM_ACT_TYPES.IS_NPC})
    mage = type("Mob", (), {"level": 10, "act": area_reader.lint.ROM_ACT_TYPES.MAGE})
    high = type("Mob", (), {"level": 61, "act": area_reader.lint.ROM_ACT_TYPES.IS_NPC})

    assert area_reader.lint.recommended(plain, "damage") == area_reader.lint.RECOMMENDED[10]
    assert area_reader.lint.recommended(mage, "damage") == area_reader.lint.RECOMMENDED[7]
    assert area_reader.lint.recommended(mage, "hit") == area_reader.lint.RECOMMENDED[9]
    assert area_reader.lint.recommended(high, "hit") is None


def test_metrics_of_the_tidy_area(tmp_path):
    metrics = judge(tmp_path, tidy())["metrics"]["tidy.are"]

    assert metrics["rooms"] == 3
    assert metrics["mobs"] == 2
    assert metrics["objects"] == 4
    assert metrics["resets"] == 9
    assert metrics["shops"] == 1
    assert metrics["specials"] == 1
    assert metrics["programs"] == 1
    assert metrics["exits"] == 4
    assert metrics["exits_per_room"] == pytest.approx(4 / 3)
    assert metrics["room_description_length_mean"] == pytest.approx(
        sum(len(text.strip()) for text in (SQUARE, VAULT, SHOP)) / 3
    )
    assert metrics["room_description_length_median"] == sorted(len(text.strip()) for text in (SQUARE, VAULT, SHOP))[1]
    assert metrics["rooms_with_extra_description"] == 0
    assert metrics["distinct_room_names"] == 1
    assert metrics["distinct_room_descriptions"] == 1
    assert metrics["mobs_with_program_or_special"] == 0.5
    assert metrics["doors"] == 2
    assert metrics["locked_doors"] == 2
    assert metrics["keys"] == 1
    assert metrics["item_types"] == {"key": 1, "weapon": 1, "drink": 1, "container": 1}
    assert metrics["sectors"] == {"city": 3}
    assert metrics["mob_levels"] == {"min": 3, "median": 3, "max": 3}
    assert 0 < metrics["description_type_token_ratio"] <= 1
    assert metrics["description_words"] > 40


def test_metrics_of_an_area_without_records(tmp_path):
    spec = neighbour()
    spec["rooms"] = {}

    metrics = judge(tmp_path, spec)["metrics"]["other.are"]

    assert metrics["rooms"] == 0
    assert metrics["exits_per_room"] is None
    assert metrics["room_description_length_mean"] is None
    assert metrics["mob_levels"] is None
    assert metrics["description_type_token_ratio"] is None


def test_cli_text_of_a_tidy_area(tmp_path, capsys):
    path = write(tmp_path, tidy())

    assert area_reader.cli.main(["lint", str(path)]) == 0
    assert capsys.readouterr().out == "Errors: 0. Warnings: 0. Info: 0.\n"


def test_cli_text_groups_findings_by_file_and_exits_1_on_an_error(tmp_path, capsys):
    spec = tidy()
    spec["rooms"][102]["exits"].append(way(2, 999))
    spec["mobs"][110]["short_desc"] = "The tidy guard"
    path = write(tmp_path, spec)

    assert area_reader.cli.main(["lint", str(path)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "tidy.are",
        "  error dangling-exit-destination room 102: room 102 south refers to room 999, which no file defines",
        "  warning short-desc-capital-article mob 110: short_desc 'The tidy guard' starts with a capital article",
        "Errors: 1. Warnings: 1. Info: 0.",
    ]


def test_cli_exits_0_on_warnings_alone(tmp_path, capsys):
    spec = tidy()
    spec["mobs"][110]["short_desc"] = "The tidy guard"
    path = write(tmp_path, spec)

    assert area_reader.cli.main(["lint", str(path)]) == 0
    assert "Errors: 0. Warnings: 1. Info: 0." in capsys.readouterr().out


def test_cli_min_severity_hides_findings_and_keeps_counts(tmp_path, capsys):
    spec = tidy()
    spec["rooms"][102]["exits"].append(way(5, -1))
    spec["mobs"][110]["short_desc"] = "The tidy guard"
    path = write(tmp_path, spec)

    area_reader.cli.main(["lint", "--json", "--min-severity", "warning", str(path)])
    result = json.loads(capsys.readouterr().out)

    assert [row["rule"] for row in result["findings"]] == ["short-desc-capital-article"]
    assert result["counts"] == {"error": 0, "warning": 1, "info": 1}


def test_cli_json_with_context(tmp_path, capsys):
    spec = tidy()
    spec["rooms"][102]["exits"].append(way(1, 200))
    path = write(tmp_path, spec)
    context = tmp_path / "context"
    context.mkdir()
    write(context, neighbour())

    assert area_reader.cli.main(["lint", "--json", str(path)]) == 1
    alone = json.loads(capsys.readouterr().out)
    assert area_reader.cli.main(["lint", "--json", "--with", str(context), "--with", str(path), str(path)]) == 0
    together = json.loads(capsys.readouterr().out)

    assert [row["rule"] for row in alone["findings"]] == ["dangling-exit-destination"]
    assert together["findings"] == []
    assert set(together) == {"findings", "counts", "metrics"}
    assert list(together["metrics"]) == ["tidy.are"]


def test_cli_lints_every_area_of_a_directory(tmp_path, capsys):
    write(tmp_path, tidy())
    write(tmp_path, neighbour())

    area_reader.cli.main(["lint", "--json", str(tmp_path)])

    assert list(json.loads(capsys.readouterr().out)["metrics"]) == ["other.are", "tidy.are"]


def test_stock_rom_error_findings():
    atlas = area_reader.atlas.load(["test/rom"], "rom")

    result = area_reader.lint.lint(atlas, atlas.areas)
    errors = [row for row in result["findings"] if row["severity"] == "error"]

    assert Counter(row["rule"] for row in errors) == {
        "dangling-exit-key": 10,
        "room-description-empty": 3,
        "mob-long-desc-empty": 1,
    }
    assert sorted((row["file"], row["vnum"]) for row in errors if row["rule"] != "dangling-exit-key") == [
        ("catacomb.are", 2006),
        ("newthalos.are", 9750),
        ("nirvana.are", 9010),
        ("wyvern.are", 1644),
    ]
    assert result["counts"]["error"] == 14
