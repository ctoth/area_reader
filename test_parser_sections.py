"""Regression tests for shared section mechanics in area_reader.parser."""

import json
from pathlib import Path

import pytest

import area_reader.dialects.merc
import area_reader.dialects.rom
import area_reader.parser

AREA_HEADER = "#AREA\nsocial.are~\nSocial test~\nBuilder~\n1 1\n"
DUPLICATE_ROOMS = "#ROOMS\n#100\nFirst~\nDesc~\n0 0 0\nS\n#100\nSecond~\nDesc~\n0 0 0\nS\n#0\n#$\n"


@pytest.mark.parametrize(
    ("reader_class", "header"),
    [
        (area_reader.dialects.rom.RomAreaFile, AREA_HEADER),
        (area_reader.dialects.merc.MercAreaFile, "#AREA Metadata~\n"),
    ],
)
def test_duplicate_room_vnums_overwrite_and_record_a_diagnostic(tmp_path, reader_class, header):
    path = tmp_path / "area.are"
    path.write_text(header + DUPLICATE_ROOMS, encoding="latin-1")
    reader = reader_class(path)
    reader.load_sections()

    assert reader.area.rooms[100].name == "Second"
    expected = [{"kind": "duplicate_vnum", "family": "rooms", "vnum": 100}]
    assert reader.diagnostics == expected
    assert reader.as_dict()["diagnostics"] == expected
    assert json.loads(reader.as_json())["diagnostics"] == expected


@pytest.mark.parametrize("family", ["mobs", "objects", "rooms"])
def test_store_vnum_records_duplicates_in_each_family(tmp_path, family):
    path = tmp_path / "area.are"
    path.write_text("#$\n", encoding="latin-1")
    reader = area_reader.dialects.rom.RomAreaFile(path)
    first, second = object(), object()

    reader.store_vnum(family, 7, first)
    reader.store_vnum(family, 8, first)
    reader.store_vnum(family, 7, second)

    assert getattr(reader.area, family)[7] is second
    assert reader.diagnostics == [{"kind": "duplicate_vnum", "family": family, "vnum": 7}]


def test_skipped_sections_are_recorded_as_diagnostics(tmp_path):
    reader = load_rom(tmp_path, AREA_HEADER + "#SOCIALS\nwave~\n#$\n")

    assert reader.skipped_sections == [("socials", "\nwave~\n")]
    assert reader.diagnostics == [{"kind": "skipped_section", "section": "socials"}]
    assert reader.as_dict()["diagnostics"] == reader.diagnostics


def test_clean_area_serializes_empty_diagnostics(tmp_path):
    reader = load_rom(tmp_path, AREA_HEADER + "#$\n")

    assert reader.as_dict()["diagnostics"] == []


def load_rom(tmp_path: Path, text: str) -> area_reader.dialects.rom.RomAreaFile:
    path = tmp_path / "area.are"
    path.write_text(text, encoding="latin-1")
    reader = area_reader.dialects.rom.RomAreaFile(path)
    reader.load_sections()
    return reader


def test_unknown_section_body_keeps_hashes_that_do_not_start_a_section(tmp_path):
    body = "\nwave~\nfoo says #hi~\n#hi there~\n"
    reader = load_rom(tmp_path, AREA_HEADER + "#SOCIALS" + body + "#$\n")

    assert reader.skipped_sections == [("socials", body)]


def test_unknown_section_stops_at_the_next_section_header(tmp_path):
    body = "\nfoo says #hi~\n"
    text = AREA_HEADER + "#SOCIALS" + body + "#ROOMS\n#100\nRoom~\nDesc~\n0 0 0\nS\n#0\n#$\n"
    reader = load_rom(tmp_path, text)

    assert reader.skipped_sections == [("socials", body)]
    assert list(reader.area.rooms) == [100]


def test_unknown_section_runs_to_end_of_file_without_a_following_header(tmp_path):
    body = "\nfoo says #hi~\n"
    path = tmp_path / "area.are"
    path.write_text("#SOCIALS" + body, encoding="latin-1")
    reader = area_reader.dialects.rom.RomAreaFile(path)
    reader.read_section_name()

    reader.skip_section("socials")

    assert reader.skipped_sections == [("socials", body)]
    assert reader.index == len(reader.data)
