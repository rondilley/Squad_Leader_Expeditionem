"""The tactical overlay of the windows (slice 22): the model, and the 2D marks.

The model (`slwindow.overlay`) holds no game library, so the first tests read it with no
screen. The pixel tests draw the marks with the dummy video driver and read the surface,
so a shade, a tracer, a burst, and a ghost each have to change pixels. Two of them prove
that the check rejects a surface with no mark, so the pixel test is not a rubber stamp.
"""

from __future__ import annotations

import os
from collections import Counter
from types import SimpleNamespace

import pytest

from slcore import geometry
from slwindow import overlay as model
from slwindow.overlay import (
    FIRE_DEFENSIVE,
    FIRE_PREP,
    RESULT_BROKEN,
    RESULT_CHECK,
    RESULT_KILL,
    RESULT_NONE,
    TONE_FOCUS,
    TONE_LOS,
    TONE_LOS_BLOCKED,
    TONE_MOVE,
    TONE_RETURN,
    TONE_TARGET,
    TONE_TRACK,
    Tracker,
    position_of,
    result_of,
)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


def _board():
    """A flat row of five hexes, A1 to E1, with the centres the core gives them."""
    hexes = [
        {
            "id": geometry.hex_id(col, 1),
            "col": col,
            "row": 1,
            "center": list(geometry.center(col, 1)),
            "terrain": "open",
            "elevation": 0,
        }
        for col in range(5)
    ]
    return {"name": "row", "cols": 5, "rows": 1, "hexes": hexes, "terrain": {}}


def _unit(unit_id: int, player: int, hex_id: str, **extra):
    base = {
        "id": unit_id,
        "player": player,
        "hex": hex_id,
        "carrier": None,
        "kind": "squad",
        "name": "4-4-7",
        "nationality": "russian" if player == 0 else "german",
        "track": [],
        "returned_from": None,
    }
    base.update(extra)
    return base


def _snapshot(units, legal=(), log=(), fire_group=None, melee=()):
    view = {"units": list(units), "fire_group": fire_group, "melee": list(melee)}
    return SimpleNamespace(view=view, legal=list(legal), log=list(log), active=0, phase="movement", board=_board())


def _legal(action: str, units: list[int], hex_id: str):
    return {"id": f"{action}-{hex_id}", "payload": {"action": action, "units": units, "hex": hex_id}}


# ---------------------------------------------------------------------- the model


def test_a_click_pins_the_focus_and_its_options_are_shaded():
    tracker = Tracker()
    snapshot = _snapshot(
        [_unit(1, 0, "A1"), _unit(2, 1, "E1")],
        legal=[_legal("move", [1], "B1"), _legal("group_add", [1], "E1"), _legal("move", [2], "D1")],
    )
    overlay = tracker.update(snapshot, 10.0, pinned=1)
    assert overlay.focus == 1
    assert overlay.focus_hex == "A1"
    assert overlay.shades["A1"] == TONE_FOCUS
    assert overlay.shades["B1"] == TONE_MOVE
    assert overlay.shades["E1"] == TONE_TARGET
    assert "D1" not in overlay.shades, "the options of the other unit are not shaded"


def test_with_no_pin_the_focus_is_the_unit_that_acted_last():
    tracker = Tracker()
    units = [_unit(1, 0, "A1"), _unit(2, 0, "C1")]
    # The first read seeds the mark and draws nothing.
    first = tracker.update(_snapshot(units, log=[{"seq": 0, "kind": "phase", "data": {}}]), 1.0)
    assert first.focus is None
    log = [
        {"seq": 0, "kind": "phase", "data": {}},
        {"seq": 1, "rule_id": "5.5", "kind": "move", "data": {"unit": 2, "from": "C1", "to": "D1"}},
    ]
    units[1]["hex"] = "D1"
    units[1]["track"] = ["D1"]
    overlay = tracker.update(_snapshot(units, log=log, legal=[_legal("move", [2], "E1")]), 2.0)
    assert overlay.focus == 2
    assert overlay.focus_hex == "D1"
    assert overlay.shades["C1"] == TONE_TRACK, "the hex the unit left is on its track"
    assert overlay.shades["E1"] == TONE_MOVE


