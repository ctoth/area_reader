"""Mob programs are serialized in one ROM 2.4-shaped list per mob, whatever the source dialect."""

import json
from pathlib import Path

import pytest

import area_reader.dialects.ack
import area_reader.dialects.rom
import area_reader.dialects.smaug
import area_reader.dialects.swr
import area_reader.mobprogs

ROM_MOBILE = """imp~
an imp~
An imp grins broadly.
~
An imp.
~
elf~
AGU J 0 -500 0
30 60 9d61+416 1d1+999 5d6+15 claw
-9 -9 -9 -9
0 0 B Z
stand stand male 1500
AHMV ABCDEFGHIJK small unknown
"""
ROM_HEADER = "#AREADATA\nName Programs~\nBuilders None~\nVNUMs 100 199\nCredits Programs~\nSecurity 9\nEnd\n"
ROM_JOINED = (
    ROM_HEADER
    + "#MOBILES\n#100\n"
    + ROM_MOBILE
    + "M GRALL 100 100~\nM random 101 15~\n#101\n"
    + ROM_MOBILE
    + "#0\n#MOBPROGS\n#100\nmob echo The imp cackles.\nmob cast fireball $n\n~\n"
    + "#101\nif rand 50\n  grin\nendif\n\n\n~\n#0\n#$\n"
)
ROM_MISSING = (
    ROM_HEADER
    + "#MOBILES\n#100\n"
    + ROM_MOBILE
    + "M GREET 100 100~\nM SPEECH 150 hello~\n#101\n"
    + ROM_MOBILE
    + "M DEATH 151 100~\n#0\n#MOBPROGS\n#100\nsay hello\n~\n#0\n#$\n"
)
SMAUG_MOBILE = "mob~\na mob~\nA mob is here.~\nA mob.~\n1 2 3 S\n4 5 6 1d2+3 2d3+4\n7 8\n9 10 1\n"


def load(reader_class, tmp_path: Path, text: str):
    path = tmp_path / "area.are"
    path.write_text(text, encoding="latin-1")
    area_file = reader_class(path)
    area_file.load_sections()
    return area_file


def load_rom(tmp_path: Path, text: str) -> area_reader.dialects.rom.RomAreaFile:
    return load(area_reader.dialects.rom.RomAreaFile, tmp_path, text)


def load_smaug_programs(tmp_path: Path, programs: str) -> area_reader.dialects.smaug.SmaugAreaFile:
    text = "#AREA Inline~\n#MOBILES\n#7\n" + SMAUG_MOBILE + programs + "|\n#0\n#$\n"
    return load(area_reader.dialects.smaug.SmaugAreaFile, tmp_path, text)


def test_rom_triggers_are_joined_with_their_program_bodies(tmp_path: Path) -> None:
    payload = load_rom(tmp_path, ROM_JOINED).as_dict()

    assert payload["mobs"][100]["mob_programs"] == [
        {
            "trigger": "GRALL",
            "phrase": "100",
            "lines": ["mob echo The imp cackles.", "mob cast fireball $n"],
            "source": "rom",
            "vnum": 100,
            "group": 0,
        },
        {
            "trigger": "RANDOM",
            "phrase": "15",
            "lines": ["if rand 50", "  grin", "endif"],
            "source": "rom",
            "vnum": 101,
            "group": 1,
        },
    ]
    assert payload["mobs"][101]["mob_programs"] == []
    assert payload["diagnostics"] == []


def test_normalized_programs_leave_the_existing_keys_and_the_native_text_alone(tmp_path: Path) -> None:
    area_file = load_rom(tmp_path, ROM_JOINED)
    rendered = area_file.dumps()

    payload = json.loads(area_file.as_json())

    assert payload["mobs"]["100"]["mprogs"] == [
        {"trig_type": "GRALL", "vnum": 100, "trig_phrase": "100"},
        {"trig_type": "random", "vnum": 101, "trig_phrase": "15"},
    ]
    assert payload["mobprogs"] == {
        "100": "mob echo The imp cackles.\nmob cast fireball $n\n",
        "101": "if rand 50\n  grin\nendif\n\n\n",
    }
    assert area_file.dumps() == rendered
    assert "mob_programs" not in rendered
    assert load_rom(tmp_path, rendered).area == area_file.area


