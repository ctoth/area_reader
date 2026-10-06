"""Reading and writing the files of an area source directory."""

import io
import re
from pathlib import Path

import yaml
from attr import Factory, attr, attributes

HEADER_NAME = "area.yaml"
LOCK_NAME = "vnums.lock.yaml"
SOURCE_SUFFIXES = (".yaml", ".yml", ".json")
FAMILIES = ("rooms", "mobs", "objects")
SINGULAR = {"rooms": "room", "mobs": "mob", "objects": "object"}
RECORD_LISTS = ("helps", "resets", "shops", "specials")
TOP_LEVEL_KEYS = ("area", *FAMILIES, *RECORD_LISTS, "mobprogs", "include")
ID = re.compile(r"[a-z][a-z0-9_-]*")


class SourceError(Exception):
    """A fault in an area source directory, located by file and key path."""

    def __init__(self, file, key, reason):
        super().__init__(": ".join(part for part in (str(file), key, reason) if part))
        self.file = str(file)
        self.key = key
        self.reason = reason


@attributes(frozen=True)
class At:
    """Where a value was written: its file and the keys leading to it."""

    file = attr()
    path = attr(default=())

    def __truediv__(self, key):
        return At(self.file, (*self.path, str(key)))

    def error(self, reason):
        return SourceError(self.file, ".".join(self.path), reason)


@attributes
class Source:
    """The merged contents of one source directory. Records are kept with the place they were written."""

    directory = attr()
    name = attr()
    area = attr(default=None)
    area_at = attr(default=None)
    rooms = attr(default=Factory(dict))
    mobs = attr(default=Factory(dict))
    objects = attr(default=Factory(dict))
    helps = attr(default=Factory(list))
    resets = attr(default=Factory(list))
    shops = attr(default=Factory(list))
    specials = attr(default=Factory(list))
    mobprogs = attr(default=Factory(dict))
    lock = attr(default=Factory(dict))


class UniqueKeyLoader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    """YAML keeps the last of two equal keys; a source file must not define a thing twice."""

    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep)
        if len(mapping) != len(node.value):
            seen = set()
            for key_node, _value in node.value:
                key = self.construct_object(key_node, deep=True)
                if key in seen:
                    raise SourceError(
                        self.name, "", f"key {key!r} is written twice (line {key_node.start_mark.line + 1})"
                    )
                seen.add(key)
        return mapping


class Flow(list):
    """A list written on one line: ``[indoors, law]``."""


class FlowMap(dict):
    """A mapping written on one line: ``{first: 60000, size: 100}``."""


class SourceDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        del indentless
        return super().increase_indent(flow, False)

    def analyze_scalar(self, scalar):
        analysis = super().analyze_scalar(scalar)
        # PyYAML refuses the block style for text with a space before a line break, which stock room
        # descriptions often have. A literal block keeps such spaces, so allow it.
        if analysis.multiline and not analysis.allow_block and self.block_safe(scalar):
            analysis.allow_block = True
        return analysis

    @staticmethod
    def block_safe(scalar):
        return all(char == "\n" or " " <= char <= "~" or "\xa0" <= char <= "\xff" for char in scalar)


