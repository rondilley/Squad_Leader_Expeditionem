"""The launcher of the packaged game: the consent, the choice of a game, and the uploads.

At the first start the launcher asks one time if the game may send the recorded games to the
collector (`slcollect.settings`). Then it shows the menu: the scenario, the side, the
opponent, and the view. Play starts the game window as a second process of the same program
(`game_argv`), so each game has a new window and a new Panda3D. The launcher waits, and after
the game it sends the saved games (`slcollect.client.send_pending`) on a thread of its own.

The model (`Choice`, `game_argv`, `entries`) has no pygame, so the tests read it directly.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from slcollect import settings as player_settings
from slcollect.keys import PLAYER_FILE

# The opponents of the menu, by key: three computer levels (`slcli.window_cmd.DIFFICULTY`),
# a person at the same computer (hot seat), and a person on the LAN.
OPPONENTS = (
    ("easy", "Computer, easy"),
    ("normal", "Computer, normal"),
    ("hard", "Computer, hard"),
    ("hotseat", "A person at this computer"),
    ("lan_host", "A person on the LAN: you are the host"),
    ("lan_join", "A person on the LAN: join a game"),
)
VIEWS = (("window3d", "3D window"), ("window", "2D window"))
LAN_PORT = 8731
# The scenarios of the menu: the project library (owner, 2026-10-16).
LIBRARY_PREFIX = "lib"

CONSENT_TEXT = (
    "Squad Leader Expeditionem saves each game that you play on this computer.",
    "May the game also send your games against the computer and against other people to the",
    "project's collection server? The computer players learn from them.",
    "A sent game has the scenario, the dice seed, and the commands of each side, with the name",
    "of your player key and the version of the game. The server also records the network address",
    "of your computer. A sent game has no other data about you.",
    "You can change this answer in the menu at any time.",
)


@dataclass(frozen=True)
class Entry:
    scenario: str
    title: str
    sides: tuple[tuple[str, str], tuple[str, str]]  # (side key, army name), player 0 first


def entries() -> list[Entry]:
    """The scenarios of the menu, with the two sides of each in the order of play."""
    folder = resources.files("sldata").joinpath("scenarios")
    found = []
    for item in sorted(folder.iterdir(), key=lambda p: p.name):
        if not (item.name.startswith(LIBRARY_PREFIX) and item.name.endswith(".json")):
            continue
        data = json.loads(item.read_text(encoding="utf-8"))
        sides = {s["side"]: str(s.get("nationality", s["side"])).replace("_", " ").title() for s in data["sides"]}
        first = data["first_mover"]
        other = next(k for k in sides if k != first)
        found.append(Entry(item.name[: -len(".json")], str(data.get("title", item.name)), ((first, sides[first]), (other, sides[other]))))
    return found


@dataclass
class Choice:
    scenario: int = 0
    side: int = 0
    opponent: str = "normal"
    view: str = "window3d"
    address: str = ""
    # The code that a joining player types, and the code of a game that this computer hosts.
    room_code: str = ""
    host_code: str = ""


def program() -> list[str]:
    """The command that starts this program again: the packaged file, or Python and the CLI."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "slcli.main"]


def game_argv(choice: Choice, found: list[Entry], seed: int, save_dir: Path, base: list[str] | None = None) -> list[str]:
    """The command line of one game in a window."""
    entry = found[choice.scenario]
    argv = [*(program() if base is None else base), choice.view, "--scenario", entry.scenario]
    if choice.opponent == "lan_join":
        return [*argv, "--connect", f"ws://{choice.address.strip()}:{LAN_PORT}/", "--room-code", choice.room_code.strip()]
    argv += ["--seed", str(seed), "--save-dir", str(save_dir)]
    if choice.opponent in ("easy", "normal", "hard"):
        computer_side = entry.sides[1 - choice.side][0]
        argv += ["--agent", choice.opponent, "--agent-side", computer_side]
    elif choice.opponent == "lan_host":
        argv += ["--lan", "--lan-port", str(LAN_PORT), "--room-code", choice.host_code]
    return argv


def upload(log: list[str]) -> None:
    """Send the saved games when the player agreed and has a key. Each result is a log line.

    The launcher calls it at its start and after each game, when no game of this launcher
    writes a save file, so a game that ended a second ago goes at once (`quiet_seconds` 0).
    """
    from slcollect import keys as keystore
    from slcollect.client import send_pending

    current = player_settings.load_settings()
    if current.consent is not True:
        return
    found = player_settings.key_file()
    if found is None:
        log.append(f"no player key: the games stay on this computer ({player_settings.games_dir()})")
        return
    try:
        key = keystore.read_player_file(found)
        report = send_pending(
            player_settings.games_dir(),
            player_settings.collector_url(current),
            key,
            player_settings.data_dir() / "sent.json",
            player_settings.package_version(),
            quiet_seconds=0.0,
        )
        log.append(f"upload: {report.text()}")
    except Exception as exc:  # noqa: BLE001 - an upload must never stop the launcher
        log.append(f"upload failed: {exc}")


