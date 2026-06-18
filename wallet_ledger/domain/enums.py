"""États et types du domaine.

On modélise le cycle de vie en énumérations plutôt qu'en chaînes libres : une faute
de frappe sur un statut financier ne doit jamais pouvoir passer en base.
"""

from enum import StrEnum


class EntryType(StrEnum):
    """Sens comptable d'une écriture."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class EntryStatus(StrEnum):
    """Une écriture réservée (PENDING) pèse sur le disponible mais pas sur le soldé."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class TransactionType(StrEnum):
    DEPOSIT = "DEPOSIT"
    TRANSFER = "TRANSFER"
    FX_TRANSFER = "FX_TRANSFER"
    REVERSAL = "REVERSAL"


class TransactionStatus(StrEnum):
    """Cycle de vie : PENDING -> SUCCESS/FAILED, puis SUCCESS -> REVERSED.

    Une transaction terminée est immuable ; on corrige par transaction compensatoire.
    """

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REVERSED = "REVERSED"
