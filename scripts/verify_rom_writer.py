import argparse
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile

from area_reader import RomAreaFile


def modernize_header_order(root: Path) -> None:
	tables = root / "src" / "tables.h"
	text = tables.read_text(encoding="latin-1")
	declarations_start = text.index("/* game tables */")
	definitions_start = text.index("struct flag_type")
	declarations = text[declarations_start:definitions_start]
	definitions = text[definitions_start:]
	with tables.open("w", encoding="latin-1", newline="\n") as output:
		output.write(text[:declarations_start])
		output.write(definitions.rstrip())
		output.write("\n\n")
		output.write(declarations)

	comm = root / "src" / "comm.c"
	comm_text = comm.read_text(encoding="latin-1")
	legacy_gettimeofday = "int\tgettimeofday\targs( ( struct timeval *tp, struct timezone *tzp ) );\n"
	if legacy_gettimeofday not in comm_text:
		raise RuntimeError("Expected the ROM 2.4b6 gettimeofday declaration")
	with comm.open("w", encoding="latin-1", newline="\n") as output:
		output.write(comm_text.replace(legacy_gettimeofday, ''))


def available_port() -> int:
	with socket.socket() as listener:
		listener.bind(("127.0.0.1", 0))
		return listener.getsockname()[1]


def run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		command,
		check=False,
		capture_output=True,
		text=True,
		timeout=timeout,
	)


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Build ROM in a temporary tree and boot it with a rendered area.",
	)
	parser.add_argument("upstream", type=Path)
	parser.add_argument("source_area", type=Path)
	args = parser.parse_args()

	upstream = args.upstream.resolve()
	source_area = args.source_area.resolve()
	area_file = RomAreaFile(source_area)
	area_file.load_sections()
	rendered = area_file.dumps()

	with tempfile.TemporaryDirectory(prefix="area-reader-rom-") as temporary:
		root = Path(temporary) / "Rom24b6"
		shutil.copytree(upstream, root)
		target = root / "area" / source_area.name
		if not target.exists():
			raise SystemExit(
				"The source basename must already be listed by the upstream ROM tree: %s"
				% source_area.name
			)
		with target.open("w", encoding="latin-1", newline="\n") as output:
			output.write(rendered)
		modernize_header_order(root)

		build = run(
			[
				"wsl",
				"--cd",
				str(root),
				"make",
				"-C",
				"src",
				"NOCRYPT=-DNOCRYPT",
				"C_FLAGS=-Wall -O -g -DNOCRYPT -fcommon",
			],
			timeout=120,
		)
		if build.returncode != 0:
			print(build.stdout)
			print(build.stderr)
			return build.returncode

		port = available_port()
		boot = run(
			[
				"wsl",
				"--cd",
				str(root / "area"),
				"timeout",
				"5s",
				"../src/rom",
				str(port),
			],
			timeout=15,
		)
		print(boot.stdout)
		print(boot.stderr)
		if boot.returncode != 124:
			return boot.returncode or 1

	print("ROM accepted %s and remained live through the boot window." % source_area)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
