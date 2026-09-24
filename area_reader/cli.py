"""Command-line interface for area-reader."""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import area_reader.dialects.circle
import area_reader.dialects.coffeemud
import area_reader.dialects.godwars
import area_reader.dialects.medievia
import area_reader.dialects.merc
import area_reader.dialects.rom
import area_reader.dialects.smaug
import area_reader.dialects.swr
import area_reader.dialects.tba
import area_reader.serialization

logger = logging.getLogger("area_reader")

SNIFF_SIZE = 64 * 1024
COFFEEMUD_ROOT = re.compile(r"<(?:AREA|MOBS?|ITEMS?|AROOMS?)\b", re.IGNORECASE)
SECTION = re.compile(r"(?m)^[ \t]*#([A-Z]+)\b", re.IGNORECASE)
AREA_SECTION = re.compile(r"(?m)^[ \t]*#AREA\b", re.IGNORECASE)
NEXT_NAMED_SECTION = re.compile(r"(?m)^[ \t]*#[A-Z$]+\b", re.IGNORECASE)
GODWARS_RECORD = re.compile(r"(?m)^[ \t]*[QT][ \t]*$")
MEDIEVIA_COMPONENTS = frozenset({"medievia.zon", "medievia.mob", "medievia.obj", "medievia.shp"})
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


def _looks_like_medievia_room(data):
    """Return whether the first record has Medievia's 4/4/3 room fields."""
    header = re.match(r"\s*#-?\d+[^\r\n]*(?:\r?\n)", data)
    if header is None:
        return False
    cursor = header.end()
    for _ in range(2):
        cursor = data.find("~", cursor)
        if cursor == -1:
            return False
        cursor += 1
    lines = [line.split() for line in data[cursor:].splitlines() if line.strip()][:3]
    if [len(line) for line in lines] != [4, 4, 3]:
        return False
    try:
        for line in lines:
            for value in line:
                int(value)
    except ValueError:
        return False
    return True


def detect_area_type(area_file_path):
    path = Path(area_file_path)
    if path.is_dir():
        direct_medievia = path / "medievia.zon"
        nested_medievia = path / "lib" / "medievia.zon"
        if direct_medievia.is_file() or nested_medievia.is_file():
            return area_reader.dialects.medievia.MedieviaAreaFile
        direct_index = path / "zon" / "index"
        nested_index = path / "lib" / "world" / "zon" / "index"
        if direct_index.is_file() or nested_index.is_file():
            world_root = path if direct_index.is_file() else path / "lib" / "world"
            if (world_root / "trg" / "index").is_file() or (world_root / "qst" / "index").is_file():
                return area_reader.dialects.tba.TbaAreaFile
            return area_reader.dialects.circle.CircleAreaFile
        raise ValueError(f"Could not detect area type for {path}")

    with path.open(mode="rt", encoding="latin-1") as area_file:
        data = area_file.read(SNIFF_SIZE)

    if path.name.lower() in MEDIEVIA_COMPONENTS or _looks_like_medievia_room(data):
        return area_reader.dialects.medievia.MedieviaAreaFile

    stripped = data.lstrip()
    if stripped.startswith("<?xml") or COFFEEMUD_ROOT.match(stripped):
        return area_reader.dialects.coffeemud.CoffeeMudAreaFile

    sections = {match.group(1).upper() for match in SECTION.finditer(data)}
    if "FUSSAREA" in sections:
        return area_reader.dialects.swr.SwrAreaFile
    if "AREADATA" in sections:
        godwars_fields = all(
            re.search(rf"(?mi)^[ \t]*{field}\b", data) for field in ("Builders", "VNUMs", "Security", "End")
        )
        if godwars_fields:
            return area_reader.dialects.godwars.GodWarsAreaFile
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
            if GODWARS_RECORD.search(data):
                return area_reader.dialects.godwars.GodWarsAreaFile
            return area_reader.dialects.merc.MercAreaFile

    raise ValueError(f"Could not detect area type for {path}")


