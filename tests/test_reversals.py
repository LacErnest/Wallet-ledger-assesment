"""Tests d'annulation : une correction se fait par contre-passation, jamais en
modifiant les écritures d'origine (qui sont immuables).
"""

from decimal import Decimal

import pytest

from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.application.reversals import ReversalService
from wallet_ledger.application.transfers import TransferService
from wallet_ledger.domain.enums import EntryStatus, TransactionStatus, TransactionType
from wallet_ledger.domain.errors import InvalidTransactionStateError
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction


class TestReversals:
    def test_reversal_restores_balances(self, alice, bob, fund):
        fund(alice, 200)
        txn = TransferService().execute(alice.id, bob.id, Decimal("30"))

        reversal = ReversalService().reverse(txn.id)

        assert reversal.type == TransactionType.REVERSAL
        assert LedgerService().balance(alice) == Money("200", "USD")
        assert LedgerService().balance(bob) == Money("0", "USD")

    def test_original_is_marked_reversed_but_entries_untouched(self, alice, bob, fund):
        fund(alice, 200)
        txn = TransferService().execute(alice.id, bob.id, Decimal("30"))
        ReversalService().reverse(txn.id)

        assert db.session.get(Transaction, txn.id).status == TransactionStatus.REVERSED
        # Les écritures d'origine restent SUCCESS : on ne réécrit pas le passé.
        original = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert all(e.status == EntryStatus.SUCCESS for e in original)

    def test_reversal_entries_sum_to_zero(self, alice, bob, fund):
        fund(alice, 200)
        txn = TransferService().execute(alice.id, bob.id, Decimal("30"))
        reversal = ReversalService().reverse(txn.id)

        entries = LedgerEntry.query.filter_by(transaction_id=reversal.id).all()
        assert sum(e.amount for e in entries) == Decimal(0)

    def test_cannot_reverse_a_pending_transaction(self, alice, bob, fund):
        fund(alice, 200)
        txn = TransferService().initiate(alice.id, bob.id, Decimal("30"))  # PENDING
        with pytest.raises(InvalidTransactionStateError):
            ReversalService().reverse(txn.id)

    def test_cannot_reverse_twice(self, alice, bob, fund):
        fund(alice, 200)
        txn = TransferService().execute(alice.id, bob.id, Decimal("30"))
        ReversalService().reverse(txn.id)
        with pytest.raises(InvalidTransactionStateError):
            ReversalService().reverse(txn.id)

    def test_cannot_reverse_a_reversal(self, alice, bob, fund):
        fund(alice, 200)
        txn = TransferService().execute(alice.id, bob.id, Decimal("30"))
        reversal = ReversalService().reverse(txn.id)
        with pytest.raises(InvalidTransactionStateError):
            ReversalService().reverse(reversal.id)
