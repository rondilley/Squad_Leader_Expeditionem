// The message shapes the host sends and the client sends (ARCHITECTURE section 8).
// The client sends intents only. It never calculates or sends a state hash (DR-04).

export interface HexDocument {
  id: string;
  col: number;
  row: number;
  center: [number, number];
  terrain: string;
  road?: boolean;
  elevation?: number;
  building?: { id: string; size: number; kind: string };
  hexsides?: Record<string, string>;
  polygons: { kind: string; points: [number, number][] }[];
}

export interface TerrainRow {
  tem: number;
  mf_halves: number;
  los: string;
  building: boolean;
}

export interface BoardDocument {
  name: string;
  cols: number;
  rows: number;
  hexes: HexDocument[];
  terrain: Record<string, TerrainRow>;
}

export interface ScenarioDocument {
  id: string;
  title: string;
  turns: number;
  sides: string[];
  players: string[];
  notes: string;
}

export interface UnitDocument {
  id: number;
  player: number;
  type: string;
  nationality: string;
  kind: string;
  hex: string | null;
  carrier: number | null;
  broken: boolean;
  berserk: boolean;
  prep_fired: boolean;
  moved: boolean;
  malfunction: boolean;
  dm: boolean;
  name: string;
  firepower: number;
  range: number;
  morale: number;
  leadership: number;
  own: boolean;
  // Rules 28 to 41. The host sends these for a vehicle counter and for nothing else.
  facing?: number;
  wreck?: boolean;
  immobilized?: boolean;
  crew_exposed?: boolean;
  gun?: number;
  movement_points?: number;
  riding?: number;
}

/** Rule 25.2: the opponent sees the counter and not what is below it. */
export interface ConcealmentToken {
  id: number;
  hex: string;
  own: boolean;
  stack: number;
  player?: number;
  units?: number[];
}

/** Rule 23: a charge of the viewer's own side, waiting on its target hex. */
export interface DemoToken {
  id: number;
  hex: string;
  own: boolean;
}

export interface ViewDocument {
  /** True in a game between two computer opponents, where the watcher sees each side. */
  spectator?: boolean;
  viewer: number;
  turn: number;
  turn_limit: number;
  phase: string;
  phasing: number;
  active: number;
  game_over: boolean;
  result: string;
  result_cause: string;
  melee: string[];
  fire_group: { target: string; members: [number, number | null][]; leader: number | null } | null;
  units: UnitDocument[];
  concealment: ConcealmentToken[];
  smoke: string[];
  demo: DemoToken[];
}

export interface CommandPayload {
  action: string;
  units?: number[];
  hex?: string;
  weapon?: number;
  targets?: number[];
  leader?: number;
}

export interface LegalCommand {
  id: string;
  payload: CommandPayload;
}

export interface LogEntry {
  rule_id: string;
  kind: string;
  data: Record<string, unknown>;
}

export interface WelcomeMessage {
  type: "welcome";
  player: number;
  seat: string;
  board: BoardDocument;
  scenario: ScenarioDocument;
}

export interface FrameMessage {
  type: "frame";
  player: number;
  view: ViewDocument;
  frame_id: string;
  active: number;
  phase: string;
  sub_step: string;
  turn: number;
  legal_commands: LegalCommand[];
  log_tail: LogEntry[];
}

export interface ErrorMessage {
  type: "error";
  rule_id: string;
  message: string;
}

export interface LosResultMessage {
  type: "los_result";
  from: string;
  to: string;
  result: {
    clear: boolean;
    rule_id: string;
    traced: string[];
    hindrance: number;
    blocking_hex: string | null;
  };
}

export interface GameOverMessage {
  type: "game_over";
  result: string;
  cause: string;
}

export type HostMessage = WelcomeMessage | FrameMessage | ErrorMessage | LosResultMessage | GameOverMessage;
