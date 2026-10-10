// The client bootstrap. It joins the host, draws the view it receives, and sends one
// command identifier when the player picks a command. It holds no rule (AR-06).

import "./style.css";
import { Camera, fitCamera, hexAt } from "./board/geometry";
import { RenderState, render } from "./board/render";
import { renderLog } from "./log/panel";
import { HostSocket } from "./net/socket";
import type { BoardDocument, HostMessage, LegalCommand, LogEntry, ScenarioDocument, UnitDocument, ViewDocument } from "./net/protocol";
import { commandsForHex, groupByAction, hexesOfCommands, label } from "./views/commands";

const MIN_SCALE = 3;
const MAX_SCALE = 60;

interface ClientState {
  board: BoardDocument | null;
  scenario: ScenarioDocument | null;
  view: ViewDocument | null;
  frameId: string | null;
  legal: LegalCommand[];
  log: LogEntry[];
  camera: Camera;
  selected: string | null;
  actionFilter: string | null;
  losFrom: string | null;
  losTraced: string[];
  losClear: boolean | null;
  losTool: boolean;
  tabletop: boolean;
  phase: string;
  subStep: string;
  watching: boolean;
}

const state: ClientState = {
  board: null,
  scenario: null,
  view: null,
  frameId: null,
  legal: [],
  log: [],
  camera: { scale: 10, offsetX: 20, offsetY: 20 },
  selected: null,
  actionFilter: null,
  losFrom: null,
  losTraced: [],
  losClear: null,
  losTool: false,
  tabletop: false,
  watching: false,
  phase: "",
  subStep: "",
};

const canvas = document.getElementById("board") as HTMLCanvasElement;
const context = canvas.getContext("2d");
const commandList = document.getElementById("command-list") as HTMLUListElement;
const commandFilter = document.getElementById("command-filter") as HTMLDivElement;
const logList = document.getElementById("log-list") as HTMLOListElement;
const statusText = document.getElementById("status") as HTMLElement;
const selectionText = document.getElementById("selection") as HTMLElement;
const scenarioText = document.getElementById("scenario") as HTMLElement;
const turnText = document.getElementById("turn") as HTMLElement;
const phaseText = document.getElementById("phase") as HTMLElement;
const tabletopBox = document.getElementById("tabletop") as HTMLInputElement;
const strictBox = document.getElementById("strict") as HTMLInputElement;
const losButton = document.getElementById("los-tool") as HTMLButtonElement;

function roomCode(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("room") ?? "";
}

const noticePanel = document.getElementById("notice-panel") as HTMLElement;
const noticeTitle = document.getElementById("notice-title") as HTMLElement;
const noticeBody = document.getElementById("notice-body") as HTMLElement;

/** Say why the page is empty, where a person reads it (SR-03). */
function showNotice(title: string, body: string): void {
  noticeTitle.textContent = title;
  noticeBody.innerHTML = body;
  noticePanel.hidden = false;
}

function hideNotice(): void {
  noticePanel.hidden = true;
}

function socketUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}`;
}

const socket = new HostSocket(socketUrl(), roomCode(), onMessage, setStatus);

function setStatus(text: string): void {
  statusText.textContent = text;
}

function onMessage(message: HostMessage): void {
  switch (message.type) {
    case "welcome":
      state.board = message.board;
      state.scenario = message.scenario;
      scenarioText.textContent = `${message.scenario.title} (${message.seat})`;
      hideNotice();
      resizeCanvas();
      setStatus(`joined as player ${message.player}`);
      state.watching = false;
      break;
    case "frame":
      state.view = message.view;
      state.frameId = message.frame_id;
      state.legal = message.legal_commands;
      state.log = message.log_tail;
      state.phase = message.phase;
      state.subStep = message.sub_step;
      // A game between two computer opponents sends a spectator view. Nobody holds a seat
      // there, so the header names the side that acts and not the seat of the reader.
      if (message.view.spectator && !state.watching) {
        state.watching = true;
        scenarioText.textContent = `${state.scenario?.title ?? ""} (computer against computer)`;
        setStatus("watching two computer opponents");
      }
      turnText.textContent = `turn ${message.turn} of ${message.view.turn_limit}`;
      const who = message.view.spectator ? `side ${message.active} acts` : `player ${message.active}`;
      phaseText.textContent = `${message.phase.replace(/_/g, " ")}, ${message.sub_step.replace(/_/g, " ")}, ${who}`;
      renderCommands();
      renderLog(logList, state.log, state.tabletop);
      draw();
      break;
    case "error":
      setStatus(`rule ${message.rule_id}: ${message.message}`);
      if (message.rule_id === "SR-03") {
        // The host refuses a join with no room code or with the wrong one. Without a
        // notice the person gets an empty board and a line of small text.
        showNotice(
          roomCode() ? "That room code is not the one this host uses" : "This page needs a room code",
          "The host prints an address that ends with <code>?room=</code> and the code. Open that " +
            "address. The code changes each time the host starts, so an old link does not work.",
        );
      }
      break;
    case "los_result":
      state.losTraced = message.result.traced;
      state.losClear = message.result.clear;
      setStatus(
        message.result.clear
          ? `line of sight from ${message.from} to ${message.to} is clear, rule ${message.result.rule_id}, hindrance ${message.result.hindrance}`
          : `no line of sight from ${message.from} to ${message.to}, rule ${message.result.rule_id}${message.result.blocking_hex ? `, stopped at ${message.result.blocking_hex}` : ""}`,
      );
      draw();
      break;
    case "game_over":
      setStatus(`game over: ${message.result}. ${message.cause}`);
      break;
  }
}

function unitsById(): Map<number, UnitDocument> {
  const map = new Map<number, UnitDocument>();
  for (const unit of state.view?.units ?? []) {
    map.set(unit.id, unit);
  }
  return map;
}

function visibleCommands(): LegalCommand[] {
  let commands = state.legal;
  if (state.selected) {
    const forHex = commandsForHex(commands, state.selected, state.view);
    if (forHex.length > 0) {
      commands = forHex;
    }
  }
  if (state.actionFilter) {
    commands = commands.filter((c) => c.payload.action === state.actionFilter);
  }
  return commands;
}

function renderCommands(): void {
  const units = unitsById();
  commandFilter.replaceChildren();
  for (const group of groupByAction(state.legal)) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${group.action.replace(/_/g, " ")} (${group.commands.length})`;
    button.className = state.actionFilter === group.action ? "on" : "";
    button.addEventListener("click", () => {
      state.actionFilter = state.actionFilter === group.action ? null : group.action;
      renderCommands();
      draw();
    });
    commandFilter.append(button);
  }
  commandList.replaceChildren();
  for (const command of visibleCommands()) {
    const item = document.createElement("li");
    item.textContent = label(command, units);
    item.dataset.commandId = command.id;
    item.addEventListener("click", () => sendIntent(command));
    item.addEventListener("mouseenter", () => {
      if (command.payload.hex) {
        state.losTraced = [];
        draw(new Set([command.payload.hex]));
      }
    });
    commandList.append(item);
  }
}

function sendIntent(command: LegalCommand): void {
  if (!state.frameId) {
    setStatus("no frame from the host yet");
    return;
  }
  if (socket.intent(state.frameId, command.id)) {
    setStatus(`sent ${command.payload.action}`);
  }
}

function draw(extra?: Set<string>): void {
  if (!context || !state.board) {
    return;
  }
  const highlighted = extra ?? hexesOfCommands(visibleCommands());
  const renderState: RenderState = {
    board: state.board,
    view: state.view,
    camera: state.camera,
    selected: state.selected,
    highlighted,
    losFrom: state.losFrom,
    losTraced: state.losTraced,
    losClear: state.losClear,
    tabletop: state.tabletop,
  };
  render(context, renderState);
}

function resizeCanvas(): void {
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(320, Math.floor(rect.width));
  canvas.height = Math.max(240, Math.floor(rect.height));
  if (state.board) {
    state.camera = fitCamera(state.board, canvas.width, canvas.height);
  }
  draw();
}

