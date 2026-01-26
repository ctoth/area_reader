# Area Reader

A Python library to parse MUD area files into structured data.

Reads area files from ROM, Merc, SMAUG, and CircleMUD and converts them to Python objects (attrs classes) that can be serialized to JSON.

## Installation

Requires Python 3.13+.

```bash
uv sync
```

Or with pip:

```bash
pip install attrs cattrs
```

## Usage

```python
import area_reader

# Load a ROM area file
af = area_reader.RomAreaFile('midgaard.are')
af.load_sections()

# Access the parsed area
print(af.area.name)  # "Midgaard"
print(af.area.rooms[3001].name)  # "The Temple Of Mota"

# Export to JSON
print(af.as_json(indent=2))

# Or get as a dict
data = af.as_dict()
```

### Supported Formats

| Class | Format | File Type |
|-------|--------|-----------|
| `RomAreaFile` | ROM 2.4 | Single `.are` file |
| `MercAreaFile` | Merc 2.1 | Single `.are` file |
| `SmaugAreaFile` | SMAUG | Single `.are` file |
| `CircleMudFile` | CircleMUD | Directory with `.wld`, `.mob`, `.obj`, `.zon`, `.shp` |

### CircleMUD Usage

CircleMUD uses a split-file format where each zone has separate files for rooms, mobs, objects, etc.

```python
from circlemud import load_circlemud_area

# Load a CircleMUD area directory
area = load_circlemud_area('/path/to/zone_directory')
area.load_sections()

# Access the parsed area
print(area.area.name)
print(area.area.rooms['12001'].name)

# Export to JSON
print(area.as_json(indent=2))
```

CircleMUD supports alphanumeric VNUMs (e.g., `QQ00`, `XX74`) which are preserved as strings.

## Output Format

The `as_dict()` / `as_json()` output contains these top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Area name |
| `metadata` | string | Builder credits, level range |
| `original_filename` | string | Source filename |
| `first_vnum` | int | First vnum in range |
| `last_vnum` | int | Last vnum in range |
| `rooms` | dict | Room definitions keyed by vnum |
| `mobs` | dict | Mobile/NPC definitions keyed by vnum |
| `objects` | dict | Item definitions keyed by vnum |
| `resets` | array | Spawn instructions |
| `shops` | array | Shopkeeper definitions |
| `specials` | array | Special mob behaviors |
| `helps` | array | Help text entries |

### Room Format

```json
{
  "vnum": 3001,
  "name": "The Temple Of Mota",
  "description": "You are in the southern end of the temple...",
  "room_flags": "ROM_ROOM_FLAGS.NO_MOB|INDOORS|LAW",
  "sector_type": "SECTOR_TYPES.INSIDE",
  "heal_rate": 100,
  "mana_rate": 100,
  "owner": null,
  "exits": [
    {
      "door": "EXIT_DIRECTIONS.NORTH",
      "destination": 3054,
      "description": "At the northern end...",
      "keyword": "",
      "exit_info": "EXIT_FLAGS.NONE",
      "key": -1
    }
  ],
  "extra_descriptions": [
    {
      "keyword": "plaque",
      "description": "This entire world has been..."
    }
  ]
}
```

### Mobile (NPC) Format

```json
{
  "vnum": 3000,
  "name": "wizard",
  "short_desc": "the wizard",
  "long_desc": "A wizard walks around behind the counter...",
  "description": "The wizard looks old and senile...",
  "race": "human",
  "level": 23,
  "alignment": 900,
  "sex": "male",
  "size": "medium",
  "hit": { "number": 1, "sides": 1, "bonus": 999 },
  "mana": { "number": 1, "sides": 1, "bonus": 999 },
  "damage": { "number": 1, "sides": 8, "bonus": 32 },
  "damtype": "magic",
  "hitroll": 0,
  "ac": {
    "pierce": -150,
    "bash": -150,
    "slash": -150,
    "exotic": -150
  },
  "act": "ROM_ACT_TYPES.IS_NPC|SENTINEL|NOPURGE",
  "affected_by": "AFFECTED_BY.INVIS",
  "off_flags": "OFFENSE.AREA_ATTACK|DODGE",
  "imm_flags": "IMM_FLAGS.SUMMON|CHARM|MAGIC|WEAPON",
  "res_flags": "IMM_FLAGS.NONE",
  "vuln_flags": "IMM_FLAGS.NONE",
  "form": "FORMS.NONE",
  "parts": "PARTS.NONE",
  "start_pos": "stand",
  "default_pos": "stand",
  "wealth": 750,
  "material": "0",
  "mprogs": []
}
```

Dice rolls (hit, mana, damage) use `NdS+B` format: roll `number` dice with `sides` sides, add `bonus`.

### Object (Item) Format

```json
{
  "vnum": 3000,
  "name": "barrel beer",
  "short_desc": "a barrel of beer",
  "description": "A beer barrel has been left here.",
  "item_type": "drink",
  "material": "wood",
  "level": 0,
  "weight": 160,
  "cost": 75,
  "condition": 100,
  "wear_flags": "WEAR_FLAGS.TAKE",
  "extra_flags": 0,
  "value": [300, 300, "beer", 0, 0],
  "affected": [],
  "extra_descriptions": []
}
```

