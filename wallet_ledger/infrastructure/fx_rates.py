"""Fournisseur de taux de change.

On interroge une API externe si elle est configurée, sinon on s'appuie sur des taux de
référence intégrés : le système reste utilisable et testable hors-ligne, sans jamais
dépendre de la disponibilité d'un tiers pour une opération.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import requests

from wallet_ledger.domain.errors import UnknownCurrencyError

logger = logging.getLogger(__name__)

# Taux de référence : nombre d'unités de la devise pour 1 EUR. Sert de repli hors-ligne.
_REFERENCE_PER_EUR: dict[str, Decimal] = {
    "EUR": Decimal("1"),
    "USD": Decimal("1.08"),
    "GBP": Decimal("0.85"),
    "JPY": Decimal("169.50"),
    "XAF": Decimal("655.957"),
    "XOF": Decimal("655.957"),
}

_RATE_PRECISION = Decimal("0.00000001")


class FxRateProvider:
    def __init__(self, api_url: str = "", api_key: str = ""):
        self._api_url = api_url
        self._api_key = api_key

    def get_rate(self, base: str, quote: str) -> Decimal:
        """Taux pour convertir 1 unité de `base` en `quote`."""
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return Decimal("1")
        rates = self._rates()
        if base not in rates:
            raise UnknownCurrencyError(base)
        if quote not in rates:
            raise UnknownCurrencyError(quote)
        # On passe par l'EUR comme pivot : (unités quote / EUR) / (unités base / EUR).
        return (rates[quote] / rates[base]).quantize(_RATE_PRECISION)

    def _rates(self) -> dict[str, Decimal]:
        if not self._api_url:
            return _REFERENCE_PER_EUR
        try:
            response = requests.get(
                self._api_url, params={"base": "EUR", "access_key": self._api_key}, timeout=10
            )
            response.raise_for_status()
            return {code: Decimal(str(value)) for code, value in response.json()["rates"].items()}
        except Exception:  # noqa: BLE001 — une API de taux indisponible ne doit pas bloquer le service
            logger.warning(
                "API de taux indisponible, repli sur les taux de référence", exc_info=True
            )
            return _REFERENCE_PER_EUR
