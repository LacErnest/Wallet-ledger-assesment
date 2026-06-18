"""Tests des transferts : équilibre comptable, fonds insuffisants, deux phases, et la
garantie clé d'un système financier — pas de solde négatif sous concurrence.
"""

import threading
from decimal import Decimal

import pytest

from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.application.transfers import TransferService
from wallet_ledger.domain.enums import EntryStatus, TransactionStatus
from wallet_ledger.domain.errors import (
    CurrencyMismatchError,
    InsufficientFundsError,
)
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.models.account import Account
from wallet_ledger.models.ledger_entry import LedgerEntry


class TestTransfers:
    def test_transfer_creates_balanced_ledger_entries(self, alice, bob, fund):
        fund(alice, 100)
        txn = TransferService().execute(alice.id, bob.id, Decimal("30"))

        entries = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert sum(e.amount for e in entries) == Decimal(0)  # partie double respectée
        assert LedgerService().balance(alice) == Money("70", "USD")
        assert LedgerService().balance(bob) == Money("30", "USD")

    def test_transfer_fails_when_balance_insufficient(self, alice, bob, fund):
        fund(alice, 20)
        with pytest.raises(InsufficientFundsError):
            TransferService().execute(alice.id, bob.id, Decimal("50"))
        # Aucun mouvement ne doit subsister après un refus.
        assert LedgerService().balance(alice) == Money("20", "USD")
        assert LedgerService().balance(bob) == Money("0", "USD")

    def test_transfer_between_different_currencies_is_rejected(self, alice, make_account, fund):
        bob_eur = make_account("bob_eur", "EUR")
        fund(alice, 100)
        with pytest.raises(CurrencyMismatchError):
            TransferService().execute(alice.id, bob_eur.id, Decimal("10"))

    def test_two_phase_reserve_then_commit(self, alice, bob, fund):
        fund(alice, 100)
        service = TransferService()

        txn = service.initiate(alice.id, bob.id, Decimal("40"))
        assert txn.status == TransactionStatus.PENDING
        # Les fonds sont réservés : disponible réduit, soldé inchangé.
        assert LedgerService().available_balance(alice) == Money("60", "USD")
        assert LedgerService().balance(alice) == Money("100", "USD")

        service.commit(txn.id)
        assert LedgerService().balance(alice) == Money("60", "USD")
        assert LedgerService().balance(bob) == Money("40", "USD")

    def test_two_phase_fail_releases_funds(self, alice, bob, fund):
        fund(alice, 100)
        service = TransferService()
        txn = service.initiate(alice.id, bob.id, Decimal("40"))

        service.fail(txn.id)
        assert txn.status == TransactionStatus.FAILED
        # Le disponible est restauré : l'argent réservé est rendu.
        assert LedgerService().available_balance(alice) == Money("100", "USD")
        pending = LedgerEntry.query.filter_by(
            transaction_id=txn.id, status=EntryStatus.PENDING
        ).count()
        assert pending == 0

    def test_concurrent_transfers_do_not_create_negative_balance(self, app, alice, bob, fund):
        """Alice a 100, deux transferts simultanés de 80 : un seul doit passer.

        Sans verrouillage réel, les deux liraient « 100 disponible » et régleraient,
        laissant Alice à -60. Le verrou de ligne PostgreSQL l'en empêche.
        """
        fund(alice, 100)
        # On fige les identifiants en chaînes : chaque thread doit travailler sur sa
        # propre session, sans jamais toucher un objet ORM lié à la session du test.
        alice_id, bob_id = alice.id, bob.id
        results: list[str] = []

        def worker():
            with app.app_context():
                try:
                    TransferService().execute(alice_id, bob_id, Decimal("80"))
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
        alice_reloaded = db.session.get(Account, alice_id)
        assert LedgerService().balance(alice_reloaded) == Money("20", "USD")
