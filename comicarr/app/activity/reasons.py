#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Registry for ``fail_reason`` base tokens and their operator-facing phrases.

**The classifiable unit is the base token before the first ``:``** (#523).
Many reasons are composite — ``postprocess_error:OperationalError`` — where the
suffix is a raw Python exception class, a route name, or a field name. The
suffix space is open and not statically enumerable, so nothing may key on the
whole ``fail_reason`` string.

This module is the single home for wording. The band and the triage surface
render ``reason_phrase`` computed here rather than mapping tokens client-side,
so matching and wording cannot drift apart (#526). Unmapped tokens degrade to a
generic phrase — never a snake_case token as an operator-facing line (#427).

The actionability verdicts decided in #523 (which base tokens the band admits,
and the reconciliation each excluded token owes) belong beside these phrases
when that work lands; they are deliberately not asserted here yet, because
excluding a reason without its reconciliation would strand the affected issues.
"""

#: Operator-facing phrase per admitted base token (#523 classification, #526 wording).
REASON_PHRASES = {
    # Bytes stranded — a file exists and did not reach the library.
    "downloaded_invalid_artifact_command": "downloaded file failed post-process checks",
    "invalid_recovered_postprocess_command": "recovered download has a bad post-process command",
    "invalid_postprocess_command": "post-process command is invalid",
    "postprocess_error": "post-processing failed",
    "recovered_postprocess_error": "recovered download failed post-processing",
    "ddl_artifact_state_persistence_error": "could not save download state (direct download)",
    "torrent_artifact_state_persistence_error": "could not save download state (torrent)",
    "nzb_artifact_state_persistence_error": "could not save download state (NZB)",
    # Ambiguity only a human can settle — an external downloader to go and look at.
    "reserved_without_persisted_acceptance": "download reserved but never fully accepted",
    "route_acceptance_missing_identity": "the downloader accepted it without identifying it",
    "submission_outcome_unknown": "submission result unknown — check the downloader",
    "route_not_restart_safe": "this route can't resume after a restart",
    # The operator asked to be asked.
    "download_failed_no_auto_handling": "download failed and auto-handling is off",
    "submission_rejected": "the downloader rejected the submission",
}

#: Shown when a base token has no phrase — the same degradation the timeline uses.
UNMAPPED_REASON_PHRASE = "something went wrong"


def base_reason(fail_reason):
    """Return the classifiable unit: everything before the first ``:``.

    ``None`` / blank in, ``None`` out. No writer concatenates raw exception
    text into ``fail_reason`` (sanitized detail rides ``payload['fail_detail']``),
    so splitting on the first colon is always unambiguous.
    """
    if fail_reason in (None, ""):
        return None
    token = str(fail_reason).strip()
    if not token:
        return None
    return token.split(":", 1)[0]


def reason_phrase(fail_reason):
    """Operator-facing phrase for a raw ``fail_reason``, matched on its base token."""
    return REASON_PHRASES.get(base_reason(fail_reason) or "", UNMAPPED_REASON_PHRASE)
