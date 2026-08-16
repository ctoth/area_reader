from pathlib import Path

import pytest
from attr import fields

import area_reader.dialects.circle
from area_reader import constants
from area_reader.native import NativeWriteError, render_record

UPSTREAM_CIRCLE = Path(r"C:\Users\Q\src\circlemud")


def load_circle(root: Path) -> area_reader.dialects.circle.CircleAreaFile:
    area_file = area_reader.dialects.circle.CircleAreaFile(root)
    area_file.load_sections()
    return area_file


def parse_rendered_circle(
    tmp_path: Path,
    tree: dict[str, str],
) -> area_reader.dialects.circle.CircleAreaFile:
    root = tmp_path / "circle"
    world = root / "lib" / "world"
    for relative_path, text in tree.items():
        path = world / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="latin-1")
    return load_circle(root)


def test_circle_corpus_has_semantic_and_canonical_fixed_points(tmp_path: Path) -> None:
    if not (UPSTREAM_CIRCLE / "lib" / "world").exists():
        pytest.skip("upstream CircleMUD corpus is unavailable")
    source = load_circle(UPSTREAM_CIRCLE)

    rendered = source.dumps()
    reparsed = parse_rendered_circle(tmp_path, rendered)

    assert reparsed.area == source.area
    assert reparsed.dumps() == rendered


def test_circle_corpus_round_trip_is_non_vacuous() -> None:
    if not (UPSTREAM_CIRCLE / "lib" / "world").exists():
        pytest.skip("upstream CircleMUD corpus is unavailable")
    area = load_circle(UPSTREAM_CIRCLE).area

    assert set(area.indexes) == {"zon", "wld", "mob", "obj", "shp"}
    assert all(area.indexes[family] for family in area.indexes)
    assert len(area.zones) > 0
    assert len(area.rooms) > 0
    assert len(area.mobs) > 0
    assert len(area.objects) > 0
    assert len(area.shops) > 0
    assert any(room.exits for room in area.rooms.values())
    assert any(room.extra_descriptions for room in area.rooms.values())
    assert any(mob.mob_type == "E" for mob in area.mobs.values())
    assert any(mob.especs for mob in area.mobs.values())
    assert any(item.affected for item in area.objects.values())
    assert any(item.extra_descriptions for item in area.objects.values())
    assert all(record.source_file for record in area.zones.values())
    assert all(record.source_file for record in area.rooms.values())
    assert all(record.source_file for record in area.mobs.values())
    assert all(record.source_file for record in area.objects.values())
    assert all(record.source_file for record in area.shops.values())
    assert set(area.shop_headers) == set(area.indexes["shp"])


def test_circle_write_uses_the_canonical_tree(tmp_path: Path) -> None:
    if not (UPSTREAM_CIRCLE / "lib" / "world").exists():
        pytest.skip("upstream CircleMUD corpus is unavailable")
    source = load_circle(UPSTREAM_CIRCLE)
    output = tmp_path / "written"

    source.write(output)

    for relative_path, text in source.dumps().items():
        assert (output / "lib" / "world" / relative_path).read_text(encoding="latin-1") == text
    assert load_circle(output).area == source.area


def test_circle_fields_are_declarative_and_editable(tmp_path: Path) -> None:
    if not (UPSTREAM_CIRCLE / "lib" / "world").exists():
        pytest.skip("upstream CircleMUD corpus is unavailable")
    source = load_circle(UPSTREAM_CIRCLE)
    room = next(iter(source.area.rooms.values()))
    mob = next(iter(source.area.mobs.values()))
    item = next(iter(source.area.objects.values()))
    zone = next(iter(source.area.zones.values()))
    shop = next(iter(source.area.shops.values()))

    room.name = "A Declarative Room"
    mob.short_desc = "a declarative mobile"
    item.cost += 1
    zone.lifespan += 1
    shop.profit_buy += 0.25
    reparsed = parse_rendered_circle(tmp_path, source.dumps())

    assert reparsed.area == source.area
    for record_type, field_names in (
        (area_reader.dialects.circle.CircleRoom, ("vnum", "name", "description", "exits")),
        (area_reader.dialects.circle.CircleMob, ("vnum", "name", "hitroll", "ac", "especs")),
        (area_reader.dialects.circle.CircleItem, ("vnum", "name", "value", "affected")),
        (area_reader.dialects.circle.CircleZone, ("vnum", "name", "resets")),
        (area_reader.dialects.circle.CircleShop, ("vnum", "products", "messages", "rooms")),
    ):
        declarations = {attribute.name: attribute.metadata.get("native") for attribute in fields(record_type)}
        assert all(declarations[name] is not None for name in field_names)


def test_circle_native_loss_ledger_has_executable_comment_witness(tmp_path: Path) -> None:
    assert area_reader.dialects.circle.CircleAreaFile.NATIVE_NORMALIZATIONS == (
        "comments",
        "whitespace-and-line-endings",
        "numeric-versus-alphabetic-flags",
        "room-and-object-metadata-order",
        "optional-second-shop-window",
        "dice-zero-bonus-spelling",
    )
    areas = []
    for name, comment in (("left", "first comment"), ("right", "changed comment")):
        root = tmp_path / name / "lib" / "world"
        zone = root / "zon"
        zone.mkdir(parents=True)
        (zone / "index").write_text("1.zon\n$\n", encoding="latin-1")
        (zone / "1.zon").write_text(
            f"#1\nA Zone~\n100 199 30 2\n* {comment}\nS\n$\n",
            encoding="latin-1",
        )
        areas.append(load_circle(tmp_path / name))

    assert areas[0].area == areas[1].area
    assert areas[0].dumps() == areas[1].dumps()


@pytest.mark.parametrize(
    "exit_info",
    (
        constants.EXIT_FLAGS.PICKPROOF,
        constants.EXIT_FLAGS.ISDOOR | constants.EXIT_FLAGS.NOPASS,
    ),
)
def test_circle_exit_rejects_flags_without_a_native_lock_code(exit_info) -> None:
    exit = area_reader.dialects.circle.CircleExit(exit_info=exit_info)

    with pytest.raises(NativeWriteError):
        render_record(exit)


def test_circle_mobile_rejects_non_integral_source_armor_class() -> None:
    mob = area_reader.dialects.circle.CircleMob(ac=15)

    with pytest.raises(NativeWriteError):
        render_record(mob)


def test_circle_object_rejects_a_non_native_value_shape() -> None:
    item = area_reader.dialects.circle.CircleItem(value=[1, 2, 3])

    with pytest.raises(NativeWriteError, match="exactly four integers"):
        render_record(item)


@pytest.mark.parametrize(
    ("reset", "message"),
    (
        (area_reader.dialects.circle.CircleReset(command="G", arg3=1), "must omit arg3"),
        (area_reader.dialects.circle.CircleReset(command="M", arg3=None), "requires arg3"),
        (area_reader.dialects.circle.CircleReset(command="X", arg3=None), "unsupported"),
    ),
)
def test_circle_reset_rejects_non_native_command_shapes(reset, message) -> None:
    with pytest.raises(NativeWriteError, match=message):
        render_record(reset)