def test_a_trigger_without_a_program_body_is_reported(tmp_path: Path) -> None:
    area_file = load_rom(tmp_path, ROM_MISSING)

    payload = area_file.as_dict()

    assert payload["mobs"][100]["mob_programs"] == [
        {"trigger": "GREET", "phrase": "100", "lines": ["say hello"], "source": "rom", "vnum": 100, "group": 0},
        {"trigger": "SPEECH", "phrase": "hello", "lines": [], "source": "rom", "vnum": 150, "group": 1},
    ]
    assert payload["mobs"][101]["mob_programs"] == [
        {"trigger": "DEATH", "phrase": "100", "lines": [], "source": "rom", "vnum": 151, "group": 0},
    ]
    assert payload["diagnostics"] == [
        {"kind": "missing_mobprog", "mob": 100, "trigger": "SPEECH", "vnum": 150},
        {"kind": "missing_mobprog", "mob": 101, "trigger": "DEATH", "vnum": 151},
    ]
    assert area_file.as_dict()["diagnostics"] == payload["diagnostics"]


def test_inline_programs_are_translated_to_rom_syntax(tmp_path: Path) -> None:
    area_file = load_smaug_programs(
        tmp_path,
        "> all_greet_prog 100~\n"
        "if name($n) == loki\n"
        "scream\n"
        "mpforce loki snarl\n"
        "else\n"
        "  if ispc($n)\n"
        "    mpe $I frowns.\n"
        "  endif\n"
        "endif\n"
        "~\n"
        "> fight_prog 40~\n"
        "if rand(10)\n"
        "mpasound A thunderous cry can be heard. \n"
        "mpmload 12012\n"
        "mpdamage $n 125\n"
        "endif\n"
        "~\n",
    )
    rendered = area_file.dumps()

    payload = area_file.as_dict()

    assert payload["mobs"][7]["mob_programs"] == [
        {
            "trigger": "GRALL",
            "phrase": "100",
            "lines": [
                "if name $n loki",
                "scream",
                "mob force loki snarl",
                "else",
                "  if ispc $n",
                "    mob echo $I frowns.",
                "  endif",
                "endif",
            ],
            "source": "inline",
            "vnum": None,
            "group": 0,
        },
        {
            "trigger": "FIGHT",
            "phrase": "40",
            "lines": [
                "if rand 10",
                "mob asound A thunderous cry can be heard. ",
                "mob mload 12012",
                "mob damage $n 125 125 kill",
                "endif",
            ],
            "source": "inline",
            "vnum": None,
            "group": 1,
        },
    ]
    assert payload["diagnostics"] == []
    assert payload["mobs"][7]["mprogs"] == []
    assert [program["trigger"] for program in payload["mobs"][7]["programs"]] == ["all_greet_prog", "fight_prog"]
    assert payload["mobs"][7]["programs"][1]["commands"].startswith("if rand(10)\nmpasound A thunderous")
    assert area_file.dumps() == rendered


@pytest.mark.parametrize(
    ("name", "trigger"),
    [
        ("act_prog", "ACT"),
        ("bribe_prog", "BRIBE"),
        ("death_prog", "DEATH"),
        ("entry_prog", "ENTRY"),
        ("fight_prog", "FIGHT"),
        ("give_prog", "GIVE"),
        ("greet_prog", "GREET"),
        ("all_greet_prog", "GRALL"),
        ("hitprcnt_prog", "HPCNT"),
        ("rand_prog", "RANDOM"),
        ("speech_prog", "SPEECH"),
        ("GREET_PROG", "GREET"),
    ],
)
def test_inline_trigger_names_map_to_rom_trigger_words(name: str, trigger: str) -> None:
    entries, diagnostics = area_reader.mobprogs.inline_programs(7, [(name, "100", "say hi\n")])

    assert entries == [
        {"trigger": trigger, "phrase": "100", "lines": ["say hi"], "source": "inline", "vnum": None, "group": 0},
    ]
    assert diagnostics == []


