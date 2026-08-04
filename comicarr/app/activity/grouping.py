#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Needs-attention grouping — the shared key contract (#524).

**Key: ``(comicid, base_reason)``** when ``payload_json.comicid`` is present,
otherwise a singleton ``(release_key, base_reason)``. A series with two admitted
base reasons is two groups, which keeps group-level actions honest and keeps the
status count aligned with distinct problems rather than distinct series titles.

**Labels come from ``payload_json`` only.** No join to ``issues`` / ``annuals``
/ ``comics``, and ``_issue_subject()`` is deliberately not reused: in production
only 13% of band rows resolve through the library join, while the payload
carries ``comicid`` on 100% of them. Grouping on ``comicname`` is also wrong —
a typographic apostrophe split one real series into two fake ones.

**Count and list share this builder.** The status bar's group count and the
band's group list run the same code over the same rows, so they cannot drift.
"""

from comicarr.app.activity.reasons import base_reason, reason_phrase
from comicarr.app.downloads import journal

#: Groups shown before the fold on the band preview (#526 — one card row).
BAND_PREVIEW_CAP = 5

MIXED_STAGE = "mixed"


def _payload_of(row):
    payload = journal.load_payload(row.get("payload_json"))
    return payload if isinstance(payload, dict) else {}


def _text(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _short_release_key(release_key):
    """Trailing segment of a release key, for a label of last resort."""
    key = _text(release_key) or ""
    tail = key.rsplit("|", 1)[-1]
    return tail[:24] if tail else key[:24]


def series_key(payload, release_key):
    """Group identity: payload ``comicid``, else the row's own release key.

    Rows without a ``comicid`` become singletons rather than joining a catch-all
    bucket — a shared "unlabelled" group would recreate the unreadable pile at
    small scale.
    """
    comicid = _text(payload.get("comicid")) or _text(payload.get("ComicID"))
    if comicid:
        return comicid, True
    return _text(release_key) or "", False


def group_key(series_identity, reason_token):
    """Stable serialization of ``(series_or_singleton_key, base_reason)``."""
    return "%s|%s" % (series_identity, reason_token or "")


def series_label(payload, release_key, has_comicid):
    """Label ladder: comicname → "Series {comicid}" → nzbname → short key."""
    name = _text(payload.get("comicname")) or _text(payload.get("ComicName"))
    if name:
        return name
    if has_comicid:
        comicid = _text(payload.get("comicid")) or _text(payload.get("ComicID"))
        return "Series %s" % comicid
    nzbname = _text(payload.get("nzbname")) or _text(payload.get("nzb_name"))
    if nzbname:
        return nzbname
    return _short_release_key(release_key)


def member_label(row, payload):
    """Per-issue label inside a group — same payload-first rule as the group."""
    name = _text(payload.get("comicname")) or _text(payload.get("ComicName"))
    number = _text(payload.get("issuenumber")) or _text(payload.get("Issue_Number"))
    if name and number:
        return "%s #%s" % (name, number)
    if name:
        return name
    nzbname = _text(payload.get("nzbname")) or _text(payload.get("nzb_name")) or _text(row.get("nzbname"))
    if nzbname:
        return nzbname
    issueid = _text(row.get("issueid")) or _text(payload.get("issueid"))
    if issueid:
        return "issue %s" % issueid
    return _short_release_key(row.get("release_key"))


def member_actions(stage):
    """Stage-legal actions for a single journal row.

    Members carry their own eligibility so a mixed-stage group stays workable:
    the group offers no one-click action, but each row can still be selected
    and resolved by whatever its own stage admits.
    """
    return list(journal.STAGE_ACTIONS.get(stage, ()))


def _available_actions(stages):
    """Intersection of stage-legal actions across a group's members.

    Mixed-stage groups get **no** group-level actions: the intersection would be
    ``stop_wanting`` alone, and offering only the destructive half of two
    different obligations as a one-click group button is worse than making the
    operator select the rows they mean (#524). Those rows are reachable through
    ``member_actions`` — a group with no group-level action is never a dead end.

    Today's writers cannot produce a mixed group (reason → stage is a function,
    pinned by ``test_reason_to_stage_is_a_function``), but rows written by older
    versions are never pruned while unresolved, so a real database can still
    hold one. The mixed branch is a live path for historical data, not dead code.
    """
    if len(stages) != 1:
        return []
    stage = next(iter(stages))
    return list(journal.STAGE_ACTIONS.get(stage, ()))


def _stage_of(stages):
    if len(stages) == 1:
        return next(iter(stages))
    return MIXED_STAGE


def build_groups(rows):
    """Group unresolved band rows, newest group first.

    Ranking is **newest first** on ``newest_updated_at``; volume rides along as
    ``member_count`` rather than driving the sort, so a restart burst does not
    permanently outrank the trouble that just happened (#526).
    """
    buckets = {}
    order = []

    for row in rows or []:
        payload = _payload_of(row)
        release_key = row.get("release_key")
        identity, has_comicid = series_key(payload, release_key)
        token = base_reason(row.get("fail_reason"))
        key = group_key(identity, token)

        updated = _text(row.get("updated_date")) or ""
        member = {
            "release_key": release_key,
            "issue_label": member_label(row, payload),
            "issueid": _text(row.get("issueid")) or _text(payload.get("issueid")),
            "stage": row.get("stage"),
            "available_actions": member_actions(row.get("stage")),
            "updated_date": row.get("updated_date"),
        }

        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "group_key": key,
                "comicid": identity if has_comicid else None,
                "series_label": series_label(payload, release_key, has_comicid),
                "base_reason": token,
                "reason_phrase": reason_phrase(row.get("fail_reason")),
                "member_count": 0,
                "newest_updated_at": updated,
                "oldest_updated_at": updated,
                "members": [],
                "_stages": set(),
            }
            buckets[key] = bucket
            order.append(key)

        bucket["member_count"] += 1
        bucket["members"].append(member)
        bucket["_stages"].add(row.get("stage"))
        if updated > (bucket["newest_updated_at"] or ""):
            bucket["newest_updated_at"] = updated
        if not bucket["oldest_updated_at"] or (updated and updated < bucket["oldest_updated_at"]):
            bucket["oldest_updated_at"] = updated

    groups = []
    for key in order:
        bucket = buckets[key]
        stages = bucket.pop("_stages")
        bucket["stage"] = _stage_of(stages)
        bucket["available_actions"] = _available_actions(stages)
        groups.append(bucket)

    groups.sort(key=lambda g: (g["newest_updated_at"] or "", g["group_key"]), reverse=True)
    return groups
