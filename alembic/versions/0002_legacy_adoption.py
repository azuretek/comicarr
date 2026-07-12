#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Adopt a fingerprinted pre-Alembic Comicarr database.

Revision ID: 0002_legacy_adoption
Revises: 0001_baseline
"""

from alembic import op
from comicarr.app.core.schema import apply_legacy_schema_compatibility

revision = "0002_legacy_adoption"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    apply_legacy_schema_compatibility(op.get_bind())


def downgrade():
    raise RuntimeError("Comicarr legacy adoption is not destructively downgradable")
