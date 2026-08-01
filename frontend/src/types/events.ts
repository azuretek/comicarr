/**
 * Server-Sent Events (SSE) type definitions
 *
 * The narrative channel is `activity` alone — its payload type is
 * `TimelineEvent` (see components/activity/timeline/types.ts), parsed through
 * `lib/activityLive.ts`. The per-feature channels that used to live here
 * (`addbyid`, `scheduler_message`, `config_check`, `search_progress`,
 * `search_complete`, generic `message`) have no producer and no listener.
 */

/** Custom window event for comic-added */
export interface ComicAddedEvent extends CustomEvent<string> {
  detail: string;
}
