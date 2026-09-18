"""The silhouettes of the counters: figures, weapon icons, and vehicle plans.

Each silhouette is a list of parts in a unit box. The box is one unit wide and one unit
tall, x to the right and y down. A part is a filled polygon, ``("poly", points)``, or a
disc, ``("disc", (cx, cy, r))``. A renderer scales the box to the rectangle it has and
fills each part with the ink of the counter, so one list gives the desktop window, the 3D
top face, and the card the same picture. `client/src/counters/silhouettes.ts` holds the
same lists for the browser, and `tests/browser/test_render_constants.py` compares the two.

The shapes are the project's own. They come from a study of what the eye sees on the
owner's photographs of the 1977 pieces, written as sentences in
`docs/research/2026-09-17_RV-10_counter_study.md`: a line squad is two riflemen at a walk,
an elite squad is two men at a run with a submachine gun held level, a crew is two smaller
men at a run, a leader is one man on his feet, and a broken unit shows men down. No point
here is a measurement of a printed shape, and no pixel of a photograph is in the tree
(SR-07, DR-01).

A figure faces left, the way the German and American men on the 1977 sheets walk. The
Russian men walk to the right, so the renderer mirrors the figure for that army.
"""

from __future__ import annotations

Point = tuple[float, float]
Part = tuple[str, object]
Silhouette = list[Part]


def _bar(x0: float, y0: float, x1: float, y1: float, width: float) -> Part:
    """A filled bar from one point to another, as a polygon of four corners."""
    dx, dy = x1 - x0, y1 - y0
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    return ("poly", [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)])


