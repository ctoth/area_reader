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
| GodWars Deluxe | `GodWarsAreaFile` | `dumps()` / `write()` | single `.are` file (`#AREA` or `#AREADATA`) |
| Devil's Silence (DSA) | `DsaAreaFile` | `dumps()` / `write()` | single `.are` file whose `#AREA` header starts `DSA Format~` |
| ACK!MUD | `AckAreaFile` | `dumps()` / `write()` | single `.are` file with a letter-keyed `#AREA` header (`K`/`L`/`N`/`I`/`V`...) |
| SMAUG | `SmaugAreaFile` | `dumps()` / `write()` | single tilde-delimited area file |
| SWR / FUSS | `SwrAreaFile` | `dumps()` / `write()` | single tilde-delimited area file |
| CircleMUD | `CircleAreaFile` | `dumps()` / `write()` | indexed world tree (`wld`/`mob`/`obj`/`zon`/`shp`) directory |
| tbaMUD | `TbaAreaFile` | `dumps()` / `write()` | indexed world tree (`zon`/`trg`/`wld`/`mob`/`obj`/`shp`/`qst`) directory |
| Medievia | `MedieviaAreaFile` | `dumps()` / `write()` | game tree with monolithic `lib/medievia.*` files and per-zone `lib/wld` room files |
| CoffeeMud | `CoffeeMudAreaFile` | `dumps()` / `write()` | `.cmare` XML export (areas, item/mob catalogs, nested boardable areas) |

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

ROM, Merc, SMAUG, and SWR/FUSS areas can be rendered to a canonical native form or written directly:

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
>>> tree = world.dumps()
>>> tree['wld/index']
>>> world.write('/path/to/canonical-circlemud')
```

For this multi-file format, `dumps()` returns an ordered mapping from paths
relative to `lib/world` to canonical native text. `write()` creates that tree,
including every family index. Index order, record-to-file membership, mobile
type, and shop version headers are part of the attrs model and survive a
semantic round trip.

### tbaMUD

tbaMUD retains CircleMUD's indexed tree but has its own native signature. Use
`TbaAreaFile` to preserve the four 32-bit flag banks, zone builder and level
metadata, DG triggers and attachments, string-valued zone variables, quests,
object levels and timers, and hidden exits.

```python
>>> import area_reader
>>> world = area_reader.TbaAreaFile('/path/to/tbamud')
>>> world.load_sections()
>>> world.area.triggers
>>> world.area.quests
>>> world.write('/path/to/canonical-tbamud')
```

Directory auto-detection distinguishes a tbaMUD tree from a CircleMUD tree by
its indexed `trg` or `qst` family.

### Medievia

Medievia uses one zone file to name its room files, monolithic tagged mobile
and object files, and a shop stream whose numeric headers are not unique.
Construct the reader with either the game root or its `lib` directory:

```python
>>> world = area_reader.MedieviaAreaFile('/path/to/Medievia')
>>> world.load_sections()
>>> world.area.rooms[100]
>>> tree = world.dumps()
>>> tree['medievia.zon']
>>> world.write('/path/to/canonical-medievia')
```

`dumps()` returns an ordered mapping relative to `lib`. Medievia-only room
restrictions, exit messages, stochastic mobile values, object deterioration,
variable reset arity, ignored historical tokens, terminal vnums, and duplicate
shop headers remain represented in the native model and survive a semantic
round trip.

### CoffeeMud

CoffeeMud `.cmare` files are XML exports. They may be full areas, item or mob
catalogs, or items (ships, caravans, castles) that embed nested boardable areas.
Native CoffeeMud identifiers (string room IDs such as `Coffee Grounds#73`, class
IDs such as `GenMob`) are preserved. Modeled tags live on typed attrs fields;
unknown or repeated tags remain ordered XML residuals on the owning object.

```python
>>> import area_reader
>>> coffee = area_reader.CoffeeMudAreaFile('monsters.cmare')
>>> coffee.load_sections()
>>> coffee.area.top_level
'MOBS'
>>> coffee.area.mobs[0].class_id
'GenMob'
>>> canonical = coffee.dumps()
>>> coffee.write('monsters-canonical.cmare')
```

