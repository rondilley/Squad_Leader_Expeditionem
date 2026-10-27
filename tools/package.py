"""Build the package of the game for players: one folder with the program, and an archive.

    python tools/package.py                       the package of this system
    python tools/package.py --collector URL       another collection server

Run it on Windows for the Windows package and on Linux for the Linux package: PyInstaller
does not build for another system. It needs the `package` extra and the game extras:

    pip install -e ".[play,package]"

The output:

    dist/SquadLeaderExpeditionem/                              the folder to play from
    dist/SquadLeaderExpeditionem-<version>-<system>.zip        Windows
    dist/SquadLeaderExpeditionem-<version>-<system>.tar.gz     Linux

The program (`SquadLeaderExpeditionem.exe` or `SquadLeaderExpeditionem`) is the launcher
(`slcli.frozen_main`). The folder also has `collector.json` (the address of the collection
server), `READ_ME_FIRST.txt` (from `tools/package_readme.txt`), and the licence. The training
libraries (torch, numpy) are not in it: the menu offers only the scripted computer players.
No key file goes into a package: each player gets a key of their own (`sl-cli collect key add`).
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "SquadLeaderExpeditionem"
DEFAULT_COLLECTOR = "http://tars.uberadmin.com:5170"
# The packages of the tree. Each one goes in whole, because the registry and the windows
# import some modules by name at run time.
PACKAGES = ("slcli", "slcore", "sldata", "slagents", "slhost", "slwindow", "slwindow3d", "slcollect", "slboards", "slcampaign", "slcards", "slruns", "slfarm", "slshape")
DATA_PACKAGES = ("sldata", "slhost", "slwindow3d")
# The training libraries and the test tools: not in the package of a player.
EXCLUDED = ("torch", "numpy", "gymnasium", "pettingzoo", "tensorboard", "transformers", "peft", "datasets", "accelerate", "playwright", "pytest", "hypothesis", "IPython", "matplotlib", "PIL", "tkinter")


def version() -> str:
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("pyproject.toml has no version")


def system_tag() -> str:
    machine = platform.machine().lower().replace("amd64", "x64").replace("x86_64", "x64")
    return f"{'windows' if sys.platform == 'win32' else sys.platform}-{machine}"


def pyinstaller_args(dist: Path, work: Path) -> list[str]:
    """The PyInstaller command line of the package."""
    args = [
        str(ROOT / "src" / "slcli" / "frozen_main.py"),
        "--name", NAME,
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--distpath", str(dist),
        "--workpath", str(work),
        "--specpath", str(work),
        "--paths", str(ROOT / "src"),
        "--copy-metadata", "squad_leader_ai",
        "--collect-all", "panda3d",
        "--collect-data", "pygame",
    ]
    for package in PACKAGES:
        args += ["--collect-submodules", package]
    for package in DATA_PACKAGES:
        args += ["--collect-data", package]
    for module in EXCLUDED:
        args += ["--exclude-module", module]
    return args


def write_extras(folder: Path, collector: str) -> None:
    (folder / "collector.json").write_text(json.dumps({"url": collector}, indent=1) + "\n", encoding="utf-8")
    shutil.copyfile(ROOT / "tools" / "package_readme.txt", folder / "READ_ME_FIRST.txt")
    for name in ("LICENSE", "LICENSE.md", "COPYING"):
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, folder / name)


def check_no_keys(folder: Path) -> None:
    found = [p for p in folder.rglob("*") if p.name.endswith(".key.txt")]
    if found:
        raise RuntimeError(f"a key file is in the package, and the build stops: {found}")


def archive(folder: Path) -> Path:
    stem = folder.parent / f"{NAME}-{version()}-{system_tag()}"
    if sys.platform == "win32":
        target = Path(str(stem) + ".zip")
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as handle:
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    handle.write(path, Path(NAME) / path.relative_to(folder))
        return target
    target = Path(str(stem) + ".tar.gz")
    with tarfile.open(target, "w:gz") as handle:
        handle.add(folder, arcname=NAME)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the package of the game for players.")
    parser.add_argument("--collector", default=DEFAULT_COLLECTOR, help="the address of the collection server")
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    parser.add_argument("--no-archive", action="store_true", help="build the folder only")
    args = parser.parse_args(argv)
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print('the packager needs PyInstaller: pip install -e ".[play,package]"', file=sys.stderr)
        return 2
    dist = Path(args.dist)
    work = ROOT / "build" / "pyinstaller"
    pyinstaller.run(pyinstaller_args(dist, work))
    folder = dist / NAME
    write_extras(folder, args.collector)
    check_no_keys(folder)
    print(f"the package folder is {folder}")
    if not args.no_archive:
        print(f"the archive is {archive(folder)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
