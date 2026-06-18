"""Tests de santé et de journalisation structurée."""

import json
import logging

from wallet_ledger.infrastructure.logging import CorrelationIdFilter, JsonFormatter


class TestHealth:
    def test_liveness(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_readiness_reports_dependencies(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["redis"] == "ok"


class TestStructuredLogging:
    def test_json_formatter_includes_correlation_id(self):
        record = logging.LogRecord("test", logging.INFO, "path", 1, "hello", None, None)
        # Hors contexte de requête, le correlation_id retombe sur "-".
        CorrelationIdFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))

        assert payload["message"] == "hello"
        assert payload["level"] == "INFO"
        assert payload["correlation_id"] == "-"
