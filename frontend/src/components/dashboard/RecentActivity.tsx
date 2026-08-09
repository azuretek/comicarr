import { Link } from "react-router-dom";
import {
  PanelBody,
  PanelSkeleton,
} from "@/components/dashboard/DashboardPanel";
import {
  sentenceFor,
  subjectHref,
  severityOf,
  type TimelineEvent,
} from "@/components/activity/timeline";
import RelativeTime from "@/components/ui/RelativeTime";
import { useDashboardActivity } from "@/hooks/useDashboard";
import { panelState } from "@/lib/panelState";

/**
 * Recent activity from the narrative stream
 * (docs/architecture/dashboard-spec.md §3.4).
 *
 * The old panel listed `t_snatched` rows, so an attempt that never reached a
 * snatch left no trace — which is how a broken downloader could look like a
 * quiet week. Reading narrative events means failures, blocked routes, and
 * manual reviews share the timeline with successes. Sentences and deep-links
 * match the Activity Center so the two surfaces never invent different prose
 * for the same event.
 */

const ACTIVITY_HREF = "/activity";

function EventHeadline({ event }: { event: TimelineEvent }) {
  const text = sentenceFor(event);
  const href = subjectHref(event);
  const label = event.subject_label;

  if (!href || !label || event.subject_type === "run") {
    return <span>{text}</span>;
  }

  const idx = text.indexOf(label);
  if (idx < 0) {
    return (
      <span>
        {text}{" "}
        <Link to={href} className="font-medium hover:text-[var(--primary)]">
          {label}
        </Link>
      </span>
    );
  }

  return (
    <span>
      {text.slice(0, idx)}
      <Link to={href} className="font-medium hover:text-[var(--primary)]">
        {label}
      </Link>
      {text.slice(idx + label.length)}
    </span>
  );
}

function EventRow({ event, first }: { event: TimelineEvent; first: boolean }) {
  const trouble = severityOf(String(event.status)) === "action_required";

  return (
    <div
      className="grid items-center gap-2 py-1.5 font-mono text-[11px]"
      style={{
        gridTemplateColumns: "120px minmax(0, 1fr)",
        borderTop: first
          ? "none"
          : "1px solid var(--border-soft, var(--border))",
      }}
      data-testid="recent-activity-row"
      data-status={event.status}
      data-activity={event.activity}
    >
      <RelativeTime value={event.created_at} />
      <div
        className="min-w-0 font-sans text-[12px] truncate"
        style={trouble ? { color: "var(--status-error)" } : undefined}
      >
        <EventHeadline event={event} />
      </div>
    </div>
  );
}

export default function RecentActivity() {
  const activity = useDashboardActivity();
  const events = activity.data?.events ?? [];
  const days = activity.data?.days ?? 30;
  const state = panelState(activity, events.length === 0);

  const meta =
    state === "loading"
      ? "…"
      : state === "unavailable"
        ? "unavailable"
        : `${events.length} event${events.length === 1 ? "" : "s"} · ${days} days`;

  return (
    <section
      className="px-5 py-4 lg:border-r lg:border-border"
      data-testid="recent-activity"
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5">
          <div className="text-[13px] font-semibold">Recent activity</div>
          <div className="font-mono text-[10px] text-muted-foreground tracking-wider uppercase">
            {meta}
          </div>
        </div>
        <Link
          to={ACTIVITY_HREF}
          className="font-mono text-[10px] text-muted-foreground hover:text-foreground"
        >
          open activity →
        </Link>
      </div>

      <PanelBody
        state={state}
        label="Recent activity"
        skeleton={<PanelSkeleton rows={5} />}
        empty={
          <>
            No activity in the last {days} days —{" "}
            <Link to={ACTIVITY_HREF} className="hover:text-foreground">
              open full activity
            </Link>
          </>
        }
        onRetry={() => void activity.refetch()}
        isRetrying={activity.isFetching}
      >
        {() => (
          <div>
            {events.map((event, i) => (
              <EventRow
                key={String(event.event_id)}
                event={event}
                first={i === 0}
              />
            ))}
          </div>
        )}
      </PanelBody>
    </section>
  );
}
