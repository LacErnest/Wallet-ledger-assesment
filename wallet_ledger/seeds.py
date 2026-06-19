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


def fund_account(number: str, amount: Decimal) -> Account:
    """Crédite un compte existant (identifié par son numéro). Pratique pour les démos."""
    account = AccountService().get_by_number(number)
    _fund(account, amount)
    return account


def _ensure(owner_id: str, currency: str, fund_amount: Decimal | None) -> tuple[Account, bool]:
    """Récupère un compte (par propriétaire + devise) ou le crée et le finance. Idempotent."""
    account = Account.query.filter_by(owner_id=owner_id, currency=currency).first()
    if account is not None:
        return account, False
    account = AccountService().create(owner_id, currency)
    if fund_amount is not None:
        _fund(account, fund_amount)
    return account, True


def seed() -> dict[str, str]:
    """Crée les comptes de démonstration et un peu d'historique. Idempotent (par compte)."""
    alice, alice_created = _ensure("alice", "USD", Decimal("200"))
    bob, _ = _ensure("bob", "USD", None)
    kamga, _ = _ensure("kamga", "XAF", Decimal("5000"))
    # Compte en EUR financé : permet de tester un transfert multi-devises (EUR -> USD)
    # sans rien préparer d'autre.
    claire, _ = _ensure("claire", "EUR", Decimal("100"))

    # Le transfert de démo ne s'exécute qu'à la première création, pour rester idempotent.
    if alice_created:
        TransferService().execute(alice.id, bob.id, Decimal("30"))

    return {
        "alice": alice.number,
        "bob": bob.number,
        "kamga": kamga.number,
        "claire": claire.number,
    }


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_command():
        """Peuple la base de comptes et transactions de démonstration."""
        for owner, number in seed().items():
            click.echo(f"  {owner:<8} -> compte n° {number}")
        click.echo("Données de démonstration prêtes.")

    @app.cli.command("fund")
    @click.argument("number")
    @click.argument("amount")
    def fund_command(number: str, amount: str):
        """Crédite un compte : flask fund <numéro> <montant>."""
        account = fund_account(number, Decimal(amount))
        click.echo(f"Crédité {amount} {account.currency} sur le compte {number}.")
