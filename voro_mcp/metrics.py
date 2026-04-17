from __future__ import annotations

from collections import defaultdict
from threading import Lock


class MetricsStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.request_count = 0
        self.success_count = 0
        self.deny_count = 0
        self.deny_by_reason: dict[str, int] = defaultdict(int)
        self.rebuild_by_reason: dict[str, int] = defaultdict(int)
        self.cache_hit_count = 0
        self.incremental_rebuild_count = 0
        self.full_rebuild_count = 0
        self._files_changed_total = 0
        self._files_reused_total = 0
        self._saved_tokens_total = 0
        self._saved_tokens_count = 0

    def record_request(self) -> None:
        with self._lock:
            self.request_count += 1

    def record_success(self, saved_tokens_est: int | float | None) -> None:
        with self._lock:
            self.success_count += 1
            if isinstance(saved_tokens_est, (int, float)):
                self._saved_tokens_total += int(saved_tokens_est)
                self._saved_tokens_count += 1

    def record_deny(self, reason_code: str) -> None:
        with self._lock:
            self.deny_count += 1
            self.deny_by_reason[reason_code] += 1

    def record_rebuild(self, rebuild_reason: str, files_changed: int, files_reused: int) -> None:
        with self._lock:
            self.rebuild_by_reason[rebuild_reason] += 1
            if rebuild_reason == "cache_hit_same_revision":
                self.cache_hit_count += 1
            elif rebuild_reason.startswith("incremental_"):
                self.incremental_rebuild_count += 1
            elif rebuild_reason.startswith("full_rebuild_"):
                self.full_rebuild_count += 1
            self._files_changed_total += max(0, int(files_changed))
            self._files_reused_total += max(0, int(files_reused))

    def snapshot(self) -> dict:
        with self._lock:
            avg_saved = (
                self._saved_tokens_total / self._saved_tokens_count
                if self._saved_tokens_count
                else 0.0
            )
            return {
                "request_count": self.request_count,
                "success_count": self.success_count,
                "deny_count": self.deny_count,
                "deny_by_reason": dict(sorted(self.deny_by_reason.items())),
                "rebuild_by_reason": dict(sorted(self.rebuild_by_reason.items())),
                "cache_hit_count": self.cache_hit_count,
                "incremental_rebuild_count": self.incremental_rebuild_count,
                "full_rebuild_count": self.full_rebuild_count,
                "files_changed_total": self._files_changed_total,
                "files_reused_total": self._files_reused_total,
                "avg_saved_tokens_est": round(avg_saved, 2),
            }


metrics = MetricsStore()
