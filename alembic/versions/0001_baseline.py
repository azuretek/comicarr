#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Create the reviewed Comicarr schema baseline for fresh databases.

Revision ID: 0001_baseline
Revises:
"""

from alembic import op
from comicarr.tables import metadata

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Comicarr's initial schema baseline is not destructively downgradable")
