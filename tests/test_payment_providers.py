"""Tests des adaptateurs de paiement : la vérification de webhook doit refuser tout ce
qui n'est pas authentique (fail closed), sinon n'importe qui pourrait créditer un compte.
"""

import time

from wallet_ledger.infrastructure.payments.base import hmac_sha256_hex
from wallet_ledger.infrastructure.payments.pawapay_provider import PawaPayProvider
from wallet_ledger.infrastructure.payments.paypal_provider import PayPalProvider
from wallet_ledger.infrastructure.payments.stripe_provider import StripeProvider


class TestPayPalWebhookVerification:
    def _provider(self):
        return PayPalProvider(api_base="x", client_id="", secret="", webhook_secret="s3cr3t")

    def test_valid_signature_is_accepted(self):
        body = b'{"event_type":"PAYMENT.CAPTURE.COMPLETED"}'
        assert self._provider().verify_webhook(body, hmac_sha256_hex("s3cr3t", body)) is True

    def test_wrong_signature_is_rejected(self):
        assert self._provider().verify_webhook(b"{}", "nope") is False

    def test_missing_secret_fails_closed(self):
        provider = PayPalProvider(api_base="x", client_id="", secret="", webhook_secret="")
        assert provider.verify_webhook(b"{}", hmac_sha256_hex("x", b"{}")) is False

    def test_callback_parsing(self):
        result = self._provider().parse_callback(
            {
                "event_type": "PAYMENT.CAPTURE.COMPLETED",
                "resource": {
                    "custom_id": "txn-9",
                    "amount": {"value": "150.00", "currency_code": "USD"},
                },
            }
        )
        assert result.reference == "txn-9"
        assert result.is_success is True
        assert str(result.amount) == "150.00"
        assert result.currency == "USD"


class TestStripeWebhookVerification:
    def _signed_header(self, secret: str, body: bytes) -> str:
        timestamp = str(int(time.time()))
        signature = hmac_sha256_hex(secret, f"{timestamp}.".encode() + body)
        return f"t={timestamp},v1={signature}"

    def test_valid_signature_is_accepted(self):
        provider = StripeProvider(api_key="", webhook_secret="whsec_test")
        body = b'{"type":"payment_intent.succeeded"}'
        header = self._signed_header("whsec_test", body)
        assert provider.verify_webhook(body, header) is True

    def test_tampered_body_is_rejected(self):
        provider = StripeProvider(api_key="", webhook_secret="whsec_test")
        header = self._signed_header("whsec_test", b'{"amount":100}')
        assert provider.verify_webhook(b'{"amount":999999}', header) is False

    def test_missing_secret_fails_closed(self):
        provider = StripeProvider(api_key="", webhook_secret="")
        body = b"{}"
        assert provider.verify_webhook(body, self._signed_header("whatever", body)) is False


class TestPawaPayWebhookVerification:
    def test_valid_signature_is_accepted(self):
        provider = PawaPayProvider(base_url="x", api_token="", webhook_secret="s3cr3t")
        body = b'{"depositId":"abc","status":"COMPLETED"}'
        assert provider.verify_webhook(body, hmac_sha256_hex("s3cr3t", body)) is True

    def test_wrong_signature_is_rejected(self):
        provider = PawaPayProvider(base_url="x", api_token="", webhook_secret="s3cr3t")
        assert provider.verify_webhook(b"{}", "not-the-right-signature") is False

    def test_callback_parsing(self):
        provider = PawaPayProvider(base_url="x", api_token="", webhook_secret="s3cr3t")
        result = provider.parse_callback(
            {"depositId": "txn-1", "status": "COMPLETED", "amount": "5000", "currency": "XAF"}
        )
        assert result.reference == "txn-1"
        assert result.is_success is True
        assert str(result.amount) == "5000"
