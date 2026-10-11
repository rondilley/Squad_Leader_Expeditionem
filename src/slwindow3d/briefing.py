"""The scenario briefing: the scenario card over the board before the game starts.

The window shows the card of the scenario (`slcards`, the same card `sl-cli cards` prints):
the situation, the forces of each side with their set up areas, the turn record, and the
victory conditions. The game starts when the person presses Begin, Space, or Enter. Every
word on the card comes from the scenario data (FR-22), and the window adds no rule (AR-06).
"""

from __future__ import annotations

from typing import Any, Callable

from panda3d.core import TextNode, TransparencyAttrib

# The card is portrait. It fills this share of the window height.
CARD_HEIGHT_SHARE = 0.94
# The briefing draws over each other widget of the window: the status panel on the right is
# made again on each new frame, and without its own bin a new panel drew over the card and
# its Begin button. The sort order also puts the button first for a click.
BRIEFING_BIN = "gui-popup"
BRIEFING_SORT = 1000


class Briefing:
    """The card on a dark backdrop, a Begin button, and the keys that begin the game."""

    def __init__(self, app: Any, scenario_doc: dict[str, Any], on_begin: Callable[[], None]) -> None:
        from direct.gui.DirectGui import DirectButton, DirectFrame
        from direct.gui.OnscreenImage import OnscreenImage
        from direct.gui.OnscreenText import OnscreenText

        from slcards.card import CARD_HEIGHT, CARD_WIDTH, render_card
        from slwindow3d.counters import _ensure_pygame, _surface_to_texture

        self.app = app
        self._on_begin = on_begin
        self.open = True
        _ensure_pygame()
        texture = _surface_to_texture(render_card(scenario_doc), f"card-{scenario_doc.get('id', 'scenario')}")
        aspect = app.getAspectRatio() or 1.6
        self.backdrop = DirectFrame(
            parent=app.aspect2d,
            frameColor=(0.06, 0.07, 0.06, 0.93),
            frameSize=(-aspect, aspect, -1.0, 1.0),
            sortOrder=BRIEFING_SORT,
        )
        self.backdrop.setBin(BRIEFING_BIN, BRIEFING_SORT)
        half_h = CARD_HEIGHT_SHARE
        half_w = half_h * CARD_WIDTH / CARD_HEIGHT
        self.card = OnscreenImage(image=texture, parent=self.backdrop, pos=(-0.25, 0, 0), scale=(half_w, 1, half_h))
        self.card.setTransparency(TransparencyAttrib.MAlpha)
        right = min(aspect - 0.35, -0.25 + half_w + 0.45)
        self.button = DirectButton(
            parent=self.backdrop,
            text="Begin",
            text_fg=(1, 0.97, 0.86, 1),
            frameColor=(0.35, 0.12, 0.1, 0.95),
            pad=(0.6, 0.35),
            scale=0.07,
            pos=(right, 0, -0.55),
            command=self.begin,
            sortOrder=BRIEFING_SORT + 1,
        )
        self.hint = OnscreenText(
            text="Read the scenario.\nPress Begin, Space, or Enter\nto start the game.",
            parent=self.backdrop,
            pos=(right, -0.75),
            scale=0.04,
            fg=(0.92, 0.92, 0.88, 1),
            align=TextNode.ACenter,
        )
        app.accept("space", self.begin)
        app.accept("enter", self.begin)

    def begin(self) -> None:
        """Close the briefing and start the game. A second call does nothing."""
        if not self.open:
            return
        self.open = False
        self.app.ignore("space")
        self.app.ignore("enter")
        self.backdrop.destroy()
        self._on_begin()
