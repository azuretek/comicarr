# Copyright (C) 2012–2024 Mylar3 contributors
# Copyright (C) 2025–2026 Comicarr contributors
#
# This file is part of Comicarr.
# Originally based on Mylar3 (https://github.com/mylar3/mylar3).
#
# Comicarr is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

import comicarr
from comicarr import db
from comicarr.tables import metadata

EXPECTED_CONSTRAINTS = {
    "issues": (["IssueID"], "uq_issues_issueid"),
    "annuals": (["IssueID"], "uq_annuals_issueid"),
    "storyarcs": (["IssueArcID"], "uq_storyarcs_issuearcid"),
    "readlist": (["IssueID"], "uq_readlist_issueid"),
    "failed": (["ID", "Provider", "NZBName"], "uq_failed_id_provider_nzbname"),
    "upcoming": (["ComicID", "IssueNumber"], "uq_upcoming_comicid_issuenum"),
    "nzblog": (["IssueID", "PROVIDER"], "uq_nzblog_issueid_provider"),
    "importresults": (["impID"], "uq_importresults_impid"),
    "jobhistory": (["JobName"], "uq_jobhistory_jobname"),
    "snatched": (["IssueID", "Status", "Provider"], "uq_snatched_issue_status_provider"),
    "oneoffhistory": (["ComicID", "IssueID"], "uq_oneoffhistory_comicid_issueid"),
    "weekly": (["ComicID", "IssueID"], "uq_weekly_comicid_issueid"),
}


@pytest.fixture
def legacy_engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(comicarr, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(comicarr, "CONFIG", SimpleNamespace(BACKUP_RETENTION=7))
    monkeypatch.setattr(comicarr, "LOG_LEVEL", 0, raising=False)
    yield engine
    engine.dispose()
    monkeypatch.setattr(db, "_engine", None)


def _successful_backup(_source_path, _dest_dir, _retention):
    return True


def _run_migration(engine, backup_func=_successful_backup):
    comicarr._migrate_unique_constraints(engine, backup_func=backup_func)


def _create_legacy_table(conn, table_name, columns):
    preparer = conn.dialect.identifier_preparer
    table_sql = preparer.quote_identifier(table_name)
    columns_sql = ", ".join(f"{preparer.quote_identifier(column)} TEXT" for column in columns)
    conn.execute(text(f"CREATE TABLE {table_sql} ({columns_sql})"))


def _unique_column_sets(engine, table_name):
    inspector = inspect(engine)
    constraints = {
        tuple(sorted(constraint.get("column_names") or []))
        for constraint in inspector.get_unique_constraints(table_name)
    }
    indexes = {
        tuple(sorted(index.get("column_names") or []))
        for index in inspector.get_indexes(table_name)
        if index.get("unique")
    }
    return constraints | indexes


def test_legacy_sqlite_migration_repairs_real_single_and_composite_upserts(legacy_engine):
    with legacy_engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName", "Status"])
        _create_legacy_table(conn, "failed", ["ID", "Provider", "NZBName", "Status"])
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name, :status)"),
            [
                {"id": "issue-1", "name": "old", "status": "Wanted"},
                {"id": "issue-1", "name": "newest", "status": "Snatched"},
                {"id": None, "name": "null-a", "status": "Wanted"},
                {"id": None, "name": "null-b", "status": "Wanted"},
                {"id": "", "name": "empty-a", "status": "Wanted"},
                {"id": "", "name": "empty-b", "status": "Wanted"},
            ],
        )
        conn.execute(
            text("INSERT INTO failed VALUES (:id, :provider, :name, :status)"),
            [
                {"id": "failure-1", "provider": "provider", "name": "release", "status": "old"},
                {"id": "failure-1", "provider": "provider", "name": "release", "status": "newest"},
                {"id": "", "provider": "provider", "name": "release", "status": "empty-a"},
                {"id": "", "provider": "provider", "name": "release", "status": "empty-b"},
            ],
        )

    with pytest.raises(OperationalError, match="ON CONFLICT clause does not match"):
        db.upsert("issues", {"ComicName": "before", "Status": "Wanted"}, {"IssueID": "issue-1"})

    _run_migration(legacy_engine)

    with legacy_engine.connect() as conn:
        issue_rows = conn.execute(text("SELECT ComicName FROM issues WHERE IssueID = 'issue-1'")).scalars().all()
        failed_rows = (
            conn.execute(
                text(
                    "SELECT Status FROM failed WHERE ID = 'failure-1' AND Provider = 'provider' AND NZBName = 'release'"
                )
            )
            .scalars()
            .all()
        )
        assert issue_rows == ["newest"]
        assert failed_rows == ["newest"]
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID IS NULL")) == 2
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = ''")) == 2
        assert conn.scalar(text("SELECT COUNT(*) FROM failed WHERE ID = ''")) == 2

    db.upsert("issues", {"ComicName": "updated", "Status": "Downloaded"}, {"IssueID": "issue-1"})
    db.upsert(
        "failed",
        {"Status": "Retrying"},
        {"ID": "failure-1", "Provider": "provider", "NZBName": "release"},
    )
    db.upsert("issues", {"ComicName": "empty-upsert", "Status": "Wanted"}, {"IssueID": ""})
    db.upsert("issues", {"ComicName": "null-upsert", "Status": "Wanted"}, {"IssueID": None})

    with legacy_engine.connect() as conn:
        assert conn.scalar(text("SELECT ComicName FROM issues WHERE IssueID = 'issue-1'")) == "updated"
        assert (
            conn.scalar(
                text(
                    "SELECT Status FROM failed WHERE ID = 'failure-1' AND Provider = 'provider' AND NZBName = 'release'"
                )
            )
            == "Retrying"
        )
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = ''")) == 3
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID IS NULL")) == 3

    with pytest.raises(IntegrityError):
        with legacy_engine.begin() as conn:
            conn.execute(text("INSERT INTO issues VALUES ('issue-1', 'duplicate', 'Wanted')"))

    with legacy_engine.begin() as conn:
        conn.execute(text("INSERT INTO issues VALUES ('', 'empty-c', 'Wanted')"))


