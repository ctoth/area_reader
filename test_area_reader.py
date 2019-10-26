import area_reader
import os

def test_loading_rom_area(rom_path):
	af = area_reader.RomAreaFile(rom_path)
	af.load_sections()
	assert af.area

def test_loading_merc_areas(merc_path):
	af = area_reader.MercAreaFile(merc_path)
	af.load_sections()
	assert af.area
