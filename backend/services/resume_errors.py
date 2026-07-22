from __future__ import annotations

from typing import Any


class StaleRevError(Exception):
    """Raised when a write's base_rev no longer matches the document (concurrent edit)."""

    def __init__(self, current: Any) -> None:
        super().__init__("resume document was modified by a concurrent edit")
        self.current = current
