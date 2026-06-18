"""Cache de solde (Redis), en lecture seule et jamais source de vérité.

Lire un solde est l'opération la plus fréquente (1000/s visés). On garde donc le
dernier solde calculé en cache. Règle d'or : si Redis est indisponible, on ne casse
JAMAIS la lecture — on retombe simplement sur le calcul depuis le grand livre.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from wallet_ledger.domain.money import Money

logger = logging.getLogger(__name__)


class BalanceCache:
    def __init__(self, client, ttl_seconds: int):
        self._client = client
        self._ttl = ttl_seconds

    def _key(self, account_id: str) -> str:
        return f"balance:{account_id}"

    def get(self, account_id: str, currency: str) -> Money | None:
        if self._client is None:
            return None
        try:
            raw = self._client.get(self._key(account_id))
        except Exception:  # noqa: BLE001 — une panne de cache ne doit pas casser une lecture
            logger.warning("Cache de solde indisponible en lecture", exc_info=True)
            return None
        if raw is None:
            return None
        return Money(Decimal(raw.decode()), currency)

    def set(self, account_id: str, money: Money) -> None:
        if self._client is None:
            return
        try:
            self._client.setex(self._key(account_id), self._ttl, str(money.amount))
        except Exception:  # noqa: BLE001
            logger.warning("Cache de solde indisponible en écriture", exc_info=True)

    def invalidate(self, account_id: str) -> None:
        # Appelée dès qu'un mouvement touche le compte : un solde périmé en cache vaut
        # pire que pas de cache du tout.
        if self._client is None:
            return
        try:
            self._client.delete(self._key(account_id))
        except Exception:  # noqa: BLE001
            logger.warning("Cache de solde indisponible en invalidation", exc_info=True)
