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
server), `READ_ME_FIRST.txt` (from `tools/package_readme.txt`), `HOW_TO_PLAY.md` (from
`docs/PLAYER_GUIDE.md`), the licence, `THIRD_PARTY.txt`
(from `tools/package_third_party.txt`), and `licenses/`, the licence texts of the third-party
software. The build removes the files of `PRUNED`, which the game does not use. The training
libraries (torch, numpy) are not in it: the menu offers only the scripted computer players.
No key file goes into a package: each player gets a key of their own (`sl-cli collect key add`).
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import sysconfig
import tarfile
import zipfile
from importlib import metadata
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
# Files that `--collect-all` and `--collect-data` bring and the game does not use: the
# examples, tests, and documents of pygame-ce (they hold third-party pictures and fonts), and
# the FMOD audio plugin (not free software) and the Direct3D 9 plugin of Panda3D. The 3D
# window uses OpenAL and OpenGL. Each pattern is a glob under `_internal`.
PRUNED = ("pygame/examples", "pygame/tests", "pygame/docs", "panda3d/*fmod*", "panda3d/*pandadx9*", "panda3d/d3dx9*")
# The distributions whose licence files go in `licenses/`, and `tools/package_third_party.txt`
# names each one.
LICENSED = ("pyinstaller", "panda3d", "websockets", "werkzeug", "markupsafe")


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
    shutil.copyfile(ROOT / "docs" / "PLAYER_GUIDE.md", folder / "HOW_TO_PLAY.md")
    for name in ("LICENSE", "LICENSE.md", "COPYING"):
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, folder / name)


def prune(folder: Path) -> None:
    for pattern in PRUNED:
        for path in (folder / "_internal").glob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def python_licence() -> Path:
    """The licence text of the interpreter that the package holds."""
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    candidates = (
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",
        Path("/usr/share/doc") / f"python{version}" / "copyright",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError(f"no licence text of Python {version} at {[str(p) for p in candidates]}, and the build stops")


def write_licences(folder: Path) -> None:
    """The licence texts of the third-party software in the package (`package_third_party.txt`)."""
    target = folder / "licenses"
    target.mkdir(exist_ok=True)
    shutil.copyfile(python_licence(), target / "Python-LICENSE.txt")
    shutil.copyfile(ROOT / "tools" / "licenses" / "LGPL-2.1.txt", target / "LGPL-2.1.txt")
    for name in LICENSED:
        dist = metadata.distribution(name)
        files = [f for f in dist.files or () if f.parent.name == "licenses" or f.name.upper().startswith(("LICENSE", "COPYING"))]
        if not files:
            raise RuntimeError(f"{name} has no licence file, and the build stops")
        (target / name).mkdir(exist_ok=True)
        for file in files:
            shutil.copyfile(dist.locate_file(file), target / name / file.name)
    shutil.copyfile(ROOT / "tools" / "package_third_party.txt", folder / "THIRD_PARTY.txt")


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
    prune(folder)
    write_extras(folder, args.collector)
    write_licences(folder)
    check_no_keys(folder)
    print(f"the package folder is {folder}")
    if not args.no_archive:
        print(f"the archive is {archive(folder)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
