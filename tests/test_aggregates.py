"""Tests des racines d'agrégat : elles POSSÈDENT les invariants du domaine.

Ce sont des objets purs (aucune base) : on peut donc vérifier les règles métier en
isolation totale, ce qui est tout l'intérêt de mettre les invariants sur l'agrégat.
"""

from decimal import Decimal

import pytest

from wallet_ledger.domain.aggregates import AccountAggregate, TransactionAggregate
from wallet_ledger.domain.enums import EntryType
from wallet_ledger.domain.errors import InsufficientFundsError, LedgerNotBalancedError
from wallet_ledger.domain.money import Money


class TestTransactionAggregate:
    def test_debit_is_negative_credit_is_positive(self):
        aggregate = TransactionAggregate("USD")
        aggregate.debit("a", Money("30", "USD"))
        aggregate.credit("b", Money("30", "USD"))

        debit, credit = aggregate.lines
        assert debit.amount == Decimal("-30.00") and debit.entry_type == EntryType.DEBIT
        assert credit.amount == Decimal("30.00") and credit.entry_type == EntryType.CREDIT

    def test_balanced_set_passes(self):
        aggregate = TransactionAggregate("USD")
        aggregate.debit("a", Money("30", "USD"))
        aggregate.credit("b", Money("30", "USD"))
        aggregate.assert_balanced()  # ne lève pas

    def test_unbalanced_set_is_rejected(self):
        aggregate = TransactionAggregate("USD")
        aggregate.debit("a", Money("30", "USD"))
        aggregate.credit("b", Money("20", "USD"))
        with pytest.raises(LedgerNotBalancedError):
            aggregate.assert_balanced()

    def test_zero_sum_is_enforced_per_currency(self):
        # Cas FX : chaque devise doit s'équilibrer séparément.
        aggregate = TransactionAggregate("USD")
        aggregate.debit("alice", Money("108", "USD"))
        aggregate.credit("pool_usd", Money("108", "USD"))
        aggregate.debit("pool_eur", Money("100", "EUR"))
        aggregate.credit("bob", Money("100", "EUR"))
        aggregate.assert_balanced()

    def test_imbalance_in_one_currency_is_caught(self):
        aggregate = TransactionAggregate("USD")
        aggregate.debit("alice", Money("108", "USD"))
        aggregate.credit("pool_usd", Money("108", "USD"))
        aggregate.debit("pool_eur", Money("100", "EUR"))  # pas de contrepartie EUR
        with pytest.raises(LedgerNotBalancedError):
            aggregate.assert_balanced()


class TestAccountAggregate:
    def test_allows_debit_within_available(self):
        AccountAggregate("a", "USD").ensure_can_debit(Money("30", "USD"), Money("100", "USD"))

    def test_rejects_overdraft(self):
        with pytest.raises(InsufficientFundsError):
            AccountAggregate("a", "USD").ensure_can_debit(Money("150", "USD"), Money("100", "USD"))
