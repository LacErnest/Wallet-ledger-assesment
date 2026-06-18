"""Sérialisation des entités vers JSON (réponses HTTP).

Centralisé pour que la forme d'un compte ou d'une transaction soit la même partout
(principe DRY) et qu'on n'expose jamais de champ interne par accident.
"""

from __future__ import annotations

from wallet_ledger.domain.money import Money
from wallet_ledger.models.account import Account
from wallet_ledger.models.transaction import Transaction


def serialize_account(account: Account) -> dict:
    return {
        "id": account.id,
        "number": account.number,
        "owner_id": account.owner_id,
        "currency": account.currency,
        "created_at": account.created_at.isoformat(),
    }


def serialize_balance(account: Account, balance: Money) -> dict:
    return {
        "account_number": account.number,
        "balance": str(balance.amount),
        "currency": balance.currency,
    }


def serialize_transaction(transaction: Transaction) -> dict:
    return {
        "transaction_id": transaction.id,
        "type": transaction.type.value,
        "status": transaction.status.value,
        "amount": str(transaction.amount),
        "currency": transaction.currency,
        "correlation_id": transaction.correlation_id,
        "created_at": transaction.created_at.isoformat(),
    }
