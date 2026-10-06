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

## Writing new areas

A new ROM 2.4 area is written as a directory of YAML files and compiled to one
`.are` file. Nobody writes vnums, bit values, reset lines or wear-location
numbers: records have ids, flags have names, and what stands in a room is
written on the room. This needs PyYAML (`pip install area-reader[authoring]`).

```
area-reader build SRC [-o OUT.are] [--set DIR ...] [--show-defaults]
area-reader unbuild AREA.are -o SRC
```

`test/authoring/saltworks` is a complete ten-room example that uses every
feature; read it first. In outline:

```yaml
# area.yaml: the header. Every other *.yaml, *.yml or *.json file below the
# directory may hold rooms, mobs, objects and helps, and they are merged.
area:
  name: The Salt Works
  filename: saltworks.are
  levels: [5, 15]
  builders: Claude
  vnums: {first: 12000, size: 100}

rooms:
  gatehouse:
    name: The Gatehouse
    description: |
      Two stumpy towers of tarred timber flank a tunnel.
    sector: city
    flags: [indoors, law]
    exits:
      north: yard                    # makes yard's south exit too
      east: {to: tally-office, door: closed, keyword: door oak}
      west: 3001                     # a vnum in another area
      up: {look: The towers go up into the smoke.}
    mobs:
      - mob: gate-warden
        wears: {wield: boat-hook}
        carries: [store-key]
    objects:
      - object: salt-chest
        contains: [coin-purse]

mobs:
  gate-warden:
    keywords: warden gate guard
    short: the gate warden
    long: The gate warden leans on a boat-hook, counting carts.
    race: human
    level: 12                        # hit, mana, damage and ac follow from the level
    act: [sentinel, stay_area]
    special: spec_guard

objects:
  boat-hook:
    keywords: hook boat-hook
    short: a long boat-hook
    long: A boat-hook as long as a man lies here.
    type: weapon
    wear: [take, wield]
    weapon: {class: polearm, dice: 2d5, attack: pierce, flags: [two_hands]}
```

- **Ids and vnums.** An id is a lowercase slug, unique among the area's rooms,
  mobs or objects. `build` numbers ids from the header's block in the order
  they are first defined and records the numbers in `vnums.lock.yaml`, so a
  later record never renumbers an earlier one. `vnum:` on a record pins its
  number. A reference is an id, a bare vnum (any area), or `DIRNAME:id` for an
  id of another source directory named with `--set`.
- **Exits.** An exit to a room of the same area also makes the opposite exit,
  with the same door, keyword and key; `back:` overrides its description.
  `oneway: true` makes one side only. When both rooms write the exit they must
  agree on destination, door and key. `door` is `open`, `closed`, `locked`, or
  `reset_open` (opened again at each reset); closed and locked doors get their
  `D` resets on both sides.
- **Placements.** A room's `mobs` and `objects` become its `M`, `G`, `E`, `O`
  and `P` resets. `count` loads a mob several times; `limit`, `max_in_room`
  and `max_in_world` set the reset limits, which otherwise allow everything
  written. `random_exits: N` is an `R` reset.
- **Mobs.** A shop, a special procedure and mob programs are written on the
  mob. Omitted `hit`, `damage` and `ac` are the values recommended for the
  level in ROM's builder guide (Rom2.4.doc, Appendix A, with its adjustments
  for the four class flags); omitted `mana` is the median of the stock mobiles
  of that level; omitted `form` and `parts` are the race's. `--show-defaults`
  prints each filled value. In program code `@room:id`, `@mob:id` and
  `@object:id` become vnums.
- **Objects.** Each item type with meaningful values has a named form
  (`weapon`, `armor`, `container`, `drink`, `fountain`, `food`, `light`,
  `money`, `potion`, `pill`, `scroll`, `wand`, `staff`, `portal`, `furniture`);
  `values: [..five..]` is accepted for any type.
- **Raw escapes.** A flag list may be a number or a ROM letter string, and may
  hold numbers beside names. Top-level `resets`, `shops`, `specials` and
  `mobprogs` take raw records, emitted after the compiled ones.
- **Errors.** A fault raises `SourceError` naming the file and the key path,
  such as `rooms.gatehouse.exits.east.key`. `build` parses its own output with
  the ROM reader and writes nothing unless the result equals what it compiled.

`unbuild` writes any ROM area the reader parses in this form: ids slugged from
names, every vnum pinned, two-way exits collapsed, resets hung on their rooms.
For the 48 stock areas with rooms, building the unbuilt directory gives back
the parsed area up to `area_reader.authoring.NORMALIZATIONS` (reset order,
line comments, and a few values the engine never reads), and unbuilding that
gives the same files again. Resets the form cannot express stay in `raw.yaml`.

ROM keeps vnums in 16 bits, so a block for a ROM server stays below 32768
(`build` itself sets no limit). Stock ROM 2.4b6 reads neither `#AREADATA` nor
mob programs; they come with the OLC and MOBprogram patches, as in QuickMUD.
An area for the stock engine uses `header: rom` and no `programs`.
`scripts/verify_rom_writer.py UPSTREAM AREA.are --new` builds either engine
from its source tree, boots it with the new area, and fails on any bug the
engine logs that it does not log without the area.

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

## Documentation

- `PROJECT.md` — the larger goal: a shared "virtual world algebra" across MUD dialects.
- `circlemud.md` — CircleMUD support plan.
- `coffeemud.md` — CoffeeMud support plan.
