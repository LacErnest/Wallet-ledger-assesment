"""Tests du change : conversion correcte et, surtout, équilibre par devise — un
transfert multi-devises ne doit créer ni détruire d'argent dans aucune des deux devises.
"""

import threading
from collections import defaultdict
from decimal import Decimal

import pytest

from wallet_ledger.application.fx import FxService
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.domain.errors import InsufficientFundsError, SameCurrencyError
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.models.account import Account
from wallet_ledger.models.ledger_entry import LedgerEntry


class TestFx:
    def test_rate_and_conversion(self):
        service = FxService()
        # 1 EUR = 1.08 USD => 108 USD valent 100 EUR.
        assert service.convert(Money("108", "USD"), "EUR") == Money("100", "EUR")

    def test_fx_transfer_moves_funds_across_currencies(self, alice, make_account, fund):
        bob_eur = make_account("bob_eur", "EUR")
        fund(alice, 200)

        FxService().execute_fx_transfer(alice.id, bob_eur.id, Decimal("108"))

        assert LedgerService().balance(alice) == Money("92", "USD")
        assert LedgerService().balance(bob_eur) == Money("100", "EUR")

    def test_fx_transfer_balances_to_zero_per_currency(self, alice, make_account, fund):
        bob_eur = make_account("bob_eur", "EUR")
        fund(alice, 200)
        txn = FxService().execute_fx_transfer(alice.id, bob_eur.id, Decimal("108"))

        totals = defaultdict(Decimal)
        for entry in LedgerEntry.query.filter_by(transaction_id=txn.id).all():
            totals[entry.currency] += entry.amount
        assert totals["USD"] == Decimal(0)
        assert totals["EUR"] == Decimal(0)

    def test_fx_transfer_requires_funds(self, alice, make_account, fund):
        bob_eur = make_account("bob_eur", "EUR")
        fund(alice, 50)
        with pytest.raises(InsufficientFundsError):
            FxService().execute_fx_transfer(alice.id, bob_eur.id, Decimal("108"))

    def test_same_currency_is_rejected(self, alice, bob, fund):
        fund(alice, 100)
        with pytest.raises(SameCurrencyError):
            FxService().execute_fx_transfer(alice.id, bob.id, Decimal("10"))

    def test_concurrent_fx_transfers_do_not_overdraw(self, app, alice, make_account, fund):
        """Le verrou de ligne sur l'expéditeur protège aussi le change : deux transferts
        FX simultanés de 108 USD avec seulement 150 USD ne peuvent pas tous deux passer.
        """
        bob_eur = make_account("bob_eur", "EUR")
        fund(alice, 150)
        alice_id, receiver_id = alice.id, bob_eur.id
        results: list[str] = []

        def worker():
            with app.app_context():
                try:
                    FxService().execute_fx_transfer(alice_id, receiver_id, Decimal("108"))
                    results.append("ok")
                except InsufficientFundsError:
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
        # L'expéditeur n'est jamais négatif : il reste 150 - 108 = 42 USD.
        alice_reloaded = db.session.get(Account, alice_id)
        assert LedgerService().balance(alice_reloaded) == Money("42", "USD")