The `value` array meaning depends on `item_type`:
- **weapon**: [weapon_class, num_dice, dice_sides, attack_type, special_flags]
- **container**: [capacity, flags, key_vnum, max_weight, weight_multiplier]
- **drink/fountain**: [current, max, liquid_type, poisoned, unused]
- **wand/staff**: [level, max_charges, charges_left, spell, unused]
- **potion/pill/scroll**: [level, spell1, spell2, spell3, spell4]
- **other**: [v0, v1, v2, v3, v4] (type-specific)

### Reset Format

Resets define what spawns where when the area repopulates.

```json
{
  "command": "M",
  "arg1": 3011,
  "arg2": 1,
  "arg3": 3001,
  "arg4": 0,
  "comment": "* Hassan"
}
```

| Command | Description | arg1 | arg2 | arg3 | arg4 |
|---------|-------------|------|------|------|------|
| M | Load mobile | mob_vnum | limit | room_vnum | - |
| O | Load object | obj_vnum | limit | room_vnum | - |
| P | Put obj in obj | obj_vnum | limit | container_vnum | - |
| G | Give obj to mob | obj_vnum | limit | - | - |
| E | Equip obj on mob | obj_vnum | limit | wear_location | - |
| D | Set door state | room_vnum | direction | state | - |
| R | Randomize exits | room_vnum | num_exits | - | - |

### Shop Format

```json
{
  "keeper": 3000,
  "buy_type": [2, 3, 4, 10, 0],
  "profit_buy": 105,
  "profit_sell": 15,
  "open_hour": 0,
  "close_hour": 23
}
```

- `keeper`: vnum of the shopkeeper mob
- `buy_type`: item types the shop will purchase (0 = slot unused)
- `profit_buy`: markup percentage when player buys
- `profit_sell`: percentage of value when player sells

### Special Format

Assigns special behavior functions to mobs.

```json
{
  "command": "M",
  "arg1": 3000,
  "arg2": "spec_cast_mage",
  "comment": "* the wizard"
}
```

Common spec functions: `spec_cast_mage`, `spec_cast_cleric`, `spec_thief`, `spec_executioner`, `spec_fido`, `spec_janitor`, `spec_poison`, `spec_breath_*`

## CircleMUD Output Format

CircleMUD areas have a slightly different structure:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Zone name |
| `zone_vnum` | string | Zone identifier (may be alphanumeric) |
| `rooms` | dict | Room definitions keyed by vnum |
| `mobs` | dict | Mobile definitions keyed by vnum |
| `objects` | dict | Object definitions keyed by vnum |
| `zone` | object | Zone metadata and resets |
| `shops` | array | Shop definitions |

### CircleMUD Mobile Format

```json
{
  "vnum": "12000",
  "aliases": ["judge", "adjudicator"],
  "short_desc": "The adjudicator",
  "long_desc": "The adjudicator is watching the games intently.",
  "description": "The adjudicator is a retired gladiator...",
  "action_flags": 2,
  "affect_flags": 128,
  "alignment": 100,
  "mob_type": "S",
  "level": 12,
  "thac0": 9,
  "ac": 2,
  "hit_dice": { "number": 3, "sides": 7, "bonus": 143 },
  "damage_dice": { "number": 2, "sides": 7, "bonus": 1 },
  "gold": 1200,
  "xp": 13000,
  "load_position": 8,
  "default_position": 8,
  "sex": 1,
  "extra_specs": {}
}
```

### CircleMUD Object Format

```json
{
  "vnum": "12000",
  "aliases": ["ring", "pewter"],
  "short_desc": "a pewter ring",
  "long_desc": "There is a pewter ring lying here.",
  "item_type": 9,
  "extra_flags": 96,
  "wear_flags": 3,
  "values": ["-3", "0", "0", "0", "0"],
  "weight": 1,
  "cost": 10000,
  "rent": 5000,
  "affects": [
    { "location": 13, "modifier": 10 },
    { "location": 2, "modifier": -1 }
  ],
  "extra_descriptions": []
}
```

Key differences from ROM format:
- VNUMs are strings (supports alphanumeric like `QQ00`)
- Uses `thac0` instead of `hitroll` (lower is better)
- Single `ac` value instead of four damage types
- Objects have `rent` cost field
- Flags are numeric bitvectors instead of enum names

## Flag Values

Flags are serialized as pipe-separated enum names (e.g., `"ROM_ACT_TYPES.IS_NPC|SENTINEL|NOPURGE"`).

See `constants.py` for all flag definitions including:
- `ROM_ACT_TYPES` / `MERC_ACT_TYPES` - mob behavior flags
- `AFFECTED_BY` - spell/status effects
- `WEAR_FLAGS` - equipment slots
- `ROM_ROOM_FLAGS` / `MERC_ROOM_FLAGS` - room properties
- `EXIT_FLAGS` - door states
- `OFFENSE` - combat behaviors
- `IMM_FLAGS` - immunities/resistances/vulnerabilities
- `FORMS` - body type
- `PARTS` - body parts
