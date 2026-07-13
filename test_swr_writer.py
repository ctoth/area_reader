from pathlib import Path

import pytest

import area_reader
from area_reader.native import NativeWriteError, render_record


UPSTREAM_SWR = Path(r"C:\Users\Q\src\swrfuss")


def swr_paths() -> tuple[Path, ...]:
	area_list = UPSTREAM_SWR / "area" / "area.lst"
	if not area_list.exists():
		return ()
	return tuple(
		UPSTREAM_SWR / "area" / name
		for name in area_list.read_text(encoding="latin-1").splitlines()
		if name and name != "$"
	)


def load_swr(path: Path) -> area_reader.SwrAreaFile:
	area_file = area_reader.SwrAreaFile(path)
	area_file.load_sections()
	return area_file


def parse_rendered_swr(tmp_path: Path, text: str) -> area_reader.SwrAreaFile:
	path = tmp_path / "rendered.are"
	path.write_text(text, encoding="latin-1")
	return load_swr(path)


@pytest.mark.parametrize("source_path", swr_paths(), ids=lambda path: path.name)
def test_swr_engine_corpus_has_semantic_and_canonical_fixed_points(
	tmp_path: Path,
	source_path: Path,
) -> None:
	source = load_swr(source_path)

	rendered = source.dumps()
	reparsed = parse_rendered_swr(tmp_path, rendered)

	assert reparsed.area == source.area
	assert reparsed.skipped_sections == source.skipped_sections
	assert reparsed.dumps() == rendered


def test_fuss_records_have_native_identities_and_non_vacuous_residuals() -> None:
	paths = swr_paths()
	if not paths:
		pytest.skip("upstream SWR/FUSS corpus is unavailable")
	areas = [
		load_swr(path).area
		for path in paths
		if path.read_text(encoding="latin-1").lstrip().startswith("#FUSSAREA")
	]

	assert areas
	assert all(isinstance(area, area_reader.SwrArea) for area in areas)
	assert all(
		isinstance(mob, area_reader.SwrMobile)
		for area in areas
		for mob in area.mobs.values()
	)
	assert all(
		isinstance(item, area_reader.SwrObject)
		for area in areas
		for item in area.objects.values()
	)
	assert all(
		isinstance(room, area_reader.SwrRoom)
		for area in areas
		for room in area.rooms.values()
	)
	assert any(mob.programs for area in areas for mob in area.mobs.values())
	assert any(mob.shop_data for area in areas for mob in area.mobs.values())
	assert any(item.unknown for area in areas for item in area.objects.values())
	assert any(item.programs for area in areas for item in area.objects.values())
	assert any(room.exits for area in areas for room in area.rooms.values())
	assert any(room.resets for area in areas for room in area.rooms.values())


def test_swr_write_uses_the_canonical_rendering(tmp_path: Path) -> None:
	paths = swr_paths()
	if not paths:
		pytest.skip("upstream SWR/FUSS corpus is unavailable")
	source = load_swr(next(path for path in paths if path.name == "limbo.are"))
	output = tmp_path / "written.are"

	source.write(output)

	assert output.read_text(encoding="latin-1") == source.dumps()
	assert load_swr(output).area == source.area


def test_fuss_fields_are_editable_declaratively(tmp_path: Path) -> None:
	source = load_swr(UPSTREAM_SWR / "area" / "kashyyyk")
	mob = next(iter(source.area.mobs.values()))
	room = next(iter(source.area.rooms.values()))

	source.area.author = "A New Builder"
	mob.race = "Bothan"
	mob.level = 41
	room.sector = "forest"
	if room.exits:
		room.exits[0].distance += 1

	reparsed = parse_rendered_swr(tmp_path, source.dumps())

	assert reparsed.area == source.area


def test_swr_mobile_rejects_non_uniform_armor_class() -> None:
	mob = area_reader.SwrMobile(
		ac=area_reader.RomArmorClass(pierce=1, bash=2, slash=1, exotic=1),
	)

	with pytest.raises(NativeWriteError):
		render_record(mob)
