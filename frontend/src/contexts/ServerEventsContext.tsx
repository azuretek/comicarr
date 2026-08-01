import { createContext, useContext, type ReactNode } from "react";
import { useServerEvents } from "@/hooks/useServerEvents";
import type { LiveConnectionState } from "@/lib/activityLive";

export interface ServerEventsHealth {
  isConnected: boolean;
  isReconnecting: boolean;
  connectionLost: boolean;
  live: LiveConnectionState;
}

const ServerEventsContext = createContext<ServerEventsHealth | null>(null);

/**
 * Owns the app's single EventSource and publishes its health to the chrome.
 * The stream itself is consumed inside `useServerEvents`; only reachability
 * escapes, because every activity surface is query-backed.
 */
export function ServerEventsProvider({
  enabled,
  children,
}: {
  enabled: boolean;
  children: ReactNode;
}) {
  const health = useServerEvents(enabled);
  return (
    <ServerEventsContext.Provider value={health}>
      {children}
    </ServerEventsContext.Provider>
  );
}

/**
 * Assume reachable outside the provider. A component rendered in isolation has
 * no evidence of an outage, and inventing one would put `unreachable` in the
 * status bar of a perfectly healthy app.
 */
const ASSUME_REACHABLE: ServerEventsHealth = {
  isConnected: true,
  isReconnecting: false,
  connectionLost: false,
  live: "connected",
};

export function useServerEventsHealth(): ServerEventsHealth {
  return useContext(ServerEventsContext) ?? ASSUME_REACHABLE;
}
