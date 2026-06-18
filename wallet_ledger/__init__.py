"""Factory applicative.

On construit l'application via une fabrique pour pouvoir l'instancier différemment en
test et en production (base dédiée, etc.) sans dupliquer le câblage. C'est aussi ici
qu'on branche les abonnés aux événements de domaine (notifications, invalidation du cache).
"""

from __future__ import annotations

import logging

import redis
from flask import Flask

from wallet_ledger import models  # noqa: F401 — l'import enregistre les tables (Alembic)
from wallet_ledger.api.accounts import bp as accounts_bp
from wallet_ledger.api.deposits import bp as deposits_bp
from wallet_ledger.api.docs import bp as docs_bp
from wallet_ledger.api.errors import register_error_handlers
from wallet_ledger.api.fx import bp as fx_bp
from wallet_ledger.api.transactions import bp as transactions_bp
from wallet_ledger.api.transfers import bp as transfers_bp
from wallet_ledger.api.webhooks import bp as webhooks_bp
from wallet_ledger.application.notifications import NotificationService
from wallet_ledger.config import Config
from wallet_ledger.domain.events import (
    DEPOSIT_COMPLETED,
    FUNDS_RESERVED,
    TRANSFER_COMPLETED,
    TRANSFER_FAILED,
    event_bus,
)
from wallet_ledger.extensions import db, migrate
from wallet_ledger.infrastructure.cache import BalanceCache
from wallet_ledger.infrastructure.notifications import EmailChannel, SmsChannel
from wallet_ledger.infrastructure.tracing import init_tracing
from wallet_ledger.seeds import register_cli

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)

    _init_redis(app)
    _register_blueprints(app)
    _register_cross_cutting(app)
    _wire_event_subscribers(app)
    register_cli(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    logging.basicConfig(level=logging.INFO)
    return app


def _init_redis(app: Flask) -> None:
    # On crée le client sans tester la connexion : le cache est tolérant aux pannes,
    # il ne doit pas empêcher l'application de démarrer.
    app.extensions["redis"] = redis.Redis.from_url(app.config["REDIS_URL"])


def _register_blueprints(app: Flask) -> None:
    for blueprint in (
        accounts_bp,
        transfers_bp,
        transactions_bp,
        deposits_bp,
        webhooks_bp,
        fx_bp,
        docs_bp,
    ):
        app.register_blueprint(blueprint, url_prefix=API_PREFIX)


def _register_cross_cutting(app: Flask) -> None:
    register_error_handlers(app)
    init_tracing(app)


def _wire_event_subscribers(app: Flask) -> None:
    """Branche les réactions aux événements : notifier le client et purger le cache de solde."""
    NotificationService(
        [
            EmailChannel(app.config["EMAIL_FROM"]),
            SmsChannel(app.config["SMS_FROM"]),
        ]
    ).register(event_bus)

    # Dès qu'un mouvement touche un compte, on purge son solde en cache pour ne jamais
    # servir une valeur périmée.
    cache = BalanceCache(app.extensions["redis"], app.config["BALANCE_CACHE_TTL_SECONDS"])

    def _invalidate_balances(event):
        for key in ("sender_id", "receiver_id", "account_id"):
            if key in event.payload:
                cache.invalidate(event.payload[key])

    for event_type in (TRANSFER_COMPLETED, TRANSFER_FAILED, DEPOSIT_COMPLETED, FUNDS_RESERVED):
        event_bus.subscribe(event_type, _invalidate_balances)
