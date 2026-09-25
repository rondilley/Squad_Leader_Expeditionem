"""The engineer tools of rules 22, 23, and 27 for agents v4 to v7.

Agent v2 has a policy for the flamethrower, the demolition charge, and the sewer, but v4
is a child of v1, so v4 to v7 had none of them. In scenarios 2 and 3A the frame offered v7
a charge more than 900 times in seven games and a sewer move more than 800 times, and v7
took none (2026-09-24). This module gives the four agents one policy for each tool. The
smoke of rule 24 and the concealment of rule 25 are not here: v7 has its own smoke, and
v1 already puts the concealment counters down at set up.

- Set up (rule 21.2): each flamethrower and each charge goes to a carrier that can use
  it, one to each carrier where the group has enough. The v1 order gave the first carrier
  each weapon of its group, so in scenario 2 one 8-3-8 squad held two flamethrowers, four
  charges, and two machine guns, and it did not leave its hex in the whole game. The
  machine guns keep the v1 order. A spread of them too lost the German of scenario 2 17
  points of its win rate (32 to 15 of 100, 2026-09-24): the v1 order makes a fixed fire
  base of the squad that holds them, and the other squads move with no load.
- Rule 22: a flamethrower fires at the enemy hex with the most units it can see, before a
  fire group forms. Its 20 firepower has no modifier, so the cover of a stone building
  does not help the target, and no fire group of a squad or two does as well.
- Rule 23: a charge goes on an enemy hex next to the carrier, and only when the agent
  would end its Movement Phase. The placer must hold its hex through the Defensive Fire
  Phase, so the agent places a charge from the hex where its move is complete. A ready
  charge always explodes: 30 firepower with the cover as the one modifier.
- Rule 27: a stack goes down a sewer when the exit is `sewer_gain` hexes or more nearer its
  target and holds no enemy it can see. The move is at most three hexes and arrives on a
  die of 4 or less, so a smaller gain does not pay for the risk of a lost stack. Only a
  side with a deadline uses a sewer, because the defender holds its buildings.
- Rule 27.22: when an enemy stack is lost, the agent brings it up at the entrance that is
  farthest from the places the agent wants.

The state is the view of the player (`slagents.base.decide`), so each count below is of
the units the player can see. The policy is deterministic for a state and a frame.
"""

from __future__ import annotations

from dataclasses import replace

from slcore import geometry
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import PHASE_ADVANCING_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_MOVEMENT, PHASE_PREP_FIRE, PHASE_SETUP, State
from slcore.geometry import HexRef
from slcore.rules import r10_resolution, r22_flamethrower, r23_demolition
from slcore.units import KIND_LEADER, KIND_SW

FIRE_PHASES = (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_ADVANCING_FIRE)

# The sewer gain in hexes. Rule 27.1 limits the move to three hexes.
SEWER_GAIN = 3


