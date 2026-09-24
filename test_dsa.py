from pathlib import Path

import area_reader
import area_reader.cli
import area_reader.dialects.dsa

DSA_SAMPLE = Path("test/dsa/dsa_sample.are")


def load_dsa(path: Path) -> area_reader.dialects.dsa.DsaAreaFile:
    area_file = area_reader.dialects.dsa.DsaAreaFile(path)
    area_file.load_sections()
    return area_file


def keyed(record) -> list[tuple[str, str]]:
    return [(line.key, line.value) for line in record.keyed]


def test_dsa_format_marker_is_detected() -> None:
    assert area_reader.DsaAreaFile is area_reader.dialects.dsa.DsaAreaFile
    assert area_reader.cli.detect_area_type(DSA_SAMPLE) is area_reader.dialects.dsa.DsaAreaFile


def test_dsa_header_and_bare_help_text() -> None:
    area_file = load_dsa(DSA_SAMPLE)
    area = area_file.area

    assert not area_file.skipped_sections
    assert (area.original_filename, area.name, area.metadata) == (
        "cloudkeep.are",
        "Cloud Keep",
        "[ 1 30] Monomach Cloud Keep",
    )
    assert (area.first_vnum, area.last_vnum) == (4700, 4799)
    assert [line.key for line in area.header_keyed] == ["Descr", "Bldrs", "Sec", "Levels", "Flags"]
    assert area.header_keyed[0].value == "No description.\n"
    assert area.header_keyed[3].value == "1 30"
    assert [help.text for help in area.helps] == [
        "Of all the giant races that exist in the realm, cloud giants are by far\nthe most civilized of the group.\n"
    ]


def test_dsa_mob_object_room_trailers_and_room_resets() -> None:
    area = load_dsa(DSA_SAMPLE).area

    child = area.mobs[4700]
    assert (child.race, child.shielded_by, child.alignment, child.level) == ("unique", 0, 200, 25)
    assert keyed(child) == []
    assert keyed(area.mobs[32200]) == [("Damroll", "70"), ("MaxWorld", "1"), ("Saves", "-40")]

    bhelliom = area.objects[32200]
    assert bhelliom.item_type == "weapon"
    assert [extra.keyword for extra in bhelliom.extra_descriptions] == ["bhelliom"]
    assert keyed(bhelliom) == [("Spec", "flaming"), ("MaxWorld", "5")]

    gate = area.rooms[4700]
    assert [(exit.destination, keyed(exit)) for exit in gate.exits] == [(4701, [("Flags", "AB")])]
    assert [
        (reset.command, reset.arg1, reset.arg2, reset.arg3, reset.arg4, reset.comment) for reset in gate.resets
    ] == [
        ("M", 4700, 1, 100, 0, "Load a child giant."),
        ("E", 32200, 16, 100, 0, ""),
    ]
    assert area.rooms[4701].resets == []


def test_dsa_native_writer_round_trips(tmp_path: Path) -> None:
    source = load_dsa(DSA_SAMPLE)
    source.area.rooms[4701].resets.append(area_reader.dialects.dsa.DsaReset(command="O", arg1=32200, arg2=1))
    output = tmp_path / "dsa.are"

    source.write(output)
    rendered = output.read_text(encoding="latin-1")
    reparsed = load_dsa(output)

    assert rendered.startswith("#AREA\nDSA Format~\ncloudkeep.are~\n")
    assert reparsed.area == source.area
    assert reparsed.dumps() == rendered
