"""Tests d'intégration HTTP : on traverse toute la pile (validation, idempotence,
traçabilité, vérification de webhook) via le client de test Flask.
"""

import json
from decimal import Decimal

from wallet_ledger.application.accounts import AccountService
from wallet_ledger.infrastructure.payments.base import hmac_sha256_hex
from wallet_ledger.infrastructure.tracing import CORRELATION_HEADER

API = "/api/v1"


def _create_account(client, owner_id, currency="USD") -> str:
    resp = client.post(f"{API}/accounts", json={"owner_id": owner_id, "currency": currency})
    assert resp.status_code == 201
    return resp.get_json()["number"]


class TestAccountsApi:
    def test_create_and_fetch_account(self, client):
        number = _create_account(client, "alice", "USD")
        resp = client.get(f"{API}/accounts/{number}")
        assert resp.status_code == 200
        assert resp.get_json()["owner_id"] == "alice"

    def test_unknown_account_returns_404(self, client):
        assert client.get(f"{API}/accounts/0000000000").status_code == 404

    def test_validation_error_returns_400(self, client):
        resp = client.post(f"{API}/accounts", json={"owner_id": "x"})  # devise manquante
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"


class TestDepositWebhookApi:
    def _pawapay_webhook(self, client, deposit_id, amount, currency, secret="pawapay_whsec_test"):
        body = json.dumps(
            {"depositId": deposit_id, "status": "COMPLETED", "amount": amount, "currency": currency}
        )
        signature = hmac_sha256_hex(secret, body.encode())
        return client.post(
            f"{API}/payments/webhook/pawapay",
            data=body,
            content_type="application/json",
            headers={"X-Signature": signature},
        )

    def test_deposit_then_webhook_credits_balance(self, client):
        number = _create_account(client, "kamga", "XAF")
        deposit = client.post(
            f"{API}/deposits",
            json={
                "account_number": number,
                "amount": "5000",
                "provider": "pawapay",
                "operator": "mtn",
                "phone_number": "237650000000",
            },
        )
        assert deposit.status_code == 201
        deposit_id = deposit.get_json()["transaction_id"]  # PawaPay : depositId == notre id

        assert self._pawapay_webhook(client, deposit_id, "5000", "XAF").status_code == 200

        balance = client.get(f"{API}/accounts/{number}/balance").get_json()
        assert balance["balance"] == "5000"

    def test_webhook_with_invalid_signature_is_rejected(self, client):
        number = _create_account(client, "kamga", "XAF")
        deposit = client.post(
            f"{API}/deposits",
            json={
                "account_number": number,
                "amount": "5000",
                "provider": "pawapay",
                "operator": "mtn",
                "phone_number": "237650000000",
            },
        )
        deposit_id = deposit.get_json()["transaction_id"]
        # Mauvais secret => signature invalide => refus, aucun crédit.
        resp = self._pawapay_webhook(client, deposit_id, "5000", "XAF", secret="WRONG")
        assert resp.status_code == 401
        assert client.get(f"{API}/accounts/{number}/balance").get_json()["balance"] == "0"


