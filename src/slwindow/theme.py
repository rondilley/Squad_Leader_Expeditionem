"""The palette of the desktop window.

The look comes from a study of the owner's own boards, which are on the owner's machine in
`background/` and which git does not record. What the study gave is the visual language and
not the art: a light yellow-green ground, terrain that is a shape on that ground and not a
coloured hexagon, buildings that are the plan of a structure, roads that are a ribbon with
a curve, and a hill that is a contour in brown. `docs/ASSET_PROVENANCE.md` records that.

Each colour here is the project's own. Nothing is sampled from a scan, and no shape here
copies a printed shape (SR-07, DR-01).

The style is cel shading: each feature has flat tones and a hard edge, and no gradient. A
tone is one of four, and a feature uses the ones it needs:

- `_LIGHT`: the face the light falls on, which is the top of the screen
- the base: the face of the feature
- `_SHADE`: the face that turns away, and the shadow the feature throws
- `_LINE`: the edge, which is darker than any of the three

The browser client draws the same board with the same base tones and no shading, so a
picture of one window and a picture of the other show one board. `client/src/board/
render.ts` holds its copy of the base tones.
"""

from __future__ import annotations

PAPER = (198, 205, 176)
INK = (36, 34, 26)
GRID = (96, 104, 74)
LABEL = (118, 128, 92)
SELECT = (172, 62, 46)
PANEL = (28, 26, 22)
PANEL_TEXT = (222, 216, 200)
PANEL_DIM = (150, 144, 130)
PANEL_RULE = (70, 65, 56)
HIGHLIGHT = (232, 190, 74)

# ---------------------------------------------------------------------- the ground

# Open ground is a light yellow-green. It is the colour most of the board carries, so it is
# muted: a counter has to be the thing the eye finds first.
GROUND = (158, 176, 104)
# The shadow a building throws. A shadow falls on the ground, so it is a darker ground and
# not a darker building.
GROUND_SHADE = (124, 142, 80)

# Rule 44.2: a wheatfield fills its hex and follows the hexsides, which is the one terrain
# that is a hexagon and not a shape on the ground.
GRAIN = (222, 198, 116)
GRAIN_LINE = (188, 162, 88)
GRAIN_STALK = (176, 148, 76)

# Rule 44.3: a shellhole is a group of pits in the ground.
SHELLHOLE = (150, 168, 104)
SHELLHOLE_PIT = (146, 116, 72)
SHELLHOLE_LIGHT = (186, 158, 106)

TERRAIN = {
    "open": GROUND,
    "wheat": GRAIN,
    "shellhole": SHELLHOLE,
    "woods": (92, 128, 68),
    "wooden_building": (128, 66, 48),
    "stone_building": (176, 130, 92),
}

# ------------------------------------------------------------------------ the woods

# Rule 7.2: woods are a mass of crowns and not a coloured hexagon. Four tones: the light on
# the crown, the crown, the shade below it, and the line around the mass.
WOODS = TERRAIN["woods"]
WOODS_LIGHT = (126, 162, 88)
WOODS_SHADE = (58, 92, 50)
WOODS_LINE = (38, 62, 36)

# --------------------------------------------------------------------- the buildings

# Rules 7.4 and 7.5: a building is the plan of a structure. It is small and it sits inside
# its hex, so the ground shows around it. The roof takes the light, the body is the wall in
# the shade, and the line is the outline. The stone building is a light tan-brown and the
# wooden building is a darker red-brown, so both read as brown and not as grey.
BUILDING = {
    "stone_building": {
        "roof": (198, 154, 112),
        "body": TERRAIN["stone_building"],
        "shade": (146, 104, 70),
        "line": (96, 62, 40),
    },
    "wooden_building": {
        "roof": (152, 84, 62),
        "body": TERRAIN["wooden_building"],
        "shade": (98, 48, 34),
        "line": (58, 28, 18),
    },
}

# ------------------------------------------------------------------------- the hills

# Rule 43.1: three levels of hills. Each one is a flat contour in brown, and it replaces the
# ground. A woods hex or a building hex on a hill keeps its own shape on top of the brown.
HILL = ((198, 142, 84), (172, 112, 76), (140, 90, 68))
CREST = (110, 68, 44)

# -------------------------------------------------------------------------- the road

ROAD = (214, 192, 130)
ROAD_EDGE = (176, 152, 92)

# Rule 3.5 and rule 7.1: the centre dot. The board rule threads a line of sight from
# one centre dot to the next, so the dot is not decoration and it goes on top of the
# terrain. FR-30 asks for it and item 1 of the board rubric scores it.
CENTRE_DOT = (244, 239, 224)
SEWER = (86, 96, 104)

# ------------------------------------------------------- the wall, the hedge, the cliff

# Rule 11.5: each of the three has height, so each is three flat bands. The light comes from
# the top of the screen, so the two hexes of a hexside draw the same three bands.
HEXSIDE = {
    "wall": (146, 140, 122),
    "hedge": (74, 110, 58),
    "cliff": (58, 50, 42),
}
HEXSIDE_TOP = {
    "wall": (192, 186, 166),
    "hedge": (112, 150, 78),
    "cliff": (104, 92, 76),
}
HEXSIDE_SHADOW = {
    "wall": (88, 84, 72),
    "hedge": (44, 70, 36),
    "cliff": (20, 16, 12),
}

