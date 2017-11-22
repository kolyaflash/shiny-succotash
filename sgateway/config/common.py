import os
from pathlib import Path

BASE_PATH = Path(__file__).parents[2]
APP_PATH = Path(__file__).parents[1]

CREDENTIALS_DIR_PATH = Path(__file__).parents[0].joinpath('credentials').resolve()

APP_LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

INTERNAL_GATEWAY_KEY = os.getenv('INTERNAL_GATEWAY_KEY', 'SECRET_KEY_HERE')

INSTALLED_SERVICES = [
    'sgateway.services.email.service',
    'sgateway.services.currency_exchange.service',
    'sgateway.services.sms.service',
    'sgateway.services.docs.service',
    'sgateway.services.domains.service',
    'sgateway.services.tax_rates.service',
]

DB_CONFIG = {
    'connection_string': os.getenv('DB_URL', 'postgresql://localhost:5432/sgateway_default'),
    'create_tmp_db': False,  # Only for testing/debugging.
}

REDIS_CONFIG = {
    'HOST': os.getenv('REDIS_HOST', 'localhost'),
    'PORT': int(os.getenv('REDIS_PORT', 6379)),
    'DB': int(os.getenv('REDIS_DB', 0)),
}

# Ordering matters.
SERVICES_PIPELINE_MIDDLEWARES = [
    'sgateway.middlewares.logger.RequestStartTimeMiddleware',  # Comes first
    'sgateway.middlewares.authentication.AuthMiddleware',
    'sgateway.middlewares.idempotency_key.IdempotencyKeyMiddleware',
    'sgateway.middlewares.rate_limiting.RateLimitingMiddleware',
    'sgateway.middlewares.billing.BillingMiddleware',
    'sgateway.middlewares.caching.CacheMiddleware',
    'sgateway.middlewares.logger.LoggerMiddleware',  # Comes last
]

CENTRAL_CONFIG_CLASS = 'sgateway.middlewares.central_config.DummyCentralConfig'

AMQP_URL = os.getenv('MESSAGE_BUS_AMQP_URL', None)
SERVICE_MQ_LOGGING = False

# Services config
DOCS_API_URL = os.getenv('DOCS_API_URL', 'https://docs.semilimes.info')

SEMILIMES_CONTACT = {
    "first_name": "",
    "last_name": "",
    "middle_name": "",
    "organization": "",
    "email": "",
    "phone": {
        "country_code": "",
        "global_number": "",
    },
    "mailing_address": {
        "address1": "",
        "address2": "",
        "city": "",
        "state": "",
        "postal_code": "",
        "country": ""
    }
}

GODADDY_API_URL = "https://api.ote-godaddy.com/v1/"  # Test API
AVATAX_API_URL = "https://sandbox-rest.avatax.com/api/v2/"  # Test API
TAXJAR_API_URL = "https://api.taxjar.com/v2/"
