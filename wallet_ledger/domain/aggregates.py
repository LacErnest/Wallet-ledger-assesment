"""Racines d'agrégat du domaine.

Un agrégat est la frontière de cohérence qui POSSÈDE ses invariants : on ne peut pas
le mettre dans un état illégal. Ici, deux racines, toutes deux pures (aucun framework) :

- `TransactionAggregate` possède ses écritures et garantit la partie double (somme = 0
  par devise) ;
- `AccountAggregate` garantit qu'un compte ne passe jamais à découvert.

Les services applicatifs construisent ces agrégats et leur délèguent les règles ; la
persistance (SQLAlchemy) ne fait que matérialiser ce que l'agrégat a validé.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from wallet_ledger.domain.enums import EntryStatus, EntryType
from wallet_ledger.domain.errors import InsufficientFundsError, LedgerNotBalancedError
from wallet_ledger.domain.money import Money


@dataclass(frozen=True)
class PostingLine:
    """Une écriture décidée par le domaine, avant matérialisation en base."""

    account_id: str
    amount: Decimal  # signé : négatif au débit, positif au crédit
    entry_type: EntryType
    currency: str
    status: EntryStatus
    metadata: dict | None = None


class TransactionAggregate:
    """Racine d'agrégat Transaction : possède ses écritures et impose la partie double."""

    def __init__(self, currency: str):
        self.currency = currency
        self._lines: list[PostingLine] = []

    def record(
        self,
        account_id: str,
        amount: Decimal,
        entry_type: EntryType,
        currency: str,
        status: EntryStatus,
        metadata: dict | None = None,
    ) -> None:
        self._lines.append(PostingLine(account_id, amount, entry_type, currency, status, metadata))

    def debit(
        self,
        account_id: str,
        money: Money,
        status: EntryStatus = EntryStatus.SUCCESS,
        metadata: dict | None = None,
    ) -> None:
        # Le sens découle de la méthode : un débit est toujours négatif.
        self.record(
            account_id, -abs(money.amount), EntryType.DEBIT, money.currency, status, metadata
        )

    def credit(
        self,
        account_id: str,
        money: Money,
        status: EntryStatus = EntryStatus.SUCCESS,
        metadata: dict | None = None,
    ) -> None:
        self.record(
            account_id, abs(money.amount), EntryType.CREDIT, money.currency, status, metadata
        )

    @property
    def lines(self) -> tuple[PostingLine, ...]:
        return tuple(self._lines)

    def assert_balanced(self) -> None:
        """Invariant d'or : la somme des écritures vaut zéro, devise par devise."""
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for line in self._lines:
            totals[line.currency] += line.amount
        for currency, total in totals.items():
            if total != 0:
                raise LedgerNotBalancedError(currency, str(total))


class AccountAggregate:
    """Racine d'agrégat Compte : garante de l'invariant « jamais à découvert »."""

    def __init__(self, account_id: str, currency: str):
        self.account_id = account_id
        self.currency = currency

    def ensure_can_debit(self, amount: Money, available: Money) -> None:
        """Autorise le débit seulement si le disponible le couvre."""
        if available < amount:
            raise InsufficientFundsError(str(available.amount), str(amount.amount))
