from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Business, BusinessEvent, MetricSnapshot
from app.schemas import BusinessState, DataSource, MetricValue


class BusinessNotFoundError(LookupError):
    pass


class BusinessStateAdapter:
    """Calculates aggregates in Python/SQL and never exposes transaction rows."""

    WINDOW_DAYS = 60

    def build(self, session: Session, business_id: str) -> BusinessState:
        business = session.get(Business, business_id)
        if business is None:
            raise BusinessNotFoundError(business_id)

        events = list(
            session.scalars(
                select(BusinessEvent)
                .where(
                    BusinessEvent.business_id == business_id,
                    BusinessEvent.event_type == "TRANSACTION",
                )
                .order_by(BusinessEvent.occurred_at)
            )
        )
        if not events:
            raise ValueError(f"No transaction fixture for business {business_id}")

        snapshots = {
            row.metric_name: row
            for row in session.scalars(
                select(MetricSnapshot).where(MetricSnapshot.business_id == business_id)
            )
        }

        end = max(self._aware(event.occurred_at) for event in events)
        start = end - timedelta(days=self.WINDOW_DAYS)
        observed_at = end
        transactions = [
            event.payload for event in events if not event.payload.get("refunded", False)
        ]
        refunded_count = len(events) - len(transactions)
        revenue = sum(float(item["amount"]) for item in transactions)
        payment_volume = sum(
            float(item["amount"])
            for item in transactions
            if item.get("payment_channel") == "acquiring"
        )
        transaction_count = len(transactions)
        average_ticket = revenue / transaction_count if transaction_count else 0.0

        customer_counts = Counter(str(item["customer_hash"]) for item in transactions)
        repeat_customers = sum(1 for count in customer_counts.values() if count > 1)
        repeat_rate = repeat_customers / len(customer_counts) if customer_counts else 0.0
        refund_rate = refunded_count / len(events) if events else 0.0

        profile = business.profile
        cost_available = bool(profile.get("cost_data_available", False)) and all(
            "variable_cost" in item for item in transactions
        )
        variable_cost = (
            sum(float(item["variable_cost"]) for item in transactions) if cost_available else None
        )
        fixed_costs = float(profile.get("fixed_costs_60d", 0.0))
        gross_margin = (
            (revenue - variable_cost) / revenue
            if variable_cost is not None and revenue > 0
            else None
        )
        contribution_margin = (
            (revenue - variable_cost - fixed_costs) / revenue
            if variable_cost is not None and revenue > 0
            else None
        )

        capacity = float(profile.get("capacity_orders_per_hour", 1.0))
        operating_hours = float(profile.get("operating_hours_per_day", 12.0))
        utilization = min(
            1.0,
            transaction_count / (self.WINDOW_DAYS * operating_hours * capacity),
        )
        morning_transactions = sum(
            1 for item in transactions if 8 <= int(item.get("hour", -1)) < 11
        )
        morning_utilization = min(
            1.0,
            morning_transactions / (self.WINDOW_DAYS * 3 * capacity),
        )

        cash_snapshot = snapshots.get("cash_balance")
        cash_balance = self._snapshot_value(cash_snapshot)
        if cash_balance is None and profile.get("cash_balance") is not None:
            cash_balance = float(profile["cash_balance"])
        daily_cost = (
            ((variable_cost or 0.0) + fixed_costs) / self.WINDOW_DAYS if cost_available else None
        )
        runway_days = (
            cash_balance / daily_cost
            if cash_balance is not None and daily_cost is not None and daily_cost > 0
            else None
        )

        peer_repeat = self._snapshot_value(snapshots.get("peer_repeat_rate"))
        peer_gap = peer_repeat - repeat_rate if peer_repeat is not None else None

        missing_fields = list(profile.get("known_missing_fields", []))
        if not cost_available:
            missing_fields.append("unit_cost")
        if cash_balance is None:
            missing_fields.append("cash_balance")
        if peer_repeat is None:
            missing_fields.append("peer_repeat_rate")
        missing_fields = sorted(set(missing_fields))

        # Coverage includes one intentionally missing non-critical marketing field.
        coverage_fields = 14
        missing_coverage = len(
            set(missing_fields).intersection(
                {"unit_cost", "cash_balance", "peer_repeat_rate", "marketing_attribution"}
            )
        )
        data_coverage = (coverage_fields - missing_coverage) / coverage_fields

        transaction_source = DataSource.SYNTHETIC
        bank_observed = self._aware(cash_snapshot.observed_at) if cash_snapshot else observed_at
        peer_snapshot = snapshots.get("peer_repeat_rate")
        peer_observed = self._aware(peer_snapshot.observed_at) if peer_snapshot else observed_at

        def metric(
            value: float | int | None,
            *,
            source: DataSource = transaction_source,
            confidence: float = 0.98,
            at: datetime = observed_at,
        ) -> MetricValue:
            return MetricValue(
                value=round(value, 6) if isinstance(value, float) else value,
                source=source,
                observed_at=at,
                confidence=confidence if value is not None else 0.0,
                is_missing=value is None,
            )

        constraints = {
            key: float(value) for key, value in profile.get("manual_constraints", {}).items()
        }
        return BusinessState(
            business_id=business_id,
            window_start=start,
            window_end=end,
            payment_volume=metric(payment_volume),
            revenue=metric(revenue),
            transaction_count=metric(transaction_count),
            average_ticket=metric(average_ticket),
            repeat_rate=metric(repeat_rate),
            refund_rate=metric(refund_rate),
            gross_margin=metric(gross_margin),
            contribution_margin=metric(contribution_margin),
            utilization=metric(utilization),
            cash_balance=metric(
                cash_balance,
                source=DataSource.BANK,
                confidence=0.99,
                at=bank_observed,
            ),
            runway_days=metric(runway_days),
            morning_utilization=metric(morning_utilization),
            peer_gap=metric(
                peer_gap,
                source=DataSource.EXTERNAL,
                confidence=0.82,
                at=peer_observed,
            ),
            data_coverage=metric(data_coverage),
            missing_fields=missing_fields,
            constraints=constraints,
        )

    @staticmethod
    def _snapshot_value(snapshot: MetricSnapshot | None) -> float | None:
        if snapshot is None or snapshot.is_missing:
            return None
        value = snapshot.value.get("value")
        return float(value) if value is not None else None

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
