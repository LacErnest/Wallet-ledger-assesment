"""Idempotence des requêtes POST (décorateur).

Pourquoi : un client qui ne reçoit pas la réponse rejoue sa requête. Sans protection,
un transfert pourrait être exécuté deux fois. On RÉSERVE la clé d'idempotence (insertion
soumise à une contrainte d'unicité) AVANT d'exécuter l'opération. Deux requêtes
simultanées portant la même clé : une seule passe, l'autre est refoulée.
"""

from __future__ import annotations

import hashlib
import json
from functools import wraps

from flask import jsonify, make_response, request
from sqlalchemy.exc import IntegrityError

from wallet_ledger.extensions import db
from wallet_ledger.models.idempotency import IdempotencyKey

IDEMPOTENCY_HEADER = "Idempotency-Key"


def _request_hash() -> str:
    return hashlib.sha256(request.get_data() or b"").hexdigest()


def _serialize(response) -> tuple[str, int]:
    """Normalise le retour d'une vue en (corps JSON, statut) pour pouvoir le rejouer."""
    body, status = (response if isinstance(response, tuple) else (response, 200))
    if hasattr(body, "get_json"):
        body = body.get_json()
    return json.dumps(body), status


def _conflict(message: str):
    return make_response(jsonify({"error": message, "code": "IDEMPOTENCY_CONFLICT"}), 409)


def _resolve_duplicate(key: str, request_hash: str):
    existing = IdempotencyKey.query.filter_by(key=key).first()
    if existing is None:
        return _conflict("Clé d'idempotence non résolue")
    if existing.request_hash != request_hash:
        return _conflict("Clé d'idempotence réutilisée avec un corps différent")
    if not existing.is_completed:
        # La requête d'origine tourne encore : laisser passer celle-ci créerait un doublon.
        return _conflict("Une requête avec cette clé est déjà en cours")
    return make_response(json.loads(existing.response_body), existing.response_status)


def idempotent(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            return view(*args, **kwargs)

        request_hash = _request_hash()

        # On pose la clé d'abord : la contrainte d'unicité est l'unique arbitre de
        # « qui a le droit d'exécuter l'opération ».
        db.session.add(IdempotencyKey(key=key, request_hash=request_hash))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return _resolve_duplicate(key, request_hash)

        try:
            response = view(*args, **kwargs)
        except Exception:
            # Échec inattendu : on libère la clé pour qu'un nouvel essai soit possible.
            db.session.rollback()
            claim = IdempotencyKey.query.filter_by(key=key).first()
            if claim is not None and not claim.is_completed:
                db.session.delete(claim)
                db.session.commit()
            raise

        body, status = _serialize(response)
        claim = IdempotencyKey.query.filter_by(key=key).first()
        claim.response_status = status
        claim.response_body = body
        db.session.commit()
        return response

    return wrapper
