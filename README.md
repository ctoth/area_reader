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
  vnums: {first: 30000, size: 100}

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

Stock ROM 2.4b6 reads neither `#AREADATA` nor mob programs (they come with
the OLC and MOBprogram patches) and keeps vnums in 16 bits, so an area meant
for it uses `header: rom`, no `programs`, and a block below 32768.
`scripts/verify_rom_writer.py UPSTREAM AREA.are --new` boots the real engine
with a new area and fails on any bug the engine logs because of it.

## Reading an area as a visitor

```
area-reader walk [--from VNUM] [--anonymous] [--with PATH ...] AREA.are
```

`walk` writes one ROM area out room by room, in the order a walk from the way
in meets them: each room's text, its exits with where they lead and how each
door is left by the resets, its extra descriptions, who the resets put there
with what they wear, carry, sell and say, and what lies on the floor with what
is inside it. Rooms are numbered in walk order, not by vnum; rooms the walk
never reaches are listed last. The walk starts at the first room with an exit
out of the area, or at `--from`. `--with` loads other areas so their rooms and
keys can be named; `--anonymous` leaves out the credits line.

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
  damage and armor class far from the table in ROM's builder guide, vnums
  above 32767 (ROM holds a vnum in a short), equipment reset into a slot its
  wear flags do not allow, doors without a keyword, and prose that is short,
  repeated, too wide, miscapitalized or tells the reader what they feel.
- Info notes levels outside the area's `{low high}` range, exits to nowhere,
  descriptions that say a way leads where the room has no exit, door sides
  with no `D` reset or reset to a different state than the far side, extra
  descriptions the room text never names, mobs both aggressive and wimpy,
  shopkeepers that can be killed, and `oldstyle` conversion leftovers.
- Metrics, per file: record counts, exits per room, room description length,
  the shares of rooms with an extra description, of distinct room names and
  descriptions, of room descriptions that say "you", and of mobs with a
  program or spec function, doors, locked doors and keys, item type and
  sector counts, the mob level spread, and the type-token ratio of all
  description words.

`area_reader.lint.RULES` maps each rule id to its severity and its function;
`area_reader.lint.lint(atlas, targets)` returns the dictionary that `--json`
prints, for the entries of an atlas given as `targets`.

## Documentation

- `PROJECT.md` — the larger goal: a shared "virtual world algebra" across MUD dialects.
- `circlemud.md` — CircleMUD support plan.
- `coffeemud.md` — CoffeeMud support plan.