def test_a_re_sent_tail_is_not_read_twice():
    tracker = Tracker()
    units = [_unit(1, 0, "A1"), _unit(2, 1, "D1")]
    tracker.update(_snapshot(units), 1.0)
    log = [
        {
            "seq": 5,
            "rule_id": "10.6",
            "kind": "fire",
            "data": {"target": "D1", "members": [{"unit": 1, "weapon": None}], "phase": "prep_fire"},
        },
        {"seq": 6, "rule_id": "10.5", "kind": "fire_result", "data": {"result": "M", "units": [2]}},
        {"seq": 7, "rule_id": "12.3", "kind": "broken", "data": {"unit": 2}},
    ]
    overlay = tracker.update(_snapshot(units, log=log), 2.0)
    assert len(overlay.tracers) == 1
    assert len(overlay.bursts) == 1
    again = tracker.update(_snapshot(units, log=log), 2.5)
    assert len(again.tracers) == 1, "the same tail gave a second tracer"
    assert len(again.bursts) == 1


def test_a_fire_gives_a_tracer_in_the_tone_of_its_phase_and_a_burst_of_its_result():
    tracker = Tracker()
    units = [_unit(1, 0, "A1"), _unit(2, 1, "D1")]
    tracker.update(_snapshot(units), 1.0)
    log = [
        {
            "seq": 0,
            "kind": "fire",
            "data": {"target": "D1", "members": [{"unit": 1, "weapon": None}], "phase": "defensive_fire"},
        },
        {"seq": 1, "kind": "fire_result", "data": {"result": "KIA", "units": [2]}},
        {"seq": 2, "kind": "eliminated", "data": {"unit": 2}},
    ]
    overlay = tracker.update(_snapshot(units, log=log), 2.0)
    tracer = overlay.tracers[0]
    assert (tracer.source, tracer.target, tracer.kind, tracer.result) == ("A1", "D1", FIRE_DEFENSIVE, RESULT_KILL)
    assert overlay.bursts[0].hex == "D1" and overlay.bursts[0].result == RESULT_KILL
    assert overlay.focus == 1, "the firer is the unit that acted last"
    assert ("A1", "D1") in overlay.los_wanted, "the window asks the host for the line of sight of the fire"


def test_the_marks_of_a_fire_linger_and_then_go():
    tracker = Tracker()
    units = [_unit(1, 0, "A1"), _unit(2, 1, "D1")]
    tracker.update(_snapshot(units), 0.0)
    log = [{"seq": 0, "kind": "fire", "data": {"target": "D1", "members": [{"unit": 1}], "phase": "prep_fire"}}]
    overlay = tracker.update(_snapshot(units, log=log), 1.0)
    assert overlay.tracers and overlay.bursts
    later = tracker.update(_snapshot(units, log=log), 1.0 + model.LINGER_BURST + 0.1)
    assert later.tracers == [] and later.bursts == []


def test_the_line_of_sight_answer_of_the_host_shades_the_hexes_it_threads():
    tracker = Tracker()
    units = [_unit(1, 0, "A1"), _unit(2, 1, "E1")]
    snapshot = _snapshot(units)
    asked = tracker.update(snapshot, 1.0, pinned=1, pointer_hex="E1")
    assert asked.los_wanted == [("A1", "E1")]
    assert TONE_LOS not in asked.shades.values()
    clear = {("A1", "E1"): {"clear": True, "traced": ["B1", "C1", "D1", "E1"], "blocking_hex": None}}
    answered = tracker.update(snapshot, 1.0, pinned=1, pointer_hex="E1", los=clear)
    assert answered.los_wanted == []
    assert answered.shades["B1"] == TONE_LOS and answered.shades["D1"] == TONE_LOS
    blocked = {("A1", "E1"): {"clear": False, "traced": ["B1", "C1", "D1", "E1"], "blocking_hex": "C1"}}
    stopped = tracker.update(snapshot, 1.0, pinned=1, pointer_hex="E1", los=blocked)
    assert stopped.shades["B1"] == TONE_LOS
    assert stopped.shades["C1"] == TONE_LOS_BLOCKED
    assert "D1" not in stopped.shades, "a line of sight ends at the hex that blocks it"


