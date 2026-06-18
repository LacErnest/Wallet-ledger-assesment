"""Sondes de santé : vivacité (liveness) et disponibilité (readiness).

On distingue les deux car l'orchestrateur en a besoin séparément : « le process tourne »
(liveness) ne veut pas dire « il peut servir » (readiness). Tant que la base ou le cache
ne répondent pas, on se déclare indisponible pour ne pas recevoir de trafic.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from wallet_ledger.extensions import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def liveness():
    return {"status": "ok"}


@bp.get("/health/ready")
def readiness():
    checks = {"database": _check(_ping_database), "redis": _check(_ping_redis)}
    ready = all(status == "ok" for status in checks.values())
    return jsonify({"status": "ready" if ready else "degraded", "checks": checks}), (
        200 if ready else 503
    )


def _check(probe) -> str:
    try:
        probe()
        return "ok"
    except Exception:  # noqa: BLE001 — toute panne de dépendance => non prêt
        return "down"


def _ping_database() -> None:
    db.session.execute(text("SELECT 1"))


def _ping_redis() -> None:
    current_app.extensions["redis"].ping()
