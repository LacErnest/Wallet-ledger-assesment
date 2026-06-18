"""Schémas de validation des requêtes (marshmallow).

On valide à la frontière HTTP : un montant mal formé ou une devise absente doit être
rejeté AVANT d'atteindre le domaine. Les montants sont lus en chaîne puis convertis en
Decimal — jamais en flottant.
"""

from __future__ import annotations

from marshmallow import Schema, fields, validate


class CreateAccountSchema(Schema):
    owner_id = fields.String(required=True, validate=validate.Length(min=1))
    currency = fields.String(required=True, validate=validate.Length(equal=3))


class TransferSchema(Schema):
    sender_account_number = fields.String(required=True)
    receiver_account_number = fields.String(required=True)
    amount = fields.Decimal(required=True, as_string=True)


class DepositSchema(Schema):
    account_number = fields.String(required=True)
    amount = fields.Decimal(required=True, as_string=True)
    provider = fields.String(required=True)
    # Champs propres au mobile money (PawaPay) : opérateur et numéro du payeur.
    operator = fields.String(required=False)
    phone_number = fields.String(required=False)


class FxRateSchema(Schema):
    from_currency = fields.String(required=True, data_key="from", validate=validate.Length(equal=3))
    to_currency = fields.String(required=True, data_key="to", validate=validate.Length(equal=3))


class FxConvertSchema(Schema):
    from_currency = fields.String(required=True, data_key="from", validate=validate.Length(equal=3))
    to_currency = fields.String(required=True, data_key="to", validate=validate.Length(equal=3))
    amount = fields.Decimal(required=True, as_string=True)


class FxTransferSchema(TransferSchema):
    pass
