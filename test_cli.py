import json
import subprocess
import sys
from pathlib import Path

import pytest

import area_reader.cli
import area_reader.dialects.circle
import area_reader.dialects.coffeemud
import area_reader.dialects.merc
import area_reader.dialects.rom
import area_reader.dialects.smaug
import area_reader.dialects.swr
import area_reader.parser


@pytest.mark.parametrize(
    ("contents", "area_type"),
    [
        ("<?xml version='1.0'?><AREA />", area_reader.dialects.coffeemud.CoffeeMudAreaFile),
        ("<MOBS />", area_reader.dialects.coffeemud.CoffeeMudAreaFile),
        ("#FUSSAREA\n#AREADATA\n", area_reader.dialects.swr.SwrAreaFile),
        ("#AREADATA\n", area_reader.dialects.swr.SwrAreaFile),
        ("#AREA\nSMAUG Test~\n#VERSION 1\n", area_reader.dialects.smaug.SmaugAreaFile),
        ("#AREA SMAUG Test~\n#AUTHOR Builder~\n", area_reader.dialects.smaug.SmaugAreaFile),
        ("#AREA\nair.are~\nIn the Air~\nMetadata~\n1000 1099\n#MOBILES\n", area_reader.dialects.rom.RomAreaFile),
        ("#AREA Metadata~\n#MOBILES\n", area_reader.dialects.merc.MercAreaFile),
    ],
)
def test_detect_area_type_from_file_signatures(tmp_path, contents, area_type):
    path = tmp_path / "area"
    path.write_text(contents, encoding="latin-1")

    assert area_reader.cli.detect_area_type(path) is area_type


def test_detect_area_type_from_circle_world_tree(tmp_path):
    (tmp_path / "lib" / "world" / "zon").mkdir(parents=True)
    (tmp_path / "lib" / "world" / "zon" / "index").write_text("$\n", encoding="latin-1")

    assert area_reader.cli.detect_area_type(tmp_path) is area_reader.dialects.circle.CircleAreaFile


def test_detect_area_type_rejects_unknown_content(tmp_path):
    path = tmp_path / "unknown.are"
    path.write_text("not an area file\n", encoding="latin-1")

    with pytest.raises(ValueError, match="Could not detect area type"):
        area_reader.cli.detect_area_type(path)


MERC_ROOM_AREA = "#AREA Metadata~\n#ROOMS\n#100\nRoom~\nDesc~\n0 0 0\nS\n#0\n#$\n"


def test_main_requires_an_area_path(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["area-reader"])

    with pytest.raises(SystemExit) as caught:
        area_reader.cli.main()

    assert caught.value.code == 2
    assert capsys.readouterr().out == ""


def test_main_prints_json_for_the_supplied_path(capsys):
    area_path = next(iter(sorted(Path("test/rom").glob("*.are"))))

    assert area_reader.cli.main([str(area_path)]) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["name"]
    assert captured.err == ""


