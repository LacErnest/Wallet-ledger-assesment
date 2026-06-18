"""Traduction des erreurs métier en statuts HTTP.

Le domaine ignore HTTP volontairement ; c'est ici, à la frontière, qu'on décide
qu'un « fonds insuffisant » devient un 422 et un « compte introuvable » un 404.
"""

from __future__ import annotations

from flask import Flask, jsonify

from wallet_ledger.domain.errors import DomainError

# Correspondance code métier -> statut HTTP. Tout code absent retombe sur 400.
_STATUS_BY_CODE = {
    "ACCOUNT_NOT_FOUND": 404,
    "TRANSACTION_NOT_FOUND": 404,
    "INSUFFICIENT_FUNDS": 422,
    "CURRENCY_MISMATCH": 422,
    "INVALID_TRANSACTION_STATE": 409,
    "LEDGER_NOT_BALANCED": 422,
    "DEPOSIT_AMOUNT_MISMATCH": 422,
    "RISK_REJECTED": 422,
    "DUPLICATE_ACCOUNT": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "WEBHOOK_VERIFICATION_FAILED": 401,
    "UNSUPPORTED_PROVIDER": 400,
}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(DomainError)
    def _handle_domain_error(error: DomainError):
        status = _STATUS_BY_CODE.get(error.code, 400)
        return jsonify({"error": error.message, "code": error.code}), status

    @app.errorhandler(404)
    def _handle_not_found(_error):
        return jsonify({"error": "Ressource introuvable", "code": "NOT_FOUND"}), 404
