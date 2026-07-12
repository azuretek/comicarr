#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Contract tests for the application-owned Alembic migration runner."""

import pytest
from sqlalchemy import Text, create_engine, inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from comicarr.app.core.schema import (
    DatabaseState,
    MigrationStateError,
    classify_database,
    current_revision,
    upgrade_database,
)
from comicarr.tables import comics, metadata


def test_classifier_identifies_a_fresh_database(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "fresh.db"))

    assert classify_database(engine) is DatabaseState.FRESH


def test_mysql_baseline_uses_varchar_for_defaulted_comic_classification_fields():
    ddl = str(CreateTable(comics).compile(dialect=mysql.dialect()))

    assert "`ContentType` VARCHAR(16) DEFAULT 'comic'" in ddl
    assert "`ReadingDirection` VARCHAR(16) DEFAULT 'ltr'" in ddl


def test_mysql_baseline_uses_bounded_types_for_every_indexed_schema_key():
    for table in metadata.sorted_tables:
        key_columns = set(table.primary_key.columns.keys())
        for constraint in table.constraints:
            key_columns.update(column.name for column in constraint.columns)
        for index in table.indexes:
            key_columns.update(column.name for column in index.columns)

        for column_name in key_columns:
            mysql_type = table.c[column_name].type.dialect_impl(mysql.dialect())
            assert not isinstance(mysql_type, Text), "%s.%s remains TEXT in a MySQL key" % (table.name, column_name)


def test_classifier_identifies_a_known_unversioned_comicarr_database(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "legacy.db"))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO mylar_info(DatabaseVersion) VALUES (0)"))

    assert classify_database(engine) is DatabaseState.LEGACY


def test_classifier_identifies_a_versioned_database(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "versioned.db"))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("INSERT INTO alembic_version(version_num) VALUES ('0001_baseline')"))

    assert classify_database(engine) is DatabaseState.VERSIONED


def test_classifier_refuses_to_adopt_an_unknown_nonempty_database(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "unknown.db"))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE unrelated_data (id INTEGER PRIMARY KEY)"))

    with pytest.raises(MigrationStateError, match="not a recognized Comicarr database"):
        classify_database(engine)


def test_upgrade_database_builds_a_fresh_database_to_the_single_head(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "fresh-upgrade.db"))

    revision = upgrade_database(engine)

    assert revision == "0002_legacy_adoption"
    assert set(metadata.tables).issubset(set(inspect(engine).get_table_names()))


def test_upgrade_database_stamps_only_a_verified_legacy_database(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "legacy-upgrade.db"))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO mylar_info(DatabaseVersion) VALUES (0)"))

    assert upgrade_database(engine) == "0002_legacy_adoption"
    assert current_revision(engine) == "0002_legacy_adoption"


def test_upgrade_database_never_stamps_an_unknown_database(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "unknown-upgrade.db"))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE unrelated_data (id INTEGER PRIMARY KEY)"))

    with pytest.raises(MigrationStateError):
        upgrade_database(engine)

    assert "alembic_version" not in set(inspect(engine).get_table_names())


def test_legacy_adoption_restores_a_missing_safe_historical_column(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "legacy-column.db"))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO mylar_info(DatabaseVersion) VALUES (0)"))
        conn.execute(text("ALTER TABLE comics DROP COLUMN MetadataSource"))

    upgrade_database(engine)

    assert "MetadataSource" in {column["name"] for column in inspect(engine).get_columns("comics")}


def test_legacy_adoption_moves_a_known_readinglist_shape_to_storyarcs(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "readinglist.db"))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO mylar_info(DatabaseVersion) VALUES (0)"))
        conn.execute(text("CREATE TABLE readinglist AS SELECT * FROM storyarcs"))
        conn.execute(
            text(
                "INSERT INTO readinglist(StoryArcID, ComicName, IssueNumber, StoryArc, IssueArcID) "
                "VALUES ('arc-1', 'Saga', '1', 'The Arc', 'arc-issue-1')"
            )
        )
        conn.execute(text("DROP TABLE storyarcs"))

    upgrade_database(engine)

    assert "readinglist" not in set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        assert conn.execute(text("SELECT ComicName FROM storyarcs WHERE IssueArcID = 'arc-issue-1'")).scalar() == "Saga"
