import argparse
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import area_reader.dialects.smaug


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wsl_path(path: Path) -> str:
    converted = subprocess.run(
        ["wsl", "wslpath", "-u", path.as_posix()],
        check=True,
        capture_output=True,
        text=True,
    )
    return converted.stdout.strip()


def run(
    command: list[str],
    *,
    timeout: int,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="latin-1",
        timeout=timeout,
        env=environment,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build SMAUG in a temporary tree and boot it with a rendered area.",
    )
    parser.add_argument("upstream", type=Path)
    parser.add_argument("source_area", type=Path)
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    source_area = args.source_area.resolve()
    area_file = area_reader.dialects.smaug.SmaugAreaFile(source_area)
    area_file.load_sections()
    rendered = area_file.dumps()

    with tempfile.TemporaryDirectory(prefix="area-reader-smaug-") as temporary:
        root = Path(temporary) / "smaug"
        shutil.copytree(upstream, root)
        (root / "m4").mkdir(exist_ok=True)
        makefile = root / "Makefile.am"
        makefile_text = makefile.read_text(encoding="latin-1")
        with makefile.open("w", encoding="latin-1", newline="\n") as output:
            output.write(makefile_text.replace("ACLOCAL_AMFLAGS = -I m4\n", ""))
        configure_source = root / "configure.ac"
        configure_text = configure_source.read_text(encoding="latin-1")
        configure_text = configure_text.replace("IT_PROG_INTLTOOL([0.50.1])\n", "")
        configure_text = configure_text.replace("po/Makefile.in\n", "")
        with configure_source.open("w", encoding="latin-1", newline="\n") as output:
            output.write(configure_text)
        runtime = root / "runtime"
        shutil.copytree(root / "db", runtime)
        for relative in (
            Path("area") / source_area.name,
            Path("area") / "en" / source_area.name,
        ):
            target = runtime / relative
            if target.exists():
                with target.open("w", encoding="latin-1", newline="\n") as output:
                    output.write(rendered)
        with (runtime / "area" / "area.lst").open("w", encoding="latin-1", newline="\n") as area_list:
            area_list.write(f"help.are\ngods.are\nlimbo.are\n{source_area.name}\n$\n")

        wsl_root = wsl_path(root)
        wsl_runtime = wsl_path(runtime) + "/"
        bootstrap = run(
            ["wsl", "--cd", str(root), "autoreconf", "-fi"],
            timeout=120,
        )
        if bootstrap.returncode != 0:
            print(bootstrap.stdout)
            print(bootstrap.stderr)
            return bootstrap.returncode

        configure = run(
            [
                "wsl",
                "--cd",
                str(root),
                "./configure",
                f"--prefix={wsl_root}/install",
                "CFLAGS=-g -O2 -fcommon",
            ],
            timeout=120,
        )
        if configure.returncode != 0:
            print(configure.stdout)
            print(configure.stderr)
            return configure.returncode

        header = root / "src" / "smaug.h"
        header_text = header.read_text(encoding="latin-1")
        header_text = header_text.replace(
            f'#define RUNDIR "{wsl_root}/install/com/smaug/"',
            f'#define RUNDIR "{wsl_runtime}"',
        )
        with header.open("w", encoding="latin-1", newline="\n") as output:
            output.write(header_text)

        build = run(
            ["wsl", "--cd", str(root / "src"), "make", "-j2"],
            timeout=240,
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
                str(root),
                "env",
                "LANG=en",
                "timeout",
                "8s",
                "./src/smaug",
                str(port),
            ],
            timeout=15,
        )
        boot_output = boot.stdout + boot.stderr
        for line in boot_output.splitlines():
            if source_area.name in line or "ready at address" in line:
                print(line)
        if boot.returncode != 124:
            return boot.returncode or 1
        if source_area.name not in boot_output:
            print(f"The engine stayed live but did not report loading {source_area.name}.")
            return 1

    print(f"SMAUG accepted {source_area} and remained live through the boot window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
