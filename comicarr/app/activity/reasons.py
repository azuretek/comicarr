#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Registry for ``fail_reason`` base tokens: phrases, verdicts, reconciliation.

**The classifiable unit is the base token before the first ``:``** (#523).
Many reasons are composite — ``postprocess_error:OperationalError`` — where the
suffix is a raw Python exception class, a route name, or a field name. The
suffix space is open and not statically enumerable, so nothing may key on the
whole ``fail_reason`` string.

This module is the single home for wording and actionability. The band and the
triage surface render ``reason_phrase`` computed here rather than mapping tokens
client-side, so matching and wording cannot drift apart (#526).

**Actionability** (#523 / #541) is a two-clause test:

1. **Admission.** The band admits a row only when resolving it requires
   information, authority, or judgement the operator holds and the system does not.
2. **Exclusion.** A reason may be excluded only if the system reconciles the
   item — returning it to the acquisition cycle, or recording it as genuinely
   terminal. Never left ``Status='Snatched'``.

Unknown tokens are **admitted (fail-open)** at runtime. Fail-closed would strand
new writers at ``Snatched`` with nothing watching. Completeness is enforced in CI
(``scripts/check_fail_reason_registry.py``), not by the predicate.
"""

from sqlalchemy import and_, not_, or_

# ---------------------------------------------------------------------------
# Operator-facing phrases (admitted base tokens)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Actionability verdicts (#523 / #541)
# ---------------------------------------------------------------------------

#: Flat base tokens excluded from the band. Exact match only (no ``:`` suffix).
NON_ACTIONABLE_FLAT = frozenset(
    {
        "download_gone",
        "download_failed_researching",
        "ddl_download_or_artifact_validation_failed",
        "ddl-worker-rejected",  # hyphen spelling is live in the journal; do not rename
        "torrent_hash_not_in_client",
        "legacy_downloading_without_correlation",
        "ambiguous_ddl_acceptance_after_restart",
    }
)

#: Composite base tokens excluded from the band. Match ``base`` or ``base:%``.
NON_ACTIONABLE_COMPOSITE = frozenset({"immutable_payload_conflict"})

#: Reconciliation obligation per excluded base token.
#:
#: * ``none`` — already reconciled at the write site (do not double-act)
#: * ``rewant`` — return the issue to Wanted (attempt dead; release may be fine)
#: * ``blocklist_and_rewant`` — blocklist the release *and* re-want (release dead)
#: * ``rewant_if_issue`` — re-want only when an issue id resolves (often none)
#: * ``rewant_and_log`` — re-want and log loudly (internal invariant violation)
RECONCILIATION = {
    "download_gone": "blocklist_and_rewant",
    "ddl_download_or_artifact_validation_failed": "blocklist_and_rewant",
    "ddl-worker-rejected": "rewant",
    "torrent_hash_not_in_client": "rewant",
    "ambiguous_ddl_acceptance_after_restart": "rewant",
    "immutable_payload_conflict": "rewant_and_log",
    "legacy_downloading_without_correlation": "rewant_if_issue",
    "download_failed_researching": "none",
}

#: Every known base token with an explicit verdict — admitted or excluded.
#: Completeness gate equates this to the writable set from the AST scan.
KNOWN_BASE_TOKENS = frozenset(REASON_PHRASES) | NON_ACTIONABLE_FLAT | NON_ACTIONABLE_COMPOSITE


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


def is_actionable(fail_reason):
    """Python-side actionability: True if the band should admit this reason.

    Unknown / blank tokens are admitted (fail-open). Matches the SQL predicate.
    """
    token = base_reason(fail_reason)
    if token is None:
        return True
    if token in NON_ACTIONABLE_FLAT:
        return False
    if token in NON_ACTIONABLE_COMPOSITE:
        return False
    return True


def reconciliation_for(fail_reason):
    """Return the reconciliation obligation string for a reason, or None if admitted."""
    token = base_reason(fail_reason)
    if token is None:
        return None
    return RECONCILIATION.get(token)


def actionable_reason_condition(col):
    """SQLAlchemy boolean expression: admit rows whose ``fail_reason`` is actionable.

    NULL-safe and dialect-portable (sqlite / postgresql / mysql): no
    ``instr``/``substr`` extraction. Composite exclusions use a bounded
    ``LIKE 'base:%'`` set (one family today). Unknown tokens pass (fail-open).
    """
    non_actionable = or_(
        col.in_(list(NON_ACTIONABLE_FLAT)),
        *[col.like("%s:%%" % base) for base in sorted(NON_ACTIONABLE_COMPOSITE)],
    )
    # ``col.in_(...)`` / ``LIKE`` yield NULL when col is NULL; ``NOT NULL`` is
    # still NULL and would drop the row. Explicitly admit NULL.
    return or_(col.is_(None), and_(col.isnot(None), not_(non_actionable)))
