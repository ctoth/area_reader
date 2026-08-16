import json
import sys
from pathlib import Path

import pytest

import area_reader.cli


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
