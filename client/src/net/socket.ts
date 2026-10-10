// The WebSocket client. Every crossing of the boundary has a handler, and a closed
// socket retries with a growing wait, so a host restart does not need a page reload.

import type { HostMessage } from "./protocol";

const FIRST_RETRY_MS = 500;
const MAX_RETRY_MS = 8000;

export type MessageHandler = (message: HostMessage) => void;
export type StatusHandler = (status: string) => void;

export class HostSocket {
  private socket: WebSocket | null = null;
  private retryMs = FIRST_RETRY_MS;
  private closed = false;

  constructor(
    private readonly url: string,
    private readonly roomCode: string,
    private readonly onMessage: MessageHandler,
    private readonly onStatus: StatusHandler,
  ) {}

  connect(): void {
    this.closed = false;
    this.onStatus("connecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url);
    } catch (error) {
      this.onStatus(`cannot open the connection: ${String(error)}`);
      this.scheduleRetry();
      return;
    }
    this.socket = socket;
    socket.onopen = () => {
      this.retryMs = FIRST_RETRY_MS;
      this.onStatus("connected");
      this.send({ type: "join", room_code: this.roomCode, display_name: "browser" });
    };
    socket.onmessage = (event) => {
      let message: HostMessage;
      try {
        message = JSON.parse(String(event.data)) as HostMessage;
      } catch (error) {
        this.onStatus(`the host sent a message that is not valid JSON: ${String(error)}`);
        return;
      }
      this.onMessage(message);
    };
    socket.onerror = () => {
      this.onStatus("the connection reported an error");
    };
    socket.onclose = () => {
      this.socket = null;
      if (this.closed) {
        return;
      }
      this.onStatus("the host closed the connection");
      this.scheduleRetry();
    };
  }

  private scheduleRetry(): void {
    const wait = this.retryMs;
    this.retryMs = Math.min(this.retryMs * 2, MAX_RETRY_MS);
    window.setTimeout(() => this.connect(), wait);
  }

  send(message: Record<string, unknown>): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.onStatus("no connection to the host");
      return false;
    }
    this.socket.send(JSON.stringify(message));
    return true;
  }

  intent(frameId: string, commandId: string): boolean {
    return this.send({ type: "intent", frame_id: frameId, command_id: commandId });
  }

  losRequest(from: string, to: string): boolean {
    return this.send({ type: "los_request", from, to });
  }

  close(): void {
    this.closed = true;
    this.socket?.close();
  }
}
