#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Restart-safe stages used by the legacy post-processing facade."""

from dataclasses import dataclass
from typing import Any

from comicarr import logger
from comicarr.app.downloads import journal


@dataclass(frozen=True)
class PostProcessContext:
    """Explicit state required to advance post-processing recovery."""

    issue_id: str | None
    issue_arc_id: str | None
    comic_id: str | None
    nzb_name: str
    nzb_folder: str
    api_call: bool
    ddl: bool
    canonical_release_key: str | None
    log_module: str


@dataclass(frozen=True)
class PostProcessTransitionResult:
    """Observable outcome of an attempted journal transition."""

    release_key: str | None
    stage: str
    recorded: bool
    error: str | None = None


class PostProcessJournalStage:
    """Advance the durable journal around irreversible post-processing work.

    The injected collaborators make failure and idempotency behavior testable
    without a database. The default journal module remains patchable by the
    facade's existing integration tests.
    """

    def __init__(self, journal=journal, log=logger):
        self._journal = journal
        self._log = log

    def release_key(
        self,
        context: PostProcessContext,
        *,
        issue_id: str | None = None,
        issue_arc_id: str | None = None,
    ) -> str:
        explicit_arc_override = issue_arc_id is not None and issue_arc_id != context.issue_arc_id
        if context.canonical_release_key and not explicit_arc_override:
            return context.canonical_release_key

        if explicit_arc_override:
            identity = {
                "issueid": issue_arc_id,
                "IssueArcID": issue_arc_id,
                "comicid": context.comic_id,
                "nzbname": context.nzb_name,
                "ddl": context.ddl,
            }
            return self._journal.derive_release_key(identity)

        identity = {
            "issueid": issue_id if issue_id is not None else context.issue_id,
            "IssueArcID": issue_arc_id if issue_arc_id is not None else context.issue_arc_id,
            "comicid": context.comic_id,
            "nzbname": context.nzb_name,
            "ddl": context.ddl,
        }
        return self._journal.derive_release_key(identity)

    def transition(
        self,
        context: PostProcessContext,
        stage: str,
        *,
        issue_id: str | None = None,
        issue_arc_id: str | None = None,
        payload: dict[str, Any] | None = None,
        conn=None,
    ) -> PostProcessTransitionResult:
        release_key = None
        try:
            release_key = self.release_key(context, issue_id=issue_id, issue_arc_id=issue_arc_id)
            if payload is None:
                payload = {
                    "issueid": issue_id if issue_id is not None else context.issue_id,
                    "issuearcid": issue_arc_id if issue_arc_id is not None else context.issue_arc_id,
                    "comicid": context.comic_id,
                    "nzb_name": context.nzb_name,
                    "nzb_folder": context.nzb_folder,
                    "apicall": context.api_call,
                    "ddl": context.ddl,
                }
            recorded = self._journal.record_transition(
                release_key,
                stage,
                payload=payload,
                conn=conn,
                issueid=issue_id if issue_id is not None else context.issue_id,
            )
            self._log.fdebug(f"{context.log_module} [JOURNAL] {stage} for {release_key}")
            return PostProcessTransitionResult(release_key, stage, bool(recorded))
        except Exception as e:
            if conn is not None:
                raise
            self._log.error(f"{context.log_module} [JOURNAL] {stage} transition failed (inert, continuing): {e}")
            return PostProcessTransitionResult(release_key, stage, False, str(e))