def test_sqlite_migration_covers_every_declared_legacy_upsert_table_and_is_idempotent(legacy_engine):
    assert comicarr._UPSERT_UNIQUE_CONSTRAINTS == EXPECTED_CONSTRAINTS
    with legacy_engine.begin() as conn:
        for table_name, (key_columns, _constraint_name) in EXPECTED_CONSTRAINTS.items():
            _create_legacy_table(conn, table_name, key_columns)

    _run_migration(legacy_engine)
    _run_migration(legacy_engine)

    inspector = inspect(legacy_engine)
    for table_name, (key_columns, constraint_name) in EXPECTED_CONSTRAINTS.items():
        assert tuple(sorted(key_columns)) in _unique_column_sets(legacy_engine, table_name)
        matching_indexes = [
            index
            for index in inspector.get_indexes(table_name)
            if index.get("unique") and tuple(sorted(index.get("column_names") or [])) == tuple(sorted(key_columns))
        ]
        assert [index["name"] for index in matching_indexes] == [constraint_name]


def test_sqlite_migration_recognizes_existing_table_unique_constraint(legacy_engine):
    with legacy_engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE issues (IssueID TEXT, ComicName TEXT, CONSTRAINT legacy_issues_unique UNIQUE (IssueID))")
        )

    _run_migration(legacy_engine)

    inspector = inspect(legacy_engine)
    assert tuple(["IssueID"]) in _unique_column_sets(legacy_engine, "issues")
    assert not any(index["name"] == "uq_issues_issueid" for index in inspector.get_indexes("issues"))


def test_sqlite_upsert_remains_compatible_with_new_full_unique_constraints(legacy_engine):
    metadata.create_all(legacy_engine)

    db.upsert("issues", {"ComicName": "first", "Status": "Wanted"}, {"IssueID": "issue-1"})
    db.upsert("issues", {"ComicName": "updated", "Status": "Downloaded"}, {"IssueID": "issue-1"})
    db.upsert("issues", {"ComicName": "empty-first", "Status": "Wanted"}, {"IssueID": ""})
    db.upsert("issues", {"ComicName": "empty-updated", "Status": "Downloaded"}, {"IssueID": ""})
    db.upsert("issues", {"ComicName": "null-first", "Status": "Wanted"}, {"IssueID": None})
    db.upsert("issues", {"ComicName": "null-second", "Status": "Wanted"}, {"IssueID": None})

    with legacy_engine.connect() as conn:
        assert conn.scalar(text("SELECT ComicName FROM issues WHERE IssueID = 'issue-1'")) == "updated"
        assert conn.scalar(text("SELECT ComicName FROM issues WHERE IssueID = ''")) == "empty-updated"
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = ''")) == 1
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID IS NULL")) == 2


@pytest.mark.parametrize(
    "legacy_predicate",
    [
        "IssueID IS NOT NULL AND IssueID != '' AND ComicName IS NOT NULL",
        "IssueID != '' AND IssueID IS NOT NULL",
    ],
)
def test_sqlite_migration_does_not_mistake_incompatible_partial_index_for_enforcement(legacy_engine, legacy_predicate):
    with legacy_engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName", "Status"])
        conn.execute(
            text(f"CREATE UNIQUE INDEX legacy_narrow_issues_index ON issues (IssueID) WHERE {legacy_predicate}")
        )

    with pytest.raises(OperationalError, match="ON CONFLICT clause does not match"):
        db.upsert("issues", {"ComicName": "before", "Status": "Wanted"}, {"IssueID": "issue-1"})

    _run_migration(legacy_engine)

    indexes = inspect(legacy_engine).get_indexes("issues")
    assert any(index["name"] == "uq_issues_issueid" and index.get("unique") for index in indexes)
    db.upsert("issues", {"ComicName": "after", "Status": "Downloaded"}, {"IssueID": "issue-1"})
    with legacy_engine.connect() as conn:
        assert conn.scalar(text("SELECT ComicName FROM issues WHERE IssueID = 'issue-1'")) == "after"


