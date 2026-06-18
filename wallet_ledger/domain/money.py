"""Value Object `Money`.

Pourquoi un objet dédié plutôt qu'un simple nombre : en finance, un montant n'a
aucun sens sans sa devise, et mélanger des devises ou perdre des centimes par
arrondi flottant provoque des écarts comptables impossibles à rattraper. On rend
donc l'argent immuable, toujours en `Decimal`, et incapable de s'additionner à une
autre devise par erreur.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from wallet_ledger.domain.errors import CurrencyMismatchError

# Nombre de décimales par devise.
# - EUR / USD : 2 décimales (les centimes habituels).
# - JPY (yen japonais), XAF / XOF (francs CFA) : 0 décimale. Ces devises n'ont pas
#   de sous-unité : arrondir un montant à 2 décimales afficherait des centimes qui
#   n'existent pas dans la vraie vie.
_CURRENCY_DECIMALS: dict[str, int] = {
    "EUR": 2,
    "USD": 2,
    "JPY": 0,
    "XAF": 0,
    "XOF": 0,
}
_DEFAULT_DECIMALS = 2


def _decimals_for(currency: str) -> int:
    return _CURRENCY_DECIMALS.get(currency.upper(), _DEFAULT_DECIMALS)


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        # Le flottant est interdit à l'entrée : 0.1 + 0.2 != 0.3 en binaire, et ce
        # genre d'écart n'a pas sa place dans un grand livre.
        if isinstance(self.amount, float):
            raise TypeError("Le flottant est interdit pour Money : utiliser Decimal, int ou str.")

        currency = self.currency.upper()
        quantum = Decimal(1).scaleb(-_decimals_for(currency))
        # Arrondi « du banquier » (HALF_EVEN) : sur de gros volumes il ne biaise pas
        # systématiquement les montants vers le haut, contrairement à HALF_UP.
        normalized = Decimal(str(self.amount)).quantize(quantum, rounding=ROUND_HALF_EVEN)

        object.__setattr__(self, "amount", normalized)
        object.__setattr__(self, "currency", currency)

    # --- Garde-fou devise ------------------------------------------------------
    def _ensure_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)

    # --- Arithmétique ----------------------------------------------------------
    def __add__(self, other: Money) -> Money:
        self._ensure_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._ensure_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    # --- Comparaisons (refusent de comparer deux devises différentes) ----------
    def __lt__(self, other: Money) -> bool:
        self._ensure_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._ensure_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._ensure_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._ensure_same_currency(other)
        return self.amount >= other.amount

    # --- Prédicats lisibles ----------------------------------------------------
    def is_positive(self) -> bool:
        return self.amount > 0

    def is_negative(self) -> bool:
        return self.amount < 0

    def is_zero(self) -> bool:
        return self.amount == 0

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    def to_dict(self) -> dict[str, str]:
        return {"amount": str(self.amount), "currency": self.currency}

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(Decimal(0), currency)
