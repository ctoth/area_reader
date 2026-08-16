"""Command-line interface for area-reader."""

import sys

import area_reader.dialects.rom
import area_reader.serialization


def print_area(area_file_path, area_type=area_reader.dialects.rom.RomAreaFile):
    area_file = area_type(area_file_path)
    area_file.load_sections()
    print(area_file.as_json())


def main():
    if len(sys.argv) < 2:
        print("Must supply an area")
        sys.exit(1)
    print_area(sys.argv[1])
