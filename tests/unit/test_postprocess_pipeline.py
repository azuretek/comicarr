#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from unittest.mock import MagicMock

import pytest

from comicarr.app.downloads.postprocess_pipeline import (
    PostProcessContext,
    PostProcessJournalStage,
)


def _stage(*, release_key=None, recorded=True, error=None):
    journal = MagicMock()
    journal.derive_release_key.return_value = "derived-key"
    if error is not None:
        journal.record_transition.side_effect = error
    else:
        journal.record_transition.return_value = recorded
    log = MagicMock()
    context = PostProcessContext(
        issue_id="I1",
        issue_arc_id=None,
        comic_id="C1",
        nzb_name="Saga.001.cbz",
        nzb_folder="/downloads/saga",
        api_call=False,
        ddl=False,
        canonical_release_key=release_key,
        log_module="[POST-PROCESSING]",
    )
    return PostProcessJournalStage(journal=journal, log=log), context, journal, log


def test_canonical_release_key_is_reused_for_primary_transition():
    stage, context, journal, _log = _stage(release_key="canonical-key")

    assert stage.release_key(context, issue_id="I1") == "canonical-key"
    journal.derive_release_key.assert_not_called()


def test_story_arc_override_derives_a_distinct_release_key():
    stage, context, journal, _log = _stage(release_key="canonical-key")

    assert stage.release_key(context, issue_arc_id="ARC9") == "derived-key"
    journal.derive_release_key.assert_called_once_with(
        {
            "issueid": "ARC9",
            "IssueArcID": "ARC9",
            "comicid": "C1",
            "nzbname": "Saga.001.cbz",
            "ddl": False,
        }
    )


def test_transition_records_explicit_context_and_reports_success():
    stage, context, journal, _log = _stage(release_key="canonical-key")

    result = stage.transition(context, "moved", issue_id="I1")

    assert result.release_key == "canonical-key"
    assert result.stage == "moved"
    assert result.recorded is True
    assert result.error is None
    journal.record_transition.assert_called_once_with(
        "canonical-key",
        "moved",
        payload={
            "issueid": "I1",
            "issuearcid": None,
            "comicid": "C1",
            "nzb_name": "Saga.001.cbz",
            "nzb_folder": "/downloads/saga",
            "apicall": False,
            "ddl": False,
        },
        conn=None,
        issueid="I1",
    )


def test_duplicate_transition_is_an_explicit_idempotent_noop():
    stage, context, _journal, _log = _stage(release_key="canonical-key", recorded=False)

    result = stage.transition(context, "moved")

    assert result.recorded is False
    assert result.error is None


def test_additive_transition_failure_is_inert_and_observable():
    stage, context, _journal, log = _stage(error=RuntimeError("boom"))

    result = stage.transition(context, "post_processing")

    assert result.recorded is False
    assert result.error == "boom"
    log.error.assert_called_once()


def test_transactional_transition_failure_propagates_for_caller_rollback():
    stage, context, _journal, _log = _stage(error=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        stage.transition(context, "post_processed", conn=object())
