"""Jeu de données de démonstration.

But : qu'un évaluateur qui lance le projet ait immédiatement des comptes et un
historique à explorer, sans devoir tout créer à la main. Le seeder est idempotent
(rejouable sans dupliquer) et alimente les soldes directement via le grand livre,
sans dépendre d'un appel réseau à un fournisseur.
"""

from __future__ import annotations

from decimal import Decimal

import click
from flask import Flask

from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.application.transfers import TransferService
from wallet_ledger.domain.enums import TransactionStatus, TransactionType
from wallet_ledger.extensions import db
from wallet_ledger.models.account import Account
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction

_CLEARING_OWNER = "PLATFORM_CLEARING"


def _fund(account: Account, amount: Decimal) -> None:
    """Crédite un compte depuis le compte de compensation (écritures équilibrées)."""
    accounts = AccountService()
    clearing = accounts.get_or_create_internal(_CLEARING_OWNER, account.currency)
    txn = Transaction(
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.SUCCESS,
        amount=amount,
        currency=account.currency,
    )
    db.session.add(txn)
    db.session.flush()
    LedgerService().post_entries(
        [
            LedgerEntry.debit(clearing.id, txn.id, amount, account.currency),
            LedgerEntry.credit(account.id, txn.id, amount, account.currency),
        ]
    )
    db.session.commit()


def seed() -> dict[str, str]:
    """Crée les comptes de démonstration et un peu d'historique. Idempotent."""
    accounts = AccountService()
    existing = Account.query.filter_by(owner_id="alice", currency="USD").first()
    if existing is not None:
        bob = Account.query.filter_by(owner_id="bob", currency="USD").first()
        kamga = Account.query.filter_by(owner_id="kamga", currency="XAF").first()
        return {"alice": existing.number, "bob": bob.number, "kamga": kamga.number}

    alice = accounts.create("alice", "USD")
    bob = accounts.create("bob", "USD")
    kamga = accounts.create("kamga", "XAF")

    _fund(alice, Decimal("200"))
    _fund(kamga, Decimal("5000"))
    TransferService().execute(alice.id, bob.id, Decimal("30"))

    return {"alice": alice.number, "bob": bob.number, "kamga": kamga.number}


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_command():
        """Peuple la base de comptes et transactions de démonstration."""
        for owner, number in seed().items():
            click.echo(f"  {owner:<8} -> compte n° {number}")
        click.echo("Données de démonstration prêtes.")
