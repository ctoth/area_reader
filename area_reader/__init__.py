"""Readers for supported MUD area formats."""

from area_reader.dialects.circle import CircleAreaFile
from area_reader.dialects.coffeemud import CoffeeMudAreaFile
from area_reader.dialects.godwars import GodWarsAreaFile
from area_reader.dialects.medievia import MedieviaAreaFile
from area_reader.dialects.merc import MercAreaFile
from area_reader.dialects.rom import RomAreaFile
from area_reader.dialects.smaug import SmaugAreaFile
from area_reader.dialects.swr import SwrAreaFile
from area_reader.dialects.tba import TbaAreaFile

__all__ = (
    "CircleAreaFile",
    "CoffeeMudAreaFile",
    "GodWarsAreaFile",
    "MedieviaAreaFile",
    "MercAreaFile",
    "RomAreaFile",
    "SmaugAreaFile",
    "SwrAreaFile",
    "TbaAreaFile",
)