def test_main_honours_an_explicit_type(tmp_path, capsys):
    path = tmp_path / "area"
    path.write_text(MERC_ROOM_AREA, encoding="latin-1")

    assert area_reader.cli.main(["--type", "merc", str(path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert list(payload["rooms"]) == ["100"]


def test_main_reports_parse_errors_as_one_json_line_on_stderr(tmp_path, capsys):
    path = tmp_path / "broken.are"
    path.write_text("#MOBILES\n#3000\nguard~\nA guard\n", encoding="latin-1")

    assert area_reader.cli.main(["--type", "rom", str(path)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "error": "Unterminated string",
        "file": str(path),
        "line": 5,
        "column": 1,
        "section": "mobiles",
    }


def test_main_reports_undetectable_files_as_json(tmp_path, capsys):
    path = tmp_path / "unknown.are"
    path.write_text("not an area file\n", encoding="latin-1")

    assert area_reader.cli.main([str(path)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert "Could not detect area type" in payload["error"]
    assert payload["file"] == str(path)
    assert payload["line"] is None
    assert payload["column"] is None
    assert payload["section"] is None


def test_main_rejects_an_unknown_type(capsys):
    with pytest.raises(SystemExit) as caught:
        area_reader.cli.main(["--type", "diku", "example.are"])

    assert caught.value.code == 2


def test_cli_module_runs_as_a_script():
    area_path = next(iter(sorted(Path("test/merc").glob("*.are"))))

    completed = subprocess.run(
        [sys.executable, "-m", "area_reader.cli", str(area_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr[-500:]
    assert json.loads(completed.stdout)["metadata"]


def test_load_area_uses_an_explicit_dialect_name(tmp_path):
    path = tmp_path / "area"
    path.write_text(MERC_ROOM_AREA, encoding="latin-1")

    reader = area_reader.cli.load_area(path, dialect="merc")

    assert type(reader) is area_reader.dialects.merc.MercAreaFile
    assert list(reader.area.rooms) == [100]


def test_load_area_uses_an_explicit_dialect_class(tmp_path):
    path = tmp_path / "area"
    path.write_text(MERC_ROOM_AREA, encoding="latin-1")

    reader = area_reader.cli.load_area(path, dialect=area_reader.dialects.merc.MercAreaFile)

    assert type(reader) is area_reader.dialects.merc.MercAreaFile


def test_load_area_rejects_an_unknown_dialect_name(tmp_path):
    with pytest.raises(ValueError, match="Unknown area dialect"):
        area_reader.cli.load_area(tmp_path / "area", dialect="diku")


def test_load_area_returns_the_detected_parse_when_it_has_rooms():
    area_path = next(iter(sorted(Path("test/rom").glob("*.are"))))

    reader = area_reader.cli.load_area(area_path)

    assert type(reader) is area_reader.dialects.rom.RomAreaFile
    assert reader.area.rooms


def test_load_area_falls_back_when_the_detected_parse_fails(tmp_path, monkeypatch):
    path = tmp_path / "area"
    path.write_text(MERC_ROOM_AREA, encoding="latin-1")
    monkeypatch.setattr(area_reader.cli, "detect_area_type", lambda _path: area_reader.dialects.smaug.SmaugAreaFile)

    def failing_load(self):
        raise area_reader.parser.ParseError("forced failure")

    monkeypatch.setattr(area_reader.dialects.smaug.SmaugAreaFile, "load_sections", failing_load)
    monkeypatch.setattr(area_reader.dialects.rom.RomAreaFile, "load_sections", failing_load)

    reader = area_reader.cli.load_area(path)

    assert type(reader) is area_reader.dialects.merc.MercAreaFile
    assert list(reader.area.rooms) == [100]


def test_load_area_falls_back_when_detection_fails(tmp_path, monkeypatch):
    path = tmp_path / "area"
    path.write_text(MERC_ROOM_AREA, encoding="latin-1")

    def undetectable(_path):
        raise ValueError("Could not detect area type")

    monkeypatch.setattr(area_reader.cli, "detect_area_type", undetectable)

    reader = area_reader.cli.load_area(path)

    assert reader.area.rooms


def test_load_area_keeps_the_first_successful_roomless_parse():
    reader = area_reader.cli.load_area(Path("test/merc/help.are"))

    assert type(reader) is area_reader.dialects.rom.RomAreaFile
    assert not reader.area.rooms
    assert reader.area.helps


def test_load_area_keeps_a_roomless_detected_parse(tmp_path):
    path = tmp_path / "helps.are"
    path.write_text("#AREA Metadata~\n#HELPS\n0 SUMMARY~\nHelp text.\n~\n0 $~\n#$\n", encoding="latin-1")

    reader = area_reader.cli.load_area(path)

    assert type(reader) is area_reader.dialects.merc.MercAreaFile
    assert reader.area.helps


def test_load_area_raises_the_detected_dialects_error_when_nothing_parses(tmp_path):
    path = tmp_path / "broken.are"
    path.write_text("#AREA Metadata~\n#MOBILES\n#3000\nguard~\nA guard\n", encoding="latin-1")

    with pytest.raises(area_reader.parser.ParseError, match="Unterminated string"):
        area_reader.cli.load_area(path)


def test_print_area_emits_json(capsys):
    area_path = next(iter(sorted(Path("test/rom").glob("*.are"))))

    area_reader.cli.print_area(area_path)

    payload = json.loads(capsys.readouterr().out)
    assert payload["name"]


def test_print_area_autodetects_merc(capsys):
    area_path = next(iter(sorted(Path("test/merc").glob("*.are"))))

    area_reader.cli.print_area(area_path)

    payload = json.loads(capsys.readouterr().out)
    assert payload["metadata"]


@pytest.mark.parametrize(
    "contents",
    [
        "#AREA\nSMAUG Test~\n#VERSION 1\n#MOBILES\n#0\n#ROOMS\n#0\n#$\n",
        "#FUSSAREA\n#AREADATA\nName SWR Test~\n#ENDAREADATA\n#ENDAREA\n",
        "<MOBS />",
    ],
)
def test_print_area_autodetects_other_single_file_dialects(tmp_path, capsys, contents):
    path = tmp_path / "area"
    path.write_text(contents, encoding="latin-1")

    area_reader.cli.print_area(path)

    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_print_area_autodetects_circle_world_tree(tmp_path, capsys):
    (tmp_path / "lib" / "world" / "zon").mkdir(parents=True)
    (tmp_path / "lib" / "world" / "zon" / "index").write_text("$\n", encoding="latin-1")

    area_reader.cli.print_area(tmp_path)

    assert isinstance(json.loads(capsys.readouterr().out), dict)
