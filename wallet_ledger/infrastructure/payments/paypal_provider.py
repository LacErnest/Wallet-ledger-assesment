"""Adaptateur PayPal (paiement par compte PayPal / carte via PayPal).

PayPal encaisse via l'API Orders v2 (montant décimal + devise) et confirme par webhook
(événement `PAYMENT.CAPTURE.COMPLETED`). On y attache notre identifiant via `custom_id`,
de sorte que la confirmation se relie sans ambiguïté à notre transaction.
"""

from __future__ import annotations

import hmac
from decimal import Decimal

import requests

from wallet_ledger.infrastructure.payments.base import (
    CallbackResult,
    PaymentProvider,
    ProviderCharge,
    hmac_sha256_hex,
)


class PayPalProvider(PaymentProvider):
    name = "paypal"

    def __init__(self, api_base: str, client_id: str, secret: str, webhook_secret: str):
        self._api_base = api_base.rstrip("/")
        self._client_id = client_id
        self._secret = secret
        self._webhook_secret = webhook_secret

    def create_deposit(
        self, *, amount: Decimal, currency: str, reference: str, context: dict
    ) -> ProviderCharge:
        # Sans identifiants, mode hors-ligne simulé : on conserve notre référence telle quelle.
        if not self._client_id or not self._secret:
            return ProviderCharge(reference=reference)

        response = requests.post(
            f"{self._api_base}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "amount": {"currency_code": currency.upper(), "value": str(amount)},
                        # custom_id = notre identifiant : il reviendra dans le webhook.
                        "custom_id": reference,
                    }
                ],
            },
            timeout=10,
        )
        response.raise_for_status()
        return ProviderCharge(reference=reference, raw=response.json())

    def _access_token(self) -> str:
        response = requests.post(
            f"{self._api_base}/v1/oauth2/token",
            auth=(self._client_id, self._secret),
            data={"grant_type": "client_credentials"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        # PayPal vérifie en réalité une signature par certificat via son API
        # (/v1/notifications/verify-webhook-signature). Pour rester testable hors-ligne,
        # on valide un HMAC du corps avec le secret. Fail closed sans secret ni signature.
        if not self._webhook_secret or not signature:
            return False
        expected = hmac_sha256_hex(self._webhook_secret, raw_body)
        return hmac.compare_digest(expected, signature)

    def parse_callback(self, payload: dict) -> CallbackResult:
        resource = payload.get("resource", {})
        amount_obj = resource.get("amount", {})
        value = amount_obj.get("value")
        return CallbackResult(
            reference=resource.get("custom_id", ""),
            is_success=payload.get("event_type") == "PAYMENT.CAPTURE.COMPLETED",
            amount=Decimal(value) if value else None,
            currency=amount_obj.get("currency_code"),
        )
