"""Regression tests for shared section mechanics in area_reader.parser."""

from pathlib import Path

import pytest

import area_reader.dialects.rom
import area_reader.parser

AREA_HEADER = "#AREA\nsocial.are~\nSocial test~\nBuilder~\n1 1\n"


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
