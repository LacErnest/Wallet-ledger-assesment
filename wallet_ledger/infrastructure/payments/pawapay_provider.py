"""Adaptateur PawaPay (mobile money : MTN, Orange).

PawaPay raisonne en montant décimal (pas de centimes) et identifie l'opérateur par un
code « correspondant » (MTN_MOMO_CMR, ORANGE_CMR…). La confirmation arrive par webhook
avec un statut COMPLETED. On vérifie l'authenticité du webhook (fail closed), là où une
intégration naïve ferait confiance aveuglément au corps reçu.
"""

from __future__ import annotations

import hmac
from decimal import Decimal

import requests

from wallet_ledger.domain.errors import UnsupportedProviderError
from wallet_ledger.infrastructure.payments.base import (
    CallbackResult,
    PaymentProvider,
    ProviderCharge,
    hmac_sha256_hex,
)

# (opérateur, devise) -> code correspondant PawaPay. La devise porte le pays :
# XAF = Cameroun (CMR), XOF = Côte d'Ivoire (CIV).
_CORRESPONDENTS = {
    ("mtn", "XAF"): "MTN_MOMO_CMR",
    ("orange", "XAF"): "ORANGE_CMR",
    ("mtn", "XOF"): "MTN_MOMO_CIV",
    ("orange", "XOF"): "ORANGE_CIV",
}


class PawaPayProvider(PaymentProvider):
    name = "pawapay"

    def __init__(self, base_url: str, api_token: str, webhook_secret: str):
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._webhook_secret = webhook_secret

    def create_deposit(self, *, amount: Decimal, currency: str, reference: str, context: dict) -> ProviderCharge:
        operator = str(context.get("operator", "")).lower()
        correspondent = _CORRESPONDENTS.get((operator, currency.upper()))
        if correspondent is None:
            raise UnsupportedProviderError(f"pawapay {operator}/{currency}")

        # Sans jeton, mode hors-ligne simulé : on garde notre référence telle quelle.
        if not self._api_token:
            return ProviderCharge(reference=reference)

        payload = {
            # depositId = notre identifiant de transaction : il assure l'idempotence
            # côté PawaPay (un même depositId ne sera pas encaissé deux fois).
            "depositId": reference,
            "amount": str(amount),  # décimal, jamais en sous-unité
            "currency": currency.upper(),
            "payer": {
                "type": "MMO",
                "accountDetails": {
                    "provider": correspondent,
                    "phoneNumber": context.get("phone_number", ""),
                },
            },
            "metadata": [{"transaction_id": reference}],
        }
        response = requests.post(
            f"{self._base_url}/v2/deposits",
            json=payload,
            headers={"Authorization": f"Bearer {self._api_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return ProviderCharge(reference=reference, raw=response.json())

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        if not self._webhook_secret or not signature:
            return False
        expected = hmac_sha256_hex(self._webhook_secret, raw_body)
        return hmac.compare_digest(expected, signature)

    def parse_callback(self, payload: dict) -> CallbackResult:
        amount = Decimal(payload["amount"]) if payload.get("amount") else None
        return CallbackResult(
            reference=payload.get("depositId", ""),
            is_success=payload.get("status") == "COMPLETED",
            amount=amount,
            currency=payload.get("currency"),
        )