@pytest.mark.parametrize(
    ("line", "translated"),
    [
        ("mpe The room shakes.", "mob echo The room shakes."),
        ("mpecho $I cackles.", "mob echo $I cackles."),
        ("MPECHO changed", "mob echo changed"),
        ("mea $n You are struck!", "mob echoat $n You are struck!"),
        ("mpechoat $r $I smashes you!", "mob echoat $r $I smashes you!"),
        ("mer $n $I slams into $n!", "mob echoaround $n $I slams into $n!"),
        ("mpechoar $n $n bursts into flames!", "mob echoaround $n $n bursts into flames!"),
        ("mpechoaround $n $I shrieks.", "mob echoaround $n $I shrieks."),
        ("mpasound A horn sounds.", "mob asound A horn sounds."),
        ("mpforce $n drop all", "mob force $n drop all"),
        ("mpat 3 wield ebony", "mob at 3 wield ebony"),
        ("mpat 3 mpe $n vanishes.", "mob at 3 mob echo $n vanishes."),
        ("mpat thor mpforce thor up", "mob at thor mob force thor up"),
        ("mpat $n mpat $n mea $n Ouch.", "mob at $n mob at $n mob echoat $n Ouch."),
        ("mpoload 12039 50", "mob oload 12039 50"),
        ("mpmload 12012", "mob mload 12012"),
        ("   mpmload 25011", "   mob mload 25011"),
        ("mpgoto 12097", "mob goto 12097"),
        ("mpgot 12797", "mob goto 12797"),
        ("mptrans $n 12000", "mob transfer $n 12000"),
        ("mptransfer 0.$n", "mob transfer 0.$n"),
        ("mpjunk all", "mob junk all"),
        ("mppurge", "mob purge"),
        ("mppurge skirnir", "mob purge skirnir"),
        ("mpkill $n", "mob kill $n"),
        ("mpdamage $r 400", "mob damage $r 400 400 kill"),
        ("if rand(25)", "if rand 25"),
        ("if ispc($r)", "if ispc $r"),
        ("if isnpc($n)", "if isnpc $n"),
        ("if isimmort($n)", "if isimmort $n"),
        ("if isgood($n)", "if isgood $n"),
        ("  if isevil($n)", "  if isevil $n"),
        ("or ispc($n)", "or ispc $n"),
        ("and rand(10)", "and rand 10"),
        ("IF ISPC($n)", "if ispc $n"),
        ("if name($n) == loki", "if name $n loki"),
        ("if name($n) == fire giant", "if name $n 'fire giant'"),
        ("if name($n) == witch tus'schepteba", 'if name $n "witch tus\'schepteba"'),
        ("if clan($n) == Dragonslayer", "if clan $n Dragonslayer"),
        ("if race($n) == elf", "if race $n elf"),
        ("if class($n) == mage", "if class $n mage"),
        ("if sex($n) == 2", "if sex $n == 2"),
        ("if level($n) < 30", "if level $n < 30"),
        ("if inroom($i) == 12099", "if room $i == 12099"),
        ("mpe _red A burly berserker charges!", "mob echo {rA burly berserker charges!{x"),
        ("mpe _gre Vines writhe.", "mob echo {GVines writhe.{x"),
        ("mpe _yel Sparks fly.", "mob echo {YSparks fly.{x"),
        ("mpe _lbl Frost spreads.", "mob echo {CFrost spreads.{x"),
        ("mpe _whi A thunderous cry.", "mob echo {WA thunderous cry.{x"),
        ("mpe _blu Lightning surges.", "mob echo {BLightning surges.{x"),
        ("mpe _dch Shadows gather.", "mob echo {DShadows gather.{x"),
        ("MPE _RED Blood sprays.", "mob echo {rBlood sprays.{x"),
        ("mea $n _yel You fall into the pit!", "mob echoat $n {YYou fall into the pit!{x"),
        ("mer $n _red $I slams into $n!", "mob echoaround $n {r$I slams into $n!{x"),
        ("mpat 3 mpe _whi A horn sounds.", "mob at 3 mob echo {WA horn sounds.{x"),
        ("mpe _not a colour", "mob echo _not a colour"),
        ("mea $n *sigh* You hear a sigh.", "mob echoat $n *sigh* You hear a sigh."),
        ("say mpe is not a command here", "say mpe is not a command here"),
        ("c 'fireball' $n", "c 'fireball' $n"),
        (", brings Gjaller to his lips.", ", brings Gjaller to his lips."),
        ("else", "else"),
        ("endif", "endif"),
        ("", ""),
    ],
)
def test_inline_lines_are_rewritten_as_rom_mob_commands(line: str, translated: str) -> None:
    assert area_reader.mobprogs.translate_line(line) == translated


