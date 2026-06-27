# CoffeeMud support plan

## Scope

Add CoffeeMud support for `C:\Users\Q\src\coffeemud` without treating it as another ROM/Merc/SMAUG token format.

CoffeeMud persisted examples use `.cmare` files. These are XML documents or XML fragments with CoffeeMud object records, not tilde-delimited Diku-style area files. The parser should support the real top-level shapes present in the CoffeeMud tree:

- `<AREA>` for full area exports.
- `<AROOMS>` / `<AROOM>` inside areas.
- `<ITEMS>` and `<ITEM>` for item catalog exports.
- `<MOBS>` and `<MOB>` for mob catalog exports.
- Nested escaped XML payloads inside fields such as `MTEXT`, `ITEXT`, `RTEXT`, `EXDAT`, and `ADATA`.

The first implementation should be read-only parsing only. It should not try to instantiate CoffeeMud Java classes, run CoffeeMud, or normalize everything into ROM/SMAUG semantics.

## Parser choice

Use the Python stdlib XML stack:

```python
import html
import xml.etree.ElementTree as ET
```

`xml.etree.ElementTree` is sufficient for the `.cmare` files observed so far. Nested CoffeeMud object text is escaped XML, so parse the outer document first, then unescape and parse inner fields when needed:

```python
outer = ET.fromstring(text)
inner = ET.fromstring(html.unescape(mtext))
```

If a real `.cmare` file turns out to contain multiple sibling top-level records without a wrapper, wrap it in a synthetic root before parsing, still using `ElementTree`.

## Upstream truth

Use CoffeeMud source as the grammar authority, especially:

- `C:\Users\Q\src\coffeemud\com\planet_ink\coffee_mud\Libraries\CoffeeMaker.java`
- `C:\Users\Q\src\coffeemud\com\planet_ink\coffee_mud\Libraries\interfaces\GenericBuilder.java`

Important methods and contracts:

- `unpackAreaFromXML(...)`
- `unpackAreaObjectFromXML(...)`
- `unpackRoomFromXML(...)`
- `unpackItemFromXML(...)`
- `unpackMobFromXML(...)`
- `addItemsFromXML(...)`
- `addMOBsFromXML(...)`

Observed CoffeeMud source files for acceptance coverage:

- `C:\Users\Q\src\coffeemud\resources\examples\monsters.cmare`
- `C:\Users\Q\src\coffeemud\resources\examples\junk.cmare`
- `C:\Users\Q\src\coffeemud\resources\examples\deities.cmare`
- `C:\Users\Q\src\coffeemud\resources\skills\shipbuilding.cmare`
- `C:\Users\Q\src\coffeemud\resources\skills\caravanbuilding.cmare`
- `C:\Users\Q\src\coffeemud\resources\skills\clancastles.cmare`

## Model shape

Add CoffeeMud-specific model classes instead of forcing CoffeeMud into existing ROM/SMAUG classes.

Proposed classes:

- `CoffeeMudAreaFile`
- `CoffeeMudArea`
- `CoffeeMudRoom`
- `CoffeeMudExit`
- `CoffeeMudMob`
- `CoffeeMudItem`
- `CoffeeMudAbility`
- `CoffeeMudBehavior`
- `CoffeeMudAffect`

Keep CoffeeMud-native identifiers intact:

- Area names are strings.
- Room IDs are strings, for example `Coffee Grounds#73` or `UNNAMED_198974801#0`.
- Class IDs are strings, for example `GenMob`, `GenItem`, `StdBoardableShip`, `ShipDeck`, `StdOpenDoorway`.
- Direction codes are integers from `XDIRE`.

Map obvious common fields to readable attributes:

- Mob: `class_id`, `level`, `ability`, `rejuv`, `name`, `description`, `display`, `race`, `gender`, `money`, `raw_text`.
- Item: `class_id`, `uses`, `level`, `ability`, `rejuv`, `name`, `description`, `display`, `value`, `material`, `worn_location`, `worn_bitmap`, `raw_text`.
- Room: `room_id`, `area`, `class_id`, `display`, `description`, `climate`, `atmosphere`, `exits`, `mobs`, `items`, `raw_text`.
- Area: `class_id`, `name`, `description`, `climate`, `sub_ops`, `theme`, `rooms`, `raw_data`.

For fields not modeled yet, preserve either raw XML text or a parsed dictionary/list structure. Do not silently drop unknown CoffeeMud tags.

## Test-first sequence

### Slice 1: XML loading and top-level dispatch

Add tests that prove `CoffeeMudAreaFile` can load each observed top-level document kind:

- `<MOBS>` produces mob records.
- `<ITEMS>` produces item records.
- `<AREA>` produces an area record.
- `<AROOM>` can be parsed as a room record when encountered directly.

Acceptance:

- Minimal hand-written fixtures parse.
- `as_dict()` and `as_json()` work.
- Existing non-CoffeeMud tests still pass.

