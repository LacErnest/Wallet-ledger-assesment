"""Service d'annulation par transaction compensatoire.

Règle du domaine : une transaction terminée est IMMUABLE. On ne « défait » donc jamais
ses écritures ; on enregistre une NOUVELLE transaction (type REVERSAL) dont les écritures
sont le miroir exact des originales. Le grand livre garde ainsi la trace complète : on
voit l'opération, puis son annulation. La transaction d'origine passe au statut REVERSED.
"""

from __future__ import annotations

import uuid

from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.domain.enums import EntryStatus, EntryType, TransactionStatus, TransactionType
from wallet_ledger.domain.errors import InvalidTransactionStateError, TransactionNotFoundError
from wallet_ledger.extensions import db
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction


class ReversalService:
    def __init__(self, ledger: LedgerService | None = None, accounts: AccountService | None = None):
        self.ledger = ledger or LedgerService()
        self.accounts = accounts or AccountService()

    def reverse(self, transaction_id: str, correlation_id: str | None = None) -> Transaction:
        txn = db.session.get(Transaction, transaction_id)
        if txn is None:
            raise TransactionNotFoundError(transaction_id)
        # On n'annule que des opérations RÉUSSIES. Une réservation se libère via /fail ;
        # annuler une annulation n'aurait pas de sens.
        if txn.status != TransactionStatus.SUCCESS:
            raise InvalidTransactionStateError(txn.status, "annulation d'une transaction non SUCCESS")
        if txn.type == TransactionType.REVERSAL:
            raise InvalidTransactionStateError(txn.status, "annulation d'une transaction d'annulation")

        original_entries = LedgerEntry.query.filter_by(
            transaction_id=txn.id, status=EntryStatus.SUCCESS
        ).all()

        # On verrouille les comptes concernés (ordre déterministe = pas d'interblocage)
        # pour figer un instantané cohérent pendant l'écriture des contre-passations.
        for account_id in sorted({entry.account_id for entry in original_entries}):
            self.accounts.lock(account_id)

        reversal = Transaction(
            type=TransactionType.REVERSAL, status=TransactionStatus.SUCCESS,
            amount=txn.amount, currency=txn.currency,
            correlation_id=correlation_id or str(uuid.uuid4()),
            details={"reverses": txn.id},
        )
        db.session.add(reversal)
        db.session.flush()

        # Miroir de chaque écriture : un débit d'origine devient un crédit, et inversement.
        # L'ensemble reste équilibré à zéro par devise (c'est le miroir d'un ensemble équilibré).
        mirrors = []
        for entry in original_entries:
            if entry.entry_type == EntryType.DEBIT:
                mirrors.append(LedgerEntry.credit(entry.account_id, reversal.id, entry.amount, entry.currency))
            else:
                mirrors.append(LedgerEntry.debit(entry.account_id, reversal.id, entry.amount, entry.currency))
        self.ledger.post_entries(mirrors)

        txn.status = TransactionStatus.REVERSED
        for account_id in {entry.account_id for entry in original_entries}:
            self.ledger.maybe_snapshot(self.accounts.get(account_id))
        db.session.commit()
        return reversal
