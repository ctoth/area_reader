# Virtual World Algebra Project

## Purpose

This project is about more than parsing MUD area files. The larger goal is to
find the common algebra of early virtual worlds: the shared semantic structure
behind Diku-family area files, CircleMUD worlds, CoffeeMud XML exports,
LambdaMOO databases, MUSH/MUX-style object databases, and later programmable
world systems.

The working thesis:

> Early virtual worlds are different concrete presentations of overlapping
> world theories.

The implementation should make that thesis operational. Each source format
must retain its native shape well enough for round-trip fidelity, while also
projecting its meaningful assertions into a shared virtual-world theory.

## Theoretical Spine

Use Goguen and Burstall's institution framing as the design guide, not as an
inheritance hierarchy or category-theory ceremony.

For each dialect or runtime, model an institution:

```text
I_D = (Sign_D, Sen_D, Mod_D, |=_D)
```

Where:

- `Sign_D` is the dialect vocabulary: record families, identifiers, flags,
  fields, arities, sections, file families, XML tags, object types, and value
  types.
- `Sen_D` is the set of assertions that can be made in that dialect.
- `Mod_D` is the parsed/interpreted model space for that dialect.
- `|=_D` is satisfaction: the relation between a model and the sentences true
  of it.

The central law is the satisfaction condition:

```text
M' |= Sen(phi)(e) iff Mod(phi)(M') |= e
```

Plainly: truth must be invariant under change of notation.

In code, this should become executable laws, not abstract machinery.

## Layers

Every reader/writer should eventually participate in these layers:

```text
Concrete source bytes/text
  -> native CST / phrase tree
  -> native AST / record tree
  -> native sentence set
  -> virtual world graph
  -> theory and satisfaction layer
```

Different formats need different amounts of each layer.

- CST preserves spelling, order, comments, whitespace where needed, original
  flag notation, and other concrete data required for native fidelity.
- AST preserves parsed native records and structure.
- Sentences express semantic assertions such as `room_has_exit`,
  `object_has_property`, or `verb_has_owner`.
- The virtual world graph is the shared semantic graph of places, entities,
  links, containment, behavior, authority, and persistence.
- The theory layer records laws, constraints, morphisms, and explicit losses.

## Core Sorts

The common algebra starts with these sorts:

```text
World
Region / Area / Zone
Room / Location
Exit / Link
Entity
Actor / Mobile / Player / Puppet
Item / Thing
Class / Parent / Prototype
Property / Attribute
Verb / Command / Method / Program
Value
Flag / Trait / Tag
Permission / Ownership / Capability
Reset / Spawn / Scheduler fact
Shop / Economy fact
Help / Documentation node
Event / Task / Process
Connection / Session
ResidualNativePayload
```

These are not all equally supported by every format. A ROM area can express
rooms, exits, mobiles, objects, resets, shops, helps, and flags. A LambdaMOO
database can express persistent objects, parents, properties, verbs, runtime
values, tasks, connections, and authority. MUSH expresses dbrefs, object types,
attributes, flags, powers, locks, ownership, location, exits, and softcode.

## Core Relations

Candidate semantic relations:

```text
contains(container, entity)
located_at(entity, location)
exits_to(exit, source, destination)
owns(actor, object)
inherits(child, parent)
defines_property(object, property)
has_property_value(object, property, value)
defines_verb(object, verb)
verb_body(verb, program)
can_read(subject, object)
can_write(subject, object)
can_execute(subject, verb)
spawns(reset, entity, location)
describes(entity, text)
aliases(entity, names)
has_trait(entity, trait)
has_native_payload(entity_or_sentence, payload)
```

The implementation should prefer semantic relations over field-name matching.
Two dialects can share a field name while giving it different meaning, scale,
arity, or authority implications.

## Native Institutions

### Area Dialects

Initial sibling institutions:

- `Rom`
- `Merc`
- `Smaug`
- `SwrFuss`
- `Circle`
- `CoffeeMud`

These are area/world-content institutions. Their first obligation is native
bijectivity:

```text
parse_D(dump_D(parse_D(source))) == parse_D(source)
```

