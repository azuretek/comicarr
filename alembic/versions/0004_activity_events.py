#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Add activity_events narrative table and required Activity Center indexes.

Revision ID: 0004_activity_events
Revises: 0003_library_chat
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_activity_events"
down_revision = "0003_library_chat"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "activity_events" not in existing_tables:
        op.create_table(
            "activity_events",
            sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.String(length=40), nullable=False),
            sa.Column("activity", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("subject_type", sa.String(length=32), nullable=False),
            sa.Column("subject_id", sa.String(length=255), nullable=False),
            sa.Column("subject_label", sa.Text(), nullable=False),
            sa.Column("reason_code", sa.String(length=64)),
            sa.Column("reason_detail", sa.Text()),
            sa.Column("provider", sa.String(length=64)),
            sa.Column("run_id", sa.String(length=64)),
            sa.Column("release_key", sa.String(length=255)),
            sa.Column("parent_series_id", sa.String(length=255)),
            sa.Column("scope_type", sa.String(length=32)),
            sa.Column("scope_id", sa.String(length=255)),
        )

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("activity_events")}
    if "activity_events_created_at" not in indexes:
        op.create_index(
            "activity_events_created_at",
            "activity_events",
            ["created_at"],
        )
    if "activity_events_parent_series_id" not in indexes:
        op.create_index(
            "activity_events_parent_series_id",
            "activity_events",
            ["parent_series_id"],
        )
    if "activity_events_subject" not in indexes:
        op.create_index(
            "activity_events_subject",
            "activity_events",
            ["subject_type", "subject_id"],
        )

    # Band / open-stage counts filter pipeline_journal by stage. Fresh installs
    # get this from metadata; older upgraded DBs may lack it until this revision.
    if "pipeline_journal" in existing_tables:
        journal_indexes = {index["name"] for index in inspector.get_indexes("pipeline_journal")}
        if "pipeline_journal_stage" not in journal_indexes:
            op.create_index(
                "pipeline_journal_stage",
                "pipeline_journal",
                ["stage"],
            )


def downgrade():
    # pipeline_journal_stage may have existed before this revision (metadata /
    # legacy adoption); only reverse the activity_events objects this revision
    # owns.
    op.drop_index("activity_events_subject", table_name="activity_events")
    op.drop_index("activity_events_parent_series_id", table_name="activity_events")
    op.drop_index("activity_events_created_at", table_name="activity_events")
    op.drop_table("activity_events")
