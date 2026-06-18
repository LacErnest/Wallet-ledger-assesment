"""Tests des dépôts : crédit correct, et surtout réconciliation du montant — un
fournisseur ne doit jamais pouvoir créditer un montant différent de l'autorisé.
"""

import threading
from decimal import Decimal

import pytest

from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.deposits import DepositService
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.domain.enums import TransactionStatus
from wallet_ledger.domain.errors import DepositAmountMismatchError, InvalidTransactionStateError
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.models.ledger_entry import LedgerEntry


class TestDeposits:
    def test_deposit_via_stripe_credits_account(self, alice):
        service = DepositService()
        txn = service.initiate(alice.id, Decimal("200"), "stripe")
        assert txn.status == TransactionStatus.PENDING

        # Le fournisseur confirme le montant exact attendu.
        settled = service.settle(txn.reference, Decimal("200"))
        assert settled.status == TransactionStatus.SUCCESS
        assert LedgerService().balance(alice) == Money("200", "USD")

        entries = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert sum(e.amount for e in entries) == Decimal(0)  # partie double

    def test_deposit_via_pawapay_mtn_credits_account(self, make_account):
        account = make_account("kamga", "XAF")
        service = DepositService()
        txn = service.initiate(
            account.id,
            Decimal("5000"),
            "pawapay",
            context={"operator": "mtn", "phone_number": "237650000000"},
        )
        service.settle(txn.reference, Decimal("5000"))
        assert LedgerService().balance(account) == Money("5000", "XAF")

    def test_confirmed_amount_mismatch_is_rejected(self, alice):
        service = DepositService()
        txn = service.initiate(alice.id, Decimal("100"), "stripe")

        # Le fournisseur tente de confirmer un montant supérieur à l'autorisé.
        with pytest.raises(DepositAmountMismatchError):
            service.settle(txn.reference, Decimal("1000000"))

        assert LedgerService().balance(alice) == Money("0", "USD")  # rien crédité
        assert txn.status == TransactionStatus.PENDING

    def test_settling_twice_is_rejected(self, alice):
        service = DepositService()
        txn = service.initiate(alice.id, Decimal("50"), "stripe")
        service.settle(txn.reference, Decimal("50"))

        # Un webhook rejoué ne doit pas créditer une seconde fois.
        with pytest.raises(InvalidTransactionStateError):
            service.settle(txn.reference, Decimal("50"))
        assert LedgerService().balance(alice) == Money("50", "USD")

    def test_concurrent_settlements_credit_only_once(self, app, make_account):
        """Deux confirmations simultanées du même dépôt : une seule crédite (verrou de ligne)."""
        account = make_account("kamga", "XAF")
        txn = DepositService().initiate(
            account.id,
            Decimal("5000"),
            "pawapay",
            context={"operator": "mtn", "phone_number": "237650000000"},
        )
        reference, account_number = txn.reference, account.number
        results: list[str] = []

        def worker():
            with app.app_context():
                try:
                    DepositService().settle(reference, Decimal("5000"), "XAF")
                    results.append("ok")
                except InvalidTransactionStateError:
                    results.append("rejected")
                finally:
                    db.session.remove()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert results.count("ok") == 1
        assert results.count("rejected") == 1
        account_reloaded = AccountService().get_by_number(account_number)
        assert LedgerService().balance(account_reloaded) == Money("5000", "XAF")
