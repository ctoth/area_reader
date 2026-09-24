from pathlib import Path

import area_reader.cli
import area_reader.dialects.rom

ROT_SAMPLE = Path("test/rot/rot_sample.are")


def load_rom(path: Path) -> area_reader.dialects.rom.RomAreaFile:
    area_file = area_reader.dialects.rom.RomAreaFile(path)
    area_file.load_sections()
    return area_file


def test_rom_olc_areadata_with_rom_mobiles_is_detected_as_rom() -> None:
    assert area_reader.cli.detect_area_type(ROT_SAMPLE) is area_reader.dialects.rom.RomAreaFile


def test_areadata_header_and_rot_shielded_mobile() -> None:
    area_file = load_rom(ROT_SAMPLE)
    area = area_file.area

    assert not area_file.skipped_sections
    assert area.header_format == "areadata"
    assert area.name == "Glen Dhoo"
    assert area.builders == "None"
    assert (area.first_vnum, area.last_vnum, area.security) == (30800, 30899, 9)
    assert area.metadata == "[ 20  55] Kandahar Glen Dhoo"
    imp = area.mobs[30800]
    assert (imp.shielded_by, imp.alignment, imp.group) == (0, -500, 0)
    assert int(imp.affected_by) == 1 << 9  # J
    assert imp.level == 30
    assert area.mobprogs == {30800: "mob echo An {mimp{x follows you.\n"}


def test_areadata_native_writer_round_trips_header_shield_and_mobprogs(tmp_path: Path) -> None:
    source = load_rom(ROT_SAMPLE)
    source.area.mobs[30800].shielded_by = 4
    output = tmp_path / "rot.are"

    source.write(output)
    rendered = output.read_text(encoding="latin-1")
    reparsed = load_rom(output)

    assert rendered.startswith("#AREADATA\nName Glen Dhoo~\n")
    assert "#MOBPROGS\n#30800\n" in rendered
    assert reparsed.area == source.area
    assert reparsed.area.mobs[30800].shielded_by == 4
    assert reparsed.dumps() == rendered
