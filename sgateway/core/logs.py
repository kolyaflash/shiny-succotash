import logging

from sanic.config import LOGGING

app_logger = logging.getLogger('sanic.sgateway')
service_request_logger = logging.getLogger('service_request')

"""
TODO: Integrate Raven 
https://docs.sentry.io/clients/python/integrations/logging/
https://github.com/getsentry/raven-aiohttp
"""


# logging.basicConfig(level=logging.INFO)
# logging.getLogger('sl_mqlib').setLevel(logging.DEBUG)
# logging.getLogger('pika').setLevel(logging.DEBUG)

def get_config(sanic_level='INFO', disable_sanic_handlers=False):
    # Default sanic loggers
    LOGGING['loggers']['sanic']['level'] = sanic_level
    LOGGING['loggers']['network']['level'] = sanic_level

    if disable_sanic_handlers:
        LOGGING['loggers']['sanic']['handlers'] = []
        LOGGING['loggers']['network']['handlers'] = []

    return LOGGING
