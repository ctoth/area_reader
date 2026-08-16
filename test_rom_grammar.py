from pathlib import Path

import pytest

import area_reader.dialects.rom


def make_reader(tmp_path: Path, text: str) -> area_reader.AreaFile:
    path = tmp_path / "grammar.are"
    path.write_text(text, encoding="latin-1")
    return area_reader.AreaFile(path)


def test_fread_word_accepts_both_engine_quote_styles(tmp_path):
    reader = make_reader(tmp_path, "'single quoted' \"double quoted\" bare")

    assert reader.read_word() == "single quoted"
    assert reader.read_word() == "double quoted"
    assert reader.read_word() == "bare"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("+12", 12),
        ("-12", -12),
        ("1|2|4", 7),
    ],
)
def test_fread_number_matches_rom_signed_and_composed_numbers(
    tmp_path,
    source,
    expected,
):
    reader = make_reader(tmp_path, source)

    assert reader.read_number() == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("A", 1),
        ("a", 1 << 26),
        ("A|C", 5),
        ("-B", -2),
    ],
)
def test_fread_flag_matches_rom_letter_and_composition_rules(
    tmp_path,
    source,
    expected,
):
    reader = make_reader(tmp_path, source)

    assert reader.read_flag() == expected


def rom_object_with_affect(affect: str) -> str:
    return f"""object keywords~
an object~
An object lies here.~
iron~
trash 0 0
0 0 0 0 0
10 2 30 P
{affect}
"""


@pytest.mark.parametrize(
    ("destination", "expected_where"),
    [
        ("A", "TO_AFFECTS"),
        ("I", "TO_IMMUNE"),
        ("R", "TO_RESIST"),
        ("V", "TO_VULN"),
    ],
)
def test_rom_object_flag_affects_preserve_destination(
    tmp_path,
    destination,
    expected_where,
):
    reader = make_reader(tmp_path, rom_object_with_affect(f"F {destination} 7 -2 C"))

    item = reader.read_object(area_reader.dialects.rom.RomItem, vnum=100)

    assert len(item.affected) == 1
    affect = item.affected[0]
    assert affect.where == expected_where
    assert affect.location == 7
    assert affect.modifier == -2
    assert affect.bitvector == 4


def test_rom_object_plain_affect_uses_object_destination(tmp_path):
    reader = make_reader(tmp_path, rom_object_with_affect("A 7 -2"))

    item = reader.read_object(area_reader.dialects.rom.RomItem, vnum=100)

    assert len(item.affected) == 1
    affect = item.affected[0]
    assert affect.where == "TO_OBJECT"
    assert affect.location == 7
    assert affect.modifier == -2
    assert affect.bitvector == 0


def test_rom_object_rejects_unknown_flag_affect_destination(tmp_path):
    reader = make_reader(tmp_path, rom_object_with_affect("F X 7 -2 C"))
    reader.current_section_name = "objects"

    with pytest.raises(area_reader.ParseError, match="Bad where on flag set"):
        reader.read_object(area_reader.dialects.rom.RomItem, vnum=100)


def rom_mobile_with_flag_removal(flag_family: str) -> str:
    return f"""mob keywords~
a mobile~
A mobile stands here.~
A plain mobile.~
human~
AB AB 0 0
1 2 1d2+3 1d2+3 1d2+3 hit
1 2 3 4
AB AB AB AB
standing standing neutral 10
AB AB medium flesh
F {flag_family} A
"""


@pytest.mark.parametrize(
    ("flag_family", "field_name"),
    [
        ("act", "act"),
        ("aff", "affected_by"),
        ("off", "off_flags"),
        ("imm", "imm_flags"),
        ("res", "res_flags"),
        ("vul", "vuln_flags"),
        ("for", "form"),
        ("par", "parts"),
    ],
)
def test_rom_mobile_flag_removal_matches_engine_f_records(
    tmp_path,
    flag_family,
    field_name,
):
    reader = make_reader(tmp_path, rom_mobile_with_flag_removal(flag_family))

    mob = reader.read_object(area_reader.dialects.rom.RomMob, vnum=200)

    assert int(getattr(mob, field_name)) == 2
