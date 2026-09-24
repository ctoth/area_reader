from pathlib import Path

import area_reader
import area_reader.cli
import area_reader.dialects.ack

ACK_SAMPLE = Path("test/ack/ack_sample.are")


def load_ack(path: Path) -> area_reader.dialects.ack.AckAreaFile:
    area_file = area_reader.dialects.ack.AckAreaFile(path)
    area_file.load_sections()
    return area_file


def test_ack_letter_keyed_area_header_is_detected() -> None:
    assert area_reader.AckAreaFile is area_reader.dialects.ack.AckAreaFile
    assert area_reader.cli.detect_area_type(ACK_SAMPLE) is area_reader.dialects.ack.AckAreaFile


def test_ack_area_header_fields() -> None:
    area = load_ack(ACK_SAMPLE).area

    assert area.name == "@@GForest @@Wof @@dConfusion@@N"
    assert area.keyword == "forestconfusion"
    assert area.level_label == "@@W(@@r10 60@@W}@@N"
    assert area.area_number == 13
    assert (area.min_level, area.max_level) == (10, 60)
    assert (area.first_vnum, area.last_vnum) == (9600, 9799)
    assert (area.offset, area.reset_rate) == (32200, 15)
    assert area.owner == "stephen"
    assert (area.can_read, area.can_write) == ("stephen jer", "stephen jer")
    assert [(flag.letter, flag.text) for flag in area.flags] == [("T", "You can teleport into here")]


def test_ack_rooms_mobs_objects_and_resets() -> None:
    area_file = load_ack(ACK_SAMPLE)
    area = area_file.area

    assert not area_file.skipped_sections
    assert list(area.rooms) == [16001, 11300]
    secretary = area.rooms[16001]
    assert (secretary.room_flags, secretary.sector_type) == (8, 0)
    assert [(exit.door.value, exit.exit_info, exit.key, exit.destination) for exit in secretary.exits] == [
        (1, 0, -1, 16000),
        (3, 225, 16010, 16002),
    ]
    assert area.rooms[11300].sector_type is None

    inmate = area.mobs[16003]
    assert (inmate.act, inmate.affected_by, inmate.alignment) == (36700163, 65536, 250)
    assert (inmate.level, inmate.sex, inmate.ac_mod, inmate.hr_mod, inmate.dr_mod) == (57, 1, -160, 120, 100)
    assert (inmate.position, inmate.skills) == (7, 6158)
    assert [prog.trigger for prog in area.mobs[9623].mobprogs] == ["act_prog", "death_prog"]
    assert area.mobs[9623].mobprogs[0].arguments == "p opens the trapdoor."

    ring = area.objects[16000]
    assert (ring.item_type, ring.wear_flags, ring.item_apply, ring.value, ring.weight) == (9, 3, 1, [0, 0, 0, 0], 1)
    assert [(affect.location, affect.modifier) for affect in ring.affected] == [(13, 60), (17, -50)]
    assert ring.level == 60
    assert area.objects[16001].level is None

    assert [(reset.command, reset.arg1, reset.arg3) for reset in area.resets] == [
        ("M", 16003, 16001),
        ("E", 16001, 16),
        ("G", 16000, 0),
    ]
    assert [(objfun.arg1, objfun.arg2) for objfun in area.objfuns] == [(16001, "objfun_cast_fight")]


def test_ack_native_writer_round_trips(tmp_path: Path) -> None:
    source = load_ack(ACK_SAMPLE)
    source.area.mobs[9623].mobprogs[1].commands = "MPECHO changed\n"
    output = tmp_path / "ack.are"

    source.write(output)
    reparsed = load_ack(output)

    assert reparsed.area == source.area
    assert reparsed.dumps() == output.read_text(encoding="latin-1")
