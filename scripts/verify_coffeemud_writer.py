import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import area_reader.dialects.coffeemud

CORPUS_PATHS = (
    Path("resources/examples/monsters.cmare"),
    Path("resources/examples/deities.cmare"),
    Path("resources/examples/junk.cmare"),
    Path("resources/skills/shipbuilding.cmare"),
    Path("resources/skills/caravanbuilding.cmare"),
    Path("resources/skills/clancastles.cmare"),
)


def run(
    command: list[str],
    *,
    timeout: int,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        cwd=cwd,
        text=True,
        encoding="latin-1",
        timeout=timeout,
    )


def report_failure(result: subprocess.CompletedProcess[str]) -> int:
    print(result.stdout)
    print(result.stderr)
    return result.returncode or 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build CoffeeMud in a temporary tree and load canonical .cmare catalogs.",
    )
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    missing = [relative for relative in CORPUS_PATHS if not (upstream / relative).is_file()]
    if missing:
        parser.error("missing CoffeeMud corpus files: {}".format(", ".join(map(str, missing))))

    with tempfile.TemporaryDirectory(prefix="area-reader-coffeemud-") as temporary:
        root = Path(temporary) / "CoffeeMud"
        shutil.copytree(
            upstream,
            root,
            ignore=shutil.ignore_patterns(".git", "*.class"),
        )
        generated = root / "writer-oracle-input"
        generated.mkdir()
        for relative in CORPUS_PATHS:
            area_file = area_reader.dialects.coffeemud.CoffeeMudAreaFile(upstream / relative)
            area_file.load_sections()
            area_file.write(generated / relative.name)

        harness = Path(__file__).with_name("CoffeeMudWriterOracle.java")
        shutil.copy2(harness, root / harness.name)

        source_list = root / "writer-oracle-sources.txt"
        source_list.write_text(
            "\n".join(path.relative_to(root).as_posix() for path in root.rglob("*.java")),
            encoding="ascii",
        )
        build = run(
            [
                "javac",
                "-nowarn",
                "-Xlint:none",
                "-g",
                "-classpath",
                r".;.\lib\js.jar;.\lib\jzlib.jar",
                "@writer-oracle-sources.txt",
            ],
            timeout=180,
            cwd=root,
        )
        if build.returncode != 0:
            return report_failure(build)

        baseline_arguments = [f"baseline:{relative}" for relative in CORPUS_PATHS]
        canonical_arguments = [
            "canonical:%s" % (Path("writer-oracle-input") / relative.name) for relative in CORPUS_PATHS
        ]
        oracle = run(
            [
                "java",
                "-classpath",
                r".;.\lib\js.jar;.\lib\jzlib.jar",
                "CoffeeMudWriterOracle",
                *baseline_arguments,
                *canonical_arguments,
            ],
            timeout=90,
            cwd=root,
        )
        if oracle.returncode != 0:
            print("\n".join(oracle.stdout.splitlines()[-200:]))
            print(oracle.stderr)
            return oracle.returncode

        active = None
        counts: dict[tuple[str, str], int] = {}
        error_counts: dict[tuple[str, str], int] = {}
        diagnostics: dict[tuple[str, str], list[str]] = {}
        for line in oracle.stdout.splitlines():
            if line.startswith("BEGIN\t"):
                _, label, path = line.split("\t", 2)
                active = (label, Path(path).name)
                error_counts[active] = 0
                diagnostics[active] = []
            elif line.startswith("RESULT\t"):
                _, label, path, count = line.split("\t", 3)
                counts[(label, Path(path).name)] = int(count)
            elif line.startswith("END\t"):
                active = None
            elif (active is not None) and (" error " in line):
                error_counts[active] += 1
                diagnostics[active].append(line)

        for relative in CORPUS_PATHS:
            name = relative.name
            baseline_count = counts.get(("baseline", name))
            canonical_count = counts.get(("canonical", name))
            baseline_errors = error_counts.get(("baseline", name))
            canonical_errors = error_counts.get(("canonical", name))
            print(
                f"{name}: baseline={baseline_count} records/{baseline_errors} errors; canonical={canonical_count} records/{canonical_errors} errors",
            )
            if baseline_count is None or canonical_count is None:
                print(f"CoffeeMud did not report both loader results for {name}.")
                return 1
            if canonical_count != baseline_count:
                print(f"CoffeeMud loaded a different record count for {name}.")
                return 1
            if canonical_errors is None or baseline_errors is None:
                print(f"CoffeeMud did not report both diagnostic counts for {name}.")
                return 1
            if canonical_errors > baseline_errors:
                print(f"Canonical {name} introduced CoffeeMud loader diagnostics.")
                for diagnostic in diagnostics[("canonical", name)][:20]:
                    print(diagnostic)
                return 1

    print("CoffeeMud canonical catalogs match the original loader baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
