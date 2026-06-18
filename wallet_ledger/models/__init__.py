"""Regroupe les modèles pour qu'Alembic et SQLAlchemy voient tout le schéma.

Importer le paquet `models` suffit à enregistrer toutes les tables sur `db.metadata`.
"""

from wallet_ledger.models.account import Account
from wallet_ledger.models.balance_snapshot import BalanceSnapshot
from wallet_ledger.models.idempotency import IdempotencyKey
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.notification import Notification
from wallet_ledger.models.transaction import Transaction

__all__ = [
    "Account",
    "BalanceSnapshot",
    "IdempotencyKey",
    "LedgerEntry",
    "Notification",
    "Transaction",
]
