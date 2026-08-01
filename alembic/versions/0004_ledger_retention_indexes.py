#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Add ledger retention eligibility indexes.

Revision ID: 0004_ledger_retention_indexes
Revises: 0003_library_chat
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_ledger_retention_indexes"
down_revision = "0003_library_chat"
branch_labels = None
depends_on = None

_RETENTION_INDEXES = (
    (
        "acquisition_run_items_state_completed",
        "acquisition_run_items",
        ["state", "completed_at"],
    ),
    (
        "acquisition_runs_state_completed",
        "acquisition_runs",
        ["completion_state", "completed_at"],
    ),
    (
        "pipeline_journal_stage_updated",
        "pipeline_journal",
        ["stage", "updated_date"],
    ),
    (
        "acquisition_maintenance_events_created",
        "acquisition_maintenance_events",
        ["created_at"],
    ),
)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for index_name, table_name, columns in _RETENTION_INDEXES:
        if table_name not in existing_tables:
            continue
        indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in indexes:
            continue
        op.create_index(index_name, table_name, columns)


def downgrade():
    for index_name, table_name, _columns in reversed(_RETENTION_INDEXES):
        op.drop_index(index_name, table_name=table_name)