### Slice 2: mobs

Add tests from a minimal `monsters.cmare`-style record:

- `MCLAS`
- `MLEVL`
- `MABLE`
- `MREJV` or `MREJUV`
- `MTEXT`
- nested `NAME`, `DESC`, `DISP`, `PROP`, `FLAG`, `MONEY`, `VARMONEY`, `GENDER`, `MRACE`
- nested `BEHAVES`, `AFFECS`, `FACTIONS`, `ABLTYS`

Acceptance:

- `resources\examples\monsters.cmare` loads all mobs.
- `resources\examples\deities.cmare` loads deity-shaped mob records without losing deity-specific nested tags.

### Slice 3: items

Add tests from a minimal `junk.cmare`-style record:

- `ICLAS`
- `IUSES`
- `ILEVL`
- `IABLE`
- `IREJV`
- `ITEXT`
- nested `NAME`, `DESC`, `DISP`, `PROP`, `FLAG`, `VALUE`, `MTRAL`, `READ`, `WORNL`, `WORNB`
- optional container fields such as `CAPA`, `CONT`, `OPENTK`

Acceptance:

- `resources\examples\junk.cmare` loads all items.
- Empty/self-closing tags parse as empty strings or `None` consistently.

### Slice 4: areas and rooms

Add tests from a minimal full area:

- `AREA`
- `ACLAS`
- `ANAME`
- `ADESC`
- `ACLIM`
- `ASUBS`
- `ATECH`
- `ADATA`
- `AROOMS`
- `AROOM`
- `ROOMID`
- `RAREA`
- `RCLAS`
- `RDISP`
- `RDESC`
- `RTEXT`
- `ROOMEXITS`
- `REXIT`
- `XDIRE`
- `XDOOR`
- `XEXIT`
- `EXID`
- `EXDAT`
- `ROOMCONTENT`
- `ROOMMOBS`
- `ROOMITEMS`

Acceptance:

- Rooms keep string `ROOMID`.
- Exits keep direction, target room ID, exit class, and raw/parsed exit data.
- Room contents parse nested `RMOB` and `RITEM` entries.

### Slice 5: nested boardable areas

Items such as ships, caravans, and castles embed `SSAREA -> AREA -> AROOMS` inside `ITEXT`.

First behavior:

- Preserve nested `SSAREA` raw XML in the parsed item.

Second behavior:

- Parse nested `SSAREA` into a nested `CoffeeMudArea`.

Acceptance:

- `resources\skills\shipbuilding.cmare` loads outer ship items and nested rooms.
- `resources\skills\caravanbuilding.cmare` loads nested room contents such as siege weapons.
- `resources\skills\clancastles.cmare` loads nested castle rooms and exits.

## Implementation notes

Keep the implementation direct and local:

- Do not add an adapter, sender, helper framework, or abstraction layer unless a concrete duplicate parser block proves it is needed.
- Prefer small parsing functions/methods owned by `CoffeeMudAreaFile`.
- Preserve unknown tags.
- Use structured XML APIs, not regex/string scanning.
- Do not mutate or require CoffeeMud source files.

Likely implementation outline:

```python
class CoffeeMudAreaFile(object):
    def __init__(self, filename):
        self.filename = os.fspath(filename)
        self.data = ...
        self.area = CoffeeMudArea()

    def load_sections(self):
        root = self.parse_document(self.data)
        self.load_root(root)

    def parse_document(self, text):
        try:
            return ET.fromstring(text)
        except ET.ParseError:
            return ET.fromstring("<ROOT>" + text + "</ROOT>")
```

Parsing nested text:

```python
def parse_escaped_xml(self, value):
    if not value:
        return None
    text = html.unescape(value)
    return self.parse_document(text)
```

## Verification gates

Before editing:

```powershell
git status --short --branch
uv run pytest
```

After each kept slice:

```powershell
uv run pytest test_area_reader.py -k coffeemud
uv run pytest test_area_reader.py
```

Before final:

```powershell
uv run pytest
git diff --check
```

The real-source acceptance test should load every selected CoffeeMud `.cmare` file without exceptions and assert nonempty parsed records for the expected top-level shape.

## Commit discipline

For implementation work, keep each source slice accountable in Git:

1. Baseline tests.
2. Failing tests for the slice.
3. Parser changes for that slice.
4. Passing targeted tests.
5. Passing broader tests.
6. Commit kept slice before starting the next parser slice.

Do not carry multiple experimental parser slices in one uncommitted tracked diff.

## Risks

- `.cmare` is used for more than full areas; catalog item and mob exports are first-class.
- CoffeeMud room and area IDs are string identifiers, not numeric vnums.
- Nested escaped XML is common and can itself contain full areas.
- Some files include self-closing empty tags; the parser must distinguish missing, empty, and present-with-children where that matters.
- CoffeeMud source may use both `MREJV` and `MREJUV` shapes in examples; accept both if observed in current fixtures.
