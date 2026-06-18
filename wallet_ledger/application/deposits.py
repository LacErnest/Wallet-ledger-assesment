"""Service de dépôt : alimenter un portefeuille depuis un fournisseur de paiement.

Flux : l'utilisateur initie un dépôt (transaction PENDING qui MÉMORISE le montant
autorisé), le fournisseur encaisse, puis confirme par webhook. Au règlement, on
réconcilie le montant confirmé avec le montant autorisé : un fournisseur ne doit
jamais pouvoir créditer plus (ni moins) que ce que le client a demandé.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.domain.enums import EntryStatus, EntryType, TransactionStatus, TransactionType
from wallet_ledger.domain.errors import (
    DepositAmountMismatchError,
    InvalidAmountError,
    InvalidTransactionStateError,
    TransactionNotFoundError,
)
from wallet_ledger.domain.events import DEPOSIT_COMPLETED, DomainEvent, event_bus as default_event_bus
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.infrastructure.payments import get_payment_provider
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction

# Propriétaire du compte de compensation interne : la contrepartie de tout dépôt.
_CLEARING_OWNER = "PLATFORM_CLEARING"


class DepositService:
    def __init__(self, ledger: LedgerService | None = None,
                 accounts: AccountService | None = None, events=default_event_bus):
        self.ledger = ledger or LedgerService()
        self.accounts = accounts or AccountService()
        self.events = events

    def initiate(self, account_id: str, amount: Decimal, provider_name: str,
                 context: dict | None = None, correlation_id: str | None = None) -> Transaction:
        """Crée un dépôt PENDING et demande au fournisseur d'encaisser."""
        account = self.accounts.get(account_id)
        money = Money(amount, account.currency)
        if not money.is_positive():
            raise InvalidAmountError()

        context = context or {}
        correlation_id = correlation_id or str(uuid.uuid4())
        txn = Transaction(
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.PENDING,
            amount=money.amount,
            currency=money.currency,
            correlation_id=correlation_id,
            details={"provider": provider_name, "account_id": account.id, **context},
        )
        db.session.add(txn)
        db.session.flush()

        provider = get_payment_provider(provider_name)
        charge = provider.create_deposit(
            amount=money.amount, currency=money.currency, reference=txn.id, context=context
        )
        # On garde la référence du fournisseur : c'est elle que portera le webhook.
        txn.reference = charge.reference
        db.session.commit()
        return txn

    def settle(self, reference: str, confirmed_amount: Decimal | None,
               confirmed_currency: str | None = None) -> Transaction:
        """Confirme un dépôt (appelé après vérification de la signature du webhook)."""
        # Verrou de ligne sur la transaction : les fournisseurs rejouent leurs webhooks,
        # parfois en parallèle. Sans ce verrou, deux confirmations simultanées
        # passeraient toutes deux le test « PENDING » et créditeraient deux fois.
        txn = db.session.query(Transaction).filter_by(reference=reference).with_for_update().first()
        if txn is None:
            raise TransactionNotFoundError(reference)
        # Déjà réglé : on ne crédite pas deux fois (sécurité face aux webhooks rejoués).
        if txn.status != TransactionStatus.PENDING:
            raise InvalidTransactionStateError(txn.status, "dépôt déjà traité")

        authorized = Money(txn.amount, txn.currency)
        # On réconcilie le montant ET la devise : un fournisseur ne doit pouvoir créditer
        # ni un autre montant, ni une autre devise que ce qui a été autorisé.
        if confirmed_currency is not None and confirmed_currency.upper() != txn.currency:
            raise DepositAmountMismatchError(
                f"{authorized.amount} {txn.currency}", f"{confirmed_amount} {confirmed_currency}"
            )
        confirmed = authorized if confirmed_amount is None else Money(confirmed_amount, txn.currency)
        if confirmed != authorized:
            raise DepositAmountMismatchError(str(authorized.amount), str(confirmed.amount))

        account = self.accounts.lock(txn.details["account_id"])
        clearing = self.accounts.get_or_create_internal(_CLEARING_OWNER, account.currency)

        self.ledger.post_entries([
            LedgerEntry(account_id=clearing.id, transaction_id=txn.id, amount=-authorized.amount,
                        entry_type=EntryType.DEBIT, status=EntryStatus.SUCCESS, currency=authorized.currency),
            LedgerEntry(account_id=account.id, transaction_id=txn.id, amount=authorized.amount,
                        entry_type=EntryType.CREDIT, status=EntryStatus.SUCCESS, currency=authorized.currency),
        ])
        txn.status = TransactionStatus.SUCCESS
        self.ledger.maybe_snapshot(account)
        self.ledger.maybe_snapshot(clearing)
        db.session.commit()

        self.events.publish(DomainEvent(
            DEPOSIT_COMPLETED,
            {
                "transaction_id": txn.id,
                "account_id": account.id,
                "amount": str(authorized.amount),
                "currency": authorized.currency,
            },
            correlation_id=txn.correlation_id,
        ))
        return txn
