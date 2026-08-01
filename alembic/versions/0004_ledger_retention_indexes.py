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

# Names match main (#492). Columns match #478 inventory.
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


def _mysql_type_is_unbounded_text(column_type) -> bool:
    """True when MySQL cannot use the column in an index without a prefix length."""

    if isinstance(column_type, sa.Text):
        return True
    type_name = type(column_type).__name__.upper()
    if type_name in {"TEXT", "TINYTEXT", "MEDIUMTEXT", "LONGTEXT"}:
        return True
    # Dialect-reflected types sometimes only expose a string form.
    return "TEXT" in str(column_type).upper() and "VARCHAR" not in str(column_type).upper()


def _ensure_pipeline_journal_updated_date_is_indexable(bind, inspector) -> None:
    """MySQL rejects indexes on bare TEXT; bound updated_date to VARCHAR(255).

    Fresh installs get MYSQL_KEY_TEXT via metadata. Pre-0004 MySQL DBs may still
    have TEXT, which would fail CREATE INDEX without a prefix length (ERROR 1170).
    SQLite/PostgreSQL accept TEXT keys and need no rewrite.
    """

    if bind.dialect.name != "mysql":
        return
    if "pipeline_journal" not in set(inspector.get_table_names()):
        return
    columns = {column["name"]: column for column in inspector.get_columns("pipeline_journal")}
    column = columns.get("updated_date")
    if column is None or not _mysql_type_is_unbounded_text(column["type"]):
        return
    op.alter_column(
        "pipeline_journal",
        "updated_date",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
        nullable=False,
    )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _ensure_pipeline_journal_updated_date_is_indexable(bind, inspector)
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for index_name, table_name, columns in _RETENTION_INDEXES:
        if table_name not in existing_tables:
            continue
        indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in indexes:
            continue
        op.create_index(index_name, table_name, columns)
        inspector = sa.inspect(bind)


def downgrade():
    for index_name, table_name, _columns in reversed(_RETENTION_INDEXES):
        op.drop_index(index_name, table_name=table_name)