canvas.addEventListener("click", (event) => {
  if (!state.board) {
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const hex = hexAt(state.board, event.clientX - rect.left, event.clientY - rect.top, state.camera);
  if (!hex) {
    return;
  }
  if (state.losTool) {
    if (state.losFrom === null) {
      state.losFrom = hex.id;
      state.losTraced = [];
      state.losClear = null;
      setStatus(`line of sight from ${hex.id}, now pick the target`);
    } else {
      socket.losRequest(state.losFrom, hex.id);
      state.losTool = false;
      losButton.classList.remove("on");
    }
    draw();
    return;
  }
  state.selected = state.selected === hex.id ? null : hex.id;
  const occupants = (state.view?.units ?? []).filter((u) => u.hex === hex.id && u.carrier === null);
  selectionText.textContent = state.selected
    ? `${hex.id}, ${hex.terrain.replace(/_/g, " ")}${hex.building ? `, building ${hex.building.id} of ${hex.building.size} hexes` : ""}, ${occupants.length} counters`
    : "";
  renderCommands();
  draw();
});

canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
  const rect = canvas.getBoundingClientRect();
  const px = event.clientX - rect.left;
  const py = event.clientY - rect.top;
  const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, state.camera.scale * factor));
  const ratio = next / state.camera.scale;
  state.camera = {
    scale: next,
    offsetX: px - (px - state.camera.offsetX) * ratio,
    offsetY: py - (py - state.camera.offsetY) * ratio,
  };
  draw();
}, { passive: false });

let dragging = false;
let dragX = 0;
let dragY = 0;

canvas.addEventListener("pointerdown", (event) => {
  if (event.button !== 1 && !event.shiftKey) {
    return;
  }
  dragging = true;
  dragX = event.clientX;
  dragY = event.clientY;
  canvas.setPointerCapture(event.pointerId);
});

canvas.addEventListener("pointermove", (event) => {
  if (!dragging) {
    return;
  }
  state.camera = {
    scale: state.camera.scale,
    offsetX: state.camera.offsetX + (event.clientX - dragX),
    offsetY: state.camera.offsetY + (event.clientY - dragY),
  };
  dragX = event.clientX;
  dragY = event.clientY;
  draw();
});

canvas.addEventListener("pointerup", () => {
  dragging = false;
});

tabletopBox.addEventListener("change", () => {
  state.tabletop = tabletopBox.checked;
  renderLog(logList, state.log, state.tabletop);
  draw();
});

strictBox.addEventListener("change", () => {
  setStatus(
    strictBox.checked
      ? "strict mode: the host answers a line of sight question only in a fire phase (rule 19.3)"
      : "casual mode: the line of sight tool is available at all times",
  );
});

losButton.addEventListener("click", () => {
  state.losTool = !state.losTool;
  state.losFrom = null;
  state.losTraced = [];
  losButton.classList.toggle("on", state.losTool);
  setStatus(state.losTool ? "pick the firing hex" : "line of sight tool off");
  draw();
});

window.addEventListener("resize", resizeCanvas);

resizeCanvas();
socket.connect();

// The Playwright test reads this handle to drive the client (TR-07).
declare global {
  interface Window {
    slClient: {
      state: ClientState;
      send: (commandId: string) => void;
      commandIds: () => string[];
      firstOfAction: (action: string) => string | null;
      los: (from: string, to: string) => boolean;
    };
  }
}

window.slClient = {
  state,
  send: (commandId: string) => {
    const command = state.legal.find((c) => c.id === commandId);
    if (command) {
      sendIntent(command);
    }
  },
  commandIds: () => state.legal.map((c) => c.id),
  firstOfAction: (action: string) => state.legal.find((c) => c.payload.action === action)?.id ?? null,
  los: (from: string, to: string) => {
    state.losFrom = from;
    state.losTraced = [];
    state.losClear = null;
    return socket.losRequest(from, to);
  },
};
