"""Narrow structural contracts for assistant-owned persistence.

These protocols let composition code describe only the operator-store methods
it passes into assistant policy. They do not move database ownership, expose a
database to research packages, or create an alternative persistence authority.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StrategyOperationalStore(Protocol):
    """Assistant operations required by strategy-proposal composition."""

    def record_provider_fetch(
        self,
        *,
        provider_id: str,
        data_class: str,
        fetched_at: str,
        requested_count: int,
        returned_count: int,
        missing_tickers: tuple[str, ...] | list[str],
        ok: bool,
        error: str | None,
        point_in_time_lineage: bool,
        latest_session: str | None,
    ) -> None: ...

    def consecutive_provider_failures(
        self, *, provider_id: str, data_class: str
    ) -> int: ...

    def upsert_operational_alert(
        self,
        *,
        fingerprint: str,
        severity: str,
        category: str,
        message: str,
        details: dict[str, Any] | None = None,
        seen_at: str | None = None,
    ) -> dict[str, Any]: ...

    def record_strategy_evaluation(
        self, strategy_key: str, evaluated_at: str, result: dict[str, Any]
    ) -> None: ...

    def list_provider_fetches(
        self,
        *,
        provider_id: str | None = None,
        data_class: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    def latest_successful_provider_fetch(
        self, *, provider_id: str, data_class: str
    ) -> dict[str, Any] | None: ...


__all__ = ["StrategyOperationalStore"]
