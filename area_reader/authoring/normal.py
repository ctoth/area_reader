"""What ``build(unbuild(area))`` is allowed to change, and the comparison that allows exactly that."""

import copy

from area_reader.constants import EXIT_FLAGS

# Each name is one way a rebuilt area may differ from the area it was unbuilt from. ``normalized`` applies
# exactly these, so two areas are equal under it only when they differ in no other way.
NORMALIZATIONS = (
    # A source directory hangs each reset on its room, so the builder emits resets room by room: a room's
    # door resets, then its mobs, then its objects, then its exit shuffle; raw resets last. The stock files
    # order them as their builders typed them. Resets that depend on one another (an M and the G/E that
    # equip it, an O/G/E and the P resets that fill it) stay together and in order: see ``reset_groups``.
    "reset_group_order",
    # The text after a reset, shop or special line, and comment-only lines, are not carried into a source
    # directory unless the reset is kept raw. src/db.c reads them with fread_to_eol() and drops them; in the
    # stock files they name the mob or object, which the source directory does with ids.
    "line_comments",
    # Shops and specials are written on their mob and emitted in mob order. src/db.c load_shops() and
    # load_specials() store each on its mobile, so their order in the file has no effect.
    "shop_and_special_order",
    # Program bodies are emitted in vnum order; ROM looks them up by vnum.
    "program_body_order",
    # A room's exits are emitted north, east, south, west, up, down. src/db.c load_rooms() stores them in an
    # array indexed by direction.
    "exit_order",
    # An exit with no door is written without a key and built with key -1. The stock files write -1 or 0
    # there; only src/act_move.c do_lock() and do_unlock() read the key, and only for a closed door.
    "doorless_exit_key",
    # Room, mob, exit and extra descriptions, and a mob's long description, end with a newline when they are
    # not empty. A few stock texts lack it, which runs the next line of output onto the same line.
    "final_newline",
)


def reset_groups(resets):
    """Split a reset list into the groups that must stay together, each in its original order.

    An M opens a group that takes the G and E resets after it, until a reset of another kind. An O is a
    group. A P joins the nearest earlier group that loads the object it fills (src/db.c reset_area() puts it
    in the newest such object, wherever in the list that was loaded). Every other reset (D, R, and a G, E or
    P with nothing to belong to) is a group of its own. Comment-only lines belong to no group.

    The groups partition the resets: flattening them in order of each group's first reset, and merging by
    original position, gives the list back without its comment lines.
    """
    groups = []
    equipping = None
    for reset in resets:
        if reset.command is None:
            continue
        if reset.command in ("G", "E") and equipping is not None:
            equipping.append(reset)
            continue
        if reset.command == "P":
            loader = next(
                (
                    group
                    for group in reversed(groups)
                    if any(member.command in ("O", "G", "E", "P") and member.arg1 == reset.arg3 for member in group)
                ),
                None,
            )
            if loader is not None:
                loader.append(reset)
                continue
        group = [reset]
        groups.append(group)
        if reset.command == "M":
            equipping = group
        elif reset.command != "P":
            equipping = None
    return groups


def reset_key(reset):
    """A reset without its comment, as a tuple that sorts."""
    return tuple(
        (value is None, value or 0) if not isinstance(value, str) else (False, value)
        for value in (reset.command, reset.if_flag, reset.arg1, reset.arg2, reset.arg3, reset.arg4)
    )


def with_final_newline(text):
    return text if not text or text.endswith("\n") else text + "\n"


def normalized(area):
    """Return a copy of ``area`` with every declared normalization applied."""
    area = copy.deepcopy(area)
    area.resets = sorted(tuple(reset_key(reset) for reset in group) for group in reset_groups(area.resets))
    for shop in area.shops:
        shop.comment = ""
    area.shops.sort(key=lambda shop: shop.keeper)
    area.specials = [special for special in area.specials if special.command is not None]
    for special in area.specials:
        special.comment = ""
    area.specials.sort(key=lambda special: (special.arg1, special.arg2))
    area.mobprogs = dict(sorted(area.mobprogs.items()))
    for room in area.rooms.values():
        room.description = with_final_newline(room.description)
        room.exits.sort(key=lambda exit: exit.door.value)
        for exit in room.exits:
            exit.description = with_final_newline(exit.description)
            if not exit.exit_info & EXIT_FLAGS.ISDOOR:
                exit.key = -1
    for mob in area.mobs.values():
        mob.long_desc = with_final_newline(mob.long_desc)
        mob.description = with_final_newline(mob.description)
    for record in (*area.rooms.values(), *area.objects.values()):
        for extra in record.extra_descriptions:
            extra.description = with_final_newline(extra.description)
    return area
