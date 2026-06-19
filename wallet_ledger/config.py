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
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

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

    # API de change externe. Vide => taux de repli intégrés (le système reste
    # utilisable hors-ligne, sans dépendre d'un tiers).
    FX_API_URL = os.environ.get("FX_API_URL", "")
    FX_API_KEY = os.environ.get("FX_API_KEY", "")

    # Fournisseurs de paiement : Stripe (cartes) et PawaPay (mobile money MTN/Orange).
    # Le secret de webhook prouve que la confirmation vient bien du fournisseur ;
    # sans secret valide on refuse de créditer (sécurité « fail closed »).
    STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    PAWAPAY_BASE_URL = os.environ.get("PAWAPAY_BASE_URL", "https://api.sandbox.pawapay.io")
    PAWAPAY_API_TOKEN = os.environ.get("PAWAPAY_API_TOKEN", "")
    PAWAPAY_WEBHOOK_SECRET = os.environ.get("PAWAPAY_WEBHOOK_SECRET", "")

    PAYPAL_API_BASE = os.environ.get("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")
    PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
    PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")
    PAYPAL_WEBHOOK_SECRET = os.environ.get("PAYPAL_WEBHOOK_SECRET", "")

    # Expéditeurs par défaut des notifications (email / SMS).
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@wallet.local")
    SMS_FROM = os.environ.get("SMS_FROM", "Wallet")


class TestConfig(Config):
    TESTING = True
    # Conteneurs jetables dédiés (profil "test" de docker compose), isolés du dev.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://wallet:wallet@localhost:5434/wallet_test",
    )
    REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6381/0")

    # Les tests doivent être hermétiques : aucun appel réseau réel. On vide les clés
    # API (mode hors-ligne simulé) mais on fixe des secrets de webhook déterministes
    # pour pouvoir vérifier les signatures.
    STRIPE_API_KEY = ""
    STRIPE_WEBHOOK_SECRET = "whsec_test"
    PAWAPAY_API_TOKEN = ""
    PAWAPAY_WEBHOOK_SECRET = "pawapay_whsec_test"
    PAYPAL_CLIENT_ID = ""
    PAYPAL_SECRET = ""
    PAYPAL_WEBHOOK_SECRET = "paypal_whsec_test"
    FX_API_URL = ""