def _rect(x0: float, y0: float, x1: float, y1: float) -> Part:
    return ("poly", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


# ------------------------------------------------------------------------ the figures
#
# A man at a walk: the head under a helmet, a trunk with a small lean forward, one leg
# out in front and one behind, and a rifle held low across the body, its muzzle forward
# and down. The near arm reaches down to the rifle.
RIFLEMAN_WALK: Silhouette = [
    ("disc", (0.44, 0.11, 0.085)),
    ("poly", [(0.33, 0.13), (0.35, 0.05), (0.42, 0.01), (0.50, 0.02), (0.56, 0.08), (0.56, 0.13)]),
    ("poly", [(0.36, 0.19), (0.52, 0.19), (0.56, 0.50), (0.38, 0.50)]),
    ("poly", [(0.46, 0.48), (0.57, 0.48), (0.70, 0.92), (0.72, 1.00), (0.61, 1.00), (0.59, 0.93), (0.43, 0.62)]),
    ("poly", [(0.38, 0.48), (0.49, 0.50), (0.37, 0.74), (0.33, 1.00), (0.21, 1.00), (0.23, 0.94), (0.28, 0.72)]),
    ("poly", [(0.40, 0.21), (0.49, 0.24), (0.31, 0.49), (0.23, 0.46)]),
    _bar(0.62, 0.36, 0.06, 0.52, 0.045),
    _rect(0.60, 0.33, 0.68, 0.42),
]

# A man at a run with a submachine gun: a strong lean, the rear leg stretched out behind,
# the front knee high, both arms forward, and the gun held level at the chest with its
# magazine below.
RUNNER_SMG: Silhouette = [
    ("disc", (0.34, 0.12, 0.085)),
    ("poly", [(0.23, 0.14), (0.25, 0.06), (0.32, 0.02), (0.40, 0.03), (0.46, 0.09), (0.46, 0.14)]),
    ("poly", [(0.27, 0.20), (0.43, 0.20), (0.53, 0.48), (0.36, 0.50)]),
    ("poly", [(0.44, 0.46), (0.55, 0.46), (0.84, 0.86), (0.90, 0.92), (0.80, 0.98), (0.74, 0.90), (0.40, 0.60)]),
    ("poly", [(0.36, 0.48), (0.47, 0.50), (0.28, 0.66), (0.24, 1.00), (0.12, 1.00), (0.14, 0.92), (0.16, 0.64)]),
    ("poly", [(0.30, 0.22), (0.40, 0.24), (0.24, 0.40), (0.16, 0.37)]),
    ("poly", [(0.38, 0.26), (0.47, 0.28), (0.36, 0.42), (0.28, 0.40)]),
    _bar(0.50, 0.32, 0.02, 0.32, 0.05),
    _rect(0.17, 0.32, 0.22, 0.44),
]

# One man on his feet: an upright trunk, a short stride, and a submachine gun slung across
# the body with its muzzle down and forward. The leader stands where the squads walk.
LEADER_STAND: Silhouette = [
    ("disc", (0.46, 0.10, 0.085)),
    ("poly", [(0.35, 0.12), (0.37, 0.04), (0.44, 0.00), (0.52, 0.01), (0.58, 0.07), (0.58, 0.12)]),
    ("poly", [(0.39, 0.18), (0.54, 0.18), (0.56, 0.52), (0.38, 0.52)]),
    ("poly", [(0.47, 0.50), (0.57, 0.50), (0.64, 0.94), (0.65, 1.00), (0.54, 1.00), (0.53, 0.94), (0.44, 0.64)]),
    ("poly", [(0.38, 0.50), (0.48, 0.52), (0.40, 0.76), (0.36, 1.00), (0.25, 1.00), (0.27, 0.94), (0.32, 0.74)]),
    ("poly", [(0.40, 0.20), (0.48, 0.24), (0.38, 0.44), (0.30, 0.41)]),
    _bar(0.62, 0.28, 0.20, 0.58, 0.045),
    _rect(0.42, 0.40, 0.48, 0.50),
]

# A man down: on his front, head up and rifle forward, the legs out behind. The box is
# wide and low, so the renderer gives it a wide rectangle.
PRONE_RIFLEMAN: Silhouette = [
    ("disc", (0.30, 0.48, 0.12)),
    ("poly", [(0.36, 0.56), (0.62, 0.52), (0.98, 0.66), (0.98, 0.80), (0.60, 0.82), (0.36, 0.86), (0.24, 0.80)]),
    ("poly", [(0.62, 0.52), (0.80, 0.40), (0.88, 0.46), (0.74, 0.58)]),
    _bar(0.42, 0.60, 0.02, 0.44, 0.06),
    ("poly", [(0.26, 0.60), (0.36, 0.58), (0.30, 0.74), (0.20, 0.72)]),
]

# A man on one knee, bent low, the rifle across the thigh. He is the second man on the
# back of a squad counter: down, but not out.
KNEELING_MAN: Silhouette = [
    ("disc", (0.40, 0.24, 0.10)),
    ("poly", [(0.42, 0.34), (0.58, 0.30), (0.68, 0.60), (0.46, 0.62)]),
    ("poly", [(0.46, 0.60), (0.68, 0.60), (0.72, 0.98), (0.60, 0.98), (0.58, 0.72), (0.40, 0.74)]),
    ("poly", [(0.30, 0.72), (0.46, 0.66), (0.44, 0.98), (0.30, 0.98)]),
    ("poly", [(0.44, 0.36), (0.54, 0.38), (0.36, 0.56), (0.28, 0.52)]),
    _bar(0.66, 0.50, 0.08, 0.66, 0.05),
]

# ------------------------------------------------------------------------- the icons
#
# The light machine gun from above: the barrel up, a bipod across it near the muzzle, the
# receiver and the butt below, and a magazine out to one side.
LMG_ICON: Silhouette = [
    _rect(0.46, 0.02, 0.54, 0.60),
    _rect(0.22, 0.17, 0.78, 0.22),
    _rect(0.40, 0.50, 0.60, 0.74),
    _rect(0.44, 0.74, 0.56, 0.98),
    _rect(0.24, 0.54, 0.40, 0.60),
]

# The medium machine gun from the side, on a tripod: a level barrel with the receiver at
# its rear, and three legs down from the mount.
MMG_ICON: Silhouette = [
    _rect(0.04, 0.28, 0.72, 0.36),
    _rect(0.56, 0.22, 0.84, 0.44),
    _bar(0.66, 0.42, 0.30, 0.96, 0.05),
    _bar(0.66, 0.42, 0.66, 0.96, 0.05),
    _bar(0.66, 0.42, 0.94, 0.96, 0.05),
]

# The heavy machine gun from the front: the barrel and the receiver above a tall tripod
# with a brace across its legs.
HMG_ICON: Silhouette = [
    _rect(0.46, 0.00, 0.54, 0.30),
    _rect(0.40, 0.28, 0.60, 0.50),
    _bar(0.50, 0.48, 0.16, 0.98, 0.05),
    _bar(0.50, 0.48, 0.50, 0.98, 0.05),
    _bar(0.50, 0.48, 0.84, 0.98, 0.05),
    _rect(0.28, 0.76, 0.72, 0.80),
]

# The flamethrower: the fuel tank as a tall pack, a hose up to the wand, and the wand
# with its nozzle out in front.
FLAMETHROWER_ICON: Silhouette = [
    _rect(0.10, 0.50, 0.44, 0.96),
    _bar(0.44, 0.72, 0.70, 0.46, 0.05),
    _bar(0.70, 0.46, 0.80, 0.14, 0.06),
    _rect(0.72, 0.06, 0.90, 0.16),
]

# The demolition charge: a satchel with a flap and a strap looped above it.
DEMO_CHARGE_ICON: Silhouette = [
    _rect(0.18, 0.46, 0.82, 0.92),
    _rect(0.18, 0.46, 0.82, 0.60),
    _bar(0.30, 0.46, 0.40, 0.14, 0.05),
    _bar(0.40, 0.14, 0.60, 0.14, 0.05),
    _bar(0.60, 0.14, 0.70, 0.46, 0.05),
]

# The panzerfaust: a slim tube with the round head at its top.
PANZERFAUST_ICON: Silhouette = [
    _rect(0.45, 0.28, 0.55, 0.98),
    ("disc", (0.50, 0.19, 0.12)),
]

# The bazooka: a tube of one width with the grip and the sight at its middle.
BAZOOKA_ICON: Silhouette = [
    _rect(0.44, 0.02, 0.56, 0.98),
    _rect(0.38, 0.48, 0.62, 0.58),
    _rect(0.56, 0.30, 0.64, 0.40),
]

# ---------------------------------------------------------------- the vehicle plans
#
# A plan is the vehicle from above with its front at the top of the box. The renderer
# turns it to the facing of the unit (rule 29.4), so the barrel lies along the spine of the
# covered arc. `hull` is the mass of the vehicle, `tracks` the two running gears at its
# sides, `turret` the part that rule 28 marks with a white band, and `barrel` the gun.
# Each name is a key, so the renderer can give the turret its band and an open top its
# light face.

TANK_PLAN: dict[str, Silhouette] = {
    "tracks": [_rect(0.18, 0.08, 0.32, 0.92), _rect(0.68, 0.08, 0.82, 0.92)],
    "hull": [_rect(0.28, 0.10, 0.72, 0.90)],
    "turret": [("disc", (0.50, 0.52, 0.17))],
    "barrel": [_rect(0.47, 0.00, 0.53, 0.42)],
}

SP_GUN_PLAN: dict[str, Silhouette] = {
    "tracks": [_rect(0.18, 0.08, 0.32, 0.92), _rect(0.68, 0.08, 0.82, 0.92)],
    "hull": [_rect(0.28, 0.10, 0.72, 0.90)],
    "casemate": [_rect(0.33, 0.30, 0.67, 0.72)],
    "barrel": [_rect(0.47, 0.00, 0.53, 0.38)],
}

HALFTRACK_PLAN: dict[str, Silhouette] = {
    "tracks": [_rect(0.18, 0.46, 0.30, 0.92), _rect(0.70, 0.46, 0.82, 0.92)],
    "wheels": [_rect(0.19, 0.12, 0.28, 0.30), _rect(0.72, 0.12, 0.81, 0.30)],
    "hull": [("poly", [(0.30, 0.08), (0.70, 0.08), (0.74, 0.40), (0.74, 0.92), (0.26, 0.92), (0.26, 0.40)])],
    "cab": [_rect(0.30, 0.34, 0.70, 0.40)],
}

TRUCK_PLAN: dict[str, Silhouette] = {
    "wheels": [_rect(0.20, 0.14, 0.28, 0.30), _rect(0.72, 0.14, 0.80, 0.30), _rect(0.20, 0.66, 0.28, 0.86), _rect(0.72, 0.66, 0.80, 0.86)],
    "hull": [_rect(0.30, 0.08, 0.70, 0.30), _rect(0.26, 0.36, 0.74, 0.94)],
}

JEEP_PLAN: dict[str, Silhouette] = {
    "wheels": [_rect(0.24, 0.22, 0.32, 0.36), _rect(0.68, 0.22, 0.76, 0.36), _rect(0.24, 0.66, 0.32, 0.80), _rect(0.68, 0.66, 0.76, 0.80)],
    "hull": [("poly", [(0.34, 0.16), (0.66, 0.16), (0.68, 0.84), (0.32, 0.84)])],
    "cab": [_rect(0.34, 0.42, 0.66, 0.47)],
}

# The wreck: the hull with a bite out of one side, the turret off its ring, and a plume of
# smoke over it. It goes on the white back of the counter with the survival number.
WRECK_PLAN: dict[str, Silhouette] = {
    "tracks": [_rect(0.18, 0.12, 0.32, 0.92)],
    "hull": [("poly", [(0.28, 0.14), (0.72, 0.14), (0.72, 0.50), (0.60, 0.58), (0.72, 0.66), (0.72, 0.90), (0.28, 0.90)])],
    "turret": [("disc", (0.62, 0.40, 0.14))],
    "smoke": [("disc", (0.40, 0.30, 0.10)), ("disc", (0.30, 0.18, 0.12)), ("disc", (0.18, 0.08, 0.09))],
}

PLANS: dict[str, dict[str, Silhouette]] = {
    "tank": TANK_PLAN,
    "sp_gun": SP_GUN_PLAN,
    "halftrack": HALFTRACK_PLAN,
    "truck": TRUCK_PLAN,
    "jeep": JEEP_PLAN,
}

FIGURES: dict[str, Silhouette] = {
    "rifleman_walk": RIFLEMAN_WALK,
    "runner_smg": RUNNER_SMG,
    "leader_stand": LEADER_STAND,
    "prone_rifleman": PRONE_RIFLEMAN,
    "kneeling_man": KNEELING_MAN,
}

ICONS: dict[str, Silhouette] = {
    "mg_light": LMG_ICON,
    "mg_medium": MMG_ICON,
    "mg_heavy": HMG_ICON,
    "flamethrower": FLAMETHROWER_ICON,
    "demo": DEMO_CHARGE_ICON,
    "panzerfaust": PANZERFAUST_ICON,
    "bazooka": BAZOOKA_ICON,
}


def icon_for(weapon_type: str, weapon_class: str = "") -> str:
    """The icon key of a support weapon, from its type name and its class.

    The class comes from the counter data (`weapon_class`) when the view carries it, and the
    type name decides between the three machine guns. An unknown weapon takes the medium
    machine gun, the most common shape on the sheets.
    """
    name = weapon_type.upper()
    if weapon_class in ICONS:
        return weapon_class
    if name.startswith("LMG"):
        return "mg_light"
    if name.startswith("HMG"):
        return "mg_heavy"
    if name.startswith("MMG"):
        return "mg_medium"
    if name in ("FT", "FLAMETHROWER"):
        return "flamethrower"
    if name in ("DC", "DEMO"):
        return "demo"
    if name in ("PF", "PANZERFAUST"):
        return "panzerfaust"
    if name in ("BAZ", "BAZOOKA"):
        return "bazooka"
    return "mg_medium"


def figure_for(kind: str, elite: bool = False) -> str:
    """The figure of an infantry counter: two riflemen at a walk for a line squad, two men
    at a run for an elite squad or a crew, one man on his feet for a leader."""
    if kind == "leader":
        return "leader_stand"
    if kind == "crew" or elite:
        return "runner_smg"
    return "rifleman_walk"


def transform(points: list[Point], left: float, top: float, width: float, height: float, mirror: bool = False) -> list[Point]:
    """Scale unit-box points to a rectangle. `mirror` turns the figure to face right."""
    out: list[Point] = []
    for x, y in points:
        if mirror:
            x = 1.0 - x
        out.append((left + x * width, top + y * height))
    return out
