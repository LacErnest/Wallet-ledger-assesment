"""Configuration applicative.

On centralise ici la lecture de l'environnement : aucun secret n'est codé en dur,
ce qui permet de déployer la même image en dev, test et production en ne changeant
que les variables d'environnement.
"""

import os

from dotenv import load_dotenv

# On charge le `.env` local s'il existe ; en production les variables sont déjà
# injectées par l'orchestrateur, donc l'absence de fichier n'est pas une erreur.
load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # PostgreSQL est la source de vérité : on y tient pour le verrouillage de lignes
    # qui empêche deux transferts simultanés de rendre un solde négatif.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://wallet:wallet@localhost:5433/wallet"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Redis n'accélère que les lectures de solde ; il n'est jamais la référence.
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6380/0")
    # Durée de vie courte du cache : en cas d'incident, un solde au plus faux
    # pendant quelques secondes vaut mieux qu'un solde faux indéfiniment.
    BALANCE_CACHE_TTL_SECONDS = int(os.environ.get("BALANCE_CACHE_TTL_SECONDS", "30"))

    # Au-delà de ce nombre d'écritures, on fige un instantané de solde pour ne pas
    # resommer des millions de lignes à chaque lecture.
    SNAPSHOT_EVERY_N_ENTRIES = int(os.environ.get("SNAPSHOT_EVERY_N_ENTRIES", "100"))

    # Un conflit de verrou optimiste est normal sous forte concurrence : on retente
    # quelques fois avant d'abandonner plutôt que de faire échouer l'utilisateur.
    MAX_WRITE_RETRIES = int(os.environ.get("MAX_WRITE_RETRIES", "3"))

    # API de change externe. Vide => taux de repli intégrés (le système reste
    # utilisable hors-ligne, sans dépendre d'un tiers).
    FX_API_URL = os.environ.get("FX_API_URL", "")
    FX_API_KEY = os.environ.get("FX_API_KEY", "")


class TestConfig(Config):
    TESTING = True
    # Base dédiée : les tests ne doivent jamais toucher les données de dev.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://wallet:wallet@localhost:5433/wallet_test",
    )
