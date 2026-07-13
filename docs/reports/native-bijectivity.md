# Native bijectivity review

## Decision

Add native writers one dialect at a time, beginning with ROM. Keep the current
readers authoritative while putting each native contract on the attrs class
that owns the data. Field metadata declares native order, phrase encoding,
conditions, tags, and section membership; one small renderer walks those
annotations. Do not create mirror-image `write_*` control flow or a second set
of writer model classes.

The first claimed law is semantic model stability:

```text
parse_D(render_D(parse_D(source))) == parse_D(source)
```

The canonical writer must also reach a fixed point:

```text
render_D(parse_D(render_D(parse_D(source))))
    == render_D(parse_D(source))
```

Neither law proves byte fidelity. Native spellings, whitespace, comments, and
file partitioning may already have been erased by a reader. Byte fidelity is a
separate CST-level goal and will not be claimed by the initial writers.

## Verified facts

- The supported reader surfaces are ROM, Merc, SMAUG, SWR/FUSS, CircleMUD, and
  CoffeeMud (`README.md`).
- The only checked-in native corpora are 52 ROM files and 44 Merc files under
  `test/`. The tests can additionally see upstream source trees under
  `C:\Users\Q\src` when those trees are present.
- `AreaFile.read_object_by_fields()` is a small declarative reader, but most
  real records bypass it through custom `read()` methods. Replacing the readers
  with a shared bidirectional grammar would therefore be a parser rewrite, not
  a writer addition.
- `PROJECT.md` already requires native writer support one dialect at a time and
  names the semantic round-trip law above.
- The current reader model is not injective over source bytes. Examples include
  numeric versus alphabetic flag spellings, leading whitespace before tilde
  strings, Circle flag spellings, and canonicalizable arithmetic transforms.
- Several readers also discard values rather than merely normalize spelling.
  A parse/render/parse equality can therefore pass vacuously unless each
  dialect has an explicit discard audit.

## Known discarded or unmodeled data

The following are verified blockers to stronger source fidelity:

- ROM/Merc resets read and discard `if_flag`.
- ROM room metadata assigns `clan` dynamically, but `clan` is not an attrs
  field and is therefore absent from equality and JSON output.
- ROM shops discard trailing comments.
- Unknown Diku-family sections are consumed by `skip_section()`.
- Merc mobiles discard XP; Merc objects discard action description and
  cost-per-day.
- SMAUG mobiles, objects, rooms, programs, repairs, and ignored keyed sections
  contain multiple discard paths.
- SWR/FUSS skips many keyed values and reuses non-FUSS model classes for records
  with different native signatures.
- Circle now retains index order, file partitioning, mobile `S`/`E` type, and
  per-file shop headers. Its remaining intentional normalizations are comments,
  whitespace, flag spelling, mixed metadata order, optional second shop-window
  presence, and zero-bonus dice spelling; these are executable in
  `CircleAreaFile.NATIVE_NORMALIZATIONS`.
- CoffeeMud repairs XML before parsing and preserves raw payloads unevenly;
  typed fields and `raw_text`/`raw_data` can also diverge after mutation.

These gaps must be removed, preserved as native residuals, or declared outside
the proved surface before a dialect is called bijective.

## Minimal writer architecture

For one dialect, annotate the existing attrs graph with:

1. ordered document sections on the area model;
2. native field order on each record model;
3. scalar encoders for tilde strings, words, numbers, flags, dice, and the few
   explicitly invertible transforms;
4. repetition, condition, and choice nodes needed to render lists and
   command-dependent record shapes.

One pure traversal renders those declarations. The classes already responsible
for reading are also responsible for their write annotations. There is no
writer class hierarchy, pairwise converter table, parallel dataclass graph,
service registry, or CST in this phase. Simple records may use the same attrs
metadata in both directions; context-sensitive readers remain authoritative
until a later change proves that replacing them is safe.

The public surface should follow the object the user already loaded:

```python
area_file.dumps()       # canonical native text for single-file dialects
area_file.write(path)   # native file, or native tree for CircleMUD
```

## Proof obligations per dialect

Every dialect slice must include all of the following before it is kept:

1. Full checked-in-corpus semantic stability.
2. Canonical fixed-point stability.
3. Non-vacuity assertions over the record families present in each source.
4. A machine-enforced discard ledger for the claimed surface, with mutation
   witnesses where a source value is intentionally outside the model.
5. Model-first tests over parser-reachable values, including rejection of
   values the native grammar cannot encode.
6. Evidence from the real upstream loader, or an explicit `unvalidated against
   upstream` label. Our reader and writer cannot be their own conformance
   oracle.
7. A passing full suite and a committed kept slice before the next dialect.

## Slice order

1. ROM: largest checked-in corpus and the shared tilde-file grammar.
2. Merc: proves that ROM declarations were not generalized prematurely.
3. SMAUG: numeric tails, programs, repairs, and keyed sections.
4. SWR/FUSS: keyed records and FUSS-native record identities.
5. CircleMUD: indexed multi-file output and invertible scalar transforms.
6. CoffeeMud: XML-specific declarations and raw/typed payload authority.
7. Cross-dialect fixed-point and public API documentation gate.

The exact-convergence rule applies: do not begin the next dialect until the
current dialect is committed or fully reverted.

## CircleMUD result

Circle records declare their native lines on the owning attrs fields. The area
model declares the five indexed collections, while `CircleAreaFile.dumps()`
returns an ordered `lib/world`-relative path-to-text mapping and `write()` emits
that tree. This is the only dialect-specific aggregation control flow; there is
no writer class graph or mirror `write_*` parser hierarchy.

The complete upstream CircleMUD 3.1 world has semantic and canonical fixed
points. A property test covers the inverse hitroll and armor-class transforms,
and invalid native lock, reset, armor, and object-value shapes are rejected.
The generated complete world was also built and booted by the upstream engine,
which reached its game loop and remained live for the five-second oracle
window.

## ROM first slice

The ROM slice may add attrs-owned native annotations, one generic renderer, and
tests. Reader changes are limited to capture-only fixes required to make the
model honest:

- store reset `if_flag`;
- make room `clan` a real field;
- preserve shop comments;
- record unknown skipped sections so a writer cannot claim complete coverage;
- fix the reset comment cursor bug if a regression fixture proves it.

The writer must reject non-representable model states rather than truncate or
guess, including invalid condition values, armor values not divisible by ten,
and exit flag combinations without a ROM lock code.

Forbidden expansion in this slice:

- no parser rewrite;
- no separate template DSL or broad parser rewrite;
- no second dialect;
- no CST or byte-perfect claim;
- no sentence algebra, morphisms, or cross-dialect conversion work.

## Open questions

- What is the smallest reproducible upstream ROM loader harness that can load
  generated areas without mutating the upstream source checkout?
- Does every ROM source section skipped by the current reader have semantic
  content that belongs in the model, or should some become explicit residual
  native payloads?
- Once ROM is green, should Merc deliberately duplicate its declaration first,
  allowing common structure to be extracted only after two proven examples?
