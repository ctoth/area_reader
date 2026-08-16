import argparse
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import area_reader.dialects.swr


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Boot a temporary SWR/FUSS tree with a canonically rendered area.",
    )
    parser.add_argument("upstream", type=Path)
    parser.add_argument("source_area", type=Path)
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    source_area = args.source_area.resolve()
    area_file = area_reader.dialects.swr.SwrAreaFile(source_area)
    area_file.load_sections()
    rendered = area_file.dumps()

    with tempfile.TemporaryDirectory(prefix="area-reader-swr-") as temporary:
        root = Path(temporary) / "swrfuss"
        shutil.copytree(
            upstream,
            root,
            ignore=shutil.ignore_patterns(".git", "o", "*.o"),
        )
        target = root / "area" / source_area.name
        if not target.exists():
            raise SystemExit(f"The source basename must already be listed by the upstream SWR tree: {source_area.name}")
        with target.open("w", encoding="latin-1", newline="\n") as output:
            output.write(rendered)

        port = available_port()
        started = time.monotonic()
        boot = subprocess.run(
            [
                "wsl",
                "--cd",
                str(root / "area"),
                "timeout",
                "5s",
                "../src/swreality",
                str(port),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="latin-1",
            timeout=15,
        )
        elapsed = time.monotonic() - started
        boot_output = boot.stdout + boot.stderr
        for line in boot_output.splitlines():
            if source_area.name in line or "Star Wars Reality ready" in line:
                print(line)
        if source_area.name not in boot_output:
            print(f"The engine did not report loading {source_area.name}.")
            return 1
        if "Star Wars Reality ready" not in boot_output:
            print("The engine did not reach its ready state.")
            return 1
        if elapsed < 4.5:
            print("The engine exited before the five-second boot window.")
            return boot.returncode or 1

    print(f"SWR accepted {source_area} and remained live through the boot window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
