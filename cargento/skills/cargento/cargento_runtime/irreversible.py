"""Current-run command reports, separate from coalesced lifecycle overlays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

PATTERNS: Final = {
    "git_force_push": "force push",
    "git_hard_reset": "hard reset",
    "sql_drop_table": "DROP TABLE",
    "recursive_delete": "recursive delete",
}
REPORT_FIELDS: Final = frozenset(
    {"v", "event", "session_id", "timestamp", "pattern_id", "tool_name"}
)
MAX_REPORTS: Final = 1000
MAX_PER_SESSION: Final = 20
RETENTION_SEC: Final = 86400


@dataclass(frozen=True)
class Report:
    harness: str
    sid: str
    pattern_id: str
    tool_name: str
    timestamp: float
    arrival_seq: int

    def published(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "sid": self.sid,
            "pattern_id": self.pattern_id,
            "label": PATTERNS[self.pattern_id],
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
        }


class Ledger:
    """Owned under the coordinator lock; duplicate delivery remains a report."""

    def __init__(self) -> None:
        self._reports: list[Report] = []

    def add(self, report: Report, *, now: float) -> None:
        self._reports.append(report)
        self._prune(now=now)

    def _prune(self, *, now: float) -> None:
        counts: dict[tuple[str, str], int] = {}
        kept = []
        for report in sorted(
            self._reports, key=lambda r: (r.timestamp, r.arrival_seq), reverse=True
        ):
            key = report.harness, report.sid
            if now - report.timestamp >= RETENTION_SEC or counts.get(key, 0) >= MAX_PER_SESSION:
                continue
            kept.append(report)
            counts[key] = counts.get(key, 0) + 1
            if len(kept) == MAX_REPORTS:
                break
        self._reports = kept

    def published(self, *, now: float) -> list[dict[str, Any]]:
        self._prune(now=now)
        return [report.published() for report in self._reports]
