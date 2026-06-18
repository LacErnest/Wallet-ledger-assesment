"""Tests du Value Object Money : ce sont les lois fondamentales de l'argent dans le
système. S'ils cassent, toute la comptabilité devient suspecte.
"""

from decimal import Decimal

import pytest

from wallet_ledger.domain.errors import CurrencyMismatchError
from wallet_ledger.domain.money import Money


class TestMoney:
    def test_float_is_rejected(self):
        # Le flottant introduit des erreurs d'arrondi : interdit dès la construction.
        with pytest.raises(TypeError):
            Money(0.1, "USD")

    def test_accepts_decimal_int_and_str(self):
        assert Money(Decimal("10"), "USD").amount == Decimal("10.00")
        assert Money(10, "USD").amount == Decimal("10.00")
        assert Money("10", "USD").amount == Decimal("10.00")

    def test_quantizes_to_currency_decimals(self):
        # USD a 2 décimales, JPY n'en a aucune.
        assert Money("10.005", "USD").amount == Decimal("10.00")  # arrondi du banquier
        assert Money("10.50", "JPY").amount == Decimal("10")
        assert Money("10.50", "XAF").amount == Decimal("10")

    def test_currency_is_normalized_uppercase(self):
        assert Money("5", "usd").currency == "USD"

    def test_addition_and_subtraction_same_currency(self):
        assert Money("10", "USD") + Money("5", "USD") == Money("15", "USD")
        assert Money("10", "USD") - Money("5", "USD") == Money("5", "USD")

    def test_cross_currency_arithmetic_is_forbidden(self):
        with pytest.raises(CurrencyMismatchError):
            Money("10", "USD") + Money("5", "EUR")
        with pytest.raises(CurrencyMismatchError):
            Money("10", "USD") < Money("5", "EUR")

    def test_comparisons(self):
        assert Money("10", "USD") > Money("5", "USD")
        assert Money("5", "USD") <= Money("5", "USD")

    def test_predicates(self):
        assert Money("1", "USD").is_positive()
        assert Money("-1", "USD").is_negative()
        assert Money("0", "USD").is_zero()

    def test_is_immutable(self):
        money = Money("10", "USD")
        with pytest.raises(Exception):
            money.amount = Decimal("20")

    def test_is_hashable(self):
        # Un Value Object doit pouvoir servir de clé / entrer dans un set.
        assert len({Money("10", "USD"), Money("10", "USD")}) == 1