When concrete source spelling matters, stronger CST-level laws can be added
after semantic round-trip laws are stable.

### Programmable World Institutions

Target and peer institutions:

- `LambdaMOO`
- `MUSH`
- `MUX` / `PennMUSH` / `TinyMUX` variants
- later: LPC, Evennia, MUCK, ColdC, Inform/TADS if useful

These are not just more area formats. They are programmable persistent-world
institutions. They add object identity, inheritance/prototypes, authority,
runtime values, commands, code, locks, tasks, sessions, and database-version
semantics.

The relation from area dialects to these systems is an implementation or
realization morphism, not a simple field converter.

`Sign_LambdaMOO` is version-indexed. The database value grammar changes across
`DBVersions`: maps appear at v7, anonymous objects at v13, WAIFs at v14, and
booleans at v17. Treat LambdaMOO as a family of related signatures, not one
flat signature.

## Morphisms

Do not build pairwise `to_rom`, `to_merc`, `to_mush` methods.

Use explicit morphisms:

```text
Source institution -> Target institution
```

Each morphism must declare:

- source signature subset
- target signature subset
- sentence translation
- model reduct or realization direction
- unsupported sentence families
- expected losses
- policy choices
- Hypothesis laws that exercise the satisfaction condition

The ergonomic API may still be:

```python
target = TargetArea.from_other(source, loss=losses)
```

But internally, `from_other` must resolve `(source_sig, target_sig)` to exactly
one `Morphism` object in a typed morphism table. This table is the only
permitted registry: it holds morphisms, not converter functions, and there is at
most one morphism per ordered pair unless the caller explicitly chooses a named
policy.

## Loss Ledger

Loss must be an explicit artifact, not a warning string.

Every morphism should produce a `LossReport` containing paths like:

```text
rooms[3001].programs
objects[7000].original_flag_spelling
circle.zones[30].lifespan
coffeemud.rooms["Area#1"].raw_text
lambda_moo.tasks[42].vm.stack
```

Each loss should be classified:

- `unsupported`: target cannot express this sentence.
- `policy_required`: target can express it only with an explicit policy.
- `normalized`: target expresses it after reversible normalization.
- `weakened`: target preserves a weaker sentence.
- `precision_loss`: scale, numeric, ordering, or spelling precision was lost.
- `bug`: the morphism was expected to preserve this but did not.

## Algebraic Operations

The shared world algebra should define operations such as:

```text
sum(W1, W2)
rename_ids(W, mapping)
restrict(W, signature_subset)
extend(W, scaffold_or_policy)
quotient(W, equivalence)
normalize(W, dialect_policy)
free_realization(source_theory, target_policy)
```

The key operation for programmable worlds is free realization:

```text
Free_MOO(AreaTheory + MooPolicy) -> MooDatabase
Free_MUSH(AreaTheory + MushPolicy) -> MushDatabase
```

Plainly: build the least target object graph satisfying the source area theory
plus the chosen realization policy, with no accidental semantic junk except
declared scaffold.

This is a later operation, not a first milestone. It should not pull the early
work into proving adjunctions or building category-theory scaffolding. For the
first phases, it is enough to record realization policies, generated scaffold,
and the source sentences each target object graph satisfies.

## Example Semantic False Friends

This project must not assume equal field names imply equal semantics.

Known examples:

- Circle source hitroll is transformed in the current reader as
  `hitroll = 20 - source_hitroll`.
- Circle source armor class is scaled as `ac = source_ac * 10`.
- ROM armor class is split into pierce, bash, slash, exotic, with reader-level
  scaling.
- ROM, Merc, SMAUG, and Circle reset arguments have different arities and
  command-specific meanings.
- ROM/Merc/SMAUG/Circle room flags have different alphabets and enum domains.
- CoffeeMud `money`, ROM `wealth`, Merc wealth/XP, and SMAUG numeric tails are
  related but not identical.
- LambdaMOO `ObjNum`, `Anon`, `MooError`, `MooCatch`, `MooFinally`, `CLEAR`,
  and plain integers must remain distinct even when their representation is
  numeric.

Translate sentences, not field names.

## Value Identity

