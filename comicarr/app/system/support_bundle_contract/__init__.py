#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Immutable Support bundle contract assets loaded via importlib.resources."""

from importlib import resources


def contract_files(version: int = 1):
    """Return a Traversable for the contract package of the given version."""
    if version != 1:
        raise ValueError("unsupported support bundle contract version")
    return resources.files(__name__).joinpath(f"v{version}")


def read_contract_bytes(name: str, version: int = 1) -> bytes:
    """Read one packaged contract asset as bytes."""
    path = contract_files(version).joinpath(name)
    return path.read_bytes()
