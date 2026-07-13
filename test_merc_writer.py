from pathlib import Path

import pytest

import area_reader
from area_reader.native import NativeWriteError, render_record


MERC_CORPUS = tuple(sorted(Path("test/merc").glob("*.are")))
UPSTREAM_MERC_CORPUS = Path(r"C:\Users\Q\src\merc-mud\area")


def load_merc(path: Path) -> area_reader.MercAreaFile:
	area_file = area_reader.MercAreaFile(path)
	area_file.load_sections()
	return area_file


def parse_rendered_merc(tmp_path: Path, text: str) -> area_reader.MercAreaFile:
	path = tmp_path / "rendered.are"
	path.write_text(text, encoding="latin-1")
	return load_merc(path)


@pytest.mark.parametrize("source_path", MERC_CORPUS, ids=lambda path: path.name)
def test_merc_corpus_has_semantic_and_canonical_fixed_points(
	tmp_path: Path,
	source_path: Path,
) -> None:
	source = load_merc(source_path)

	rendered = source.dumps()
	reparsed = parse_rendered_merc(tmp_path, rendered)

	assert reparsed.area == source.area
	assert reparsed.skipped_sections == source.skipped_sections
	assert reparsed.dumps() == rendered


def test_merc_corpus_round_trip_is_non_vacuous() -> None:
	areas = [load_merc(path).area for path in MERC_CORPUS]

	assert any(area.metadata for area in areas)
	assert sum(len(area.helps) for area in areas) > 0
	assert sum(len(area.rooms) for area in areas) > 0
	assert sum(len(area.mobs) for area in areas) > 0
	assert sum(len(area.objects) for area in areas) > 0
	assert sum(len(area.resets) for area in areas) > 0


def test_upstream_merc_corpus_has_semantic_fixed_point_when_available(
	tmp_path: Path,
) -> None:
	if not UPSTREAM_MERC_CORPUS.exists():
		pytest.skip("upstream Merc corpus is unavailable")

	paths = tuple(sorted(UPSTREAM_MERC_CORPUS.glob("*.are")))
	assert paths
	for index, source_path in enumerate(paths):
		source = load_merc(source_path)
		output = tmp_path / f"{index}.are"
		output.write_text(source.dumps(), encoding="latin-1")
		reparsed = load_merc(output)
		assert reparsed.area == source.area, source_path
		assert reparsed.skipped_sections == source.skipped_sections, source_path


def test_merc_write_uses_the_canonical_rendering(tmp_path: Path) -> None:
	source = load_merc(MERC_CORPUS[0])
	output = tmp_path / "written.are"

	source.write(output)

	assert output.read_text(encoding="latin-1") == source.dumps()
	assert load_merc(output).area == source.area


def test_merc_mobile_preserves_xp(tmp_path: Path) -> None:
	path = tmp_path / "mobile.are"
	path.write_text(
		"""#AREA
Merc test~
#MOBILES
#1
mob~
a mob~
A mob is here.~
A mob.~
1 0 0 S
5 2 3 1d4+5 2d6+7
8 9
10 11 1
#0
#$
""",
		encoding="latin-1",
	)

	area_file = load_merc(path)

	assert area_file.area.mobs[1].xp == 9
	assert parse_rendered_merc(tmp_path, area_file.dumps()).area == area_file.area


def test_merc_object_preserves_action_and_rent(tmp_path: Path) -> None:
	path = tmp_path / "object.are"
	path.write_text(
		"""#AREA
Merc test~
#OBJECTS
#1
object~
an object~
An object is here.~
An action.~
1 2 3
4 5 6 7
8 9 10
#0
#$
""",
		encoding="latin-1",
	)

	area_file = load_merc(path)
	item = area_file.area.objects[1]

	assert item.action_description == "An action."
	assert item.cost_per_day == 10
	assert parse_rendered_merc(tmp_path, area_file.dumps()).area == area_file.area


def test_merc_exit_rejects_rom_only_lock_states() -> None:
	exit = area_reader.MercExit(
		door=0,
		exit_info=area_reader.EXIT_FLAGS.ISDOOR | area_reader.EXIT_FLAGS.NOPASS,
	)

	with pytest.raises(NativeWriteError):
		render_record(exit)
