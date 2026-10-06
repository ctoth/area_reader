"""Area source directories: YAML that compiles to a ROM 2.4 area file, and back.

``build`` compiles a source directory; ``unbuild`` writes a parsed ROM area as one. The format is described
in the README under "Writing new areas". This package needs PyYAML (the ``authoring`` extra).
"""

from area_reader.authoring.builder import Built, build, compile_source, parse, render
from area_reader.authoring.normal import NORMALIZATIONS, normalized, reset_groups
from area_reader.authoring.source import SourceError, load_source, write_files
from area_reader.authoring.unbuilder import unbuild, unbuild_file

__all__ = [
    "NORMALIZATIONS",
    "Built",
    "SourceError",
    "build",
    "compile_source",
    "load_source",
    "normalized",
    "parse",
    "render",
    "reset_groups",
    "unbuild",
    "unbuild_file",
    "write_files",
]
