// The command panel. The client shows the legal list the host sent and sends back one
// identifier. It never builds a command of its own (AR-06, DR-04).

import type { LegalCommand, UnitDocument, ViewDocument } from "../net/protocol";

export interface CommandGroup {
  action: string;
  commands: LegalCommand[];
}

export function groupByAction(commands: LegalCommand[]): CommandGroup[] {
  const groups = new Map<string, LegalCommand[]>();
  for (const command of commands) {
    const list = groups.get(command.payload.action) ?? [];
    list.push(command);
    groups.set(command.payload.action, list);
  }
  return [...groups.entries()]
    .map(([action, list]) => ({ action, commands: list }))
    .sort((a, b) => a.action.localeCompare(b.action));
}

export function hexesOfCommands(commands: LegalCommand[]): Set<string> {
  const out = new Set<string>();
  for (const command of commands) {
    if (command.payload.hex) {
      out.add(command.payload.hex);
    }
  }
  return out;
}

export function commandsForHex(commands: LegalCommand[], hexId: string, view: ViewDocument | null): LegalCommand[] {
  const unitsInHex = new Set<number>();
  if (view) {
    for (const unit of view.units) {
      if (unit.hex === hexId) {
        unitsInHex.add(unit.id);
      }
    }
  }
  return commands.filter((command) => {
    if (command.payload.hex === hexId) {
      return true;
    }
    const units = command.payload.units ?? [];
    return units.some((id) => unitsInHex.has(id));
  });
}

export function label(command: LegalCommand, units: Map<number, UnitDocument>): string {
  const payload = command.payload;
  const names = (payload.units ?? []).map((id) => describeUnit(units.get(id), id)).join(" and ");
  switch (payload.action) {
    case "end_phase":
      return "end the phase";
    case "end_setup":
      return "set up is complete";
    case "place":
      return `place ${names} in ${payload.hex}`;
    case "place_weapon":
      return `give weapon ${payload.weapon} to ${names}`;
    case "move":
      return `move ${names} to ${payload.hex}`;
    case "stack_move":
      return `move the stack ${names} to ${payload.hex}`;
    case "advance":
      return `advance ${names} to ${payload.hex}`;
    case "pickup":
      return `${names} picks up weapon ${payload.weapon}`;
    case "drop":
      return `${names} drops weapon ${payload.weapon}`;
    case "rally":
      return `rally ${names}`;
    case "repair":
      return `repair weapon ${payload.weapon}`;
    case "rout":
      return `rout ${names} to ${payload.hex}`;
    case "stay":
      return `${names} stays in cover`;
    case "track_return":
      return `return ${names} to ${payload.hex}`;
    case "group_add":
      return `${names} fires at ${payload.hex}`;
    case "group_add_weapon":
      return `${names} fires weapon ${payload.weapon} at ${payload.hex}`;
    case "group_leader":
      return `${names} directs the fire group`;
    case "group_fire":
      return "resolve the fire group";
    case "cc_attack":
      return `close combat: ${names} attack ${(payload.targets ?? []).join(", ")}`;
    default:
      return `${payload.action} ${names}`;
  }
}

function describeUnit(unit: UnitDocument | undefined, id: number): string {
  if (!unit) {
    return `unit ${id}`;
  }
  if (unit.kind === "leader") {
    return unit.name || `leader ${unit.morale}`;
  }
  return `${unit.type}`;
}