@pytest.mark.parametrize("occupied_index_name", ["uq_issues_issueid", "UQ_ISSUES_ISSUEID"])
def test_sqlite_migration_uses_alternate_name_when_canonical_index_name_is_taken(
    legacy_engine, monkeypatch, occupied_index_name
):
    monkeypatch.setattr(legacy_engine.dialect, "max_identifier_length", 30)
    with legacy_engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName"])
        quoted_index_name = conn.dialect.identifier_preparer.quote_identifier(occupied_index_name)
        conn.execute(text(f"CREATE INDEX {quoted_index_name} ON issues (ComicName)"))
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name)"),
            [
                {"id": "issue-1", "name": "old"},
                {"id": "issue-1", "name": "newest"},
            ],
        )

    _run_migration(legacy_engine)

    with legacy_engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'")) == 1
    unique_indexes = [index for index in inspect(legacy_engine).get_indexes("issues") if index.get("unique")]
    assert len(unique_indexes) == 1
    assert unique_indexes[0]["name"] == comicarr._bounded_alternate_index_name(
        legacy_engine,
        "uq_issues_issueid",
        "issues",
        ["IssueID"],
        0,
    )
    assert len(unique_indexes[0]["name"]) <= legacy_engine.dialect.max_identifier_length

    db.upsert("issues", {"ComicName": "updated"}, {"IssueID": "issue-1"})
    with legacy_engine.connect() as conn:
        assert conn.scalar(text("SELECT ComicName FROM issues WHERE IssueID = 'issue-1'")) == "updated"


def test_sqlite_migration_rolls_back_deduplication_on_forced_ddl_failure(legacy_engine):
    with legacy_engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName"])
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name)"),
            [
                {"id": "issue-1", "name": "old"},
                {"id": "issue-1", "name": "newest"},
            ],
        )

    def fail_index_creation(_conn, _cursor, statement, parameters, _context, _executemany):
        if statement.lstrip().startswith("CREATE UNIQUE INDEX"):
            raise OperationalError(statement, parameters, sqlite3.OperationalError("injected failure"))

    event.listen(legacy_engine, "before_cursor_execute", fail_index_creation)
    try:
        _run_migration(legacy_engine)
    finally:
        event.remove(legacy_engine, "before_cursor_execute", fail_index_creation)

    with legacy_engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'")) == 2
    assert tuple(["IssueID"]) not in _unique_column_sets(legacy_engine, "issues")


def test_sqlite_migration_backs_up_before_delete_and_only_once(legacy_engine):
    with legacy_engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName"])
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name)"),
            [
                {"id": "issue-1", "name": "old"},
                {"id": "issue-1", "name": "newest"},
            ],
        )

    backup_calls = []

    def backup_before_delete(source_path, dest_dir, retention):
        with legacy_engine.connect() as conn:
            assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'")) == 2
        backup_calls.append((source_path, dest_dir, retention))
        return True

    with patch.object(comicarr.maintenance, "auto_backup_db", side_effect=backup_before_delete) as backup:
        comicarr._migrate_unique_constraints(legacy_engine)
        comicarr._migrate_unique_constraints(legacy_engine)

    assert backup_calls == [
        (
            os.path.abspath(legacy_engine.url.database),
            os.path.join(comicarr.DATA_DIR, "backups", "migrations"),
            7,
        )
    ]
    backup.assert_called_once_with(*backup_calls[0])


def test_migration_backup_survives_same_second_normal_backup(legacy_engine):
    with legacy_engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName"])
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name)"),
            [
                {"id": "issue-1", "name": "old"},
                {"id": "issue-1", "name": "newest"},
            ],
        )

    fixed_timestamp = "20260710_010203"
    source_path = os.path.abspath(legacy_engine.url.database)
    normal_backup_dir = Path(comicarr.DATA_DIR) / "backups"
    migration_backup_dir = normal_backup_dir / "migrations"
    with patch.object(comicarr.maintenance.time, "strftime", return_value=fixed_timestamp):
        _run_migration(legacy_engine, comicarr.maintenance.auto_backup_db)
        assert comicarr.maintenance.auto_backup_db(source_path, str(normal_backup_dir), 7)

    migration_backup = migration_backup_dir / f"comicarr.db.{fixed_timestamp}.bak"
    normal_backup = normal_backup_dir / f"comicarr.db.{fixed_timestamp}.bak"
    assert migration_backup != normal_backup
    assert migration_backup.is_file()
    assert normal_backup.is_file()

    with sqlite3.connect(migration_backup) as conn:
        assert conn.execute("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'").fetchone()[0] == 2
    with sqlite3.connect(normal_backup) as conn:
        assert conn.execute("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'").fetchone()[0] == 1


