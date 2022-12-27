import area_reader
import os

def test_loading_rom_area(rom_path):
	af = area_reader.RomAreaFile(rom_path)
	af.load_sections()
	assert af.area
	assert af.as_dict()

def test_loading_merc_area(merc_path):
	af = area_reader.MercAreaFile(merc_path)
	af.load_sections()
	assert af.area