@pytest.mark.parametrize(
    "line",
    [
        "mprestore self 50",
        "mpslay $n",
        "mpopenpassage 12180 12181 2",
        "mpclosepassage 12180 2",
        "mpea Just as your blows begin to tell on $I, his wounds start to close!",
        "mpe _pur A violet haze descends.",
        "mea $n _ora You are burned!",
        "mer $n *gre With a cry, $n falls into the pit!",
        "mpat 3 mprestore self 50",
        "mpforce thor mpslay $n",
        "mpdamage $n",
        "mpdamage $n lots",
        "if goldamt($n) > 20000000",
        "if con($n) < 15",
        "if mobinarea(25011) >= 1",
        "if name($n) != loki",
        "if name($n) == both ' and \"",
        "if ispc(loki)",
        "if ispc($n) == 1",
        "if rand(ten)",
        "if level($n) / 3",
        "if level($n) > high",
        "if ispc $n",
    ],
)
def test_lines_without_a_confident_rom_form_are_not_translated(line: str) -> None:
    assert area_reader.mobprogs.translate_line(line) is None


def test_untranslated_lines_are_kept_and_reported(tmp_path: Path) -> None:
    area_file = load_smaug_programs(
        tmp_path,
        "> hitprcnt_prog 50~\n"
        "mpe $I staggers.\n"
        "mprestore self 500\n"
        "if con($n) < 15\n"
        "mpe _red Blood sprays.\n"
        "mpe _pur A violet haze descends.\n"
        "endif\n"
        "~\n",
    )

    payload = area_file.as_dict()

    assert payload["mobs"][7]["mob_programs"] == [
        {
            "trigger": "HPCNT",
            "phrase": "50",
            "lines": [
                "mob echo $I staggers.",
                "mprestore self 500",
                "if con($n) < 15",
                "mob echo {rBlood sprays.{x",
                "mpe _pur A violet haze descends.",
                "endif",
            ],
            "source": "inline",
            "vnum": None,
            "group": 0,
        },
    ]
    assert payload["diagnostics"] == [
        {"kind": "untranslated_mobprog_line", "mob": 7, "trigger": "HPCNT", "line": "mprestore self 500"},
        {"kind": "untranslated_mobprog_line", "mob": 7, "trigger": "HPCNT", "line": "if con($n) < 15"},
        {"kind": "untranslated_mobprog_line", "mob": 7, "trigger": "HPCNT", "line": "mpe _pur A violet haze descends."},
    ]


def test_an_inline_trigger_without_a_rom_equivalent_keeps_its_name(tmp_path: Path) -> None:
    area_file = load_smaug_programs(tmp_path, "> time_prog 12~\nmpe The bell tolls.\n~\n")

    payload = area_file.as_dict()

    assert payload["mobs"][7]["mob_programs"] == [
        {
            "trigger": "TIME_PROG",
            "phrase": "12",
            "lines": ["mob echo The bell tolls."],
            "source": "inline",
            "vnum": None,
            "group": 0,
        },
    ]
    assert payload["diagnostics"] == [{"kind": "unknown_mobprog_trigger", "mob": 7, "trigger": "TIME_PROG"}]


