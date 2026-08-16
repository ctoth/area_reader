"""Serialization of parsed area models."""

import enum

from cattr import converters


class EnumNameConverter(converters.Converter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_unstructure_hook_func(
            lambda field_type: isinstance(field_type, type) and issubclass(field_type, enum.Enum),
            self._unstructure_enum,
        )

    def _unstructure_enum(self, obj):
        # Composite Flag values have no .name before Python 3.11; decompose
        # into single-bit member names in ascending bit order, matching the
        # names 3.11+ produces, so JSON output is identical on every version.
        name = obj.name
        if name is None and isinstance(obj, enum.Flag):
            bits = {
                member.value: member.name
                for member in type(obj).__members__.values()
                if member.value and not member.value & (member.value - 1)
            }
            names = [bits[bit] for bit in sorted(bits) if obj.value & bit]
            covered = 0
            for bit in bits:
                if obj.value & bit:
                    covered |= bit
            if names and covered == obj.value:
                name = "|".join(names)
        if name is None:
            name = str(obj.value)
        return obj.__class__.__name__ + "." + name