def test_a_returned_unit_stands_at_its_end_hex_and_a_ghost_at_the_track_hex():
    unit = _unit(1, 0, "B1", returned_from="D1", track=["B1", "C1", "D1"])
    assert position_of(unit) == "D1"
    tracker = Tracker()
    overlay = tracker.update(_snapshot([unit]), 1.0)
    assert len(overlay.ghosts) == 1
    ghost = overlay.ghosts[0]
    assert (ghost.unit, ghost.hex, ghost.end) == (1, "B1", "D1")
    assert overlay.shades["B1"] == TONE_RETURN


def test_the_stronger_tone_wins_a_hex():
    tracker = Tracker()
    units = [_unit(1, 0, "A1", track=["A1"])]
    overlay = tracker.update(_snapshot(units, legal=[_legal("move", [1], "A1")]), 1.0, pinned=1)
    assert overlay.shades["A1"] == TONE_FOCUS


def test_result_of_reads_the_events_and_the_table_results():
    assert result_of([]) == RESULT_NONE
    assert result_of(["fire_result"], ["-"]) == RESULT_NONE
    assert result_of(["fire_result", "morale_pass"], ["M"]) == RESULT_CHECK
    assert result_of(["fire_result", "broken"], ["1"]) == RESULT_BROKEN
    assert result_of(["fire_result", "eliminated"], ["KIA"]) == RESULT_KILL
    assert result_of(["broken", "eliminated"]) == RESULT_KILL


def test_a_bad_snapshot_gives_an_empty_model():
    tracker = Tracker()
    assert tracker.update(None, 1.0).shades == {}
    assert tracker.update(SimpleNamespace(view=None), 1.0).shades == {}
    bad = SimpleNamespace(view={"units": []}, legal=[{}], log=[{"kind": "fire"}, {"kind": "move"}])
    assert tracker.update(bad, 1.0).focus is None


def test_the_key_changes_with_the_drawing():
    tracker = Tracker()
    units = [_unit(1, 0, "A1")]
    one = tracker.update(_snapshot(units), 1.0, pinned=1)
    same = tracker.update(_snapshot(units), 1.5, pinned=1)
    other = tracker.update(_snapshot(units), 2.0, pinned=None)
    assert one.key() == same.key()
    assert one.key() != other.key()
    assert model.fire_kind("prep_fire") == FIRE_PREP


# --------------------------------------------------------------------- the pixels

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slwindow import layout, marks, render, theme  # noqa: E402
from slwindow.overlay import Burst, Ghost, Overlay, Tracer  # noqa: E402

SIZE = (600, 240)


@pytest.fixture(scope="module")
def picture():
    pygame.init()
    board = _board()
    camera = layout.fit(board, *SIZE)
    small = pygame.font.SysFont("dejavusansmono,consolas,couriernew", 12)
    return board, camera, small


def _colours(surface: pygame.Surface) -> Counter:
    raw = pygame.image.tobytes(surface, "RGB")
    return Counter(tuple(raw[i : i + 3]) for i in range(0, len(raw), 3))


def _pixel_at(surface: pygame.Surface, board, camera, hex_id: str) -> tuple[int, int, int]:
    centre = next(h["center"] for h in board["hexes"] if h["id"] == hex_id)
    x, y = camera.to_screen(*centre)
    return tuple(surface.get_at((int(x), int(y)))[:3])


def _blank(board, camera, small) -> pygame.Surface:
    surface = pygame.Surface(SIZE)
    render.draw_board(surface, board, camera, small)
    return surface


def test_a_shade_is_a_quiet_wash_on_the_ground(picture):
    board, camera, small = picture
    plain = _blank(board, camera, small)
    ground = _pixel_at(plain, board, camera, "B1")
    shaded = _blank(board, camera, small)
    marks.draw_shades(shaded, board, camera, Overlay(shades={"B1": TONE_MOVE}))
    tone = _pixel_at(shaded, board, camera, "B1")
    assert tone != ground, "the shade did not change the hex"
    untouched = _pixel_at(shaded, board, camera, "C1")
    assert untouched == _pixel_at(plain, board, camera, "C1"), "the shade spilled on the next hex"
    # A wash, and not a flat fill: the pixel is between the ground and the tone.
    r, g, b, alpha = theme.SHADE[TONE_MOVE]
    for got, base, wanted in zip(tone, ground, (r, g, b)):
        low, high = sorted((base, wanted))
        assert low - 2 <= got <= high + 2, (tone, ground, theme.SHADE[TONE_MOVE])
    assert alpha < 128, "a shade is translucent"