def test_inline_phrases_drop_the_exact_phrase_marker_and_split_word_lists(tmp_path: Path) -> None:
    area_file = load_smaug_programs(
        tmp_path,
        "> act_prog p pokes you in the ribs.~\ngrin\n~\n"
        "> speech_prog p i wish to see the baron~\nnod\n~\n"
        "> act_prog flees~\ncackle\n~\n"
        "> speech_prog witch necromancer  witch ~\nspit\nmpslay $n\n~\n"
        "> give_prog rotting heart necromancer~\nsmile\n~\n",
    )

    payload = area_file.as_dict()

    programs = payload["mobs"][7]["mob_programs"]
    assert [(entry["trigger"], entry["phrase"], entry["group"]) for entry in programs] == [
        ("ACT", "pokes you in the ribs.", 0),
        ("SPEECH", "i wish to see the baron", 1),
        ("ACT", "flees", 2),
        ("SPEECH", "witch", 3),
        ("SPEECH", "necromancer", 3),
        ("SPEECH", "witch", 3),
        ("GIVE", "rotting heart necromancer", 4),
    ]
    assert [entry["lines"] for entry in programs[3:6]] == [["spit", "mpslay $n"]] * 3
    assert payload["diagnostics"] == [
        {"kind": "untranslated_mobprog_line", "mob": 7, "trigger": "SPEECH", "line": "mpslay $n"},
    ]
    assert payload["mobs"][7]["programs"][3]["argument"] == "witch necromancer  witch "


def test_an_inline_phrase_trigger_without_a_phrase_is_kept_and_reported(tmp_path: Path) -> None:
    area_file = load_smaug_programs(tmp_path, "> speech_prog ~\nnod\n~\n")

    payload = area_file.as_dict()

    assert payload["mobs"][7]["mob_programs"] == [
        {"trigger": "SPEECH", "phrase": "", "lines": ["nod"], "source": "inline", "vnum": None, "group": 0},
    ]
    assert payload["diagnostics"] == [
        {"kind": "untranslated_mobprog_phrase", "mob": 7, "trigger": "SPEECH", "phrase": ""},
    ]


def test_ack_inline_programs_are_normalized() -> None:
    area_file = area_reader.dialects.ack.AckAreaFile(Path("test/ack/ack_sample.are"))
    area_file.load_sections()

    payload = area_file.as_dict()

    programs = payload["mobs"][9623]["mob_programs"]
    assert [(entry["trigger"], entry["source"], entry["vnum"]) for entry in programs] == [
        ("ACT", "inline", None),
        ("DEATH", "inline", None),
    ]
    assert programs[0]["phrase"] == "opens the trapdoor."
    assert [program.trigger for program in area_file.area.mobs[9623].mobprogs] == ["act_prog", "death_prog"]
    assert payload["mobs"][16003]["mob_programs"] == []
    assert programs[1]["lines"] == [
        "mob echo Ymmas crashes to the ground, and errupts into a mass of spiders!",
        "    mob mload 9624",
    ]
    assert payload["diagnostics"] == []


def test_fuss_inline_programs_are_normalized(tmp_path: Path) -> None:
    area_file = load(
        area_reader.dialects.swr.SwrAreaFile,
        tmp_path,
        "#FUSSAREA\n#AREADATA\nVersion      1\nName         Programs~\n#ENDAREADATA\n\n"
        "#MOBILE\nVnum       5\nKeywords   test mob~\n"
        "#MUDPROG\nProgtype  greet_prog~\nArglist   100~\nComlist   mpecho $I nods.\n~\n#ENDPROG\n\n"
        "#ENDMOBILE\n\n#ENDAREA\n",
    )

    payload = area_file.as_dict()

    assert payload["mobs"][5]["mob_programs"] == [
        {
            "trigger": "GREET",
            "phrase": "100",
            "lines": ["mob echo $I nods."],
            "source": "inline",
            "vnum": None,
            "group": 0,
        },
    ]
    assert payload["mobs"][5]["programs"][0]["progtype"] == "greet_prog"
    assert payload["diagnostics"] == []
