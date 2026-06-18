"""Journalisation structurée (JSON) enrichie du correlation_id.

Pourquoi : en production, les logs sont agrégés par une machine (ELK, Loki…). Du JSON
se filtre et se corrèle, là où du texte libre se cherche à la main. Surtout, chaque
ligne porte le correlation_id de la requête : en cas d'incident sur un paiement, on
retrouve toute la chaîne d'un seul coup.
"""

from __future__ import annotations

import json
import logging

from flask import Flask, g, has_request_context


class CorrelationIdFilter(logging.Filter):
    """Injecte le correlation_id courant dans chaque enregistrement de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = g.get("correlation_id", "-") if has_request_context() else "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # ensure_ascii=False : on garde les messages français lisibles.
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(app.config.get("LOG_LEVEL", "INFO"))
