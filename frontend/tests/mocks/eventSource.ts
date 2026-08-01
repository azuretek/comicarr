/**
 * Controllable EventSource stub.
 *
 * happy-dom ships no EventSource, and even a real one would make the SSE tests
 * depend on a server. This lets a test open, fail, and feed a socket by hand,
 * and — the point of it — inspect exactly which event types got a listener.
 */

type Listener = (event: MessageEvent) => void;

export class MockEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  /** Every socket the hook has constructed, oldest first. */
  static instances: MockEventSource[] = [];

  static reset() {
    MockEventSource.instances = [];
  }

  static get latest(): MockEventSource {
    const last = MockEventSource.instances.at(-1);
    if (!last) throw new Error("No EventSource was constructed");
    return last;
  }

  readyState = MockEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;

  private readonly listeners = new Map<string, Set<Listener>>();

  constructor(readonly url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    const bucket = this.listeners.get(type) ?? new Set<Listener>();
    bucket.add(listener);
    this.listeners.set(type, bucket);
  }

  removeEventListener(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  close() {
    this.readyState = MockEventSource.CLOSED;
  }

  /** Event types this socket has at least one listener for. */
  get registeredTypes(): string[] {
    return [...this.listeners.keys()].filter(
      (type) => (this.listeners.get(type)?.size ?? 0) > 0,
    );
  }

  open() {
    this.readyState = MockEventSource.OPEN;
    this.onopen?.();
  }

  fail() {
    this.readyState = MockEventSource.CLOSED;
    this.onerror?.();
  }

  emit(type: string, data: unknown) {
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    for (const listener of [...(this.listeners.get(type) ?? [])]) {
      listener({ data: payload } as MessageEvent);
    }
  }
}
