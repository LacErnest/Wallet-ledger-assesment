"""Factory applicative.

On construit l'application via une fabrique pour pouvoir l'instancier différemment
en test et en production (base dédiée, etc.) sans dupliquer le câblage.
"""

from __future__ import annotations

import logging

from flask import Flask

from wallet_ledger.config import Config
from wallet_ledger.extensions import db, migrate


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)

    # Importer les modèles enregistre toutes les tables sur les métadonnées, ce dont
    # Alembic a besoin pour générer les migrations.
    from wallet_ledger import models  # noqa: F401

    from wallet_ledger.api.errors import register_error_handlers

    register_error_handlers(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    logging.basicConfig(level=logging.INFO)
    return app
