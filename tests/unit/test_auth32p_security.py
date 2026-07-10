#  Copyright (C) 2025-2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Security regression tests for 32P authentication logging."""

import comicarr
from comicarr import logger
from comicarr.auth32p import info32p


def test_authenticate_logs_success_without_derived_credentials(monkeypatch):
    """Successful authentication must not write runtime credentials to logs."""
    authentication = info32p.__new__(info32p)
    authentication.module = "[32P-AUTHENTICATION]"
    authentication.status = True
    authentication.status_msg = None
    authentication.error = None
    authentication.test = False
    authentication.mode = None
    authentication.uid = "24680"
    authentication.auth = "runtime-auth-token"
    authentication.authkey = "runtime-auth-key"
    authentication.passkey = "runtime-pass-key"

    messages = []
    monkeypatch.setattr(comicarr, "KEYS_32P", None)
    monkeypatch.setattr(comicarr, "INKDROPS_32P", 0)
    monkeypatch.setattr(logger, "info", messages.append)

    result = authentication.authenticate()

    assert result["status"] is True
    assert messages == ["[32P-AUTHENTICATION] Successfully authenticated using keyed credentials."]
    for credential in (
        authentication.uid,
        authentication.auth,
        authentication.authkey,
        authentication.passkey,
    ):
        assert credential not in messages[0]
