"""Endpoints comptes : création, consultation, solde (dérivé du grand livre) et historique."""

from __future__ import annotations

from flask import Blueprint, current_app, request

from wallet_ledger.api.schemas import CreateAccountSchema
from wallet_ledger.api.serializers import serialize_account, serialize_balance, serialize_transaction
from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.balance_query import BalanceQuery
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.extensions import db
from wallet_ledger.infrastructure.cache import BalanceCache
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction

bp = Blueprint("accounts", __name__)
_accounts = AccountService()


def _balance_query() -> BalanceQuery:
    cache = BalanceCache(current_app.extensions.get("redis"), current_app.config["BALANCE_CACHE_TTL_SECONDS"])
    return BalanceQuery(LedgerService(), cache)


@bp.post("/accounts")
def create_account():
    data = CreateAccountSchema().load(request.get_json(silent=True) or {})
    account = _accounts.create(data["owner_id"], data["currency"])
    return serialize_account(account), 201


@bp.get("/accounts/<number>")
def get_account(number: str):
    return serialize_account(_accounts.get_by_number(number))


@bp.get("/accounts/<number>/balance")
def get_balance(number: str):
    account = _accounts.get_by_number(number)
    return serialize_balance(account, _balance_query().get(account))


@bp.get("/accounts/<number>/transactions")
def list_transactions(number: str):
    account = _accounts.get_by_number(number)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Une transaction concerne le compte dès qu'elle porte une écriture sur lui.
    query = (
        db.select(Transaction)
        .join(LedgerEntry, LedgerEntry.transaction_id == Transaction.id)
        .where(LedgerEntry.account_id == account.id)
        .distinct()
        .order_by(Transaction.created_at.desc())
    )
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
    return {
        "items": [serialize_transaction(t) for t in pagination.items],
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    }
