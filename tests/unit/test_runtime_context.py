#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Runtime-context ownership invariants.

These tests deliberately exercise the process boundary rather than a copied
``AppContext`` fixture.  Queue, lock, scheduler, and DDL set identities are
the contract shared by worker, scheduler, and FastAPI code during the staged
legacy migration.
"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import comicarr
from comicarr.app.core.context import AppContext, get_context
from comicarr.app.core.runtime import RuntimeNotInitializedError, create_runtime, get_runtime

RUNTIME_GLOBAL_ALLOWLIST = {
    # These files are the first migrated system/acquisition ownership boundary.
    # Keep the list explicit so a new mutable module-global read/write cannot
    # creep back in while the larger legacy scheduler service drains later.
    "comicarr/app/system/router.py": set(),
    "comicarr/app/acquisition/maintenance.py": set(),
    "comicarr/weeklypullit.py": set(),
    "comicarr/app/ai/enrichment.py": set(),
    "comicarr/app/ai/parsing.py": set(),
    "comicarr/app/ai/pull_list.py": set(),
    "comicarr/app/ai/reconciliation.py": set(),
    "comicarr/app/ai/search_expansion.py": set(),
    "comicarr/app/ai/service.py": set(),
    "comicarr/app/ai/story_arcs.py": set(),
}


@pytest.fixture(autouse=True)
def _clear_runtime(monkeypatch):
    """Keep the process singleton isolated between factory tests."""
    from comicarr.app.core import runtime

    monkeypatch.setattr(runtime, "_runtime", None)
    yield
    monkeypatch.setattr(runtime, "_runtime", None)


@pytest.fixture
def _legacy_runtime_objects(monkeypatch):
    """Install distinct legacy objects that the factory must adopt by identity."""
    config = SimpleNamespace(SECURE_DIR=None, AI_BASE_URL=None, AI_API_KEY=None)
    scheduler = MagicMock(name="scheduler")
    ddl_queued = set()
    search_queue = MagicMock(name="search_queue")
    ddl_queue = MagicMock(name="ddl_queue")
    search_lock = MagicMock(name="search_lock")
    ddl_lock = MagicMock(name="ddl_lock")
    acquisition_resume_lock = MagicMock(name="acquisition_resume_lock")
    mass_add_pool = MagicMock(name="mass_add_pool")

    values = {
        "CONFIG": config,
        "PROG_DIR": "/runtime/program",
        "DATA_DIR": "/runtime/data",
        "DB_FILE": "/runtime/data/comicarr.db",
        "SCHED": scheduler,
        "SEARCH_QUEUE": search_queue,
        "DDL_QUEUE": ddl_queue,
        "SEARCHLOCK": search_lock,
        "DDL_LOCK": ddl_lock,
        "ACQUISITION_RESUME_LOCK": acquisition_resume_lock,
        "MASS_ADD": mass_add_pool,
        "DDL_QUEUED": ddl_queued,
        "PUBLISHER_IMPRINTS": {},
        "PROVIDER_BLOCKLIST": [],
        "DDL_STUCK_NOTIFIED": set(),
        "PACK_ISSUEIDS_DONT_QUEUE": {},
        "FORCE_STATUS": {},
        "PROVIDER_STATUS": {},
        "UPDATE_VALUE": {},
        "ACQUISITION_SCHEMA_READY": True,
        "ACQUISITION_SCHEMA_VERSION": 1,
        "ACQUISITION_SCHEMA_ERROR": None,
        "ACQUISITION_WORKERS_BLOCKED": False,
        "ACQUISITION_BLOCK_REASON": None,
    }
    for name, value in values.items():
        monkeypatch.setattr(comicarr, name, value, raising=False)

    return SimpleNamespace(
        scheduler=scheduler,
        ddl_queued=ddl_queued,
        search_queue=search_queue,
        ddl_queue=ddl_queue,
        search_lock=search_lock,
        ddl_lock=ddl_lock,
        acquisition_resume_lock=acquisition_resume_lock,
        mass_add_pool=mass_add_pool,
    )


