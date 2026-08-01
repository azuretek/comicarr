import { describe, expect, it } from "vitest";
import {
  ACTIVITY_COALESCE_MS,
  ACTIVITY_INVALIDATION_KEYS,
  NO_TROUBLE,
  collateralKeys,
  comicAddedDetail,
  latchOnAttention,
  latchOnEvent,
  parseActivityEvent,
} from "@/lib/activityLive";
import type { TimelineEvent } from "@/components/activity/timeline/types";

function event(partial: Partial<TimelineEvent> = {}): TimelineEvent {
  return {
    event_id: 41,
    created_at: "2026-08-01T12:00:00+00:00",
    activity: "import",
    status: "succeeded",
    subject_type: "issue",
    subject_id: "9001",
    subject_label: "Saga #12",
    ...partial,
  };
}

describe("parseActivityEvent", () => {
  it("accepts a full narrative payload", () => {
    const parsed = parseActivityEvent(JSON.stringify(event()));
    expect(parsed?.subject_label).toBe("Saga #12");
    expect(parsed?.event_id).toBe(41);
  });

  it("rejects payloads missing identity fields", () => {
    expect(
      parseActivityEvent(JSON.stringify({ ...event(), subject_id: "" })),
    ).toBeNull();
    expect(
      parseActivityEvent(JSON.stringify({ ...event(), event_id: null })),
    ).toBeNull();
    expect(
      parseActivityEvent(JSON.stringify({ ...event(), status: undefined })),
    ).toBeNull();
  });

  it("rejects non-object, empty, and malformed data", () => {
    expect(parseActivityEvent(undefined)).toBeNull();
    expect(parseActivityEvent("")).toBeNull();
    expect(parseActivityEvent("not json")).toBeNull();
    expect(parseActivityEvent("[]")).toBeNull();
    expect(parseActivityEvent("null")).toBeNull();
  });
});

describe("invalidation contract", () => {
  it("covers the narrative feed and both derived projections", () => {
    expect(ACTIVITY_INVALIDATION_KEYS).toEqual([
      ["activity", "timeline"],
      ["activity", "band"],
      ["activity", "status"],
    ]);
  });

  it("coalesces on a sub-second trailing window", () => {
    expect(ACTIVITY_COALESCE_MS).toBeGreaterThan(0);
    expect(ACTIVITY_COALESCE_MS).toBeLessThan(1000);
  });
});

describe("collateralKeys", () => {
  it("stales the series caches for a series narration", () => {
    expect(
      collateralKeys(
        event({ activity: "add", subject_type: "series", subject_id: "4050" }),
      ),
    ).toEqual([["series"], ["series", "4050"]]);
  });

  it("stales the story arc cache for an arc narration", () => {
    expect(
      collateralKeys(event({ activity: "add", subject_type: "arc" })),
    ).toEqual([["storyArcs"]]);
  });

  it("stales nothing extra for issue-scoped narration", () => {
    expect(collateralKeys(event())).toEqual([]);
  });
});

describe("comicAddedDetail", () => {
  it("re-emits a completed series add for the search cards", () => {
    const detail = comicAddedDetail(
      event({
        activity: "add",
        status: "succeeded",
        subject_type: "series",
        subject_id: "4050",
        subject_label: "Saga (2012)",
      }),
    );
    expect(detail && JSON.parse(detail)).toEqual({
      comicid: "4050",
      comicname: "Saga (2012)",
      status: "success",
      message: "Added Saga (2012)",
    });
  });

  it("re-emits a failed series add with the failure sentence", () => {
    const detail = comicAddedDetail(
      event({
        activity: "add",
        status: "failed",
        subject_type: "series",
        subject_id: "4050",
        subject_label: "Saga (2012)",
        reason_code: "provider_error",
      }),
    );
    expect(detail && JSON.parse(detail)).toMatchObject({
      comicid: "4050",
      status: "failure",
      message: "Couldn't add Saga (2012)",
    });
  });

  it("stays silent for in-progress, arc, and non-add narration", () => {
    expect(
      comicAddedDetail(
        event({ activity: "add", status: "started", subject_type: "series" }),
      ),
    ).toBeNull();
    expect(
      comicAddedDetail(
        event({ activity: "add", status: "succeeded", subject_type: "arc" }),
      ),
    ).toBeNull();
    expect(
      comicAddedDetail(
        event({
          activity: "refresh",
          status: "succeeded",
          subject_type: "series",
        }),
      ),
    ).toBeNull();
  });
});

describe("enter-trouble latch", () => {
  it("toasts on the edge into trouble and stays silent after", () => {
    const first = latchOnEvent(NO_TROUBLE, event({ status: "failed" }));
    expect(first.toast).toEqual({
      title: "Needs attention",
      description: "Couldn't import Saga #12",
    });
    expect(first.latch.latched).toBe(true);

    const second = latchOnEvent(
      first.latch,
      event({ status: "needs_attention", subject_label: "Saga #13" }),
    );
    expect(second.toast).toBeNull();
    expect(second.latch.latched).toBe(true);
  });

  it("never toasts normal severity, latched or not", () => {
    for (const status of ["started", "succeeded", "no_match", "cancelled"]) {
      const result = latchOnEvent(NO_TROUBLE, event({ status }));
      expect(result.toast).toBeNull();
      expect(result.latch.latched).toBe(false);
    }
  });

  it("re-arms only once the visible attention count reaches zero", () => {
    const troubled = latchOnEvent(NO_TROUBLE, event({ status: "blocked" }));
    expect(latchOnAttention(troubled.latch, 3).latched).toBe(true);

    const cleared = latchOnAttention(troubled.latch, 0);
    expect(cleared.latched).toBe(false);
    expect(latchOnEvent(cleared, event({ status: "failed" })).toast).not.toBe(
      null,
    );
  });

  it("ignores an unknown attention count", () => {
    const troubled = latchOnEvent(NO_TROUBLE, event({ status: "failed" }));
    expect(latchOnAttention(troubled.latch, undefined).latched).toBe(true);
  });
});
