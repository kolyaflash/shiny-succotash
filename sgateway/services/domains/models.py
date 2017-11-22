import time

from sqlalchemy import Table, Column, Integer, String, JSON, Boolean, ForeignKey, Numeric, Index, UniqueConstraint

from sgateway.core.db import metadata

IntentionTable = Table(
    'domain_register_intention', metadata,
    Column('id', Integer, primary_key=True),
    Column('domain', String(255), nullable=False),
    Column('entity_id', String(60)),
    Column('provider', String(60), nullable=False),
    Column('registration_data', JSON, nullable=True),
    Column('finished', Boolean, default=False),
    Column('timestamp', Integer, nullable=False, default=time.time),
)

Index('already_purchased', IntentionTable.c.domain, IntentionTable.c.finished,
      unique=True,
      postgresql_where=(IntentionTable.c.finished == True)),

RegistrantAccountTable = Table(
    'domain_registrant_account', metadata,
    Column('id', Integer, primary_key=True),
    Column('entity_id', String(60), nullable=False),
    Column('provider', String(60), nullable=False),
    Column('account_data', JSON),
    Column('ip_address', String(60)),
    Column('created_at', Integer, nullable=False, default=time.time),
    UniqueConstraint('entity_id', 'provider', name='uix_1')
)

DomainsPurchasesTable = Table(
    'domain_purchase', metadata,
    Column('id', Integer, primary_key=True),
    Column('intention_id', Integer, ForeignKey(IntentionTable.c.id), nullable=False, unique=True),
    Column('account_id', Integer, ForeignKey(RegistrantAccountTable.c.id), nullable=True),
    Column('provider_purchase_uid', String(64), nullable=True),
    Column('price', Numeric()),
    Column('price_currency', String(3)),
    Column('post_registration_complete', Boolean, default=False),
    Column('timestamp', Integer, nullable=False, default=time.time),
)
