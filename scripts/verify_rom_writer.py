"""Build a ROM server in a temporary copy of its tree and boot it with a rendered area.

    python scripts/verify_rom_writer.py UPSTREAM AREA.are [--new]

UPSTREAM is one of two trees, told apart by src/mob_prog.c:

- stock ROM 2.4b6. It reads neither #AREADATA nor mob programs, so with --new both are rewritten away
  first, and the run says so.
- QuickMUD (ROM 2.4b6 with OLC and MOBprograms), which reads both. Verified against
  https://github.com/avinson/rom24-quickmud at commit 364c26f1b124e238156e3d11b4e72a8992c66b74.

Both keep vnums in a sh_int, so an area booted here stays at or below 32767. Needs WSL with make and gcc.
"""

import argparse
import collections
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import area_reader.dialects.rom
from area_reader.native import render_document

BUG = "[*****] BUG"


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
        output.write(comm_text.replace(legacy_gettimeofday, ""))


def is_quickmud(root: Path) -> bool:
    return (root / "src" / "mob_prog.c").is_file()


def modernize_quickmud(root: Path) -> None:
    comm = root / "src" / "comm.c"
    comm_text = comm.read_text(encoding="latin-1")
    legacy_gettimeofday = "int gettimeofday args ((struct timeval * tp, struct timezone * tzp));\n"
    if legacy_gettimeofday not in comm_text:
        raise RuntimeError("Expected the QuickMUD gettimeofday declaration")
    with comm.open("w", encoding="latin-1", newline="\n") as output:
        output.write(comm_text.replace(legacy_gettimeofday, ""))


def make_arguments(root: Path) -> list[str]:
    if is_quickmud(root):
        # The inter-MUD client is compiled in (imc.c does not build without it) but imc/imc.config ships
        # with Autoconnect 0, so the server does not dial out.
        return ["C_FLAGS=-O -g3 -Wall -fcommon -DIMC -DIMCROM"]
    return ["NOCRYPT=-DNOCRYPT", "C_FLAGS=-Wall -O -g -DNOCRYPT -fcommon"]


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
        # gcc quotes with UTF-8 and the area files are Latin-1; neither may stop the run.
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def boot(root: Path) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "wsl",
            "--cd",
            str(root / "area"),
            "timeout",
            "5s",
            # QuickMUD's Makefile links the server into the area directory.
            "./rom" if is_quickmud(root) else "../src/rom",
            str(available_port()),
        ],
        timeout=15,
    )


def log_lines(process: subprocess.CompletedProcess[str]) -> list[str]:
    """ROM's log without its timestamps, so two boots can be compared."""
    lines = (process.stdout + process.stderr).splitlines()
    return [line.split(" :: ", 1)[-1] for line in lines if line.strip() and "ready to rock on port" not in line]


def for_stock_rom(area: area_reader.dialects.rom.RomArea) -> list[str]:
    """Rewrite what ROM 2.4b6 cannot read, and say what was changed.

    The stock engine knows neither #AREADATA nor mob programs (src/db.c boot_db() has no such sections and
    src/db2.c load_mobiles() no M line); both come from the OLC and MOBprogram patches.
    """
    changes = []
    if area.header_format == "areadata":
        area.header_format = "rom"
        area.builders = ""
        area.security = None
        area.zone = None
        changes.append("#AREADATA header written as #AREA (builders and security dropped)")
    programs = sum(len(mob.mprogs) for mob in area.mobs.values())
    if programs or area.mobprogs:
        for mob in area.mobs.values():
            mob.mprogs = []
        changes.append(f"{programs} mob program triggers and {len(area.mobprogs)} program bodies dropped")
        area.mobprogs.clear()
    return changes


def list_area(root: Path, name: str) -> None:
    """Add an area file to area.lst, before the line that ends the list."""
    listing = root / "area" / "area.lst"
    names = listing.read_text(encoding="latin-1").split()
    if name in names:
        raise SystemExit(f"{name} is already listed by the upstream ROM tree; run without --new")
    names.insert(names.index("$"), name)
    with listing.open("w", encoding="latin-1", newline="\n") as output:
        output.write("\n".join(names) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build ROM in a temporary tree and boot it with a rendered area.",
    )
    parser.add_argument("upstream", type=Path)
    parser.add_argument("source_area", type=Path)
    parser.add_argument(
        "--new",
        action="store_true",
        help="the area is not part of the upstream tree: add it to area.lst, and for a stock ROM tree "
        "rewrite what that engine cannot read (#AREADATA, mob programs)",
    )
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    source_area = args.source_area.resolve()
    area_file = area_reader.dialects.rom.RomAreaFile(source_area)
    area_file.load_sections()
    print(f"Engine: {'QuickMUD' if is_quickmud(upstream) else 'stock ROM 2.4b6'} at {upstream}")
    if args.new and not is_quickmud(upstream):
        for change in for_stock_rom(area_file.area):
            print(f"for stock ROM 2.4b6: {change}")
    rendered = render_document(area_file.area, area_file.area.NATIVE_SECTIONS, area_file.skipped_sections)

    with tempfile.TemporaryDirectory(prefix="area-reader-rom-") as temporary:
        root = Path(temporary) / "Rom24b6"
        shutil.copytree(upstream, root, ignore=shutil.ignore_patterns(".git"))
        target = root / "area" / source_area.name
        if not args.new and not target.exists():
            raise SystemExit(
                f"The source basename must already be listed by the upstream ROM tree: {source_area.name} "
                "(pass --new for an area that is not)"
            )
        if is_quickmud(root):
            modernize_quickmud(root)
        else:
            modernize_header_order(root)

        build = run(["wsl", "--cd", str(root), "make", "-C", "src", *make_arguments(root)], timeout=300)
        if build.returncode != 0:
            print(build.stdout)
            print(build.stderr)
            return build.returncode

        stock = boot(root)
        if stock.returncode != 124:
            print(stock.stdout)
            print(stock.stderr)
            print("The unmodified ROM tree did not stay up through the boot window.")
            return stock.returncode or 1
        baseline = collections.Counter(log_lines(stock))
        if args.new:
            list_area(root, source_area.name)
        with target.open("w", encoding="latin-1", newline="\n") as output:
            output.write(rendered)

        booted = boot(root)
        print(booted.stdout)
        print(booted.stderr)
        if booted.returncode != 124:
            print(f"ROM exited with status {booted.returncode} instead of staying up.")
            return booted.returncode or 1

    # The engine reports most area faults with bug() and carries on, so staying up is not enough: compare its
    # log with the unmodified tree's. Lines that are not bugs ("Err: obj ..." level warnings) come and go with
    # the resets' dice, so only bug lines decide the result.
    logged = collections.Counter(log_lines(booted))
    for title, lines in (
        (f"with this {source_area.name} and not with the upstream tree", logged - baseline),
        (f"with the upstream tree and not with this {source_area.name}", baseline - logged),
    ):
        print(f"Log lines ROM wrote {title}: {sum(lines.values())}")
        for line, count in lines.items():
            print(f"  {line}" + (f"  (x{count})" if count > 1 else ""))
    if any(BUG in line for line in logged - baseline):
        print(f"ROM logged bugs for {source_area.name}.")
        return 1
    print(f"ROM accepted {source_area} and remained live through the boot window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
