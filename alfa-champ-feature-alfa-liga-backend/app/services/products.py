from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import DEFAULT_ACTION_BY_PRODUCT
from app.config import Settings
from app.models import AlfaProduct
from app.schemas import (
    BankEffect,
    BusinessState,
    CandidateSpec,
    IntegrationStatus,
    ProductAction,
    ProductInfo,
    SimulationResult,
)


class ProductConnector(Protocol):
    def plan(self, session: Session, candidate: CandidateSpec) -> list[ProductAction]: ...


class UnknownProductError(ValueError):
    pass


class MockProductConnector:
    """Plans execution but performs no external side effect or payment."""

    def plan(self, session: Session, candidate: CandidateSpec) -> list[ProductAction]:
        if not candidate.recommended_product_ids:
            return []
        products = {
            product.id: product
            for product in session.scalars(
                select(AlfaProduct).where(
                    AlfaProduct.id.in_(candidate.recommended_product_ids),
                    AlfaProduct.active.is_(True),
                )
            )
        }
        unknown = sorted(set(candidate.recommended_product_ids) - set(products))
        if unknown:
            raise UnknownProductError(f"Unknown product ids: {', '.join(unknown)}")
        return [
            ProductAction(
                product_id=product_id,
                product_name=products[product_id].name,
                action=DEFAULT_ACTION_BY_PRODUCT[product_id],
                integration_status=IntegrationStatus(products[product_id].integration_status),
                requires_confirmation=products[product_id].requires_confirmation,
            )
            for product_id in candidate.recommended_product_ids
        ]


class ProductGateway:
    def __init__(self, settings: Settings, connector: ProductConnector | None = None):
        self.settings = settings
        self.connector = connector or MockProductConnector()

    def list_products(self, session: Session) -> list[ProductInfo]:
        return [
            ProductInfo(
                product_id=item.id,
                name=item.name,
                description=item.description,
                integration_status=IntegrationStatus(item.integration_status),
                actions=list(item.actions),
                requires_confirmation=item.requires_confirmation,
            )
            for item in session.scalars(
                select(AlfaProduct).where(AlfaProduct.active.is_(True)).order_by(AlfaProduct.id)
            )
        ]

    def execution_plan(self, session: Session, candidate: CandidateSpec) -> list[ProductAction]:
        return self.connector.plan(session, candidate)

    def bank_effect(
        self,
        state: BusinessState,
        candidate: CandidateSpec,
        simulation: SimulationResult,
        products: list[ProductAction],
    ) -> BankEffect:
        acquiring_share = float(state.payment_volume.value or 0.0) / float(
            state.revenue.value or 1.0
        )
        incremental_payment_volume = simulation.expected_revenue_delta * acquiring_share
        average_ticket = max(1.0, float(state.average_ticket.value or 1.0))
        incremental_transactions = simulation.expected_revenue_delta / average_ticket
        fee_revenue = incremental_payment_volume * self.settings.bank_acquiring_fee_rate
        service_cost = self.settings.bank_service_cost_per_sprint
        return BankEffect(
            incremental_payment_volume=round(incremental_payment_volume, 2),
            incremental_transaction_count=round(incremental_transactions, 2),
            estimated_fee_revenue=round(fee_revenue, 2),
            connected_product_count=len(products),
            estimated_service_cost=round(service_cost, 2),
            net_bank_effect=round(fee_revenue - service_cost, 2),
            assumptions=[
                (
                    "Ставка эквайринга и стоимость сервиса — демонстрационные "
                    "допущения, не тарифы Альфа-Банка."
                ),
                f"Демонстрационная ставка fee: {self.settings.bank_acquiring_fee_rate:.2%}.",
                f"Демонстрационная стоимость сопровождения: {service_cost:.0f} ₽ за спринт.",
            ],
        )
