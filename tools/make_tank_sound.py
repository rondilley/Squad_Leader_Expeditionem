"""Make the vehicle sound of the 3D window from the owner's recording of a tank.

The owner gave the recording on 2026-10-11 as `background/Tank_Noise.m4a` (48 kHz mono,
11.2 seconds). Git does not record `background/`, so this tool converts it into the file
the package ships, `src/slwindow3d/assets/tank_drive.wav`: 16-bit mono at the rate of the
sound bank (`slwindow3d.sounds.RATE`). `docs/ASSET_PROVENANCE.md` records the source.

Panda3D decodes the m4a (its FFmpeg plugin). A three-tap low-pass filter comes before the
linear resample, so the drop from 48 kHz to 22,050 Hz does not fold high noise down into
the band. The tank is low in pitch, so the filter takes nothing that it needs.

Run it with the venv active:

    python tools/make_tank_sound.py
"""

from __future__ import annotations

import sys
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Datagram, Filename, MovieAudio  # noqa: E402

from slwindow3d.sounds import RATE  # noqa: E402

SOURCE = ROOT / "background" / "Tank_Noise.m4a"
TARGET = ROOT / "src" / "slwindow3d" / "assets" / "tank_drive.wav"


def decode(path: Path) -> tuple[list[float], int]:
    """The samples of a mono recording, as floats from -1 to 1, and its rate."""
    cursor = MovieAudio.get(Filename.fromOsSpecific(str(path))).open()
    if cursor is None:
        raise RuntimeError(f"Panda3D cannot open {path}")
    if cursor.audioChannels() != 1:
        raise RuntimeError(f"{path} has {cursor.audioChannels()} channels; this tool reads mono")
    rate = cursor.audioRate()
    # The string form of readSamples decodes the PCM as text; a Datagram keeps the bytes.
    datagram = Datagram()
    cursor.readSamples(int(cursor.length() * rate), datagram)
    raw = array("h")
    raw.frombytes(bytes(datagram.getMessage()))
    return [s / 32768.0 for s in raw], rate


def resample(samples: list[float], rate: int, target: int) -> list[float]:
    """A three-tap low-pass, then a linear resample to `target`."""
    n = len(samples)
    smooth = [
        0.25 * samples[max(0, i - 1)] + 0.5 * samples[i] + 0.25 * samples[min(n - 1, i + 1)]
        for i in range(n)
    ]
    out = []
    step = rate / target
    t = 0.0
    while t < n - 1:
        i = int(t)
        f = t - i
        out.append(smooth[i] * (1.0 - f) + smooth[i + 1] * f)
        t += step
    return out


def main() -> int:
    if not SOURCE.exists():
        print(f"no recording at {SOURCE}", file=sys.stderr)
        return 1
    samples, rate = decode(SOURCE)
    data = resample(samples, rate, RATE)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    pcm = array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in data))
    with wave.open(str(TARGET), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    print(f"{TARGET.relative_to(ROOT)}: {len(data) / RATE:.2f} s at {RATE} Hz from {rate} Hz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
