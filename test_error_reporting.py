"""Regression tests for issue #12: section readers must not hide the real diagnostic."""

from pathlib import Path

import pytest

import area_reader.parser


def write_area(tmp_path: Path, text: str, name: str = "broken.are") -> Path:
	path = tmp_path / name
	path.write_text(text, encoding="latin-1")
	return path


def test_rom_section_error_keeps_the_specific_parse_message(tmp_path):
	path = write_area(tmp_path, "#MOBILES\n#3000\nguard~\nA guard\n")
	reader = area_reader.RomAreaFile(path)

	with pytest.raises(area_reader.parser.ParseError) as caught:
		reader.load_sections()

	assert "Unterminated string" in str(caught.value)
	assert "Error reading section" not in str(caught.value)


def test_smaug_section_error_keeps_the_specific_parse_message(tmp_path):
	path = write_area(tmp_path, "#MOBILES\n#3000\nguard~\nA guard\n")
	reader = area_reader.SmaugAreaFile(path)

	with pytest.raises(area_reader.parser.ParseError) as caught:
		reader.load_sections()

	assert "Unterminated string" in str(caught.value)
	assert "Error reading section" not in str(caught.value)


def test_non_parse_errors_are_reported_with_the_original_error(tmp_path, monkeypatch):
	path = write_area(tmp_path, "#MOBILES\n#0\n\n#$\n")
	reader = area_reader.RomAreaFile(path)

	def exploding_reader():
		raise RuntimeError("internal boom")

	monkeypatch.setattr(reader, "load_mobiles", exploding_reader)

	with pytest.raises(area_reader.parser.ParseError) as caught:
		reader.load_sections()

	assert "Error reading section 'mobiles'" in str(caught.value)
	assert "internal boom" in str(caught.value)


@pytest.mark.parametrize("reader_class", ["SmaugAreaFile", "SwrAreaFile"])
def test_vnum_section_tolerates_a_trailing_hash_at_end_of_file(tmp_path, reader_class):
	path = write_area(tmp_path, "#MOBILES\n#", name="trailing.are")
	reader = getattr(area_reader, reader_class)(path)

	reader.load_sections()

	assert reader.area.mobs == {}


def test_circle_record_header_rejects_a_non_numeric_vnum(tmp_path):
	path = tmp_path / "broken.wld"
	path.write_text("#\nname~\n", encoding="latin-1")
	reader = area_reader.CircleAreaFile(tmp_path)
	reader.open_circle_file(path)

	with pytest.raises(area_reader.parser.ParseError, match="Expected numeric record header"):
		reader.read_record_header()
