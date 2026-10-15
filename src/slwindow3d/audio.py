"""The sound board of the 3D window: it plays the sounds of `sounds.py` for the new events.

The sounds are made in memory when the window opens (the vehicle from the one recording,
`assets/tank_drive.wav`) and put on a ramdisk of the Panda3D virtual file system, so the
window loads them like files.
Each new event of the log (the same events the indicators read) gives its cues
(`sounds.sound_cues`); the cues of one frame are merged (`sounds.merge_cues`), and each one
plays with a volume and a left to right balance from where its hex is on the screen. A hex
off the screen plays quieter. `m` mutes and unmutes.
"""

from __future__ import annotations

import itertools
from typing import Any

from panda3d.core import Filename, Point2, Point3, VirtualFileMountRamdisk, VirtualFileSystem

from slwindow3d import sounds

MOUNT = "/sl-sounds"
# Each variant of a sound is loaded this many times, so a sound can play again before the
# last one ends.
COPIES = 2
OFF_SCREEN_VOLUME = 0.35
MASTER_VOLUME = 0.8

_mounted = False


def _mount(files: dict[str, bytes]) -> None:
    """Put the WAV bytes on a ramdisk of the virtual file system, one time a process."""
    global _mounted
    vfs = VirtualFileSystem.getGlobalPtr()
    if not _mounted:
        vfs.mount(VirtualFileMountRamdisk(), MOUNT, 0)
        _mounted = True
    for path, data in files.items():
        vfs.writeFile(Filename(path), data, False)


class SoundBoard:
    def __init__(self, app: Any, muted: bool = False) -> None:
        self.app = app
        self.muted = muted
        self.played: list[tuple[str, str | None, float]] = []
        files: dict[str, bytes] = {}
        for name, variants in sounds.bank().items():
            for index, data in enumerate(variants):
                files[f"{MOUNT}/{name}_{index}.wav"] = data
        _mount(files)
        self.pools: dict[str, Any] = {}
        for name in sounds.NAMES:
            loaded = []
            for index in range(sounds.VARIANTS):
                for _ in range(COPIES):
                    loaded.append(app.loader.loadSfx(f"{MOUNT}/{name}_{index}.wav"))
            self.pools[name] = itertools.cycle(loaded)

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        return self.muted

    def on_events(self, events: list[dict], units: dict) -> None:
        """The sounds of the new events of one frame."""
        cues: list[tuple[str, str | None, float]] = []
        for event in events:
            cues.extend(sounds.sound_cues(event, units))
        for name, where, volume in sounds.merge_cues(cues):
            self.play(name, where, volume)

    def play(self, name: str, where: str | None, volume: float) -> None:
        self.played.append((name, where, volume))
        if self.muted or name not in self.pools:
            return
        sound = next(self.pools[name])
        balance, on_screen = self._place(where)
        sound.setVolume(MASTER_VOLUME * volume * (1.0 if on_screen else OFF_SCREEN_VOLUME))
        sound.setBalance(balance)
        sound.play()

    def _place(self, where: str | None) -> tuple[float, bool]:
        """The left to right balance of a hex on the screen (-1 to 1), and whether it is on
        the screen. A sound with no hex is in the middle."""
        indicators = getattr(self.app, "indicators", None)
        point = indicators._ground(where) if (indicators is not None and where) else None
        if point is None:
            return 0.0, True
        lens = self.app.cam.node().getLens()
        screen = Point2()
        if not lens.project(self.app.cam.getRelativePoint(self.app.render, Point3(*point)), screen):
            return 0.0, False
        return max(-1.0, min(1.0, screen.x)), abs(screen.x) <= 1.0 and abs(screen.y) <= 1.0
