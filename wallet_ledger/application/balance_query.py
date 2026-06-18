"""Lecture de solde optimisée (cache-aside).

On sépare la LECTURE (qui peut passer par le cache) de l'ÉCRITURE comptable (qui,
elle, recalcule toujours sous verrou). Ainsi une décision financière s'appuie toujours
sur le grand livre, jamais sur un cache potentiellement périmé.
"""

from __future__ import annotations

from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.domain.money import Money
from wallet_ledger.infrastructure.cache import BalanceCache
from wallet_ledger.models.account import Account


class BalanceQuery:
    def __init__(self, ledger: LedgerService, cache: BalanceCache):
        self.ledger = ledger
        self.cache = cache

    def get(self, account: Account) -> Money:
        cached = self.cache.get(account.id, account.currency)
        if cached is not None:
            return cached
        money = self.ledger.balance(account)
        self.cache.set(account.id, money)
        return money
