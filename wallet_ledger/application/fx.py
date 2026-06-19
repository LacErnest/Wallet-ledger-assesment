"""Service de change : conversion et transfert entre comptes de devises différentes.

Un transfert FX passe par deux comptes « pool » internes (un par devise). Ainsi, devise
par devise, la somme des écritures reste nulle : l'argent n'est ni créé ni détruit, on
ne fait que l'échanger via le pool.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.domain.aggregates import AccountAggregate, TransactionAggregate
from wallet_ledger.domain.enums import TransactionStatus, TransactionType
from wallet_ledger.domain.errors import InvalidAmountError, SameCurrencyError
from wallet_ledger.domain.events import TRANSFER_COMPLETED, DomainEvent
from wallet_ledger.domain.events import event_bus as default_event_bus
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.infrastructure.fx_rates import FxRateProvider
from wallet_ledger.models.transaction import Transaction

# Propriétaire des comptes pool de change (un compte interne par devise).
_FX_POOL_OWNER = "FX_POOL"


class FxService:
    def __init__(
        self,
        rates: FxRateProvider | None = None,
        ledger: LedgerService | None = None,
        accounts: AccountService | None = None,
        events=default_event_bus,
    ):
        self.rates = rates or FxRateProvider()
        self.ledger = ledger or LedgerService()
        self.accounts = accounts or AccountService()
        self.events = events

    def get_rate(self, base: str, quote: str) -> Decimal:
        return self.rates.get_rate(base, quote)

    def convert(self, money: Money, to_currency: str) -> Money:
        rate = self.rates.get_rate(money.currency, to_currency)
        return Money(money.amount * rate, to_currency)

    def execute_fx_transfer(
        self, sender_id: str, receiver_id: str, amount: Decimal, correlation_id: str | None = None
    ) -> Transaction:
        sender = self.accounts.lock(sender_id)
        receiver = self.accounts.get(receiver_id)
        if sender.currency == receiver.currency:
            raise SameCurrencyError(sender.currency)

        sent = Money(amount, sender.currency)
        if not sent.is_positive():
            raise InvalidAmountError()
        available = self.ledger.available_balance(sender)
        AccountAggregate(sender.id, sender.currency).ensure_can_debit(sent, available)

        received = self.convert(sent, receiver.currency)
        pool_from = self.accounts.get_or_create_internal(_FX_POOL_OWNER, sender.currency)
        pool_to = self.accounts.get_or_create_internal(_FX_POOL_OWNER, receiver.currency)

        correlation_id = correlation_id or str(uuid.uuid4())
        txn = Transaction(
            type=TransactionType.FX_TRANSFER,
            status=TransactionStatus.SUCCESS,
            amount=sent.amount,
            currency=sent.currency,
            correlation_id=correlation_id,
            details={
                "sender_id": sender.id,
                "receiver_id": receiver.id,
                "target_amount": str(received.amount),
                "target_currency": received.currency,
            },
        )
        db.session.add(txn)
        db.session.flush()

        # Quatre écritures via l'agrégat : devise source équilibrée par pool_from, devise
        # cible par pool_to. L'agrégat vérifie que CHAQUE devise se solde à zéro.
        transaction = TransactionAggregate(sent.currency)
        transaction.debit(sender.id, sent)
        transaction.credit(pool_from.id, sent)
        transaction.debit(pool_to.id, received)
        transaction.credit(receiver.id, received)
        self.ledger.post(transaction, txn.id)
        # On fige aussi les comptes pool : sinon leur historique grossit sans limite et
        # le calcul de leur solde se dégrade — c'est précisément ce que l'instantané évite.
        for account in (sender, receiver, pool_from, pool_to):
            self.ledger.maybe_snapshot(account)
        db.session.commit()

        self.events.publish(
            DomainEvent(
                TRANSFER_COMPLETED,
                {
                    "transaction_id": txn.id,
                    "sender_id": sender.id,
                    "receiver_id": receiver.id,
                    "amount": str(sent.amount),
                    "currency": sent.currency,
                    "target_amount": str(received.amount),
                    "target_currency": received.currency,
                },
                correlation_id=correlation_id,
            )
        )
        return txn
