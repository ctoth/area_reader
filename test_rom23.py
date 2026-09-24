from pathlib import Path

import area_reader.cli
import area_reader.dialects.rom

ROM23_SAMPLE = Path("test/rom23/rom23_sample.are")


def load_rom(path: Path) -> area_reader.dialects.rom.RomAreaFile:
    area_file = area_reader.dialects.rom.RomAreaFile(path)
    area_file.load_sections()
    return area_file


def test_merc_header_with_rom_mobiles_is_detected_as_rom() -> None:
    assert area_reader.cli.detect_area_type(ROM23_SAMPLE) is area_reader.dialects.rom.RomAreaFile


def test_rom23_merc_header_s_marker_and_short_resets() -> None:
    area = load_rom(ROM23_SAMPLE).area

    assert area.header_format == "merc"
    assert area.name == area.metadata == "{ 5 15} Paulanka  Sesame Street"
    oscar = area.mobs[715]
    assert oscar.group is None
    assert (oscar.level, oscar.race, oscar.damtype, oscar.start_pos, oscar.sex) == (5, "muppet", "1", "8", "1")
    assert [(reset.command, reset.arg3, reset.arg4) for reset in area.resets] == [
        ("M", 715, None),
        ("G", 0, 0),
        ("M", 716, 1),
    ]


def test_rom_dice_tolerate_flat_numbers_and_negative_bonus_after_plus() -> None:
    bird = load_rom(ROM23_SAMPLE).area.mobs[716]

    assert (bird.mana.number, bird.mana.sides, bird.mana.bonus) == (0, 0, 100)
    assert (bird.damage.number, bird.damage.sides, bird.damage.bonus) == (1, 5, -1)


def test_rom23_native_writer_round_trips(tmp_path: Path) -> None:
    source = load_rom(ROM23_SAMPLE)
    output = tmp_path / "rom23.are"

    source.write(output)
    rendered = output.read_text(encoding="latin-1")
    reparsed = load_rom(output)

    assert rendered.startswith("#AREA\n{ 5 15} Paulanka  Sesame Street~\n#")
    assert reparsed.area == source.area
    assert reparsed.dumps() == rendered
