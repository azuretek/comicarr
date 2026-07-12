#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Tests for the structured AI response adapter."""

from types import SimpleNamespace

import pytest

from comicarr.app.ai.structured import request_structured


class _Schema:
    @classmethod
    def model_json_schema(cls):
        return {"type": "object"}

    @classmethod
    def model_validate_json(cls, _raw):
        raise ValueError("invalid JSON")

    @classmethod
    def model_validate(cls, _data):
        raise AssertionError("fallback validation should not run for this case")


def test_parse_failure_preserves_value_error_contract():
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_kwargs: response)))

    with pytest.raises(ValueError, match="Failed to parse structured response from LLM: Expecting value"):
        request_structured(client, "model", "system", "user", _Schema)
