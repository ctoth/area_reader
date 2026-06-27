# CircleMUD Support Plan

No implementation is part of this plan.

## Scope

- Leave the current `master` state intact, including the pre-existing untracked `uv.lock`.
- Treat `C:\Users\Q\src\circlemud` as the source oracle.
- Use CircleMUD loader behavior from:
  - `C:\Users\Q\src\circlemud\src\db.c`
  - `C:\Users\Q\src\circlemud\src\db.h`
  - `C:\Users\Q\src\circlemud\src\structs.h`
  - `C:\Users\Q\src\circlemud\src\shop.c`
- Run `uv run pytest` before implementation edits begin.

## Architecture

Add a direct CircleMUD reader rather than trying to force CircleMUD data through `RomAreaFile.load_sections()`.

CircleMUD uses an indexed world tree split across separate file families:

- `lib/world/zon`
- `lib/world/wld`
- `lib/world/mob`
- `lib/world/obj`
- `lib/world/shp`

That shape is materially different from ROM, Merc, and SMAUG single-file `.are` readers, so the reader should model CircleMUD directly.

Do not introduce a generic adapter, interface, sender, or helper layer unless a concrete CircleMUD requirement proves it necessary.

## Data Model

Add Circle-specific attrs classes in `area_reader/__init__.py`:

- `CircleArea`
- `CircleZone`
- `CircleRoom`
- `CircleMob`
- `CircleItem`
- `CircleShop`
- Circle reset command records
- Circle exit records

Reuse existing shared records where they fit naturally:

- `MudBase`
- `ExtraDescription`
- `Dice`

Preserve vnums in parsed output. Circle's runtime loader later renumbers vnums to rnums, but the parser should expose the source data unless a derived mapping is explicitly added.

## Reader

Add `CircleAreaFile`.

The constructor should accept either the CircleMUD root or the `lib/world` root, not a single `.are` file.

Load in CircleMUD boot order:

1. Zones from `lib/world/zon/index`
2. Rooms from `lib/world/wld/index`
3. Mobiles from `lib/world/mob/index`
4. Objects from `lib/world/obj/index`
5. Shops from `lib/world/shp/index`

Index files list world files and terminate with `$`.

## Parser Semantics

Match CircleMUD source behavior, not nearby ROM/Merc behavior.

### Flags

Implement Circle's `asciiflag_conv` semantics:

- Numeric strings parse as numeric values.
- Lowercase letters map from bit 0: `a == 1`.
- Uppercase letters map from bit 26.

### Rooms

Parse room records from `.wld` files:

- `#<vnum>`
- name string
- description string
- numeric line: ignored zone number, flags, sector type
- `D<direction>` exits
- `E` extra descriptions
- `S` terminator
- `$` file terminator

Exit lock semantics follow `setup_dir()`:

- `0` means no door flags.
- `1` means `ISDOOR`.
- `2` means `ISDOOR | PICKPROOF`.

### Mobiles

Parse mobile records from `.mob` files:

- `#<vnum>`
- name string
- short description string
- long description string
- description string
- numeric line: act flags, affected flags, alignment, type letter
- `S` simple mobile body
- `E` enhanced mobile body, which starts with the simple body and then reads `Keyword: value` lines until a bare `E`

Keep the important Circle transforms:

- `MOB_ISNPC` is always added.
- Simple mob hitroll is `20 - source_hitroll`.
- Simple mob AC is `source_ac * 10`.
- Simple mob hit dice are stored as dice fields, matching Circle's max-hit sentinel behavior.

### Objects

Parse object records from `.obj` files:

- `#<vnum>`
- name string
- short description string
- description string
- action description string
- numeric line: item type, extra flags, wear flags
- value line: four integers
- weight, cost, rent line
- optional `E` extra descriptions
- optional `A` affect records

Object records do not have an explicit `S` terminator. A record ends at the next `#`, `$`, or object continuation line boundary, mirroring `parse_object()`.

### Zones

Parse zone records from `.zon` files:

- `#<zone number>`
- zone name
- `bot top lifespan reset_mode`
- reset commands until `S` or `$`

Supported reset commands:

- `M`
- `O`
- `P`
- `G`
- `E`
- `R`
- `D`

Command arity follows `load_zones()`:

- `M`, `O`, `E`, `P`, and `D` use `if_flag arg1 arg2 arg3`.
- `G` and `R` use `if_flag arg1 arg2`.

### Shops

Parse CircleMUD v3.0 shop files from `.shp` files:

- file version header
- `#<shop vnum>~`
- producing object list terminated by `-1`
- buy and sell profit values
- trade list terminated by `-1`
- shop messages
- temper, bitvector, keeper, trade-with flags
- room list terminated by `-1`
- open and close hours

Keep shop vnums, keeper vnums, room vnums, products, trade types, messages, hours, and flags.

## Tests

Add focused synthetic tests before implementation:

- Circle room flags and exits
- Simple mob parsing
- Enhanced mob `E` section parsing
- Object record ending at the next `#`
- Zone reset command arity
- v3.0 shop record parsing

Add live-source tests that run only when `C:\Users\Q\src\circlemud` exists:

- load all indexed zone files
- load all indexed room files
- load all indexed mobile files
- load all indexed object files
- load all indexed shop files
- load the complete Circle world through `CircleAreaFile`

## Acceptance Gate

Use the repo's Python tooling convention:

```powershell
uv run pytest test_area_reader.py -k circle
uv run pytest test_area_reader.py
uv run pytest
```

The final implementation is acceptable only when existing ROM, Merc, SMAUG, and SWR coverage still passes and CircleMUD live-source loading covers the real indexed world tree.
