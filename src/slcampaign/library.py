"""The scenario library: 12 project scenarios from 12 slots (owner directive, 2026-10-16).

The printed game had 12 scenarios. The project does not copy them. It makes 12 of its own,
and each one comes from a slot of `sldata/library/slots.json` and two seeds:

- The draw seed decides the scenario: the point total, the turns, the victory condition,
  the attack share, and the two forces. It reads the seeded generator of the core, the
  way the random construction of Game Set IV does (`slcampaign.generator`), so one seed
  always gives the same scenario (NFR-04).
- The board seed decides the board. The balance of a slot comes from a search of the board
  seeds first, with the forces fixed (the owner's decision of 2026-10-16). So the two seeds
  are separate: a new board seed does not change the forces.

A slot names its rule level. The draw takes only the counters and the features that the
rules of that level play: a slot of rule 21 has no smoke, no concealment, no engineers,
and no vehicles, and a slot of rule 41 or more has the armor. Halftracks, trucks, and
jeeps wait for rules 47, 51, and 52 (PR-20), so the vehicle list of the slot file holds
tanks and guns only.

A slot with more than one board stacks them from north to south (`slboards.compose`), so
the front gets wider with the force and the depth of the fight stays one board. Each side
has a group on each board. The defender holds one stone building on each board, and the
victory condition names those buildings.

`candidate` gives the scenario document, which is the JSON of a scenario file. The loader
of a scenario file reads it (`sldata.loaders.scenario_from_document`), so a candidate plays
through `file:` or as a document on the game farm before it becomes a library file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from slboards import edges
from slcampaign.generator import ATTACK_SHARE, ScenarioError, army_types, pick
from slcore.rng import RngState, choice_index, seed_state
from slcore.rules import r06_stacking
from slcore.scenario import band_text
from slcore.units import KIND_LEADER, KIND_SQUAD, KIND_SW, UnitType

AXIS = "axis"
ALLIED = "allied"
AXIS_ARMIES = ("german",)
ARMY_NAMES = {"german": "German", "russian": "Russian", "american": "American"}
PLURAL_NAMES = {"german": "Germans", "russian": "Russians", "american": "Americans"}

# The bands of columns on each board: the defender holds the east end, and the attacker
# starts at the west end, with a gap of eleven columns between them. The vehicles of each
# side have the two columns at its own edge, because two set up areas share no hex.
DEFENDER_BAND = (20, 30)
ATTACKER_BAND = (2, 8)
DEFENDER_VEHICLE_BAND = (31, 32)
ATTACKER_VEHICLE_BAND = (0, 1)
# A board stacked to the south starts `edges.ROWS` rows below the board before it, and the
# half hexes of the seam row are one hex of the two boards (`slboards.compose.offsets`).
ROWS_PER_BOARD = edges.ROWS
BUILDING_MIN_HEXES = 2
BUILDING_MAX_HEXES = 6
BOARD_RETRIES = 48
POINT_STEP = 10
MIN_SQUADS = 3
SQUADS_PER_LEADER = 4
# A force takes at most this many of one support weapon, so a draw does not give one side
# five flamethrowers.
WEAPON_CAP = {"FT": 1, "DC": 2, "HMG": 2, "MMG": 2, "BAZ": 3, "PF": 4}
NOT_COVER = ["stone_building", "wooden_building"]
NOT_VEHICLE = ["stone_building", "wooden_building", "woods"]


@dataclass(frozen=True)
class Slot:
    """One slot of the library, from the slot file."""

    id: str
    name: str
    title: str
    theme: str
    boards: tuple[str, ...]
    attacker: str
    defender: str
    defender_second: str
    rules: int
    points: tuple[int, int]
    turns: tuple[int, int]
    weapons: tuple[str, ...]
    engineers: bool
    vehicles_percent: tuple[int, int]
    # The counters that each side always gets, by key: what the card of the slot names.
    required: tuple[tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]]
    smoke: int
    concealment: tuple[int, int]
    hidden: bool
    two_sided: bool
    victory: tuple[str, ...]
    # PR-56: how many orchards each board of the slot has, beside its roads.
    orchards: int = 0
    # PR-57: a mill on the building that the defender holds on each board, or "".
    defender_landmark: str = ""

    @property
    def attacker_side(self) -> str:
        return AXIS if self.attacker in AXIS_ARMIES else ALLIED

    @property
    def defender_side(self) -> str:
        return AXIS if self.defender in AXIS_ARMIES else ALLIED

    @property
    def armor(self) -> bool:
        """Rules 28 to 41: the armor game."""
        return self.rules >= 41


def slot_from_dict(d: Mapping[str, Any]) -> Slot:
    vehicles = d.get("vehicles_percent", {})
    concealment = d.get("concealment", {})
    slot = Slot(
        id=str(d["id"]),
        name=str(d["name"]),
        title=str(d["title"]),
        theme=str(d["theme"]),
        boards=tuple(str(b) for b in d["boards"]),
        attacker=str(d["attacker"]),
        defender=str(d["defender"]),
        defender_second=str(d.get("defender_second", "")),
        rules=int(d["rules"]),
        points=(int(d["points"][0]), int(d["points"][1])),
        turns=(int(d["turns"][0]), int(d["turns"][1])),
        weapons=tuple(str(w) for w in d.get("weapons", [])),
        engineers=bool(d.get("engineers", False)),
        required=(
            tuple(sorted((str(k), int(n)) for k, n in d.get("required", {}).get("attacker", {}).items())),
            tuple(sorted((str(k), int(n)) for k, n in d.get("required", {}).get("defender", {}).items())),
        ),
        vehicles_percent=(int(vehicles.get("attacker", 0)), int(vehicles.get("defender", 0))),
        smoke=int(d.get("smoke", 0)),
        concealment=(int(concealment.get("attacker", 0)), int(concealment.get("defender", 0))),
        hidden=bool(d.get("hidden", False)),
        two_sided=bool(d.get("two_sided", False)),
        victory=tuple(str(v) for v in d["victory"]),
        orchards=int(d.get("orchards", 0)),
        defender_landmark=str(d.get("landmark", {}).get("defender", "")),
    )
    if slot.defender_landmark not in ("", "mill"):
        # The defender holds a stone building, and a windmill is a wooden building (PR-57).
        raise ScenarioError(f"slot {slot.id}: the defender holds a stone building, so its landmark can only be a mill")
    if slot.attacker_side == slot.defender_side:
        raise ScenarioError(f"slot {slot.id}: the attacker and the defender are on one side")
    if not slot.armor and any(slot.vehicles_percent):
        raise ScenarioError(f"slot {slot.id}: rule level {slot.rules} has no armor, so it has no vehicles")
    return slot


def load_slots() -> tuple[tuple[Slot, ...], dict[str, tuple[str, ...]]]:
    """The slots, and the vehicles that each army may field in the library."""
    from sldata.loaders import load_library_slots

    data = load_library_slots()
    vehicles = {str(k): tuple(str(v) for v in vs) for k, vs in data.get("vehicles", {}).items()}
    return tuple(slot_from_dict(s) for s in data["slots"]), vehicles


def slot_by_id(slot_id: str) -> tuple[Slot, dict[str, tuple[str, ...]]]:
    slots, vehicles = load_slots()
    for slot in slots:
        if slot.id.lower() == slot_id.lower():
            return slot, vehicles
    raise ScenarioError(f"no library slot {slot_id!r}; the slots are {', '.join(s.id for s in slots)}")


def pick_between(rng: RngState, low: int, high: int, step: int = 1) -> tuple[RngState, int]:
    """A value from low to high, both included, in steps of `step`."""
    count = (high - low) // step + 1
    rng, index = choice_index(rng, count)
    return rng, low + index * step


@dataclass(frozen=True)
class LibraryForce:
    """One side of a library scenario: a count for each counter key of one army."""

    nationality: str
    vehicles: tuple[tuple[str, int], ...]
    leaders: tuple[tuple[str, int], ...]
    squads: tuple[tuple[str, int], ...]
    weapons: tuple[tuple[str, int], ...]
    points: int

    def squad_count(self) -> int:
        return sum(n for _, n in self.squads)

    def leader_count(self) -> int:
        return sum(n for _, n in self.leaders)

    def vehicle_count(self) -> int:
        return sum(n for _, n in self.vehicles)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nationality": self.nationality,
            "points": self.points,
            "vehicles": dict(self.vehicles),
            "leaders": dict(self.leaders),
            "squads": dict(self.squads),
            "weapons": dict(self.weapons),
        }


def _add(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def build_force(
    rng: RngState,
    types: Mapping[str, UnitType],
    values: Mapping[str, int],
    nationality: str,
    budget: int,
    slot: Slot,
    vehicle_percent: int,
    vehicle_keys: Sequence[str],
    min_leaders: int,
    required: Sequence[tuple[str, int]] = (),
) -> tuple[RngState, LibraryForce]:
    """A force of one army that costs at most `budget` on the project's point scale.

    The vehicles take their share of the budget first, because a tank costs more than a
    squad and a share spent last finds no room. Then the leaders and the squads, with one
    leader for each four squads, because rule 14.1 rallies a squad only with a leader in
    the hex. Then the support weapons that the slot permits, one for each squad at most,
    because rule 5.7 gives a squad three portage points.

    The required counters of the slot come first after the leader, with no draw, so the
    card can name them and a slot with none of them draws as before (2026-10-17).
    """
    army = army_types(types, nationality)
    leaders = sorted(k for k, t in army.items() if t.kind == KIND_LEADER)
    # Squads only: a crew of rule 2 serves a gun, and a force with no gun has no crew.
    squads = sorted(k for k, t in army.items() if t.kind == KIND_SQUAD and (slot.engineers or not t.assault_engineer))
    weapons = sorted(k for k, t in army.items() if t.kind == KIND_SW and k.split(":", 1)[1] in slot.weapons)
    tanks = sorted(f"{nationality}:{v}" for v in vehicle_keys if f"{nationality}:{v}" in army)
    if not leaders or not squads:
        raise ScenarioError(f"the army {nationality!r} has no leader or no squad in the counter data")

    vehicles: dict[str, int] = {}
    spent = 0
    if vehicle_percent and tanks:
        share = budget * vehicle_percent // 100
        while True:
            affordable = [k for k in tanks if spent + values[k] <= share]
            if not affordable:
                break
            rng, key = pick(rng, affordable)
            _add(vehicles, key)
            spent += values[key]
        if not vehicles:
            # A share smaller than the cheapest tank still buys one, so an armor slot has armor.
            cheapest = min(tanks, key=lambda k: (values[k], k))
            _add(vehicles, cheapest)
            spent += values[cheapest]

    chosen_leaders: dict[str, int] = {}
    rng, leader = pick(rng, leaders)
    _add(chosen_leaders, leader)
    spent += values[leader]

    chosen_squads: dict[str, int] = {}
    chosen_weapons: dict[str, int] = {}
    taken = 0
    for short_key, count in required:
        key = f"{nationality}:{short_key}"
        unit_type = army.get(key)
        if unit_type is None:
            raise ScenarioError(f"slot {slot.id}: the required counter {short_key!r} is not in the {nationality} army")
        target = chosen_weapons if unit_type.kind == KIND_SW else chosen_squads
        for _ in range(count):
            _add(target, key)
            spent += values[key]
        if unit_type.kind == KIND_SQUAD:
            taken += count
    while True:
        affordable = [k for k in squads if spent + values[k] <= budget]
        if not affordable or (taken >= MIN_SQUADS and spent * 5 >= budget * 4):
            break
        rng, key = pick(rng, affordable)
        _add(chosen_squads, key)
        spent += values[key]
        taken += 1
    if taken < MIN_SQUADS:
        raise ScenarioError(f"a budget of {budget} points buys {taken} squads of {nationality}, and a force needs {MIN_SQUADS}")

    # One leader for each four squads, and one for each board the side holds at least.
    wanted = max(min_leaders, (taken + SQUADS_PER_LEADER - 1) // SQUADS_PER_LEADER)
    cheap = sorted(leaders, key=lambda k: (values[k], k))
    while sum(chosen_leaders.values()) < wanted:
        affordable = [k for k in leaders if spent + values[k] <= budget] or cheap[:1]
        rng, key = pick(rng, affordable)
        _add(chosen_leaders, key)
        spent += values[key]

    room = taken - sum(chosen_weapons.values())
    while weapons and room > 0:
        affordable = [
            k
            for k in weapons
            if spent + values[k] <= budget and chosen_weapons.get(k, 0) < WEAPON_CAP.get(k.split(":", 1)[1], room)
        ]
        if not affordable:
            break
        rng, key = pick(rng, affordable)
        _add(chosen_weapons, key)
        spent += values[key]
        room -= 1

    def short(counts: dict[str, int]) -> tuple[tuple[str, int], ...]:
        return tuple(sorted((k.split(":", 1)[1], n) for k, n in counts.items()))

    return rng, LibraryForce(
        nationality,
        short(vehicles),
        short(chosen_leaders),
        short(chosen_squads),
        short(chosen_weapons),
        spent,
    )


@dataclass(frozen=True)
class LibraryDraw:
    """What the draw seed decided."""

    slot: str
    seed: int
    defender_points: int
    attack_share: tuple[int, int]
    turns: int
    victory_kind: str
    attacker: LibraryForce
    defender: LibraryForce
    defender_second: LibraryForce | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "seed": self.seed,
            "defender_points": self.defender_points,
            "attack_share": list(self.attack_share),
            "turns": self.turns,
            "victory": self.victory_kind,
            "attacker": self.attacker.to_dict(),
            "defender": self.defender.to_dict(),
            "defender_second": None if self.defender_second is None else self.defender_second.to_dict(),
        }


def draw(
    slot: Slot,
    seed: int,
    types: Mapping[str, UnitType],
    values: Mapping[str, int],
    vehicles: Mapping[str, Sequence[str]],
) -> LibraryDraw:
    """The draws of one candidate of a slot. The board is not in it: the board seed is."""
    rng = seed_state(seed)
    rng, points = pick_between(rng, slot.points[0], slot.points[1], POINT_STEP)
    rng, turns = pick_between(rng, slot.turns[0], slot.turns[1])
    rng, victory_kind = pick(rng, slot.victory)
    rng, share = pick(rng, ATTACK_SHARE)
    boards = len(slot.boards)
    second = None
    if slot.defender_second:
        # A defence of two armies: the second holds the last board, with its share of the points.
        first_points = points * (boards - 1) // boards
        rng, defending = build_force(
            rng, types, values, slot.defender, first_points, slot, slot.vehicles_percent[1],
            vehicles.get(slot.defender, ()), boards - 1, slot.required[1],
        )
        # The second army holds one sector with a quarter or less of the points, so it has
        # infantry only: a tank takes most of a small budget and leaves too few squads.
        rng, second = build_force(
            rng, types, values, slot.defender_second, points - first_points, slot, 0,
            vehicles.get(slot.defender_second, ()), 1,
        )
    else:
        rng, defending = build_force(
            rng, types, values, slot.defender, points, slot, slot.vehicles_percent[1],
            vehicles.get(slot.defender, ()), boards, slot.required[1],
        )
    # A two-sided slot gets the attack share too: with forces of equal points, the L03 search
    # of 2026-10-17 gave the side of the condition 19.1 percent at best.
    attack_points = points * share[0] // share[1]
    rng, attacking = build_force(
        rng, types, values, slot.attacker, attack_points, slot, slot.vehicles_percent[0],
        vehicles.get(slot.attacker, ()), boards * (2 if slot.two_sided else 1), slot.required[0],
    )
    return LibraryDraw(slot.id, seed, points, share, turns, victory_kind, attacking, defending, second)


# ------------------------------------------------------------------------------ layout


def board_rows(index: int, boards: int) -> dict[str, int]:
    """The row band of board `index` of a stack of boards, or no band for one board.

    Board i holds the rows from i * 10 to i * 10 + 10. The seam row is the half hexes of
    the odd columns that two boards share (rule 3.5), and two set up areas share no hex,
    so the seam row belongs to the board above it.
    """
    if boards == 1:
        return {}
    first = index * ROWS_PER_BOARD
    return {"min_row": first if index == 0 else first + 1, "max_row": first + ROWS_PER_BOARD}


def _units(pairs: Sequence[tuple[str, int]]) -> list[dict[str, Any]]:
    return [{"type": key, "count": n} if n > 1 else {"type": key} for key, n in pairs if n > 0]


def _deal(pairs: Sequence[tuple[str, int]], parts: int) -> list[list[tuple[str, int]]]:
    """Counts dealt one at a time to `parts` piles, so each pile gets a fair share."""
    piles: list[dict[str, int]] = [{} for _ in range(parts)]
    turn = 0
    for key, n in pairs:
        for _ in range(n):
            _add(piles[turn % parts], key)
            turn += 1
    return [sorted(p.items()) for p in piles]


def _hold_and_rest(
    leaders: list[tuple[str, int]], squads: list[tuple[str, int]], weapons: list[tuple[str, int]]
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """The units of one board in two parts: what one stone building holds (rule 6.1), and
    the rest. The building takes a leader, up to three squads, and up to two weapons."""
    hold: dict[str, int] = {}
    rest: dict[str, int] = {}
    squad_keys = {key for key, _ in squads}
    leader_keys = {key for key, _ in leaders}
    leader_left = 1
    for key, n in leaders:
        take = min(n, leader_left)
        leader_left -= take
        if take:
            hold[key] = hold.get(key, 0) + take
        if n - take:
            rest[key] = rest.get(key, 0) + n - take
    room = r06_stacking.LIMIT_SQUADS
    for key, n in squads:
        take = min(n, room)
        room -= take
        if take:
            hold[key] = hold.get(key, 0) + take
        if n - take:
            rest[key] = rest.get(key, 0) + n - take
    room = 2
    for key, n in weapons:
        take = min(n, room)
        room -= take
        if take:
            hold[key] = hold.get(key, 0) + take
        if n - take:
            rest[key] = rest.get(key, 0) + n - take
    # A weapon needs a unit to set up with. When the rest has no squad and no leader, its
    # weapons stay in the building (the L03 search of 2026-10-17 put an MMG alone in a hex).
    if rest and not any(key in squad_keys or key in leader_keys for key in rest):
        for key, n in rest.items():
            hold[key] = hold.get(key, 0) + n
        rest = {}
    return sorted(hold.items()), sorted(rest.items())


def _area(zone: str, low: int, high: int, rows: Mapping[str, int], **extra: Any) -> dict[str, Any]:
    area: dict[str, Any] = {"zone": zone, "min_col": low, "max_col": high, **rows, **extra}
    return area


def _side_groups(
    prefix: str,
    force: LibraryForce,
    boards: int,
    band: tuple[int, int],
    vehicle_band: tuple[int, int],
    holds: bool,
    total_boards: int,
    first_board: int = 0,
    nationality: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """The groups of one side: on each board a holding group in a stone building (when the
    side holds buildings) and a line group in the band, and one group for the vehicles."""
    groups: list[dict[str, Any]] = []
    hold_ids: list[str] = []
    leader_piles = _deal(force.leaders, boards)
    squad_piles = _deal(force.squads, boards)
    weapon_piles = _deal(force.weapons, boards)
    for i in range(boards):
        board = first_board + i
        rows = board_rows(board, total_boards)
        if holds:
            hold, rest = _hold_and_rest(leader_piles[i], squad_piles[i], weapon_piles[i])
            gid = f"{prefix}_hold{board + 1}"
            group: dict[str, Any] = {
                "id": gid,
                "objective": True,
                "area": _area("stone_building", band[0], band[1], rows, rank=0, min_hexes=BUILDING_MIN_HEXES),
                "units": _units(hold),
            }
            if nationality:
                group["nationality"] = nationality
            groups.append(group)
            hold_ids.append(gid)
        else:
            rest = sorted(leader_piles[i] + squad_piles[i] + weapon_piles[i])
        if rest:
            group = {
                "id": f"{prefix}_line{board + 1}",
                "area": _area("columns", band[0], band[1], rows, not_terrain=NOT_COVER if holds else []),
                "units": _units(rest),
            }
            if not holds:
                group["objective"] = i == 0
                group["area"].pop("not_terrain")
            if nationality:
                group["nationality"] = nationality
            groups.append(group)
    if force.vehicles:
        # The vehicles set up on the boards of their own side, so a second army keeps its own.
        rows = {}
        if total_boards > 1:
            rows = {
                "min_row": board_rows(first_board, total_boards)["min_row"],
                "max_row": board_rows(first_board + boards - 1, total_boards)["max_row"],
            }
        group = {
            "id": f"{prefix}_armor",
            "area": _area("columns", vehicle_band[0], vehicle_band[1], rows, not_terrain=NOT_VEHICLE),
            "units": _units(force.vehicles),
        }
        if nationality:
            group["nationality"] = nationality
        groups.append(group)
    return groups, hold_ids


def _generator_record(board_type: str, seed: int, zones: list[dict[str, Any]], slot: Slot | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"seed": seed, "board_type": board_type, "cols": edges.COLS, "rows": edges.ROWS, "zones": zones}
    # The keys go in only when the slot asks for them, so each earlier record stays the same.
    if slot is not None and slot.orchards:
        record["style"] = {"orchards": slot.orchards}
    if slot is not None and slot.defender_landmark:
        # The building of rank 0 in the band of the defender: the building it holds.
        record["landmarks"] = [
            {"kind": slot.defender_landmark, "rank": 0, "min_col": DEFENDER_BAND[0], "max_col": DEFENDER_BAND[1]}
        ]
    return record


def _zones(two_sided: bool) -> list[dict[str, Any]]:
    zones = [
        {"count": 1, "min_hexes": BUILDING_MIN_HEXES, "max_hexes": BUILDING_MAX_HEXES, "min_col": DEFENDER_BAND[0], "max_col": DEFENDER_BAND[1]}
    ]
    if two_sided:
        zones.append(
            {"count": 1, "min_hexes": BUILDING_MIN_HEXES, "max_hexes": BUILDING_MAX_HEXES, "min_col": ATTACKER_BAND[0], "max_col": ATTACKER_BAND[1]}
        )
    return zones


def board_seed_for(board_seed: int, index: int) -> int:
    """The generator seed of board `index` of a candidate: one board seed gives them all."""
    return board_seed * 10 + index


# ---------------------------------------------------------------------------- the card


def counted(n: int, one: str, many: str) -> str:
    """`1 leader`, `3 leaders`: the card counts each item."""
    return f"{n} {one if n == 1 else many}"


def _force_text(force: LibraryForce) -> str:
    leaders = counted(force.leader_count(), "leader", "leaders")
    parts = [f"{counted(force.squad_count(), 'squad', 'squads')} under {leaders}"]
    if force.weapons:
        parts.append(counted(sum(n for _, n in force.weapons), "support weapon", "support weapons"))
    if force.vehicles:
        parts.append(counted(force.vehicle_count(), "armored vehicle", "armored vehicles"))
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def building_words(band: tuple[int, int], count: int, landmark: str = "") -> str:
    """The buildings of a set up band in words. Nothing on the board marks a building, so the
    card names it as the set up area does: by its rank and its band of columns (2026-10-17).
    A building with a landmark (PR-57) has its name first."""
    columns = band_text({"min_col": band[0], "max_col": band[1]})
    if count == 1:
        words = f"the largest stone building {columns}"
        return f"the {landmark} ({words})" if landmark else words
    words = f"the {count} largest stone buildings {columns}, one on each board"
    return f"the {count} {landmark}s ({words})" if landmark else words


def victory_text(slot: Slot, kind: str, hold_count: int, count: int) -> str:
    attacker = PLURAL_NAMES[slot.attacker]
    defender = (
        f"{PLURAL_NAMES[slot.defender]} and the {PLURAL_NAMES[slot.defender_second]}"
        if slot.defender_second
        else PLURAL_NAMES[slot.defender]
    )
    buildings = building_words(DEFENDER_BAND, hold_count, slot.defender_landmark)
    if kind == "hex_control":
        return (
            f"The {attacker} win if they end the game in control of {counted(count, 'hex', 'hexes')} "
            f"of {buildings}. Otherwise the {defender} win."
        )
    if kind == "building_count":
        taken = buildings if hold_count == 1 else f"{count} of {buildings}"
        return f"The {attacker} win if they end the game in control of {taken}. Otherwise the {defender} win."
    if kind == "sole_occupant":
        return (
            f"The {attacker} win if, at the end, they have unbroken units in {buildings} and the {defender} have none there. "
            f"Otherwise the {defender} win."
        )
    if kind == "building_swing":
        return (
            f"Each side holds the largest stone building at its own end. The {attacker} win if they take "
            f"{buildings} and keep their own. Otherwise the {PLURAL_NAMES[slot.defender]} win."
        )
    raise ScenarioError(f"slot {slot.id}: the victory condition {kind!r} has no layout in the library")


def situation_text(slot: Slot, d: LibraryDraw, victory: str) -> str:
    """The text of the card for the players, made from the slot and the draw."""
    attacker = PLURAL_NAMES[slot.attacker]
    lines = [slot.theme]
    lines.append(f"The {attacker} attack with {_force_text(d.attacker)}.")
    if d.defender_second is not None:
        lines.append(
            f"The {PLURAL_NAMES[slot.defender]} hold with {_force_text(d.defender)}, "
            f"and the {PLURAL_NAMES[slot.defender_second]} hold the last sector with {_force_text(d.defender_second)}."
        )
    else:
        lines.append(f"The {PLURAL_NAMES[slot.defender]} hold with {_force_text(d.defender)}.")
    lines.append(victory)
    if slot.hidden:
        # Rules 42.1, 42.2, 42.4, 42.5, and 42.7, in the words of the card. The rule names a
        # side, so the units of a second defending army hide too.
        armies = ARMY_NAMES[slot.defender]
        if slot.defender_second:
            armies += f" or {ARMY_NAMES[slot.defender_second]}"
        lines.append(
            f"Each {armies} unit that sets up in a woods hex or a building hex is hidden, "
            f"and the other units set up in full view. A vehicle hides only in woods or in a wooden building. "
            f"A hidden unit comes on the board when it moves, fires, or makes smoke, when an attack on its hex "
            f"has an effect, when an enemy enters its hex, or when an enemy is next to it at the end of a "
            f"Defensive Fire Phase or an Advance Phase."
        )
    if slot.two_sided:
        lines.append(
            f"The {attacker} also hold {building_words(ATTACKER_BAND, 1)}. It does not count for the victory. "
            f"A die roll decides which side moves first."
        )
    else:
        lines.append(f"The {attacker} move first.")
    lines.append(f"{d.turns} turns.")
    return " ".join(lines)


# ----------------------------------------------------------------------- the candidate


def rules_used(level: int) -> list[str]:
    return [str(n) for n in range(1, level + 1)]


def candidate(
    slot: Slot,
    seed: int,
    board_seed: int,
    types: Mapping[str, UnitType],
    values: Mapping[str, int],
    vehicles: Mapping[str, Sequence[str]],
) -> tuple[dict[str, Any], LibraryDraw]:
    """The scenario document of one candidate of a slot, and the draw that made it."""
    d = draw(slot, seed, types, values, vehicles)
    boards = len(slot.boards)
    attacker_side, defender_side = slot.attacker_side, slot.defender_side

    defender_boards = boards - 1 if d.defender_second is not None else boards
    defender_groups, holds = _side_groups(
        "d", d.defender, defender_boards, DEFENDER_BAND, DEFENDER_VEHICLE_BAND, holds=True, total_boards=boards
    )
    if d.defender_second is not None:
        second_groups, second_holds = _side_groups(
            "s", d.defender_second, 1, DEFENDER_BAND, DEFENDER_VEHICLE_BAND, holds=True,
            total_boards=boards, first_board=boards - 1, nationality=slot.defender_second,
        )
        defender_groups += second_groups
        holds += second_holds
    attacker_groups, own_holds = _side_groups(
        "a", d.attacker, boards, ATTACKER_BAND, ATTACKER_VEHICLE_BAND, holds=slot.two_sided, total_boards=boards
    )

    kind = d.victory_kind
    if kind == "building_swing":
        count = 1
        condition: dict[str, Any] = {
            "kind": kind, "side": attacker_side, "margin": 1, "enemy_groups": holds, "own_groups": own_holds,
        }
    else:
        # One hex or one building of each two boards, and at least one.
        count = max(1, (len(holds) + 1) // 2)
        condition = {"kind": kind, "side": attacker_side, "groups": holds}
        if kind in ("hex_control", "building_count"):
            condition["count"] = count
    text = victory_text(slot, kind, len(holds), count)
    condition["note"] = text

    zones = _zones(slot.two_sided)
    document: dict[str, Any] = {
        "id": f"lib{slot.id[1:]}_{slot.name}",
        "title": slot.title,
        "board": slot.boards[0],
    }
    if boards == 1:
        document["board_generator"] = _generator_record(slot.boards[0], board_seed_for(board_seed, 0), zones, slot)
    else:
        document["board_composition"] = {
            "side": "south",
            "boards": [_generator_record(t, board_seed_for(board_seed, i), zones, slot) for i, t in enumerate(slot.boards)],
        }
    document.update(
        {
            "board_retries": BOARD_RETRIES,
            "turns": d.turns,
            "first_mover": attacker_side,
            "setup_order": [defender_side, attacker_side],
            "rules_used": rules_used(slot.rules),
            "switches": {"predesignation": "basic", "semi_simultaneous": "off"},
        }
    )
    if slot.two_sided:
        document["first_mover_roll"] = True
    if slot.smoke:
        document["smoke_counters"] = {attacker_side: slot.smoke}
    concealment = {k: v for k, v in ((attacker_side, slot.concealment[0]), (defender_side, slot.concealment[1])) if v}
    if concealment:
        document["concealment_counters"] = concealment
    if slot.hidden:
        document["hidden_placement"] = {"side": defender_side, "note": "Rule 42: the defender sets up hidden."}
    document["sides"] = [
        {"side": attacker_side, "nationality": slot.attacker, "groups": attacker_groups},
        {"side": defender_side, "nationality": slot.defender, "groups": defender_groups},
    ]
    document["victory"] = [condition]
    document["situation"] = situation_text(slot, d, text)
    document["notes"] = (
        f"A project scenario of the library, slot {slot.id} (owner directive, 2026-10-16), not a printed scenario. "
        f"`sl-cli library` made it from draw seed {seed} and board seed {board_seed}. The rule level is {slot.rules}. "
        f"The defending force is {d.defender.points + (d.defender_second.points if d.defender_second else 0)} points "
        f"and the attacking force is {d.attacker.points} points on the scale of slcampaign.points, "
        f"a share of {d.attack_share[0]} to {d.attack_share[1]}. No part of it is card text (SR-07)."
    )
    return document, d
