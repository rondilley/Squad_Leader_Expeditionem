"""The set up tray and the boxes of the 3D window: a pygame picture over the board.

The drawing of the tray is `slwindow.traydraw`, and the drawing of the boxes is
`slwindow.boxes`; the 2D window draws the same pictures on its surface. This module shows
a picture as a texture over the 3D board (`Overlay2D`), and gives the names of the
drawing to the 3D window.
"""

from __future__ import annotations

from typing import Any

from slwindow.traydraw import (  # noqa: F401
    ACTION_ABOUT,
    ACTION_AUTO,
    ACTION_FINISH,
    ACTION_UNIT,
    BUTTON,
    BUTTON_HEIGHT,
    BUTTON_ON,
    BUTTON_TEXT,
    HEADER_HEIGHT,
    LABEL_HEIGHT,
    MAX_SHARE,
    MAX_TILE,
    MIN_TILE,
    REFUSED,
    SELECTED,
    TEXT,
    TEXT_DIM,
    TILE_GAP,
    TRAY_BACK,
    TRAY_LINE,
    about_height,
    draw_about,
    draw_carried,
    draw_tray,
    tray_height,
)


class Overlay2D:
    """One pygame picture shown over the board at a pixel rectangle of the window."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.image = None
        self.rect: tuple[int, int, int, int] | None = None

    def show(self, surface: Any, left: int, top: int, key: str) -> None:
        from direct.gui.OnscreenImage import OnscreenImage
        from panda3d.core import TransparencyAttrib

        from slwindow3d.counters import _surface_to_texture

        self.hide()
        win_w, win_h = self.app._window_size()
        width, height = surface.get_size()
        texture = _surface_to_texture(surface, key)
        aspect = self.app.getAspectRatio() or (win_w / win_h)
        half_w = aspect * width / win_w
        half_h = height / win_h
        self.image = OnscreenImage(image=texture, parent=self.app.aspect2d, pos=self._centre(left, top, width, height), scale=(half_w, 1, half_h))
        self.image.setTransparency(TransparencyAttrib.MAlpha)
        self.rect = (left, top, width, height)

    def _centre(self, left: int, top: int, width: int, height: int) -> tuple[float, float, float]:
        """The pixel rectangle in the -aspect..aspect and -1..1 space of aspect2d."""
        win_w, win_h = self.app._window_size()
        aspect = self.app.getAspectRatio() or (win_w / win_h)
        return (-aspect + 2 * aspect * (left + width / 2) / win_w, 0, 1 - 2 * (top + height / 2) / win_h)

    def move(self, left: int, top: int) -> None:
        """Move the picture to a new pixel position, with no new texture."""
        if self.image is None or self.rect is None:
            return
        width, height = self.rect[2], self.rect[3]
        self.image.setPos(*self._centre(left, top, width, height))
        self.rect = (left, top, width, height)

    def hide(self) -> None:
        if self.image is not None:
            self.image.destroy()
        self.image = None
        self.rect = None

    def point(self, pixel: tuple[int, int]) -> tuple[int, int] | None:
        """The pixel of the picture under a pixel of the window, or None off it."""
        if self.rect is None:
            return None
        left, top, width, height = self.rect
        x, y = pixel[0] - left, pixel[1] - top
        if 0 <= x < width and 0 <= y < height:
            return (x, y)
        return None
