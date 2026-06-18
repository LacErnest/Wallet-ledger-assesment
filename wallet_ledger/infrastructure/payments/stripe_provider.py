"""Adaptateur Stripe (paiements par carte).

Particularité : Stripe raisonne en plus petite unité (centimes) et signe ses webhooks
via l'en-tête `Stripe-Signature` (« t=...,v1=... »). On VÉRIFIE cette signature — un
webhook non vérifié laisserait n'importe qui créditer un compte gratuitement.
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

_STRIPE_API_URL = "https://api.stripe.com/v1/payment_intents"
# Devises sans sous-unité chez Stripe : le montant n'est pas multiplié par 100.
_ZERO_DECIMAL = {"JPY", "XAF", "XOF"}


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self, api_key: str, webhook_secret: str):
        self._api_key = api_key
        self._webhook_secret = webhook_secret

    def create_deposit(self, *, amount: Decimal, currency: str, reference: str, context: dict) -> ProviderCharge:
        # Sans clé API, on reste en mode hors-ligne simulé : le système doit pouvoir
        # tourner et être testé sans secrets réels.
        if not self._api_key:
            return ProviderCharge(reference=f"pi_stub_{reference}")

        minor_units = int(amount if currency.upper() in _ZERO_DECIMAL else amount * 100)
        response = requests.post(
            _STRIPE_API_URL,
            auth=(self._api_key, ""),
            data={
                "amount": minor_units,
                "currency": currency.lower(),
                "metadata[transaction_id]": reference,
            },
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        return ProviderCharge(reference=body["id"], raw=body)

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        if not self._webhook_secret or not signature:
            return False
        parts = dict(piece.split("=", 1) for piece in signature.split(",") if "=" in piece)
        timestamp, provided = parts.get("t"), parts.get("v1")
        if not timestamp or not provided:
            return False
        # Stripe signe la concaténation « timestamp.corps_brut » : on refait le calcul.
        expected = hmac_sha256_hex(self._webhook_secret, f"{timestamp}.".encode() + raw_body)
        return hmac.compare_digest(expected, provided)

    def parse_callback(self, payload: dict) -> CallbackResult:
        obj = payload.get("data", {}).get("object", {})
        reference = obj.get("metadata", {}).get("transaction_id", "")
        is_success = payload.get("type") == "payment_intent.succeeded"
        amount = None
        if obj.get("amount") is not None:
            currency = (obj.get("currency") or "").upper()
            divisor = 1 if currency in _ZERO_DECIMAL else 100
            amount = Decimal(obj["amount"]) / divisor
        return CallbackResult(
            reference=reference,
            is_success=is_success,
            amount=amount,
            currency=(obj.get("currency") or "").upper() or None,
        )
