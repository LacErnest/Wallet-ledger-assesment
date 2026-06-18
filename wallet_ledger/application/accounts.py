"""Accès aux comptes : création, lecture et verrouillage.

Centraliser ces opérations (plutôt que les répéter dans chaque service) garantit que
le verrou de ligne et la règle « un compte par devise » s'appliquent partout pareil.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from wallet_ledger.domain.errors import AccountNotFoundError, DuplicateAccountError
from wallet_ledger.extensions import db
from wallet_ledger.models.account import Account


class AccountService:
    def create(self, owner_id: str, currency: str) -> Account:
        account = Account(owner_id=owner_id, currency=currency.upper())
        db.session.add(account)
        try:
            db.session.commit()
        except IntegrityError:
            # La contrainte d'unicité (propriétaire, devise) a parlé : pas de doublon.
            db.session.rollback()
            raise DuplicateAccountError(owner_id, currency)
        return account

    def get(self, account_id: str) -> Account:
        account = db.session.get(Account, account_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        return account

    def get_by_number(self, number: str) -> Account:
        account = Account.query.filter_by(number=number).first()
        if account is None:
            raise AccountNotFoundError(number)
        return account

    def lock(self, account_id: str) -> Account:
        # Verrou de ligne : sérialise les opérations concurrentes sur le même compte
        # pour qu'un contrôle de solde ne s'appuie jamais sur une lecture périmée.
        account = db.session.query(Account).filter_by(id=account_id).with_for_update().first()
        if account is None:
            raise AccountNotFoundError(account_id)
        return account

    def get_or_create_internal(self, owner_id: str, currency: str) -> Account:
        """Comptes internes (compensation, pool de change) : créés à la demande, une seule fois."""
        account = Account.query.filter_by(owner_id=owner_id, currency=currency.upper()).first()
        if account is None:
            account = Account(owner_id=owner_id, currency=currency.upper())
            db.session.add(account)
            db.session.flush()
        return account