def test_a_tracer_and_a_burst_draw_in_their_tones(picture):
    board, camera, small = picture
    plain = _colours(_blank(board, camera, small))
    surface = _blank(board, camera, small)
    overlay = Overlay(
        tracers=[Tracer("A1", "E1", FIRE_PREP, RESULT_BROKEN, "prep_fire", 9.0)],
        bursts=[Burst("E1", RESULT_BROKEN, 9.0)],
    )
    marks.draw_marks(surface, board, None, camera, overlay, small)
    found = _colours(surface)
    assert found[theme.TRACER[FIRE_PREP]] > plain[theme.TRACER[FIRE_PREP]], "no tracer"
    assert found[theme.BURST[RESULT_BROKEN]] > plain[theme.BURST[RESULT_BROKEN]], "no burst"
    # Thin, in the manner of a pencil line: the tracer covers a small share of the board.
    assert found[theme.TRACER[FIRE_PREP]] < SIZE[0] * 4


def test_a_ghost_draws_the_outline_of_the_counter_on_the_track_hex(picture):
    board, camera, small = picture
    plain = _colours(_blank(board, camera, small))
    surface = _blank(board, camera, small)
    view = {"units": [_unit(1, 0, "B1", returned_from="D1")]}
    marks.draw_marks(surface, board, view, camera, Overlay(ghosts=[Ghost(1, "B1", "D1")]), small)
    found = _colours(surface)
    assert found[theme.GHOST_LINE] > plain[theme.GHOST_LINE], "no ghost outline"


def test_the_focus_hex_gets_a_line_round_it(picture):
    board, camera, small = picture
    plain = _colours(_blank(board, camera, small))
    surface = _blank(board, camera, small)
    marks.draw_marks(surface, board, None, camera, Overlay(focus=1, focus_hex="C1"), small)
    assert _colours(surface)[theme.SELECT] > plain[theme.SELECT]


def test_an_empty_model_draws_nothing(picture):
    board, camera, small = picture
    plain = _blank(board, camera, small)
    surface = _blank(board, camera, small)
    marks.draw_shades(surface, board, camera, Overlay())
    marks.draw_marks(surface, board, None, camera, Overlay(), small)
    assert pygame.image.tobytes(surface, "RGB") == pygame.image.tobytes(plain, "RGB")


def test_the_returned_counter_is_drawn_at_its_end_hex(picture):
    """Rule 16.1: the counter stays where the move ended; only the ghost is on the track."""
    from slwindow import counters

    from slcore.view import UnitView

    board, camera, small = picture
    font = pygame.font.SysFont("dejavusans,arial,helvetica", 15)
    squad = UnitView(
        id=1, player=0, type_key="russian:squad_447", kind="squad", hex=(1, 1), carrier=None,
        broken=False, berserk=False, prep_fired=False, moved=True, malfunction=False, dm=False,
        name="4-4-7", firepower=4, range=4, morale=7, leadership=0, own=True,
        track=((1, 1), (2, 1), (3, 1)), returned_from=(3, 1),
    ).to_dict()
    assert squad["hex"] == "B1" and squad["returned_from"] == "D1" and squad["track"] == ["B1", "C1", "D1"]
    view = {"units": [squad], "concealment": [], "smoke": [], "nationalities": {"0": "russian"}}
    plain = _blank(board, camera, small)
    surface = _blank(board, camera, small)
    counters.draw_counters(surface, board, view, camera, font, small)
    assert _pixel_at(surface, board, camera, "D1") != _pixel_at(plain, board, camera, "D1"), "no counter at the end hex"
    assert _pixel_at(surface, board, camera, "B1") == _pixel_at(plain, board, camera, "B1"), "a counter at the track hex"
