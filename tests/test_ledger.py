"""Tests du grand livre : le solde se déduit des écritures, et la partie double tient."""

from decimal import Decimal

import pytest

from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.domain.enums import EntryStatus, EntryType, TransactionStatus, TransactionType
from wallet_ledger.domain.errors import LedgerNotBalancedError
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.models.balance_snapshot import BalanceSnapshot
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction


def _credit_debit(account_id, clearing_id, amount, currency="USD", status=EntryStatus.SUCCESS):
    """Paire équilibrée : on crédite un compte et on débite la contrepartie."""
    txn = Transaction(
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.SUCCESS,
        amount=Decimal(amount),
        currency=currency,
    )
    db.session.add(txn)
    db.session.flush()
    return txn, [
        LedgerEntry(
            account_id=clearing_id,
            transaction_id=txn.id,
            amount=Decimal(-amount),
            entry_type=EntryType.DEBIT,
            status=status,
            currency=currency,
        ),
        LedgerEntry(
            account_id=account_id,
            transaction_id=txn.id,
            amount=Decimal(amount),
            entry_type=EntryType.CREDIT,
            status=status,
            currency=currency,
        ),
    ]


class TestLedger:
    def test_balance_computed_correctly_from_ledger(self, alice, make_account):
        clearing = make_account("clearing", "USD")
        ledger = LedgerService()

        for amount in (100, 50, 20):
            _txn, entries = _credit_debit(alice.id, clearing.id, amount)
            ledger.post_entries(entries)
        db.session.commit()

        assert ledger.balance(alice) == Money("170", "USD")
        # La contrepartie porte le miroir négatif : l'argent n'est ni créé ni détruit.
        assert ledger.balance(clearing) == Money("-170", "USD")

    def test_post_entries_rejects_unbalanced_set(self, alice, make_account):
        clearing = make_account("clearing", "USD")
        ledger = LedgerService()
        txn = Transaction(
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.SUCCESS,
            amount=Decimal(100),
            currency="USD",
        )
        db.session.add(txn)
        db.session.flush()

        unbalanced = [
            LedgerEntry(
                account_id=alice.id,
                transaction_id=txn.id,
                amount=Decimal(100),
                entry_type=EntryType.CREDIT,
                status=EntryStatus.SUCCESS,
                currency="USD",
            ),
            LedgerEntry(
                account_id=clearing.id,
                transaction_id=txn.id,
                amount=Decimal(-90),
                entry_type=EntryType.DEBIT,
                status=EntryStatus.SUCCESS,
                currency="USD",
            ),
        ]
        with pytest.raises(LedgerNotBalancedError):
            ledger.post_entries(unbalanced)

    def test_pending_debit_reduces_available_but_not_settled(self, alice, make_account):
        clearing = make_account("clearing", "USD")
        ledger = LedgerService()
        _txn, funded = _credit_debit(alice.id, clearing.id, 100)
        ledger.post_entries(funded)
        db.session.flush()

        # Réservation : un débit PENDING de 30 sur Alice (contrepartie en attente aussi).
        reserve_txn = Transaction(
            type=TransactionType.TRANSFER,
            status=TransactionStatus.PENDING,
            amount=Decimal(30),
            currency="USD",
        )
        db.session.add(reserve_txn)
        db.session.flush()
        db.session.add(
            LedgerEntry(
                account_id=alice.id,
                transaction_id=reserve_txn.id,
                amount=Decimal(-30),
                entry_type=EntryType.DEBIT,
                status=EntryStatus.PENDING,
                currency="USD",
            )
        )
        db.session.commit()

        assert ledger.balance(alice) == Money("100", "USD")  # soldé inchangé
        assert ledger.available_balance(alice) == Money("70", "USD")  # disponible réduit

    def test_snapshot_matches_full_recomputation(self, alice, make_account, app):
        clearing = make_account("clearing", "USD")
        ledger = LedgerService()
        app.config["SNAPSHOT_EVERY_N_ENTRIES"] = 5

        for _ in range(12):
            _txn, entries = _credit_debit(alice.id, clearing.id, 10)
            ledger.post_entries(entries)
            db.session.flush()
            ledger.maybe_snapshot(alice)
        db.session.commit()

        # Un instantané a forcément été coupé ; le solde via instantané+delta doit
        # rester identique à la somme brute de toutes les écritures.
        assert ledger.balance(alice) == Money("120", "USD")
        assert BalanceSnapshot.query.filter_by(account_id=alice.id).count() >= 1
