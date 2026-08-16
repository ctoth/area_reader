"""Declarative attrs field metadata shared by readers and writers."""

from attr import attr


def field(type=None, read=True, on_read=None, original_type=None, only_if=None, native=None, *args, **kwargs):
    metadata = {"read": read}
    if on_read:
        metadata["on_read"] = on_read
    if original_type:
        metadata["original_type"] = original_type
    if only_if:
        metadata["only_if"] = only_if
    if native:
        metadata["native"] = native
    return attr(*args, type=type, metadata=metadata, **kwargs)
