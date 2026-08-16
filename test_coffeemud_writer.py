from pathlib import Path

import pytest
from attr import fields

import area_reader.dialects.coffeemud
from area_reader.native import NativeWriteError, render_record

UPSTREAM_COFFEEMUD = Path(r"C:\Users\Q\src\CoffeeMud")
COFFEEMUD_PATHS = tuple(
	UPSTREAM_COFFEEMUD / relative
	for relative in (
		Path("resources/examples/monsters.cmare"),
		Path("resources/examples/deities.cmare"),
		Path("resources/examples/junk.cmare"),
		Path("resources/skills/shipbuilding.cmare"),
		Path("resources/skills/caravanbuilding.cmare"),
		Path("resources/skills/clancastles.cmare"),
	)
	if (UPSTREAM_COFFEEMUD / relative).exists()
)


def load_coffeemud(path: Path) -> area_reader.CoffeeMudAreaFile:
	area_file = area_reader.CoffeeMudAreaFile(path)
	area_file.load_sections()
	return area_file


def parse_rendered_coffeemud(
	tmp_path: Path,
	text: str,
	name: str = "rendered.cmare",
) -> area_reader.CoffeeMudAreaFile:
	path = tmp_path / name
	path.write_text(text, encoding="latin-1")
	return load_coffeemud(path)


@pytest.mark.parametrize("source_path", COFFEEMUD_PATHS, ids=lambda path: path.name)
def test_coffeemud_corpus_has_semantic_and_canonical_fixed_points(
	tmp_path: Path,
	source_path: Path,
) -> None:
	source = load_coffeemud(source_path)

	rendered = source.dumps()
	reparsed = parse_rendered_coffeemud(tmp_path, rendered, source_path.name)

	assert reparsed.area == source.area
	assert reparsed.dumps() == rendered


def test_coffeemud_corpus_round_trip_is_non_vacuous() -> None:
	if not COFFEEMUD_PATHS:
		pytest.skip("upstream CoffeeMud corpus is unavailable")
	areas = [load_coffeemud(path).area for path in COFFEEMUD_PATHS]

	assert any(area.mobs for area in areas)
	assert any(area.items for area in areas)
	assert any(mob.behaviors for area in areas for mob in area.mobs)
	assert any(mob.abilities for area in areas for mob in area.mobs)
	assert any(mob.inner_residual for area in areas for mob in area.mobs)
	assert any(item.inner_residual for area in areas for item in area.items)
	assert any(item.nested_area for area in areas for item in area.items)
	assert any(
		room.exits
		for area in areas
		for item in area.items
		if item.nested_area is not None
		for room in item.nested_area.rooms.values()
	)


def test_coffeemud_write_uses_the_canonical_rendering(tmp_path: Path) -> None:
	if not COFFEEMUD_PATHS:
		pytest.skip("upstream CoffeeMud corpus is unavailable")
	source = load_coffeemud(COFFEEMUD_PATHS[0])
	output = tmp_path / "written.cmare"

	source.write(output)

	assert output.read_text(encoding="latin-1") == source.dumps()
	assert load_coffeemud(output).area == source.area


def test_coffeemud_typed_fields_override_stale_raw_views(tmp_path: Path) -> None:
	path = UPSTREAM_COFFEEMUD / "resources" / "examples" / "monsters.cmare"
	if not path.exists():
		pytest.skip("upstream CoffeeMud corpus is unavailable")
	source = load_coffeemud(path)
	mob = source.area.mobs[0]
	original_residual = tuple(mob.inner_residual)

	mob.name = "a declarative death dog"
	mob.money += 5
	mob.behaviors[0].parameters = "GUARD"
	mob.raw_text = "<NAME>stale raw text</NAME>"
	mob.raw_data["NAME"] = "stale raw data"
	reparsed = parse_rendered_coffeemud(tmp_path, source.dumps())

	assert reparsed.area == source.area
	assert reparsed.area.mobs[0].name == "a declarative death dog"
	assert reparsed.area.mobs[0].money == mob.money
	assert reparsed.area.mobs[0].behaviors[0].parameters == "GUARD"
	assert tuple(reparsed.area.mobs[0].inner_residual) == original_residual


