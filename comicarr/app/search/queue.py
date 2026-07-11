#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Fair in-memory scheduling for durable search commands."""

from __future__ import annotations

import queue
from collections import deque
from typing import Any

INTERACTIVE = "interactive"
ROUTINE = "routine"
RECOVERY = "recovery"
CONTROL = "control"
_PRIORITIES = (INTERACTIVE, ROUTINE, RECOVERY, CONTROL)


class FairSearchQueue(queue.Queue):
    """Favor operator work without indefinitely starving durable recovery."""

    def __init__(self, maxsize: int = 0, *, interactive_burst: int = 3):
        self.interactive_burst = max(1, int(interactive_burst))
        super().__init__(maxsize=maxsize)

    def _init(self, _maxsize: int) -> None:
        self.queue = {priority: deque() for priority in _PRIORITIES}
        self._interactive_streak = 0
        self._non_recovery_streak = 0

    def _priority(self, item: Any) -> str:
        if item == "exit":
            return CONTROL
        if isinstance(item, dict):
            value = str(item.get("queue_priority") or ROUTINE).strip().lower()
            if value in {INTERACTIVE, ROUTINE, RECOVERY}:
                return value
        return ROUTINE

    def _qsize(self) -> int:
        return sum(len(items) for items in self.queue.values())

    def _put(self, item: Any) -> None:
        self.queue[self._priority(item)].append(item)

    def _get(self) -> Any:
        if self.queue[CONTROL]:
            return self.queue[CONTROL].popleft()

        has_background = bool(self.queue[ROUTINE] or self.queue[RECOVERY])
        if self.queue[RECOVERY] and self._non_recovery_streak >= self.interactive_burst:
            self._interactive_streak = 0
            self._non_recovery_streak = 0
            return self.queue[RECOVERY].popleft()
        if self.queue[INTERACTIVE] and (self._interactive_streak < self.interactive_burst or not has_background):
            self._interactive_streak += 1
            self._non_recovery_streak += 1
            return self.queue[INTERACTIVE].popleft()
        for priority in (ROUTINE, RECOVERY, INTERACTIVE):
            if self.queue[priority]:
                self._interactive_streak = 0
                if priority == RECOVERY:
                    self._non_recovery_streak = 0
                else:
                    self._non_recovery_streak += 1
                return self.queue[priority].popleft()
        raise queue.Empty
