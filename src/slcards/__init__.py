"""The scenario card generator (a new consumer of the scenario data).

`sl-cli cards --scenario <id>` renders one printable scenario card. The card evokes the
look and feel of the 1977 scenario card, but every word on it comes from the scenario JSON
(the project's own text, FR-22) and every shape is the project's own drawing. No Avalon Hill
text and no Avalon Hill art is in this module, in its output, or in its tests (SR-07, DR-01).
"""

from __future__ import annotations

from slcards.card import render_card, save_card

__all__ = ["render_card", "save_card"]
