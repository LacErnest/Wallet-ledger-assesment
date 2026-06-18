"""Documentation interactive de l'API (Swagger UI).

On sert la spec OpenAPI en JSON et une interface Swagger UI pour explorer et essayer
les endpoints, à la manière d'une référence d'API de fournisseur (type Stripe).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from wallet_ledger.api.openapi import build_spec

bp = Blueprint("docs", __name__)

# Swagger UI chargé depuis un CDN : pas de dépendance Python supplémentaire à embarquer.
_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>wallet-ledger API</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/api/v1/openapi.json",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis],
      layout: "BaseLayout"
    });
  </script>
</body>
</html>"""


@bp.get("/openapi.json")
def openapi_json():
    return jsonify(build_spec())


@bp.get("/docs")
def swagger_ui():
    return Response(_SWAGGER_HTML, mimetype="text/html")
