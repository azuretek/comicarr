#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Shared acquisition contracts for search, refresh, downloads, and repair."""

from comicarr.app.acquisition.models import (
    AcquisitionIntent,
    DispatchState,
    Fulfillment,
    ItemOutcome,
    RouteReadiness,
    RunState,
    StateProjection,
)
from comicarr.app.acquisition.policy import EligibilityDecision, EligibilityInput, evaluate_eligibility

__all__ = [
    "AcquisitionIntent",
    "DispatchState",
    "EligibilityDecision",
    "EligibilityInput",
    "Fulfillment",
    "ItemOutcome",
    "RouteReadiness",
    "RunState",
    "StateProjection",
    "evaluate_eligibility",
]