def test_sqlite_migration_backup_failure_prevents_all_changes(legacy_engine):
    with legacy_engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName"])
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name)"),
            [
                {"id": "issue-1", "name": "old"},
                {"id": "issue-1", "name": "newest"},
            ],
        )

    with pytest.raises(RuntimeError, match="backup"):
        _run_migration(legacy_engine, lambda *_args: False)

    with legacy_engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'")) == 2
    assert tuple(["IssueID"]) not in _unique_column_sets(legacy_engine, "issues")


def test_sqlite_in_memory_migration_does_not_attempt_durable_backup(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "_engine", engine)
    with engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName"])
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name)"),
            [
                {"id": "issue-1", "name": "old"},
                {"id": "issue-1", "name": "newest"},
            ],
        )

    comicarr._migrate_unique_constraints(engine)

    with engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'")) == 1
    engine.dispose()


def test_sqlite_named_memory_uri_migration_does_not_attempt_filesystem_backup(monkeypatch):
    engine = create_engine("sqlite:///file:comicarr_unique_migration?mode=memory&cache=shared&uri=true")
    monkeypatch.setattr(db, "_engine", engine)
    with engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName"])
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name)"),
            [
                {"id": "issue-1", "name": "old"},
                {"id": "issue-1", "name": "newest"},
            ],
        )

    with patch.object(comicarr.maintenance, "auto_backup_db", return_value=True) as backup:
        comicarr._migrate_unique_constraints(engine)

    backup.assert_not_called()
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'")) == 1
    engine.dispose()


@pytest.mark.parametrize(
    ("database_url", "database_name"),
    [
        ("sqlite:///foo.db?mode=memory", "foo.db"),
        ("sqlite:///file::memory:", "file::memory:"),
        ("sqlite:///foo.db?mode=memory&uri=true", "foo.db?mode=memory"),
    ],
)
def test_sqlite_memory_like_paths_without_uri_mode_are_backed_up(tmp_path, monkeypatch, database_url, database_name):
    monkeypatch.chdir(tmp_path)
    engine = create_engine(database_url)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(comicarr, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(comicarr, "CONFIG", SimpleNamespace(BACKUP_RETENTION=7))
    with engine.begin() as conn:
        _create_legacy_table(conn, "issues", ["IssueID", "ComicName"])
        conn.execute(
            text("INSERT INTO issues VALUES (:id, :name)"),
            [
                {"id": "issue-1", "name": "old"},
                {"id": "issue-1", "name": "newest"},
            ],
        )

    backup = MagicMock(return_value=True)
    comicarr._migrate_unique_constraints(engine, backup_func=backup)

    backup.assert_called_once_with(
        str(tmp_path / database_name),
        str(tmp_path / "backups" / "migrations"),
        7,
    )
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM issues WHERE IssueID = 'issue-1'")) == 1
    engine.dispose()


@pytest.mark.parametrize(
    ("dialect_name", "dialect_options", "filter_definition"),
    [
        ("postgresql", {"postgresql_where": "IssueID IS NOT NULL"}, None),
        ("other", {}, "IssueID IS NOT NULL"),
    ],
)
def test_non_sqlite_partial_unique_indexes_are_not_full_enforcement(dialect_name, dialect_options, filter_definition):
    engine = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
    inspector = MagicMock()
    inspector.get_unique_constraints.return_value = []
    inspector.get_indexes.return_value = [
        {
            "name": "partial_issues",
            "column_names": ["IssueID"],
            "unique": True,
            "dialect_options": dialect_options,
            "filter_definition": filter_definition,
        }
    ]

    with patch.object(comicarr, "inspect", return_value=inspector):
        assert not comicarr._has_unique_enforcement(engine, "issues", ["IssueID"])


def test_non_sqlite_full_unique_index_is_enforcement():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    inspector = MagicMock()
    inspector.get_unique_constraints.return_value = []
    inspector.get_indexes.return_value = [
        {
            "name": "full_issues",
            "column_names": ["IssueID"],
            "unique": True,
            "dialect_options": {"postgresql_where": None},
        }
    ]

    with patch.object(comicarr, "inspect", return_value=inspector):
        assert comicarr._has_unique_enforcement(engine, "issues", ["IssueID"])
