from .common import *

IS_LOCAL = True

APP_LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')
DEFAULT_ENTITY_ID = 1

SERVICES_PIPELINE_MIDDLEWARES.remove('sgateway.middlewares.caching.CacheMiddleware')

DB_CONFIG['connection_string'] = os.getenv('DB_URL', 'postgresql://localhost:5432/sgateway_local')
