import json
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


def test_main_requires_an_area_path(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["area-reader"])

    with pytest.raises(SystemExit, match="1"):
        area_reader.cli.main()

    assert capsys.readouterr().out == "Must supply an area\n"


def test_main_delegates_the_supplied_path(monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "argv", ["area-reader", "example.are"])
    monkeypatch.setattr(area_reader.cli, "print_area", seen.append)

    area_reader.cli.main()

    assert seen == ["example.are"]


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
