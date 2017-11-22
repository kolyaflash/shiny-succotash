from .common import *

APP_LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')
DEFAULT_ENTITY_ID = 1

SERVICES_PIPELINE_MIDDLEWARES.remove('sgateway.middlewares.caching.CacheMiddleware')
