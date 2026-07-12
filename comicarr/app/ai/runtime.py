#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Canonical runtime accessor for AI consumers.

AI entry points can be reached by legacy background work before FastAPI is
serving. They therefore treat an unavailable/disposed runtime as an
unconfigured AI service, while every active consumer reads the one canonical
``AppContext`` bundle created by the process runtime factory.
"""

from comicarr.app.core.runtime import get_runtime_if_initialized


def get_ai_runtime():
    """Return the active canonical runtime, or ``None`` before/after lifecycle."""
    ctx = get_runtime_if_initialized()
    if ctx is None or ctx.disposed:
        return None
    return ctx
