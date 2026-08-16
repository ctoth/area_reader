"""Readers for supported MUD area formats."""

from area_reader.dialects.circle import CircleAreaFile
from area_reader.dialects.coffeemud import CoffeeMudAreaFile
from area_reader.dialects.merc import MercAreaFile
from area_reader.dialects.rom import RomAreaFile
from area_reader.dialects.smaug import SmaugAreaFile
from area_reader.dialects.swr import SwrAreaFile

__all__ = (
    "CircleAreaFile",
    "CoffeeMudAreaFile",
    "MercAreaFile",
    "RomAreaFile",
    "SmaugAreaFile",
    "SwrAreaFile",
)