def represent_text(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


SourceDumper.add_representer(str, represent_text)
SourceDumper.add_representer(
    Flow, lambda dumper, value: dumper.represent_sequence("tag:yaml.org,2002:seq", value, flow_style=True)
)
SourceDumper.add_representer(
    FlowMap, lambda dumper, value: dumper.represent_mapping("tag:yaml.org,2002:map", value, flow_style=True)
)


def dump_yaml(data):
    return yaml.dump(data, Dumper=SourceDumper, sort_keys=False, allow_unicode=True, width=100000)


class NamedText(io.StringIO):
    """Text that knows its file, so that a YAML syntax error names it."""

    def __init__(self, text, name):
        super().__init__(text)
        self.name = name


def load_yaml(text, name):
    loader = UniqueKeyLoader(NamedText(text, str(name)))
    loader.name = str(name)
    data = loader.get_single_data()
    loader.dispose()
    return data


def read_text(path):
    with open(path, encoding="utf-8", newline=None) as source_file:
        return source_file.read()


def check_text(value, at):
    """Reject text that a ROM area file cannot hold."""
    if "~" in value:
        raise at.error("'~' ends a string in a ROM area file and cannot appear in text")
    for char in value:
        if ord(char) > 255:
            raise at.error(f"character {char!r} (U+{ord(char):04X}) cannot be written to a Latin-1 area file")


def check_tree(value, at):
    if isinstance(value, str):
        check_text(value, at)
    elif isinstance(value, dict):
        for key, item in value.items():
            check_tree(key, at / key)
            check_tree(item, at / key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_tree(item, at / index)


def label(path):
    return Path(path).as_posix()


def source_files(directory):
    header = directory / HEADER_NAME
    if not header.is_file():
        raise SourceError(label(directory), "", f"a source directory needs {HEADER_NAME}")
    others = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES and path != header and path.name != LOCK_NAME
    ]
    return [header, *sorted(others, key=lambda path: path.relative_to(directory).as_posix())]


def merge_file(source, path, seen):
    file = label(path)
    if path.resolve() in seen:
        raise SourceError(file, "", "this file is read twice; an include names a file already in the directory")
    seen.add(path.resolve())
    at = At(file)
    data = load_yaml(read_text(path), file)
    if data is None:
        return
    if not isinstance(data, dict):
        raise at.error("a source file is a mapping of top-level keys")
    check_tree(data, at)
    for key in data:
        if key not in TOP_LEVEL_KEYS:
            raise (at / key).error(f"unknown top-level key; expected one of {', '.join(TOP_LEVEL_KEYS)}")

    if "area" in data:
        if source.area is not None:
            raise (at / "area").error(f"the area header is already written in {source.area_at.file}")
        source.area = data["area"]
        source.area_at = at / "area"
    for family in FAMILIES:
        records = data.get(family) or {}
        if not isinstance(records, dict):
            raise (at / family).error("expected a mapping from id to record")
        merged = getattr(source, family)
        for identifier, record in records.items():
            where = at / family / identifier
            if not isinstance(identifier, str) or not ID.fullmatch(identifier):
                raise where.error("an id is a lowercase slug: a letter, then letters, digits, '_' or '-'")
            if identifier in merged:
                raise where.error(
                    f"{SINGULAR[family]} id {identifier!r} is already defined in {merged[identifier][1].file}"
                )
            merged[identifier] = (record, where)
    for name in RECORD_LISTS:
        records = data.get(name) or []
        if not isinstance(records, list):
            raise (at / name).error("expected a list")
        getattr(source, name).extend((record, at / name / index) for index, record in enumerate(records))
    mobprogs = data.get("mobprogs") or {}
    if not isinstance(mobprogs, dict):
        raise (at / "mobprogs").error("expected a mapping from program vnum to code")
    for vnum, code in mobprogs.items():
        if vnum in source.mobprogs:
            raise (at / "mobprogs" / vnum).error(
                f"program {vnum} is already written in {source.mobprogs[vnum][1].file}"
            )
        source.mobprogs[vnum] = (code, at / "mobprogs" / vnum)

    includes = data.get("include") or []
    if not isinstance(includes, list):
        raise (at / "include").error("expected a list of file paths")
    for index, included in enumerate(includes):
        if not isinstance(included, str):
            raise (at / "include" / index).error("expected a file path")
        target = path.parent / included
        if not target.is_file():
            raise (at / "include" / index).error(f"no such file: {label(target)}")
        merge_file(source, target, seen)


def load_source(directory):
    """Read a source directory: ``area.yaml`` first, then every other source file in sorted path order."""
    directory = Path(directory)
    source = Source(directory=directory, name=directory.resolve().name)
    seen = set()
    for path in source_files(directory):
        if path.resolve() not in seen:
            merge_file(source, path, seen)
    if source.area is None:
        raise SourceError(label(directory / HEADER_NAME), "area", "the header file has no area key")
    lock_path = directory / LOCK_NAME
    if lock_path.is_file():
        lock = load_yaml(read_text(lock_path), label(lock_path)) or {}
        lock_at = At(label(lock_path))
        if not isinstance(lock, dict) or not all(isinstance(lock.get(family, {}), dict) for family in FAMILIES):
            raise lock_at.error("expected a mapping from rooms, mobs and objects to their id-to-vnum mappings")
        source.lock = lock
    return source


def write_files(directory, files):
    """Write a mapping from relative path to text below ``directory``."""
    directory = Path(directory)
    for relative, text in files.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as output:
            output.write(text)
