#!/usr/bin/env sh
# Au démarrage on applique les migrations avant de servir : le schéma doit toujours
# être à jour pour qu'aucune écriture comptable ne parte sur une table obsolète.
set -e

uv run flask --app wallet_ledger db upgrade
# On démarre via la fabrique applicative : robuste quel que soit le répertoire courant.
exec uv run gunicorn --bind 0.0.0.0:8000 --workers 4 "wallet_ledger:create_app()"
