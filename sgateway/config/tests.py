from .common import *

IS_TEST = True
CREDENTIALS_DIR_PATH = None

APP_LOG_LEVEL = 'ERROR'

AMQP_URL = None

SERVICES_PIPELINE_MIDDLEWARES = []
INSTALLED_SERVICES = []

CENTRAL_CONFIG_CLASS = 'middlewares.central_config.DummyCentralConfig'

DB_CONFIG['connection_string'] = os.getenv('DB_URL', 'postgresql://localhost:5432/')
DB_CONFIG['create_tmp_db'] = True  # See :ref:`sgateway.core.db.GatewayDB`

# See pytest-redis
REDIS_CONFIG = {
    'HOST': '127.0.0.1',
    'PORT': '8899',
}