class Engineer:
    """The mixin of the engineer tools. The agent class sets `engineer_on` and `sewer_gain`."""

    engineer_on: bool = True
    sewer_gain: int = SEWER_GAIN

    def _engineer_first(self, state: State, frame: DecisionFrame, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """The decision of a tool that comes before the agent's own policy, or None."""
        if frame.phase == PHASE_SETUP and self._tools(state, by_action) and not self._carriers_to_come(state, by_action):
            return self._arm(state, by_action)
        if frame.sub_step == "demo_window":
            return self._explode_all(by_action)
        if frame.sub_step == "sewer_return" and by_action.get("sewer_return"):
            return self._bring_up_far(by_action)
        if frame.phase in FIRE_PHASES and state.fire_group is None and by_action.get("ft_fire"):
            return self._burn(state, by_action)
        if frame.phase == PHASE_MOVEMENT and by_action.get("sewer_move"):
            return self._go_below(state, by_action)
        return None

    def _engineer_frame(self, state: State, frame: DecisionFrame, by_action: dict[str, list[LegalCommand]]) -> DecisionFrame:
        """The frame the agent's own policy reads: at set up, no weapon before its carriers.

        The frame offers a weapon as soon as one carrier of its group is on the board, and
        the policy of v1 takes a weapon before a carrier. So the weapons wait while a
        carrier of their group can still go down, and then `_arm` spreads them.
        """
        if frame.phase != PHASE_SETUP or not self._tools(state, by_action) or not self._carriers_to_come(state, by_action):
            return frame
        held = {lc.id for lc in self._tools(state, by_action)}
        return replace(frame, commands=tuple(lc for lc in frame.commands if lc.id not in held))

    def _tools(self, state: State, by_action: dict[str, list[LegalCommand]]) -> list[LegalCommand]:
        """The `place_weapon` commands of a flamethrower or a charge."""
        types = self.engine.types
        out = []
        for lc in by_action.get("place_weapon", []):
            weapon = state.units[lc.command.weapon]
            if r22_flamethrower.is_flamethrower(types, weapon) or r23_demolition.is_charge(types, weapon):
                out.append(lc)
        return out

    def _carriers_to_come(self, state: State, by_action: dict[str, list[LegalCommand]]) -> bool:
        """True when the frame can place a carrier of the group of an offered tool."""
        groups = {state.units[lc.command.weapon].group for lc in self._tools(state, by_action)}
        for lc in by_action.get("place", []):
            unit = state.units[lc.command.units[0]]
            if unit.kind != KIND_SW and unit.group in groups:
                return True
        return False

    def _engineer_last(self, state: State, frame: DecisionFrame, by_action: dict[str, list[LegalCommand]], choice: str) -> str:
        """The agent's own choice, or a charge when that choice ends the Movement Phase."""
        if frame.phase != PHASE_MOVEMENT or not by_action.get("place_demo"):
            return choice
        ends = any(lc.id == choice for lc in by_action.get("end_phase", []))
        if not ends:
            return choice
        charge = self._charge_at(state, by_action)
        return choice if charge is None else charge

    # -------------------------------------------------------------- rule 21.2

    def _arm(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """The tool to the carrier that can use it and carries the least (rules 22.4 and 23.2).

        A leader takes a tool last. A flamethrower goes before a charge, because only a
        squad fires it and it is the heavier load.
        """
        types = self.engine.types

        def key(lc: LegalCommand) -> tuple:
            carrier = state.units[lc.command.units[0]]
            weapon_type = types[state.units[lc.command.weapon].type_key]
            flame = r22_flamethrower.is_flamethrower(types, state.units[lc.command.weapon])
            if flame:
                # Rule 22.4: a leader may carry it, but only a squad fires it.
                usable = carrier.kind != KIND_LEADER and r22_flamethrower.may_operate(types, carrier)
            else:
                usable = r23_demolition.may_place(types, carrier)
            carried = state.carried_by(carrier.id)
            tools = sum(1 for w in carried if r22_flamethrower.is_flamethrower(types, w) or r23_demolition.is_charge(types, w))
            load = sum(types[w.type_key].portage_squad_halves for w in carried) + weapon_type.portage_squad_halves
            return (not usable, carrier.kind == KIND_LEADER, tools, not flame, load, carrier.id, lc.id)

        return min(self._tools(state, by_action), key=key).id

    # ---------------------------------------------------------------- rule 22

    def _burn(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        best = self._best_enemy_hex(state, by_action["ft_fire"])
        return None if best is None else best.id

    # ---------------------------------------------------------------- rule 23

    def _charge_at(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        # The charge attacks each unit in its hex (rule 23.1), so a hex with an own unit is out.
        own = {u.hex for u in state.player_units(self.player) if u.hex is not None}
        candidates = [lc for lc in by_action["place_demo"] if lc.command.hex not in own]
        best = self._best_enemy_hex(state, candidates)
        return None if best is None else best.id

    def _explode_all(self, by_action: dict[str, list[LegalCommand]]) -> str:
        charges = by_action.get("explode_demo", [])
        if charges:
            return min(charges, key=lambda lc: lc.id).id
        return min(by_action["end_phase"], key=lambda lc: lc.id).id

    def _best_enemy_hex(self, state: State, commands: list[LegalCommand]) -> LegalCommand | None:
        """The command at the enemy hex with the most units this player sees, then the first."""
        targets = set(r10_resolution.enemy_occupied_hexes(state, self.player))
        best: LegalCommand | None = None
        best_key: tuple[int, str] | None = None
        for lc in commands:
            hex_ref = lc.command.hex
            if hex_ref is None or hex_ref not in targets:
                continue
            seen = sum(1 for u in state.infantry_in(hex_ref) if u.player != self.player)
            counters = sum(1 for c in state.concealment if c.hex == hex_ref and c.player != self.player)
            key = (-(seen + counters), lc.id)
            if best_key is None or key < best_key:
                best = lc
                best_key = key
        return best

    # ---------------------------------------------------------------- rule 27

    def _go_below(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        if not getattr(self, "has_deadline", True):
            return None
        enemies = set(r10_resolution.enemy_occupied_hexes(state, self.player))
        best: LegalCommand | None = None
        best_key: tuple[int, str] | None = None
        for lc in by_action["sewer_move"]:
            lead = lc.command.units[0]
            start = state.units[lead].hex
            target = lc.command.hex
            if start is None or target is None or target in enemies:
                continue
            gain = self._engineer_distance(lead, start) - self._engineer_distance(lead, target)
            if gain < self.sewer_gain:
                continue
            key = (-gain, lc.id)
            if best_key is None or key < best_key:
                best = lc
                best_key = key
        return None if best is None else best.id

    def _bring_up_far(self, by_action: dict[str, list[LegalCommand]]) -> str:
        return min(
            by_action["sewer_return"],
            key=lambda lc: (-(self._distance(lc.command.hex) if lc.command.hex is not None else 0), lc.id),
        ).id

    def _engineer_distance(self, unit_id: int, hex_ref: HexRef) -> int:
        """The distance of a unit to its own target (v6 and v7), or to the nearest objective."""
        unit_distance = getattr(self, "_unit_distance", None)
        if unit_distance is not None:
            return unit_distance(unit_id, hex_ref)
        if not self.objectives:
            return 0
        return min(geometry.distance(hex_ref, o) for o in self.objectives)
