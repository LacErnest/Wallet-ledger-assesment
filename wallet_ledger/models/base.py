"""Briques de colonnes partagées par les modèles (principe DRY).

Centraliser ces choix (type monétaire, horodatage, énumérations) garantit que tous
les modèles parlent le même langage : un montant stocké ici a la même précision que
là, et une devise est toujours validée de la même façon.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Enum as SAEnum

from wallet_ledger.extensions import db

# Précision large et fixe : 8 décimales couvrent même les actifs très divisibles,
# sans jamais recourir au flottant. Money ré-arrondit selon la devise.
MONEY_NUMERIC = db.Numeric(precision=28, scale=8)


def utcnow() -> datetime:
    """Horodatage en UTC : un grand livre lu depuis plusieurs fuseaux doit rester cohérent."""
    return datetime.now(UTC)


def uuid_pk():
    """Clé primaire opaque : un identifiant non devinable évite d'exposer des volumes métier."""
    return db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def enum_column(enum_cls: type[StrEnum], **kwargs):
    """Stocke une énumération en VARCHAR contrôlé (CHECK) plutôt qu'en type natif PG :
    plus simple à faire évoluer en migration, tout en interdisant les valeurs hors liste."""
    return db.Column(
        SAEnum(
            enum_cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]
        ),
        **kwargs,
    )