# ---------------------------------------------------------------------- the overlay
# The tactical overlay of `slwindow.overlay`. A shade is a translucent fill on the ground,
# in the manner of a pencil wash on a field map, so it stays quiet under the counters.
# Each tone is RGBA, and the key is the tone name of the model.
SHADE = {
    "focus": (172, 62, 46, 36),
    "move": (64, 92, 132, 72),
    "target": (150, 58, 40, 72),
    "track": (128, 104, 56, 64),
    "los": (48, 44, 30, 44),
    "los_blocked": (48, 44, 30, 120),
    "return": (150, 58, 40, 48),
    "melee": (120, 40, 40, 80),
}
# A tracer is a thin dashed line in the tone of its phase: the prep fire, the defensive
# fire, and the advancing fire of rule 4.
TRACER = {
    "prep": (118, 32, 24),
    "defensive": (38, 54, 92),
    "advancing": (84, 96, 38),
    "other": (60, 50, 40),
}
# A burst is a few short spokes on the target hex in the tone of the result, over a pale
# stroke that keeps it readable on a counter of any stock.
BURST = {
    "none": (84, 84, 76),
    "check": (198, 140, 38),
    "broken": (168, 48, 30),
    "kill": (30, 26, 20),
}
BURST_HALO = (240, 236, 222)
# A ghost is the outline of a counter on the track hex where the defensive fire catches
# a moved unit (rule 16.1). The counter itself stays at its end hex.
GHOST_LINE = (36, 34, 26)
GHOST_LINE_ALPHA = 150
GHOST_FILL_ALPHA = 64

# --------------------------------------------------------------------- the counters

# The national colours of `client/src/counters/draw.ts`. Each is more saturated than the
# ground, and each counter has a dark edge, so a counter reads first on a green board.
NATIONAL = {
    "german": (108, 122, 140),
    "russian": (186, 152, 82),
    "american": (172, 190, 76),
}
BROKEN = (162, 62, 46)
# The study of the 1977 pieces (RV-10): a support weapon counter is printed on the stock of
# its army, the berserk squads are on a red stock, and the markers are on a white stock.
BERSERK = (206, 48, 44)
MARKER = (236, 232, 220)      # the white marker stock: prep fire, malfunction, the wreck back
MARKER_RED = (214, 58, 40)    # the red of a starburst on a marker
CONCEALED = (226, 220, 202)
SMOKE = (226, 222, 212)
CHARGE = (162, 62, 46)

# Rules 28 to 41: a vehicle counter, its covered arc, and its wreck.
VEHICLE_EDGE = (24, 22, 18)
TURRET_BAND = (238, 233, 218)
OPEN_TOP = (236, 232, 220)    # rule 28: an open top vehicle is printed as a light plan
ARC = (232, 190, 74)
ARC_ALPHA = 56
WRECK = (86, 80, 70)
IMMOBILE = (196, 104, 48)
CREW_EXPOSED = (232, 190, 74)

# The physical look of a counter. A counter is a die-cut cardboard chit, so it has rounded
# corners, a thin cut edge that shows the pale cardboard core, a bevel from its thickness
# (the light is at the top of the screen), and wear at the corners where the printed layer
# has chipped. A broken unit is a counter turned to its reverse: the same stock, with the
# word for its state, its broken morale, and its men down. Each wear mark comes from the
# unit id and not from a generator, so a counter draws the same in each session (SR-07,
# DR-01).
CHIT_RADIUS = 0.16           # the corner radius as a fraction of the counter size
CHIT_EDGE = (208, 200, 178)  # the pale cardboard core at the cut edge
CHIT_SHADOW = (26, 24, 18)   # the shadow the thickness throws, drawn with an alpha
CHIT_SHADOW_ALPHA = 96
CHIT_BEVEL_LIGHT = 46        # how much to lighten the face on the lit top-left edge
CHIT_BEVEL_DARK = 42         # how much to darken the face on the shaded bottom-right edge
CHIT_WEAR = (216, 208, 188)  # a corner nick that shows the cardboard core
BACK_SHADE = 22              # how much darker a reverse is when it is too small for its print

# ---------------------------------------------------------------------- the card
#
# A scenario card is a paper document and not the green board, so it has its own small
# palette: a cream paper, a dark ink, a red accent for the scenario number and the counts,
# and two grey tones for a rule line and a diagram fill. The 1977 card is cream paper with
# black text and a red spot colour. These values are the project's own (SR-07, DR-01).
CARD_PAPER = (238, 231, 210)   # the cream stock of the card
CARD_PAPER_EDGE = (214, 205, 180)  # the darker edge of the paper, for a diagram fill
CARD_INK = (34, 30, 24)        # the printed black text
CARD_RED = (168, 44, 36)       # the red spot colour: the scenario number and the counts
CARD_RULE = (120, 112, 96)     # a thin rule line between the blocks
CARD_SHADE = (198, 190, 168)   # a shaded half of the board configuration diagram
