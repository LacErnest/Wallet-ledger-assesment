"""Service de transfert : déplacer de l'argent entre deux comptes, sans jamais en perdre.

Deux modes :
  - direct (`execute`) : débit et crédit écrits d'un coup, dans la même transaction ;
  - deux phases (`initiate` puis `commit`/`fail`) : on réserve d'abord les fonds, on
    règle après accord du contrôle de risque. C'est ainsi qu'on gère l'argent « en vol ».
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.application.risk import RiskService
from wallet_ledger.domain.enums import EntryStatus, EntryType, TransactionStatus, TransactionType
from wallet_ledger.domain.errors import (
    CurrencyMismatchError,
    InsufficientFundsError,
    InvalidAmountError,
    InvalidTransactionStateError,
    TransactionNotFoundError,
)
from wallet_ledger.domain.events import (
    DomainEvent,
    FUNDS_RESERVED,
    TRANSFER_COMPLETED,
    TRANSFER_FAILED,
    event_bus as default_event_bus,
)
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.models.account import Account
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction


class TransferService:
    def __init__(self, ledger: LedgerService | None = None, risk: RiskService | None = None,
                 accounts: AccountService | None = None, events=default_event_bus):
        self.ledger = ledger or LedgerService()
        self.risk = risk or RiskService()
        self.accounts = accounts or AccountService()
        self.events = events

    # --- Mode direct -----------------------------------------------------------
    def execute(self, sender_id: str, receiver_id: str, amount: Decimal,
                correlation_id: str | None = None) -> Transaction:
        sender = self._lock(sender_id)
        receiver = self._get(receiver_id)
        money = self._validate(sender, receiver, amount)
        self._ensure_funds(sender, money)

        correlation_id = correlation_id or str(uuid.uuid4())
        txn = self._new_transaction(
            TransactionType.TRANSFER, TransactionStatus.SUCCESS, money,
            sender, receiver, correlation_id,
        )
        self.ledger.post_entries([
            LedgerEntry.debit(sender.id, txn.id, money.amount, money.currency),
            LedgerEntry.credit(receiver.id, txn.id, money.amount, money.currency),
        ])
        self._snapshot(sender, receiver)
        db.session.commit()

        self._publish(TRANSFER_COMPLETED, txn, money, sender, receiver)
        return txn

    # --- Mode deux phases ------------------------------------------------------
    def initiate(self, sender_id: str, receiver_id: str, amount: Decimal,
                 correlation_id: str | None = None) -> Transaction:
        """Phase 1 : réserve les fonds via un débit PENDING (rien n'est encore réglé)."""
        sender = self._lock(sender_id)
        receiver = self._get(receiver_id)
        money = self._validate(sender, receiver, amount)
        self._ensure_funds(sender, money)

        correlation_id = correlation_id or str(uuid.uuid4())
        txn = self._new_transaction(
            TransactionType.TRANSFER, TransactionStatus.PENDING, money,
            sender, receiver, correlation_id,
        )
        # Réservation = débit PENDING seul. La transaction ne s'équilibrera qu'au
        # règlement, quand le crédit sera créé ; on n'appelle donc pas post_entries ici.
        db.session.add(
            LedgerEntry.debit(sender.id, txn.id, money.amount, money.currency, EntryStatus.PENDING)
        )
        db.session.commit()

        self._publish(FUNDS_RESERVED, txn, money, sender, receiver)
        return txn

    def commit(self, transaction_id: str) -> Transaction:
        """Phase 2 : après accord du risque, le débit devient SUCCESS et le crédit est créé."""
        txn = self._pending_transaction(transaction_id)
        money = Money(txn.amount, txn.currency)

        # Le contrôle de risque peut refuser ici : c'est tout l'intérêt des deux phases.
        self.risk.assess(money)

        debit = LedgerEntry.query.filter_by(
            transaction_id=txn.id, entry_type=EntryType.DEBIT, status=EntryStatus.PENDING
        ).first()
        if debit is None:
            raise InvalidTransactionStateError(txn.status, "commit sans débit réservé")

        sender = self._lock(debit.account_id)
        receiver = self._get(txn.details["receiver_id"])

        debit.status = EntryStatus.SUCCESS
        credit = LedgerEntry.credit(receiver.id, txn.id, money.amount, money.currency)
        db.session.add(credit)

        # Filet de sécurité : l'ensemble des écritures de la transaction doit désormais
        # s'équilibrer à zéro.
        self.ledger.assert_balanced([debit, credit])

        txn.status = TransactionStatus.SUCCESS
        self._snapshot(sender, receiver)
        db.session.commit()

        self._publish(TRANSFER_COMPLETED, txn, money, sender, receiver)
        return txn

    def fail(self, transaction_id: str) -> Transaction:
        """Annule une réservation : les écritures PENDING passent FAILED, les fonds sont libérés."""
        txn = self._pending_transaction(transaction_id)
        for entry in LedgerEntry.query.filter_by(transaction_id=txn.id, status=EntryStatus.PENDING).all():
            entry.status = EntryStatus.FAILED
        txn.status = TransactionStatus.FAILED
        db.session.commit()

        self.events.publish(DomainEvent(
            TRANSFER_FAILED, {"transaction_id": txn.id}, correlation_id=txn.correlation_id
        ))
        return txn

    # --- Aides privées ---------------------------------------------------------
    def _lock(self, account_id: str) -> Account:
        return self.accounts.lock(account_id)

    def _get(self, account_id: str) -> Account:
        return self.accounts.get(account_id)

    def _validate(self, sender: Account, receiver: Account, amount: Decimal) -> Money:
        if sender.currency != receiver.currency:
            raise CurrencyMismatchError(sender.currency, receiver.currency)
        money = Money(amount, sender.currency)
        if not money.is_positive():
            raise InvalidAmountError()
        return money

    def _ensure_funds(self, sender: Account, money: Money) -> None:
        available = self.ledger.available_balance(sender)
        if available < money:
            raise InsufficientFundsError(str(available.amount), str(money.amount))

    def _new_transaction(self, type_, status, money: Money, sender: Account,
                         receiver: Account, correlation_id: str) -> Transaction:
        txn = Transaction(
            type=type_, status=status, amount=money.amount, currency=money.currency,
            correlation_id=correlation_id,
            details={"sender_id": sender.id, "receiver_id": receiver.id},
        )
        db.session.add(txn)
        db.session.flush()
        return txn

    def _snapshot(self, *accounts: Account) -> None:
        for account in accounts:
            self.ledger.maybe_snapshot(account)

    def _pending_transaction(self, transaction_id: str) -> Transaction:
        txn = db.session.get(Transaction, transaction_id)
        if txn is None:
            raise TransactionNotFoundError(transaction_id)
        if txn.status != TransactionStatus.PENDING:
            raise InvalidTransactionStateError(txn.status, "opération sur transaction non PENDING")
        return txn

    def _publish(self, event_type: str, txn: Transaction, money: Money,
                 sender: Account, receiver: Account) -> None:
        self.events.publish(DomainEvent(
            event_type,
            {
                "transaction_id": txn.id,
                "sender_id": sender.id,
                "receiver_id": receiver.id,
                "amount": str(money.amount),
                "currency": money.currency,
            },
            correlation_id=txn.correlation_id,
        ))
