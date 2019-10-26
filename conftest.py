import os

def pytest_generate_tests(metafunc):
	if "rom_path" in metafunc.fixturenames:
		metafunc.parametrize("rom_path", files_in_directory('test/rom'))
	if "merc_path" in metafunc.fixturenames:
			metafunc.parametrize("merc_path", files_in_directory('test/merc'))

def files_in_directory(directory):
		for f in os.listdir(directory):
			path = os.path.join(directory, f)
			yield path