Value equality is structural, never raw Python `==`.

Two values are equal iff both their semantic type and payload match:

```text
(type_name(value), payload(value))
```

This matters because `lambdamoo-db-py` represents several persisted MOO value
types as `int` subclasses. `ObjNum(1)`, `Anon(1)`, `MooError(1)`,
`MooCatch(1)`, `MooFinally(1)`, and plain `1` can compare equal under Python's
normal equality even though they are different MOO values. They also collide as
dictionary keys or set members if raw equality and hashing are used.

All sentence arguments, loss paths, set differences, and round-trip laws must
use structural identity. Laws over typed values are invalid if they rely on raw
Python equality.

## Hypothesis Strategy

Hypothesis is the executable authority for this project.

Build strategies bottom-up:

1. phrase strategies
   - flags
   - dice
   - tilde strings
   - vnum headers
   - reset command lines
   - CoffeeMud XML fragments
   - LambdaMOO typed values
   - MUSH attribute and lock phrases

2. record strategies
   - rooms
   - exits
   - mobs/actors
   - objects/items
   - resets/spawns
   - properties/attributes
   - verbs/programs

3. document/database strategies
   - native area files
   - Circle file-family worlds
   - CoffeeMud exports
   - LambdaMOO databases
   - MUSH database fragments

4. morphism strategies
   - generate source sentence sets
   - translate to target
   - check satisfaction or explicit loss

Core laws:

```python
project(model) is total and deterministic

source_sentences == preserved_sentences.disjoint_union(lost_sentences)

# Later, after a real non-trivial morphism exists:
target_model.satisfies(morphism.translate(sentence)) == (
    morphism.reduct(target_model).satisfies(sentence)
)
```

Native round-trip laws remain required once a dialect has a writer:

```python
parse_D(dump_D(model)) == model
```

Avoid using the project's own reader and writer as the only oracle for a
format. Where possible, compare against real upstream loaders, reference
databases, or byte/line-level fixtures produced by the original system.

Every translation law must also assert coverage. A passing law over an empty
sentence family, or one where both source and target satisfaction are simply
false, is not evidence.

## Oracle Provenance

Reader/writer pairs are not automatically authorities for their own formats.

| Format | Oracle | External? |
|---|---|---|
| LambdaMOO | Server-produced `.db` byte or line round-trip fixtures such as `LambdaCore-latest.db` and `mongoose-*.db` | yes |
| `lambdamoo-db-py` reader/writer | Self-checking parser/writer pair; must be validated against server-produced fixtures before use as ground truth | no |
| ROM/Merc/SMAUG/SWR/Circle/CoffeeMud | Upstream loader behavior and native fixtures; native bijectivity is blocked until a writer exists | pending |

For MOO-style databases, byte-level or line-level comparison against a
server-produced database is stronger than parse-parse comparison. For area
dialects, upstream loader conformance and generated native writers must be
separated: a reader can match upstream loading behavior while still lacking the
CST data needed to write the original source shape.

## First Milestone

Create an institutional inventory and the first executable laws without
changing parser behavior.

Deliverables:

- `docs/institutions.md` or equivalent sectioned document.
- `tests/test_institution_laws.py`.
- sentence definitions for a narrow source slice.
- loss-report type and path vocabulary.
- Hypothesis strategies for that source slice.
- at least one deliberate mutation per law that turns the law red.

Recommended first slice:

```text
ROM/Merc reset sentences
Circle AC/hitroll phrase transforms
CoffeeMud nested raw_text/raw_data preservation
LambdaMOO typed value distinctions
```

This slice is small but representative:

- reset arity catches same-field/different-meaning failures.
- Circle AC/hitroll catches scale and transform failures.
- CoffeeMud raw payloads catch residual preservation failures.
- LambdaMOO typed values catch representation-collapse failures.

Each law must be falsifiable. Examples:

- swapping `MooError(n)` with `ObjNum(n)` must fail typed-value identity.
- dropping a ROM/Merc reset argument must fail reset sentence preservation.
- removing Circle AC/hitroll scaling must fail the transform law.
- dropping CoffeeMud nested `raw_text`/`raw_data` must fail residual
  preservation.

