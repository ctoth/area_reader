# Area Reader
[![CI](https://github.com/ctoth/area_reader/actions/workflows/ci.yml/badge.svg)](https://github.com/ctoth/area_reader/actions/workflows/ci.yml)

A Python library to parse MUD area files.

This project reads area files from old MUDs and presents them as Python objects.
The returned objects all use the [attrs](https://pypi.python.org/pypi/attrs) package, so it is
very easy to do things like render the entire tree of objects out as JSON or similar.

## Supported formats

| Format | Reader class | Native writer | Source shape |
|---|---|---|---|
| ROM | `RomAreaFile` | `dumps()` / `write()` | single tilde-delimited `.are` file |
| Merc | `MercAreaFile` | `dumps()` / `write()` | single tilde-delimited area file |
| SMAUG | `SmaugAreaFile` | `dumps()` / `write()` | single tilde-delimited area file |
| SWR / FUSS | `SwrAreaFile` | — | single tilde-delimited area file |
| CircleMUD | `CircleAreaFile` | — | indexed world tree (`wld`/`mob`/`obj`/`zon`/`shp`) directory |
| CoffeeMud | `CoffeeMudAreaFile` | — | `.cmare` XML export (areas, item/mob catalogs, nested boardable areas) |

## Example usage

Every reader exposes the same shape: construct it with a path, call
`load_sections()`, then read the parsed tree off `.area`.

### ROM / Merc / SMAUG / SWR

```python
>>> import area_reader
>>> area_file = area_reader.RomAreaFile('midgaard.are')
>>> area_file.load_sections()
>>> area_file.area
RomArea(name='Midgaard', metadata='{ All } Diku    Midgaard', original_filename='midgaard.are', first_vnum=3000, last_vnum=3399, ... )
```

ROM, Merc, and SMAUG areas can be rendered to a canonical native form or written directly:

```python
text = area_file.dumps()
area_file.write("midgaard-canonical.are")
```

The native writers preserve the parsed semantic model and reach a canonical
fixed point: parsing their output and rendering again produces the same model
and text. They do not claim byte-for-byte reproduction of source whitespace or
flag spelling. Native field order and codecs live on the existing attrs models,
and unrecognized source sections are retained as native sections.

### CircleMUD

CircleMUD splits a world across an indexed file tree, so the reader takes the
world root directory rather than a single file.

```python
>>> import area_reader
>>> world = area_reader.CircleAreaFile('/path/to/circlemud')
>>> world.load_sections()
>>> world.area
```

### CoffeeMud

CoffeeMud `.cmare` files are XML exports. They may be full areas, item or mob
catalogs, or items (ships, caravans, castles) that embed nested boardable areas.
Native CoffeeMud identifiers (string room IDs such as `Coffee Grounds#73`, class
IDs such as `GenMob`) are preserved, and unknown tags are kept as raw payloads.

```python
>>> import area_reader
>>> coffee = area_reader.CoffeeMudAreaFile('monsters.cmare')
>>> coffee.load_sections()
>>> coffee.area.top_level
'MOBS'
>>> coffee.area.mobs[0].class_id
'GenMob'
```

## Documentation

- `PROJECT.md` — the larger goal: a shared "virtual world algebra" across MUD dialects.
- `circlemud.md` — CircleMUD support plan.
- `coffeemud.md` — CoffeeMud support plan.