def test_coffeemud_nested_area_fields_are_editable(tmp_path: Path) -> None:
	path = UPSTREAM_COFFEEMUD / "resources" / "skills" / "shipbuilding.cmare"
	if not path.exists():
		pytest.skip("upstream CoffeeMud corpus is unavailable")
	source = load_coffeemud(path)
	item = source.area.items[0]
	room = next(iter(item.nested_area.rooms.values()))

	item.name = "the declarative ship"
	item.nested_area.name = "Declarative Ship"
	room.display = "A Declarative Deck"
	reparsed = parse_rendered_coffeemud(tmp_path, source.dumps())

	assert reparsed.area == source.area
	assert reparsed.area.items[0].nested_area.name == "Declarative Ship"
	assert next(iter(reparsed.area.items[0].nested_area.rooms.values())).display == "A Declarative Deck"


def test_coffeemud_nested_payloads_have_one_xml_escape_boundary() -> None:
	path = UPSTREAM_COFFEEMUD / "resources" / "skills" / "shipbuilding.cmare"
	if not path.exists():
		pytest.skip("upstream CoffeeMud corpus is unavailable")
	source = load_coffeemud(path)
	room = next(iter(source.area.items[0].nested_area.rooms.values()))

	assert room.climate == -1
	rendered = source.dumps()
	assert "&lt;RTEXT&gt;&lt;RCLIM&gt;-1&lt;/RCLIM&gt;" in rendered
	assert "&lt;RTEXT&gt;&amp;lt;RCLIM" not in rendered


def test_coffeemud_unknown_xml_is_an_ordered_residual(tmp_path: Path) -> None:
	path = tmp_path / "unknown.cmare"
	path.write_text(
		"<MOBS><MOB><MCLAS>GenMob</MCLAS><MLEVL>1</MLEVL><MABLE>2</MABLE>"
		"<MREJV>3</MREJV><OUTER DATA=kept /><MTEXT>"
		"&lt;NAME&gt;a residual mob&lt;/NAME&gt;"
		"&lt;MYSTERY FLAG=&quot;yes&quot;&gt;&lt;VALUE&gt;7&lt;/VALUE&gt;&lt;/MYSTERY&gt;"
		"&lt;MYSTERY FLAG=&quot;again&quot; /&gt;"
		"</MTEXT></MOB></MOBS>",
		encoding="latin-1",
	)
	source = load_coffeemud(path)
	mob = source.area.mobs[0]

	assert len(mob.outer_residual) == 1
	assert len(mob.inner_residual) == 2
	reparsed = parse_rendered_coffeemud(tmp_path, source.dumps(), "unknown-rendered.cmare")

	assert reparsed.area == source.area
	assert 'DATA="kept"' in reparsed.area.mobs[0].outer_residual[0]
	assert 'FLAG="yes"' in reparsed.area.mobs[0].inner_residual[0]
	assert 'FLAG="again"' in reparsed.area.mobs[0].inner_residual[1]


def test_coffeemud_fields_own_their_native_xml_declarations() -> None:
	for record_type, field_names in (
		(area_reader.dialects.coffeemud.CoffeeMudMob, ("class_id", "level", "name", "behaviors", "inner_residual")),
		(area_reader.dialects.coffeemud.CoffeeMudItem, ("class_id", "uses", "name", "nested_area", "inner_residual")),
		(area_reader.dialects.coffeemud.CoffeeMudRoom, ("room_id", "display", "exits", "inner_residual")),
		(area_reader.dialects.coffeemud.CoffeeMudArea, ("class_id", "name", "raw_data", "rooms")),
	):
		declarations = {attribute.name: attribute.metadata.get("native") for attribute in fields(record_type)}
		assert all(declarations[name] is not None for name in field_names)


def test_coffeemud_native_normalization_ledger_is_explicit() -> None:
	assert area_reader.CoffeeMudAreaFile.NATIVE_NORMALIZATIONS == (
		"xml-declaration-and-whitespace",
		"empty-element-spelling",
		"unquoted-attribute-repair",
		"bare-ampersand-repair",
		"split-entity-repair",
		"mob-rejuvenation-tag-spelling",
	)


def test_coffeemud_rejects_malformed_residual_xml() -> None:
	mob = area_reader.dialects.coffeemud.CoffeeMudMob(inner_residual=["<BROKEN>"])

	with pytest.raises(NativeWriteError, match="residual XML"):
		render_record(mob)
