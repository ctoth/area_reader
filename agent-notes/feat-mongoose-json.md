# feat/mongoose-json: a JSON output from `build` that carries what ROM cannot hold

## Goal

Q, 2026-10-12: the area source format gets extended beyond ROM ("we can always enhance the format we own
everything"), and the infrastructure must not be specific to one setting. This branch is the first piece: `build`
can write the reader's own JSON directly, so a source directory can say things a ROM `.are` file has no place for,
and a world that loads the JSON (Mongoose's `$area_reader` / `$mud_world`) receives them.

## State (2026-10-12)

Branch from `origin/master` `5e64b9c`, worktree `C:\Users\Q\code\area_reader-mongoose-json`.

Written in `area_reader/authoring/builder.py`:

- Source keys `kind` (a slug), `with` (a mapping; needs `kind`) and `properties` (a mapping with text keys) on
  the area header, rooms, mobs, objects and exits written as mappings.
- An exit whose name is not one of the six compass words is a named exit: any slug, one side only, keys `to`,
  `keyword`, `description` and the three extension keys.
- `build(..., output_format="json")` / `area-reader build --format json`: renders the ROM part, parses it back
  and checks it as before, then writes `RomAreaFile.as_dict()` of the parsed area with the extension keys laid
  over each record and the named exits appended to their rooms' `exits` (with `door` set to the name). Default
  output name is the header's filename with `.json`.
- `--format rom` (the default) raises a `SourceError` at the first extension key or named exit.

## Decisions and why

- The JSON is the reader's JSON, not a new schema: the Mongoose loader already consumes `as_dict()` output, so a
  plain source built to JSON is exactly what the server's wrapper prints for the same area's `.are`.
- The pass-through block is called `properties`, not after any one game: area_reader is a general tool.
- No version field in the JSON.
- Named exits take no door, key or reverse side: ROM's door resets address exits by direction number, and what
  stands in the way of a named exit is the kind's business.
- `rom` refuses rather than drops: silently losing a kind would build an area that looks right and is not.

## Not done

- `lint`, `walk` and `atlas` read `.are` files only; they do not see the JSON or check kind names.
- No registry of kinds: any slug is accepted.
- `unbuild` does not read the JSON back.
- Text in a source file must still be Latin-1 without `~` everywhere, including inside `properties`.
- A typo in a compass name (`nroth`) is now a named exit, caught only by `--format rom`.

## Checked (2026-10-12)

- Whole suite: 1722 passed (11 new tests in `test_authoring.py`); `ruff check .` clean. `ruff format --check`
  flags only code blocks in `PROJECT.md`, which this branch does not touch.
- A copy of `mongoose-areas/areas/saltworks` (30 rooms, 11 mobs, 18 objects) built with `--format json` equals,
  as parsed JSON, what `area-reader saltworks.are` prints for the same source built to ROM.
- Not checked: any load of this JSON by a MOO. The Mongoose server wrapper and `$area_reader:load` take `.are`
  files only today.

## Next step

In Mongoose, outside this repo: the server wrapper accepts a `.json` file; the loader reads `kind` to choose a
class and applies `properties`.