A law with no demonstrated failing mutation does not count as delivered.

## Phase Plan

### Phase 1: Inventory

Document current native signatures, phrase types, sentence families, model
fields, and known discarded data for each existing reader:

- ROM
- Merc
- SMAUG
- SWR/FUSS
- Circle
- CoffeeMud

Also document LambdaMOO as an external programmable-world institution, using
`lambdamoo-db-py` as the evidence source.

Acceptance:

- every listed reader/runtime has a signature inventory.
- every known skip/discard/normalization is recorded.
- every reader-level transform that destroys native source tokens is recorded.
- no implementation code is changed.

### Phase 2: Sentence and Loss Core

Define a small, concrete sentence representation and a `LossReport`.

Start with a flat sentence shape:

```python
Sentence(pred: str, args: tuple[Value, ...])
```

Do not add nested term algebras, quantified formulas, or proof machinery until
a concrete law requires them.

Acceptance:

- existing parsed objects can project into sentence sets for the first slice.
- value and sentence equality use structural identity.
- loss paths are stable and testable.
- source sentences partition into preserved and lost sentences without overlap.
- no pairwise converters are introduced.

### Phase 3: Native Bijectivity

Add native writer or rendering support one dialect at a time.

Acceptance per dialect:

```text
parse(render(parse(source))) == parse(source)
```

For LambdaMOO-like databases, use external reference outputs where available;
line-level or byte-level comparison is stronger than parse-parse comparison.

For current area readers, native bijectivity may require preserving raw tokens
that are currently normalized during parse. Circle AC and hitroll are known
examples: the current reader stores transformed values, not the original source
tokens.

### Phase 4: Area-Theory Morphisms

Implement morphisms among area dialects through the canonical area theory.

Acceptance:

- morphisms preserve declared source sentence families.
- every unsupported sentence is present in the loss report.
- Hypothesis can find transform and arity mistakes.

### Phase 5: Programmable Realizations

Implement realization policies from canonical area theory into LambdaMOO and
MUSH-like object worlds.

Acceptance:

- generated target object graph satisfies the source area sentences under the
  chosen policy.
- generated scaffold is declared.
- extra target facts are either scaffold, policy, or loss/bug.

### Phase 6: Duplex and Multiplex Worlds

Support mixed theories: target-native constraints plus source-world sentences.

Examples:

- area graph plus MOO permission policy.
- Circle zones plus ROM-like rooms.
- CoffeeMud XML residuals plus canonical room graph.
- MUSH locks plus canonical exits.

Acceptance:

- target-native constraints can coexist with canonical world facts.
- satisfaction laws still run over the combined theory.

## What Not To Build Yet

Do not start with:

- a large abstract category framework.
- a service-locator-style conversion registry.
- pairwise converter methods between every dialect.
- a giant canonical model that tries to contain every native field directly.
- byte-perfect writers before semantic round-trip laws exist.
- MUSH/MOO realization before the canonical sentence and loss machinery exists.
- broad refactors of existing readers just to make the theory look tidy.

The first implementation should be deliberately boring: sentence objects,
projection functions, loss reports, and Hypothesis laws.

## Practical API Direction

Public API should stay ergonomic:

```python
source = RomAreaFile.load(path)
target = CoffeeMudArea.from_other(source.area, loss=losses)
text = CoffeeMudAreaFile.dumps(target)
```

But internally:

```text
native model -> source sentences -> morphism -> target sentences/model
```

The user-facing API can be beautiful. The correctness ledger must remain
explicit.

## External Review Note

A Claude design critique was run against `area_reader`, `PROJECT.md`,
`lambdamoo-db-py`, and the Goguen/Burstall paper notes. The critique changed
this document in several concrete ways:

- structural value identity is required before typed LambdaMOO laws are valid.
- the first laws must be non-vacuous projection and loss-partition laws.
- every law needs a deliberate mutation that turns it red.
- LambdaMOO is version-indexed by database format features.
- `from_other` needs a typed morphism table rather than hidden pairwise
  converter dispatch.
- free realization belongs in later phases, not in the initial implementation
  slice.
