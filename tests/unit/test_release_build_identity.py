#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT_DIR / "Dockerfile"
RELEASE_WORKFLOW = ROOT_DIR / ".github" / "workflows" / "release.yml"


def test_runtime_image_exports_build_arguments_as_runtime_metadata():
    runtime_stage = DOCKERFILE.read_text(encoding="utf-8").split("FROM python:3.12-slim AS runtime", maxsplit=1)[1]

    assert "ARG COMICARR_BUILD_ID" in runtime_stage
    assert "ARG COMICARR_BUILD_COMMIT" in runtime_stage
    assert "COMICARR_BUILD_ID=${COMICARR_BUILD_ID}" in runtime_stage
    assert "COMICARR_BUILD_COMMIT=${COMICARR_BUILD_COMMIT}" in runtime_stage


def test_release_workflow_passes_release_identity_to_docker_build():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "build-args: |" in workflow
    assert "COMICARR_BUILD_ID=${{ needs.changesets.outputs.tag_name }}" in workflow
    assert "COMICARR_BUILD_COMMIT=${{ github.sha }}" in workflow
