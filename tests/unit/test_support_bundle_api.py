#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""HTTP adapter tests for POST /api/system/support-bundle."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from comicarr.app.core.context import AppContext, get_context
from comicarr.app.core.security import require_api_key, require_session
from comicarr.app.system import support_bundle as sb
from comicarr.app.system.router import router


def _app(ctx: AppContext) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_context] = lambda: ctx
    app.dependency_overrides[require_session] = lambda: "operator"
    return app


@pytest.fixture
def ctx(tmp_path):
    return AppContext(
        prog_dir=str(tmp_path),
        data_dir=str(tmp_path / "data"),
        db_file=str(tmp_path / "data" / "comicarr.db"),
        config=SimpleNamespace(),
        disposed=False,
    )


def test_success_headers_and_body(ctx):
    artifact = sb.SupportBundleArtifact(
        content=b"PK\x03\x04fake-zip-bytes-for-header-test",
        contract_version=1,
        filename="comicarr-support-bundle-v1.zip",
        status="complete",
    )
    app = _app(ctx)
    with patch.object(sb, "generate_support_bundle", return_value=artifact):
        with TestClient(app) as client:
            response = client.post(
                "/api/system/support-bundle",
                headers={"X-Requested-With": "ComicarrFrontend"},
            )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert response.headers["content-disposition"] == 'attachment; filename="comicarr-support-bundle-v1.zip"'
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-comicarr-support-bundle-contract"] == "1"
    assert response.headers["x-comicarr-support-bundle-status"] == "complete"
    assert "etag" not in {k.lower() for k in response.headers.keys()}
    assert "last-modified" not in {k.lower() for k in response.headers.keys()}
    assert response.content == artifact.content


def test_in_progress_conflict(ctx):
    app = _app(ctx)
    with patch.object(sb, "generate_support_bundle", side_effect=sb.SupportBundleInProgress()):
        with TestClient(app) as client:
            response = client.post(
                "/api/system/support-bundle",
                headers={"X-Requested-With": "ComicarrFrontend"},
            )
    assert response.status_code == 409
    assert response.headers.get("retry-after") == "2"
    body = response.json()
    assert body["code"] == "support_bundle_in_progress"
    assert body["retryable"] is True
    assert body["detail"].startswith("Another support bundle")


def test_unavailable(ctx):
    app = _app(ctx)
    with patch.object(sb, "generate_support_bundle", side_effect=sb.SupportBundleUnavailable()):
        with TestClient(app) as client:
            response = client.post(
                "/api/system/support-bundle",
                headers={"X-Requested-With": "ComicarrFrontend"},
            )
    assert response.status_code == 503
    assert response.json()["code"] == "support_bundle_unavailable"


def test_validation_failed(ctx):
    app = _app(ctx)
    with patch.object(sb, "generate_support_bundle", side_effect=sb.SupportBundleValidationFailed()):
        with TestClient(app) as client:
            response = client.post(
                "/api/system/support-bundle",
                headers={"X-Requested-With": "ComicarrFrontend"},
            )
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "support_bundle_validation_failed"
    assert body["retryable"] is False


def test_generation_failed(ctx):
    app = _app(ctx)
    with patch.object(sb, "generate_support_bundle", side_effect=sb.SupportBundleGenerationFailed()):
        with TestClient(app) as client:
            response = client.post(
                "/api/system/support-bundle",
                headers={"X-Requested-With": "ComicarrFrontend"},
            )
    assert response.status_code == 500
    assert response.json()["code"] == "support_bundle_generation_failed"


def test_requires_session_dependency():
    route = next(r for r in router.routes if getattr(r, "path", None) == "/api/system/support-bundle")
    assert route.methods == {"POST"}
    # Dependency is attached via dependencies= and/or signature.
    dependant = route.dependant
    callables = []
    for dep in dependant.dependencies:
        callables.append(dep.call)
    assert require_session in callables or any(
        getattr(d, "call", None) is require_session for d in dependant.dependencies
    )
    # Endpoint is synchronous.
    assert not inspect.iscoroutinefunction(route.endpoint)


def test_no_get_route_and_not_api_key_only():
    methods_by_path = {}
    for route in router.routes:
        path = getattr(route, "path", None)
        if path and "support-bundle" in path:
            methods_by_path.setdefault(path, set()).update(route.methods or set())
            # Must not be API-key only.
            for dep in route.dependant.dependencies:
                assert dep.call is not require_api_key
    assert methods_by_path == {"/api/system/support-bundle": {"POST"}}


def test_unauthenticated_without_override(ctx):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_context] = lambda: ctx
    # Leave require_session real — missing cookie should 401.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/system/support-bundle",
            headers={"X-Requested-With": "ComicarrFrontend"},
        )
    assert response.status_code in {401, 403}
