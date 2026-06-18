"""Tests du change : conversion correcte et, surtout, équilibre par devise — un
transfert multi-devises ne doit créer ni détruire d'argent dans aucune des deux devises.
"""

from collections import defaultdict
from decimal import Decimal

import pytest

from wallet_ledger.application.fx import FxService
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.domain.errors import InsufficientFundsError, SameCurrencyError
from wallet_ledger.domain.money import Money
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