# ------------------------------------------------------------------------ the window

BACK = (24, 28, 34)
PANEL = (40, 46, 56)
TEXT = (226, 230, 236)
DIM = (150, 158, 170)
ACCENT = (64, 132, 92)
ACCENT_OFF = (80, 88, 100)
FIELD = (60, 68, 80)
WARN = (210, 160, 70)


@dataclass
class Launcher:
    """The launcher window. `rects` names each clickable rectangle of the last drawing."""

    size: tuple[int, int] = (900, 660)
    choice: Choice = field(default_factory=Choice)
    log: list[str] = field(default_factory=list)
    rects: dict[str, Any] = field(default_factory=dict)
    focus: str = ""
    running: bool = True
    game: subprocess.Popen | None = None

    def __post_init__(self) -> None:
        import pygame

        pygame.init()
        self.pygame = pygame
        self.surface = pygame.display.set_mode(self.size)
        pygame.display.set_caption("Squad Leader Expeditionem")
        self.font = pygame.font.Font(None, 30)
        self.small = pygame.font.Font(None, 22)
        self.title_font = pygame.font.Font(None, 44)
        self.settings = player_settings.load_settings()
        self.found = entries()
        self.choice.host_code = self.choice.host_code or _room_code()
        threading.Thread(target=upload, args=(self.log,), daemon=True).start()

    # -------------------------------------------------------------- the actions

    def click(self, pos: tuple[int, int]) -> None:
        name = next((n for n, r in self.rects.items() if r.collidepoint(pos)), "")
        self.focus = name if name in ("address", "room_code") else ""
        if not name:
            return
        if name == "consent_yes":
            self.settings.set_consent(True)
        elif name == "consent_no":
            self.settings.set_consent(False)
        elif name in ("scenario_prev", "scenario_next"):
            step = -1 if name == "scenario_prev" else 1
            self.choice.scenario = (self.choice.scenario + step) % len(self.found)
        elif name.startswith("side_"):
            self.choice.side = int(name[-1])
        elif name.startswith("opponent_"):
            self.choice.opponent = name[len("opponent_") :]
        elif name.startswith("view_"):
            self.choice.view = name[len("view_") :]
        elif name == "send_toggle":
            self.settings.set_consent(not bool(self.settings.consent))
        elif name == "play":
            self.play()
        elif name == "quit":
            self.running = False

    def key(self, event: Any) -> None:
        if not self.focus:
            return
        pygame = self.pygame
        text = getattr(self.choice, self.focus)
        if event.key == pygame.K_BACKSPACE:
            text = text[:-1]
        elif event.key in (pygame.K_TAB, pygame.K_RETURN):
            self.focus = "room_code" if self.focus == "address" else ""
            return
        elif event.unicode and event.unicode.isprintable() and len(text) < 64:
            text += event.unicode
        setattr(self.choice, self.focus, text)

    def play(self) -> None:
        if self.game is not None and self.game.poll() is None:
            return
        if self.choice.opponent == "lan_join" and not (self.choice.address.strip() and self.choice.room_code.strip()):
            self.log.append("give the address of the host computer and its room code")
            return
        argv = game_argv(self.choice, self.found, random.randint(1, 2**31 - 1), player_settings.games_dir())
        self.log.append(f"the game starts: {self.found[self.choice.scenario].title}")
        self.game = subprocess.Popen(argv)

    def poll_game(self) -> None:
        if self.game is not None and self.game.poll() is not None:
            code = self.game.returncode
            self.game = None
            self.log.append("the game ended" if code == 0 else f"the game stopped with code {code}")
            threading.Thread(target=upload, args=(self.log,), daemon=True).start()

    # -------------------------------------------------------------- the drawing

    def _text(self, text: str, pos: tuple[int, int], font: Any = None, colour: tuple[int, int, int] = TEXT) -> Any:
        image = (font or self.font).render(text, True, colour)
        return self.surface.blit(image, pos)

    def _button(self, name: str, label: str, rect: tuple[int, int, int, int], on: bool = False) -> None:
        r = self.pygame.Rect(rect)
        self.pygame.draw.rect(self.surface, ACCENT if on else ACCENT_OFF, r, border_radius=6)
        image = self.small.render(label, True, TEXT)
        self.surface.blit(image, (r.centerx - image.get_width() // 2, r.centery - image.get_height() // 2))
        self.rects[name] = r

    def _field(self, name: str, label: str, value: str, rect: tuple[int, int, int, int]) -> None:
        r = self.pygame.Rect(rect)
        self.pygame.draw.rect(self.surface, FIELD, r, border_radius=4)
        if self.focus == name:
            self.pygame.draw.rect(self.surface, ACCENT, r, 2, border_radius=4)
        self._text(label, (r.left, r.top - 20), self.small, DIM)
        self._text(value[-48:], (r.left + 8, r.top + 7), self.small)
        self.rects[name] = r

    def draw(self) -> None:
        self.rects = {}
        self.surface.fill(BACK)
        self._text("Squad Leader Expeditionem", (32, 24), self.title_font)
        if self.settings.consent is None:
            self._draw_consent()
        else:
            self._draw_menu()
        y = self.size[1] - 18 - 20 * min(3, len(self.log))
        for line in self.log[-3:]:
            self._text(line, (32, y), self.small, DIM)
            y += 20
        self.pygame.display.flip()

    def _draw_consent(self) -> None:
        y = 110
        for line in CONSENT_TEXT:
            self._text(line, (32, y), self.small)
            y += 28
        self._button("consent_yes", "Yes, send my games", (32, y + 24, 260, 44))
        self._button("consent_no", "No, keep them here", (312, y + 24, 260, 44))

    def _draw_menu(self) -> None:
        entry = self.found[self.choice.scenario]
        self._text("Scenario", (32, 90), self.small, DIM)
        self._button("scenario_prev", "<", (32, 112, 40, 36))
        self._text(f"{entry.title}  ({self.choice.scenario + 1} of {len(self.found)})", (84, 118))
        self._button("scenario_next", ">", (520, 112, 40, 36))
        lan = self.choice.opponent in ("lan_host", "lan_join")
        self._text("Your side" + ("  (on the LAN the host moves first)" if lan else ""), (32, 166), self.small, DIM)
        for index, (_key, army) in enumerate(entry.sides):
            label = f"{army} ({'moves first' if index == 0 else 'moves second'})"
            self._button(f"side_{index}", label, (32 + 270 * index, 188, 260, 36), on=self.choice.side == index and not lan)
        self._text("Opponent", (32, 240), self.small, DIM)
        for index, (key, label) in enumerate(OPPONENTS):
            col, row = index % 3, index // 3
            self._button(f"opponent_{key}", label, (32 + 285 * col, 262 + 44 * row, 275, 36), on=self.choice.opponent == key)
        if self.choice.opponent == "lan_host":
            self._text(f"Give the other person the address of this computer, {lan_address()}, and the room code:", (32, 360), self.small)
            self._text(self.choice.host_code, (32, 384), self.small, WARN)
        elif self.choice.opponent == "lan_join":
            self._field("address", "Address of the host computer", self.choice.address, (32, 380, 300, 32))
            self._field("room_code", "Room code", self.choice.room_code, (352, 380, 500, 32))
        self._text("View", (32, 428), self.small, DIM)
        for index, (key, label) in enumerate(VIEWS):
            self._button(f"view_{key}", label, (32 + 170 * index, 450, 160, 36), on=self.choice.view == key)
        sending = self.settings.consent is True
        self._text("Training data", (32, 498), self.small, DIM)
        self._button("send_toggle", "Send games: yes" if sending else "Send games: no", (32, 520, 200, 36), on=sending)
        key = player_settings.key_file()
        status = f"player key: {key.name}" if key is not None else f"no player key: put {PLAYER_FILE} next to the game program"
        self._text(status, (250, 530), self.small, DIM if key is not None else WARN)
        busy = self.game is not None and self.game.poll() is None
        self._button("play", "The game is open" if busy else "Play", (620, 440, 240, 56), on=not busy)
        self._button("quit", "Quit", (760, 24, 100, 36))

    def run(self) -> int:
        pygame = self.pygame
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    self.key(event)
            self.poll_game()
            self.draw()
            clock.tick(20)
        pygame.quit()
        return 0


def lan_address() -> str:
    """The address of this computer on its LAN, as another computer reaches it.

    A UDP socket that connects sends no packet; it only selects the interface of the route.
    """
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _room_code() -> str:
    from slhost.rooms import new_room_code

    return new_room_code()
