#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Architecture boundary tests for FastAPI-domain database access."""

from pathlib import Path


def test_fastapi_domains_do_not_use_the_legacy_db_connection_shim():
    app_root = Path(__file__).parents[2] / "comicarr" / "app"
    offenders = [path for path in app_root.rglob("*.py") if "DBConnection(" in path.read_text()]

    assert offenders == []