class TestTransfersApi:
    def test_transfer_moves_funds(self, client, fund):
        alice_number = _create_account(client, "alice", "USD")
        bob_number = _create_account(client, "bob", "USD")
        fund(AccountService().get_by_number(alice_number), 200)

        resp = client.post(
            f"{API}/transfers",
            json={
                "sender_account_number": alice_number,
                "receiver_account_number": bob_number,
                "amount": "30",
            },
        )
        assert resp.status_code == 201
        # Les soldes sont sérialisés à la précision de la devise (USD = 2 décimales).
        assert (
            client.get(f"{API}/accounts/{alice_number}/balance").get_json()["balance"] == "170.00"
        )
        assert client.get(f"{API}/accounts/{bob_number}/balance").get_json()["balance"] == "30.00"

    def test_idempotency_key_prevents_double_spend(self, client, fund):
        alice_number = _create_account(client, "alice", "USD")
        bob_number = _create_account(client, "bob", "USD")
        fund(AccountService().get_by_number(alice_number), 200)

        headers = {"Idempotency-Key": "transfer-key-1"}
        payload = {
            "sender_account_number": alice_number,
            "receiver_account_number": bob_number,
            "amount": "50",
        }

        first = client.post(f"{API}/transfers", json=payload, headers=headers)
        second = client.post(f"{API}/transfers", json=payload, headers=headers)

        assert first.status_code == 201
        assert second.status_code == 201
        # Réponse rejouée à l'identique, et un SEUL débit appliqué.
        assert first.get_json()["transaction_id"] == second.get_json()["transaction_id"]
        assert (
            client.get(f"{API}/accounts/{alice_number}/balance").get_json()["balance"] == "150.00"
        )

    def test_reverse_transaction_restores_balance(self, client, fund):
        alice_number = _create_account(client, "alice", "USD")
        bob_number = _create_account(client, "bob", "USD")
        fund(AccountService().get_by_number(alice_number), 200)
        txn = client.post(
            f"{API}/transfers",
            json={
                "sender_account_number": alice_number,
                "receiver_account_number": bob_number,
                "amount": "30",
            },
        ).get_json()

        reversal = client.post(f"{API}/transactions/{txn['transaction_id']}/reverse")
        assert reversal.status_code == 201
        assert reversal.get_json()["type"] == "REVERSAL"
        assert (
            client.get(f"{API}/accounts/{alice_number}/balance").get_json()["balance"] == "200.00"
        )

    def test_insufficient_funds_returns_422(self, client, fund):
        alice_number = _create_account(client, "alice", "USD")
        bob_number = _create_account(client, "bob", "USD")
        resp = client.post(
            f"{API}/transfers",
            json={
                "sender_account_number": alice_number,
                "receiver_account_number": bob_number,
                "amount": "50",
            },
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "INSUFFICIENT_FUNDS"


class TestApiDocs:
    def test_openapi_spec_is_served(self, client):
        spec = client.get(f"{API}/openapi.json").get_json()
        assert spec["openapi"].startswith("3.")
        # Tous les endpoints clés sont documentés.
        assert "/transfers" in spec["paths"]
        assert "/payments/webhook/{provider}" in spec["paths"]

    def test_swagger_ui_is_served(self, client):
        resp = client.get(f"{API}/docs")
        assert resp.status_code == 200
        assert "swagger-ui" in resp.get_data(as_text=True)

    def test_redoc_is_served(self, client):
        resp = client.get(f"{API}/redoc")
        assert resp.status_code == 200
        assert "redoc" in resp.get_data(as_text=True).lower()


class TestFxApi:
    def test_rate(self, client):
        body = client.get(f"{API}/fx/rate?from=USD&to=EUR").get_json()
        assert body["from"] == "USD" and body["to"] == "EUR"
        assert Decimal(body["rate"]) > 0

    def test_convert(self, client):
        body = client.get(f"{API}/fx/convert?from=USD&to=EUR&amount=108").get_json()
        assert body == {"converted_amount": "100.00", "currency": "EUR"}

    def test_fx_transfer_moves_funds_across_currencies(self, client, fund):
        usd = _create_account(client, "alice", "USD")
        eur = _create_account(client, "bob", "EUR")
        fund(AccountService().get_by_number(usd), 200)

        resp = client.post(
            f"{API}/fx/transfer",
            json={"sender_account_number": usd, "receiver_account_number": eur, "amount": "108"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["type"] == "FX_TRANSFER"
        assert client.get(f"{API}/accounts/{usd}/balance").get_json()["balance"] == "92.00"
        assert client.get(f"{API}/accounts/{eur}/balance").get_json()["balance"] == "100.00"

    def test_same_currency_fx_is_rejected(self, client, fund):
        a = _create_account(client, "alice", "USD")
        b = _create_account(client, "bob", "USD")
        fund(AccountService().get_by_number(a), 100)
        resp = client.post(
            f"{API}/fx/transfer",
            json={"sender_account_number": a, "receiver_account_number": b, "amount": "10"},
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "SAME_CURRENCY"


class TestCrossCuttingApi:
    def test_correlation_id_is_returned_and_echoed(self, client):
        resp = client.get("/health", headers={CORRELATION_HEADER: "trace-123"})
        assert resp.headers[CORRELATION_HEADER] == "trace-123"

    def test_transaction_history_is_paginated(self, client, fund):
        alice_number = _create_account(client, "alice", "USD")
        bob_number = _create_account(client, "bob", "USD")
        fund(AccountService().get_by_number(alice_number), 500)
        for _ in range(3):
            client.post(
                f"{API}/transfers",
                json={
                    "sender_account_number": alice_number,
                    "receiver_account_number": bob_number,
                    "amount": "10",
                },
            )

        page = client.get(
            f"{API}/accounts/{alice_number}/transactions?page=1&per_page=2"
        ).get_json()
        assert page["per_page"] == 2
        # 1 dépôt de financement + 3 transferts = 4 transactions touchant Alice.
        assert page["total"] == 4
        assert len(page["items"]) == 2
