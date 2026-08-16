import argparse
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import area_reader.dialects.merc


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Boot a temporary Merc tree with a canonically rendered area.",
    )
    parser.add_argument("upstream", type=Path)
    parser.add_argument("source_area", type=Path)
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    source_area = args.source_area.resolve()
    area_file = area_reader.dialects.merc.MercAreaFile(source_area)
    area_file.load_sections()
    engine = wsl_path(upstream / "src" / "merc")

    with tempfile.TemporaryDirectory(prefix="area-reader-merc-") as temporary:
        root = Path(temporary) / "merc-mud"
        shutil.copytree(upstream, root)
        target = root / "area" / source_area.name
        if not target.exists():
            raise SystemExit(
                f"The source basename must already be listed by the upstream Merc tree: {source_area.name}"
            )
        with target.open("w", encoding="latin-1", newline="\n") as output:
            output.write(area_file.dumps())

        port = available_port()
        boot = subprocess.run(
            [
                "wsl",
                "--cd",
                str(root / "area"),
                "timeout",
                "5s",
                "/lib64/ld-linux-x86-64.so.2",
                engine,
                str(port),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        print(boot.stdout)
        print(boot.stderr)
        if boot.returncode != 124:
            return boot.returncode or 1

    print(f"Merc accepted {source_area} and remained live through the boot window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
