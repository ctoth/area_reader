"""Build a ROM server in a temporary copy of its tree and boot it with a rendered area.

    python scripts/verify_rom_writer.py UPSTREAM AREA.are [--new]

UPSTREAM is a ROM source tree. What its loader reads is taken from the tree itself (an "AREADATA" section
in src/db.c, src/mob_prog.c for mob programs), and with --new only what it cannot read is rewritten away,
which the run reports. Two trees are known to build:

- stock ROM 2.4b6, which reads neither #AREADATA nor mob programs;
- QuickMUD (ROM 2.4b6 with OLC and MOBprograms), which reads both: https://github.com/avinson/rom24-quickmud
  at commit 364c26f1b124e238156e3d11b4e72a8992c66b74.

Both keep vnums in a sh_int, so an area booted here stays at or below 32767. Needs WSL with make and gcc.
The exit status is 0 only when the server stays up and logs no bug it does not log without the area.
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
STOCK_GETTIMEOFDAY = "int\tgettimeofday\targs( ( struct timeval *tp, struct timezone *tzp ) );\n"
QUICKMUD_GETTIMEOFDAY = "int gettimeofday args ((struct timeval * tp, struct timezone * tzp));\n"


def source_text(root: Path, name: str) -> str:
    return (root / "src" / name).read_text(encoding="latin-1")


def reads_areadata(root: Path) -> bool:
    return '"AREADATA"' in source_text(root, "db.c")


def reads_programs(root: Path) -> bool:
    return (root / "src" / "mob_prog.c").is_file()


def modernize(root: Path) -> None:
    """Apply the fix a modern compiler needs, chosen by the declaration the tree's comm.c holds."""
    comm = source_text(root, "comm.c")
    if STOCK_GETTIMEOFDAY in comm:
        modernize_header_order(root)
    elif QUICKMUD_GETTIMEOFDAY in comm:
        modernize_quickmud(root)
    else:
        raise RuntimeError("comm.c has neither the ROM 2.4b6 nor the QuickMUD gettimeofday declaration")


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


def modernize_quickmud(root: Path) -> None:
    comm = root / "src" / "comm.c"
    comm_text = comm.read_text(encoding="latin-1")
    legacy_gettimeofday = "int gettimeofday args ((struct timeval * tp, struct timezone * tzp));\n"
    if legacy_gettimeofday not in comm_text:
        raise RuntimeError("Expected the QuickMUD gettimeofday declaration")
    with comm.open("w", encoding="latin-1", newline="\n") as output:
        output.write(comm_text.replace(legacy_gettimeofday, ""))


def make_arguments(root: Path) -> list[str]:
    if (root / "src" / "imc.c").is_file():
        # QuickMUD: the inter-MUD client is compiled in (imc.c does not build without it), but
        # imc/imc.config ships with Autoconnect 0, so the server does not dial out.
        return ["C_FLAGS=-O -g3 -Wall -fcommon -DIMC -DIMCROM"]
    return ["NOCRYPT=-DNOCRYPT", "C_FLAGS=-Wall -O -g -DNOCRYPT -fcommon"]


def server(root: Path) -> str:
    """The server's path from the area directory: QuickMUD's Makefile links it there, ROM's into src."""
    return "./rom" if "../area/rom" in source_text(root, "Makefile") else "../src/rom"


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
            server(root),
            str(available_port()),
        ],
        timeout=15,
    )


def log_lines(process: subprocess.CompletedProcess[str]) -> list[str]:
    """ROM's log without its timestamps, so two boots can be compared."""
    lines = (process.stdout + process.stderr).splitlines()
    return [line.split(" :: ", 1)[-1] for line in lines if line.strip() and "ready to rock on port" not in line]


def for_engine(area: area_reader.dialects.rom.RomArea, root: Path) -> list[str]:
    """Rewrite what the tree's loader cannot read, and say what was changed.

    Stock ROM 2.4b6 knows neither #AREADATA nor mob programs (src/db.c boot_db() has no such sections and
    src/db2.c load_mobiles() no M line); both come from the OLC and MOBprogram patches.
    """
    changes = []
    if area.header_format == "areadata" and not reads_areadata(root):
        area.header_format = "rom"
        area.builders = ""
        area.security = None
        area.zone = None
        changes.append("#AREADATA header written as #AREA (builders and security dropped)")
    programs = sum(len(mob.mprogs) for mob in area.mobs.values())
    if (programs or area.mobprogs) and not reads_programs(root):
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
        help="the area is not part of the upstream tree: add it to area.lst, and rewrite away what that "
        "tree's loader cannot read (#AREADATA, mob programs)",
    )
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    source_area = args.source_area.resolve()
    area_file = area_reader.dialects.rom.RomAreaFile(source_area)
    area_file.load_sections()
    print(
        f"Engine tree {upstream}: #AREADATA {'read' if reads_areadata(upstream) else 'not read'}, "
        f"mob programs {'read' if reads_programs(upstream) else 'not read'}"
    )
    if args.new:
        for change in for_engine(area_file.area, upstream):
            print(f"for this engine: {change}")
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
        modernize(root)

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