def test_runtime_factory_is_single_shot_and_adopts_identity_sensitive_objects(_legacy_runtime_objects):
    """The bridge may project legacy aliases, but it must never snapshot them."""
    from comicarr.app.core import runtime

    with patch("comicarr.app.core.runtime.AppContext", wraps=AppContext) as context_type:
        first = create_runtime()
        second = create_runtime()

    assert first is second
    assert context_type.call_count == 1
    assert first.scheduler is _legacy_runtime_objects.scheduler
    assert first.search_queue is _legacy_runtime_objects.search_queue
    assert first.ddl_queue is _legacy_runtime_objects.ddl_queue
    assert first.search_lock is _legacy_runtime_objects.search_lock
    assert first.ddl_lock is _legacy_runtime_objects.ddl_lock
    assert first.acquisition_resume_lock is _legacy_runtime_objects.acquisition_resume_lock
    assert first.mass_add_pool is _legacy_runtime_objects.mass_add_pool
    assert first.ddl_queued is _legacy_runtime_objects.ddl_queued
    assert first.acquisition_schema_ready is True
    assert first.acquisition_workers_blocked is False

    first.ddl_queued.add("issue-42")
    assert "issue-42" in comicarr.DDL_QUEUED
    assert runtime.get_runtime() is first


def test_runtime_factory_owns_and_projects_one_ai_client_bundle(_legacy_runtime_objects):
    """AI aliases are a compatibility view of the factory-created bundle."""
    config = comicarr.CONFIG
    config.AI_BASE_URL = "https://ai.example.test/v1"
    config.AI_API_KEY = "test-key"
    sync_client = MagicMock(name="sync_ai_client")
    async_client = MagicMock(name="async_ai_client")

    with patch("comicarr.app.ai.client.create_ai_clients", return_value=(sync_client, async_client)) as create_clients:
        ctx = create_runtime()
        assert create_runtime() is ctx

    create_clients.assert_called_once_with(config)
    assert ctx.ai_client is sync_client
    assert ctx.ai_async_client is async_client
    assert comicarr.AI_CLIENT is sync_client
    assert comicarr.AI_ASYNC_CLIENT is async_client
    assert comicarr.AI_CIRCUIT_BREAKER is ctx.ai_circuit_breaker
    assert comicarr.AI_RATE_LIMITER is ctx.ai_rate_limiter


def test_runtime_access_fails_closed_before_initialization():
    """Request code must not silently receive a partial or replacement context."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    with pytest.raises(RuntimeNotInitializedError, match="not initialized"):
        get_runtime()
    with pytest.raises(RuntimeNotInitializedError, match="not initialized"):
        get_context(request)


def test_worker_bootstrap_refuses_to_start_before_a_runtime_exists(monkeypatch):
    """A missing context is rejected before scheduler/worker bootstrap can run."""
    scheduler = MagicMock(name="scheduler")
    monkeypatch.setattr(comicarr, "SCHED", scheduler)
    monkeypatch.setattr(comicarr, "_INITIALIZED", True)

    with pytest.raises(RuntimeNotInitializedError, match="before an active runtime"):
        comicarr.start(None)

    scheduler.add_job.assert_not_called()
    scheduler.start.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_attaches_the_factory_runtime_instance(_legacy_runtime_objects, monkeypatch):
    """FastAPI receives the worker-created runtime rather than building a snapshot."""
    from comicarr.app.acquisition.maintenance import RuntimeGateStatus
    from comicarr.app.main import lifespan

    ctx = create_runtime()
    app = SimpleNamespace(state=SimpleNamespace())
    gate = RuntimeGateStatus(
        blocked=False,
        reason=None,
        schema_ready=True,
        maintenance_active=False,
        epoch=0,
    )
    monkeypatch.setattr("comicarr.app.acquisition.maintenance.refresh_runtime_state", lambda *_args: gate)
    monkeypatch.setattr("comicarr.db.get_engine", lambda: None)

    cm = lifespan(app)
    await cm.__aenter__()
    try:
        assert app.state.ctx is ctx
        assert app.state.ctx.ddl_queued is comicarr.DDL_QUEUED
        assert get_runtime() is ctx
    finally:
        await cm.__aexit__(None, None, None)

    with pytest.raises(RuntimeNotInitializedError, match="disposed"):
        get_context(SimpleNamespace(app=app))


def test_migrated_runtime_boundaries_have_no_unallowlisted_legacy_globals():
    """Prevent a new direct mutable-global dependency in the first ownership wave."""
    project_root = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"\bcomicarr\.([A-Z][A-Z0-9_]+)\b")

    for relative_path, allowed in RUNTIME_GLOBAL_ALLOWLIST.items():
        source = (project_root / relative_path).read_text(encoding="utf-8")
        found = set(pattern.findall(source))
        assert found <= allowed, "%s added direct legacy runtime access: %s" % (
            relative_path,
            sorted(found - allowed),
        )


def test_fastapi_lifespan_has_no_legacy_snapshot_builder():
    """A future lifecycle change must attach the runtime rather than copy it."""
    from comicarr.app import main

    assert not hasattr(main, "_build_context_from_globals")
    assert "_build_context_from_globals" not in Path(main.__file__).read_text(encoding="utf-8")
