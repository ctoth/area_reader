"""Command-line interface for area-reader."""

import re
import sys
from pathlib import Path

import area_reader.dialects.circle
import area_reader.dialects.coffeemud
import area_reader.dialects.merc
import area_reader.dialects.rom
import area_reader.dialects.smaug
import area_reader.dialects.swr
import area_reader.serialization

SNIFF_SIZE = 64 * 1024
COFFEEMUD_ROOT = re.compile(r"<(?:AREA|MOBS?|ITEMS?|AROOMS?)\b", re.IGNORECASE)
SECTION = re.compile(r"(?m)^[ \t]*#([A-Z]+)\b", re.IGNORECASE)
AREA_SECTION = re.compile(r"(?m)^[ \t]*#AREA\b", re.IGNORECASE)
NEXT_NAMED_SECTION = re.compile(r"(?m)^[ \t]*#[A-Z$]+\b", re.IGNORECASE)
SMAUG_SECTIONS = frozenset(
    {
        "AUTHOR",
        "CLIMATE",
        "CONTINENT",
        "CREDITS",
        "ECONOMY",
        "FLAGS",
        "RANGES",
        "REPAIRS",
        "RESETMSG",
        "SPELLLIMIT",
        "VERSION",
    }
)


def detect_area_type(area_file_path):
    path = Path(area_file_path)
    if path.is_dir():
        direct_index = path / "zon" / "index"
        nested_index = path / "lib" / "world" / "zon" / "index"
        if direct_index.is_file() or nested_index.is_file():
            return area_reader.dialects.circle.CircleAreaFile
        raise ValueError(f"Could not detect area type for {path}")

    with path.open(mode="rt", encoding="latin-1") as area_file:
        data = area_file.read(SNIFF_SIZE)

    stripped = data.lstrip()
    if stripped.startswith("<?xml") or COFFEEMUD_ROOT.match(stripped):
        return area_reader.dialects.coffeemud.CoffeeMudAreaFile

    sections = {match.group(1).upper() for match in SECTION.finditer(data)}
    if sections.intersection({"FUSSAREA", "AREADATA"}):
        return area_reader.dialects.swr.SwrAreaFile
    if sections.intersection(SMAUG_SECTIONS):
        return area_reader.dialects.smaug.SmaugAreaFile

    area_section = AREA_SECTION.search(data)
    if area_section is not None:
        area_metadata = data[area_section.end() :]
        next_section = NEXT_NAMED_SECTION.search(area_metadata)
        if next_section is not None:
            area_metadata = area_metadata[: next_section.start()]
        string_count = area_metadata.count("~")
        if string_count >= 3:
            return area_reader.dialects.rom.RomAreaFile
        if string_count == 1:
            return area_reader.dialects.merc.MercAreaFile

    raise ValueError(f"Could not detect area type for {path}")


def print_area(area_file_path, area_type=None):
    if area_type is None:
        area_type = detect_area_type(area_file_path)
    area_file = area_type(area_file_path)
    area_file.load_sections()
    print(area_file.as_json())


def main():
    if len(sys.argv) < 2:
        print("Must supply an area")
        sys.exit(1)
    print_area(sys.argv[1])
