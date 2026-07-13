import argparse
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

from area_reader import CircleAreaFile


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
		encoding="latin-1",
		timeout=timeout,
	)


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Build CircleMUD in a temporary tree and boot its canonical world.",
	)
	parser.add_argument("upstream", type=Path)
	args = parser.parse_args()

	upstream = args.upstream.resolve()
	area_file = CircleAreaFile(upstream)
	area_file.load_sections()

	with tempfile.TemporaryDirectory(prefix="area-reader-circle-") as temporary:
		root = Path(temporary) / "circlemud"
		shutil.copytree(
			upstream,
			root,
			ignore=shutil.ignore_patterns(".git", "*.o", "circle"),
		)
		area_file.write(root)

		configure = run(
			[
				"wsl",
				"--cd",
				str(root),
				"env",
				"CFLAGS=-g -O2 -fcommon",
				"./configure",
			],
			timeout=120,
		)
		if configure.returncode != 0:
			print(configure.stdout)
			print(configure.stderr)
			return configure.returncode

		build = run(
			["wsl", "--cd", str(root), "make", "-C", "src", "-j2", "circle"],
			timeout=240,
		)
		if build.returncode != 0:
			print(build.stdout)
			print(build.stderr)
			return build.returncode

		port = available_port()
		started = time.monotonic()
		boot = run(
			[
				"wsl",
				"--cd",
				str(root),
				"timeout",
				"5s",
				"./bin/circle",
				str(port),
			],
			timeout=15,
		)
		elapsed = time.monotonic() - started
		boot_output = boot.stdout + boot.stderr
		for line in boot_output.splitlines():
			if "CircleMUD" in line or "Entering game loop" in line or "SYSERR" in line:
				print(line)
		if "Entering game loop" not in boot_output:
			print("CircleMUD did not reach its game loop.")
			return boot.returncode or 1
		if elapsed < 4.5:
			print("CircleMUD exited before the five-second boot window.")
			return boot.returncode or 1

	print("CircleMUD accepted the canonical indexed world and remained live through the boot window.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
