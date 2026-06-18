"""Traçabilité distribuée via un `correlation_id`.

Un même identifiant suit la requête, les événements, les écritures et les notifications.
En cas de litige sur un mouvement d'argent, on peut ainsi reconstituer toute la chaîne.
"""

from __future__ import annotations

import uuid

from flask import Flask, g, request

CORRELATION_HEADER = "X-Correlation-ID"


def init_tracing(app: Flask) -> None:
    @app.before_request
    def _assign_correlation_id():
        # On respecte un identifiant fourni par l'appelant (utile pour relier plusieurs
        # services entre eux), sinon on en génère un.
        g.correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())

    @app.after_request
    def _return_correlation_id(response):
        response.headers[CORRELATION_HEADER] = g.get("correlation_id", "")
        return response


def get_correlation_id() -> str | None:
    return g.get("correlation_id")