CoffeeMud payload boundaries (`MTEXT`, `ITEXT`, `RTEXT`, and `EXDAT`) are
escaped once at the document boundary, including nested boardable areas. Typed
field edits are authoritative over the read-side `raw_text` and `raw_data`
views. The six upstream example and skill catalogs have semantic and canonical
fixed points and are accepted by CoffeeMud's native MOB/item loaders.

## Questions about a set of areas

`area-reader atlas` loads several ROM or Merc area files together and answers
one question about the set. Each path is an area file, or a directory whose
`*.are` files are all loaded. Answers are text; `--json` prints the same
answer as JSON. A file that does not parse stops the command with the parser's
error.

```
area-reader atlas summary test/rom
area-reader atlas reach --from 3001 [--rooms] [--with-portals] [--with-progs] test/rom
area-reader atlas links [--rooms] test/rom
area-reader atlas dangling test/rom
area-reader atlas depends test/rom
area-reader atlas path 3001 3472 test/rom
area-reader atlas find mota test/rom
```

- `summary`: counts per file, totals, and vnum ranges that overlap between files.
- `reach`: what a walk over exits from one room reaches, and what can walk
  back. `--with-portals` adds portals that an `O` reset places in a room;
  `--with-progs` adds `mob transfer` and `mob gtransfer` from the room an `M`
  reset loads the mob in.
- `links`: which areas have exits to which, and the links with no exit back.
- `dangling`: references to vnums no file defines (exits, keys, resets, shop
  keepers, specials, mob programs, portals, and vnums in `mob transfer`,
  `gtransfer`, `otransfer`, `goto`, `at`, `mload` and `oload` lines), and the
  exits whose destination is 0 or less.
- `depends`: the other areas each area refers to, by kind of reference.
- `path`: the shortest path between two rooms.
- `find`: rooms, mobs and objects by name or short description.

The same questions are functions of `area_reader.atlas`, each returning the
dictionary that `--json` prints.

`area-reader lint` judges ROM 2.4 area files: it lists their defects and
measures them. Each path is an area file or a directory of `*.are` files.
`--with` paths are loaded only so references into other areas resolve; they
get no findings. The files are read as ROM, and one that does not parse stops
the command with the parser's error.

```
area-reader lint [--json] [--with PATH ...] [--min-severity error|warning|info] PATH ...
area-reader lint new.are --with test/rom
```

A finding has a `rule` (a stable id such as `dangling-exit-key`), a `severity`
(`error`, `warning` or `info`), the `file`, a `kind` (`room`, `mob`, `object`,
`reset`, `shop`, `special`, `program` or `area`), a `vnum` or, for a reset, its
`index` among the file's resets counted from 0 without comment lines, and a
`message`. Text output is one line per finding under each file's name, then
the count per severity. `--json` prints `{"findings": [...], "counts": {...},
"metrics": {file: {...}}}`. `--min-severity` shortens the list of findings;
the counts always cover all of them. The exit status is 1 when there is any
error finding, else 0.

- Errors are what stops ROM booting or leaves a record that cannot work: a
  reference to a vnum nothing defines, a vnum outside the area's range or
  defined twice, resets out of order, an unknown spec function, item type,
  position, sex, size, liquid or section, a broken mob program, and an empty
  name, short description, room description or mob long description.
- Warnings are defects ROM runs with: one-way exits, doors that disagree
  between their two sides, rooms cut off from the rest, mobs, objects, keys
  and programs nothing loads or uses, shops without stock, mob hit points,
  damage and armor class far from the table in ROM's builder guide, and prose
  that is short, repeated, too wide or miscapitalized.
- Info notes levels outside the area's `{low high}` range, exits to nowhere,
  and descriptions that say a way leads where the room has no exit.
- Metrics, per file: record counts, exits per room, room description length,
  the shares of rooms with an extra description, of distinct room names and
  descriptions and of mobs with a program or spec function, doors, locked
  doors and keys, item type and sector counts, the mob level spread, and the
  type-token ratio of all description words.

`area_reader.lint.RULES` maps each rule id to its severity and its function;
`area_reader.lint.lint(atlas, targets)` returns the dictionary that `--json`
prints, for the entries of an atlas given as `targets`.

## Documentation

- `PROJECT.md` — the larger goal: a shared "virtual world algebra" across MUD dialects.
- `circlemud.md` — CircleMUD support plan.
- `coffeemud.md` — CoffeeMud support plan.
