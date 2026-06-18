"""Fixtures de test.

On teste contre un vrai PostgreSQL (et non SQLite) : la garantie « pas de solde
négatif sous concurrence » repose sur le verrouillage réel de la base, qu'un moteur
en mémoire ne reproduit pas. Chaque test repart d'une base vide.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text

from wallet_ledger import create_app
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.config import TestConfig
from wallet_ledger.domain.enums import (
    EntryStatus,
    EntryType,
    TransactionStatus,
    TransactionType,
)
from wallet_ledger.extensions import db as _db
from wallet_ledger.models.account import Account
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction


@pytest.fixture(scope="session")
def app():
    application = create_app(TestConfig)
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(autouse=True)
def _clean_db(app):
    # Après chaque test : on vide tout et on remet les séquences à zéro, pour que le
    # curseur `seq` des écritures soit déterministe d'un test à l'autre.
    yield
    _db.session.rollback()
    tables = ", ".join(table.name for table in _db.metadata.sorted_tables)
    _db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    _db.session.commit()


@pytest.fixture
def session(app):
    return _db.session


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_account(app):
    """Fabrique de comptes pour les tests."""

    def _make(owner_id: str, currency: str = "USD") -> Account:
        account = Account(owner_id=owner_id, currency=currency)
        _db.session.add(account)
        _db.session.commit()
        return account

    return _make


@pytest.fixture
def alice(make_account):
    return make_account("alice", "USD")


@pytest.fixture
def bob(make_account):
    return make_account("bob", "USD")


@pytest.fixture
def fund(app):
    """Crédite un compte (depuis un compte de compensation) pour préparer un scénario."""

    def _fund(account: Account, amount) -> None:
        clearing = Account.query.filter_by(owner_id="CLEARING", currency=account.currency).first()
        if clearing is None:
            clearing = Account(owner_id="CLEARING", currency=account.currency)
            _db.session.add(clearing)
            _db.session.flush()

        txn = Transaction(type=TransactionType.DEPOSIT, status=TransactionStatus.SUCCESS,
                          amount=Decimal(amount), currency=account.currency)
        _db.session.add(txn)
        _db.session.flush()
        LedgerService().post_entries([
            LedgerEntry(account_id=clearing.id, transaction_id=txn.id, amount=Decimal(-amount),
                        entry_type=EntryType.DEBIT, status=EntryStatus.SUCCESS, currency=account.currency),
            LedgerEntry(account_id=account.id, transaction_id=txn.id, amount=Decimal(amount),
                        entry_type=EntryType.CREDIT, status=EntryStatus.SUCCESS, currency=account.currency),
        ])
        _db.session.commit()

    return _fund