DIALECTS = {
    "rom": area_reader.dialects.rom.RomAreaFile,
    "merc": area_reader.dialects.merc.MercAreaFile,
    "smaug": area_reader.dialects.smaug.SmaugAreaFile,
    "circle": area_reader.dialects.circle.CircleAreaFile,
    "tba": area_reader.dialects.tba.TbaAreaFile,
    "medievia": area_reader.dialects.medievia.MedieviaAreaFile,
    "godwars": area_reader.dialects.godwars.GodWarsAreaFile,
    "swr": area_reader.dialects.swr.SwrAreaFile,
    "coffeemud": area_reader.dialects.coffeemud.CoffeeMudAreaFile,
}
FALLBACK_DIALECTS = (
    area_reader.dialects.rom.RomAreaFile,
    area_reader.dialects.merc.MercAreaFile,
    area_reader.dialects.smaug.SmaugAreaFile,
)


def _parse(area_type, area_file_path):
    area_file = area_type(area_file_path)
    area_file.load_sections()
    return area_file


def load_area(area_file_path, dialect=None):
    """Parse an area and return the loaded area-file reader.

    ``dialect`` is a key of ``DIALECTS``, an area-file class, or ``None``.
    A given dialect is parsed as-is and its errors propagate.  With ``None``
    the detected dialect is tried first, then the ROM, Merc and SMAUG
    readers (files only); the first parse with rooms is returned.  When no
    parse has rooms, the first successful parse in that order is returned.
    When no candidate parses, the detected dialect's error is raised; when
    detection itself failed, its ``ValueError`` is raised, chained from the
    error of the fallback that got furthest into the file.
    """
    if isinstance(dialect, str):
        if dialect not in DIALECTS:
            raise ValueError(f"Unknown area dialect {dialect!r}; expected one of {', '.join(DIALECTS)}")
        dialect = DIALECTS[dialect]
    if dialect is not None:
        return _parse(dialect, area_file_path)

    try:
        detected = detect_area_type(area_file_path)
    except ValueError as error:
        detected = None
        detection_error = error
    candidates = [] if detected is None else [detected]
    if not Path(area_file_path).is_dir():
        candidates.extend(area_type for area_type in FALLBACK_DIALECTS if area_type is not detected)

    first_result = None
    detected_error = None
    furthest_error = None
    furthest_index = -1
    for area_type in candidates:
        area_file = None
        try:
            area_file = area_type(area_file_path)
            area_file.load_sections()
        except Exception as error:  # noqa: BLE001 - a failed candidate falls through to the next dialect
            logger.debug("%s could not parse %s: %s", area_type.__name__, area_file_path, error)
            if area_type is detected:
                detected_error = error
            index = getattr(area_file, "index", -1)
            if index > furthest_index:
                furthest_index = index
                furthest_error = error
            continue
        if area_file.area.rooms:
            return area_file
        if first_result is None:
            first_result = area_file

    if first_result is not None:
        return first_result
    if detected_error is not None:
        raise detected_error
    raise detection_error from furthest_error


def print_area(area_file_path, area_type=None):
    print(load_area(area_file_path, area_type).as_json())


def _error_payload(error, area_file_path):
    return {
        "error": getattr(error, "reason", None) or str(error),
        "file": getattr(error, "filename", None) or str(area_file_path),
        "line": getattr(error, "line", None),
        "column": getattr(error, "column", None),
        "section": getattr(error, "section", None),
    }


def build_parser():
    parser = argparse.ArgumentParser(prog="area-reader", description="Parse a MUD area and print it as JSON.")
    parser.add_argument(
        "--type",
        choices=("auto", *DIALECTS),
        default="auto",
        help="area dialect (default: detect it)",
    )
    parser.add_argument("path", help="area file or world directory")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    dialect = None if arguments.type == "auto" else arguments.type
    try:
        area_file = load_area(arguments.path, dialect)
    except Exception as error:  # noqa: BLE001 - every failure is reported as one JSON line
        print(json.dumps(_error_payload(error, arguments.path)), file=sys.stderr)
        return 1
    print(area_file.as_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
